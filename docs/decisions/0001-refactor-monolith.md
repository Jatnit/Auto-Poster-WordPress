# ADR 0001: Refactor Monolith In Safe Phases

## Status

Accepted

## Context

The project works but concentrates most backend behavior in `app.py` and most frontend behavior in `templates/index.html`. This slows future development and makes regression risk higher.

## Decision

Refactor by extracting pure, testable helpers first, then progressively move browser automation, publishing workflows, Flask routes, and frontend assets into dedicated modules.

## Consequences

- Short-term compatibility wrappers remain in `app.py`.
- Tests are added before high-risk browser workflow extraction.
- The project can keep running between phases.
