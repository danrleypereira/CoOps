"""Tests for the transport extracted from ``coops/utils/github_api.py`` (#27).

The move to ``coops/github/client.py`` must be behaviour-identical, and
three of the transported properties were broken and fixed once each while
landing (#199): offline serves a cached body regardless of ETag, an
offline miss raises :class:`OfflineCacheMiss` instead of returning
``None``, and offline mode cannot write — no cache body, no ETag sidecar,
no watermark-shaped URL it would ever write under. These stub the HTTP
boundary on the module that now owns it
(``coops.github.client.requests``) and assert on the call count, because a
green test that never asserted on the call count would prove nothing: the
failure mode is precisely a response quietly coming from somewhere other
than the cache.

Below those structural pins sit the transport's day-to-day behaviours,
migrated here from the retired ``test_github_api_*`` sprawl (#31):
construction and the URL-keyed body cache, ``get_with_cache`` (retries,
error statuses, ``return_headers``, ``silent``), pagination,
``graphql`` (cache, error vocabularies) and rate-limit logging. The
feature-sized transports — ETag revalidation, corpus capture, offline
replay, the MongoDB raw layer — live in their own
``test_github_client_<feature>.py`` files.

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
import requests

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


# -- Migrated from the retired test_github_api_* files (#31) --------------
#
# Bodies are moved verbatim except where a constructor relied on the
# default ``cache_dir="cache"`` and would write into the checkout; those
# take a ``tmp_path`` cache like every other test here.


class TestTransportConstruction:
    """``__init__`` and the URL-keyed body cache."""

    def test_client_initialization(self, tmp_path):
        """Testa inicialização do cliente"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test_token", cache_dir=cache_dir)

        assert client.token == "test_token"
        assert client.headers["Authorization"] == "Bearer test_token"
        assert os.path.exists(cache_dir)

    def test_get_cache_key(self, tmp_path):
        """Testa geração de chave de cache"""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path / "cache"))

        key1 = client._get_cache_key("https://api.github.com/repos/test/repo")
        key2 = client._get_cache_key("https://api.github.com/repos/test/repo")
        key3 = client._get_cache_key("https://api.github.com/repos/other/repo")

        assert key1 == key2
        assert key1 != key3
        assert key1.endswith(".json")

    def test_cache_set_and_get(self, tmp_path):
        """Testa armazenamento e recuperação de cache"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test", cache_dir=cache_dir)

        test_data = {"test": "data", "value": 123}
        cache_key = "test_key"

        client._cache_set(cache_key, test_data)
        cached = client._cache_get(cache_key)

        assert cached == test_data

    def test_cache_get_missing(self, tmp_path):
        """Testa recuperação de cache inexistente"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test", cache_dir=cache_dir)

        cached = client._cache_get("nonexistent_key")
        assert cached is None


class TestGetWithCache:
    """REST reads: error statuses, retries, headers, silence."""

    def test_get_with_cache_404(self, tmp_path, capsys):
        """Testa get_with_cache com erro 404"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test", cache_dir=cache_dir)

        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            result = client.get_with_cache("https://api.github.com/test", use_cache=False)

            assert result is None
            captured = capsys.readouterr()
            assert "404" in captured.out

    def test_get_with_cache_403_forbidden_non_rate_limit(self, tmp_path, capsys):
        """Test 403 response without rate limit (private resource)"""
        client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 403
            mock_response.text = "Resource private or forbidden"
            mock_get.return_value = mock_response

            result = client.get_with_cache("https://api.github.com/test", use_cache=False)

            assert result is None
            captured = capsys.readouterr()
            assert "might be private" in captured.out

    def test_unknown_status_code(self, tmp_path):
        """Test handling of unexpected status codes"""
        client = GitHubAPIClient(
            token="test_token", cache_dir=str(tmp_path / "cache")
        )

        mock_response = Mock()
        mock_response.status_code = 418  # I'm a teapot
        mock_response.text = "Unexpected error"

        with patch("requests.get", return_value=mock_response):
            result = client.get_with_cache(
                "https://api.github.com/test", use_cache=False, silent=True
            )
        assert result is None

    @pytest.mark.skip(reason="Trava no CI - retry infinito com rate limit")
    def test_get_with_cache_403_rate_limit(self, tmp_path, capsys):
        """Test 403 response with rate limit message"""
        client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 403
            mock_response.text = "API rate limit exceeded"
            mock_get.return_value = mock_response

            with patch('time.sleep') as mock_sleep:  # Don't actually sleep
                client.get_with_cache("https://api.github.com/test", use_cache=False, retries=1, backoff_base=0.001)

            # Should retry after rate limit
            assert mock_get.call_count >= 1
            # Verify sleep was called (exponential backoff)
            assert mock_sleep.call_count >= 0

    def test_get_with_cache_silent_mode(self, tmp_path):
        """Test that silent=True suppresses output"""
        client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"test": "data"}
            mock_response.headers = {}
            mock_get.return_value = mock_response

            result = client.get_with_cache("https://api.github.com/test", use_cache=False, silent=True)

            assert result == {"test": "data"}

    @patch('time.sleep', return_value=None)
    def test_get_with_cache_retry_on_500(self, mock_sleep, tmp_path):
        """Testa retry em erros 5xx"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test", cache_dir=cache_dir)

        with patch('requests.get') as mock_get:
            mock_response_fail = Mock()
            mock_response_fail.status_code = 500

            mock_response_success = Mock()
            mock_response_success.status_code = 200
            mock_response_success.json.return_value = {"success": True}
            mock_response_success.headers = {
                'X-RateLimit-Remaining': '5000',
                'X-RateLimit-Limit': '5000'
            }

            mock_get.side_effect = [mock_response_fail, mock_response_success]

            result = client.get_with_cache("https://api.github.com/test", use_cache=False, retries=3)

            assert result == {"success": True}
            assert mock_get.call_count == 2
            assert mock_sleep.call_count >= 1

    @patch('time.sleep', return_value=None)
    def test_get_with_cache_timeout_retry(self, mock_sleep, tmp_path):
        """Testa retry em timeout"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test", cache_dir=cache_dir)

        with patch('requests.get') as mock_get:
            mock_response_success = Mock()
            mock_response_success.status_code = 200
            mock_response_success.json.return_value = {"success": True}
            mock_response_success.headers = {
                'X-RateLimit-Remaining': '5000',
                'X-RateLimit-Limit': '5000'
            }

            # Primeira chamada: timeout, segunda: sucesso
            mock_get.side_effect = [
                requests.exceptions.Timeout(),
                mock_response_success
            ]

            result = client.get_with_cache("https://api.github.com/test", use_cache=False, retries=3)

            assert result == {"success": True}
            assert mock_get.call_count == 2
            assert mock_sleep.call_count >= 1

    def test_get_with_cache_exhausted_retries(self, tmp_path, capsys):
        """Testa esgotamento de tentativas"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test", cache_dir=cache_dir)

        with patch('time.sleep'), patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_get.return_value = mock_response

            result = client.get_with_cache("https://api.github.com/test", use_cache=False, retries=2)

            assert result is None
            assert mock_get.call_count == 2
            captured = capsys.readouterr()
            assert "Exhausted retries" in captured.out

    def test_get_with_cache_request_exception(self, tmp_path, capsys):
        """Test generic RequestException is caught"""
        client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.RequestException("Connection error")

            result = client.get_with_cache("https://api.github.com/test", use_cache=False)

            assert result is None
            captured = capsys.readouterr()
            assert "Request error" in captured.out

    def test_get_with_cache_rate_limit_display(self, tmp_path, capsys):
        """Testa exibição de rate limit"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test", cache_dir=cache_dir)

        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": "test"}
            mock_response.headers = {
                'X-RateLimit-Remaining': '100',
                'X-RateLimit-Limit': '5000'
            }
            mock_get.return_value = mock_response

            client.get_with_cache("https://api.github.com/test", use_cache=False)

            captured = capsys.readouterr()
            assert "Rate limit" in captured.out
            assert "100" in captured.out

    def test_get_with_cache_return_headers_from_api(self, tmp_path):
        """Testa retorno de headers da API"""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))

        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": "test"}
            mock_response.headers = {"X-Custom": "value"}
            mock_get.return_value = mock_response

            data, headers = client.get_with_cache(
                "https://api.github.com/test",
                use_cache=False,
                return_headers=True
            )

            assert data == {"data": "test"}
            assert headers["X-Custom"] == "value"

    def test_get_with_cache_return_headers_from_cache(self, tmp_path):
        """Testa retorno de headers do cache (None)"""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))

        # Set cache first
        test_url = "https://api.github.com/test"
        test_data = {"cached": "data"}
        client._cache_set(test_url, test_data)

        data, headers = client.get_with_cache(test_url, return_headers=True)

        assert data == test_data
        assert headers is None  # No headers from cache


class TestPagination:
    """``get_paginated`` over list endpoints."""

    def test_get_paginated(self, tmp_path):
        """Testa paginação de resultados"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test", cache_dir=cache_dir)

        with patch.object(client, 'get_with_cache') as mock_get:
            mock_get.side_effect = [
                [{"id": 1}, {"id": 2}],
                [{"id": 3}],
            ]

            results = client.get_paginated("https://api.github.com/test", per_page=2)

            assert len(results) == 3
            assert results[0]["id"] == 1
            assert results[2]["id"] == 3

    def test_get_paginated_max_pages(self, tmp_path):
        """Testa limite de páginas"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test", cache_dir=cache_dir)

        with patch.object(client, 'get_with_cache') as mock_get:
            mock_get.return_value = [{"id": i} for i in range(50)]

            client.get_paginated("https://api.github.com/test", per_page=50, max_pages=2)

            assert mock_get.call_count == 2

    def test_get_paginated_warns_when_a_later_page_fails(self, tmp_path, capsys):
        """Uma página que falha no meio devolve o parcial, mas com aviso"""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path / "cache"))

        with patch.object(client, 'get_with_cache') as mock_get:
            mock_get.side_effect = [[{"id": 1}, {"id": 2}], None]

            results = client.get_paginated("https://api.github.com/test", per_page=2)

        assert results == [{"id": 1}, {"id": 2}]
        out = capsys.readouterr().out
        assert "Stopped paginating https://api.github.com/test at page 2" in out
        assert "returning the 2 items fetched so far" in out

    def test_get_paginated_first_page_failure_is_not_a_partial_result(self, tmp_path, capsys):
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path / "cache"))

        with patch.object(client, 'get_with_cache', return_value=None):
            assert client.get_paginated("https://api.github.com/test") == []

        assert "Stopped paginating" not in capsys.readouterr().out

    def test_get_paginated_non_list_response(self, tmp_path):
        """Testa paginação com resposta não-lista"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test", cache_dir=cache_dir)

        with patch.object(client, 'get_with_cache') as mock_get:
            mock_get.return_value = {"error": "not a list"}

            results = client.get_paginated("https://api.github.com/test")

            assert results == []
            assert mock_get.call_count == 1

    def test_get_paginated_with_params_in_url(self, tmp_path):
        """Test get_paginated preserves existing query params"""
        client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

        with patch.object(client, 'get_with_cache') as mock_get:
            mock_get.side_effect = [
                [{"id": 1}],  # Page 1
                []  # Empty page signals end
            ]

            result = client.get_paginated("https://api.github.com/test?state=open", use_cache=False)

            assert result == [{"id": 1}]
            # Check that params are preserved
            first_call = mock_get.call_args_list[0]
            assert "state=open" in first_call[0][0] or "state=open" in str(first_call)


class TestGraphqlTransport:
    """``graphql``: cache, and the error vocabulary it collapses to None."""

    def test_graphql_with_cache(self, tmp_path):
        """Testa GraphQL com cache"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test", cache_dir=cache_dir)

        query = "query { viewer { login } }"

        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": {"viewer": {"login": "test"}}}
            mock_post.return_value = mock_response

            result1 = client.graphql(query, use_cache=True)
            assert result1["data"]["viewer"]["login"] == "test"
            assert mock_post.call_count == 1

            result2 = client.graphql(query, use_cache=True)
            assert result2["data"]["viewer"]["login"] == "test"
            assert mock_post.call_count == 1

    def test_graphql_errors(self, tmp_path, capsys):
        """Testa tratamento de erros GraphQL"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test", cache_dir=cache_dir)

        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "errors": [{"type": "FORBIDDEN", "message": "Access denied"}]
            }
            mock_post.return_value = mock_response

            result = client.graphql("query { test }", use_cache=False)

            assert result is None
            captured = capsys.readouterr()
            assert "ERROR" in captured.out

    def test_graphql_service_unavailable(self, tmp_path, capsys):
        """Testa tratamento de SERVICE_UNAVAILABLE (commit stats)"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test", cache_dir=cache_dir)

        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "errors": [{
                    "type": "SERVICE_UNAVAILABLE",
                    "path": ["additions"],
                    "message": "Stats unavailable"
                }]
            }
            mock_post.return_value = mock_response

            result = client.graphql("query { test }", use_cache=False)

            assert result is None
            captured = capsys.readouterr()
            assert "Stats unavailable" in captured.out or "SERVICE_UNAVAILABLE" in captured.out

    def test_graphql_service_unavailable_non_stats(self, tmp_path):
        """Test SERVICE_UNAVAILABLE error for non-stats fields"""
        client = GitHubAPIClient(
            token="test_token", cache_dir=str(tmp_path / "cache")
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errors": [
                {
                    "type": "SERVICE_UNAVAILABLE",
                    "path": ["repository", "name"],
                    "message": "Service temporarily unavailable"
                }
            ]
        }

        with patch("requests.post", return_value=mock_response):
            result = client.graphql("query { test }")

        assert result is None

    def test_graphql_403_rate_limit(self, tmp_path, capsys):
        """Test GraphQL 403 with rate limit"""
        client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 403
            mock_response.text = "rate limit exceeded"
            mock_post.return_value = mock_response

            result = client.graphql("query { viewer { login } }", use_cache=False)

            assert result is None
            captured = capsys.readouterr()
            assert "Rate limit exceeded" in captured.out

    def test_graphql_403_forbidden_no_rate_limit(self, tmp_path, capsys):
        """Test GraphQL 403 without rate limit"""
        client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 403
            mock_response.text = "Forbidden"
            mock_post.return_value = mock_response

            result = client.graphql("query { viewer { login } }", use_cache=False)

            assert result is None
            captured = capsys.readouterr()
            assert "Forbidden (403)" in captured.out

    def test_graphql_502_server_overload(self, tmp_path, capsys):
        """Test GraphQL 502 error"""
        client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 502
            mock_response.text = "Bad Gateway"
            mock_post.return_value = mock_response

            result = client.graphql("query { viewer { login } }", use_cache=False)

            assert result is None
            captured = capsys.readouterr()
            assert "502" in captured.out

    def test_graphql_500_503_errors(self, tmp_path, capsys):
        """Test GraphQL 500 and 503 errors"""
        client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

        for status in [500, 503]:
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = status
                mock_response.text = "Server Error"
                mock_post.return_value = mock_response

                result = client.graphql("query { viewer { login } }", use_cache=False)

                assert result is None
                captured = capsys.readouterr()
                assert str(status) in captured.out

    def test_graphql_other_status_codes(self, tmp_path, capsys):
        """Test GraphQL other unexpected status codes"""
        client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.text = "Bad Request"
            mock_post.return_value = mock_response

            result = client.graphql("query { viewer { login } }", use_cache=False)

            assert result is None
            captured = capsys.readouterr()
            assert "Request failed" in captured.out

    @patch('time.sleep', return_value=None)
    def test_graphql_timeout(self, mock_sleep, tmp_path, capsys):
        """Testa timeout em GraphQL"""
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient(token="test", cache_dir=cache_dir)

        with patch('requests.post') as mock_post:
            mock_post.side_effect = requests.exceptions.Timeout()

            result = client.graphql("query { test }", use_cache=False, timeout=1)

            assert result is None
            captured = capsys.readouterr()
            assert "Timeout" in captured.out

    def test_graphql_request_exception(self, tmp_path, capsys):
        """Test GraphQL generic request exception"""
        client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

        with patch('requests.post') as mock_post:
            mock_post.side_effect = requests.exceptions.RequestException("Connection error")

            result = client.graphql("query { viewer { login } }", use_cache=False)

            assert result is None
            captured = capsys.readouterr()
            assert "Request error" in captured.out

    def test_graphql_cache_serialization_error(self, tmp_path):
        """Test GraphQL handles cache serialization errors gracefully"""
        client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

        # Create non-serializable variables
        class NonSerializable:
            pass

        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": {"viewer": {"login": "test"}}}
            mock_post.return_value = mock_response

            # Should handle serialization error and still make request
            result = client.graphql("query { viewer { login } }", variables={"obj": NonSerializable()}, use_cache=True)

            assert result is not None
            assert result["data"]["viewer"]["login"] == "test"


class TestRateLimitLogging:
    """``_log_rate_limit`` with complete, partial and absent headers."""

    def test_log_rate_limit_all_headers_present(self, tmp_path, capsys):
        """Test log_rate_limit with all headers present"""
        client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

        mock_response = Mock()
        mock_response.headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "4500",
            "X-RateLimit-Reset": "1234567890"
        }

        client._log_rate_limit(mock_response, prefix="TEST")

        captured = capsys.readouterr()
        assert "4500" in captured.out
        assert "TEST" in captured.out

    def test_log_rate_limit_missing_remaining_header(self, tmp_path, capsys):
        """Test log_rate_limit when remaining header is missing"""
        client = GitHubAPIClient(token="test_token", cache_dir=str(tmp_path))

        mock_response = Mock()
        mock_response.headers = {
            "X-RateLimit-Limit": "5000",
            # Missing X-RateLimit-Remaining
            "X-RateLimit-Reset": "1234567890"
        }

        client._log_rate_limit(mock_response)

        captured = capsys.readouterr()
        # Should handle missing header gracefully - check for lowercase "Rate limit"
        assert "Rate limit" in captured.out or captured.out == ""

    def test_log_rate_limit_without_headers(self, tmp_path, capsys):
        """Testa logging quando não há headers de rate limit"""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))

        mock_response = Mock()
        mock_response.headers = {}

        client._log_rate_limit(mock_response)

        captured = capsys.readouterr()
        # Should print Unknown/Unknown when headers are missing
        assert "Unknown/Unknown" in captured.out
