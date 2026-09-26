"""
Main orchestrator for Bronze layer data extraction.
Extracts raw data from GitHub API and saves to bronze layer.

Since #30 wired it in, the extraction itself is driven by
:class:`coops.bronze.bronze_service.BronzeService` through the source and
storage ports (:func:`run_extraction`); the two families the port cannot
express — members (#238) and issue events (#239) — stay on the legacy
extractors on the same path. This module remains the composition root: it
owns the client, the tenant, the watermarks' persistence decision, the
filesystem chores the port cannot express (the #216 reconciliation, the
#170 aggregate sweep, the #248 dedupe report) and the registry update.
"""

import argparse
import contextlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from coops.bronze.bronze_service import BronzeService
from coops.bronze.dedupe import write_report
from coops.bronze.files import bronze_dedupe_report, remove_aggregate
from coops.bronze.reconcile import reconcile_orphans
from coops.bronze.watermarks import WatermarkStore
from coops.domain import Tenant, TenantId
from coops.domain.ports.storage_port import validate_layer
from coops.github.adapter import GitHubSourceAdapter
from coops.infrastructure import get_settings, resolve_tenant_from_settings
from coops.storage.file import FileStorageAdapter
from coops.utils.github_api import (
    GitHubAPIClient,
    OrganizationConfig,
    update_data_registry,
)


def _write_run_summary(client: GitHubAPIClient) -> None:
    """Report cache hits/misses and the remaining REST rate limit.

    Written to stdout always, and appended to ``GITHUB_STEP_SUMMARY`` when the
    workflow provides one, so the run summary in Actions shows how the cache
    performed.
    """
    rl = client.last_rate_limit
    remaining = f"{rl['remaining']}/{rl['limit']}" if rl else "n/a"
    reset = ""
    if rl and rl.get("reset"):
        try:
            # The reset epoch is UTC; render it as UTC, not local time.
            reset = datetime.fromtimestamp(int(rl["reset"]), tz=timezone.utc).isoformat()
        except (TypeError, ValueError):
            reset = ""

    rows = [
        "| Metric | Value |",
        "|---|---|",
        f"| Cache hits | {client.cache_hits} |",
        f"| Cache misses | {client.cache_misses} |",
        f"| REST rate limit remaining | {remaining} |",
    ]
    if reset:
        rows.append(f"| REST rate limit resets | {reset} |")

    summary = "\n".join(["## Extraction cache & rate limit", "", *rows]) + "\n"
    print("\n" + summary)

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as f:
            f.write(summary)


def persist_watermarks(store: WatermarkStore, client: GitHubAPIClient) -> None:
    """Write the watermark file at the end of a run — never an offline one.

    An offline replay (#199) reads whatever the cache holds, so a watermark
    derived from it is a claim about the provider's state the run has no
    evidence for; writing it is precisely how a stale read became durable
    corruption. Skipping the write keeps the replay a diagnostic that cannot
    reproduce the mechanism it exists to diagnose.
    """
    if client.offline:
        print("Offline mode: watermarks are not saved (a replay must not move them from cached reads)")
        return
    store.save()


def _reconcile_bronze(args: argparse.Namespace) -> None:
    """Remove per-repository Bronze files the current listing does not name (#216).

    A renamed or recased repository leaves its old-case files beside the new
    ones, Silver and Gold glob both, and the repository is counted twice in
    published data. The deletion guard lives in ``reconcile_orphans`` and
    reads the FILE: ``repositories_filtered.json`` carries
    ``_metadata.complete: true`` only when the run that wrote it enumerated
    the organisation unbounded, and every other shape — a ``--max-repos``
    cap, a ``--repo`` restriction, an offline replay, or any listing that
    predates the provenance — refuses and deletes nothing, whatever this
    process's argv says. That last clause is the point: the narrowed run and
    the reconciliation need not be the same process, so an argv guard is a
    guard that is not there when it matters (a capped run exits; a later
    clean-argv reconciliation reads its 5-entry listing and would delete
    every other repository's files — the provenance is the only thing that
    stops it).

    **Reporting is the default; deletion is opt-in** via
    ``--reconcile-apply``. A routine that deletes files must not delete them
    because nobody passed a flag: the safe mode is the one you get by
    forgetting. Every run prints which mode ran.
    """
    reconcile_orphans("data/bronze", apply=args.reconcile_apply)


def _report_bronze_dedupe(bronze_dir: str = "data/bronze") -> None:
    """Print the by-id dedupe report and publish it beside the data (#248).

    Two halves of one requirement: the run report names every refused pair
    (repository id, both files, the totals each contributes) so a human
    reading the log sees the double count, and ``data/bronze/dedupe.json``
    ships the same statement WITH the published totals, so a number that is
    double-counted never travels without saying so. Written on every run —
    the clean corpus too — because an artifact that appears only on failure
    is indistinguishable from a check that never ran.

    A refusal never halts the run (#248): both copies stay counted, visibly.
    A failure to WRITE the artifact is printed loudly and also does not halt
    the extraction — the data is already on disk and the report is a
    statement about it, not a gate on it.
    """
    report = bronze_dedupe_report(bronze_dir)
    print()
    for line in report.format_lines():
        print(line)
    try:
        published = write_report(bronze_dir, report)
    except OSError as exc:
        print(
            f"ERROR: the dedupe report could not be published ({exc}); "
            "any refusal above did NOT reach the published metadata"
        )
        return
    print(f"Bronze dedupe report published: {published}")


def positive_int(value: str) -> int:
    """argparse type for caps: a cap of 0 or less would fetch nothing."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value}")
    return number


class PublishedLayoutStorage(FileStorageAdapter):
    """``StoragePort`` over the published layout: ``data/<layer>/<entity>.json``.

    The port's own filesystem adapter (#41) gives every tenant its own tree
    (``<root>/<tenant-slug>/<layer>/…``) — the layout a multi-tenant
    deployment needs. The published tree Silver and Gold read today is flat
    and single-tenant: one organisation per checkout, ``data/bronze/*.json``
    with no tenant segment. Wiring ``BronzeService`` onto the live path (#30)
    must not move the published files — every downstream reader globs
    ``data/bronze`` — so the composition maps the port's addresses onto the
    published layout here by dropping the tenant segment from the path,
    which is the only change: atomic replace, address validation and the
    never-written-tenant read all stay inherited.

    The tenant is still named on every call and the port still validates the
    address; this layout simply does not encode the tenant as a directory.
    Moving the published tree onto the tenant-scoped one is a decision that
    belongs with the Silver/Gold reimplementation (#264), which is when the
    readers move.
    """

    def _layer_dir(self, tenant: TenantId, layer: str) -> Path:
        return self._root / validate_layer(layer)


def _retire_bronze_aggregates(bronze_dir: str = "data/bronze") -> None:
    """Remove the retired ``*_all.json`` aggregates (#170).

    The sweep lived inside the legacy issues/commits extractors, where the
    aggregates used to be written. Those steps are ``BronzeService``'s now,
    and ``StoragePort`` has no delete (the service's own docstring assigns
    deletion to the caller that owns the filesystem), so the sweep runs here
    — one place, after every family has been written, exactly the guarantee
    the extractors used to give per-family.
    """
    for family in ("commits", "issues", "prs", "issue_events"):
        remove_aggregate(bronze_dir, family)


def run_extraction(
    client: GitHubAPIClient,
    tenant: Tenant,
    config: OrganizationConfig,
    *,
    use_cache: bool = True,
    offline: bool = False,
    max_repos: int | None = None,
    repo_filter: list[str] | None = None,
    max_issues: int | None = None,
    max_prs: int | None = None,
    max_commits_per_repo: int | None = None,
    skip_structure: bool = False,
    watermarks: WatermarkStore | None = None,
) -> list[str]:
    """Drive one Bronze run — the live extraction path ``main()`` calls.

    Every family the source port can express goes through
    :class:`coops.bronze.bronze_service.BronzeService` (repositories,
    issues, PRs, commits, structures). Two families the port cannot express
    stay on the legacy extractors, on this path and not beside it:

    - ``members_basic``/``members_detailed`` (#238): the ``Member`` model is
      a projection (identity, login, totals) and today's member records
      carry the provider payload (``avatar_url``, ``type``, profile fields,
      ``profile_fetched``, ``data_source``, …), not reconstructible without
      changing the model;
    - ``issue_events_<repo>`` (#239): ``SourcePort`` has no
      ``fetch_issue_events``.

    Removing either from the run would starve the Silver/Gold modules that
    read those files; that decision belongs to #238/#239, not to this
    wiring. Everything returns as ``data/bronze/<entity>.json`` paths for
    the registry.
    """
    if watermarks is None:
        watermarks = WatermarkStore()

    service = BronzeService(
        GitHubSourceAdapter(client, tenant, use_cache=use_cache),
        PublishedLayoutStorage("data"),
        tenant.id,
        watermarks=watermarks,
        offline=offline,
    )

    # Imported at call time, like the extractors always were, so the modules
    # (and their tests) stay patchable at the source.
    from coops.bronze.issues import extract_issue_events
    from coops.bronze.members import extract_members

    all_files: list[str] = []

    # ========================================
    # STEP 1: Extract Repositories (Required First)
    # ========================================
    print("\n" + "=" * 60)
    print("STEP 1: Extracting repositories")
    print("=" * 60)
    repo_entities = service.extract_repositories(
        max_repos=max_repos, repo_filter=repo_filter
    )
    repo_files = [f"data/bronze/{entity}.json" for entity in repo_entities]
    all_files.extend(repo_files)
    print(f"Generated {len(repo_files)} repository files")

    # ========================================
    # STEP 2: Extract Issues and Pull Requests (+ events, #239)
    # ========================================
    print("\n" + "=" * 60)
    print("STEP 2: Extracting issues and pull requests")
    print("=" * 60)
    conversation_entities = service.extract_issues(
        max_issues=max_issues, max_prs=max_prs
    )
    # The events family cannot cross the port (#239), so it stays on the
    # legacy extractor — same run, same step, reported as the gap it is.
    event_files = extract_issue_events(
        client, config, use_cache=use_cache, watermarks=watermarks
    )
    issue_files = [f"data/bronze/{entity}.json" for entity in conversation_entities]
    all_files.extend(issue_files)
    all_files.extend(event_files)
    print(f"Generated {len(issue_files)} issue/PR files, {len(event_files)} event files")

    # ========================================
    # STEP 3: Extract Commits
    # ========================================
    print("\n" + "=" * 60)
    print("STEP 3: Extracting commits")
    print("=" * 60)
    commit_entities = service.extract_commits(
        max_commits_per_repo=max_commits_per_repo
    )
    commit_files = [f"data/bronze/{entity}.json" for entity in commit_entities]
    all_files.extend(commit_files)
    print(f"Generated {len(commit_files)} commit files")

    # ========================================
    # STEP 4: Extract Organization Members (#238: legacy path)
    # ========================================
    print("\n" + "=" * 60)
    print("STEP 4: Extracting organization members")
    print("=" * 60)
    member_files = extract_members(client, config, use_cache=use_cache)
    all_files.extend(member_files)
    print(f"Generated {len(member_files)} member files")

    # ========================================
    # STEP 5: Extract Repository Structure
    # ========================================
    structure_files: list[str] = []
    if not skip_structure:
        print("\n" + "=" * 60)
        print("STEP 5: Extracting repository structures")
        print("=" * 60)
        structure_entities = service.extract_structures()
        structure_files = [f"data/bronze/{entity}.json" for entity in structure_entities]
        all_files.extend(structure_files)
        print(f"Generated {len(structure_files)} structure files")
    else:
        print("\nSkipping repository structure extraction (--skip-structure)")

    # The retired ``*_all.json`` aggregates (#170): the service cannot
    # delete through the port, so the sweep runs here, after every family
    # has been written (see _retire_bronze_aggregates).
    _retire_bronze_aggregates()

    print("\n" + "=" * 60)
    print(f"Total files generated: {len(all_files)}")
    print(f"   - Repositories: {len(repo_files)}")
    print(f"   - Issues/PRs: {len(issue_files)}")
    print(f"   - Issue events: {len(event_files)}")
    print(f"   - Commits: {len(commit_files)}")
    print(f"   - Members: {len(member_files)}")
    print(f"   - Structures: {len(structure_files)}")
    print("=" * 60)

    return all_files


def main():
    parser = argparse.ArgumentParser(description='Extract GitHub organization data to Bronze layer')
    parser.add_argument('--cache', action='store_true', help='Use cached data when available')
    parser.add_argument('--offline', action='store_true', help='Serve every response from the cache and never touch the network. A cache miss aborts the run (offline replay), so the run sees exactly what the cache holds. Implies --cache.')
    parser.add_argument('--cache-dir', default='cache', help='Directory for the API response cache (default: ./cache, relative to the current directory). Point it at the corpus when replaying, or a run from a scratch directory reads an empty cache while looking like it worked.')
    parser.add_argument('--repo', action='append', metavar='OWNER/NAME', help='Restrict the run to exactly these repositories (repeatable). Applied after the blacklist/fork filter, so a name that is unknown, blacklisted or a fork fails the run instead of being silently skipped.')
    parser.add_argument('--max-repos', type=positive_int, help='Optional hard cap of repositories to fetch')
    parser.add_argument('--max-issues', type=positive_int, help='Optional hard cap of issues per repo to fetch')
    parser.add_argument('--max-prs', type=positive_int, help='Optional hard cap of pull requests per repo to fetch')
    parser.add_argument('--max-commits-per-repo', type=positive_int, help='Optional hard cap of commits per repo to fetch (applied to the records written)')
    parser.add_argument('--skip-structure', action='store_true', help='Skip repository structure extraction')
    parser.add_argument('--reconcile-apply', action='store_true', help='Delete the Bronze orphans the reconciliation finds (#216: files left by a renamed or recased repository, counted twice downstream). Without this flag the reconciliation only REPORTS what it would remove. Deletion additionally refuses whenever the listing does not assert its own completeness in its _metadata (a --repo, --max-repos or --offline run, or one that predates #216).')
    parser.add_argument('--capture-dir', help='Capture every raw API response (REST and GraphQL) into this directory, tenant-scoped (corpus-raw, PRIVATE)')

    args = parser.parse_args()

    cfg = get_settings()
    if not cfg.github_token or not cfg.github_org:
        print(
            "ERROR: GITHUB_TOKEN and GITHUB_ORG must be set "
            "(environment, .env or .secrets). See RUNNING_LOCALLY.md.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Starting Bronze layer extraction for organization: {cfg.github_org}")
    print(f"Started at: {datetime.now().isoformat()}")  # noqa: DTZ005 — human log, not data: #143 deliberately left console timestamps in the operator's local wall clock
    if args.offline:
        print("Offline mode: every response is served from the cache; a cache miss aborts the run")

    # Initialize API client
    # One tenant per run, resolved from the deployment settings (#92): the
    # capture tree is keyed by tenant (`<root>/<tenant_id>/`), not by provider
    # account, so the writer gets the tenant's slug. The infrastructure
    # resolver translates the domain's errors into the configuration
    # vocabulary ("check TENANT_MODE"); the domain itself stays free of it.
    tenant = resolve_tenant_from_settings(cfg)
    client = GitHubAPIClient(
        cfg.github_token,
        cache_dir=args.cache_dir,
        capture_dir=args.capture_dir,
        tenant_id=(str(tenant.id) if args.capture_dir else None),
        offline=args.offline,
    )
    config = OrganizationConfig(cfg.github_org)

    # Offline implies cache use: the replay must read the cache even when
    # --cache was not spelled out (the client enforces this too; keeping the
    # flag in step makes the extractors' own cache reads explicit).
    use_cache = args.cache or args.offline

    # Per-repository extraction watermarks (issue #110): loaded from disk at the
    # start of the run and written back at the end, so the next run fetches only
    # what changed. A missing/corrupt file simply yields a full extraction.
    watermark_store = WatermarkStore()

    # Raw layer (MongoDB): when MONGO_URI is set, capture responses and read
    # them back instead of the API when they are fresh enough. Best-effort — a
    # missing/down MongoDB must not stop the extraction, so a failure to open
    # the store simply leaves the client on the API-only path.
    if cfg.mongo_uri:
        try:
            from coops.storage import MongoRawStore

            client.raw_store = MongoRawStore(cfg.mongo_uri)
            client.tenant_id = tenant.id
            client.raw_max_age_seconds = cfg.raw_max_age_seconds
        except Exception as exc:  # pragma: no cover - defensive, env-dependent  # noqa: BLE001 — optional Mongo raw layer: unavailability degrades to API-only, never fails the run
            print(f"[WARN] MongoDB raw layer unavailable ({exc}); using API only.")

    try:
        all_files = run_extraction(
            client,
            tenant,
            config,
            use_cache=use_cache,
            offline=args.offline,
            max_repos=args.max_repos,
            repo_filter=args.repo,
            max_issues=args.max_issues,
            max_prs=args.max_prs,
            max_commits_per_repo=args.max_commits_per_repo,
            skip_structure=args.skip_structure,
            watermarks=watermark_store,
        )

        # ========================================
        # Persist Watermarks
        # ========================================
        # Offline runs are excluded here, not in the store: loading the
        # watermark is what makes the replay request the same URL set as the
        # run it diagnoses, while persisting one would move it on no evidence.
        persist_watermarks(watermark_store, client)

        # ========================================
        # Reconcile Bronze with the current listing (#216)
        # ========================================
        # After every family has been written, so a rename leftover is
        # deleted in the same run that creates it — and before the registry,
        # which scans the layers and would otherwise legitimise the orphan.
        _reconcile_bronze(args)

        # ========================================
        # Report and publish the by-id dedupe (#248)
        # ========================================
        # After the reconciliation (an applied reconcile removes orphans, so
        # reporting first would name files that no longer exist) and still
        # before the registry, which scans the layers: the report must be on
        # disk with them.
        _report_bronze_dedupe()

        # ========================================
        # Update Registry
        # ========================================
        update_data_registry('bronze', 'all_extractions', all_files)

        print("\n" + "="*60)
        print("SUCCESS: Bronze extraction completed!")
        print("="*60)
        print(f"Total files generated: {len(all_files)}")
        print("="*60)

        _write_run_summary(client)

    except Exception as e:  # noqa: BLE001 — CLI boundary: report the failure and exit non-zero
        print("\nERROR: Bronze extraction failed")
        print(f"   {e!s}")
        import traceback
        traceback.print_exc()
        # Already on the abort path: if writing the run summary fails too,
        # there is nothing left to do but report the original failure.
        with contextlib.suppress(Exception):
            _write_run_summary(client)
        sys.exit(1)

if __name__ == "__main__":
    main()
