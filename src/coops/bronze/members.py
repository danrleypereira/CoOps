"""
Organization members extraction for Bronze layer.

"Members" are the union of the organization's members (as visible to the
token) and everyone who contributed to the extracted repositories.
"""

from typing import Any

from coops.utils.data_helpers import strip_metadata
from coops.utils.github_api import (
    GitHubAPIClient,
    OrganizationConfig,
    load_json_data,
    save_json_data,
)


def _discover_contributors(client: GitHubAPIClient, use_cache: bool) -> list[dict[str, Any]]:
    """Contributors of the extracted repositories, with their total contributions."""
    repos_data = load_json_data("data/bronze/repositories_filtered.json")
    if not repos_data or not isinstance(repos_data, list):
        print(" Contributors: no repository data available")
        return []

    contributor_details: dict[str, dict[str, Any]] = {}
    for repo in strip_metadata(repos_data):
        if not (repo and isinstance(repo, dict) and repo.get('full_name')):
            continue
        contrib_url = f"https://api.github.com/repos/{repo['full_name']}/contributors"
        repo_contributors = client.get_paginated(contrib_url, use_cache=use_cache, per_page=100)
        for contrib in repo_contributors or []:
            if not (contrib and isinstance(contrib, dict) and contrib.get('login')):
                continue
            login = contrib['login']
            if login not in contributor_details:
                contributor_details[login] = {
                    'login': login,
                    'type': contrib.get('type', 'User'),
                    'contributions_total': contrib.get('contributions', 0),
                    'avatar_url': contrib.get('avatar_url'),
                    'html_url': contrib.get('html_url'),
                    'data_source': 'contributors_api',
                    'discovered_from_repo': repo.get('name'),
                }
            else:
                # Accumulate contributions from multiple repos
                contributor_details[login]['contributions_total'] += contrib.get('contributions', 0)

    contributors = sorted(contributor_details.values(), key=lambda c: c.get('contributions_total', 0), reverse=True)
    if contributors:
        print(f" Contributors: found {len(contributors)} across the extracted repositories")
        print(f"Top contributor: {contributors[0]['login']} ({contributors[0]['contributions_total']} contributions)")
    else:
        print(" Contributors: none found in the extracted repositories")
    return contributors


def _merge_members(
    org_members: list[dict[str, Any]], contributors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Union of organization members and contributors, one record per login.

    `is_org_member` tells whether the login was returned by the organization
    members API; `contributions_total` is 0 for members who didn't contribute.
    Sorted by contributions (descending), then login.
    """
    merged: dict[str, dict[str, Any]] = {}
    for member in org_members:
        if not (isinstance(member, dict) and member.get('login')):
            continue
        merged[member['login']] = {
            **member,
            'is_org_member': True,
            'contributions_total': 0,
            'data_source': 'members_api',
        }
    for contributor in contributors:
        login = contributor['login']
        if login in merged:
            merged[login].update(
                contributions_total=contributor.get('contributions_total', 0),
                data_source='members_api+contributors_api',
                discovered_from_repo=contributor.get('discovered_from_repo'),
            )
        else:
            merged[login] = {**contributor, 'is_org_member': False}
    return sorted(merged.values(), key=lambda m: (-m.get('contributions_total', 0), m['login'].lower()))


# Profile fields kept from /users/{login}: what Silver's member analytics
# uses. Personal fields (email, location, bio, company, ...) are not stored,
# since the data is committed to a public branch.
PROFILE_FIELDS = (
    'login', 'id', 'name', 'type', 'avatar_url', 'html_url',
    'created_at', 'updated_at', 'public_repos', 'followers', 'following',
)

# Stop requesting profiles when fewer REST requests than this remain in the
# current rate-limit window, so the rest of the pipeline can still run.
RATE_LIMIT_RESERVE = 200


def _remaining_requests(headers: Any) -> int | None:
    try:
        return int(headers.get('X-RateLimit-Remaining'))
    except (AttributeError, TypeError, ValueError):
        return None


def _fetch_member_details(
    client: GitHubAPIClient, members: list[dict[str, Any]], use_cache: bool
) -> list[dict[str, Any]]:
    """Add each member's profile (created_at, public_repos, followers, ...).

    Silver's member analytics needs these fields; the basic member list doesn't
    have them. Every member is kept: `profile_fetched` tells whether the
    profile could be fetched. Fields only present in the basic record (e.g.
    contributions_total from the contributor fallback) are kept.
    """
    detailed = []
    fetched = 0
    stopped_for_rate_limit = False
    for member in members:
        login = member.get('login')
        if not login:
            continue
        record = {**member, 'profile_fetched': False}
        if not stopped_for_rate_limit:
            result = client.get_with_cache(
                f"https://api.github.com/users/{login}", use_cache, return_headers=True
            )
            profile, headers = result if isinstance(result, tuple) else (result, None)
            if isinstance(profile, dict) and profile.get('login'):
                record = {
                    **member,
                    **{k: profile[k] for k in PROFILE_FIELDS if k in profile},
                    'profile_fetched': True,
                }
                fetched += 1
            else:
                print(f" Could not fetch profile for {login}")
            remaining = _remaining_requests(headers)
            if remaining is not None and remaining < RATE_LIMIT_RESERVE:
                stopped_for_rate_limit = True
                print(f"[WARN] Only {remaining} API requests left; skipping the remaining member profiles")
        detailed.append(record)
    print(f" Fetched {fetched} of {len(detailed)} member profiles")
    return detailed


def extract_members(client: GitHubAPIClient, config: OrganizationConfig, use_cache: bool = True) -> list[str]:
    """Extract organization members and repository contributors to the bronze layer."""

    members_url = f"https://api.github.com/orgs/{config.org_name}/members"
    org_members = client.get_paginated(members_url, use_cache=use_cache, per_page=100) or []
    print(f" Organization members API returned {len(org_members)} members")
    if not org_members:
        print("   (the default Actions token only sees public memberships; see COOPS_GITHUB_TOKEN)")

    contributors = _discover_contributors(client, use_cache)
    raw_members = _merge_members(org_members, contributors)
    org_count = sum(1 for m in raw_members if m['is_org_member'])
    print(f" Found {len(raw_members)} members ({org_count} organization members, "
          f"{len(raw_members) - org_count} other contributors)")

    if not raw_members:
        print("  No members data available, but continuing with empty dataset")
        generated_files = [
            save_json_data([], "data/bronze/members_basic.json"),
            save_json_data([], "data/bronze/members_detailed.json"),
        ]
        print(" Created empty member files to maintain data structure")
        return generated_files

    members_file = save_json_data(raw_members, "data/bronze/members_basic.json")
    detailed_members = _fetch_member_details(client, raw_members, use_cache)
    detailed_file = save_json_data(detailed_members, "data/bronze/members_detailed.json")
    return [members_file, detailed_file]
