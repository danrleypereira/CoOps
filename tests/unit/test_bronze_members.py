"""
Testes unitários para o módulo bronze.members.

Testa a extração de membros da organização: lista paginada, fallback para
contributors e perfis detalhados (necessários para o member analytics do Silver).
"""

import pytest
from unittest.mock import patch, MagicMock
from coops.bronze.members import extract_members


def make_client(members=None, contributors=None, profiles=None):
    """Client falso: listas via get_paginated, perfis via get_with_cache."""
    client = MagicMock()
    profiles = profiles if profiles is not None else {}

    def get_paginated(url, use_cache=True, per_page=50, **kwargs):
        if url.endswith("/members"):
            return members
        if url.endswith("/contributors"):
            return contributors(url) if callable(contributors) else contributors
        return None

    def get_with_cache(url, use_cache=True):
        login = url.rsplit("/", 1)[-1]
        if "/users/" in url:
            return profiles.get(login, {"login": login, "created_at": "2020-01-01T00:00:00Z",
                                        "public_repos": 3, "followers": 1})
        return None

    client.get_paginated.side_effect = get_paginated
    client.get_with_cache.side_effect = get_with_cache
    return client


@pytest.fixture
def saved():
    """Captura o que é salvo, por caminho."""
    data = {}

    def fake_save(payload, path, *args, **kwargs):
        data[path] = payload
        return path

    with patch('coops.bronze.members.save_json_data', side_effect=fake_save):
        yield data


def config(org="test-org"):
    cfg = MagicMock()
    cfg.org_name = org
    return cfg


class TestExtractMembers:
    """Testes para extract_members"""

    def test_members_api_success(self, saved, capsys):
        client = make_client(members=[{"login": "user1"}, {"login": "user2"}])
        result = extract_members(client, config())

        assert result == ["data/bronze/members_basic.json", "data/bronze/members_detailed.json"]
        assert [m["login"] for m in saved["data/bronze/members_basic.json"]] == ["user1", "user2"]
        assert "Successfully fetched 2 organization members" in capsys.readouterr().out

    def test_members_list_is_paginated(self, saved):
        """A lista de membros não pode parar na primeira página (30 itens)."""
        client = make_client(members=[{"login": "user1"}])
        extract_members(client, config("my-organization"), use_cache=False)

        url = client.get_paginated.call_args_list[0].args[0]
        assert url == "https://api.github.com/orgs/my-organization/members"
        assert client.get_paginated.call_args_list[0].kwargs == {"use_cache": False, "per_page": 100}

    def test_detailed_file_has_profiles(self, saved):
        profile = {"login": "user1", "created_at": "2015-05-05T00:00:00Z", "public_repos": 42, "followers": 7}
        client = make_client(members=[{"login": "user1", "type": "User"}], profiles={"user1": profile})
        extract_members(client, config())

        detailed = saved["data/bronze/members_detailed.json"]
        assert detailed == [{"login": "user1", "type": "User", "created_at": "2015-05-05T00:00:00Z",
                             "public_repos": 42, "followers": 7}]
        client.get_with_cache.assert_called_once_with("https://api.github.com/users/user1", True)

    def test_profile_request_respects_cache_flag(self, saved):
        client = make_client(members=[{"login": "user1"}])
        extract_members(client, config(), use_cache=False)
        client.get_with_cache.assert_called_once_with("https://api.github.com/users/user1", False)

    def test_missing_profiles_are_skipped(self, saved, capsys):
        client = make_client(members=[{"login": "ghost"}, {"login": "user2"}, {"type": "User"}],
                             profiles={"ghost": None})
        extract_members(client, config())

        assert [m["login"] for m in saved["data/bronze/members_detailed.json"]] == ["user2"]
        out = capsys.readouterr().out
        assert "Could not fetch profile for ghost" in out
        assert "Fetched 1 of 3 member profiles" in out

    def test_does_not_write_one_file_per_member(self, saved):
        client = make_client(members=[{"login": "user1"}, {"login": "user2"}])
        extract_members(client, config())
        assert set(saved) == {"data/bronze/members_basic.json", "data/bronze/members_detailed.json"}


class TestContributorFallback:
    """Fallback quando a API de membros não retorna ninguém."""

    REPOS = [
        {"_metadata": {"extracted_at": "2024-01-01"}},
        None,
        {"name": "invalid"},  # sem full_name
        {"full_name": "test-org/repo1", "name": "repo1"},
        {"full_name": "test-org/repo2", "name": "repo2"},
    ]

    def test_fallback_accumulates_and_sorts_contributors(self, saved, capsys):
        def contributors(url):
            if "repo1" in url:
                return [{"login": "low", "contributions": 5}, {"login": "top", "contributions": 30}]
            return [{"login": "top", "contributions": 30}]

        client = make_client(members=[], contributors=contributors)
        with patch('coops.bronze.members.load_json_data', return_value=self.REPOS):
            extract_members(client, config())

        basic = saved["data/bronze/members_basic.json"]
        assert [(m["login"], m["contributions_total"]) for m in basic] == [("top", 60), ("low", 5)]
        assert basic[0]["data_source"] == "contributors_api"
        contrib_urls = [c.args[0] for c in client.get_paginated.call_args_list[1:]]
        assert contrib_urls == ["https://api.github.com/repos/test-org/repo1/contributors",
                                "https://api.github.com/repos/test-org/repo2/contributors"]
        # detailed profiles keep the fallback's contribution counts
        detailed = saved["data/bronze/members_detailed.json"]
        assert [(m["login"], m["contributions_total"]) for m in detailed] == [("top", 60), ("low", 5)]

        out = capsys.readouterr().out
        assert "Fallback successful: Found 2 active contributors" in out
        assert "Top contributor: top (60 contributions)" in out

    @pytest.mark.parametrize("members", [[], None])
    def test_no_repositories_writes_empty_files(self, saved, capsys, members):
        client = make_client(members=members)
        with patch('coops.bronze.members.load_json_data', return_value=None):
            result = extract_members(client, config())

        assert result == ["data/bronze/members_basic.json", "data/bronze/members_detailed.json"]
        assert saved == {"data/bronze/members_basic.json": [], "data/bronze/members_detailed.json": []}
        out = capsys.readouterr().out
        assert "Fallback impossible" in out
        assert "Created empty member files" in out

    def test_no_contributors_writes_empty_files(self, saved, capsys):
        client = make_client(members=[], contributors=[])
        with patch('coops.bronze.members.load_json_data', return_value=self.REPOS):
            extract_members(client, config())

        assert saved == {"data/bronze/members_basic.json": [], "data/bronze/members_detailed.json": []}
        assert "Fallback failed" in capsys.readouterr().out
