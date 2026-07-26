"""Runtime logging and pause helpers."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List


def add_state_log(state, message: str, log_type: str = "info") -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    lock = getattr(state, "lock", None)
    if lock is not None:
        with lock:
            _append(state, timestamp, message, log_type)
    else:
        _append(state, timestamp, message, log_type)
    print(f"[{timestamp}] [{log_type.upper()}] {message}")


def _append(state, timestamp: str, message: str, log_type: str) -> None:
    seq = getattr(state, "log_seq", 0) + 1
    state.log_seq = seq
    state.logs.append({
        "seq": seq,
        "time": timestamp,
        "message": message,
        "type": log_type,
    })


def logs_since(state, since: int = 0) -> List[Dict[str, Any]]:
    """Return log entries newer than ``since``.

    ``since <= 0`` means "send everything currently buffered", which keeps the
    first poll of a session — and any client that does not track a cursor —
    working exactly as before.
    """
    entries = list(state.logs)
    if since <= 0:
        return entries
    return [entry for entry in entries if int(entry.get("seq", 0)) > since]


def wait_if_paused(state, interval: float = 0.5) -> bool:
    while state.is_paused and state.is_running:
        time.sleep(interval)
    return state.is_running
