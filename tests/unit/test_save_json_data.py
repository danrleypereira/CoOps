import json

from coops.utils.github_api import load_json_data, save_json_data


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


def test_save_json_data_complete_provenance(tmp_path):
    """#216: `complete: true` is written into _metadata only when the
    producer positively asserts an unbounded enumeration; the default
    shape keeps the key ABSENT (absent means incomplete), so every other
    caller's output is unchanged."""
    provenanced = tmp_path / "filtered.json"
    save_json_data([{"name": "x"}], str(provenanced), complete=True)
    meta = load_json_data(str(provenanced))[0]["_metadata"]
    assert meta["complete"] is True

    plain = tmp_path / "plain.json"
    save_json_data([{"name": "x"}], str(plain))
    assert "complete" not in load_json_data(str(plain))[0]["_metadata"]


def test_save_json_data_empty_list_carries_no_provenance(tmp_path):
    """#216, the empty-listing hole: _metadata is prepended only for
    non-empty lists, so a zero-repository listing carries none at all —
    the most destructive possible input is the one with the least
    evidence, and the reconciler must refuse on exactly this shape."""
    empty = tmp_path / "empty.json"
    save_json_data([], str(empty), complete=True)
    assert load_json_data(str(empty)) == []
