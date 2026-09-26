"""The Commit record's committer, disclosed as a value gap rather than a pass.

The #30 differential's stub GraphQL nodes carry no ``committer`` — its own
docstring says so, and names the reason: the ``Commit`` model has none, so a
node that had one would make the legacy arm write values the service cannot
reproduce. The commits arms of that comparison were therefore green by
construction, the same shaping #241's twin
(``tests/unit/test_repository_projection_gap.py``) names for repositories.

Measured against the real corpus (all 130,186 records in the 486 per-repository
``commits_<name>.json`` files of the fga snapshot, both paths fed the same
node). The retired ``commits_all.json`` aggregate is **excluded**: it repeats
every per-repository record, so counting it doubles every figure exactly — the
same reason ``bronze_files`` reads per-repository files and not the ``_all``
aggregates (#170):

* **key sets are identical at every level** — root 8 keys, ``commit`` 3,
  ``commit.committer`` 2, ``commit.author`` 3-4 in the same conditional
  shapes. The repositories defect (99 keys legacy vs 17 ported, #241) has
  no commit twin: the legacy GraphQL path writes an 8-key intermediate, and
  the projection matches it.
* the defect is **one value**: ``commit.committer.name`` is a real string on
  130,108 of 130,186 legacy records (99.9%) and always ``None`` through the
  port. The other 78 are the deliberate ``_is_address`` blanks
  (``_sanitize_commit``), which survive untouched.

No seam carries the payload here: ``SourcePort`` yields domain models by
contract ("never a provider payload"), so the GraphQL node — which *does*
carry ``committer { name email date … }`` because the live query requests it
(``queries.COMMIT_HISTORY_DEFAULT_BRANCH_QUERY``) — is consumed inside the
adapter, where the mapper drops the name the model cannot hold. Widening
``Commit`` is the fix the Bronze-is-conformed ruling rejects (the model
exists for the domain, not to envelope GitHub's schema); the fix is a
payload-carrying seam, which is a port-contract change, not a projection
change. Until it lands, the xfail below is the honest state of #240.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from coops.bronze.bronze_service import _commit_record
from coops.bronze.commits import _sanitize_commit
from coops.domain.tenancy import resolve_tenant
from coops.github.mapper import map_commit_graphql

TENANT = resolve_tenant("single", "test-org")

#: One REAL Bronze commit record, verbatim, from the fga snapshot (protected
#: corpus, read-only): ``data/bronze/commits_2016.1-AbasteceAqui.json``, the
#: record for sha ``8e89a1e6…``. It is the legacy GraphQL-path shape the
#: whole corpus shares, and its committer is a real person who is not the
#: author — the exact field #240 names, exercised so no author-name
#: substitution can pass vacuously.
REAL_COMMIT_RECORD: dict[str, Any] = {
    "sha": "8e89a1e6b65c6f751e42144c2f63b673bc66c35c",
    "html_url": None,
    "commit": {
        "author": {
            "name": "Ygor Galeno",
            "date": "2016-06-24T02:38:01Z",
            "login": "ygortgaleno",
            "id": 12112239,
        },
        "committer": {"name": "Victor Fernandes", "date": "2016-06-24T02:38:01Z"},
        "message": "repairing some errors, and refactoring layout",
    },
    "parents": ["4b69dc7f3669052c2e9c57b60e4eaa0cd18947ab"],
    "additions": 135,
    "deletions": 57,
    "total_changes": 192,
    "repo_name": "2016.1-AbasteceAqui",
}

#: The corpus record is post-scrub, so the author's raw email is gone; the
#: live node carries one, and *both* paths below hash whatever arrives into
#: ``author_email_hash`` with the same SHA-256 twin helpers — the value is
#: synthetic here, the channel is not.
NODE_AUTHOR_EMAIL = "ygortgaleno@example.org"


def _graphql_node(record: dict[str, Any]) -> dict[str, Any]:
    """The node the live query returns for this record.

    The inverse of the legacy REST-like assembly (``commits.py``): the corpus
    record *is* that assembly's output after ``_sanitize_commit``, so name,
    dates, message, parents and stats are real; only the emails, scrubbed
    from the corpus, are synthetic. No ``url`` — the live query does not
    request it, which is why every corpus ``html_url`` is ``null``.
    """
    author = record["commit"]["author"]
    committer = record["commit"]["committer"]
    return {
        "oid": record["sha"],
        "message": record["commit"]["message"],
        "committedDate": committer["date"],
        "author": {
            "name": author["name"],
            "email": NODE_AUTHOR_EMAIL,
            "date": author["date"],
            "user": {"login": author.get("login"), "databaseId": author.get("id")},
        },
        "committer": {
            "name": committer["name"],
            "email": "committer@example.org",
            "date": committer["date"],
        },
        "parents": {"nodes": [{"oid": parent} for parent in record["parents"]]},
        "additions": record["additions"],
        "deletions": record["deletions"],
    }


def _legacy_stored_record(node: dict[str, Any], repo_name: str) -> dict[str, Any]:
    """The legacy writer: the REST-like assembly, then ``_sanitize_commit``.

    A verbatim transcription of the GraphQL branch of the legacy
    ``extract_commits`` (``commits.py``) plus the scrub it applies on save —
    test-local only because the legacy step builds it inline in a 300-line
    function. The fixture anchors it: if the transcription mangles the
    committer, the asserts against ``REAL_COMMIT_RECORD`` fail.
    """
    author = node["author"]
    user = author.get("user") or {}
    committer = node["committer"] or {}
    committed = node.get("committedDate")
    additions = node.get("additions")
    deletions = node.get("deletions")
    total = (
        (additions or 0) + (deletions or 0)
        if additions is not None and deletions is not None
        else None
    )
    record = {
        "sha": node.get("oid"),
        "html_url": node.get("url"),
        "commit": {
            "author": {
                "name": author.get("name"),
                "email": author.get("email"),
                "date": author.get("date") or committed,
                "login": user.get("login"),
                "id": user.get("databaseId"),
            },
            "committer": {
                "name": committer.get("name"),
                "email": committer.get("email"),
                "date": committer.get("date") or committed,
            },
            "message": node.get("message"),
        },
        "parents": [
            p.get("oid")
            for p in (node.get("parents") or {}).get("nodes") or []
            if isinstance(p, dict) and p.get("oid")
        ],
        "additions": additions,
        "deletions": deletions,
        "total_changes": total,
        "repo_name": repo_name,
    }
    return _sanitize_commit(record)


def _ported_stored_record(node: dict[str, Any], repo_name: str) -> dict[str, Any]:
    """The ported writer: the live adapter path, ``map_commit_graphql`` and
    the service's own projection."""
    commit = map_commit_graphql(node, TENANT.id, TENANT.accounts[0], repo_name)
    return _commit_record(commit)


def _key_paths(obj: Any, prefix: str = "") -> dict[str, tuple[str, ...]]:
    """Every dict level of the record, as ``level -> sorted key tuple``."""
    paths: dict[str, tuple[str, ...]] = {}
    if isinstance(obj, dict):
        paths[prefix or "/"] = tuple(sorted(obj.keys()))
        for key, value in obj.items():
            paths.update(_key_paths(value, f"{prefix}.{key}" if prefix else key))
    return paths


def test_the_fixture_exercises_the_committer_field():
    """The control that stops the xfail below from being vacuous.

    A fixture whose committer name were absent, blank, or equal to the
    author's name would let a fabricated fix (copy the author's name across)
    pass. This one cannot: the committer is a different, real person.
    """
    committer = REAL_COMMIT_RECORD["commit"]["committer"]["name"]
    author = REAL_COMMIT_RECORD["commit"]["author"]["name"]
    assert isinstance(committer, str) and committer.strip()
    assert committer != author


def test_ported_record_key_set_matches_legacy_at_every_level():
    """Key sets are identical at every level — the measured corpus finding.

    The repositories defect (#241: 99 legacy keys vs 17 ported) has no commit
    twin: both paths write the same 8/3/2-key shape. Fails if either path's
    key set drifts.
    """
    node = _graphql_node(REAL_COMMIT_RECORD)
    repo = REAL_COMMIT_RECORD["repo_name"]
    assert _key_paths(_ported_stored_record(node, repo)) == _key_paths(
        _legacy_stored_record(node, repo)
    )


def test_ported_record_equals_legacy_except_the_committer_name():
    """Whole-artifact equality modulo exactly one value: the #240 defect.

    Everything the model carries survives the port — this is the arms-differ
    proof that the two paths produce the same record except the one field,
    so the xfail below is about that field and nothing else.
    """
    node = _graphql_node(REAL_COMMIT_RECORD)
    repo = REAL_COMMIT_RECORD["repo_name"]
    legacy = _legacy_stored_record(node, repo)
    expected = copy.deepcopy(legacy)
    expected["commit"]["committer"]["name"] = None
    assert _ported_stored_record(node, repo) == expected


@pytest.mark.xfail(
    reason="#240: the port yields models, never payloads, so the committer's "
    "name the live query carries dies at the mapper and the projection "
    "writes None where the legacy path writes the real name",
    strict=True,
)
def test_ported_record_carries_the_real_committer_name():
    """The ported record must carry the real ``commit.committer.name``.

    Fails today (writes ``None``); flips to an unexpected pass — and pytest
    reports it, which is the point — the day a payload-carrying seam lands.
    """
    node = _graphql_node(REAL_COMMIT_RECORD)
    repo = REAL_COMMIT_RECORD["repo_name"]
    real_name = REAL_COMMIT_RECORD["commit"]["committer"]["name"]
    legacy = _legacy_stored_record(node, repo)
    # The legacy arm keeps the real name (and the _is_address blanking rule
    # leaves it alone: it is a name, not an address).
    assert legacy["commit"]["committer"]["name"] == real_name
    assert _ported_stored_record(node, repo)["commit"]["committer"]["name"] == real_name
