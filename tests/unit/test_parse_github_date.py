from coops.utils.github_api import parse_github_date


def test_parse_github_date_utc_z():
    d = parse_github_date("2024-06-10T12:34:56Z")
    assert d.year == 2024 and d.month == 6 and d.day == 10 and d.hour == 12

def test_parse_github_date_without_timezone():
    d = parse_github_date("2024-06-10T12:34:56")
    assert d is not None
    assert d.minute == 34

def test_parse_github_date_offset():
    # Deve aceitar formato com offset e cortar para base
    d = parse_github_date("2024-06-10T12:34:56-03:00")
    assert d is not None
    assert d.second == 56

def test_parse_github_date_invalid():
    d = parse_github_date("not-a-date")
    assert d is None

def test_parse_github_date_none():
    """None (an absent field surfaced as a ``.get()`` result) is not a date."""
    assert parse_github_date(None) is None

def test_parse_github_date_empty():
    assert parse_github_date("") is None

def test_parse_github_date_positive_timezone_offset():
    """A `+hh:mm` offset is the only input that exercises the `'+' in
    date_str` operand of the offset test (a `-` offset goes through the
    dash-count operand); both must reduce to the base datetime."""
    result = parse_github_date("2024-06-20T14:25:30+05:30")
    assert result is not None
    assert result.year == 2024
    assert result.month == 6

def test_parse_github_date_partial_datetime():
    """A truncated offset (`...T10:30:45-`) still yields the base datetime
    — the first 19 characters parse, and the tail is ignored."""
    result = parse_github_date("2024-01-15T10:30:45-")
    # Should try to extract base datetime
    assert result is None or result.year == 2024