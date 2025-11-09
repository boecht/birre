from __future__ import annotations

from birre.resources import iter_data_files


def test_iter_data_files_yields_json_paths() -> None:
    matches = list(iter_data_files("*.json"))
    assert any(path.endswith(".json") for path in matches)
