import json
import os
import stat

import pytest

from wp_auto_poster.state.config_store import load_app_config, save_app_config
from wp_auto_poster.state.json_store import read_json, write_json_atomic
from wp_auto_poster.state.presets import load_site_presets, save_site_presets


def test_write_json_atomic_sets_owner_only_permissions(tmp_path):
    target = tmp_path / "app_config.json"

    write_json_atomic({"wp_password": "hunter2"}, str(target))

    mode = stat.S_IMODE(os.stat(target).st_mode)
    assert mode == 0o600


def test_write_json_atomic_leaves_no_temp_files(tmp_path):
    target = tmp_path / "app_config.json"

    write_json_atomic({"a": 1}, str(target))

    assert [p.name for p in tmp_path.iterdir()] == ["app_config.json"]


def test_write_json_atomic_preserves_previous_file_on_failure(tmp_path):
    target = tmp_path / "app_config.json"
    write_json_atomic({"keep": "me"}, str(target))

    class Unserializable:
        pass

    with pytest.raises(TypeError):
        write_json_atomic({"bad": Unserializable()}, str(target))

    # The original content must survive a failed write.
    assert json.loads(target.read_text(encoding="utf-8")) == {"keep": "me"}
    assert [p.name for p in tmp_path.iterdir()] == ["app_config.json"]


def test_read_json_returns_none_for_missing_and_corrupt(tmp_path):
    missing = tmp_path / "nope.json"
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")

    assert read_json(str(missing)) is None
    assert read_json(str(corrupt)) is None


def test_config_round_trip_merges_defaults(tmp_path):
    target = str(tmp_path / "app_config.json")
    defaults = {"posts_per_day": 2, "category_name": "Tin tức"}

    assert save_app_config({"posts_per_day": 5}, target) is True
    loaded = load_app_config(target, defaults)

    assert loaded["posts_per_day"] == 5
    assert loaded["category_name"] == "Tin tức"


def test_presets_round_trip(tmp_path):
    target = str(tmp_path / "wp_site_presets.json")

    assert save_site_presets({"site": {"wp_username": "admin"}}, target) is True

    assert load_site_presets(target) == {"site": {"wp_username": "admin"}}
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600


def test_save_reports_failure_through_log_func(tmp_path):
    logged = []

    ok = save_app_config(
        {"x": object()},
        str(tmp_path / "app_config.json"),
        log_func=lambda message, level: logged.append((message, level)),
    )

    assert ok is False
    assert logged and logged[-1][1] == "error"
