# WP Auto Poster — Kế hoạch cải thiện toàn diện

> Phạm vi: sửa toàn bộ lỗi đã phát hiện, cải thiện hiệu suất, và xử lý nợ kỹ thuật.
> Trạng thái khởi điểm: 87 unit test pass, `./scripts/check.sh` xanh.

## Trạng thái: HOÀN THÀNH (2026-07-26)

| Chỉ số | Trước | Sau |
| --- | --- | --- |
| Test | 87 | **193** (183 unit + 10 integration) |
| Lỗi ruff | 231 | **0** (đã bật thành lỗi cứng) |
| `app.py` | 976 dòng | **436 dòng** |
| Hàm chết trong `app.py` | 43 | 0 |
| Payload `/api/status` (400 log) | 47.002 bytes/giây | **311 bytes/giây** |
| Mật khẩu WP qua HTTP | có | **không** |
| Nền tảng chạy được | chỉ macOS | macOS + Windows + Linux |

Các mục có thay đổi so với kế hoạch ban đầu được đánh dấu **Đính chính** ngay
tại phần tương ứng bên dưới.

## Quyết định đã chốt

| Vấn đề | Lựa chọn |
| --- | --- |
| Secrets | Mask ở API + bỏ khỏi localStorage. Giữ `app_config.json` như hiện tại, không đổi workflow. |
| Nền tảng | Hỗ trợ đầy đủ macOS + Windows + Linux. |
| Gemini API | Giữ provider, migrate `google-generativeai` → `google-genai`. |

## Nguyên tắc thực thi

- Mỗi phase là một commit độc lập, revert được riêng lẻ.
- Kết thúc mỗi phase phải chạy `./scripts/check.sh` xanh trước khi sang phase kế.
- Logic thuần được thêm test cùng lúc với fix, không để sau.
- Không đổi shape của API response trừ chỗ bắt buộc (config/preset secrets) — và khi đổi thì sửa frontend đi kèm trong cùng commit.
- Xóa code chết theo lô nhỏ, chạy check sau mỗi lô.

---

## Phase 0 — Dựng lưới an toàn

Làm trước tiên để các phase sau không âm thầm phá vỡ thứ gì.

1. **`pyproject.toml`**: thêm `[project]` (name, version, `requires-python = ">=3.9"`, dependencies), `[build-system]` setuptools, `[tool.setuptools.packages.find] where = ["src"]`, và optional group `dev`.
2. **Khai báo dependency còn thiếu**: `requests` hiện **không có trong `requirements.txt`** — nó chỉ tồn tại nhờ transitive từ `google-api-core` (kéo theo bởi `google-generativeai`). Provider Ollama phụ thuộc trực tiếp vào nó (`providers/ollama.py:7`). Khi Phase 4 migrate sang `google-genai` (dùng httpx thay vì requests), `requests` có thể biến mất và **Ollama gãy im lặng**. Phải khai báo tường minh ngay từ Phase 0.
3. Tách `requirements.txt` (runtime) và `requirements-dev.txt` (pytest, ruff).
4. **`scripts/check.sh`**: thêm `ruff check --exit-zero` (chỉ báo cáo ở phase này; siết thành lỗi cứng ở Phase 5).
5. **`.gitignore`**: thêm `.ruff_cache/`, `screenshots/`.

**Verify:** `pip install -e ".[dev]"` thành công, 87 test vẫn pass.

---

## Phase 1 — Bảo mật

### 1.1 Không rò rỉ secrets qua API

Hiện `GET /api/config` ([routes.py:89](../src/wp_auto_poster/web/routes.py#L89)) trả nguyên `state.config` gồm `wp_password` và `gemini_api_key`. `GET /api/presets/<name>` ([routes.py:107-110](../src/wp_auto_poster/web/routes.py#L107-L110)) cũng trả password của preset.

- Thêm `src/wp_auto_poster/state/redaction.py`:
  - `SECRET_KEYS = {"wp_password", "gemini_api_key"}`
  - `redact_config(config)` → bỏ secrets, thêm cờ `wp_password_set: bool`, `gemini_api_key_set: bool`
  - `merge_config_update(current, incoming)` → nếu secret gửi lên rỗng/`None` thì **giữ giá trị cũ**
- `GET /api/config` trả `redact_config(...)`; `POST /api/config` dùng `merge_config_update(...)`.
- Áp dụng y hệt cho `GET`/`PUT /api/presets/<name>`.

**Frontend `static/js/config.js` (bắt buộc sửa kèm, nếu không sẽ ghi đè mật khẩu bằng chuỗi rỗng):**
- Ô password để trống, `placeholder="(đã lưu — để trống nếu không đổi)"`, dùng cờ `wp_password_set` để hiện badge "đã lưu".
- Bỏ `wp_password` và `gemini_api_key` khỏi object ghi vào `localStorage` ([config.js:51](../static/js/config.js#L51)) và khỏi nhánh đọc lại ([config.js:81-82](../static/js/config.js#L81-L82)). Hiện mật khẩu đang nằm plaintext trong localStorage — bất kỳ extension hay XSS nào cũng đọc được.

### 1.2 Siết CORS và chống DNS rebinding

`CORS(app)` ([app_factory.py:26](../src/wp_auto_poster/web/app_factory.py#L26)) mở cho mọi origin. Đây là thứ biến 1.1 từ "hơi bất cẩn" thành "lỗ hổng thật": bất kỳ trang web nào bạn mở đều `fetch('http://localhost:5001/api/config')` được.

- `CORS(app, origins=["http://localhost:5001", "http://127.0.0.1:5001"])`.
- Thêm `before_request` chặn request có `Host` header không thuộc `localhost`/`127.0.0.1` (chống DNS rebinding).
- `after_request` set `X-Content-Type-Options: nosniff`.

### 1.3 Tắt debug và reloader

[app.py:969](../app.py#L969) đang `app.run(debug=True)`. Ngoài rủi ro Werkzeug debugger console, **auto-reloader restart process mỗi khi save file → giết automation đang chạy giữa chừng.**

```python
app.run(
    host=os.getenv("WP_HOST", "127.0.0.1"),
    port=int(os.getenv("WP_PORT", "5001")),
    debug=os.getenv("WP_DEBUG") == "1",
    use_reloader=False,   # tắt cứng kể cả khi debug bật
    threaded=True,
)
```

### 1.4 Ghi file config an toàn

`config_store.py` và `presets.py`:
- Ghi atomic: ghi ra `path + ".tmp"` rồi `os.replace()` → không mất config khi crash giữa chừng.
- `os.chmod(path, 0o600)` sau khi ghi.

**Test mới:** `tests/unit/test_config_redaction.py` (redact, merge giữ password khi gửi rỗng, preset redact), cập nhật `test_web_routes.py`.

---

## Phase 2 — Bug chặn và bug làm hỏng dữ liệu

### 2.1 `KeyError: 'headless_mode'` khi clone mới

[runner.py:129](../src/wp_auto_poster/automation/runner.py#L129) đọc `config["headless_mode"]` nhưng key này không có trong `DEFAULT_CONFIG` ([app_state.py:8-33](../src/wp_auto_poster/state/app_state.py#L8-L33)). Máy hiện tại chạy được chỉ vì `app_config.json` đã có sẵn key. Người clone mới về sẽ crash ngay lúc mở browser.

- Thêm `"headless_mode": False` vào `DEFAULT_CONFIG`.
- Rà toàn bộ truy cập config bằng index → đổi sang `.get()`: `runner.py:129`, `runner.py:87` (`delay_between_requests`), `editor.py:26` (`wp_admin_url` — nếu rỗng thì log lỗi rõ ràng thay vì `KeyError`).
- Test: `test_automation_runner.py` thêm case config thiếu `headless_mode` → không raise.

### 2.2 Thread-safety cho global `state`

Không có `threading.Lock` nào trong toàn bộ codebase. `state` bị mutate đồng thời bởi automation thread và các Flask request thread.

- Thêm `threading.RLock` vào `AppState`, expose context manager `state.mutation()`.
- Bọc lock quanh mutation của list dùng chung: `update_content`, `delete_content`, `handle_topics` POST, `upsert_content_row`, `process_content_retry_queue`.
- **Quan trọng hơn lock — chặn sửa cấu trúc khi đang đăng bài:** `DELETE /api/content/<i>` ([routes.py:184-207](../src/wp_auto_poster/web/routes.py#L184-L207)) xóa phần tử khỏi `state.topics`/`state.generated_contents` trong khi runner đang lặp `zip(...)` ([runner.py:241](../src/wp_auto_poster/automation/runner.py#L241)) → lệch index, đăng nhầm hoặc sót bài. Ở phase `creating_posts` → trả 409 kèm thông báo. Ở phase `generating_content` → cho phép nhưng làm dưới lock.
- Runner chụp snapshot `topics`/`generated_contents` một lần dưới lock trước vòng lặp, thay vì `zip` trực tiếp trên list sống.

### 2.3 Lệnh Stop bị nuốt do `reset()` gọi hai lần

`/api/start` gọi `state.reset()` ([routes.py:310](../src/wp_auto_poster/web/routes.py#L310)), rồi `run_automation` gọi lại ([runner.py:36](../src/wp_auto_poster/automation/runner.py#L36)). Bấm Stop đúng khe giữa hai lệnh → reset thứ hai set `is_running = True` trở lại, lệnh Stop mất.

- Bỏ `state.reset()` trong `run_automation`, giữ duy nhất ở `/api/start`.
- Thêm cờ `state.stop_requested`; `/api/stop` set cờ, `wait_if_paused` và các vòng lặp kiểm tra cờ này.

### 2.4 `skip_post_indices` và `retry_queue` lệch sau khi xóa content

`delete_content` re-index `content_list` ([routes.py:200-203](../src/wp_auto_poster/web/routes.py#L200-L203)) nhưng **không** re-index `state.skip_post_indices` và `state.retry_queue` — cả hai đều dùng `post_index`. Sau một lần xóa, các index này trỏ sai bài.

- Re-index cả ba theo cùng quy tắc.
- Test: `tests/unit/test_content_delete_reindex.py`.

### 2.5 Provider không hợp lệ rơi ngầm về Gemini API

[generation.py:63](../src/wp_auto_poster/content/generation.py#L63) — mọi tên provider lạ đều fallthrough xuống `gemini_api_func`, kể cả lỗi gõ nhầm.

- Thêm nhánh tường minh cho `gemini`/`gemini_api`; còn lại log lỗi và trả `None`.

### 2.6 21 chỗ `except:` trần

Bắt cả `KeyboardInterrupt`/`SystemExit`. Phân bố: `taxonomy.py` (5), `gemini_web.py` (9), `app.py` (7). Đổi sang `except Exception:`; ruff rule `E722` chặn tái phạm.

---

## Phase 3 — Hiệu suất

### 3.1 `check_ollama()` gọi HTTP mỗi giây

`check_ollama()` thực hiện HTTP request thật, được gọi trong `/api/status` — mà frontend poll **mỗi 1000ms**, kể cả khi provider không phải Ollama.

- Cache kết quả với TTL 10s.
- Chỉ gọi khi `ai_provider == "ollama"`; provider khác trả `False` ngay.

> **Đính chính sau khi đo thật:** ban đầu tôi đánh giá mục này chặn worker thread tới 2 giây (theo `timeout=2`). Đo thực tế cho thấy **không phải vậy**: khi không có gì lắng nghe ở `localhost:11434`, OS trả `connection refused` ngay lập tức (~6ms), timeout 2s chỉ có tác dụng khi cổng bị firewall chặn hoặc Ollama phản hồi chậm. Giá trị thật của mục này vì thế nhỏ hơn nhiều so với dự đoán — khoảng 6ms mỗi lần poll và tránh tạo socket liên tục, chứ không phải nguyên nhân gây giật UI.

### 3.2 `OLLAMA_AVAILABLE` gọi mạng lúc import

`OLLAMA_AVAILABLE = check_ollama()` chạy ở **module import time**, tốn một round-trip mạng mỗi lần khởi động app và mỗi lần pytest collect.

- Đổi thành lazy qua module `__getattr__`.

> **Đính chính:** đo thực tế cho thấy chi phí này ~0ms trong điều kiện bình thường (cùng lý do như 3.1). Việc sửa vẫn đúng về nguyên tắc — không nên có I/O mạng ở import time — nhưng đây không phải nút thắt hiệu suất.
>
> **Regression tự gây ra, phát hiện ở Phase 5.2:** sửa `ollama.py` thôi là chưa
> đủ. `providers/__init__.py` re-export `OLLAMA_AVAILABLE` bằng `from ... import`,
> mà `__init__.py` chạy trước **mọi** import `wp_auto_poster.providers.*` — nên
> probe mạng vẫn xảy ra. Đo lại xác nhận: 2 lần connect tới cổng 11434, import
> mất 410ms. Sau khi cho `__init__.py` cũng lazy: **0 lần connect, 64ms**.
> Bài học: sửa module lá là chưa đủ khi package `__init__` còn re-export eager.

### 3.3 Log tăng vô hạn + payload status khổng lồ

`state.logs` append không giới hạn ([logging.py:11](../src/wp_auto_poster/utils/logging.py#L11)), và `/api/status` trả **toàn bộ** mảng logs mỗi giây ([routes.py:61](../src/wp_auto_poster/web/routes.py#L61)). Chạy 100 bài → vài nghìn entry, serialize lại từ đầu mỗi giây.

- `state.logs` → `collections.deque(maxlen=1000)`; thêm counter `state.log_seq`, mỗi entry mang `seq`.
- `/api/status?since=<seq>` chỉ trả log mới + `log_seq` hiện tại. Không có `since` thì trả full (tương thích ngược).
- `automation.js` gửi seq cuối đã nhận và append, thay vì render lại toàn bộ.
- Kết quả: payload mỗi giây từ O(tổng log) xuống O(log mới), thường 0–3 dòng.

> **Đo thực tế sau khi sửa** (buffer 400 log): payload `since=0` là **47.002 bytes** → `since=400` là **311 bytes**, giảm **99,3%**; thời gian phản hồi trung bình từ 1,38ms xuống 0,69ms. Đây là mục có giá trị hiệu suất lớn nhất trong Phase 3.

### 3.4 Matrix rain chạy vĩnh viễn ở 30fps

[core.js:78](../static/js/core.js#L78) `setInterval(draw, 33)` chạy cả khi tab ẩn và cả khi đang bật light theme (canvas ẩn). Máy lúc đó đang đồng thời chạy Playwright.

- Đổi sang `requestAnimationFrame`, dừng khi `document.hidden` hoặc canvas không hiển thị.

### 3.5 `slow_mo=100` toàn cục

[runner.py:131](../src/wp_auto_poster/automation/runner.py#L131) cộng 100ms vào **mọi** thao tác Playwright. Với hàng trăm thao tác mỗi bài × N bài, đây là phần lớn thời gian chạy.

- Đưa thành config `browser_slow_mo`, **default giữ 100** để không đổi hành vi hiện tại; cho phép hạ xuống 0–30 khi đã tin tưởng độ ổn định.

### 3.6 `content_list_summary` build lại mỗi giây

~~Thêm `content_list_version` counter để frontend bỏ qua re-render khi không đổi.~~

**Không cần làm.** Kiểm tra lại code cho thấy frontend **đã có sẵn** cơ chế này: `renderContentList` so sánh `contentListRenderSignature` và thoát sớm khi chữ ký không đổi ([content-list.js:63-70](../static/js/content-list.js#L63-L70)). Mục này bị đưa vào plan do tôi chưa đọc kỹ file đó.

---

## Phase 4 — Nợ kỹ thuật

### 4.1 Đảo ngược dependency: `src/` đang phụ thuộc `config/`

4 file trong `src/wp_auto_poster/providers/` đều `from config.prompts import ...` — package lõi phụ thuộc vào shim compat ở root, mà shim đó lại hack `sys.path` để import ngược vào `src/`. Hệ quả: `src/wp_auto_poster` không cài được như package độc lập.

- Chuyển `config/prompts.py` → `src/wp_auto_poster/content/prompts.py`.
- 4 provider đổi import.
- `config/prompts.py` còn lại 3 dòng shim.
- Sau bước này bỏ được toàn bộ hack `sys.path` ở [app.py:10-13](../app.py#L10-L13), `config/*.py`, `ai_providers/*.py` (nhờ `pip install -e .` ở Phase 0).

### 4.2 Prompt hardcode tên khách hàng và năm cứng

`config/prompts.py` nhúng thẳng `CÔNG TY: THANG MÁY KENZO VIỆT NAM` vào `PROMPT_PART1`/`PART2`, và `"Báo giá {keyword} mới nhất năm 2025"` — hôm nay đã là 2026, prompt này đang sinh bài lỗi thời.

- Thay bằng `{company}` và `{year}`.
- Config `company_name` với default đúng giá trị hiện tại (không đổi hành vi của bạn); `year` lấy tự động từ `datetime.now().year`.
- Test: `tests/unit/test_prompts.py`.

> **Phát sinh ngoài kế hoạch (đã làm):** khi triển khai mới phát hiện
> `providers/ollama.py` và `providers/gemini_api.py` **không có nhánh custom
> prompt** — khác với hai browser provider. Nghĩa là nếu chuyển sang Ollama
> hoặc Gemini API, cả 4 site (hoa tươi, thang máy, cửa, sự kiện) đều nhận
> prompt và khối liên hệ của công ty thang máy. Đã bổ sung `get_custom_prompt()`
> cho cả hai, cộng thêm config `contact_section_html` để mỗi site có khối liên
> hệ riêng. Đây là bug nội dung thật, không chỉ là nợ kỹ thuật.
>
> Với provider hiện tại (`chatgpt_web`) thì không bị ảnh hưởng, vì cả 4 preset
> đều đã có `gemini_prompt` riêng chứa đủ `{title}` và `{keyword}`.

### 4.3 Xóa code chết

**Đính chính:** quét lại chính xác cho **36 hàm** không được tham chiếu (lần quét đầu báo 38 — regex bị cắt ở ký tự số nên `_try_insert_image_at_h2` và `insert_images_after_h2` bị báo nhầm là chết, thực tế cả hai đều được dùng qua runtime dataclass).

36/81 hàm trong `app.py` là chết. Xóa chúng cùng import tương ứng đưa `app.py` từ 969 xuống ~250 dòng. Xóa theo lô ~8 hàm, chạy `./scripts/check.sh` sau mỗi lô.

> **Đính chính lần 2 (sau khi thực hiện):** con số đúng là **43**, không phải 36.
> Lần quét thứ hai vẫn thiếu vì nó đếm cả tham chiếu ở file khác — trong khi
> nhiều hàm private của `app.py` **trùng tên** với hàm private trong
> `inline_images.py` (`_select_visible_media_attachment`,
> `_click_first_selector_resilient`, `_wait_for_visible_media_attachments`…).
> Vì không module nào import `app.py`, phép quét đúng phải giới hạn trong chính
> `app.py`. Kết quả cuối: **43 hàm bị xóa**.
>
> `app.py` dừng ở **436 dòng**, không phải ~250 như ước lượng. Phần còn lại là
> ~100 dòng import và ~30 wrapper thật sự được dùng để dựng các runtime
> dataclass — đó là vai trò wiring hợp lệ của entry point.

**Xóa `ai_providers/`**: `grep -rn "ai_providers"` trên `app.py`, `src/`, `tests/`, `config/` cho **0 kết quả**. Dead code thuần. Xóa thư mục + cập nhật `scripts/check.sh` và README.

### 4.4 Migrate `google-generativeai` → `google-genai`

SDK cũ đã bị Google khai tử, in `FutureWarning` mỗi lần import ([gemini_api.py:11](../src/wp_auto_poster/providers/gemini_api.py#L11)).

- Viết lại `providers/gemini_api.py` theo API mới: `from google import genai` → `genai.Client(api_key=...)` → `client.models.generate_content(model=..., contents=..., config=types.GenerateContentConfig(...))`.
- **Giữ nguyên chữ ký** `generate_content_gemini(title, keyword, api_key, log_func, max_retries)` để router không phải đổi.
- Giữ guard `GEMINI_AVAILABLE` và logic retry khi gặp 429/quota.
- **Kiểm tra `requests` vẫn còn** sau khi gỡ SDK cũ (xem Phase 0, mục 2).
- Test: `test_gemini_api_provider.py` với fake client, không gọi mạng.

### 4.5 Hỗ trợ Windows/Linux

Hiện hardcode macOS-only ([runner.py:123](../src/wp_auto_poster/automation/runner.py#L123)) trong khi README hứa hỗ trợ Windows.

- Thêm `src/wp_auto_poster/wordpress/browser_launch.py` với `resolve_browser_executable(config)`:
  1. `config["browser_executable_path"]` nếu có
  2. auto-detect theo `sys.platform` — macOS: Brave/Chrome trong `/Applications`; Windows: `%ProgramFiles%\BraveSoftware\...`, `%LOCALAPPDATA%\...`; Linux: `/usr/bin/brave-browser`, `/usr/bin/google-chrome`
  3. `None` → Playwright dùng Chromium bundled
- `user_data_dir`: `~/.gemini/browser_data` → `Path.home()/".wp_auto_poster"/"browser_data"`, **có bước migrate**: nếu thư mục cũ tồn tại thì vẫn dùng nó, để không mất session đăng nhập Google hiện có.
- Screenshot `/tmp/*.png` (app.py:436, 523, 534; gemini_web.py:542; chatgpt_web.py:272) → `tempfile.gettempdir()` hoặc `screenshots/` trong repo.
- Test: `test_browser_launch.py` giả lập `sys.platform` + `os.path.exists`.

### 4.6 Hằng số ảnh về đúng module

`MAX_RETRY_ROUNDS`, `MEDIA_LIB_POLL_TIMEOUT`… nằm ở [app.py:558-571](../app.py#L558-L571) nhưng chỉ được `src/wp_auto_poster/wordpress/inline_images.py` tiêu thụ. Đưa thành default của `InlineImageWorkflowConfig`; `app.py` chỉ override khi cần.

---

## Phase 5 — Test và tooling

### 5.1 `login_to_wordpress` — 145 dòng, 0% coverage

Đây là hàm rủi ro nhất và hiện không testable ([app.py:392-537](../app.py#L392-L537)).

- Chuyển sang `src/wp_auto_poster/wordpress/auth.py` với `AuthRuntime` dataclass (đúng pattern đang dùng ở các module khác). `app.py` giữ wrapper mỏng.
- `_sync_config_domain_from_url` ([app.py:342-371](../app.py#L342-L371)) chuyển kèm và có test riêng.
- Test với fake page: thiếu credentials, không tìm thấy form, sai mật khẩu (có `#login_error`), thành công, redirect www→non-www.

### 5.2 Bật ruff thật sự

`[tool.ruff]` đã có trong `pyproject.toml` nhưng ruff không nằm trong requirements và `scripts/check.sh` không chạy nó — config hiện chỉ mang tính trang trí.

- Bỏ `--exit-zero`, select `E,F,W,B,UP` (bao gồm `E722` cho bare except). Sửa các vi phạm còn lại.

### 5.3 Thêm `tests/integration/`

README hứa "Unit/integration tests" nhưng thư mục không tồn tại.

- Test end-to-end với Flask test client + fake Playwright: `/api/start` → runner chạy với fake browser → `/api/status` phản ánh đúng tiến trình → `/api/stop` dừng thật.

### 5.4 Pin dependencies

`requirements.txt` chỉ dùng `>=`. Đổi sang `~=` khớp version đang chạy.

---

## Phase 6 — Tài liệu

- **README**: sửa mô tả chèn ảnh ("H2 #1, #3, #5") cho khớp logic inset even-spaced thực tế trong `image_policy.py`; cập nhật cài đặt (`pip install -e .`), biến môi trường mới (`WP_DEBUG`, `WP_HOST`, `WP_PORT`), config mới (`company_name`, `browser_executable_path`, `browser_slow_mo`); phần Windows giờ đã đúng sự thật.
- **`docs/architecture.md`**: cập nhật sau khi bỏ `ai_providers/`, chuyển `prompts` vào `src/`, thêm `auth.py` và `browser_launch.py`.
- **`docs/decisions/0002-security-and-hardening.md`**: ADR ghi lại quyết định redact secrets, siết CORS, bỏ debug/reloader.
- **`.env.example`**: thêm các biến mới.

---

## Rủi ro và cách giảm thiểu

| Rủi ro | Giảm thiểu |
| --- | --- |
| Sửa API config làm hỏng luồng lưu mật khẩu | Sửa backend + frontend trong **cùng một commit**; test khẳng định gửi password rỗng không xóa mất giá trị cũ |
| Xóa 36 hàm nhầm phải hàm còn dùng | Xóa theo lô ~8 hàm, `./scripts/check.sh` sau mỗi lô |
| Migrate Gemini SDK làm mất `requests` → gãy Ollama | Khai báo `requests` tường minh ngay Phase 0, trước khi động vào SDK |
| Đổi `user_data_dir` làm mất session đăng nhập Google | Ưu tiên dùng thư mục cũ nếu nó tồn tại |
| Thay đổi timing Playwright gây flaky | `browser_slow_mo` giữ default 100, chỉ là mở đường để hạ sau |
| Thread lock gây deadlock | Dùng `RLock`, phạm vi lock hẹp, không gọi I/O mạng bên trong lock |

## Những gì cố tình KHÔNG làm đợt này

- **Không tách nhỏ `media.py` (1078 dòng), `gemini_web.py` (869), `inline_images.py` (824).** Đây là code automation đã được tôi luyện qua lỗi thật; tách ra lúc này rủi ro cao mà lợi ích thấp. Để dành cho đợt sau, sau khi Phase 5 đã có integration test làm lưới an toàn.
- **Không thêm authentication cho web UI.** App chạy localhost; sau Phase 1 (siết CORS + chặn Host lạ) thì rủi ro còn lại là chấp nhận được.
- **Không đổi sang database.** JSON file đủ cho quy mô hiện tại.

## Thứ tự khuyến nghị nếu muốn dừng sớm

Nếu không làm hết, giá trị giảm dần theo đúng thứ tự phase. Riêng ba mục sau nên làm bằng mọi giá vì chúng là lỗ hổng/bug đang hoạt động:

1. Phase 1.1 + 1.2 — mật khẩu WordPress đang đọc được từ bất kỳ website nào
2. Phase 2.1 — repo hiện không chạy được trên máy mới
3. Phase 3.1 + 3.3 — hai thứ này làm UI chậm dần theo thời gian chạy
