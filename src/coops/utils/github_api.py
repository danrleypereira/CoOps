"""
Shared utilities for GitHub API interactions and data processing.

Includes REST and GraphQL support, caching, parallel commit fetching,
repository tree extraction, and organization configuration.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

# Unused here since #27 moved the transport to coops.github.client, but the
# name must keep resolving: tests stub the HTTP boundary through this
# module's attribute (patch("coops.utils.github_api.requests.get") and
# monkeypatch.setattr(github_api.requests, "post", ...)).
import requests  # noqa: F401

from coops.github.client import (
    GitHubTransport,
)
from coops.github.client import (
    OfflineCacheMiss as OfflineCacheMiss,  # noqa: PLC0414 - explicit re-export
)


class GitHubAPIClient(GitHubTransport):
    """GitHub queries over the extracted transport (#27).

    The transport half of this class — HTTP/GraphQL, the URL-keyed cache
    and its ETag sidecars, retry/backoff, rate-limit accounting, the raw
    layer, the capture and the offline replay — moved verbatim to
    :class:`coops.github.client.GitHubTransport`. What remains are the
    GitHub *queries* (issue #28 moves those behind the transport) and, at
    module level, the JSON/config helpers this module has always exported.
    """

    def _split_time_range(
        self,
        since: str | None,
        until: str | None,
        chunks: int = 3,
    ) -> list[tuple[str | None, str | None]]:
        """
        Split a time range into smaller chunks for efficient extraction.

        Args:
            since: Start date (ISO format) or None
            until: End date (ISO format) or None
            chunks: Number of chunks to split into (default: 3)

        Returns:
            List of (since, until) tuples representing time ranges
        """
        from datetime import datetime, timedelta, timezone

        # If no date range specified, return single range
        if not since and not until:
            return [(None, None)]

        # Parse dates
        try:
            if since:
                start_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            else:
                # Default to 1 year ago if not specified
                start_dt = datetime.now(timezone.utc) - timedelta(days=365)

            if until:
                end_dt = datetime.fromisoformat(until.replace('Z', '+00:00'))
            else:
                end_dt = datetime.now(timezone.utc)
        except (ValueError, AttributeError):
            # If parsing fails, return None range to indicate invalid dates
            return [(None, None)]

        # Calculate chunk duration
        total_duration = end_dt - start_dt
        chunk_duration = total_duration / chunks

        # Generate time ranges
        ranges = []
        for i in range(chunks):
            chunk_start = start_dt + (chunk_duration * i)
            chunk_end = start_dt + (chunk_duration * (i + 1))

            # Format as ISO strings
            ranges.append((
                chunk_start.isoformat().replace('+00:00', 'Z'),
                chunk_end.isoformat().replace('+00:00', 'Z')
            ))

        return ranges

    def get_active_unmerged_branches(
        self,
        owner: str,
        repo: str,
        days: int = 30,
        use_cache: bool = True,
    ) -> list[str]:
        """
        Get branches that were updated recently and have unmerged commits.
        Uses a single efficient query combining branch listing and comparison.

        Args:
            days: Consider branches updated in last N days

        Returns:
            List of branch names with unmerged commits
        """
        from datetime import datetime, timedelta, timezone

        # Get default branch first
        repo_info = self.get_with_cache(
            f"https://api.github.com/repos/{owner}/{repo}",
            use_cache=use_cache
        )
        default_branch = repo_info.get("default_branch", "main") if repo_info else "main"

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_date.isoformat()

        # Single GraphQL query to get branches with commit info
        query = """
        query($owner: String!, $name: String!, $cursor: String) {
          repository(owner: $owner, name: $name) {
            refs(refPrefix: "refs/heads/", first: 100, after: $cursor, orderBy: {field: TAG_COMMIT_DATE, direction: DESC}) {
              pageInfo { hasNextPage endCursor }
              nodes {
                name
                target {
                  ... on Commit {
                    oid
                    committedDate
                  }
                }
              }
            }
          }
          rateLimit { remaining resetAt limit cost }
        }
        """

        active_branches = []
        cursor = None

        while True:
            variables = {"owner": owner, "name": repo, "cursor": cursor}
            data = self.graphql(query, variables, use_cache=use_cache)
            if not data:
                break

            repo_data = data.get("data", {}).get("repository")
            if not repo_data:
                break

            refs = repo_data.get("refs", {})
            nodes = refs.get("nodes", [])

            # Filter by date and exclude default branch
            for node in nodes:
                branch_name = node.get("name")
                if branch_name == default_branch:
                    continue

                # Skip gh-pages and similar branches
                if branch_name and branch_name.startswith("gh-pages"):
                    continue

                target = node.get("target", {})
                commit_date = target.get("committedDate")

                if commit_date:
                    commit_dt = datetime.fromisoformat(commit_date.replace('Z', '+00:00'))
                    if commit_dt >= cutoff_date:
                        active_branches.append(branch_name)

            page_info = refs.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        if not active_branches:
            return []

        # Batch check which branches have unmerged commits (max 10 at a time to avoid rate limits)
        print(f"  Found {len(active_branches)} active branches (gh-pages excluded), checking merge status...")
        unmerged_branches = []
        batch_size = 10

        for i in range(0, len(active_branches), batch_size):
            batch = active_branches[i:i+batch_size]
            for branch in batch:
                # Use REST API compare endpoint (more efficient than GraphQL for this)
                compare_url = f"https://api.github.com/repos/{owner}/{repo}/compare/{default_branch}...{branch}"
                compare_data = self.get_with_cache(compare_url, use_cache=use_cache)

                if compare_data and isinstance(compare_data, dict):
                    ahead_by = compare_data.get("ahead_by", 0)
                    if ahead_by > 0:
                        unmerged_branches.append(branch)
                        print(f"    {branch}: {ahead_by} commits ahead")

            # Small delay between batches to respect rate limits
            if i + batch_size < len(active_branches):
                time.sleep(1)

        return unmerged_branches

    def _fetch_with_thread_id(self, owner: str, repo: str, sha: str, use_cache: bool) -> dict[str, Any]:
        """Helper function to fetch commit details with thread identification."""
        thread_id = threading.get_ident() % 1000  # Use last 3 digits for readability
        data, headers = self.get_with_cache(
            f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}",
            use_cache,
            return_headers=True,
            silent=True  # Don't log individual requests
        )
        return {'data': data, 'thread_id': thread_id, 'headers': headers}

    def _fetch_rest_commit_details_parallel(self, commits_list: list[dict], owner: str, repo: str, use_cache: bool, max_workers: int = 5) -> list[dict[str, Any]]:
        """
        Fetch commit details in parallel with conservative settings.

        Args:
            commits_list: List of commit objects with 'sha' field
            owner: Repository owner
            repo: Repository name
            use_cache: Whether to use cache
            max_workers: Maximum parallel requests (default: 5)

        Returns:
            List of processed commits with stats
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        processed_commits = []
        batch_size = 10  # Process in small batches
        thread_id_map = {}  # Map real thread IDs to sequential worker numbers

        # Create executor once and reuse across all batches
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for batch_idx in range(0, len(commits_list), batch_size):
                batch = commits_list[batch_idx:batch_idx+batch_size]
                batch_headers = []  # Collect headers from this batch

                # Submit all requests in this batch with worker tracking
                future_to_data = {}
                for c in batch:
                    future = executor.submit(
                        self._fetch_with_thread_id,
                        owner,
                        repo,
                        c['sha'],
                        use_cache
                    )
                    future_to_data[future] = c

                # Collect results as they complete
                for future in as_completed(future_to_data):
                    rest_commit = future_to_data[future]
                    sha = rest_commit.get('sha')

                    try:
                        result = future.result(timeout=40)
                        commit_details = result['data']
                        thread_id = result['thread_id']
                        headers = result['headers']

                        # Collect headers for batch summary
                        if headers:
                            batch_headers.append(headers)

                        # Map thread ID to sequential worker number (1, 2, 3, ...)
                        if thread_id not in thread_id_map:
                            thread_id_map[thread_id] = len(thread_id_map) + 1
                        worker_num = thread_id_map[thread_id]

                        if commit_details:
                            stats = commit_details.get('stats', {})
                            additions = stats.get('additions', 0)
                            deletions = stats.get('deletions', 0)

                            commit_payload = rest_commit.get('commit', {}) or {}
                            raw_author = commit_payload.get('author') or {}
                            raw_committer = commit_payload.get('committer') or {}

                            # The GitHub account, present only when the commit
                            # is linked to one: an unlinked commit has
                            # `author: null`. The git `name` is not a login —
                            # standing in for one fabricates an account that
                            # never existed, and dropping `email` leaves the
                            # commit unattributable (#203).
                            account = rest_commit.get('author')
                            if not isinstance(account, dict):
                                account = {}

                            print(f"[REST][Worker-{worker_num}] Fetched {sha[:8]}: +{additions}/-{deletions}")

                            processed_commits.append({
                                'oid': sha,
                                'message': commit_payload.get('message', ''),
                                'messageHeadline': commit_payload.get('message', '').split('\n')[0],
                                'committedDate': raw_author.get('date'),
                                # The node shape the GraphQL query returns
                                # (`author { name email user { login
                                # databaseId } }`), so the GraphQL->REST
                                # mapping in bronze/commits.py treats both
                                # paths identically. REST's `author.id` is
                                # GraphQL's `user.databaseId`.
                                'author': {
                                    'name': raw_author.get('name'),
                                    'email': raw_author.get('email'),
                                    'date': raw_author.get('date'),
                                    'user': {
                                        'login': account.get('login'),
                                        'databaseId': account.get('id'),
                                    },
                                },
                                'committer': {
                                    'name': raw_committer.get('name'),
                                    'email': raw_committer.get('email'),
                                    'date': raw_committer.get('date'),
                                },
                                'parents': {
                                    'nodes': [
                                        {'oid': p.get('sha')}
                                        for p in (rest_commit.get('parents') or [])
                                        if isinstance(p, dict) and p.get('sha')
                                    ]
                                },
                                'additions': additions,
                                'deletions': deletions,
                            })
                    except OfflineCacheMiss:
                        # An offline replay miss must stop the run; swallowing
                        # it here would drop the commit and report a partial
                        # answer (#199).
                        raise
                    except Exception as e:  # noqa: BLE001 — per-commit worker: one failed commit is logged and the batch continues
                        print(f"[REST][Worker-?][WARN] Failed {sha[:8] if sha else 'unknown'}: {e}")

                # Show rate limit summary for this batch
                if batch_headers:
                    last_header = batch_headers[-1]  # Use most recent
                    remaining = last_header.get('X-RateLimit-Remaining', 'Unknown')
                    limit = last_header.get('X-RateLimit-Limit', 'Unknown')
                    reset_time = last_header.get('X-RateLimit-Reset', 'Unknown')
                    if reset_time != 'Unknown':
                        reset_datetime = datetime.fromtimestamp(int(reset_time), tz=timezone.utc)
                        print(f"[REST][Batch {batch_idx//batch_size + 1}] Rate limit: {remaining}/{limit}, resets at {reset_datetime}")
                    else:
                        print(f"[REST][Batch {batch_idx//batch_size + 1}] Rate limit: {remaining}/{limit}")

                # Small delay between batches
                if batch_idx + batch_size < len(commits_list):
                    time.sleep(0.3)

        return processed_commits

    def graphql_commit_history(
        self,
        owner: str,
        repo: str,
        page_size: int,
        max_pages: int | None = None,
        max_commits: int | None = None,
        since: str | None = None,
        until: str | None = None,
        use_cache: bool = True,
        branches: list[str] | None = None,
        split_large_extractions: bool = True,
        time_chunks: int = 3,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """
        Fetch commit history with automatic REST fallback on GraphQL failures.

        Features:
        - Switches to REST after 16s timeout (2 failed attempts)
        - REST fallback extracts 50 commits, then retries GraphQL
        - Circuit breaker for repeated failures

        Args:
            branches: List of branch names to extract from. If None, uses default branch.
            split_large_extractions: If True, splits extraction into time chunks
            time_chunks: Number of time periods to split extraction into (default: 3)

        Returns:
            Tuple of (commits list, rate limit metadata)
        """
        commits_by_sha: dict[str, dict[str, Any]] = {}  # Deduplicate by SHA
        rate_meta: dict[str, Any] = {}
        graphql_failures = 0  # Track GraphQL failures
        using_rest_fallback = False
        rest_commit_count = 0
        rest_commits_before_retry = 50  # Try GraphQL again after 50 REST commits

        # Always include default branch, optionally add others
        branches_to_process = [None]  # None = default branch
        if branches:
            branches_to_process.extend(branches)
            print(f"  Processing {len(branches_to_process)} branches (main + {len(branches)} active)")

        # Determine if we should split by time
        time_ranges = [(since, until)]  # Default: single time range

        if split_large_extractions and (since or until):
            time_ranges = self._split_time_range(since, until, chunks=time_chunks)
            print(f"  Splitting extraction into {len(time_ranges)} time periods to avoid API overload")

        for branch in branches_to_process:
            branch_name = branch or "default branch"
            print(f"    Extracting from: {branch_name}")

            # Process each time range for this branch
            for time_idx, (range_since, range_until) in enumerate(time_ranges):
                if len(time_ranges) > 1:
                    print(f"      Time period {time_idx + 1}/{len(time_ranges)}: {range_since} to {range_until}")

                if branch:
                    query = """
                    query($owner: String!, $name: String!, $branch: String!, $pageSize: Int!, $cursor: String, $since: GitTimestamp, $until: GitTimestamp) {
                      repository(owner: $owner, name: $name) {
                        ref(qualifiedName: $branch) {
                          target {
                            ... on Commit {
                              history(first: $pageSize, after: $cursor, since: $since, until: $until) {
                                pageInfo { hasNextPage endCursor }
                                nodes {
                                  oid
                                  message
                                  messageHeadline
                                  committedDate
                                  author { name email user { login databaseId } }
                                  committer { name email date user { login databaseId } }
                                  additions
                                  deletions
                                  parents(first: 100) { nodes { oid } }
                                }
                              }
                            }
                          }
                        }
                      }
                      rateLimit { remaining resetAt limit cost }
                    }
                    """
                else:
                    query = """
                    query($owner: String!, $name: String!, $pageSize: Int!, $cursor: String, $since: GitTimestamp, $until: GitTimestamp) {
                      repository(owner: $owner, name: $name) {
                        defaultBranchRef {
                          name
                          target {
                            ... on Commit {
                              history(first: $pageSize, after: $cursor, since: $since, until: $until) {
                                pageInfo { hasNextPage endCursor }
                                nodes {
                                  oid
                                  message
                                  messageHeadline
                                  committedDate
                                  author { name email user { login databaseId } }
                                  committer { name email date user { login databaseId } }
                                  additions
                                  deletions
                                  parents(first: 100) { nodes { oid } }
                                }
                              }
                            }
                          }
                        }
                      }
                      rateLimit { remaining resetAt limit cost }
                    }
                    """

                cursor: str | None = None
                pages = 0
                period_commits = 0
                rest_page = 1
                last_rest_commit_sha = None

                while True:
                    if max_pages is not None and pages >= max_pages:
                        break
                    if max_commits is not None and len(commits_by_sha) >= max_commits:
                        break

                    # CIRCUIT BREAKER: Switch to REST after 1 GraphQL failure (30s timeout)
                    if graphql_failures >= 1 and not using_rest_fallback:
                        print("[CIRCUIT BREAKER] GraphQL failed (30s timeout)")
                        print("        Switching to REST API fallback...")
                        using_rest_fallback = True
                        rest_commit_count = 0
                        graphql_failures = 0

                    # REST FALLBACK
                    if using_rest_fallback:

                        rest_url = f"https://api.github.com/repos/{owner}/{repo}/commits"
                        params = []
                        if branch:
                            params.append(f"sha={branch}")
                        if range_since:
                            params.append(f"since={range_since}")
                        if range_until:
                            params.append(f"until={range_until}")
                        params.append("per_page=50")
                        params.append(f"page={rest_page}")

                        rest_url = f"{rest_url}?{'&'.join(params)}"

                        rest_data = self.get_with_cache(rest_url, use_cache=use_cache, silent=True)

                        if not rest_data or not isinstance(rest_data, list):
                            print(f"[REST] Page {rest_page}: No more commits available")
                            break

                        # Filter commits that haven't been processed yet
                        new_commits = [
                            c for c in rest_data
                            if c.get('sha') and c.get('sha') not in commits_by_sha
                        ]

                        total_in_page = len(rest_data)
                        already_processed = total_in_page - len(new_commits)

                        if not new_commits:
                            print(f"[REST] Page {rest_page}: Found {total_in_page} commits, all already in dataset (skipping)")
                            rest_page += 1
                            continue

                        print(f"[REST] Page {rest_page}: Found {total_in_page} commits, {already_processed} already in dataset (processing {len(new_commits)} new)")

                        # Fetch commit details in parallel
                        processed = self._fetch_rest_commit_details_parallel(
                            new_commits, owner, repo, use_cache, max_workers=5
                        )

                        # Add to commits dictionary
                        for commit in processed:
                            sha = commit.get('oid')
                            if sha and sha not in commits_by_sha:
                                commits_by_sha[sha] = commit
                                rest_commit_count += 1
                                period_commits += 1
                                last_rest_commit_sha = sha

                        rest_page += 1

                        # Check if we should retry GraphQL
                        if rest_commit_count >= rest_commits_before_retry:
                            if last_rest_commit_sha:
                                print(f"[REST->GRAPHQL] Extracted {rest_commit_count} commits via REST (last: {last_rest_commit_sha[:8]}...)")
                                print("[REST->GRAPHQL] GraphQL will continue from cursor position (deduplication prevents reprocessing)")
                            else:
                                print(f"[REST->GRAPHQL] Extracted {rest_commit_count} commits via REST. Retrying GraphQL...")
                            using_rest_fallback = False
                            rest_commit_count = 0
                            graphql_failures = 0
                            time.sleep(1)
                            continue

                        # If REST returned less than 100 commits, we're done
                        if len(rest_data) < 100:
                            print("[REST] Reached end of commits")
                            break

                        time.sleep(1)  # Rate limit protection for REST
                        continue

                    # GRAPHQL MODE
                    variables = {
                        "owner": owner,
                        "name": repo,
                        "pageSize": page_size,
                        "cursor": cursor,
                        "since": range_since,
                        "until": range_until,
                    }
                    if branch:
                        variables["branch"] = f"refs/heads/{branch}"


                    data = self.graphql(query, variables, use_cache=use_cache, timeout=30)

                    if not data:
                        graphql_failures += 1
                        continue  # Circuit breaker will activate REST fallback after 1 failure

                    repo_data = data.get("data", {}).get("repository")
                    rate_meta = data.get("data", {}).get("rateLimit", {}) or {}

                    # Success! Reset failure counter
                    graphql_failures = 0

                    if not repo_data:
                        break

                    # Extract history based on query type
                    if branch:
                        ref_data = repo_data.get("ref")
                        if not ref_data:
                            print(f"[GRAPHQL] Branch '{branch}' not found")
                            break
                        target = ref_data.get("target", {})
                    else:
                        default_ref = repo_data.get("defaultBranchRef")
                        if not default_ref:
                            break
                        target = default_ref.get("target", {})

                    history = target.get("history") if isinstance(target, dict) else None
                    if not history:
                        break

                    nodes = history.get("nodes", [])

                    # Add commits to dict (auto-deduplicates by SHA)
                    for node in nodes:
                        sha = node.get('oid')
                        if sha and sha not in commits_by_sha:
                            # Set additions/deletions to 0 if unavailable (SERVICE_UNAVAILABLE errors)
                            if node.get('additions') is None:
                                node['additions'] = 0
                            if node.get('deletions') is None:
                                node['deletions'] = 0

                            commits_by_sha[sha] = node
                            period_commits += 1

                    page_info = history.get("pageInfo", {})
                    has_next = page_info.get("hasNextPage")
                    cursor = page_info.get("endCursor")
                    pages += 1

                    # Log rate limit after processing commits
                    if rate_meta:
                        remaining = rate_meta.get("remaining", 0)
                        limit = rate_meta.get("limit", 5000)
                        print(f"[GRAPHQL] Rate limit: {remaining}/{limit}, {len(commits_by_sha)} commits processed")
                        if remaining < 100:
                            print(f"[GRAPHQL][WARN] Rate limit low ({remaining}). Pausing 30s...")
                            time.sleep(30)

                    # Delay between pages
                    if has_next:
                        time.sleep(1)

                    if not has_next:
                        break

                if len(time_ranges) > 1 and period_commits > 0:
                    print(f"[GRAPHQL] Extracted {period_commits} total unique commits from this period")

        # The commit half of the #199 fold is NOT wired here. A GraphQL history
        # body carries no repository name, so attributing one needs evidence
        # from the commit graph — and continuing the graph across shared history
        # folded a successor repository's commits into its predecessor
        # (2021.1-PC-GO1-Frontend: 510 -> 818, all 308 of them its successor's).
        # Attributing another repository's work is worse than the staleness it
        # would have cured. The issue and event folds are unaffected.
        commits = list(commits_by_sha.values())
        if branches:
            print(f"  [GRAPHQL] Total unique commits across all branches: {len(commits)}")
        return commits, rate_meta

    # ============================================================================
    # REPOSITORY STRUCTURE EXTRACTION (REST + GraphQL Fallback)
    # ============================================================================

    def get_repository_tree(
        self,
        owner: str,
        repo: str,
        branch: str = "main",
        use_cache: bool = True
    ) -> dict[str, Any]:
        """
        Get file tree using REST API Git Trees as primary method.
        If the tree is truncated, automatically falls back to GraphQL.

        Args:
            owner: Repository owner
            repo: Repository name
            branch: Branch to analyze (default: "main")
            use_cache: Whether to use cache

        Returns:
            Dictionary with the standardized file tree
        """
        logger = logging.getLogger(__name__)

        try:
            # Step 1: Get branch SHA via REST
            branch_url = f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}"
            branch_data = self.get_with_cache(branch_url, use_cache=use_cache)

            if not branch_data:
                logger.error(f"Branch {branch} not found for {owner}/{repo}")
                return self._empty_tree_response(owner, repo, branch, error="Branch not found")

            tree_sha = branch_data['commit']['sha']
            logger.info(f"Fetching tree for {owner}/{repo} (SHA: {tree_sha[:8]})")

            # Step 2: Get recursive tree with REST (1 request!)
            tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{tree_sha}"
            tree_data = self.get_with_cache(
                f"{tree_url}?recursive=1",
                use_cache=use_cache
            )

            if not tree_data:
                logger.error(f"Failed to fetch tree for {owner}/{repo}")
                return self._empty_tree_response(owner, repo, branch, error="Tree fetch failed")

            is_truncated = tree_data.get('truncated', False)
            raw_tree = tree_data.get('tree', [])

            logger.info(f"  Items fetched: {len(raw_tree)}")
            logger.info(f"  Truncated: {is_truncated}")

            # If truncated, fallback to GraphQL
            if is_truncated:
                logger.warning("  Tree truncated! Falling back to GraphQL...")
                return self.graphql_repository_tree(owner, repo, branch, use_cache)

            # Step 3: Standardize node format
            standardized_tree = []
            for item in raw_tree:
                node = self._standardize_tree_node(item)
                if node:
                    standardized_tree.append(node)

            return {
                'owner': owner,
                'repository': repo,
                'branch': branch,
                'sha': tree_sha,
                'tree': standardized_tree,
                'truncated': is_truncated,
                'extracted_at': datetime.now(timezone.utc).isoformat(),
                'method': 'rest',
                'total_items': len(standardized_tree)
            }

        except OfflineCacheMiss:
            # Must not become an "empty tree" result: an offline replay miss
            # stops the run (#199).
            raise
        except Exception as e:  # noqa: BLE001 — tree contract: any failure returns the documented empty/error tree
            logger.error(f"Error in get_repository_tree: {e!s}")
            return self._empty_tree_response(owner, repo, branch, error=str(e))

    def graphql_repository_tree(
        self,
        owner: str,
        repo: str,
        branch: str = "main",
        use_cache: bool = True,
        max_depth: int = 100
    ) -> dict[str, Any]:
        """
        Extract full tree using GraphQL (used when REST truncates).
        Iterative implementation with stack to avoid deep recursion.

        Args:
            owner: Repository owner
            repo: Repository name
            branch: Branch to analyze
            use_cache: Whether to use cache
            max_depth: Maximum depth for safety

        Returns:
            Dictionary with hierarchical tree
        """
        logger = logging.getLogger(__name__)

        def build_tree_iterative(start_path: str = "") -> list[dict[str, Any]]:
            """Build tree using iterative stack."""
            root_tree = []
            stack = [(start_path, root_tree)]
            processed = set()

            while stack and len(processed) < max_depth:
                current_path, parent_list = stack.pop()

                if current_path in processed:
                    logger.warning(f"Skipping already processed path: {current_path}")
                    continue
                processed.add(current_path)

                expression = f"{branch}:{current_path}" if current_path else f"{branch}:"

                query = """
                query($owner: String!, $repo: String!, $expression: String!) {
                  repository(owner: $owner, name: $repo) {
                    object(expression: $expression) {
                      ... on Tree {
                        entries {
                          name
                          type
                          mode
                          path
                          extension
                          object {
                            ... on Blob {
                              byteSize
                              isBinary
                              oid
                            }
                          }
                        }
                      }
                    }
                  }
                }
                """

                variables = {
                    "owner": owner,
                    "repo": repo,
                    "expression": expression
                }

                try:
                    result = self.graphql(query, variables, use_cache=use_cache)

                    if not result or 'data' not in result:
                        logger.warning(f"No data returned for path: {current_path}")
                        continue

                    repo_obj = result.get('data', {}).get('repository', {})
                    if not repo_obj:
                        logger.warning("Repository not found")
                        continue

                    tree_obj = repo_obj.get('object', {})
                    if not tree_obj:
                        logger.debug(f"No tree object for path: {current_path}")
                        continue

                    entries = tree_obj.get('entries', [])

                    for entry in entries:
                        entry_type = entry.get('type')
                        entry_name = entry.get('name')
                        entry_path = entry.get('path')

                        if entry_type == 'tree':
                            logger.debug(f"Processing directory: {entry_path}")
                            directory_node = {
                                'name': entry_name,
                                'path': entry_path,
                                'type': 'directory',
                                'children': []
                            }
                            parent_list.append(directory_node)
                            stack.append((entry_path, directory_node['children']))

                        elif entry_type == 'blob':
                            blob_info = entry.get('object', {})
                            file_node = {
                                'name': entry_name,
                                'path': entry_path,
                                'type': 'file',
                                'extension': entry.get('extension', ''),
                                'size': blob_info.get('byteSize', 0),
                                'is_binary': blob_info.get('isBinary', False),
                                'oid': blob_info.get('oid', '')
                            }
                            parent_list.append(file_node)

                except OfflineCacheMiss:
                    # Must not be skipped as a "failed path": an offline
                    # replay miss stops the run (#199).
                    raise
                except Exception as e:  # noqa: BLE001 — per-path walk: one failed path is logged and the walk continues
                    logger.error(f"Error processing path {current_path}: {e!s}")
                    continue

            return root_tree

        logger.info(f"Building repository tree via GraphQL for {owner}/{repo}")

        try:
            tree = build_tree_iterative("")

            return {
                'owner': owner,
                'repository': repo,
                'branch': branch,
                'tree': tree,
                'extracted_at': datetime.now(timezone.utc).isoformat(),
                'method': 'graphql',
                'total_items': len(tree)
            }
        except OfflineCacheMiss:
            # Must not become an "empty tree" error payload: an offline
            # replay miss stops the run (#199).
            raise
        except Exception as e:  # noqa: BLE001 — tree contract: any failure returns the documented error payload
            logger.error(f"Failed to build repository tree: {e!s}")
            return {
                'owner': owner,
                'repository': repo,
                'branch': branch,
                'tree': [],
                'error': str(e),
                'extracted_at': datetime.now(timezone.utc).isoformat(),
                'method': 'graphql'
            }

    def _standardize_tree_node(self, item: dict[str, Any]) -> dict[str, Any] | None:
        """
        Standardize the format of a tree node (REST or GraphQL).

        Args:
            item: Raw API item

        Returns:
            Standardized node or None if invalid
        """
        node_type = item.get('type', '')
        path = item.get('path', '')

        if not path:
            return None

        name = path.split('/')[-1] if '/' in path else path

        if node_type == 'blob':
            file_type = 'file'
        elif node_type == 'tree':
            file_type = 'directory'
        else:
            file_type = node_type

        standardized = {
            'name': name,
            'path': path,
            'type': file_type,
            'sha': item.get('sha', item.get('oid', '')),
            'mode': item.get('mode', '')
        }

        if file_type == 'file':
            extension = ''
            if '.' in name:
                extension = '.' + name.rsplit('.', 1)[-1]

            standardized['extension'] = extension

            size = item.get('size')
            if size is None and 'object' in item:
                size = item['object'].get('byteSize', 0)

            standardized['size'] = size or 0
            standardized['is_binary'] = item.get('is_binary', False)

        elif file_type == 'directory':
            standardized['children'] = item.get('children', [])

        return standardized

    def _empty_tree_response(
        self,
        owner: str,
        repo: str,
        branch: str,
        error: str = ""
    ) -> dict[str, Any]:
        """
        Return empty structure on error.

        Args:
            owner: Repository owner
            repo: Repository name
            branch: Branch
            error: Error message

        Returns:
            Standardized empty structure
        """
        return {
            'owner': owner,
            'repository': repo,
            'branch': branch,
            'sha': '',
            'tree': [],
            'truncated': False,
            'extracted_at': datetime.now(timezone.utc).isoformat(),
            'method': 'rest',
            'total_items': 0,
            'error': error
        }


def save_json_data(data: Any, filepath: str, timestamp: bool = True) -> str:
    """Save data to JSON file with optional timestamp metadata."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    if timestamp:
        now = datetime.now(timezone.utc).isoformat()
        if isinstance(data, dict):
            # Copy: callers may reuse the dict (e.g. in a consolidated file).
            data = {**data, '_metadata': {
                'extracted_at': now,
                'file_path': filepath
            }}
        elif isinstance(data, list) and len(data) > 0:

            metadata = {
                '_metadata': {
                    'extracted_at': now,
                    'file_path': filepath,
                    'record_count': len(data)
                }
            }
            data = [metadata, *data]

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Saved data to: {filepath}")
    return filepath

def load_json_data(filepath: str) -> Any:
    """Load data from JSON file."""
    if not os.path.exists(filepath):
        return None

    with open(filepath, encoding='utf-8') as f:
        return json.load(f)

def update_data_registry(layer: str, entity: str, files: list[str]) -> None:
    """Update the data registry with new files."""
    registry_path = f"data/{layer}/registry.json"

    registry = load_json_data(registry_path) or {}

    if entity not in registry:
        registry[entity] = {}

    registry[entity]['files'] = files
    registry[entity]['updated_at'] = datetime.now(timezone.utc).isoformat()
    registry[entity]['layer'] = layer

    save_json_data(registry, registry_path, timestamp=False)

class OrganizationConfig:
    """Configuration for organization data extraction."""

    def __init__(self, org_name: str):
        self.org_name = org_name
        # CoOps-specific blacklist for repositories to skip
        self.repo_blacklist: list[str] = [
            "Hi.Events",
            "Qualifying-Software-Engineers-Undergraduates-in-DevOps"
        ]

    def should_skip_repo(self, repo: dict[str, Any]) -> bool:
        """Check if repository should be skipped (blacklisted or fork)."""
        return (
            repo.get('name') in self.repo_blacklist or
            repo.get('fork', False)
        )


def parse_github_date(date_str: str | None) -> datetime | None:
    """
    Parse GitHub API date strings in various formats.
    Handles both UTC (Z) and timezone offset formats.

    Args:
        date_str: Date string from GitHub API, or None when the field is
            absent — the first statement below has always answered that
            with None, so the parameter is annotated with the type the
            callers actually pass (JSON ``.get()`` results).

    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None

    date_str = str(date_str).strip()

    # Try multiple date formats that GitHub uses
    formats = [
        '%Y-%m-%dT%H:%M:%SZ',  # UTC format: 2025-09-21T17:13:42Z
        '%Y-%m-%dT%H:%M:%S',    # Without timezone
    ]

    # Handle ISO 8601 format with timezone offset (e.g., 2025-09-21T17:13:42-03:00)
    if '+' in date_str or (date_str.count('-') > 2):  # Check for timezone offset
        try:
            # Extract the base datetime part (YYYY-MM-DDTHH:MM:SS)
            # Remove timezone suffix like -03:00 or +05:30
            base_date_str = date_str[:19]  # First 19 chars: YYYY-MM-DDTHH:MM:SS
            return datetime.strptime(base_date_str, '%Y-%m-%dT%H:%M:%S')  # noqa: DTZ007 — deliberate: GitHub timestamps are read as naive UTC, the pipeline-wide convention every consumer compares like-with-like; see #143
        except (ValueError, IndexError):
            pass

    # Try standard formats
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)  # noqa: DTZ007 — deliberate: GitHub timestamps are read as naive UTC, the pipeline-wide convention every consumer compares like-with-like; see #143
        except ValueError:
            continue

    # If all parsing fails, return None
    return None
