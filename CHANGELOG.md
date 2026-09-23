# Changelog

All notable changes to CoOps are documented in this file.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and
the project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `coops.domain.ports.ai_port` (issue [#24](https://github.com/danrleypereira/CoOps/issues/24)):
  the tenant-scoped `AiSummaryPort` — one method, `summarize_members(tenant,
  summaries)`, abstracting the member-analysis step behind
  `data/silver/ai/members_ai.json`. Batching, throttling and provider wiring
  stay out of the interface on purpose: they are properties of a particular
  provider's quota and client, and a caller passing them is a caller that
  knows the provider — the failure the port exists to prevent. Provider
  condition crosses the boundary as data (`status="complete" | "partial" |
  "unavailable"` on the `MemberAnalyses` outcome, the `RawStore`
  down-storage-must-not-break-the-pipeline invariant, tested this time
  because of #138), never as an exception and never as placeholder text: a
  member without an analysis is absent from the result. `MemberSummary` is
  the already-projected summary (`JSONValue` payload, as with
  `StoragePort.save`); `MemberAnalysis` carries the three per-entity texts
  the dashboard consumes. Guards: member keys are trimmed but never
  case-folded (folding merges people, #151), address-shaped keys are
  rejected without echoing the address (#132), duplicate members are
  rejected on both request and result, and the outcome's status must be
  consistent with the count it reports. A source sweep with a
  can-find-a-leak control keeps provider tokens out of the module. Nothing
  consumes the port yet — rewiring `generate_members_ai.py` is a separate
  change; test fixtures are synthetic (no real people, `example.com`
  addresses).

### Fixed
- Silver artifacts are now deterministic across runs (issue [#172](https://github.com/danrleypereira/CoOps/issues/172)):
  `members_statistics.json`, `user_collaboration_metrics.json`,
  `repository_collaboration_analysis.json` and the emitted edge order of
  `collaboration_edges.json` serialized Python sets with a bare `list()`, so
  row order depended on `PYTHONHASHSEED` (random per process) and every
  scheduled run over unchanged Bronze produced ~900 meaningless diffs in the
  fork-and-forget commit. Every set-derived list is now `sorted()` before it
  reaches an artifact (4 sites in `silver/members_statistics.py` and
  `silver/collaboration_networks.py`). Values are unchanged — only the order
  within lists. Proven in tests by running the serialization in subprocesses
  under five `PYTHONHASHSEED` values and asserting byte-identical output.

### Added
- `coops.domain.ports.storage_port` (issue [#23](https://github.com/danrleypereira/CoOps/issues/23)):
  the tenant-scoped `StoragePort` — `save`/`load`/`list` per `(layer,
  entity)`, generalising `RawStore` (#113) over a different key space
  (Medallion datasets, not HTTP capture). A `TenantId` is the first,
  required parameter of every method and implementations scope every query
  to it; `load` returns the frozen `StoredDataset`, never a driver type,
  and nothing under `domain/` imports a database library. Decisions the
  issue left open: `layer` is `Literal["bronze", "silver", "gold"]`;
  `entity` is the dataset name within the layer (the file stem on disk
  today, e.g. `issues_<repository>`); `list` returns sorted entity names,
  not datasets. The `*_all.json` publish aggregates repeat every
  per-repository record of their kind, so they are **not addressable**:
  `validate_entity` rejects the `_all` suffix on both save and load.
  Nothing consumes the port yet — #30 moves Bronze onto it, #39 is the
  Mongo adapter. Entity examples use synthetic names (`2099.1-Demo`);
  no value from the private validation corpus appears in this change.
- `coops.domain.models` (issue [#21](https://github.com/danrleypereira/CoOps/issues/21)):
  provider-agnostic entities — `Repository`, `Member`, `Commit`, `Issue`,
  `PullRequest`, `ActivityEvent`, `FileTree`/`FileEntry`, plus the `Actor`
  value object they share — every one carrying a `TenantId` and exported
  from `coops.domain` alongside `TenantId`/`CorrelationId`. Identity and
  display name are two fields, never one (the #151 defect): `identity`
  resolves `login → author_email_hash → name`, while `display_name` may be
  `None` (address-shaped names, #132); a null event actor stays an absent
  actor, never a Member named "unknown", and so does a commit author no
  channel identifies (`Commit.author: Actor | None`, the 2,076 commits of
  [#154](https://github.com/danrleypereira/CoOps/issues/154)).
- `coops.github.mapper` (issue [#25](https://github.com/danrleypereira/CoOps/issues/25)):
  GitHub REST and GraphQL payloads → the domain models, built from named
  fields only (never by spreading a provider response). Handles commits in
  both provider shapes — REST (`sha`, `commit.author`, top-level
  `author.{login,id}`) and GraphQL (`oid`, `author.user.login`,
  `committedDate`, `parents.nodes`) — including unlinked authors (no
  account, identified by email hash), address-shaped author names and
  authors no channel identifies at all, who map to `author=None` instead
  of aborting ([#154](https://github.com/danrleypereira/CoOps/issues/154):
  2,076 real commits; `Actor.resolve` still refuses an empty identity —
  the mapper decides absence, as it already did for null event actors).
  Members, issues, pull requests, activity events and file trees (REST and
  GraphQL) map the same way. Nothing consumes the models yet; no existing
  module changed behaviour.
- Managed raw-corpus capture and the two-artifact split (issue
  [#109](https://github.com/danrleypereira/CoOps/issues/109)): `coops-bronze
  --capture-dir` now writes every REST and GraphQL response in the capture
  shape `{tenant_id, provider, endpoint, params, etag, fetched_at, payload}`
  (the shape #113 indexes on), tenant-scoped under mode `700`/`600`, with a
  retention policy enforced by `coops-corpus prune`.
  `scripts/data-snapshot.sh` gains `pack-raw` / `unpack-raw` (the private
  `corpus-raw` artifact) and `pack-fixtures` / `unpack-fixtures` (the
  sanitized, shareable `corpus-fixtures` artifact). `coops-corpus sanitize`
  drops the personal keys (`email`, `location`, `bio`, `company`, `blog`,
  `hireable`, `twitter_username`) and redacts email addresses found in free
  text. **`corpus-fixtures` is safe to share; `corpus-raw` is not** and must
  never be published, committed, uploaded, attached to an issue/PR, or stored
  in an `actions/cache`.
- `scripts/data-snapshot.sh`: pack, unpack, list and verify the raw GitHub
  corpus (`cache/` + `data/`) as a compressed, checksummed snapshot kept in a
  fixed directory outside the worktree, so a new git worktree can restore the
  corpus instead of re-fetching it (which takes about an hour of rate-limited
  API calls).
- Installable `coops` package (`src/coops/`) with a `pyproject.toml` declaring
  dependencies and metadata, plus `coops-bronze`, `coops-silver`, `coops-gold`,
  `coops-aggregate` and `coops-registry` console entry points —
  issue [#14](https://github.com/danrleypereira/CoOps/issues/14).
- `coops.infrastructure.Settings`: typed configuration read from the
  environment, `.env` or `.secrets` (`GITHUB_TOKEN`, `GITHUB_ORG`,
  `GEMINI_API_KEY`, `GEMINI_MODEL`, ...) — issue
  [#18](https://github.com/danrleypereira/CoOps/issues/18).
- `coops.domain.tenancy`: `TenantId` (organization name, trimmed and
  lower-cased) and `CorrelationId` value objects — issue
  [#19](https://github.com/danrleypereira/CoOps/issues/19).
- `coops-bronze` flags `--max-repos`, `--max-issues` and `--max-prs`
  (positive integers; capping issues never truncates PRs and vice versa),
  and the matching `workflow_dispatch` inputs of `bronze-extract.yaml`.
- **Validate Pipeline (manual)** workflow and
  `docs/TESTING_PULL_REQUESTS.md`: PRs are validated against a real
  organization before review.
- Dashboard: **AI Analysis** page (`/ai`, linked from the sidebar) with the
  AI-generated member analyses (`silver/ai/members_ai.json`). When the file
  is missing the page says AI analysis requires the `GEMINI_API_KEY` secret.
  The Analytics page stays unrouted (#74): it is slow on real data and
  duplicates the routed pages.
- Gold `organization_health.members_with_profile`: members with maturity data.
- Conditional requests for the Bronze REST client: each cached response now
  stores its `ETag` (in a `cache/<md5(url)>.etag` sidecar, leaving the JSON
  body format untouched), and the next request sends `If-None-Match`. A `304`
  serves the cached body without consuming a rate-limit slot; a `200` replaces
  the cached body and ETag. The Bronze workflow deliberately does **not**
  upload the cache to GitHub Actions storage: `cache/` holds unmodified API
  bodies that contain personal data (emails, full `/users` profiles) and this
  is a public repository, so `actions/cache` would expose the corpus to
  pull-request authors through the base-branch scope. A durable cross-run
  cache belongs on infrastructure we control — a self-hosted runner, or the
  Mongo raw layer tracked in
  [#113](https://github.com/danrleypereira/CoOps/issues/113). The run summary
  still reports cache hits/misses and the remaining REST rate limit — issue
  [#108](https://github.com/danrleypereira/CoOps/issues/108).
- Commit extraction now keeps the fields that cannot be recovered later: the
  GraphQL selection requests the full commit message body, the committer, and
  the parent shas (previously only the headline, author and stats were
  fetched, so the body, committer and parents were absent even from the raw
  cache). The REST paths store the same record shape, and everything still
  passes through the Bronze scrub, so no raw email reaches `data/bronze/` —
  issue [#111](https://github.com/danrleypereira/CoOps/issues/111).
- `.actrc` and `docs/local-actions.md`: the workflows run locally with
  [`act`](https://github.com/nektos/act) (`gh extension install nektos/gh-act`).
  `.actrc` pins the `catthehacker/ubuntu` runner images and the artifact
  server path; the guide documents the exact command for each workflow, how
  to pass secrets and variables safely, measured runtimes, and what cannot
  run locally (`deploy-pages.yaml`, which needs GitHub's OIDC endpoint).

- Local MongoDB for development: `docker-compose.dev.yml` (pinned `mongo:7.0.14`
  on a configurable non-27017 port bound to loopback only, persistent named
  volume), a `.env.example`
  template, and `make mongo-up` / `mongo-down` / `mongo-reset` / `mongo-load`
  recipes that load the sanitized `data/` output without a GitHub token. The
  private raw `cache/` corpus is only ever imported behind the explicit
  `make mongo-load-raw` opt-in — issue
  [#112](https://github.com/danrleypereira/CoOps/issues/112).
- Raw layer in MongoDB: a tenant-scoped `raw_capture` collection shaped
  `{tenant_id, provider, endpoint, params_hash, etag, fetched_at, payload}`,
  indexed on `(tenant_id, provider, endpoint, params_hash)`, behind a thin
  `RawStore` adapter (`coops.storage.raw`) ready to sit behind the StoragePort
  (#23). The tenant filter is enforced in the adapter, not by the callers, so
  one tenant cannot read another's documents by omitting a filter. When
  `MONGO_URI` is set, Bronze reads a fresh raw document instead of re-fetching
  the API (making re-processing free) and captures each fetched response back
  into the raw layer. The raw payload keeps personal data — author/committer
  emails — by design (#111); the Bronze scrub still runs on the raw-read path,
  so nothing personal reaches `data/bronze/` — issue
  [#113](https://github.com/danrleypereira/CoOps/issues/113).
- Incremental Bronze extraction with per-repository watermarks
  ([#110](https://github.com/danrleypereira/CoOps/issues/110)): a
  `watermarks.json` record per repository (last run, head sha per branch, last
  issue-event id, last issue/PR `updated_at`) lets a run fetch only what
  changed. Commits use a per-repository `since` (bounded by the previous run's
  start) and merge with the stored commits by sha; issues and PRs use the REST
  `since` filter (with a one-second margin for GitHub's exclusive comparison)
  and merge by number; issue events fetch only ids newer than the last seen and
  append; the repository tree is re-fetched only when the branch head sha
  moved; members and repositories are still re-fetched whole (they are cheap).
  Issues, PRs and events are now stored sorted by number/id, so a full
  extraction and an incremental one produce identical `data/`. Watermarks
  compose with the ETag cache and the raw layer rather than bypassing them, and
  everything written to `data/bronze/` still goes through the Bronze scrub.

### Changed
- Silver renders contributor display names again (issue
  [#151](https://github.com/danrleypereira/CoOps/issues/151), step 3 of 3):
  `name` in `members_statistics.json` and in the `daily_activity_summary`
  authors is now the label chain **login → real name → `Unknown contributor
  (<first 8 hash chars>)`**, while `id` keeps the identity chain
  (login → `author_email_hash` → name) unchanged. Unlinked commit authors
  whose real name exists in Bronze had been rendering as
  `Unknown contributor (a1b2c3d4)`; they now display that name, and labels
  may repeat across records (distinct `id`s keep them apart). Where an
  identity carries several spellings of its name, the label is picked by a
  deterministic rule — prefer a spelling containing a space, then the
  highest occurrence count, then lexicographic order — decided at
  aggregation, after every event for that identity has been seen.
  `temporal_events.json` still carries the raw identity in `user`, which is
  the join key Gold uses.
- The dashboard no longer treats a member's display `name` as their
  identity (issue [#151](https://github.com/danrleypereira/CoOps/issues/151),
  step 2 of 3): `AISummary` selection, deselection, highlight, removal and
  React keys all compare and key on the stable `id` added in step 1, and the
  `MemberAnalysis` guard rejects records without a non-empty `id`. Searching
  still matches on the display name. The Gold monthly timeline
  (`timeline_last_12_months.json`) now aggregates authors keyed by `id`
  instead of `name`, keeping `name` as a field of each entry, so two people
  who share a display name keep separate counts instead of merging.
- **Breaking:** `coops-bronze` reads the token and organization from
  `GITHUB_TOKEN`/`GITHUB_ORG` (environment, `.env` or `.secrets`); the
  `--token` and `--org` flags were removed, and `coops-silver`/`coops-gold`
  no longer accept the unused `--org`. On GitHub Actions the organization
  comes from the `COOPS_ORG` repository variable, falling back to the
  repository owner.
- Dependencies are managed with [uv](https://docs.astral.sh/uv/)
  (`uv.lock`, `uv_build` backend); dev tools are a `dev` dependency group
  installed by `uv sync`.
- The default Gemini model is now `gemini-3.5-flash-lite` (configurable with
  `GEMINI_MODEL`); `gemini-2.5-flash-lite` is no longer available to new API
  keys.
- The integration test workflow reports coverage without a threshold;
  coverage is gated by the unit test workflow.
- The daily pipeline now runs the KPI aggregation (`gold-aggregate.yaml`)
  after Gold processing, and the GitHub Pages deploy runs when the whole
  chain succeeds on `main` (it was triggered by a workflow nothing called).
- `bronze-extract.yaml` no longer runs on pull requests (it committed data to
  the PR branch); PRs are validated with `validate-pipeline.yaml`.
- Production workflow jobs install without the dev dependency group.
- Package version is `1.1.0.dev0`; `coops.__version__` is read from the
  package metadata.
- ETL modules moved under the `coops` namespace; all imports now use absolute
  `coops.*` paths.
- CI workflows install the project with `uv sync --locked` and invoke the
  console commands (`uv run coops-*`) instead of `python src/*.py`.
- Test/coverage configuration consolidated into `pyproject.toml`
  (`pytest.ini` and `.coveragerc` removed).
- Members are the union of the organization's members and the contributors
  of the extracted repositories (`is_org_member`, `contributions_total`);
  before, contributors were only used when the members API returned nobody.
- The daily Bronze workflow reads GitHub with the `COOPS_GITHUB_TOKEN` secret
  when it is set. With it, concealed organization memberships are extracted
  and published with the data.
- `docs/TESTING_PULL_REQUESTS.md`: a PR is now validated by running the
  workflows locally with `act`, not by dispatching them in the `unb-mds/CoOps`
  fork. Validating on a real fork is kept as an optional appendix, for the
  things only GitHub can run (Pages, `workflow_run`, the commit-and-push
  steps).
- `validate-pipeline.yaml` resolves the target organization with `curl`
  instead of `gh api`: the act runner images have no GitHub CLI. Same request,
  same error messages, same exit codes.
- The `Checkout repository` steps of `bronze-extract.yaml`,
  `silver-process.yaml` and `gold-process.yaml` no longer carry
  `if: ${{ !env.ACT }}`. `act` implements `actions/checkout` as the step that
  populates the container workspace, so skipping it left the job with no
  source and `uv sync` failed. The guard on the *Commit and push* steps is
  unchanged.

- Silver resolves commit-author identity as `login` → `author_email_hash` →
  `name` instead of `login` → `name`, so distinct unlinked contributors are no
  longer bucketed by display name (a shared name merged people, one person
  committing under two names split). `members_statistics` now separates
  identity from display: unlinked authors render as
  `Unknown contributor (a1b2c3d4)` (the first 8 hex chars of the hash) rather
  than the shared `unknown` bucket, and the label stays unique per person and
  never empty — #125.

### Fixed
- Dashboard: the data source no longer falls back to a hardcoded
  `DW-Corp` organization when `VITE_GITHUB_ORG` is unset. Without it the
  dashboard now fails closed — no fetch is attempted and every page shows a
  "configure VITE_GITHUB_ORG" state (`DataUnconfiguredError` /
  `DataNotConfigured`, siblings of `DataNotFoundError` / `DataNotGenerated`)
  instead of silently rendering a third party's data — #129.
- `dashboard/package-lock.json` was missing most dev dependencies, so
  `npm ci` failed; `@testing-library/dom` (a required peer of
  `@testing-library/react`) is now declared.
- Dashboard: the test suite and the production build (`tsc`) pass again;
  the tests were updated to the current UI, orphan tests for components that
  never existed were removed, and new tests raise frontend coverage to 91%.
  Fixes found on the way: the Structure page's member filter, the Analytics
  heatmap's weekday rows, HTTP status in data-fetch errors, and null entries
  in `filterMetadata`.
- Bronze fetches every organization member (the list stopped at 30) and
  their profiles, so Silver produces `members_analytics.json` and the
  dashboard's member counts are no longer 0 — #70. Only the profile fields
  Silver uses are stored (no email, location, bio or company); members whose
  profile can't be fetched are kept with `profile_fetched: false`, and profile
  requests stop when fewer than 200 API requests remain.
- `members_analytics.json` is always written (an empty list when there are
  no members), and no longer includes email, location, bio or company.
- Silver writes `data/silver/available_repos.json` for the dashboard's
  repository selectors — #71.
- `save_json_data` no longer adds `_metadata` to the dict it is given;
  consolidated files such as `language_analysis_all.json` had it on every
  record.
- Dashboard: every data file is loaded through `dataSource`, so the
  Visualization page and the repository selectors work on GitHub Pages;
  the per-repository tree is read from `silver/hierarchy_<repo>.json` — #48.
- Dashboard: a data file that hasn't been generated yet shows an explanatory
  message instead of an error, and real errors are no longer hidden — #87,
  #73.
- Dashboard: RepoStructureAnalysis no longer crashes on repositories without
  languages (#72); Analytics no longer mutates state while sorting (#75);
  Structure's filtering overlay follows data changes (#76); chart fixes in
  BarChart, PieChart, Histogram (`showKDE`, negative values), Heatmap and
  StackedBarChart — #77–#81.
- `validate-pipeline.yaml` checks every dataset the dashboard reads.
- Gold `organization_health.total_members` counts every extracted member,
  including those whose profile couldn't be fetched; `maturity_bands.json` is
  rewritten even when there are no members.
- Deep links to dashboard pages (e.g. `/CoOps/ai`) work on GitHub Pages
  (`404.html` fallback).
- Bronze no longer persists raw commit author/committer emails in
  `commits_all.json` and the per-repo commit files (committed to a public
  branch). Linked authors keep `login` + numeric `id`; unlinked authors get an
  `author_email_hash` (SHA-256 of the trimmed, lower-cased email) instead of
  the address. The two free-text fields that carry an address past a key-name
  sweep on the REST paths are handled too: the signed `commit.verification`
  object is dropped, and addresses in the commit message's `Co-authored-by:` /
  `Signed-off-by:` trailers are replaced with `[email removed]`, leaving the
  attributed name so contributor credit survives — #89.

### Removed
- `sys.path` manipulation hacks in `src/` modules and `tests/conftest.py`.
- Legacy `fetch_issues.py` GitHub code path (standalone `requests` client, own
  headers, `GH_TOKEN`, no pagination/retry, wrote to `src/data/extractions/`)
  along with its tests and the `save-issues.yaml` workflow — superseded by the
  Bronze layer (`coops/bronze/issues.py`); its output had no consumers.

### Security
- Bronze blanks `commit.author.name` / `commit.committer.name` when the value
  is itself an email address — a third free-text channel that carried real
  addresses past the email-key scrub (contributors who set `git user.name` to
  their address). The field is set to `None`, never a placeholder string, so a
  truthy placeholder cannot become a person downstream; every other name is
  left intact so attribution survives — #132.
- `scripts/data-snapshot.sh` keeps snapshots private at rest: the snapshot
  directory is created mode 700 and the archive and its checksum mode 600,
  under a restrictive umask. The corpus contains raw API responses with user
  email addresses, so a snapshot must not be published or shared.

## [1.0.0] - 2026-05-12

First stable release; baseline for the Journal of Open Source Software
submission. The version consolidates the AI analysis module, ETL enhancements,
and the contextual analytics frontend onto a single audited `main`.

### Added
- Google Gemini AI analysis module under `src/gemini_ai/` with graceful
  degradation when `GEMINI_API_KEY` is absent — PR
  [#7](https://github.com/danrleypereira/CoOps/pull/7).
- Backend ETL enhancements ported from the UnB `2025-2-Squad-01` instance
  (extended Silver layer, AI orchestration, repository-structure analytics) —
  PR [#6](https://github.com/danrleypereira/CoOps/pull/6).
- Frontend collaboration-network visualization built with D3.js force-directed
  layout — PR [#5](https://github.com/danrleypereira/CoOps/pull/5).
- Contextual analytics pages with per-page dynamic data fetching and improved
  UX in the dashboard — PR
  [#4](https://github.com/danrleypereira/CoOps/pull/4).
- Backend test coverage for the Medallion ETL raised to 88% with new unit
  suites under `tests/unit/` — PR
  [#8](https://github.com/danrleypereira/CoOps/pull/8).
- `CHANGELOG.md`, English-first `README.md`, issue and pull request templates,
  and a Maintainership section in `CONTRIBUTING.md` (this release).
- JOSS paper manuscript on the `paper` branch (`paper/paper.md`,
  `paper/paper.bib`, `paper/figures/`).

### Changed
- Bronze extraction migrated from GitHub GraphQL to the REST API, yielding an
  approximately 100x speedup on a single-organization daily run.
- Several frontend strings internationalized from Portuguese to English.

### Fixed
- Daily GitHub Actions pull-request workflow did not always push freshly
  extracted data — PR [#3](https://github.com/danrleypereira/CoOps/pull/3).
- Prompt-injection surfaces hardened in the Gemini module; safety filter has a
  documented fallback when responses are blocked.
- `React.FC` namespace import on `RepoFingerprint` component.

## [0.1.0] - 2025-09-26

Initial public release.

### Added
- GPL-3.0 license, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CONTRIBUTING.md`.
- Bronze → Silver → Gold Medallion ETL skeleton orchestrated by GitHub
  Actions (`bronze-extract.yaml`, `silver-process.yaml`, `gold-process.yaml`,
  `gold-aggregate.yaml`).
- React 19 + TypeScript + D3.js + Vite + Tailwind dashboard scaffold under
  `dashboard/`.
- Architecture documentation (`ARCHITECTURE.md`) covering data layers and
  workflow topology.

[Unreleased]: https://github.com/danrleypereira/CoOps/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/danrleypereira/CoOps/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/danrleypereira/CoOps/releases/tag/v0.1.0
