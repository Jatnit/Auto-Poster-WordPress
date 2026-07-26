# 2. Security hardening and runtime correctness

Date: 2026-07-26

## Status

Accepted

## Context

A review of the post-refactor codebase found several defects that a local-only
tool is easy to overlook:

1. `GET /api/config` returned the whole config object, including
   `wp_password` and `gemini_api_key` in plain text, and `CORS(app)` allowed
   every origin. Any website open in the same browser could read the
   WordPress admin password with a single `fetch()`.
2. `app.run(debug=True)` exposed the Werkzeug debugger and, more disruptive in
   practice, enabled the auto-reloader — which restarts the process on any file
   save and kills an automation run mid-post.
3. `runner.py` read `config["headless_mode"]`, a key absent from
   `DEFAULT_CONFIG`. Existing installs worked only because their
   `app_config.json` already had it; a fresh clone crashed at browser launch.
4. Nothing guarded the shared `AppState`. `DELETE /api/content/<i>` mutated
   `topics`/`generated_contents` while the runner iterated them, and only
   `content_list` was re-indexed — `skip_post_indices` and `retry_queue` kept
   pointing at the wrong articles.
5. `/api/start` and `run_automation` both called `state.reset()`; a Stop
   arriving between the two was silently undone.
6. `/api/status` returned the entire log history on every 1-second poll, and
   `state.logs` was unbounded.
7. The browser path was hardcoded to a macOS Brave location while the README
   advertised Windows support.
8. `ollama.py` and `gemini_api.py` had no custom-prompt branch, so all four
   configured sites received prompts and a contact block naming one specific
   elevator company.

## Decision

**Secrets stay server-side.** Reads report `wp_password_set` / `gemini_api_key_set`
booleans instead of values. A blank secret on write means "keep the stored one".
Applying a preset happens through `POST /api/presets/<name>/apply` so the
password is copied within the server and never traverses HTTP. The browser no
longer persists secrets to `localStorage`.

**The server answers only to loopback.** CORS is limited to
`localhost`/`127.0.0.1` on the configured port, a `before_request` hook rejects
foreign `Host` headers (DNS rebinding), and `debug`/`host`/`port` are
environment-gated with the reloader disabled unconditionally.

**Index-linked collections are mutated under a lock**, structural edits are
rejected with HTTP 409 while publishing, and the posting loop iterates a
snapshot. `state.request_stop()` sets a `stop_requested` flag that `reset()`
clears, so the ordering between start and stop is explicit.

**Logs are a bounded deque with monotonic sequence ids.** Clients poll
`/api/status?since=<seq>`; omitting `since` returns the full buffer for
backwards compatibility.

**Prompts are parameterised** through `{company}` and `{year}`, with an
optional `contact_section_html` override, and every provider honours the
per-site `gemini_prompt`.

**Browser discovery is per-platform** with a config override and a fallback to
Playwright's bundled Chromium. The profile directory moved to
`~/.wp_auto_poster/browser_data` but the legacy `~/.gemini/browser_data` is
reused when present so existing sessions survive.

## Consequences

- Any client reading `wp_password` from `/api/config` breaks. The bundled UI
  was updated in the same change; external scripts, if any, must use the
  `_set` flags.
- `google-generativeai` is replaced by `google-genai`. `requests` is now an
  explicit dependency because it previously arrived only transitively through
  the old SDK.
- `POST /api/topics` and `DELETE /api/content/<i>` return 409 during the
  publishing phase rather than corrupting indices.
- Reaching the UI through a hostname other than localhost now returns 403.
  Set `WP_HOST` and extend `allowed_hostnames` if remote access is ever needed.
