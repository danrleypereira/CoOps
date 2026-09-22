import copy
import hashlib
import os
import re
from typing import Any, Dict, List, Optional

# Free text headed for a public branch: commit messages carry `Co-authored-by:`
# and `Signed-off-by:` trailers with real addresses, which a key-name sweep
# cannot see. Matched loosely on purpose — over-scrubbing a message is harmless,
# leaking an address is not.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
from coops.utils.github_api import GitHubAPIClient, OrganizationConfig, save_json_data, load_json_data
from coops.utils.data_helpers import strip_metadata
from coops.bronze.watermarks import WatermarkStore, max_iso


def _hash_email(email: str) -> str:
    """SHA-256 of a trimmed, lower-cased email address.

    Pseudonymization, not anonymization: a known address can still be confirmed
    by hashing it, but casual scraping/search exposure is removed from the
    public branch.
    """
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _remove_email_keys(obj: Any) -> None:
    """Recursively delete every 'email' key from a (possibly nested) structure."""
    if isinstance(obj, dict):
        for key in list(obj.keys()):
            if key == "email":
                del obj[key]
            else:
                _remove_email_keys(obj[key])
    elif isinstance(obj, list):
        for item in obj:
            _remove_email_keys(item)


def _sanitize_commit(commit: Dict[str, Any]) -> Dict[str, Any]:
    """Drop raw author/committer emails, keeping a stable identity key.

    Commit data is committed to a public branch, so raw email addresses must not
    be persisted. Linked authors (with a GitHub account) keep ``login`` and the
    numeric ``id``; unlinked authors keep ``author_email_hash`` (the SHA-256 of
    the trimmed, lower-cased email) instead of the raw address.
    """
    commit = copy.deepcopy(commit)

    top_author = commit.get("author")
    commit_author = (commit.get("commit") or {}).get("author")

    login = None
    numeric_id = None
    email = None

    if isinstance(top_author, dict):
        login = top_author.get("login")
        numeric_id = top_author.get("id")
    if isinstance(commit_author, dict):
        login = login or commit_author.get("login")
        if numeric_id is None:
            numeric_id = commit_author.get("id")
        email = commit_author.get("email")

    # Remove every 'email' key (author/committer, top-level and nested).
    _remove_email_keys(commit)

    commit_obj = commit.get("commit")
    if isinstance(commit_obj, dict):
        # The REST paths persist the raw API response, whose `verification`
        # object carries the signed payload — and that payload embeds the raw
        # address as `author Name <a@example.com>`, which `_remove_email_keys`
        # cannot see because it is free text, not an `email` key. Nothing
        # downstream reads verification, so drop it.
        commit_obj.pop("verification", None)

        # Same class of leak in the other free-text field: the REST paths keep
        # the full message, whose `Co-authored-by:` / `Signed-off-by:` trailers
        # carry addresses. The attributed name is left intact, so credit
        # survives — only the address goes.
        message = commit_obj.get("message")
        if isinstance(message, str):
            commit_obj["message"] = _EMAIL_RE.sub("[email removed]", message)

        raw_author = commit_obj.get("author")
        author_data = dict(raw_author) if isinstance(raw_author, dict) else {}
        author_data.pop("login", None)
        author_data.pop("id", None)

        if login:
            author_data["login"] = login
        if numeric_id is not None:
            author_data["id"] = numeric_id
        if not login and numeric_id is None:
            # Unlinked author: the email is the only identifier. Store a stable
            # hash instead of the raw address so distinct people aren't merged
            # into "unknown" downstream.
            if email:
                author_data["author_email_hash"] = _hash_email(email)

        commit_obj["author"] = author_data

    return commit


def extract_commits(
    client: GitHubAPIClient,
    config: OrganizationConfig,
    use_cache: bool = True,
    method: str = "rest",
    since: Optional[str] = None,
    until: Optional[str] = None,
    max_commits_per_repo: Optional[int] = None,
    page_size: int = 50,
    include_active_branches: bool = False,
    active_days: int = 30,
    time_chunks: int = 3,
    watermarks: Optional[WatermarkStore] = None,
) -> List[str]:

    # Load filtered repositories
    filtered_repos = load_json_data("data/bronze/repositories_filtered.json")
    if not filtered_repos:
        print("No repositories found. Run repository extraction first.")
        return []

    generated_files = []
    all_commits: List[Dict[str, Any]] = []

    # Skip metadata if present
    if isinstance(filtered_repos, list) and len(filtered_repos) > 0 and isinstance(filtered_repos[0], dict) and '_metadata' in filtered_repos[0]:
        filtered_repos = filtered_repos[1:]

    # Extract commits from each repository
    for repo in filtered_repos:
        if not repo or not isinstance(repo, dict):
            print(f"Skipping invalid repo entry: {repo}")
            continue

        repo_name = repo.get('name', 'unknown')
        full_name = repo.get('full_name', repo_name)
        owner = full_name.split('/')[0] if '/' in full_name else None
        name_only = full_name.split('/')[1] if '/' in full_name else full_name

        # Incremental extraction (issue #110): a watermark with a `last_run`
        # bounds the commit fetch to what was committed after the previous run.
        # `effective_since` is the later of the caller's `since` and the
        # watermark's `last_run`, so an explicit historical `--since` is never
        # widened, only narrowed to what is still unknown.
        wm = watermarks.get(full_name) if watermarks is not None else None
        incremental = bool(wm and wm.last_run)
        effective_since = max_iso(since, wm.last_run if wm else None)

        print(f"Processing commits for: {repo_name}")

        # Determine which branches to extract
        branches_to_extract = None
        if include_active_branches and method.lower() == "graphql":
            print(f"  Finding active unmerged branches (last {active_days} days)...")
            branches_to_extract = client.get_active_unmerged_branches(
                owner=owner,
                repo=name_only,
                days=active_days,
                use_cache=use_cache,
            )
            if branches_to_extract:
                print(f"  Found {len(branches_to_extract)} unmerged branches to extract")
            else:
                print(f"  No active unmerged branches found")

        # Choose extraction method
        data_commits: List[Dict[str, Any]] = []
        if method.lower() == "graphql":
            if not owner:
                print(f"[WARN] Skipping {full_name}: cannot determine owner/name for GraphQL")
                continue
            nodes, meta = client.graphql_commit_history(
                owner=owner,
                repo=name_only,
                branches=branches_to_extract,
                split_large_extractions=bool(since or until),  # chunk only explicit user ranges
                time_chunks=3,  # Split into 3 time periods
                page_size=page_size,
                max_commits=max_commits_per_repo,
                since=effective_since,
                until=until,
                use_cache=use_cache,
            )

            for n in nodes:
                # Map GraphQL fields to a REST-like structure to preserve downstream compatibility
                sha = n.get('oid')
                author = n.get('author') or {}
                user = author.get('user') if isinstance(author.get('user'), dict) else {}
                committer = n.get('committer') or {}
                committed_date = n.get('committedDate')
                # The full message (headline + body); older nodes — e.g. the
                # REST-fallback shape — may only carry the headline.
                message = n.get('message') or n.get('messageHeadline')
                additions = n.get('additions')
                deletions = n.get('deletions')
                total_changes = (additions or 0) + (deletions or 0) if (additions is not None and deletions is not None) else None
                parent_nodes = (n.get('parents') or {}).get('nodes') or []
                parents = [p.get('oid') for p in parent_nodes if isinstance(p, dict) and p.get('oid')]

                # `email` is carried only so `_sanitize_commit` can derive a stable
                # identity key for unlinked authors; it is never persisted.
                data_commits.append({
                    'sha': sha,
                    'html_url': n.get('url'),
                    'commit': {
                        'author': {
                            'name': author.get('name'),
                            'email': author.get('email'),
                            'date': author.get('date') or committed_date,
                            'login': user.get('login'),
                            'id': user.get('databaseId'),
                        },
                        'committer': {
                            'name': committer.get('name'),
                            'email': committer.get('email'),
                            'date': committer.get('date') or committed_date,
                        },
                        'message': message,
                    },
                    'parents': parents,
                    'additions': additions,
                    'deletions': deletions,
                    'total_changes': total_changes,
                    'repo_name': repo_name,
                })

            if not nodes:
                print(f"[WARN] GraphQL returned no commits for {repo_name}. Falling back to REST.")
                # Fallback to REST list + details to avoid data gaps
                commits_base = f"https://api.github.com/repos/{full_name}/commits"
                if effective_since or until:
                    sep = '&' if ('?' in commits_base) else '?'
                    if effective_since:
                        commits_base = f"{commits_base}{sep}since={effective_since}"
                        sep = '&'
                    if until:
                        commits_base = f"{commits_base}{sep}until={until}"
                commits = client.get_paginated(commits_base, use_cache=use_cache, per_page=100)
                for commit in commits or []:
                    sha = commit.get('sha')
                    additions = None
                    deletions = None
                    total_changes = None
                    if sha:
                        details_url = f"https://api.github.com/repos/{full_name}/commits/{sha}"
                        details = client.get_with_cache(details_url, use_cache)
                        if details and isinstance(details, dict):
                            stats = details.get('stats') or {}
                            additions = stats.get('additions')
                            deletions = stats.get('deletions')
                            total_changes = stats.get('total')

                    # Ensure commit.commit.author.login is populated from commit.author.login if available
                    commit_data = {**commit}
                    if 'commit' in commit_data and 'author' in commit_data['commit']:
                        # If commit.author.login exists at root level, copy it to commit.commit.author.login
                        if 'author' in commit_data and isinstance(commit_data['author'], dict) and 'login' in commit_data['author']:
                            commit_data['commit']['author']['login'] = commit_data['author']['login']

                    # The REST response nests parents as `[{sha, ...}]`; store
                    # just the shas so this path agrees with the GraphQL one.
                    data_commits.append({
                        **commit_data,
                        'parents': [
                            p.get('sha')
                            for p in (commit_data.get('parents') or [])
                            if isinstance(p, dict) and p.get('sha')
                        ],
                        'repo_name': repo_name,
                        'additions': additions,
                        'deletions': deletions,
                        'total_changes': total_changes,
                    })
                print(f"Found {len(data_commits)} commits in {repo_name} via REST fallback")
            else:
                print(f"Found {len(nodes)} commits in {repo_name} via GraphQL")
        else:
            # REST fallback (existing behavior): list commits, then fetch details per commit to get stats
            commits_base = f"https://api.github.com/repos/{full_name}/commits"
            # Apply since/until filters when available to reduce pages
            if effective_since or until:
                sep = '&' if ('?' in commits_base) else '?'
                if effective_since:
                    commits_base = f"{commits_base}{sep}since={effective_since}"
                    sep = '&'
                if until:
                    commits_base = f"{commits_base}{sep}until={until}"
            commits = client.get_paginated(commits_base, use_cache=use_cache, per_page=page_size)
            if commits:
                for commit in commits:
                    sha = commit.get('sha')
                    additions = None
                    deletions = None
                    total_changes = None
                    if sha:
                        details_url = f"https://api.github.com/repos/{full_name}/commits/{sha}"
                        details = client.get_with_cache(details_url, use_cache)
                        if details and isinstance(details, dict):
                            stats = details.get('stats') or {}
                            additions = stats.get('additions')
                            deletions = stats.get('deletions')
                            total_changes = stats.get('total')

                    # Ensure commit.commit.author.login is populated from commit.author.login if available
                    commit_data = {**commit}
                    if 'commit' in commit_data and 'author' in commit_data['commit']:
                        # If commit.author.login exists at root level, copy it to commit.commit.author.login
                        if 'author' in commit_data and isinstance(commit_data['author'], dict) and 'login' in commit_data['author']:
                            commit_data['commit']['author']['login'] = commit_data['author']['login']

                    # Merge original commit with stats and repo context. Parents
                    # are reduced to their shas to match the GraphQL record shape.
                    data_commits.append({
                        **commit_data,
                        'parents': [
                            p.get('sha')
                            for p in (commit_data.get('parents') or [])
                            if isinstance(p, dict) and p.get('sha')
                        ],
                        'repo_name': repo_name,
                        'additions': additions,
                        'deletions': deletions,
                        'total_changes': total_changes,
                    })

                print(f"Found {len(commits)} commits in {repo_name} via REST")

        if data_commits or incremental:
            # Drop raw author/committer emails before persisting to the public
            # branch; keep a stable identity key (login + id, or email hash).
            new_sanitized = [_sanitize_commit(c) for c in data_commits]

            if incremental:
                # Commits are immutable, so merging is a prepend: anything newly
                # fetched is newer than everything already stored (the previous
                # run's file is newest-first). Dedup by sha guards against the
                # `since` window over-fetching the tail of the previous run. The
                # stored file was already capped by the previous run, so no cap
                # is re-applied here — that would truncate it below what a full
                # extraction of the same window keeps.
                prior = strip_metadata(
                    load_json_data(f"data/bronze/commits_{repo_name}.json") or []
                )
                seen = set()
                merged = []
                for commit in new_sanitized + prior:
                    sha = commit.get('sha')
                    if sha and sha not in seen:
                        seen.add(sha)
                        merged.append(commit)
                data_commits = merged
            else:
                data_commits = new_sanitized

            if data_commits:
                # Add to global list
                all_commits.extend(data_commits)

                # Save per-repo commits
                repo_commits_file = save_json_data(
                    data_commits,
                    f"data/bronze/commits_{repo_name}.json"
                )
                generated_files.append(repo_commits_file)

        # Advance this repository's watermark (its `last_run` in particular), so
        # the next run's `since` starts where this one left off.
        if watermarks is not None:
            watermarks.update(full_name)

    # Save all commits (always save, even if empty, to ensure files exist)
    all_commits_file = save_json_data(
        all_commits,
        "data/bronze/commits_all.json"
    )
    generated_files.append(all_commits_file)

    print(f"Total commits extracted: {len(all_commits)}")

    return generated_files
