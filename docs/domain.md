# Domain

The vocabulary the code uses, and the shapes the data actually has.

## Tenancy

`src/coops/domain/tenancy.py` holds the primitives added in Phase 0:

- **`TenantId(org_id)`** — trimmed and lower-cased, because GitHub organization
  names are case-insensitive; `TenantId("UNB-MDS ") == TenantId("unb-mds")`.
- **`CorrelationId`** — one id per pipeline run, `CorrelationId.new()`.

Nothing consumes them yet. Phase 1 (#20) revises this: `TenantId` becomes an
opaque slug we assign, `ProviderAccount(provider, org_id)` hangs under a tenant,
and every entity carries tenant + account + the provider's own id (#92). Don't
build new code on `TenantId(org_id)` meaning "the GitHub org".

## Members

"Members" are the **union** of the organization's members and everyone who
contributed to the extracted repositories, one record per login:

| Field | Meaning |
|---|---|
| `is_org_member` | returned by `/orgs/{org}/members` (needs a token that can see concealed memberships) |
| `contributions_total` | summed across repositories; 0 for members who never contributed |
| `data_source` | `members_api`, `contributors_api` or both |
| `profile_fetched` | whether `/users/{login}` succeeded |

`members_detailed.json` keeps only the profile fields Silver uses — login, id,
name, type, avatar, html_url, created_at, updated_at, public_repos, followers,
following. Personal fields (email, location, bio, company) are deliberately not
stored: this data is committed to a public branch. Members with
`profile_fetched: false` are excluded from `members_analytics.json` (no maturity
data) but still count in the Gold `total_members`; `members_with_profile`
reports the rest.

Profile requests stop when fewer than 200 REST requests remain in the rate-limit
window, so a large organization can't exhaust the token mid-run.

## Repositories, issues and events

- `repositories_filtered.json` excludes forks and blacklisted repositories; the
  filter runs **after** any `--max-repos` cap.
- Issues and pull requests come from the same paginated endpoint, so a cap on
  one can truncate the other unless both are set (see
  [development.md](development.md)).
- Issue events are stored with only the fields Silver needs, which is what keeps
  `issue_events_all.json` from growing without bound. Even so, Bronze files are
  the large ones: on `unb-mds`, `issues_all.json` is ~49 MB and GitHub rejects
  files over 100 MB — see #43, the planned move to a real storage adapter.

## Metadata convention

`save_json_data` prepends one metadata entry to a list, or adds a `_metadata`
key to a dict:

```json
[{"_metadata": {"extracted_at": "…", "file_path": "…", "record_count": 3}},
 {"login": "…"}]
```

Use `coops.utils.data_helpers.strip_metadata` to drop it — it removes only a
**leading** metadata-only entry. Don't filter records by "has a `_metadata`
key": records saved individually and then consolidated (the per-repository
language analyses) used to carry one each, which silently emptied
`language_analysis_all.json` for every consumer that filtered that way.

## Datasets the dashboard depends on

| Page | Reads |
|---|---|
| Organization | `silver/members_analytics.json`, `silver/contribution_metrics.json` |
| Timeline | `gold/timeline_last_7_days.json`, `gold/timeline_last_12_months.json` |
| Heatmap, Collaboration | `silver/activity_heatmap.json`, `silver/collaboration_edges.json` |
| Commits, Issues, Pull Requests | `silver/temporal_events.json` |
| Structure | `silver/temporal_events.json` |
| Visualization | `silver/language_analysis_all.json`, `silver/hierarchy_<repo>.json` |
| Repository selectors | `silver/available_repos.json` (plain array of names) |
| AI Analysis | `silver/ai/members_ai.json` (`{_metadata, members: {login: {...}}}`) |

`validate-pipeline.yaml` enforces this list: adding a dataset to a page means
adding it there too, or a missing file will only surface as an empty state in
production.
