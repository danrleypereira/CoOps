"""
Testes unitários para o módulo bronze.members.

Testa a extração de membros: união dos membros da organização com os
contributors dos repositórios, e perfis detalhados (necessários para o member
analytics do Silver).
"""

from unittest.mock import MagicMock, patch

import pytest

from coops.bronze.members import extract_members


def make_client(members=None, contributors=None, profiles=None, remaining=None):
    """Client falso: listas via get_paginated, perfis via get_with_cache.

    `remaining` é a sequência de valores de X-RateLimit-Remaining devolvidos
    pelas chamadas de perfil (None = sem cabeçalhos, como numa resposta do cache).
    """
    client = MagicMock()
    profiles = profiles if profiles is not None else {}
    remaining = list(remaining) if remaining is not None else []

    def get_paginated(url, use_cache=True, per_page=50, **kwargs):
        if url.endswith("/members"):
            return members
        if url.endswith("/contributors"):
            return contributors(url) if callable(contributors) else contributors
        return None

    def get_with_cache(url, use_cache=True, return_headers=False):
        login = url.rsplit("/", 1)[-1]
        data = None
        if "/users/" in url:
            data = profiles.get(login, {"login": login, "created_at": "2020-01-01T00:00:00Z",
                                        "public_repos": 3, "followers": 1})
        if not return_headers:
            return data
        left = remaining.pop(0) if remaining else None
        return data, (None if left is None else {"X-RateLimit-Remaining": str(left)})

    client.get_paginated.side_effect = get_paginated
    client.get_with_cache.side_effect = get_with_cache
    return client


REPOS = [
    {"_metadata": {"extracted_at": "2024-01-01"}},
    None,
    {"name": "invalid"},  # sem full_name
    {"full_name": "test-org/repo1", "name": "repo1"},
    {"full_name": "test-org/repo2", "name": "repo2"},
]


@pytest.fixture(autouse=True)
def no_repositories():
    """Por padrão não há repositórios extraídos (nada de ./data real)."""
    with patch('coops.bronze.members.load_json_data', return_value=None) as mock_load:
        yield mock_load


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
        out = capsys.readouterr().out
        assert "Organization members API returned 2 members" in out
        assert "Found 2 members (2 organization members, 0 other contributors)" in out

    def test_members_list_is_paginated(self, saved):
        """A lista de membros não pode parar na primeira página (30 itens)."""
        client = make_client(members=[{"login": "user1"}])
        extract_members(client, config("my-organization"), use_cache=False)

        url = client.get_paginated.call_args_list[0].args[0]
        assert url == "https://api.github.com/orgs/my-organization/members"
        assert client.get_paginated.call_args_list[0].kwargs == {"use_cache": False, "per_page": 100}

    def test_detailed_file_has_profiles(self, saved):
        profile = {"login": "user1", "id": 1, "created_at": "2015-05-05T00:00:00Z",
                   "public_repos": 42, "followers": 7, "following": 2}
        client = make_client(members=[{"login": "user1", "type": "User"}], profiles={"user1": profile})
        extract_members(client, config())

        detailed = saved["data/bronze/members_detailed.json"]
        assert detailed == [{"login": "user1", "id": 1, "type": "User", "created_at": "2015-05-05T00:00:00Z",
                             "public_repos": 42, "followers": 7, "following": 2, "profile_fetched": True,
                             "is_org_member": True, "contributions_total": 0, "data_source": "members_api"}]
        client.get_with_cache.assert_called_once_with(
            "https://api.github.com/users/user1", True, return_headers=True)

    def test_personal_profile_fields_are_not_stored(self, saved):
        """The data is committed to a public branch: keep only what Silver uses."""
        profile = {"login": "user1", "created_at": "2015-05-05T00:00:00Z", "public_repos": 1, "followers": 1,
                   "email": "user1@example.com", "location": "Somewhere", "bio": "Hi", "company": "ACME",
                   "hireable": True, "blog": "https://example.com", "twitter_username": "u1"}
        client = make_client(members=[{"login": "user1"}], profiles={"user1": profile})
        extract_members(client, config())

        record = saved["data/bronze/members_detailed.json"][0]
        for field in ("email", "location", "bio", "company", "hireable", "blog", "twitter_username"):
            assert field not in record

    def test_profile_request_respects_cache_flag(self, saved):
        client = make_client(members=[{"login": "user1"}])
        extract_members(client, config(), use_cache=False)
        client.get_with_cache.assert_called_once_with(
            "https://api.github.com/users/user1", False, return_headers=True)

    def test_members_without_profile_are_kept_and_flagged(self, saved, capsys):
        client = make_client(members=[{"login": "ghost"}, {"login": "user2"}, {"type": "User"}],
                             profiles={"ghost": None})
        extract_members(client, config())

        detailed = saved["data/bronze/members_detailed.json"]
        assert [(m["login"], m["profile_fetched"]) for m in detailed] == [("ghost", False), ("user2", True)]
        out = capsys.readouterr().out
        assert "Could not fetch profile for ghost" in out
        assert "Fetched 1 of 2 member profiles" in out

    def test_stops_fetching_profiles_when_rate_limit_is_low(self, saved, capsys):
        members = [{"login": f"user{i}"} for i in range(4)]
        client = make_client(members=members, remaining=[500, 199])
        extract_members(client, config())

        assert client.get_with_cache.call_count == 2
        detailed = saved["data/bronze/members_detailed.json"]
        assert [m["profile_fetched"] for m in detailed] == [True, True, False, False]
        out = capsys.readouterr().out
        assert "Only 199 API requests left" in out
        assert "Fetched 2 of 4 member profiles" in out

    def test_cached_profiles_without_headers_do_not_stop_fetching(self, saved):
        members = [{"login": f"user{i}"} for i in range(3)]
        client = make_client(members=members, remaining=[None, None, None])
        extract_members(client, config())

        assert client.get_with_cache.call_count == 3
        assert all(m["profile_fetched"] for m in saved["data/bronze/members_detailed.json"])

    def test_does_not_write_one_file_per_member(self, saved):
        client = make_client(members=[{"login": "user1"}, {"login": "user2"}])
        extract_members(client, config())
        assert set(saved) == {"data/bronze/members_basic.json", "data/bronze/members_detailed.json"}


class TestContributors:
    """Contributors dos repositórios extraídos entram na lista de membros."""

    @staticmethod
    def contributors(url):
        if "repo1" in url:
            return [{"login": "low", "contributions": 5}, {"login": "top", "contributions": 30}]
        return [{"login": "top", "contributions": 30}]

    def test_contributors_are_accumulated_and_sorted(self, saved, capsys, no_repositories):
        no_repositories.return_value = REPOS
        client = make_client(members=[], contributors=self.contributors)
        extract_members(client, config())

        basic = saved["data/bronze/members_basic.json"]
        assert [(m["login"], m["contributions_total"], m["is_org_member"]) for m in basic] == [
            ("top", 60, False), ("low", 5, False)]
        assert basic[0]["data_source"] == "contributors_api"
        contrib_urls = [c.args[0] for c in client.get_paginated.call_args_list[1:]]
        assert contrib_urls == ["https://api.github.com/repos/test-org/repo1/contributors",
                                "https://api.github.com/repos/test-org/repo2/contributors"]
        # detailed profiles keep the contribution counts
        detailed = saved["data/bronze/members_detailed.json"]
        assert [(m["login"], m["contributions_total"]) for m in detailed] == [("top", 60), ("low", 5)]

        out = capsys.readouterr().out
        assert "Organization members API returned 0 members" in out
        assert "Contributors: found 2 across the extracted repositories" in out
        assert "Top contributor: top (60 contributions)" in out
        assert "Found 2 members (0 organization members, 2 other contributors)" in out

    def test_org_members_and_contributors_are_merged(self, saved, capsys, no_repositories):
        """Membros que não contribuíram também entram; quem é as duas coisas aparece uma vez."""
        no_repositories.return_value = REPOS
        client = make_client(members=[{"login": "alice", "id": 1}, {"login": "top", "id": 2}],
                             contributors=self.contributors)
        extract_members(client, config())

        basic = saved["data/bronze/members_basic.json"]
        assert [(m["login"], m["is_org_member"], m["contributions_total"], m["data_source"]) for m in basic] == [
            ("top", True, 60, "members_api+contributors_api"),
            ("low", False, 5, "contributors_api"),
            ("alice", True, 0, "members_api"),
        ]
        assert basic[0]["id"] == 2
        assert "Found 3 members (2 organization members, 1 other contributors)" in capsys.readouterr().out

    @pytest.mark.parametrize("members", [[], None])
    def test_no_repositories_and_no_org_members_writes_empty_files(self, saved, capsys, members):
        client = make_client(members=members)
        result = extract_members(client, config())

        assert result == ["data/bronze/members_basic.json", "data/bronze/members_detailed.json"]
        assert saved == {"data/bronze/members_basic.json": [], "data/bronze/members_detailed.json": []}
        out = capsys.readouterr().out
        assert "Contributors: no repository data available" in out
        assert "Created empty member files" in out

    def test_org_members_without_repositories(self, saved, capsys):
        client = make_client(members=[{"login": "alice"}])
        extract_members(client, config())

        assert [m["login"] for m in saved["data/bronze/members_basic.json"]] == ["alice"]

    def test_no_contributors_writes_empty_files(self, saved, capsys, no_repositories):
        no_repositories.return_value = REPOS
        client = make_client(members=[], contributors=[])
        extract_members(client, config())

        assert saved == {"data/bronze/members_basic.json": [], "data/bronze/members_detailed.json": []}
        assert "Contributors: none found" in capsys.readouterr().out
