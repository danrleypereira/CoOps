from coops.utils.github_api import GitHubAPIClient


def test_split_time_range_no_dates():
    client = GitHubAPIClient(token="x")
    ranges = client._split_time_range(None, None, chunks=3)
    assert ranges == [(None, None)]

def test_split_time_range_single_year():
    client = GitHubAPIClient(token="x")
    since = "2024-01-01T00:00:00Z"
    until = "2025-01-01T00:00:00Z"
    ranges = client._split_time_range(since, until, chunks=3)
    assert len(ranges) == 3
    # Garantir ordem cronológica
    assert ranges[0][0] == since
    assert ranges[-1][1] == until

def test_split_time_range_invalid_format():
    client = GitHubAPIClient(token="x")
    ranges = client._split_time_range("invalid", "also-invalid", chunks=2)
    # Retorna (None, None) para indicar datas inválidas
    assert ranges == [(None, None)]

def test_split_time_range_only_since(tmp_path):
    """Test split with only since parameter"""
    client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

    result = client._split_time_range(since="2024-01-01T00:00:00Z", until=None, chunks=2)

    assert len(result) == 2
    # Should split from since to now
    for chunk_start, _chunk_end in result:
        assert chunk_start is not None

def test_split_time_range_only_until(tmp_path):
    """Test split with only until parameter"""
    client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

    result = client._split_time_range(since=None, until="2024-12-31T23:59:59Z", chunks=2)

    assert len(result) == 2
    # Should split from default (1 year ago) to until
    for _chunk_start, chunk_end in result:
        assert chunk_end is not None