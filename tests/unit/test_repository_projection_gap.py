"""The Repository projection, disclosed as a shaping rather than a pass.

``REPO_RECORDS`` in the differential harness is hand-written with exactly
the seventeen keys :class:`coops.domain.models.Repository` carries, so the
``repo_*.json`` arms of that comparison *cannot* disagree — the fixture is
shaped by the thing under test. Two of the twelve "byte-identical" families
are therefore green by construction.

Real Bronze repository payloads carry 99 or 100 keys (measured over all 486
``repo_*.json`` in the fga corpus: **476 carry 99 and 10 carry 100**, the ten
adding ``template_repository``). One key is our own ``_metadata`` envelope, so
the model drops **82 real GitHub fields**.

The list below is the GitHub schema — field *names* only, no organisation
data — taken from a real payload.

This test is expected to fail while #241 is open. When #241 lands and
``Repository`` can carry the payload, it flips to an unexpected pass and
pytest reports it, which is the point: a docstring cannot regress.
"""

import pytest

from coops.domain.models import Repository

GITHUB_REPO_FIELDS_NOT_ON_THE_MODEL = (
    'allow_auto_merge',
    'allow_forking',
    'allow_merge_commit',
    'allow_rebase_merge',
    'allow_squash_merge',
    'allow_update_branch',
    'archive_url',
    'assignees_url',
    'blobs_url',
    'branches_url',
    'clone_url',
    'collaborators_url',
    'comments_url',
    'commits_url',
    'compare_url',
    'contents_url',
    'contributors_url',
    'custom_properties',
    'delete_branch_on_merge',
    'deployments_url',
    'disabled',
    'downloads_url',
    'events_url',
    'forks',
    'forks_url',
    'git_commits_url',
    'git_refs_url',
    'git_tags_url',
    'git_url',
    'has_discussions',
    'has_downloads',
    'has_issues',
    'has_pages',
    'has_projects',
    'has_pull_requests',
    'has_wiki',
    'homepage',
    'hooks_url',
    'is_template',
    'issue_comment_url',
    'issue_events_url',
    'issues_url',
    'keys_url',
    'labels_url',
    'languages_url',
    'license',
    'merge_commit_message',
    'merge_commit_title',
    'merges_url',
    'milestones_url',
    'mirror_url',
    'network_count',
    'node_id',
    'notifications_url',
    'open_issues',
    'organization',
    'owner',
    'permissions',
    'pull_request_creation_policy',
    'pulls_url',
    'releases_url',
    'security_and_analysis',
    'squash_merge_commit_message',
    'squash_merge_commit_title',
    'ssh_url',
    'stargazers_url',
    'statuses_url',
    'subscribers_count',
    'subscribers_url',
    'subscription_url',
    'svn_url',
    'tags_url',
    'teams_url',
    'temp_clone_token',
    'topics',
    'trees_url',
    'url',
    'use_squash_pr_title_as_default',
    'visibility',
    'watchers',
    'watchers_count',
    'web_commit_signoff_required',
)


#: The seventeen the model does carry.
MODEL_FIELDS = (
    "id", "name", "full_name", "private", "fork", "archived", "description",
    "default_branch", "language", "html_url", "size", "stargazers_count",
    "forks_count", "open_issues_count", "created_at", "updated_at", "pushed_at",
)


def _realistic_payload() -> dict:
    """A repository payload the shape of a real one: 99 GitHub fields."""
    payload = {f: f"value-for-{f}" for f in MODEL_FIELDS}
    payload["id"] = 957040204
    payload["name"] = "2025-1-NoFluxoUnB"
    payload["full_name"] = "unb-mds/2025-1-NoFluxoUnB"
    for f in GITHUB_REPO_FIELDS_NOT_ON_THE_MODEL:
        payload.setdefault(f, f"value-for-{f}")
    return payload


def test_the_harness_fixture_is_not_a_realistic_payload():
    """Names the shaping the differential's docstring omits (#241).

    This one PASSES: it asserts the gap exists, so it is the control that
    stops the xfail below from being vacuous.
    """
    assert len(MODEL_FIELDS) == 17
    assert len(GITHUB_REPO_FIELDS_NOT_ON_THE_MODEL) == 82
    assert len(_realistic_payload()) == 99


@pytest.mark.xfail(
    reason="#241: Repository is a 17-field projection of a 99-field payload; "
           "the differential's repo_ arms are green only because REPO_RECORDS "
           "is hand-written with the model's own keys",
    strict=True,
)
def test_repository_round_trips_a_realistic_payload():
    """A real payload through the model and back must lose nothing.

    Fed the harness's own 17-key fixture this would pass and prove nothing;
    fed a realistic payload it fails, which is what makes the two green
    ``repo_*.json`` arms of the differential a fixture artifact rather than
    agreement.
    """
    payload = _realistic_payload()
    repo = Repository(
        external_id=str(payload["id"]),
        name=payload["name"],
        full_name=payload["full_name"],
    )
    round_tripped = getattr(repo, "raw", {}) or {}
    missing = sorted(set(payload) - set(round_tripped))
    assert not missing, f"the model dropped {len(missing)} fields: {missing[:5]}…"
