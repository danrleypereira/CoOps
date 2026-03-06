"""Tests for src/utils/data_helpers.py — strip_metadata helper."""

from utils.data_helpers import strip_metadata


class TestStripMetadata:
    def test_empty_list(self):
        assert strip_metadata([]) == []

    def test_non_list_input_string(self):
        assert strip_metadata("not a list") == "not a list"

    def test_non_list_input_none(self):
        assert strip_metadata(None) is None

    def test_non_list_input_dict(self):
        d = {"key": "value"}
        assert strip_metadata(d) == d

    def test_list_with_metadata_first_element(self):
        data = [{"_metadata": {"ts": "2024-01-01"}}, {"id": 1}, {"id": 2}]
        result = strip_metadata(data)
        assert result == [{"id": 1}, {"id": 2}]

    def test_list_without_metadata(self):
        data = [{"id": 1}, {"id": 2}]
        assert strip_metadata(data) == [{"id": 1}, {"id": 2}]

    def test_first_element_not_a_dict(self):
        data = ["string", {"id": 1}]
        assert strip_metadata(data) == ["string", {"id": 1}]

    def test_first_element_dict_without_metadata_key(self):
        data = [{"other_key": "value"}, {"id": 1}]
        assert strip_metadata(data) == [{"other_key": "value"}, {"id": 1}]

    def test_single_metadata_element(self):
        """Stripping metadata from a single-element list yields empty list."""
        data = [{"_metadata": {"ts": "2024-01-01"}}]
        assert strip_metadata(data) == []
