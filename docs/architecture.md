# WP Auto Poster Architecture

WP Auto Poster is a local Flask control panel that generates SEO content with AI providers and publishes scheduled posts to WordPress through Playwright browser automation.

The current architecture keeps `app.py` as a compatibility entrypoint while domain logic is extracted into `src/wp_auto_poster/`. This lets the app keep existing Flask endpoints, JSON config files, and UI behavior while making individual workflows testable.

## Runtime Shape

```text
Browser UI
  -> Flask routes (`src/wp_auto_poster/web/routes.py`)
  -> Automation runner (`src/wp_auto_poster/automation/runner.py`)
  -> Content generation + validation (`src/wp_auto_poster/content/`)
  -> WordPress browser workflows (`src/wp_auto_poster/wordpress/`)
  -> State/config/logging (`src/wp_auto_poster/state/`, `src/wp_auto_poster/utils/`)
```

`app.py` is still intentionally present because many existing call sites, saved configs, and manual workflows expect it. Its role is now compatibility wiring: it imports the extracted modules, builds runtime dataclasses/callbacks, and starts Flask.

### Import direction

`src/wp_auto_poster/` no longer imports from the top-level `config/` package. The
prompt templates moved to `wp_auto_poster.content.prompts`, and `config/prompts.py`
is a thin re-export kept for older imports. The only remaining `sys.path`
bootstrap lives in `app.py` so `python app.py` works without `pip install -e .`;
library modules must not add one.

## Backend Modules

| Path | Responsibility | Notes |
| --- | --- | --- |
| `app.py` | Compatibility entrypoint and local run target | Keeps legacy wrappers and runtime wiring; no direct Flask route decorators. |
| `src/wp_auto_poster/web/app_factory.py` | Flask app factory | Creates the Flask app, restricts CORS to loopback, rejects foreign `Host` headers, and sets security headers. |
| `src/wp_auto_poster/web/routes.py` | HTTP API routes | Routes parse requests and delegate to runtime callbacks. Secrets are redacted on read; structural edits are rejected with 409 while publishing. |
| `src/wp_auto_poster/automation/runner.py` | Main automation loop | Owns start/reset/progress orchestration while delegating provider and WordPress work. |
| `src/wp_auto_poster/automation/schedule.py` | Schedule calculation | Pure scheduling helpers for day/slot/date planning. |
| `src/wp_auto_poster/content/cleanup.py` | Generated content cleanup | Removes AI-injected images/logos/media wrappers and unsafe metadata artifacts. |
| `src/wp_auto_poster/content/validation.py` | Word count and validation | Enforces configurable minimum word counts and returns structured validation results. |
| `src/wp_auto_poster/content/html_convert.py` | Lightweight markdown/HTML conversion | Keeps content formatting cleanup independent from Flask/Playwright. |
| `src/wp_auto_poster/content/generation.py` | Provider router | Normalizes provider calls through a shared generation entrypoint. Unknown provider names error instead of falling through to the Gemini API. |
| `src/wp_auto_poster/content/prompts.py` | Prompt templates and formatting | Owns the default two-part templates and the contact block. Parameterised through `{company}`/`{year}`; `get_custom_prompt` selects the per-site override; `safe_format` tolerates stray braces in user prompts. |
| `src/wp_auto_poster/content/retry_queue.py` | Content retry and rerender queue workflow | Keeps failed content visible, retries under-word-count output, and updates content-list state. |
| `src/wp_auto_poster/providers/` | AI provider implementations | Contains Ollama, Gemini API, Gemini Web, ChatGPT Web, and browser-provider session cleanup. Browser providers use runtime dataclasses so they can keep Playwright behavior without owning Flask globals. |
| `src/wp_auto_poster/state/app_state.py` | Runtime state model | Centralizes progress, generated content, queues, image usage, and control flags. Owns the `RLock` guarding index-linked collections plus `snapshot_posting_plan()` and `request_stop()`. |
| `src/wp_auto_poster/state/redaction.py` | Secret redaction | Strips `wp_password`/`gemini_api_key` from API reads and preserves stored secrets when a write sends a blank value. |
| `src/wp_auto_poster/state/json_store.py` | Atomic JSON persistence | Shared writer: temp file + `os.replace`, `0600` permissions. Used by both config and preset stores. |
| `src/wp_auto_poster/state/config_store.py` | App config persistence | Reads/writes `app_config.json` without changing the existing schema. |
| `src/wp_auto_poster/state/presets.py` | WordPress preset persistence | Reads/writes `wp_site_presets.json` without changing the existing schema. |
| `src/wp_auto_poster/utils/logging.py` | UI/system logging helpers | Appends to a bounded deque, stamps monotonic `seq` ids, and serves `logs_since()` for cursor-based polling. |
| `src/wp_auto_poster/wordpress/auth.py` | WordPress login | Navigation, form discovery with fallback selectors, credential fill, error detection, and post-login www/non-www domain sync. |
| `src/wp_auto_poster/wordpress/browser.py` | Browser resilience helpers | Navigation, modal handling, click/fill helpers, URL normalization. |
| `src/wp_auto_poster/wordpress/browser_launch.py` | Browser discovery | Per-platform Brave/Chrome lookup with config override and Playwright-Chromium fallback; profile dir resolution (legacy path preferred) and cross-platform screenshot paths. |
| `src/wp_auto_poster/wordpress/media.py` | Media library primitives | Opens media modal, waits for attachments, picks candidates, inserts selected media. |
| `src/wp_auto_poster/wordpress/image_policy.py` | Image placement policy | Calculates inset H2 targets and guards against contact-section placement. |
| `src/wp_auto_poster/wordpress/inline_images.py` | Inline image workflow | Handles no-repeat random pool, valid-image filtering, insert retries, final scan, and repair. |
| `src/wp_auto_poster/wordpress/featured_image.py` | Featured image workflow | Optional featured-image selection and validation. |
| `src/wp_auto_poster/wordpress/editor.py` | Classic Editor helpers | Title/content insertion, editor mode handling, Rank Math keyword setting. |
| `src/wp_auto_poster/wordpress/taxonomy.py` | Category and tag helpers | Preserves existing taxonomy selectors and timing behavior. |
| `src/wp_auto_poster/wordpress/publisher.py` | Publish/schedule action | Handles publish button, timestamp save, and confirmation paths. |
| `src/wp_auto_poster/wordpress/post_workflow.py` | Single post orchestration | Thin workflow that composes editor, images, taxonomy, featured image, and publisher steps. |

## Frontend Modules

The UI keeps the existing visual design but is split into assets so changes are easier to isolate.

| Path | Responsibility |
| --- | --- |
| `templates/index.html` | Flask-rendered markup and script/style includes. |
| `static/css/app.css` | All UI styling previously embedded in the template. |
| `static/js/core.js` | Shared state, utility helpers, fetch wrappers, and app bootstrap helpers. |
| `static/js/checklist.js` | Checklist rendering and progress event UI. |
| `static/js/dialogs.js` | Confirmation dialogs and user prompts. |
| `static/js/presets.js` | WordPress preset loading/saving/deleting. |
| `static/js/content-list.js` | Generated content list, expand/collapse, actions, rerender controls. |
| `static/js/config.js` | Runtime config read/write and UI sync. |
| `static/js/topics.js` | Topic/keyword input behavior. |
| `static/js/schedule.js` | Schedule distribution UI and calculations. |
| `static/js/automation.js` | Start/pause/resume/stop automation and polling. |

## Data And Local Files

| File | Purpose | Git Status |
| --- | --- | --- |
| `app_config.json` | Saved runtime configuration from the UI. | Ignored. |
| `wp_site_presets.json` | Saved WordPress site presets. | Ignored. |
| `.env` | Optional local secrets if introduced. | Ignored. |
| `.env.example` | Safe template for future environment variables. | Tracked. |

The refactor intentionally does not migrate JSON schemas. Existing saved config files should continue to load.

## Testing Strategy

The test suite focuses on extracted pure logic and compatibility seams:

- Content cleanup, word count, validation, and HTML conversion.
- Content retry/rerender queue behavior and failed-row visibility.
- Browser provider validation/runtime seams for Gemini Web and ChatGPT Web.
- H2 image placement policy and contact-safe behavior.
- Random image uniqueness and inline-image workflow decisions.
- State reset behavior.
- WordPress helper units using fake page/locator objects.
- Schedule calculation and post workflow orchestration.
- Flask route registration and response compatibility.

Run the full local check with:

```bash
./scripts/check.sh
```

## Compatibility Guarantees

During this staged refactor, these behaviors are preserved:

- Existing Flask endpoints and JSON response shapes.
- Existing `app_config.json` and `wp_site_presets.json` formats.
- Existing provider names and UI controls.
- Content retry/rerender queue behavior.
- No-repeat image tracking across generated posts.
- Valid-image-only filtering so AI/link logos do not satisfy image checks.
- Contact-safe final image placement.
- Inset H2 placement so images are not too close to the first or final heading.

## Migration Direction

Future cleanup should continue shrinking `app.py` by removing compatibility wrappers only after their callers have moved into `src/wp_auto_poster/`. Each removal should be covered by tests or a smoke check so behavior remains stable.
