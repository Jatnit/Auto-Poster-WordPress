# WP Auto Poster Hardening Summary

This improvement plan is complete and has been cleared from the active planning
queue. The detailed checklist was archived into this summary so the repository
does not keep presenting finished work as pending work.

## Completed On 2026-07-26

| Area | Result |
| --- | --- |
| Test coverage | Increased from 87 tests to 193 tests |
| Linting | Ruff violations reduced from 231 to 0 and made blocking |
| Entrypoint size | `app.py` reduced from 976 lines to 436 lines |
| Dead code | Removed unused app wrappers and the obsolete `ai_providers/` tree |
| Status payload | Reduced incremental `/api/status` payload from about 47 KB to about 311 B |
| Secrets | Redacted sensitive config responses and stopped storing secrets in localStorage |
| Browser support | Added macOS, Windows, Linux, and bundled Chromium fallback handling |
| Gemini SDK | Migrated from `google-generativeai` to `google-genai` |

## Decisions Kept

- Keep local JSON config files for the current scale.
- Mask secrets at the API boundary while preserving the existing local workflow.
- Keep the app localhost-oriented, with CORS and Host checks reducing browser
  exposure.
- Keep slow browser timing configurable instead of changing the default behavior
  abruptly.

## Current References

- Architecture overview: [architecture.md](architecture.md)
- Security and hardening ADR: [decisions/0002-security-and-hardening.md](decisions/0002-security-and-hardening.md)
- Setup and operations guide: [../README.md](../README.md)
