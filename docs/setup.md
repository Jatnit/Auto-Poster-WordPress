# Setup

This project is a local Flask + Playwright automation app. The recommended run target remains `app.py`, while most implementation code now lives under `src/wp_auto_poster/`.

## Requirements

- Python 3.9+
- A virtual environment
- Playwright browser binaries
- Network access to the configured WordPress admin site
- Optional provider dependencies/API keys depending on the selected AI provider

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install
```

## Configure

The UI saves runtime settings into local JSON files. These files are intentionally ignored by Git:

- `app_config.json`
- `wp_site_presets.json`
- `.env`

A safe environment template exists at `.env.example`. The current app primarily uses UI-saved JSON config, but `.env.example` is kept so future secrets can be introduced without changing onboarding.

## Run The App

```bash
source .venv/bin/activate
python app.py
```

Open the local URL printed in the terminal. If the terminal is noisy from previous runs, clear it first:

```bash
clear && python app.py
```

## Run Checks

Use the project check script before and after each refactor phase:

```bash
./scripts/check.sh
```

The script compiles Python files and runs `pytest`.

## Useful Development Commands

```bash
python3 -m py_compile app.py $(find src -name '*.py')
pytest
for f in static/js/*.js; do node --check "$f"; done
```

## Project Layout

```text
app.py                         # compatibility entrypoint
src/wp_auto_poster/             # extracted backend modules
templates/index.html            # Flask markup
static/css/app.css              # frontend styles
static/js/*.js                  # frontend feature modules
tests/unit/                     # unit and compatibility tests
docs/                           # architecture, setup, troubleshooting, decisions
scripts/check.sh                # local verification script
```

## Adding New Backend Code

Prefer adding new logic inside `src/wp_auto_poster/` instead of expanding `app.py`.

- Content logic belongs in `src/wp_auto_poster/content/`.
- Provider logic belongs in `src/wp_auto_poster/providers/`.
- WordPress browser logic belongs in `src/wp_auto_poster/wordpress/`.
- Route-only parsing belongs in `src/wp_auto_poster/web/routes.py`.
- Cross-run automation orchestration belongs in `src/wp_auto_poster/automation/`.

Keep `app.py` for compatibility wrappers and runtime wiring until the wrapper is no longer used.

## Adding New Frontend Code

Prefer editing the feature file closest to the behavior:

- Generated content UI: `static/js/content-list.js`
- Checklist/progress UI: `static/js/checklist.js`
- Start/pause/resume/stop: `static/js/automation.js`
- Config save/load: `static/js/config.js`
- Topics and keywords: `static/js/topics.js`
- Schedule distribution: `static/js/schedule.js`

Avoid putting new CSS or JavaScript directly into `templates/index.html` unless it is a very small Flask template variable.
