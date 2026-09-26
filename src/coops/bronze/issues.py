"""Issue events for the Bronze layer — the one family of the old issues
step the source port cannot express (#239).

Issues and pull requests themselves are written by
:class:`coops.bronze.bronze_service.BronzeService` since #30 wired it onto
the live path, through ``SourcePort.fetch_issues`` /
``fetch_pull_requests``. ``SourcePort`` has no ``fetch_issue_events``, and
faking one would change published data, so the events step stays here on
the legacy extraction path — on the run itself
(``coops.etl.bronze_extract.run_extraction`` calls it in the same step),
not beside it. Moving it is #239's to do, by growing the port method.

The files this module writes are read, together with the member files, by
``silver/collaboration_networks.py``, ``silver/contribution_metrics.py``,
``silver/member_analytics.py``, ``silver/members_statistics.py``,
``silver/temporal_analysis.py``, ``etl/gold_aggregate.py``, plus
``etl/registry_manager.py`` and ``scripts/verify_medallion.py``; see the
#30 wiring report. Removing this step would starve all of them.

``data/bronze/`` is a publish boundary: in fork-and-forget mode the
pipeline commits it to a public branch. So the stored record is BUILT from
named fields (:func:`_project_event`) rather than copied from the provider
and trimmed — a denylist only removes what someone has already noticed.
"""

from coops.bronze.watermarks import WatermarkStore
from coops.utils.cache_fold import client_fold
from coops.utils.data_helpers import strip_metadata
from coops.utils.github_api import (
    GitHubAPIClient,
    OrganizationConfig,
    load_json_data,
    save_json_data,
)


def _project_event(event, repo_name):
    """Keep only the event fields Silver reads; drop everything else.

    The full event payload is large and carries fields no consumer reads, so
    this projection is what keeps ``issue_events_*.json`` from growing without
    bound.
    """
    actor = event.get("actor")
    issue = event.get("issue")
    return {
        "id": event.get("id"),
        "event": event.get("event"),
        "created_at": event.get("created_at"),
        "repo_name": repo_name,
        "actor": {"login": actor.get("login")} if actor else None,
        "issue": {"number": issue.get("number")} if issue else None,
    }


def _load_prior_records(path: str, project=None) -> list[dict]:
    """Load a previously written bronze list, dropping the leading ``_metadata``.

    Returns ``[]`` when the file is missing or empty, so an incremental run over
    a repository whose previous run produced nothing still yields a fresh full
    extraction for that repository.

    ``project`` re-applies the field whitelist to every record read back. Without
    it the whitelist is only a guarantee about *writes*: an incremental run keeps
    prior records verbatim, so a record the provider never updates again would
    carry its original shape forever. Re-projecting on load makes the file
    self-healing — the whole file converges on the current whitelist at the next
    run, not just the rows that moved.

    The projection is idempotent (verified over 4,171 event records), so this
    costs nothing on data that is already clean.
    """
    data = load_json_data(path)
    if not isinstance(data, list):
        return []
    records = strip_metadata(data)
    if project is None:
        return records
    return [
        project(record, record.get("repo_name"))
        for record in records
        if isinstance(record, dict)
    ]


def _fetch_events_after(client, full_name: str, last_event_id: int, use_cache: bool) -> list[dict]:
    """Fetch issue events with ``id`` greater than ``last_event_id``.

    The repository issue-events endpoint has no ``since`` filter (a ``since``
    query is accepted but ignored), so incrementality must come from the id:
    events are returned newest-first, so we page forward from the newest page
    until we reach an event whose id is ``<= last_event_id``, then stop. A
    repository with no new events costs exactly one page.
    """
    newer: list[dict] = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{full_name}/issues/events?per_page=100&page={page}"
        data = client.get_with_cache(url, use_cache)
        if not isinstance(data, list) or not data:
            break
        for event in data:
            eid = event.get("id")
            if eid is None or eid > last_event_id:
                newer.append(event)
            else:
                return newer  # reached the boundary; everything later is older
        if len(data) < 100:
            break
        page += 1
    return newer


def extract_issue_events(
    client: GitHubAPIClient,
    config: OrganizationConfig,
    use_cache: bool = True,
    watermarks: WatermarkStore | None = None,
) -> list[str]:
    """Extract issue events for the filtered repositories.

    This is the events half of the extraction the legacy ``extract_issues``
    performed, kept whole: issues and PRs are the service's now, and events
    cannot cross the port (#239).

    Events are filtered to the essential fields (id, event, created_at,
    repo_name, actor.login, issue.number) to keep the files small. When
    ``watermarks`` carries a ``last_event_id`` for a repository, extraction is
    incremental for it: only newer events are fetched and appended, and
    records are stored sorted by id so a full extraction and an incremental
    one produce identical ``data/``.

    An offline replay (#199) replaces the fetched pages with the cache fold
    for the repository — the union of every cached events body, keyed by id,
    first version seen — exactly as the legacy step did.
    """
    filtered_repos = load_json_data("data/bronze/repositories_filtered.json")
    if not filtered_repos:
        print("No repositories found. Run repository extraction first.")
        return []

    generated_files = []
    all_issue_events = []

    # Skip metadata if present
    if isinstance(filtered_repos, list) and len(filtered_repos) > 0 and isinstance(filtered_repos[0], dict) and '_metadata' in filtered_repos[0]:
        filtered_repos = filtered_repos[1:]

    for repo in filtered_repos:
        if not repo or not isinstance(repo, dict):
            print(f"Skipping invalid repo entry: {repo}")
            continue

        repo_name = repo.get('name', 'unknown')
        full_name = repo.get('full_name') or repo_name
        wm = watermarks.get(full_name) if watermarks is not None else None
        last_event_id = wm.last_event_id if wm else None

        print(f"Processing issue events for: {repo_name}")

        if last_event_id is not None:
            fetched_events = _fetch_events_after(client, full_name, last_event_id, use_cache)
        else:
            fetched_events = client.get_paginated(
                f"https://api.github.com/repos/{full_name}/issues/events",
                use_cache=use_cache, per_page=100,
            )

        # Offline replay: the fold unions every cached events body of the
        # repository (pages of the unconditional URL included), keyed by id,
        # first version seen.
        last_seen_by_event_id = {}
        fold = client_fold(client)
        if fold is not None:
            folded_events = fold.events(full_name)
            fetched_events = [entry.record for entry in folded_events.values()]
            last_seen_by_event_id = {
                eid: entry.last_seen_at for eid, entry in folded_events.items()
            }

        repo_events = []
        for event in fetched_events or []:
            record = _project_event(event, repo_name)
            last_seen = last_seen_by_event_id.get(event.get("id"))
            if last_seen is not None:
                record["last_seen_at"] = last_seen
            repo_events.append(record)
        if last_event_id is not None:
            # Only events newer than the last one seen are appended.
            repo_events = _load_prior_records(
                f"data/bronze/issue_events_{repo_name}.json", _project_event
            ) + repo_events
        repo_events = sorted(repo_events, key=lambda item: item.get("id") or 0)

        all_issue_events.extend(repo_events)

        # Save per-repo events (unconditionally, as the legacy step did: a
        # repository with no events still writes its empty file).
        events_file = save_json_data(
            repo_events,
            f"data/bronze/issue_events_{repo_name}.json"
        )
        generated_files.append(events_file)

        # Advance the watermark for this repository. Only the event id is
        # this step's to advance: the issues/PRs half of the old single
        # update moved to the service, which sets ``last_updated_at``;
        # ``WatermarkStore.update`` merges, so each side keeps the other's.
        if watermarks is not None:
            newest_event_id = max((e.get("id") or 0 for e in repo_events), default=None)
            prior_event_id = wm.last_event_id if wm else None
            new_event_id = newest_event_id if newest_event_id is not None else prior_event_id
            watermarks.update(full_name, last_event_id=new_event_id)

    print(f"Extracted {len(all_issue_events)} events")

    return generated_files
