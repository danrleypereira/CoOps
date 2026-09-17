"""Shared data processing helpers for the Silver layer."""

from typing import List, Any


def strip_metadata(data: List[Any]) -> List[Any]:
    """Remove the _metadata entry from the beginning of a bronze data list.

    Bronze layer JSON files start with a metadata dict containing '_metadata'.
    This helper strips that entry so downstream processing only sees real records.
    """
    if isinstance(data, list) and data and isinstance(data[0], dict) and '_metadata' in data[0]:
        return data[1:]
    return data
