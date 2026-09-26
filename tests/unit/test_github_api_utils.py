"""Tests for the module-level helpers of ``coops.utils.github_api``.

The helpers with dedicated files live there: ``save_json_data`` in
``test_save_json_data.py``, ``parse_github_date`` in
``test_parse_github_date.py`` and ``_split_time_range`` in
``test_split_time_range.py``. What is left here is ``load_json_data``,
``update_data_registry`` and ``OrganizationConfig`` — the JSON/config
surface this module has always exported.

Migrated from the retired ``test_github_api_utils.py`` and friends (#31);
the registry and config tests are the real-filesystem versions from
``test_github_api_comprehensive.py`` carrying the extra assertions of the
mocked ``test_github_api_client.py`` versions they replace.
"""

import json
import os

import pytest

from coops.utils.github_api import (
    OrganizationConfig,
    load_json_data,
    update_data_registry,
)


class TestLoadJsonData:
    def test_existing_file(self, tmp_path):
        """Testa load_json_data com arquivo existente"""
        filepath = str(tmp_path / "test.json")
        data = {"test": "value"}

        with open(filepath, 'w') as f:
            json.dump(data, f)

        loaded = load_json_data(filepath)
        assert loaded == data

    def test_missing_file(self):
        """Testa load_json_data com arquivo inexistente"""
        loaded = load_json_data("nonexistent.json")
        assert loaded is None

    def test_invalid_json(self, tmp_path):
        """Testa carregar arquivo JSON inválido"""
        test_file = str(tmp_path / "invalid.json")

        with open(test_file, 'w') as f:
            f.write("not valid json {")

        # Function should raise JSONDecodeError
        with pytest.raises(json.JSONDecodeError):
            load_json_data(test_file)


class TestUpdateDataRegistry:
    def test_creates_new_registry(self):
        """Test creating a new registry entry (real filesystem, under a
        temporary cwd — the registry path is relative by contract)."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily change data directory
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.makedirs("data/bronze", exist_ok=True)

                update_data_registry("bronze", "commits", ["file1.json", "file2.json"])

                registry = load_json_data("data/bronze/registry.json")
                assert "commits" in registry
                assert registry["commits"]["files"] == ["file1.json", "file2.json"]
                assert registry["commits"]["layer"] == "bronze"
                assert "updated_at" in registry["commits"]
            finally:
                os.chdir(original_cwd)

    def test_updates_existing_registry(self):
        """A same-entity update replaces the file list; a new entity is
        added beside the entries already there."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.makedirs("data/bronze", exist_ok=True)

                # Create initial registry
                update_data_registry("bronze", "commits", ["file1.json"])

                # Update the same entity
                update_data_registry("bronze", "commits", ["file1.json", "file2.json"])

                # Add another entity
                update_data_registry("bronze", "issues", ["new.json"])

                registry = load_json_data("data/bronze/registry.json")
                # Same entity: the file list was replaced, not appended to.
                assert len(registry["commits"]["files"]) == 2
                # Other entity: both survive side by side.
                assert "commits" in registry
                assert "issues" in registry
                assert registry["issues"]["files"] == ["new.json"]
            finally:
                os.chdir(original_cwd)


class TestOrganizationConfig:
    def test_organization_config(self):
        """Testa configuração de organização"""
        config = OrganizationConfig("test-org")

        assert config.org_name == "test-org"
        assert isinstance(config.repo_blacklist, list)
        # CoOps has a default blacklist; non-blacklisted repos should not be
        # skipped — whatever their other flags.
        assert config.should_skip_repo({"name": "some-normal-repo"}) is False

        repo = {"name": "test-repo", "private": True}
        assert config.should_skip_repo(repo) is False

        repo2 = {"name": "another-repo", "archived": True}
        assert config.should_skip_repo(repo2) is False
