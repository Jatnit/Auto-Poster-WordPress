# WP Auto Poster Refactor Summary

This refactor plan is complete and has been cleared from the active planning
queue. The file is kept only as a short historical summary.

## Completed Scope

- Added the local safety net: test dependencies, `scripts/check.sh`, setup docs,
  and focused unit tests.
- Split backend logic by domain under `src/wp_auto_poster/`: content, providers,
  runtime state, WordPress helpers, publishing workflow, automation runner, and
  Flask routes.
- Kept `app.py` as the compatibility entrypoint and runtime wiring layer.
- Moved frontend styling and behavior out of `templates/index.html` into
  `static/css/app.css` and feature-based files under `static/js/`.
- Preserved existing Flask endpoints, JSON config formats, content retry
  behavior, image placement policy, and WordPress posting workflow.

## Current References

- Active architecture notes: [architecture.md](architecture.md)
- Hardening summary: [improvement-plan.md](improvement-plan.md)
- Security decisions: [decisions/0002-security-and-hardening.md](decisions/0002-security-and-hardening.md)

## Remaining Follow-up Ideas

- Continue shrinking `app.py` only when compatibility wrappers are no longer
  used.
- Add browser-level smoke tests when a stable harness is available.
- Add integration tests around a real staging WordPress site if isolated
  credentials and test content are available.
