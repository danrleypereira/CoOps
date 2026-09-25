"""
Repository extraction for Bronze layer.
Extracts raw repository data from GitHub API.
"""

import math

from coops.utils.github_api import GitHubAPIClient, OrganizationConfig, save_json_data


def extract_repositories(
    client: GitHubAPIClient,
    config: OrganizationConfig,
    use_cache: bool = True,
    max_repos: int | None = None,
    repo_filter: list[str] | None = None,
) -> list[str]:
    """Extract organization repositories to bronze layer.

    max_repos caps the number of filtered repositories kept, and also bounds
    how many pages of the raw repository list are fetched (useful for quick
    local tests). Since blacklist/fork filtering happens after the raw fetch,
    the result may include fewer than max_repos repos if early entries get
    filtered out.

    repo_filter restricts the run to exactly the named ``owner/name``
    repositories. It is applied after the blacklist/fork filter, so naming an
    excluded repository cannot resurrect it, and a name that is not in the
    filtered set raises instead of running on an empty set and reporting
    success. The restricted list is what downstream steps read
    (issues/commits/structures enumerate ``repositories_filtered.json``), so
    the whole run follows. Comparison is case-insensitive because GitHub
    repository names are.
    """

    repos_url = f"https://api.github.com/orgs/{config.org_name}/repos"
    max_pages = math.ceil(max_repos / 100) if max_repos is not None else None
    raw_repos = client.get_paginated(repos_url, use_cache=use_cache, per_page=100, max_pages=max_pages)

    if not raw_repos:
        print("ERROR: Failed to fetch repositories")
        return []

    # Filter out blacklisted repos and forks
    filtered_repos = []
    for repo in raw_repos:
        if not config.should_skip_repo(repo):
            filtered_repos.append(repo)
        else:
            print(f"Skipping repository: {repo.get('name', 'unknown')} (blacklisted/fork)")

    # Restrict to the named repositories, before anything is written: a name
    # absent from the filtered set (unknown, blacklisted or a fork) fails the
    # run here rather than extracting nothing and looking successful.
    if repo_filter:
        wanted = {name.lower() for name in repo_filter}
        available = {repo.get('full_name', '').lower() for repo in filtered_repos}
        missing = sorted(wanted - available)
        if missing:
            raise ValueError(
                "--repo: not in the filtered repository set "
                f"(unknown, blacklisted or fork): {', '.join(missing)}"
            )
        filtered_repos = [
            repo for repo in filtered_repos
            if repo.get('full_name', '').lower() in wanted
        ]

    if max_repos is not None:
        filtered_repos = filtered_repos[:max_repos]

    print(f"Found {len(filtered_repos)} repositories (filtered from {len(raw_repos)})")

    # Listing provenance (#216): `complete: true` is a POSITIVE assertion
    # that this run enumerated the organisation unbounded — no max_repos
    # cap (which also bounds the fetch itself, so after a capped run
    # neither the raw nor the filtered file holds the full list), no
    # repo_filter restriction, and not an offline replay (which reads only
    # what the cache holds, so completeness would be a claim about the
    # provider the run has no evidence for — the same rule that keeps an
    # offline run from persisting watermarks). Every narrowing path simply
    # does not set it, and the Bronze reconciliation refuses to delete
    # anything unless the file itself says the listing was complete: the
    # guard travels with the data, not with the argv of whatever process
    # reads it next.
    listing_complete = (
        max_repos is None
        and repo_filter is None
        and not getattr(client, "offline", False)
    )

    generated_files = []

    repos_file = save_json_data(
        raw_repos,
        "data/bronze/repositories_raw.json"
    )
    generated_files.append(repos_file)

    # Filter repositories and save
    filtered_file = save_json_data(
        filtered_repos,
        "data/bronze/repositories_filtered.json",
        complete=listing_complete,
    )
    generated_files.append(filtered_file)

    # Save individual repositories
    repo_details = []
    for repo in filtered_repos:
        repo_detail_url = f"https://api.github.com/repos/{repo['full_name']}"
        detail = client.get_with_cache(repo_detail_url, use_cache)
        if detail:
            repo_details.append(detail)

            # Save individual repo detail
            repo_file = save_json_data(
                detail,
                f"data/bronze/repo_{repo['name']}.json"
            )
            generated_files.append(repo_file)

    if repo_details:
        details_file = save_json_data(
            repo_details,
            "data/bronze/repositories_detailed.json"
        )
        generated_files.append(details_file)

    return generated_files
