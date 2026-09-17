import json
import os
from coops.utils.github_api import save_json_data, load_json_data

def test_save_json_data_list_metadata(tmp_path):
    file = tmp_path / "data.json"
    save_json_data([{"a": 1}, {"b": 2}], str(file))
    data = load_json_data(str(file))
    assert isinstance(data, list)
    assert data[0].get("_metadata")
    assert data[0]["_metadata"]["record_count"] == 2
    # Garantir que dados originais permanecem
    assert data[1]["a"] == 1 and data[2]["b"] == 2

def test_save_json_data_dict_metadata(tmp_path):
    file = tmp_path / "single.json"
    save_json_data({"a": 1}, str(file))
    data = load_json_data(str(file))
    assert data.get("_metadata")
    assert data["a"] == 1


def test_save_json_data_does_not_mutate_input(tmp_path):
    """Records saved individually are reused in consolidated files (e.g.
    language_analysis_all.json); they must not gain a `_metadata` key."""
    record = {"repository": "repo1", "languages": []}
    records = [record]
    save_json_data(record, str(tmp_path / "one.json"))
    save_json_data(records, str(tmp_path / "all.json"))

    assert record == {"repository": "repo1", "languages": []}
    assert records == [record]
    saved = json.loads((tmp_path / "all.json").read_text())
    assert saved[1] == {"repository": "repo1", "languages": []}
