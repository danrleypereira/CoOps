"""Tests for the GitHub query knowledge extracted in #28.

``coops.github.queries`` holds the REST URL templates and the GraphQL
documents — *what to ask*, not how to send it or what to do with the
answer. Its content is load-bearing in a way ordinary constants are not:
the transport hashes the whole GraphQL query text into its cache key
(``GitHubTransport._graphql_cache_key``), so any edit to a document —
even pure whitespace — orphans every cache entry and raw-layer document
written before #28, and an offline replay (#199) stops on its first miss.

The test here migrated from ``test_github_api_additional.py`` (#31) pins
the fields of the commit-history document that the raw tier cannot
recover later; the URL builders are exercised through the orchestration
tests in ``test_github_api.py`` and the transport tests.
"""

import re
from unittest.mock import patch

from coops.utils.github_api import GitHubAPIClient


class TestCommitHistoryDocument:
    """The GraphQL documents in ``coops.github.queries``."""

    def test_selects_recoverable_fields(self, tmp_path):
        """The GraphQL query must request the fields the raw tier cannot recover
        later: the full message body, the committer, and the parent shas."""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))
        captured_queries = []

        def mock_graphql(query, variables=None, use_cache=True, timeout=4):
            captured_queries.append(query)
            return {"data": {"repository": {"defaultBranchRef": None}}}

        with patch.object(client, 'graphql', side_effect=mock_graphql):
            client.graphql_commit_history("owner", "repo", page_size=10)

        assert captured_queries
        query = captured_queries[0]
        # `\bmessage\b` so the full-body `message` field is selected, not only
        # `messageHeadline` (which shares the prefix).
        assert re.search(r"\bmessage\b", query)
        assert "committer { name email date user { login databaseId } }" in query
        assert "parents(first: 100) { nodes { oid } }" in query
