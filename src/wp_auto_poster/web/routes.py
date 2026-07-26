"""Flask route registration for WP Auto Poster."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from flask import jsonify, render_template, request

from wp_auto_poster.state.redaction import (
    merge_config_update,
    redact_config,
    redact_preset,
)
from wp_auto_poster.utils.logging import logs_since

LogFunc = Callable[[str, str], None]


@dataclass
class RouteRuntime:
    state: Any
    add_log: LogFunc
    load_site_presets: Callable[[], dict]
    save_site_presets: Callable[[dict], bool]
    save_app_config: Callable[[dict], bool]
    check_ollama: Callable[[], bool]
    run_automation: Callable[[], None]
    get_min_valid_words: Callable[[], int]
    find_content_row_by_post_index: Callable[[int], Optional[int]]
    queue_content_rerender: Callable[[int], bool]
    gemini_available: bool
    playwright_available: bool


def register_routes(app, runtime: RouteRuntime) -> None:
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/status')
    def get_status():
        try:
            since = int(request.args.get("since", 0))
        except (TypeError, ValueError):
            since = 0

        with runtime.state.mutation():
            # Return content_list without full content for performance
            content_list_summary = [
                {
                    "post_index": c.get("post_index", 0),
                    "title": c["title"],
                    "keyword": c["keyword"],
                    "word_count": c["word_count"],
                    "status": c.get("status", "success"),
                    "error_reason": c.get("error_reason", ""),
                    "attempts": c.get("attempts", 1),
                }
                for c in runtime.state.content_list
            ]
            logs = logs_since(runtime.state, since)
            log_seq = getattr(runtime.state, "log_seq", len(logs))

        # Probing Ollama costs a blocking HTTP round-trip; skip it entirely
        # unless Ollama is the selected provider.
        provider = runtime.state.config.get("ai_provider", "ollama")
        ollama_available = runtime.check_ollama() if provider == "ollama" else False

        return jsonify({
            "is_running": runtime.state.is_running,
            "is_paused": runtime.state.is_paused,
            "pause_reason": runtime.state.pause_reason,
            "current_task": runtime.state.current_task,
            "progress": runtime.state.progress,
            "successful_posts": runtime.state.successful_posts,
            "failed_posts": runtime.state.failed_posts,
            "logs": logs,
            "log_seq": log_seq,
            "gemini_available": runtime.gemini_available,
            "ollama_available": ollama_available,
            "playwright_available": runtime.playwright_available,
            "current_phase": runtime.state.current_phase,
            "retry_queue_count": len(runtime.state.retry_queue),
            "content_list": content_list_summary,
            "content_count": len(runtime.state.content_list)
        })

    @app.route('/api/config', methods=['GET', 'POST'])
    def handle_config():
        if request.method == 'POST':
            data = dict(request.json or {})
            if "content_min_valid_words" in data:
                try:
                    data["content_min_valid_words"] = max(1, int(data["content_min_valid_words"]))
                except (TypeError, ValueError):
                    data["content_min_valid_words"] = 1401
            if "content_auto_rerender_retries" in data:
                try:
                    data["content_auto_rerender_retries"] = max(0, int(data["content_auto_rerender_retries"]))
                except (TypeError, ValueError):
                    data["content_auto_rerender_retries"] = 2
            # An empty secret means "keep the stored value" so the UI can render
            # a blank password field without wiping saved credentials.
            data = merge_config_update(runtime.state.config, data)
            runtime.state.config.update(data)
            if runtime.save_app_config(runtime.state.config):
                redacted = redact_config(runtime.state.config)
                return jsonify({"success": True, "data": redacted, **{
                    key: redacted[key] for key in redacted if key.endswith("_set")
                }})
            return jsonify({"success": False, "message": "Could not save config"}), 500
        return jsonify(redact_config(runtime.state.config))

    #: Phases where topic/content indices are locked to a live posting plan.
    POSTING_PHASES = ("creating_posts", "retry_post_queue")

    def _structural_edit_blocked() -> bool:
        """True while the runner is publishing and indices must not shift."""
        return (
            runtime.state.is_running
            and (runtime.state.current_phase or "") in POSTING_PHASES
        )

    @app.route('/api/topics', methods=['GET', 'POST'])
    def handle_topics():
        if request.method == 'POST':
            if _structural_edit_blocked():
                return jsonify({
                    "success": False,
                    "message": "Đang đăng bài — không thể thay đổi danh sách tiêu đề lúc này",
                }), 409
            with runtime.state.mutation():
                runtime.state.topics = request.json.get('topics', [])
                count = len(runtime.state.topics)
            return jsonify({"success": True, "count": count})
        return jsonify(runtime.state.topics)

    @app.route('/api/presets', methods=['GET'])
    def list_presets():
        presets = runtime.load_site_presets()
        return jsonify({"success": True, "presets": list(presets.keys())})

    @app.route('/api/presets/<name>/apply', methods=['POST'])
    def apply_preset(name):
        """Copy a preset into the live config server-side.

        Secrets never travel to the browser: the preset password is merged
        into ``state.config`` here, so the UI only has to refresh the
        non-sensitive fields afterwards.
        """
        presets = runtime.load_site_presets()
        if name not in presets:
            return jsonify({"success": False, "message": "Preset not found"}), 404

        runtime.state.config.update(presets[name])
        if not runtime.save_app_config(runtime.state.config):
            return jsonify({"success": False, "message": "Could not save config"}), 500

        runtime.add_log(f"Đã áp dụng cấu hình site: {name}", "info")
        return jsonify({
            "success": True,
            "message": f"Đã tải cấu hình: {name}",
            "data": redact_config(runtime.state.config),
        })

    @app.route('/api/presets/<name>', methods=['GET', 'PUT', 'DELETE'])
    def manage_preset(name):
        presets = runtime.load_site_presets()

        if request.method == 'GET':
            if name in presets:
                return jsonify({"success": True, "data": redact_preset(presets[name])})
            return jsonify({"success": False, "message": "Preset not found"})

        elif request.method == 'PUT':
            data = request.json or {}
            try:
                content_min_valid_words = max(1, int(data.get("content_min_valid_words", 1401)))
            except (TypeError, ValueError):
                content_min_valid_words = 1401
            # A blank incoming password means "keep what is stored". Fall back
            # to the preset's own password first, then to the live config, so
            # that "save current settings as a new preset" captures the
            # password the user is actually working with.
            existing = presets.get(name, {})
            fallback = existing if existing.get("wp_password") else runtime.state.config
            merged_secrets = merge_config_update(fallback, {
                "wp_password": data.get("wp_password", ""),
            })
            presets[name] = {
                "wp_username": data.get("wp_username", ""),
                "wp_password": merged_secrets.get("wp_password", ""),
                "wp_login_url": data.get("wp_login_url", ""),
                "wp_admin_url": data.get("wp_admin_url", ""),
                "category_name": data.get("category_name", "Tin tức"),
                "gemini_prompt": data.get("gemini_prompt", ""),
                "auto_set_seo_keyword": data.get("auto_set_seo_keyword", True),
                "auto_insert_inline_images": data.get("auto_insert_inline_images", True),
                "auto_set_featured_image": data.get("auto_set_featured_image", False),
                "auto_select_category": data.get("auto_select_category", True),
                "auto_add_tags": data.get("auto_add_tags", True),
                "content_min_valid_words": content_min_valid_words,
            }
            if runtime.save_site_presets(presets):
                return jsonify({"success": True, "message": f"Preset '{name}' saved"})
            return jsonify({"success": False, "message": "Could not save preset"})

        elif request.method == 'DELETE':
            if name in presets:
                del presets[name]
                if runtime.save_site_presets(presets):
                    return jsonify({"success": True, "message": f"Preset '{name}' deleted"})
            return jsonify({"success": False, "message": "Preset not found"})

    def _reindex_post_indices_after_delete(removed_post_index: int) -> None:
        """Shift every post-index reference down after a post is removed.

        ``content_list``, ``skip_post_indices`` and ``retry_queue`` all key off
        ``post_index``. Re-indexing only ``content_list`` (the previous
        behaviour) left the other two pointing at the wrong article.
        Callers must already hold ``state.lock``.
        """
        for item in runtime.state.content_list:
            item_post_index = int(item.get("post_index", -1))
            if item_post_index > removed_post_index:
                item["post_index"] = item_post_index - 1

        runtime.state.skip_post_indices = {
            idx - 1 if idx > removed_post_index else idx
            for idx in runtime.state.skip_post_indices
            if idx != removed_post_index
        }

        remaining_queue = []
        for item in runtime.state.retry_queue:
            queued_index = int(item.get("post_index", -1))
            if queued_index == removed_post_index:
                continue
            if queued_index > removed_post_index:
                item = {**item, "post_index": queued_index - 1}
            remaining_queue.append(item)
        runtime.state.retry_queue = remaining_queue

    @app.route('/api/content/<int:index>')
    def get_content(index):
        if 0 <= index < len(runtime.state.content_list):
            return jsonify({
                "success": True,
                "data": runtime.state.content_list[index]
            })
        return jsonify({"success": False, "message": "Content not found"})

    @app.route('/api/content/<int:index>', methods=['PUT'])
    def update_content(index):
        data = request.get_json(silent=True) or {}
        if 'content' not in data:
            return jsonify({"success": False, "message": "Content not found"})

        with runtime.state.mutation():
            if not (0 <= index < len(runtime.state.content_list)):
                return jsonify({"success": False, "message": "Content not found"})

            new_content = data['content']
            # Recalculate word count
            text_only = re.sub(r'<[^>]*>', ' ', new_content)
            word_count = len(text_only.split())

            row = runtime.state.content_list[index]
            row['content'] = new_content
            row['word_count'] = word_count
            min_valid_words = runtime.get_min_valid_words()
            if word_count < min_valid_words:
                row['status'] = "failed"
                row['error_reason'] = (
                    f"chỉ có {word_count}/{min_valid_words} từ (cập nhật thủ công)"
                )
            else:
                row['status'] = "success"
                row['error_reason'] = ""
            row['attempts'] = row.get('attempts', 1)

            # Also update generated_contents for WordPress posting
            post_index = int(row.get("post_index", index))
            if 0 <= post_index < len(runtime.state.generated_contents):
                runtime.state.generated_contents[post_index] = new_content

        runtime.add_log(f"Content #{index + 1} đã được cập nhật ({word_count} từ)", "info")
        return jsonify({"success": True, "word_count": word_count})

    @app.route('/api/content/<int:index>', methods=['DELETE'])
    def delete_content(index):
        if _structural_edit_blocked():
            return jsonify({
                "success": False,
                "message": "Đang đăng bài — không thể xóa nội dung lúc này",
            }), 409

        with runtime.state.mutation():
            if not (0 <= index < len(runtime.state.content_list)):
                return jsonify({"success": False, "message": "Content not found"})

            row = runtime.state.content_list[index]
            deleted_title = row['title']
            post_index = int(row.get("post_index", index))
            del runtime.state.content_list[index]

            # Also remove from generated_contents/topics by real post index
            if 0 <= post_index < len(runtime.state.generated_contents):
                del runtime.state.generated_contents[post_index]

            if 0 <= post_index < len(runtime.state.topics):
                del runtime.state.topics[post_index]

            _reindex_post_indices_after_delete(post_index)

        runtime.add_log(f"Đã xóa: {deleted_title}", "warning")
        return jsonify({"success": True})


    def _handle_rerender_request(content_row_index: int, skip_post: bool):
        if not runtime.state.is_running:
            return {"success": False, "message": "Chỉ có thể rend lại khi automation đang chạy"}, 400

        if not (0 <= content_row_index < len(runtime.state.content_list)):
            return {"success": False, "message": "Content không tồn tại"}, 404

        row = runtime.state.content_list[content_row_index]
        post_index = int(row.get("post_index", content_row_index))
        phase = runtime.state.current_phase or ""

        if phase in ("generating_content", "retry_content_queue"):
            if runtime.queue_content_rerender(post_index):
                runtime.add_log(
                    f"Đã thêm vào hàng chờ rend lại content: bài {post_index + 1} - {row.get('title', '')}",
                    "warning",
                )
                return {"success": True, "queued": True, "message": "Đã thêm vào hàng chờ rend lại"}, 200
            return {"success": True, "queued": False, "message": "Bài này đã có trong hàng chờ rend lại"}, 200

        if phase in ("creating_posts", "retry_post_queue"):
            if not skip_post:
                return {
                    "success": False,
                    "requires_confirmation": True,
                    "message": "Đang trong quá trình đăng bài. Bạn có muốn bỏ qua bài này để không đăng không?"
                }, 409

            runtime.state.skip_post_indices.add(post_index)
            if 0 <= post_index < len(runtime.state.generated_contents):
                runtime.state.generated_contents[post_index] = None
            runtime.add_log(
                f"Đánh dấu bỏ qua đăng bài {post_index + 1} theo yêu cầu người dùng",
                "warning",
            )
            return {
                "success": True,
                "queued": False,
                "message": "Đã đánh dấu bỏ qua đăng bài này. Hãy rend lại ở pha tạo content."
            }, 200

        return {
            "success": False,
            "message": "Chỉ có thể thêm hàng chờ rend lại khi đang ở pha tạo content"
        }, 400


    @app.route('/api/content/<int:index>/rerender', methods=['POST'])
    def rerender_content(index):
        data = request.get_json(silent=True) or {}
        skip_post = bool(data.get("skip_post", False))
        payload, status_code = _handle_rerender_request(index, skip_post)
        return jsonify(payload), status_code


    @app.route('/api/retry-queue', methods=['POST'])
    def enqueue_retry_action():
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        try:
            post_index = int(data.get("post_index", 0)) - 1
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "post_index không hợp lệ"}), 400
        skip_post = bool(data.get("skip_post", False))

        if action != "content":
            return jsonify({"success": False, "message": "Hiện chỉ hỗ trợ retry content"}), 400
        if post_index < 0:
            return jsonify({"success": False, "message": "post_index không hợp lệ"}), 400

        row_index = runtime.find_content_row_by_post_index(post_index)
        if row_index is None:
            return jsonify({"success": False, "message": "Không tìm thấy content tương ứng"}), 404
        payload, status_code = _handle_rerender_request(row_index, skip_post)
        return jsonify(payload), status_code

    @app.route('/api/start', methods=['POST'])
    def start_automation():
        if runtime.state.is_running:
            return jsonify({"success": False, "message": "Already running"})

        if not runtime.state.topics:
            return jsonify({"success": False, "message": "No topics configured"})

        provider = runtime.state.config.get("ai_provider", "ollama")

        if provider == "ollama":
            if not runtime.check_ollama():
                return jsonify({"success": False, "message": "Ollama is not running! Please start Ollama first (run: ollama serve)"})
        elif provider == "gemini":
            if not runtime.state.config.get("gemini_api_key"):
                return jsonify({"success": False, "message": "Gemini API key not configured"})

        if not runtime.state.config.get("wp_username"):
            return jsonify({"success": False, "message": "WordPress credentials not configured"})

        data = request.get_json() or {}
        runtime.state.config["schedule_start_date"] = data.get("schedule_start_date", "")
        runtime.state.config["schedule_end_date"] = data.get("schedule_end_date", "")

        runtime.state.reset()

        thread = threading.Thread(target=runtime.run_automation)
        thread.daemon = True
        thread.start()

        return jsonify({"success": True, "message": "Started"})

    @app.route('/api/stop', methods=['POST'])
    def stop_automation():
        runtime.state.request_stop()
        runtime.add_log("Đã dừng bởi người dùng", "warning")
        return jsonify({"success": True})

    @app.route('/api/pause', methods=['POST'])
    def pause_automation():
        if not runtime.state.is_running:
            return jsonify({"success": False, "message": "Not running"})
        runtime.state.is_paused = True
        runtime.state.pause_reason = "Tạm dừng bởi người dùng"
        runtime.add_log("Đã tạm dừng", "warning")
        return jsonify({"success": True})

    @app.route('/api/resume', methods=['POST'])
    def resume_automation():
        if not runtime.state.is_running:
            return jsonify({"success": False, "message": "Not running"})
        runtime.state.is_paused = False
        runtime.state.pause_reason = ""
        runtime.add_log("Tiếp tục thực thi...", "success")
        return jsonify({"success": True})

    @app.route('/api/ollama/start', methods=['POST'])
    def start_ollama():
        try:
            import subprocess
            result = subprocess.run(
                ["brew", "services", "start", "ollama"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                # Wait a moment for service to start
                time.sleep(3)
                if runtime.check_ollama():
                    return jsonify({"success": True, "message": "Ollama service started successfully"})
                else:
                    return jsonify({"success": False, "message": "Ollama started but not responding yet. Please wait a moment."})
            else:
                return jsonify({"success": False, "message": f"Failed to start Ollama: {result.stderr}"})

        except subprocess.TimeoutExpired:
            return jsonify({"success": False, "message": "Timeout starting Ollama service"})
        except Exception as e:
            return jsonify({"success": False, "message": f"Error: {str(e)}"})

    @app.route('/api/ollama/stop', methods=['POST'])
    def stop_ollama():
        try:
            import subprocess
            result = subprocess.run(
                ["brew", "services", "stop", "ollama"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                time.sleep(2)
                return jsonify({"success": True, "message": "Ollama service stopped"})
            else:
                return jsonify({"success": False, "message": f"Failed to stop Ollama: {result.stderr}"})

        except subprocess.TimeoutExpired:
            return jsonify({"success": False, "message": "Timeout stopping Ollama service"})
        except Exception as e:
            return jsonify({"success": False, "message": f"Error: {str(e)}"})

    @app.route('/api/ollama/status', methods=['GET'])
    def ollama_status():
        is_running = runtime.check_ollama()
        return jsonify({
            "running": is_running,
            "status": "running" if is_running else "stopped"
        })
