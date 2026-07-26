from wp_auto_poster.state.app_state import LOG_HISTORY_LIMIT, AppState
from wp_auto_poster.utils.logging import add_state_log, logs_since


def test_log_entries_carry_increasing_sequence_ids():
    state = AppState()

    add_state_log(state, "first", "info")
    add_state_log(state, "second", "warning")

    entries = list(state.logs)
    assert [entry["seq"] for entry in entries] == [1, 2]
    assert state.log_seq == 2


def test_logs_since_returns_only_newer_entries():
    state = AppState()
    for i in range(5):
        add_state_log(state, f"msg-{i}", "info")

    fresh = logs_since(state, since=3)

    assert [entry["message"] for entry in fresh] == ["msg-3", "msg-4"]


def test_logs_since_zero_returns_everything_buffered():
    state = AppState()
    add_state_log(state, "only", "info")

    assert len(logs_since(state, since=0)) == 1


def test_log_buffer_is_bounded():
    """A long run used to grow state.logs without limit."""
    state = AppState()
    for i in range(LOG_HISTORY_LIMIT + 250):
        add_state_log(state, f"msg-{i}", "info")

    assert len(state.logs) == LOG_HISTORY_LIMIT
    # Sequence ids keep counting even after old entries scroll out, so a
    # polling client never re-receives what it already rendered.
    assert state.log_seq == LOG_HISTORY_LIMIT + 250
    assert list(state.logs)[-1]["message"] == f"msg-{LOG_HISTORY_LIMIT + 249}"


def test_reset_clears_buffer_and_sequence():
    state = AppState()
    add_state_log(state, "before reset", "info")

    state.reset()

    assert list(state.logs) == []
    assert state.log_seq == 0
