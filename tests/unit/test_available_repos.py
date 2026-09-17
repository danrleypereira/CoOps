"""Unit tests for coops.silver.available_repos."""

import json

import pytest

from coops.silver.available_repos import process_available_repos


@pytest.fixture(autouse=True)
def _in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def write_bronze(tmp_path, repos):
    path = tmp_path / "data" / "bronze" / "repositories_filtered.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(repos))


def read_output(tmp_path):
    return json.loads((tmp_path / "data" / "silver" / "available_repos.json").read_text())


def test_writes_sorted_unique_names_without_metadata(tmp_path):
    write_bronze(tmp_path, [
        {"_metadata": {"extracted_at": "2026-01-01"}},
        {"name": "zeta", "full_name": "org/zeta"},
        {"name": "Alpha", "full_name": "org/Alpha"},
        {"name": "beta"},
        {"name": "beta"},
        {"full_name": "org/no-name"},
        None,
    ])

    assert process_available_repos() == ["data/silver/available_repos.json"]
    assert read_output(tmp_path) == ["Alpha", "beta", "zeta"]


@pytest.mark.parametrize("bronze", [None, []])
def test_writes_empty_list_when_nothing_was_extracted(tmp_path, bronze):
    if bronze is not None:
        write_bronze(tmp_path, bronze)

    process_available_repos()

    assert read_output(tmp_path) == []
