#!/usr/bin/env python3
"""
Organization members extraction for Bronze layer.
Extracts raw member data from GitHub API with contributor fallback.
"""

from typing import Any, Dict, List
from coops.utils.github_api import GitHubAPIClient, OrganizationConfig, save_json_data, load_json_data
from coops.utils.data_helpers import strip_metadata


def _discover_contributors(client: GitHubAPIClient, use_cache: bool) -> List[Dict[str, Any]]:
    """Fallback when the members API returns nothing: contributors of the extracted repositories."""
    repos_data = load_json_data("data/bronze/repositories_filtered.json")
    if not repos_data or not isinstance(repos_data, list):
        print(" Fallback impossible: No repository data available")
        return []

    contributor_details: Dict[str, Dict[str, Any]] = {}
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

    if not contributor_details:
        print(" Fallback failed: No contributors found in repositories")
        return []

    contributors = sorted(contributor_details.values(), key=lambda c: c.get('contributions_total', 0), reverse=True)
    print(f" Fallback successful: Found {len(contributors)} active contributors")
    print(f"Top contributor: {contributors[0]['login']} ({contributors[0]['contributions_total']} contributions)")
    return contributors


def _fetch_member_details(
    client: GitHubAPIClient, members: List[Dict[str, Any]], use_cache: bool
) -> List[Dict[str, Any]]:
    """Fetch each member's user profile (created_at, public_repos, followers, ...).

    Silver's member analytics needs these fields; the basic member list doesn't
    have them. Fields only present in the basic record (e.g. contributions_total
    from the contributor fallback) are kept.
    """
    detailed = []
    for member in members:
        login = member.get('login')
        if not login:
            continue
        detail = client.get_with_cache(f"https://api.github.com/users/{login}", use_cache)
        if isinstance(detail, dict) and detail.get('login'):
            detailed.append({**member, **detail})
        else:
            print(f" Could not fetch profile for {login}; skipping")
    print(f" Fetched {len(detailed)} of {len(members)} member profiles")
    return detailed


def extract_members(client: GitHubAPIClient, config: OrganizationConfig, use_cache: bool = True) -> List[str]:
    """Extract organization members to bronze layer with contributor fallback."""

    members_url = f"https://api.github.com/orgs/{config.org_name}/members"
    raw_members = client.get_paginated(members_url, use_cache=use_cache, per_page=100)

    if not raw_members:
        print(" Organization members API returned empty. This could be due to:")
        print("   - Private member visibility settings")
        print("   - Insufficient token permissions")
        print("   - Organization configuration")
        print("Activating fallback: discovering active contributors...")
        raw_members = _discover_contributors(client, use_cache)
    else:
        print(f" Successfully fetched {len(raw_members)} organization members via members API")

    print(f" Found {len(raw_members)} organization members")

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
