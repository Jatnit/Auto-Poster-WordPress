"""Shared JSON persistence helpers.

Both the app config and the site presets hold WordPress credentials, so writes
go through a single place that (a) replaces the file atomically, and (b) keeps
the file readable by its owner only.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Mapping

#: Owner read/write only — these files hold plaintext credentials.
SECRET_FILE_MODE = 0o600


def read_json(path: str) -> Any:
    """Return parsed JSON, or ``None`` when missing/unreadable/corrupt."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def write_json_atomic(payload: Mapping[str, Any], path: str) -> None:
    """Write ``payload`` to ``path`` atomically with restrictive permissions.

    Writing through a temporary file in the same directory means a crash
    mid-write cannot leave a truncated config behind.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)

    handle_fd, temp_path = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".",
        suffix=".tmp",
        dir=directory,
    )
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, SECRET_FILE_MODE)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
