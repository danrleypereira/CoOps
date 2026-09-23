"""Guard tests for the domain models (issue #21).

These test the *models* directly, the way ``test_tenancy.py`` tests the
Phase 0 value objects: every ``__post_init__`` guard gets a test that can
fail, and the identity precedence is tested on **combinations** — per
``docs/definition-of-done.md`` ("Precedence needs two things present at
once"), a chain like ``login -> hash -> name`` is only observable when two
channels are present together, so every pair is exercised, not each channel
in isolation.

All names, logins and hashes below are invented: this file is committed to
a public repository, so it carries no real contributor identifier.
"""

from dataclasses import FrozenInstanceError

import pytest

from coops.domain import (
    ENTRY_KINDS,
    ActivityEvent,
    Actor,
    Commit,
    FileEntry,
    FileTree,
    Issue,
    Member,
    PullRequest,
    Repository,
    TenantId,
    identity_key,
)

TENANT = TenantId("test-org")

# Deliberately synthetic hashes: 64 hex chars like the real SHA-256 email
# pseudonyms, but derived from nothing.
HASH_ONE = "11" * 32
HASH_TWO = "22" * 32


# --- identity precedence (login -> email_hash -> name) ---------------------


def test_login_beats_hash_when_both_present():
    actor = Actor.resolve(login="rosa-almeida", email_hash=HASH_ONE)
    assert actor.identity == "rosa-almeida"


def test_login_beats_name_when_both_present():
    actor = Actor.resolve(login="rosa-almeida", name="Rosa Almeida")
    assert actor.identity == "rosa-almeida"


def test_hash_beats_name_when_both_present():
    """The pair where precedence is observable: name AND hash, no login.

    Deliberately constructed combination (docs/definition-of-done.md,
    "Precedence needs two things present at once"): generated-in-isolation
    fixtures can never see the ordering. The hash must win — 16 name
    strings in the real corpus are each shared by several distinct people,
    so a name key would merge them — while the name survives as the label.
    """
    actor = Actor.resolve(name="Rosa Almeida", email_hash=HASH_ONE)
    assert actor.identity == HASH_ONE
    assert actor.display_name == "Rosa Almeida"


def test_login_beats_hash_and_name_when_all_three_present():
    actor = Actor.resolve(
        login="rosa-almeida", email_hash=HASH_ONE, name="Rosa Almeida"
    )
    assert actor.identity == "rosa-almeida"
    assert actor.display_name == "Rosa Almeida"


def test_name_only_identity_is_the_name():
    actor = Actor.resolve(name="Rosa Almeida")
    assert actor.identity == "Rosa Almeida"


def test_hash_only_identity_is_the_hash():
    actor = Actor.resolve(email_hash=HASH_ONE)
    assert actor.identity == HASH_ONE


# --- display-name policy ----------------------------------------------------


def test_address_shaped_name_becomes_none_display_name():
    """#132: a name that is literally an address is blanked, never kept.

    Real corpus shape (149 such names); the address value here is synthetic
    and reserved (example.com), as every address in these fixtures is.
    """
    actor = Actor.resolve(name="rosa.almeida@example.com", email_hash=HASH_ONE)
    assert actor.display_name is None
    # The address is not an identity either; the hash is.
    assert actor.identity == HASH_ONE


def test_display_name_none_is_a_normal_state():
    actor = Actor.resolve(login="rosa-almeida")
    assert actor.display_name is None


def test_blank_inputs_are_treated_as_absent_channels():
    actor = Actor.resolve(login="", name="", email_hash=HASH_ONE)
    assert actor.login is None
    assert actor.email_hash == HASH_ONE
    assert actor.display_name is None
    assert actor.identity == HASH_ONE


def test_resolve_with_no_channel_raises():
    with pytest.raises(ValueError):
        Actor.resolve()


def test_identity_key_returns_none_when_no_channel():
    assert identity_key(None, None, None) is None


# --- Actor construction guards ----------------------------------------------


@pytest.mark.parametrize("identity", [None, "", "   "])
def test_actor_blank_identity_raises(identity):
    """The None param is the case only this guard catches: a blank identity
    with no components to disagree with — the mismatch guard alone would
    let ``identity=None`` through (``None == None``)."""
    with pytest.raises(ValueError):
        Actor(identity=identity, display_name=None)


def test_actor_blank_display_name_raises():
    with pytest.raises(ValueError):
        Actor(identity="rosa-almeida", display_name="   ", login="rosa-almeida")


def test_actor_identity_must_match_resolved_key():
    """The stored identity cannot disagree with the components (#151).

    Direct construction with an identity that is not what the precedence
    resolves to must raise, so no code path can hand-build an inconsistent
    Actor even where it bypasses ``resolve``.
    """
    with pytest.raises(ValueError, match="resolved key"):
        Actor(identity=HASH_ONE, display_name=None, login="rosa-almeida")


def test_actor_identity_mismatch_does_not_echo_the_values():
    """#177: the mismatch guard diagnoses without quoting what it rejected.

    ``display_name`` can be an email address (149 corpus names are) and a
    traceback in a public CI log is a publish surface, so the message
    names the rule, never the values. Asserts on the whole message: a
    truncated check is how a leaked value hides in the unseen tail. The
    address is synthetic and reserved (example.com), like every address
    in this file.
    """
    with pytest.raises(ValueError) as excinfo:
        Actor(identity="wrong-key", display_name="rosa.almeida@example.com")
    message = str(excinfo.value)
    assert "rosa.almeida@example.com" not in message
    assert "wrong-key" not in message


def test_actor_identity_mismatch_message_names_the_rule_and_the_winner():
    """Still diagnosable without the values: the whole message names the
    precedence rule, which channel wins it for the channels present, and
    that the supplied key matched none of them.
    """
    with pytest.raises(ValueError) as excinfo:
        Actor(
            identity="wrong-key",
            display_name="rosa.almeida@example.com",
            login="rosa-almeida",
        )
    message = str(excinfo.value)
    assert "login -> email_hash -> name" in message
    assert "login: yes, email_hash: no, display_name: yes" in message
    assert "the resolved key is the login channel" in message
    assert "matches none of the channels" in message
    assert "rosa-almeida" not in message
    assert "rosa.almeida@example.com" not in message


def test_actor_identity_mismatch_names_the_supplied_channel():
    """When the supplied key *is* one of the channels, the message says
    which one — naming the channel, never its contents (the whole point
    of #177: this display_name is an address).
    """
    with pytest.raises(ValueError) as excinfo:
        Actor(
            identity="rosa.almeida@example.com",
            display_name="rosa.almeida@example.com",
            login="rosa-almeida",
        )
    message = str(excinfo.value)
    assert "matches the display_name channel" in message
    assert "the resolved key is the login channel" in message
    assert "rosa.almeida@example.com" not in message
    assert "rosa-almeida" not in message


def test_actor_is_immutable():
    actor = Actor.resolve(login="rosa-almeida")
    with pytest.raises(FrozenInstanceError):
        actor.identity = "other"


def test_actors_same_display_name_different_identity_stay_distinct():
    """Two people, one legible label: never merged (#151/#158).

    The real corpus has 16 name strings each shared by several distinct
    people ("CI/CD Bot" is six of them); values here are synthetic.
    """
    first = Actor.resolve(name="CI Bot", email_hash=HASH_ONE)
    second = Actor.resolve(name="CI Bot", email_hash=HASH_TWO)
    assert first.display_name == second.display_name
    assert first.identity != second.identity
    assert first != second
    # Keying by identity keeps both: the exact merge the old name key caused.
    assert len({first, second}) == 2


# --- Member -----------------------------------------------------------------


@pytest.mark.parametrize("identity", [None, "", "   "])
def test_member_blank_identity_raises(identity):
    """As on Actor: the None param (with no components to disagree with) is
    the shape only this guard rejects."""
    with pytest.raises(ValueError):
        Member(tenant=TENANT, identity=identity, display_name=None)


def test_member_blank_display_name_raises():
    with pytest.raises(ValueError):
        Member(
            tenant=TENANT,
            identity="rosa-almeida",
            display_name=" ",
            login="rosa-almeida",
        )


def test_member_identity_must_match_resolved_key():
    with pytest.raises(ValueError, match="resolved key"):
        Member(
            tenant=TENANT,
            identity=HASH_ONE,
            display_name=None,
            login="rosa-almeida",
        )


def test_member_identity_mismatch_does_not_echo_the_values():
    """#177, the Member twin of the Actor guard: same rule, same
    value-free message — the address, the login and the supplied key are
    all absent from the whole message, which still names the rule and the
    winning channel.
    """
    with pytest.raises(ValueError) as excinfo:
        Member(
            tenant=TENANT,
            identity="wrong-key",
            display_name="rosa.almeida@example.com",
            login="rosa-almeida",
        )
    message = str(excinfo.value)
    assert "rosa.almeida@example.com" not in message
    assert "rosa-almeida" not in message
    assert "wrong-key" not in message
    assert "login -> email_hash -> name" in message
    assert "the resolved key is the login channel" in message


def test_member_negative_contributions_raises():
    with pytest.raises(ValueError, match="contributions_total"):
        Member(
            tenant=TENANT,
            identity="rosa-almeida",
            display_name="Rosa Almeida",
            login="rosa-almeida",
            contributions_total=-1,
        )


def test_member_display_name_none_is_a_normal_state():
    member = Member(
        tenant=TENANT, identity="rosa-almeida", display_name=None, login="rosa-almeida"
    )
    assert member.display_name is None
    assert member.is_org_member is False
    assert member.contributions_total == 0


def test_members_same_display_name_different_identity_stay_distinct():
    """Required combination: same name, different hashes -> two Members.

    Deliberately synthetic (the hashes belong to no real address): the real
    corpus produces this shape ("CI/CD Bot" is six people, "root" five),
    and a model or consumer that merged on display_name would collapse them.
    """
    first = Member(
        tenant=TENANT, identity=HASH_ONE, display_name="CI Bot", email_hash=HASH_ONE
    )
    second = Member(
        tenant=TENANT, identity=HASH_TWO, display_name="CI Bot", email_hash=HASH_TWO
    )
    assert first != second
    by_identity = {first.identity: first, second.identity: second}
    assert len(by_identity) == 2
    assert {m.display_name for m in by_identity.values()} == {"CI Bot"}


def test_member_is_immutable():
    member = Member(
        tenant=TENANT, identity="rosa-almeida", display_name=None, login="rosa-almeida"
    )
    with pytest.raises(FrozenInstanceError):
        member.contributions_total = 5


# --- Repository ---------------------------------------------------------------


def test_repository_zero_id_raises():
    with pytest.raises(ValueError, match="repo_id"):
        Repository(tenant=TENANT, repo_id=0, name="coops", full_name="test-org/coops")


def test_repository_blank_name_raises():
    with pytest.raises(ValueError, match="name"):
        Repository(tenant=TENANT, repo_id=1, name=" ", full_name="test-org/coops")


def test_repository_blank_full_name_raises():
    with pytest.raises(ValueError, match="full_name"):
        Repository(tenant=TENANT, repo_id=1, name="coops", full_name="")


# --- Commit -------------------------------------------------------------------


def _author() -> Actor:
    return Actor.resolve(login="rosa-almeida")


def test_commit_blank_repo_name_raises():
    with pytest.raises(ValueError, match="repo_name"):
        Commit(
            tenant=TENANT,
            repo_name=" ",
            sha="a" * 40,
            author=_author(),
            committed_at="2026-03-04T10:00:00Z",
            message="",
        )


def test_commit_blank_sha_raises():
    with pytest.raises(ValueError, match="sha"):
        Commit(
            tenant=TENANT,
            repo_name="coops",
            sha="",
            author=_author(),
            committed_at="2026-03-04T10:00:00Z",
            message="",
        )


def test_commit_blank_committed_at_raises():
    with pytest.raises(ValueError, match="committed_at"):
        Commit(
            tenant=TENANT,
            repo_name="coops",
            sha="a" * 40,
            author=_author(),
            committed_at=" ",
            message="",
        )


def test_commit_author_may_be_absent():
    """#154 measured 2,076 commits whose author has no identifier at all —
    no login, no account, no name, no email (a deleted account, or author
    metadata that never resolved).

    The model carries that as ``author=None``: an absent author, not an
    ``Actor`` with a blank field — a shared empty identity would merge
    distinct people, the #151 defect. The field stays required (no
    default): every commit has an author *slot*, present or absent.
    """
    commit = Commit(
        tenant=TENANT,
        repo_name="coops",
        sha="a" * 40,
        author=None,
        committed_at="2026-03-04T10:00:00Z",
        message="x",
    )
    assert commit.author is None


# --- Issue / PullRequest --------------------------------------------------------


def _issue_kwargs(**over):
    kwargs = {
        "tenant": TENANT,
        "repo_name": "coops",
        "number": 42,
        "state": "open",
        "title": "Fix the thing",
    }
    kwargs.update(over)
    return kwargs


def test_issue_blank_repo_name_raises():
    with pytest.raises(ValueError, match="repo_name"):
        Issue(**_issue_kwargs(repo_name=" "))


def test_issue_zero_number_raises():
    with pytest.raises(ValueError, match="number"):
        Issue(**_issue_kwargs(number=0))


def test_issue_blank_state_raises():
    with pytest.raises(ValueError, match="state"):
        Issue(**_issue_kwargs(state=" "))


def test_pull_request_blank_repo_name_raises():
    with pytest.raises(ValueError, match="repo_name"):
        PullRequest(**_issue_kwargs(repo_name=" "))


def test_pull_request_zero_number_raises():
    with pytest.raises(ValueError, match="number"):
        PullRequest(**_issue_kwargs(number=0))


def test_pull_request_blank_state_raises():
    with pytest.raises(ValueError, match="state"):
        PullRequest(**_issue_kwargs(state=" "))


# --- ActivityEvent --------------------------------------------------------------


def _event_kwargs(**over):
    kwargs = {
        "tenant": TENANT,
        "repo_name": "coops",
        "event_id": 91,
        "event_type": "closed",
        "created_at": "2026-03-05T10:00:00Z",
    }
    kwargs.update(over)
    return kwargs


def test_activity_event_zero_event_id_raises():
    with pytest.raises(ValueError, match="event_id"):
        ActivityEvent(**_event_kwargs(event_id=0))


def test_activity_event_blank_event_type_raises():
    with pytest.raises(ValueError, match="event_type"):
        ActivityEvent(**_event_kwargs(event_type=" "))


def test_activity_event_blank_repo_name_raises():
    with pytest.raises(ValueError, match="repo_name"):
        ActivityEvent(**_event_kwargs(repo_name=" "))


def test_activity_event_blank_created_at_raises():
    with pytest.raises(ValueError, match="created_at"):
        ActivityEvent(**_event_kwargs(created_at=" "))


def test_activity_event_actor_none_is_an_absent_actor():
    """957 event actors in the corpus are literally null: absent, not "unknown"."""
    event = ActivityEvent(**_event_kwargs(actor=None))
    assert event.actor is None


# --- FileTree ---------------------------------------------------------------------


def test_file_entry_blank_path_raises():
    with pytest.raises(ValueError, match="path"):
        FileEntry(path=" ", kind="blob")


def test_file_entry_unknown_kind_raises():
    with pytest.raises(ValueError, match="kind"):
        FileEntry(path="README.md", kind="symlink")


def test_file_entry_accepts_every_documented_kind():
    for kind in sorted(ENTRY_KINDS):
        assert FileEntry(path="README.md", kind=kind).kind == kind


def test_file_tree_blank_repo_name_raises():
    with pytest.raises(ValueError, match="repo_name"):
        FileTree(tenant=TENANT, repo_name=" ")
