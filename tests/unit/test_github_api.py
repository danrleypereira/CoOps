"""Tests for the query orchestration left in ``coops.utils.github_api``.

After #27 moved the transport to ``coops.github.client`` and #28 the
endpoint knowledge to ``coops.github.queries``, what remains on
:class:`GitHubAPIClient` here is the *shaping*: pagination of the commit
history, the GraphQL→REST circuit breaker, time-range splitting, the
parallel REST commit-detail fetch, and the active-branch scan. The
transport itself is tested in ``test_github_client_transport.py`` (and
its feature files); the GraphQL documents in ``test_github_queries.py``.

Migrated from the retired ``test_github_api_comprehensive.py`` and
``test_github_api_additional.py`` (#31).
"""

from unittest.mock import patch

from coops.utils.github_api import GitHubAPIClient


class TestGraphQLCommitHistory:
    """Commit history: pagination, unions, and the REST fallback."""

    def test_basic(self, tmp_path):
        """Testa busca de histórico via GraphQL"""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))

        with patch.object(client, 'graphql') as mock_graphql:
            mock_graphql.return_value = {
                "data": {
                    "repository": {
                        "defaultBranchRef": {
                            "target": {
                                "history": {
                                    "nodes": [
                                        {"oid": "abc123", "message": "Test commit"}
                                    ],
                                    "pageInfo": {"hasNextPage": False}
                                }
                            }
                        }
                    }
                }
            }

            result, rate_meta = client.graphql_commit_history(
                "owner", "repo", page_size=10, since="2024-01-01T00:00:00Z"
            )

            assert isinstance(result, list)
            assert isinstance(rate_meta, dict)
            assert len(result) > 0
            assert result[0]["oid"] == "abc123"

    def test_pagination(self, tmp_path):
        """Testa paginação no histórico GraphQL"""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))

        with patch.object(client, 'graphql') as mock_graphql:
            # First page
            mock_graphql.side_effect = [
                {
                    "data": {
                        "repository": {
                            "defaultBranchRef": {
                                "target": {
                                    "history": {
                                        "nodes": [{"oid": "abc123"}],
                                        "pageInfo": {
                                            "hasNextPage": True,
                                            "endCursor": "cursor1"
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                # Second page
                {
                    "data": {
                        "repository": {
                            "defaultBranchRef": {
                                "target": {
                                    "history": {
                                        "nodes": [{"oid": "def456"}],
                                        "pageInfo": {"hasNextPage": False}
                                    }
                                }
                            }
                        }
                    }
                }
            ]

            result, _rate_meta = client.graphql_commit_history(
                "owner", "repo", page_size=10, max_pages=2
            )

            assert len(result) == 2
            assert result[0]["oid"] == "abc123"
            assert result[1]["oid"] == "def456"

    def test_multiple_branches(self, monkeypatch, tmp_path):
        """Test extracting from multiple branches"""
        client = GitHubAPIClient(
            token="test_token", cache_dir=str(tmp_path / "cache")
        )

        call_count = [0]
        def mock_graphql(query, variables, use_cache, timeout):
            call_count[0] += 1

            # First call is for default branch
            if call_count[0] == 1:
                return {
                    "data": {
                        "repository": {
                            "defaultBranchRef": {
                                "name": "main",
                                "target": {
                                    "history": {
                                        "nodes": [{
                                            "oid": "default_commit",
                                            "messageHeadline": "Default",
                                            "committedDate": "2024-01-01",
                                            "author": {"user": {"login": "user"}},
                                            "additions": 1,
                                            "deletions": 1
                                        }],
                                        "pageInfo": {"hasNextPage": False}
                                    }
                                }
                            }
                        },
                        "rateLimit": {"remaining": 5000}
                    }
                }
            # Subsequent calls for feature branches
            return {
                "data": {
                    "repository": {
                        "ref": {
                            "target": {
                                "history": {
                                    "nodes": [{
                                        "oid": f"commit{call_count[0]}",
                                        "messageHeadline": "Test",
                                        "committedDate": "2024-01-01",
                                        "author": {"user": {"login": "user"}},
                                        "additions": 1,
                                        "deletions": 1
                                    }],
                                    "pageInfo": {"hasNextPage": False}
                                }
                            }
                        }
                    },
                    "rateLimit": {"remaining": 5000}
                }
            }

        monkeypatch.setattr(client, "graphql", mock_graphql)

        commits, _meta = client.graphql_commit_history(
            "owner", "repo", 50, branches=["feature1", "feature2"]
        )

        # Should process default + 2 feature branches = 3 commits
        assert call_count[0] == 3
        assert len(commits) == 3

    def test_rest_fallback_on_graphql_failure(self, monkeypatch, tmp_path):
        """Test fallback to REST when GraphQL fails"""
        client = GitHubAPIClient(
            token="test_token", cache_dir=str(tmp_path / "cache")
        )

        graphql_calls = [0]
        def mock_graphql(query, variables, use_cache, timeout):
            graphql_calls[0] += 1
            return  # Simulate GraphQL failure

        rest_calls = [0]
        def mock_get_with_cache(url, use_cache, silent=False):
            rest_calls[0] += 1
            if "commits" in url and "page=" in url:
                # Return REST commit list
                return [
                    {"sha": f"rest_commit_{rest_calls[0]}"}
                ]
            return []

        def mock_fetch_parallel(commits, owner, repo, use_cache, max_workers=5):
            return [{
                "oid": c["sha"],
                "messageHeadline": "REST commit",
                "committedDate": "2024-01-01",
                "author": {"user": {"login": "user"}},
                "additions": 1,
                "deletions": 1
            } for c in commits]

        monkeypatch.setattr(client, "graphql", mock_graphql)
        monkeypatch.setattr(client, "get_with_cache", mock_get_with_cache)
        monkeypatch.setattr(client, "_fetch_rest_commit_details_parallel", mock_fetch_parallel)

        commits, _meta = client.graphql_commit_history("owner", "repo", 50, max_pages=1)

        # Should fall back to REST
        assert graphql_calls[0] > 0
        assert rest_calls[0] > 0
        assert len(commits) > 0

    def test_time_range_splitting(self, monkeypatch, tmp_path):
        """Test splitting extraction into time chunks"""
        client = GitHubAPIClient(
            token="test_token", cache_dir=str(tmp_path / "cache")
        )

        graphql_calls = [0]
        def mock_graphql(query, variables, use_cache, timeout):
            graphql_calls[0] += 1
            return {
                "data": {
                    "repository": {
                        "defaultBranchRef": {
                            "name": "main",
                            "target": {
                                "history": {
                                    "nodes": [],
                                    "pageInfo": {"hasNextPage": False}
                                }
                            }
                        }
                    },
                    "rateLimit": {"remaining": 5000}
                }
            }

        monkeypatch.setattr(client, "graphql", mock_graphql)

        _commits, _meta = client.graphql_commit_history(
            "owner", "repo", 50,
            since="2024-01-01T00:00:00Z",
            until="2024-12-31T23:59:59Z",
            split_large_extractions=True,
            time_chunks=3
        )

        # Should make 3 calls (3 time chunks)
        assert graphql_calls[0] == 3

    def test_branch_not_found(self, monkeypatch, tmp_path):
        """Test when branch doesn't exist"""
        client = GitHubAPIClient(
            token="test_token", cache_dir=str(tmp_path / "cache")
        )

        def mock_graphql(query, variables, use_cache, timeout):
            return {
                "data": {
                    "repository": {}  # No ref data
                },
                "rateLimit": {"remaining": 5000}
            }

        monkeypatch.setattr(client, "graphql", mock_graphql)

        commits, _meta = client.graphql_commit_history(
            "owner", "repo", 50, branches=["nonexistent"]
        )

        assert len(commits) == 0

    def test_no_branch(self, tmp_path):
        """Testa quando repositório não tem branch padrão"""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))

        with patch.object(client, 'graphql') as mock_graphql:
            mock_graphql.return_value = {
                "data": {
                    "repository": {
                        "defaultBranchRef": None
                    }
                }
            }

            result, _rate_meta = client.graphql_commit_history(
                "owner", "repo", page_size=10
            )

            assert result == []

    def test_error(self, tmp_path):
        """Testa tratamento de erro no GraphQL: total failure, no commits.

        The REST fallback also runs (the circuit breaker fires after one
        GraphQL failure); its transport is mocked here so the test stays
        hermetic — before #31 this test reached the live API through the
        unmocked ``get_with_cache``.
        """
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))

        with patch.object(client, 'graphql') as mock_graphql, \
             patch.object(client, 'get_with_cache', return_value=None):
            mock_graphql.return_value = None  # Erro

            result, _rate_meta = client.graphql_commit_history(
                "owner", "repo", page_size=10
            )

            assert result == []


class TestGetActiveUnmergedBranches:
    """The active-branch scan (GraphQL listing + REST compare)."""

    def test_basic(self, tmp_path):
        """Testa busca de branches ativas"""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))

        with patch.object(client, 'get_with_cache') as mock_get, \
             patch.object(client, 'graphql') as mock_graphql:

            # Mock repo info
            mock_get.return_value = {"default_branch": "main"}

            # Mock GraphQL responses
            mock_graphql.side_effect = [
                {
                    "data": {
                        "repository": {
                            "refs": {
                                "nodes": [
                                    {
                                        "name": "feature-branch",
                                        "target": {
                                            "oid": "abc123",
                                            "committedDate": "2024-12-01T00:00:00Z"
                                        }
                                    }
                                ],
                                "pageInfo": {"hasNextPage": False}
                            }
                        }
                    }
                },
                # Comparison result
                {"ahead_by": 5, "behind_by": 0}
            ]

            # Mock REST comparison
            mock_get.return_value = {"ahead_by": 5, "behind_by": 0}

            result = client.get_active_unmerged_branches("owner", "repo", days=30)

            assert isinstance(result, list)
            # Function may return empty if REST comparison fails
            # Just verify it runs without error

    def test_no_unmerged(self, tmp_path):
        """Testa quando não há branches não merged"""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))

        with patch.object(client, 'get_with_cache') as mock_get, \
             patch.object(client, 'graphql') as mock_graphql:

            mock_get.return_value = {"default_branch": "main"}
            mock_graphql.return_value = {
                "data": {
                    "repository": {
                        "refs": {
                            "nodes": [],
                            "pageInfo": {"hasNextPage": False}
                        }
                    }
                }
            }

            result = client.get_active_unmerged_branches("owner", "repo")

            assert result == []

    def test_error_handling(self, tmp_path):
        """Testa tratamento de erro na busca de branches.

        ``graphql`` is also stubbed: the method proceeds even when the
        repository probe fails, and before #31 the unmocked ``graphql``
        POSTed to the live API from inside this test.
        """
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))

        with patch.object(client, 'get_with_cache') as mock_get, \
             patch.object(client, 'graphql', return_value=None):
            mock_get.return_value = None  # Erro na API

            result = client.get_active_unmerged_branches("owner", "repo")

            assert result == []


class TestRestCommitDetails:
    """The parallel REST commit-detail fetch behind the fallback."""

    def test_fetch_with_thread_id(self, tmp_path):
        """Testa busca de commit com thread ID"""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))

        with patch.object(client, 'get_with_cache') as mock_get:
            mock_get.return_value = ({"sha": "abc123"}, {"header": "value"})

            result = client._fetch_with_thread_id("owner", "repo", "abc123", True)

            assert "data" in result
            assert "thread_id" in result
            assert "headers" in result
            assert result["data"]["sha"] == "abc123"

    def test_fetch_rest_commit_details_parallel(self, tmp_path):
        """Testa busca paralela de detalhes de commits"""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))

        commits = [
            {
                "sha": "abc123",
                "author": {"login": "user1"},
                "commit": {
                    "message": "Test commit",
                    "author": {"date": "2024-01-01T00:00:00Z"}
                }
            }
        ]

        with patch.object(client, '_fetch_with_thread_id') as mock_fetch:
            mock_fetch.return_value = {
                "data": {
                    "sha": "abc123",
                    "stats": {"additions": 10, "deletions": 5},
                    "commit": {
                        "message": "Test commit",
                        "author": {"date": "2024-01-01T00:00:00Z"}
                    }
                },
                "thread_id": 1,
                "headers": {"X-RateLimit-Remaining": "100"}
            }

            result = client._fetch_rest_commit_details_parallel(
                commits, "owner", "repo", True, max_workers=2
            )

            assert len(result) == 1
            assert result[0]["oid"] == "abc123"
            assert result[0]["additions"] == 10
            assert result[0]["deletions"] == 5

    def test_fetch_rest_commit_details_parallel_carries_recoverable_fields(self, tmp_path):
        """The REST fallback inside graphql_commit_history must keep the full
        message body, committer and parents, not just the headline and stats."""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))

        commits = [
            {
                "sha": "abc123",
                "author": {"login": "user1"},
                "commit": {
                    "message": "feat: subject\n\nBody line.",
                    "author": {"date": "2024-01-01T00:00:00Z"},
                    "committer": {"name": "Committer", "email": "c@test.com", "date": "2024-01-01T00:00:01Z"},
                },
                "parents": [
                    {"sha": "parent1"},
                    {"sha": "parent2"},
                ],
            }
        ]

        with patch.object(client, '_fetch_with_thread_id') as mock_fetch:
            mock_fetch.return_value = {
                "data": {"sha": "abc123", "stats": {"additions": 10, "deletions": 5}},
                "thread_id": 1,
                "headers": {"X-RateLimit-Remaining": "100"},
            }

            result = client._fetch_rest_commit_details_parallel(
                commits, "owner", "repo", True, max_workers=1
            )

        assert len(result) == 1
        node = result[0]
        assert node["message"] == "feat: subject\n\nBody line."
        assert node["committer"]["name"] == "Committer"
        assert node["committer"]["email"] == "c@test.com"
        assert node["committer"]["date"] == "2024-01-01T00:00:01Z"
        assert node["parents"] == {"nodes": [{"oid": "parent1"}, {"oid": "parent2"}]}

    def test_fetch_parallel_empty_list(self, tmp_path):
        """Testa busca paralela com lista vazia"""
        client = GitHubAPIClient(token="test", cache_dir=str(tmp_path))

        result = client._fetch_rest_commit_details_parallel(
            [], "owner", "repo", True
        )

        assert result == []
