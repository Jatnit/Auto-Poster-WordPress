#!/usr/bin/env bash
set -euo pipefail

if [ -n "${PYTHON:-}" ]; then
  PYTHON_BIN="$PYTHON"
elif [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" -m py_compile app.py config/prompts.py config/settings.py
if [ -d src ]; then
  src_files="$(find src -name '*.py' -type f | sort)"
  if [ -n "$src_files" ]; then
    # shellcheck disable=SC2086
    "$PYTHON_BIN" -m py_compile $src_files
  fi
fi

if "$PYTHON_BIN" -m ruff --version >/dev/null 2>&1; then
  "$PYTHON_BIN" -m ruff check .
else
  echo "ruff not installed, skipping lint (pip install -r requirements-dev.txt)"
fi

"$PYTHON_BIN" -m pytest
