# WP Auto Poster Refactor Plan

## Objective

Refactor the Flask + Playwright automation tool in small, safe phases while preserving existing behavior, Flask API compatibility, and local JSON config compatibility.

## Current State

- `app.py` is now a compatibility entrypoint and runtime wiring layer. It keeps legacy wrappers, but Flask routes and most domain workflows have moved into `src/wp_auto_poster/`.
- Backend logic is split by domain: content, content retry queue, providers, state, WordPress workflows, automation runner, web routes, and utilities.
- `templates/index.html` now focuses on markup and asset includes. CSS lives in `static/css/app.css`; JavaScript is split by feature under `static/js/`.
- Sensitive runtime files such as `app_config.json`, `wp_site_presets.json`, and `.env` remain ignored.
- The local safety net is `./scripts/check.sh`, which compiles Python files and runs `pytest`.

## Phases

Core refactor status: complete.

1. Done: Add safety net: tests, check script, env template, documentation.
2. Done: Extract content validation, cleanup, and minimal HTML conversion.
3. Done: Centralize state/config/logging.
4. Done: Extract AI provider modules.
5. Done: Extract WordPress browser helpers.
6. Done: Extract media and inline image workflow.
7. Done: Extract publishing and post workflow.
8. Done: Introduce Flask app factory and route modules.
9. Done: Split frontend CSS/JS by feature.
10. Done: Final documentation and cleanup.

## Progress

| Phase | Status | Notes |
| --- | --- | --- |
| 1 | Done | Added `pyproject.toml`, `scripts/check.sh`, docs, and unit tests for content cleanup/validation/HTML conversion/image placement policy. |
| 2 | Done | Moved runtime state, config store, preset store, and logging helpers into `src/wp_auto_poster/state` and `src/wp_auto_poster/utils`; `config/settings.py` is now a compatibility facade. |
| 3 | Done | Moved Ollama, Gemini API, Gemini Web, and ChatGPT Web providers into `src/wp_auto_poster/providers`; added a testable provider router in `src/wp_auto_poster/content/generation.py`. Browser providers use runtime dataclasses to preserve Playwright/session behavior. |
| 3a | Done | Moved content retry/rerender queue bookkeeping into `src/wp_auto_poster/content/retry_queue.py` with tests for duplicate queue protection, retry attempts, failed-row visibility, and generated-content slot updates. |
| 3b | Done | Moved Gemini/ChatGPT browser session cleanup into `src/wp_auto_poster/providers/session_cleanup.py` with fake-page tests for dispatch, skip, and delete-confirm flows. |
| 4 | Done | Moved shared browser helpers into `src/wp_auto_poster/wordpress/browser.py` and kept wrapper functions in `app.py` for compatibility. |
| 5 | Done | Moved media/editor helpers into `src/wp_auto_poster/wordpress/media.py`, stateful inline-image orchestration into `src/wp_auto_poster/wordpress/inline_images.py`, and featured-image flow into `src/wp_auto_poster/wordpress/featured_image.py`. |
| 6 | Done | Moved Classic Editor helpers into `wordpress/editor.py`, category/tag helpers into `wordpress/taxonomy.py`, publish/schedule helper into `wordpress/publisher.py`, schedule calculation into `automation/schedule.py`, and post-level orchestration into `wordpress/post_workflow.py`. |
| 7 | Done | Moved automation runner into `automation/runner.py`, Flask route registration into `web/routes.py`, and Flask app creation into `web/app_factory.py`. `app.py` now keeps compatibility runtime wiring and CLI startup. |
| 8 | Done | Introduced Flask app factory and route modules. |
| 9 | Done | Moved inline CSS out to `static/css/app.css`; split frontend JS into feature files under `static/js/` (`core`, `checklist`, `dialogs`, `presets`, `content-list`, `config`, `topics`, `schedule`, `automation`); removed duplicate wake-lock implementation. |
| 10 | Done | Updated README and docs to reflect the extracted architecture, setup flow, troubleshooting paths, and current module ownership. |

## Compatibility Rules

- Preserve existing Flask endpoints and response shapes.
- Preserve `app_config.json` and `wp_site_presets.json` formats.
- Preserve current content retry, rerender queue, image no-repeat, valid-image-only, contact-safe, and inset-H2 behavior.
- Keep the app runnable after every phase.

## Remaining Cleanup Opportunities

These are intentionally left as follow-up work because they can be done safely after the architecture split:

- Continue shrinking `app.py` by deleting compatibility wrappers only after all callers are moved to `src/wp_auto_poster/`.
- Add browser-level smoke tests for the local UI when a browser test harness is available.
- Add integration tests around real WordPress staging sites if credentials and test content can be isolated.
