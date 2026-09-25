"""Behavioural checks for the extracted transport (issue #27).

The move from ``coops/utils/github_api.py`` to ``coops/github/client.py``
must be behaviour-identical, and three of the transported properties were
broken and fixed once each while landing (#199): offline serves a cached
body regardless of ETag, an offline miss raises :class:`OfflineCacheMiss`
instead of returning ``None``, and offline mode cannot write — no cache
body, no ETag sidecar, no watermark-shaped URL it would ever write under.
These stub the HTTP boundary on the module that now owns it
(``coops.github.client.requests``) and assert on the call count, because a
green test that never asserted on the call count would prove nothing: the
failure mode is precisely a response quietly coming from somewhere other
than the cache.

The last two tests pin the structure the extraction created:
``github_api.requests`` must keep resolving (tests stub the transport
through it) and the import cycle broken by the lazy adapter re-export in
``coops/github/__init__.py`` must not come back.
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from coops.github.client import OfflineCacheMiss as ClientOfflineCacheMiss
from coops.utils.github_api import GitHubAPIClient, OfflineCacheMiss

#: ``tests/unit/x.py`` → repository root (for subprocess PYTHONPATH).
REPO_ROOT = Path(__file__).resolve().parents[2]


def _no_network():
    """A stubbed transport whose only job is to fail if it is ever reached."""
    return Mock(side_effect=AssertionError("offline mode must not touch the network"))


def test_offline_warm_etagged_entry_served_with_zero_network_calls(tmp_path):
    """A warm entry *with* an ETag must be served without revalidation:
    online it would send ``If-None-Match``, and a blocked network would
    turn that into ``None`` — the entry silently leaving the replay."""
    client = GitHubAPIClient(
        token="test", cache_dir=str(tmp_path / "cache"), offline=True
    )
    url = "https://api.github.com/repos/test-org/repo/issues?per_page=100&page=1"
    body = [{"number": 1}, {"number": 2}]

    client._cache_set(url, body)
    client._etag_set(url, '"etag-warm"')

    transport = _no_network()
    with patch("coops.github.client.requests.get", transport):
        result = client.get_with_cache(url)

    assert result == body
    assert transport.call_count == 0
    assert client.cache_hits == 1
    assert client.cache_misses == 0


def test_offline_miss_raises_offlinecachemiss_naming_the_url(tmp_path):
    client = GitHubAPIClient(
        token="test", cache_dir=str(tmp_path / "cache"), offline=True
    )
    url = "https://api.github.com/orgs/test-org/repos?per_page=100&page=1"

    transport = _no_network()
    with patch("coops.github.client.requests.get", transport), pytest.raises(
        OfflineCacheMiss
    ) as exc_info:
        client.get_with_cache(url)

    assert url in str(exc_info.value)
    assert exc_info.value.url == url
    assert transport.call_count == 0
    # The re-export must be the same class the transport raises, or the
    # adapter's `except OfflineCacheMiss` would stop catching it.
    assert isinstance(exc_info.value, ClientOfflineCacheMiss)


def test_offline_mode_cannot_reach_the_cache_writers(tmp_path):
    """``_cache_set``/``_etag_set`` must be unreachable while offline: an
    offline run replays a fixed cache, so a write would corrupt the very
    corpus under replay. The cache directory must also come out exactly as
    it went in — no new keys, no rewritten bodies, no watermarks."""
    client = GitHubAPIClient(
        token="test", cache_dir=str(tmp_path / "cache"), offline=True
    )
    url = "https://api.github.com/repos/test-org/repo"
    client._cache_set(url, {"id": 1})
    before = sorted(os.listdir(client.cache_dir))

    def _forbidden(*args, **kwargs):
        raise AssertionError("offline mode must not write the cache")

    client._cache_set = _forbidden
    client._etag_set = _forbidden

    with patch("coops.github.client.requests.get", _no_network()):
        assert client.get_with_cache(url) == {"id": 1}

    assert sorted(os.listdir(client.cache_dir)) == before


def test_github_api_requests_attribute_still_resolves():
    """Tests stub the HTTP boundary through ``github_api.requests`` (e.g.
    ``patch("coops.utils.github_api.requests.get")``); the import must keep
    resolving even though no code in that module uses it anymore."""
    import coops.utils.github_api as github_api

    assert github_api.requests is sys.modules["requests"]


@pytest.mark.parametrize(
    "statement",
    [
        "import coops.utils.github_api",
        "import coops.github",
        "import coops.github.adapter",
        "import coops.github.client",
        "import coops.github.mapper; import coops.utils.github_api",
        "import coops.utils.cache_fold",
        "from coops.github import GitHubSourceAdapter",
        "from coops.github.adapter import GitHubSourceAdapter; "
        "from coops.utils.github_api import GitHubAPIClient",
    ],
)
def test_every_import_order_resolves(statement):
    """The extraction created the first utils→github import edge; with the
    adapter eagerly re-exported from ``coops/github/__init__.py`` every
    entry order died on a partially initialized module. Each order must
    keep importing cleanly, in a fresh interpreter, from this tree."""
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    result = subprocess.run(
        [sys.executable, "-c", statement],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, (
        f"import failed: {statement}\n{result.stderr}"
    )
