"""Runtime logging and pause helpers."""

from __future__ import annotations

import time
from datetime import datetime


def add_state_log(state, message: str, log_type: str = "info") -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    state.logs.append({"time": timestamp, "message": message, "type": log_type})
    print(f"[{timestamp}] [{log_type.upper()}] {message}")


def wait_if_paused(state, interval: float = 0.5) -> bool:
    while state.is_paused and state.is_running:
        time.sleep(interval)
    return state.is_running
