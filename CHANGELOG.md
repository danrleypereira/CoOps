# Changelog

All notable changes to CoOps are documented in this file.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and
the project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- `BronzeService` is on the live extraction path (#30). `coops-bronze` now
  drives the service through the source and storage ports
  (`coops.etl.bronze_extract.run_extraction`) for every family the port can
  express — repositories, issues, pull requests, commits and structures —
  and keeps the legacy extractors for the two it cannot: members (#238,
  the `Member` model cannot express today's member record) and issue
  events (#239, the port has no `fetch_issue_events`), both still produced
  by the same run, so the six Silver/Gold modules that read
  `members_*.json` and `issue_events_*.json` are not starved. Byte-parity
  is no longer the acceptance (#30 redefined: a diff report, not a gate —
  the owner is reimplementing the layers, #264): the wiring's output
  changes are the named port gaps — `commit.committer.name` and
  `html_url` become `None` on commit records (#240: the model cannot
  carry the committer's name across the port, and the history query
  requests no URL), and `repositories_*`/`repo_*` records become the
  `Repository` model's seventeen-key projection (#241: ~82 provider fields
  the model never reads no longer reach `data/bronze/`). The published
  location is unchanged: the composition stores through
  `PublishedLayoutStorage`, which maps the port's addresses onto the flat
  `data/bronze/` tree Silver and Gold glob (the port's own file adapter
  writes a tenant-scoped tree; moving the published tree onto it belongs
  with #264, when the readers move). The retired `*_all.json` aggregate
  sweep (#170) moved from the extractors to the CLI, where the
  filesystem chores the port cannot express live (deletion has no port
  method). `extract_repositories`, `extract_issues` and
  `extract_repository_structure` are removed;
  `coops.bronze.issues.extract_issue_events` is the events half of the
  old issues step, kept whole. `extract_commits` stays in the tree
  unedited: `TestRawReadPathScrub` (#111) pins the raw-read scrub through
  it and must pass unedited — `_sanitize_commit` and the scrub helpers it
  lives beside are imported by the service, and removing the function is
  entangled with rewriting that guard (a decision this change does not
  make). CLI flags the port cannot express are removed rather than kept
  as no-ops: `--commits-method`, `--since`, `--until`,
  `--commits-page-size`, `--include-active-branches`, `--active-days`,
  `--time-chunks` (there is no fetch window on the port and no transport
  choice — the adapter owns the policy); the two workflows that passed
  `--commits-method graphql` and `--since` were updated, and the
  `since` dispatch input was removed outright so a dispatcher passing it
  gets a loud unknown-input error instead of a silently ignored one.

### Added
- Bronze deduped by repository id at the reader (#248): a repository that
  is renamed or recased leaves its old per-repository files on disk beside
  the current ones (`repo_2025-1-NoFluxoUNB.json` and
  `repo_2025-1-NoFluxoUnB.json` both carry repository id `957040204`), and
  every reader globbed the family, so both spellings were read and the
  repository was counted twice in published data (measured: commits
  1,239 + 1,219, issues 117 + 109, prs 70 + 61, issue_events 1,414 +
  1,336). `coops.bronze.files.bronze_files` now feeds its enumeration
  through `coops.bronze.dedupe`, which keys every file by the `id` of its
  `repo_<name>.json` sibling — no listing provenance is consulted (#216's
  deletion needed it; "two files whose repository id is the same are the
  same repository" needs nothing) and nothing is deleted: the duplicate
  stays on disk, it is simply no longer read. The winner rule keeps the
  copy with the latest `_metadata.extracted_at` when the stamps are more
  than 48h apart (only the orphan mechanism explains a gap that size; the
  live pair is 7 days apart, one stamp naive and one aware, compared on
  UTC wall times so mixed awareness never raises). At most 48h apart — or
  with a stamp that cannot be read — the pair REFUSES: no winner is
  picked, both copies stay counted and the pair is reported, because an
  orphan that young is indistinguishable from concurrent duplicate
  generation, which is a different bug and must not be hidden by picking a
  winner. A family file whose `repo_` sibling is missing or carries no
  readable id is unmapped: counted, kept and reported, never dropped or
  merged. The refusal reaches OUTPUT, not a log line alone: every
  `coops-bronze` run prints the report (naming the repository id and the
  totals each copy contributes) and publishes `data/bronze/dedupe.json`
  beside the data — a new published artifact whose named consumer is the
  operator reading the corpus (the issue assigns the dashboard no new
  view); it is written on clean runs too, so absence is a choice, not a
  check that never ran. Silver and the AI step dedupe automatically
  through the shared reader; published totals for a deduped repository
  drop to that repository's single current copy.
- Bronze orchestration on the ports (#30): `coops.bronze.bronze_service.
  BronzeService` runs the Bronze layer's decisions — what to fetch, in
  what order, with what watermarks, and where each result is written —
  against `SourcePort` and `StoragePort` only, importing no concrete
  GitHub client and none of the legacy JSON file helpers. A differential
  acceptance (`tests/integration/test_bronze_service_differential.py`)
  runs the legacy extractors and the service over one fixed corpus from
  one stub client and asserts the two Bronze trees are byte-identical
  modulo the generation timestamps, with an arms-differ control that
  plants a dropped field and confirms the comparison fails and names it.
  The service covers repositories (raw/filtered/detail), commits, issues,
  PRs and structures, and writes the #216 listing provenance
  (`complete: true`) exactly when the enumeration is unbounded. Members
  and issue events are deliberately not ported — the source port has no
  `fetch_issue_events` and the `Member` model cannot express the member
  record — so `coops-bronze` keeps the legacy extractors until the port
  grows those; the findings, and the other not-yet-expressible behaviours
  (incremental fetch windows, the unchanged-tree skip, deletion, the
  watermark store's location), are documented in the module docstring.
  No published data changes in this step.

- Bronze orphan reconciliation (#216): a repository that is renamed or
  recased (`unb-mds/2025-1-NoFluxoUNB` and `2025-1-NoFluxoUnB` are one
  repository, id 957040204) leaves its old per-repository Bronze files on
  disk forever beside the new ones; Silver and Gold consume Bronze by
  glob, so both are read and the repository is counted twice in published
  data (measured: commits 1,239 current + 1,219 orphan = 2,458). Every
  existing guard asserts records must not *fall* — the orphan *adds*, so
  nothing could see it. Two halves. `coops.bronze.reconcile` removes
  per-repository files the current `repositories_filtered.json` does not
  name (`coops-bronze` runs it after every family is written, so a
  rename leftover is reported in the run that creates it;
  `--reconcile-apply` opts in to deleting), and
  `scripts/verify_medallion.py` gains `no-orphaned-bronze-files` — an
  orphan is bad data (rc 1, the file named), a missing or unreadable
  listing is the instrument (rc 2) — taking `--self-test` to 16
  controls, with the arms-differ control proving a clean corpus passes.
  Deletion refuses — deleting nothing — unless the listing itself
  asserts its own completeness: `save_json_data` can now write
  `complete: true` into the `_metadata` element, and
  `extract_repositories` sets it only when the run enumerated the
  organisation unbounded (no `--max-repos`, no `--repo`, not an offline
  replay). Absent means incomplete — fail closed, so every listing
  already on disk refuses too — and the guard is in the FILE, never the
  argv: a capped run that exits and a later clean-argv reconciliation
  are the shape that wipes a corpus, and provenance, never
  `record_count` (computed after truncation, indistinguishable from a
  small organisation), is what stops it. An empty `[]` listing carries
  no provenance at all and deletes nothing; a differently-cased file
  that is the only copy for its repository is kept; nothing outside
  `data/bronze` is touched.
- The contract suite for `scripts/verify_medallion.py` (#209): the phase
  gate was itself verified by nothing — `--self-test` proves its 14 checks
  can fail, and nothing proved the *script's* behaviour. Every defect it
  has shipped with (rc 0 while checks were skipped for want of
  `--reference`, a verdict that denied record loss while rc 2 was set by
  the instrument, a missing — then an empty — layer reading as success,
  an early return that dropped `no-record-vanished` from the report)
  lived in that second category, and each was caught by a human
  re-running the script. `tests/unit/test_verify_medallion.py` now drives
  `main()` end to end over synthetic corpora under `tmp_path` (never the
  frozen corpus): an exit-code matrix whose every row runs its clean twin
  in the same test (0 clean / 1 broken invariant / 2 skipped check,
  silent control, absent or empty layer), the precedence row (a missing
  layer AND real record loss → rc 2, with both findings named), check
  registration under every layer-presence × `--reference` combination —
  asserting the *set of names in the report*, the shape an absent row
  hides in — `--self-test` returning 14 of 14 and exiting 2 when a
  control stops firing (planted by stubbing one check), and row-format
  parsing for the tooling that reads the output. The script is unchanged:
  these tests assert its documented contract, and `--self-test` remains
  the evidence the checks work.
- `GitHubSourceAdapter` in `coops/github/adapter.py` (#29): the GitHub
  implementation of `SourcePort`, composing the existing
  `GitHubAPIClient` (transport), `coops.github.mapper` (every
  payload→model rule) and the domain's `Tenant` — glue with no mapping
  or HTTP of its own. One adapter serves one tenant through one GitHub
  account; a call naming another tenant reads nothing (empty
  organization-wide, `SourceNotFoundError` on repository addresses),
  mirroring the reference implementation in
  `tests/unit/test_source_port.py`. Provider faults that escape the
  client surface as `SourceUnavailableError`, never as the transport's
  own exception; `OfflineCacheMiss` still passes through so an offline
  replay (#199) stops the run. Provider policies the port leaves open:
  commits are the default-branch history (`graphql_commit_history`,
  REST fallback included), issues and PRs are read `state=all` from the
  shared endpoint and split behind the port, a truncated REST tree is
  finished by the GraphQL level walk, and repositories/members are
  yielded unfiltered (fork/blacklist policy stays with the Bronze
  caller, #26). A `TYPE_CHECKING` conformance anchor — the twin of the
  storage adapters' — binds the adapter to `SourcePort` so signature
  drift is a mypy error under `strict = true`.
- `select_storage` in `coops.storage.selection` (#42): the factory that
  turns configuration into the dataset `StoragePort`. `COOPS_STORAGE=data`
  (the `Settings` default, and what an empty value resolves to) selects
  `FileStorageAdapter` over `./data`; `COOPS_STORAGE=mongo` selects
  `MongoStorageAdapter` through `MONGO_URI`. An unknown value raises,
  naming the value and the accepted set — it does **not** fall back to a
  default: `COOPS_STORAGE=mongoo` must stop the run rather than quietly
  write files nobody asked for (the #129 wrong-org dashboard and #212
  evergreen skips are this defect class). `mongo` without `MONGO_URI`
  raises naming the setting. `FileStorageAdapter` is now exported from
  `coops.storage` alongside `MongoStorageAdapter`, as #41 promised. The
  ETL does not call the selector yet — that wiring lands with the layers'
  move onto the port (#30/#33/#34).
- The one `StoragePort` contract suite (#55):
  `tests/unit/test_storage_contract_suite.py` parametrises every
  behaviour the port promises over **every** adapter exported by
  `coops.storage.__all__` — round-trip, the absent read (`None`, never
  `[]`), sorted `list` plus empty for an unknown tenant,
  replace-not-append, and tenant isolation on **both** read paths. Each
  contract is written once and runs once per adapter: the per-adapter
  suites prove each adapter does what its author thought, this one
  proves they agree — the property the port exists to provide.
  Anti-drift is structural: the parameter list is derived from the
  exports rather than hand-written, a parametrised adapter with no
  factory fails the run, and a keystone test re-scans the exports
  against the collected parameters. `MongoStorageAdapter` skips without
  a reachable `MONGO_URI` (the reason names the variable), the terminal
  summary reports which adapters ran and which skipped, and a guard test
  fails any run that exercised nothing — the suite cannot pass
  vacuously.

### Changed
- Migrated the ten overlapping `tests/unit/test_github_api_*.py` files
  (2,717 lines, 139 tests) onto the seams #27–#29 created (#31):
  transport behaviour to `test_github_client_transport.py`, with the
  feature-sized transports renamed to `test_github_client_{etag,capture,
  offline,raw_layer}.py`; the GraphQL-document pin to
  `test_github_queries.py`; the query orchestration that remains in
  `coops/utils/github_api.py` to `test_github_api.py`; and the module
  helpers into the dedicated files that already existed
  (`test_save_json_data.py`, `test_parse_github_date.py`,
  `test_split_time_range.py`) plus a slimmed `test_github_api_utils.py`.
  45 duplicate tests were deleted, each paired with the named survivor
  that covers its behaviour, and 7 near-duplicates were merged into 4;
  per-file coverage of `src/coops/github/` and
  `src/coops/utils/github_api.py` is unchanged, missing-line lists
  included. Two migrated tests (`test_get_active_branches_error_handling`,
  `test_graphql_commit_history_error`) reached the live GitHub API
  through unmocked client calls; both are now hermetic.
  `TestRawReadPathScrub::test_no_address_reaches_bronze_from_raw_read`
  moved as part of a 100%-similarity rename and still fails in isolation
  when `_sanitize_commit` is neutered.
- Extracted the GitHub endpoint knowledge out of `coops/utils/github_api.py`
  into `coops/github/queries.py` (#28): the six REST URL templates
  (`repository_url`, `compare_url`, `commit_url`, `commits_url`,
  `branch_url`, `tree_url`) and the four GraphQL documents
  (`ACTIVE_BRANCHES_QUERY`, `COMMIT_HISTORY_BRANCH_QUERY`,
  `COMMIT_HISTORY_DEFAULT_BRANCH_QUERY`, `REPOSITORY_TREE_QUERY`) — every
  template and document byte-identical to the inline original it replaced.
  `queries.py` knows *what to ask GitHub* and nothing about *how to send
  it* (`coops/github/client.py`, #27) or *what to do with the answer*
  (that stays with the caller); the GraphQL documents keep their original
  inner indentation because the transport hashes the whole query text
  into its cache key, so a whitespace edit would orphan every existing
  cache entry and stop an offline replay on its first miss. The response
  shaping (`_standardize_tree_node`, `_empty_tree_response`, pagination,
  the REST fallback's circuit breaker) deliberately stayed in
  `github_api.py`. No behaviour change: 1406 passed, 24 skipped before
  and after.
- Extracted the reusable transport out of `coops/utils/github_api.py` into
  `coops/github/client.py` (#27): `GitHubTransport` now carries
  `OfflineCacheMiss`, construction, the URL-keyed cache and its ETag
  sidecars, the MongoDB raw layer, the raw-corpus capture, offline replay,
  run-summary accounting, `get_with_cache`, `graphql` and `get_paginated`,
  every method moved byte-identically; `GitHubAPIClient` inherits it and
  `OfflineCacheMiss` is re-exported, so all 43 importers of
  `coops.utils.github_api` keep resolving unchanged (the GitHub *queries*
  stay there for #28). Two consequences of the new
  `utils → github` import edge, both without a behavioural change:
  `coops/github/__init__.py` now serves `GitHubSourceAdapter` lazily (an
  eager re-export is a cycle in which every import order dies on a
  partially initialized module — `from coops.github import
  GitHubSourceAdapter` still works), and `GitHubTransport` imports
  `CacheFold` at first `offline_fold()` call instead of at module import
  (`coops/utils/__init__.py` eagerly imports `github_api`, so any
  module-level `coops.utils` import in `client.py` would make it
  unimportable as an entry point). `github_api.requests` is kept (noqa'd)
  as the attribute tests stub the HTTP boundary through.
- **Lint, format and type-check must be green, not "no worse than the base"**
  (owner ruling, 2026-09-25). Documented in `docs/definition-of-done.md` and
  `docs/phase-workflow.md`, and tightened in the pull request template. A phase
  PR exists to prove no regression was added; a tool that already fails on the
  base cannot prove that, because the new findings are lost in an argument about
  the existing ones. A phase branch must not be started from a base where these
  are not green — fix the base first on its own patch branch.

### Fixed
- A repository renamed or recased is no longer counted twice in published
  data (#216). `unb-mds/2025-1-NoFluxoUNB` and `unb-mds/2025-1-NoFluxoUnB`
  are one repository (id 957040204); the pipeline wrote the current-case
  Bronze file, the old-case file was never written again and never
  removed, and Silver and Gold glob both — measured, one recase published
  2,458 commits for 1,239. No check could see it: every assertion in the
  codebase is that records must not *fall*, and the orphan *adds* records.
  Two halves. `coops.bronze.reconcile` removes per-repository Bronze files
  whose repository is not in the current `repositories_filtered.json`
  (keying files by repository id remains the durable fix and is out of
  scope), run by `coops-bronze` after every family is written; a deletion
  routine is one bug away from wiping a corpus, so it REFUSES — deleting
  nothing — when the listing is missing, unreadable or empty, or when the
  run was narrowed by `--repo`, `--max-repos` or `--offline` (guarded on
  the flags, never on the size: a subset is indistinguishable from "every
  other repository is gone", and the capped debugging run is the one that
  would wipe). An old-case file that is the *only* copy for its repository
  is kept — deleting the only copy is the record loss every other guard
  exists to prevent. Reporting is the default and deletion is opt-in via
  `--reconcile-apply`: a routine that removes files must not remove them
  because nobody passed a flag. Every run prints which mode ran. Second half:
  `scripts/verify_medallion.py` gains `no-orphaned-bronze-files` — every
  per-repository Bronze file must correspond to the current filtered
  listing (rc 1, the file named; a missing or unreadable listing is the
  instrument, rc 2) — with two new controls, so `--self-test` goes from
  14 to 16: the planted recase leftover is rejected, and the same corpus
  without it passes.
- The 37 mypy errors Phase 1 added to pre-existing files (per-file gate
  against `a48bec6`): `Optional` plumbing threaded into Bronze/Silver without
  narrowing. Watermark reads in `bronze/issues.py` now narrow once
  (`last_updated_at`/`last_event_id`) with the guard at the use site, instead
  of dereferencing `wm` behind a bool computed eleven lines earlier;
  `full_name` falls back with `or` so it is never `None` at the
  watermark/fold call sites it was added to; `parse_github_date` is annotated
  `str | None`, which its first statement has always answered with `None`;
  and the Phase-1 locals (`name_counts`, `daily_activity`, the watermark
  `payload`, `GitHubAPIClient._cache_fold`) carry annotations instead of
  inferred unions. No `# type: ignore`, no `assert`, no behaviour change; the
  pre-existing debt in these files is untouched except where it shares the
  same inferred type as a regression (`daily_activity`'s day record,
  `full_name` in `commits`/`repository_structure`), which the same one-line
  fix clears incidentally.

### Added
- `scripts/check_regressions.py` (#119): a per-file regression gate comparing
  BASE to HEAD under ruff and mypy. Phase 1 shipped to `main` with +69 ruff
  findings in files that already existed at the base commit and +37 mypy
  errors in pre-existing files — invisible because ruff was never pinned or
  run, and because `pyproject.toml` scopes mypy to 21 of 62 files, so
  `bronze/issues.py` went 0 → 10 with no configured run seeing it. An
  aggregate total cannot catch this: Phase 1's net mypy count *fell*
  236 → 139 while seven files got worse. The gate materializes each ref with
  `git archive` (never a checkout; `data/` untouched), runs the pinned ruff
  (`ruff check src tests`) and a deliberately config-free mypy
  (`mypy --config-file /dev/null src/coops`) on both arms, and fails (rc 1,
  naming every file with its base → head counts) when a pre-existing file
  has more findings at head or a new file has any. Absolute counts are never
  gated — only the per-file delta — so the pre-ports debt does not block
  Phase 2. rc 2 means the gate could not run (tool missing, ref
  unresolvable, tool crash) and is never a pass. `--self-test` proves the
  gate can fail with four controls: a type error planted in the
  scope-excluded `bronze/issues.py` (the exact Phase 1 blind spot — the
  configured scope must not see it, the gate must fail on it), findings in a
  new file, an unchanged tree passing, and a file that improves passing
  without being named.
- `ruff==0.16.9` pinned in the dev group (#119), with a matching
  `[tool.ruff]` section (`target-version`, `line-length`,
  `required-version`): every "lint passes" claim before this used whichever
  ruff happened to be on PATH, or none. The section restates what ruff
  already infers (`requires-python`) or affects only rules `ruff check` does
  not enable by default, so pinning the version shifts no finding: 831 with
  the section, 831 without, measured on the same tree.
- `gold-regenerated` in `scripts/verify_medallion.py` (#201): with
  `--reference`, every Gold artifact's in-content `generated_at` must be
  strictly newer than the same artifact's in the reference corpus, or the
  gate fails (rc 1). A phase regeneration seeds `data/` from a previous
  corpus, so a Gold step that crashed — or never ran — left the seed's five
  valid artifacts in place and passed every presence, file-set and
  non-emptiness check: the phase was certified on numbers from the previous
  corpus. Unlike a backwards watermark — a reported diagnostic that must
  never gate, because it is the repair mechanism — stale Gold never
  self-corrects, so it gates. A stamp byte-identical to its reference
  counterpart fails outright, settled as a string comparison before any
  clock arithmetic: a copied seed sits at Δ0 — inside the tolerance band —
  and a band-first comparison passed it as `inconclusive`, the exact no-run
  the check exists to catch. Pre-#143 stamps are naive local time
  (ambiguous by up to 3h, measured at `-03:00`), so any comparison touching
  one is conclusive only outside a 3h band and reports `inconclusive` inside
  it rather than failing, and a naive/aware pair never raises. An artifact
  whose `generated_at` cannot be read — on either side — is the instrument,
  not the data (rc 2, naming the artifact); that is today's honest verdict
  for the two timelines (`_metadata.extracted_at`) and `registry.json`
  (`updated_at`), which carry no `generated_at` at all, so the check
  reports rc 2 naming them until the Gold writers stamp all five artifacts.
  Without `--reference` the check is skipped and the run exits 2, like the
  bronze staleness pair. `--self-test` grows from 12 to 14 controls.
- Offline replays now read the **newest cached version** of a record, not
  whichever URL the run happens to ask for (#199). The cache is keyed
  `md5(full URL)`, so one logical record lives in several entries — the
  unconditional listing and the `?since=<watermark>` ones — and a no-watermark
  replay read only the unconditional body, which can be months old: a
  regeneration on such a cache lost 55 records and reverted 34 others. In
  `--offline` mode, reading a repository's issues, PRs, commits or issue
  events now unions every cached response holding that repository's records
  and keeps the newest version of each (issues/PRs by `number` and the
  greatest `updated_at`; commits by `sha` and events by `id`, immutable, never
  compared; a record absent from every newer body survives — absence from a
  `?since=` response means "not changed", never "deleted"). Cache entries are
  attributed to repositories by content (GraphQL commit bodies carry no
  repository name and attach by commit-graph continuation). Measured on the
  #199 corpus: MED-APP issues 18 → 23 with `#5` at its newest cached
  `updated_at` (`2026-09-24T00:07:06Z`, was `2026-09-11T20:06:09Z`);
  2026.2-MeasureSoftGram-DOC commits 21 → 25. Online runs are unchanged.
- `last_seen_at` on every bronze issue, PR, commit and issue-event record
  written by an offline replay: when the cache last held a response containing
  that record (the entry's mtime). Nothing downstream reads it yet; it is what
  makes a staleness question answerable at all — today nothing records when a
  record was last confirmed (#199's staleness tooling is the named consumer).
- `--offline` for `coops-bronze` (and `offline=` on `GitHubAPIClient`): an
  offline replay mode that is a guarantee, not a preference. Every response
  is served from the cache — including warm entries with an ETag, which
  online would revalidate, so a blocked network can no longer turn them into
  `None` and silently drop the newest part of the corpus — and a cache miss
  raises `OfflineCacheMiss` naming the URL instead of producing a
  plausible-looking partial answer. Covers REST and GraphQL. Nothing can be
  written to the cache in offline mode (all write paths sit behind a
  successful HTTP response, which cannot happen). Nor does the run write
  `watermarks.json`: a replay has no evidence for any watermark it computes
  from cached reads — writing one is the mechanism that made the #199 loss
  durable — so the run says so once in its output and skips the write
  entirely. For reproducing the #199 regeneration loss.
- `--repo <owner/name>` (repeatable) for `coops-bronze`: restrict the run to
  exactly the named repositories. Applied after the blacklist/fork filter —
  naming an excluded repository fails the run naming it, rather than
  resurrecting it or running on an empty set and reporting success.
  `--max-repos` remains a count cap and cannot express "re-run this one
  repository"; this can.
- `--cache-dir` for `coops-bronze`: the API response cache directory
  (default `./cache`, relative to the current directory). A run from a
  scratch directory otherwise reads an empty cache and replays nothing while
  looking like it worked.

### Changed
- `ruff check src tests` now exits 0 and is the Python lint gate
  (`chore/ruff-green-baseline`): a finding on a phase PR is unambiguously
  new, where the previous state — 831 findings under ruff 0.16's defaults,
  with no `[tool.ruff]` at all — made "831 before, 840 after" a number
  nobody acts on. The gate is pinned to an explicit rule selection
  (`pyproject.toml`, `[tool.ruff]`) so a ruff upgrade cannot widen it on
  its own; two of its rule families are this repo's own defect classes:
  `DTZ` (naive datetimes, #143) and `BLE` (blind `except Exception`, #212).
  Deliberate breadth — CLI boundaries, per-item resilience in the
  extractors, best-effort raw layer — carries a targeted `# noqa` with the
  reason on the line; the md5 cache keys are marked
  `usedforsecurity=False` (content addressing, not security); the
  integration tests that turned every exception into a skip (#212) were
  rewritten to either fail or skip on a named precondition. Rules measured
  and left out of the gate (with counts) are documented next to the
  selection.
- Every timestamp the pipeline **persists** is now timezone-aware UTC and
  carries its offset in the value (`2026-09-25T04:40:09+00:00`, #143):
  `generated_at` in the Gold dashboard and tiers, `created_at` and
  `generated_at` in the registry/catalog, and `extracted_at`/`updated_at`
  in the `_metadata` sidecars and per-layer registries that
  `save_json_data`/`update_data_registry`/the tree responses write. They
  were naive local stamps — a GitHub Actions run wrote UTC while a local
  run wrote `-03:00`, so two corpora were not comparable and nothing in
  the value said which machine had written it. Readers are not broken:
  the Silver capture-time parser accepts both shapes and treats the old
  naive values as UTC. **Values shift once**: the first run after this
  change writes UTC, so a timestamp produced by a previous local run moves
  by its UTC offset in the wall-clock reading — that single jump is the
  fix, not drift. Console `Started at:` lines are untouched (human log,
  not data).
- The #143 UTC sweep missed `file_inventory[].modified_at` in
  `data/master_registry.json`: `create_master_registry` still wrote the
  local wall clock there, so the registry's inventory disagreed with the
  UTC `created_at`/`generated_at` written beside it by the same run. It is
  now `fromtimestamp(..., tz=timezone.utc)`, the same convention as the
  rest of the registry; the value shifts once, by the writing machine's
  offset, on the first run after this change.
- `performance_tiers.json` now carries `generated_at`, in the same format
  and from the same single clock reading as `executive_dashboard.json`, so
  the two artifacts written by one `coops-aggregate` run cannot disagree
  about freshness. Dashboard consumers that iterate the tier lists are
  unaffected (the new key is a scalar beside them).
- `FileStorageAdapter` (`coops.storage.file`): the local-filesystem
  `StoragePort` implementation (issue
  [#41](https://github.com/danrleypereira/CoOps/issues/41)), for development
  and the regression harness. Each tenant is one directory tree
  (`<root>/<tenant>/<layer>/<entity>.json`), files are written with the same
  `indent=2, ensure_ascii=False` JSON as the rest of the corpus, and reads
  for a tenant that was never written return `None`/`[]` without creating
  anything. Legacy `*_all.json` files left by pre-#170 runs are rejected on
  load and never listed. Not yet exported from `coops.storage` or wired into
  the ETL — exports land with the sibling adapters (#39) and
  `COOPS_STORAGE` (#42). The strict mypy run now covers `src/coops/storage`.
  Supersedes this branch's first `coops.storage.files_adapter`: that variant
  wrote compact JSON (not the corpus's `indent=2` format) and joined the
  tenant slug into the path without checking it is a single directory name,
  so a slug containing `..` could address another tenant's tree.
- `MongoStorageAdapter` (`coops.storage.datasets`), the MongoDB driver behind
  the `StoragePort` protocol (issue
  [#39](https://github.com/danrleypereira/CoOps/issues/39)). One document per
  `(tenant, layer, entity)` address in the `datasets` collection; `save`
  replaces outright (upsert on the full key, so a re-save cannot accumulate a
  second copy), `load` returns a `StoredDataset` or `None`, and `list` returns
  the tenant's entity names sorted. The compound index is
  `(tenant_id, layer, entity)`, unique — not the `{org_id, entity}` of the
  original issue text, which predates the port design: the port's key space is
  `(layer, entity)` and the codebase's vocabulary is `tenant_id`, and an index
  without `layer` would collide `bronze/members_detailed` with
  `silver/members_detailed`. Tenancy follows the proven `MongoRawStore`
  pattern: `tenant_id = str(tenant)` injected by the adapter on every write
  and filtered on every read, with no method that addresses data without a
  tenant. A static conformance anchor (`_conforms_to_storage_port`,
  under `TYPE_CHECKING`) binds the adapter to the port: widening mypy to cover
  `src/coops/storage` checks the module's own types but does not by itself
  assert the adapter still implements `StoragePort` — renaming `list` left the
  run green before the anchor and fails on it after.

### Removed
- The Bronze `_all` aggregates are no longer written and are removed by the
  pipeline where the write used to be (issue
  [#170](https://github.com/danrleypereira/CoOps/issues/170)):
  `commits_all.json` (80.6 MiB — 80.6% of GitHub's 100 MB hard push limit),
  `issue_events_all.json`, `issues_all.json` and `prs_all.json` repeated
  every record the per-repository files already contain and were 41% of the
  bronze tree. A run over an existing `data/bronze/` now deletes an aggregate
  left by an earlier run rather than leaving it stale beside current
  per-repository files. `data/silver/language_analysis_all.json` is a
  different layer's artifact and is untouched, as is the content of the
  per-repository files.

### Changed
- Silver member ages are now **ages at capture**, not ages "whenever the
  Silver step ran" (issue [#188](https://github.com/danrleypereira/CoOps/issues/188)).
  `account_age_days`, `maturity_score` and `status` in
  `members_analytics.json` (and therefore `member_status_distribution.json`
  and `maturity_bands.json`) were measured against `datetime.now()`, so
  every member's values incremented once per day with **no change to any
  input** — the file could never be byte-stable across days, every
  scheduled run in fork-and-forget mode emitted a diff in `data/silver/`
  whether or not anything happened, and a diff-by-key migration check
  against it could never be satisfied (during #185's review, 8 users'
  values differed between two regenerations and were wrongly attributed
  to the code change under test). Ages are now measured against the
  extraction timestamp already recorded in the Bronze sidecar
  (`_metadata.extracted_at` in `members_detailed.json`), so the artifact
  is stable for a given corpus. A corpus that carries members but no
  usable `extracted_at` (missing, not a string, or unparseable) now
  fails the Silver run with `ValueError` instead of guessing: a silent
  `datetime.now()` fallback would reintroduce the defect for exactly the
  corpora nobody tests, and a fixed age of 0 would publish every member
  as "new". An empty members corpus is unchanged: it still writes the
  empty artifacts and needs no capture time. Values shift once, on the
  first run after this change, from "age today" to "age at capture".
- Silver carries unattributed records in one explicit bucket, in both
  consumers (issues [#154](https://github.com/danrleypereira/CoOps/issues/154)
  and [#155](https://github.com/danrleypereira/CoOps/issues/155) — one
  defect, two symptoms). A commit whose identity channels are all null
  (measured 2026-09-23: 1,038 of 28,244 commits in local-run, 3.68%;
    0 of 130,186 in fga-eps-mds) and an issue event with
  `"actor": null` (measured: 957 of 298,395 — GitHub's answer for a
  deleted account) used to resolve to the string `'unknown'`, which the
  two Silver modules then treated oppositely: `members_statistics`
  excluded it (a silent drop — those records contributed to no member)
  while `temporal_analysis` kept it (a phantom contributor literally
  named `unknown`, credited with 1,081 events and rendered by three
  dashboard pages). The root cause, `or {}` / `or 'unknown'`, conflated
  "the key is missing" with "the provider told us there is nobody".
  Both modules now resolve identity through one shared module,
  `coops.silver.unattributed`, whose chains end in `None` — the same
  answer the domain layer settled in `Actor`/`github/mapper.py` (#165,
  #151): a person no channel identifies is absent, never an identity
  carrying a blank field. Unattributed records are **carried**, not
  dropped, and marked with a boolean `unattributed` field a reader and
  the dashboard can test — a field, not a magic name, since `'unknown'`
  collides with a login a real member may legitimately hold (a member
  whose login is literally `unknown` keeps their records). Shape
  changes on the next run: `temporal_events.json` records with no
  attribution carry `"user": null` plus `"unattributed": true` instead
  of `"user": "unknown"`; `daily_activity_summary.json` day rows gain
  `unattributed_events` (counted in the day's totals, never in
  `unique_users` or `authors`, so no aggregate presents them as one
  person); `members_statistics.json` gains one marked row —
  `"id": null, "name": null, "unattributed": true`, no averages —
  appended after the members when any exist. Gold's timeline reads
  unchanged (`if author and repo` already skips a null user). A corpus
  with no unattributed records gains no rows or events anywhere — the
  only output difference is the always-present
  `unattributed_events: 0` key on `daily_activity_summary.json` day
  rows (which Gold's day copies carry into the timelines).
- Corrected two measured figures cited throughout the source, the tests and
  the docs (issue [#154](https://github.com/danrleypereira/CoOps/issues/154)).
  **2,076 commits with no identifier was wrong; it is 1,038** — the original
  count read the *top-level* `author` object, so records carrying a login at
  `commit.author` were counted as identifier-less, roughly doubling it.
  **5.8% of authors with no account link was wrong; it is 5.1%** on
  `fga-eps-mds` (6,624 of 130,186). Both figures now name the corpus and the
  measurement date, because "the corpus" was ambiguous between two with
  different answers — `local-run` has 1,038 of 28,244 (3.68%) identifier-less
  commits where `fga-eps-mds` has **0 of 130,186** — and that ambiguity is
  what let a wrong number survive in seven places.
- Every commit author keeps `author_email_hash`, not only the unlinked ones
  (issues [#101](https://github.com/danrleypereira/CoOps/issues/101) and
  [#171](https://github.com/danrleypereira/CoOps/issues/171)). The hash was
  gated on `not login and numeric_id is None` — kept only when it was the sole
  identifier — which made the two identifier spaces disjoint. Measured over all
  130,186 commits in the `fga-eps-mds` corpus: 123,562 records carried an id and
  no hash, 6,614 a hash and no id, and **zero carried both**, so nothing
  downstream could learn that a hash and a login belong to the same person. The
  1,311 linked contributors and 231 unlinked hashes were therefore counted as
  1,542 people, with no way to reduce it. Applied at both ends — Bronze's
  `_sanitize_commit` and the domain mapper, which would otherwise discard the
  hash Bronze now stores. **No identity changes**: `identity_key` resolves
  `login -> email_hash -> name`, so a linked author still keys on its login and
  the hash is an additional, non-deciding channel. Publishing it adds no new
  *class* of data — it is already published for 6,614 records, and a SHA-256 is
  what `data/bronze/` stores in place of an address. Existing Bronze files are
  unaffected until re-projected from the cache; the code change does not
  rewrite data already written.
- Tenancy model, second half of issue
  [#92](https://github.com/danrleypereira/CoOps/issues/92) (issue
  [#187](https://github.com/danrleypereira/CoOps/issues/187)): every
  provider-neutral entity now carries the full tenancy triple — `tenant_id`
  (the opaque slug), `account` (the `ProviderAccount` the record was
  extracted from) and `external_id`, the provider's own identifier for the
  record as a plain string (GitHub's numeric ids stringified; for commits,
  the SHA). The shape of `external_id` was decided with the Mongo adapter
  (issue [#39](https://github.com/danrleypereira/CoOps/issues/39)) in view:
  it indexes `{org_id, entity}` and filters every query by `org_id`, so
  `external_id` is the record's key *within* an account — a whole provider
  id, never a composite, unique per provider account rather than globally.
  This changes the domain-model shape only: Silver output is byte-identical
  before and after (corpus-diffed per file), because the entity layer is
  not yet the Silver write path. `Member` gains a reserved, unpopulated
  `person_id` for cross-provider linking later (issue
  [#89](https://github.com/danrleypereira/CoOps/issues/89) removes
  email matching). The GitHub mapper rejects an account from another
  provider before mapping.
- Tenancy error vocabulary, the config leak #187 names: `resolve_tenant`
  in `coops.domain` now describes the domain ("no tenant mode named
  'bogus'"; a missing organization login) and never names environment
  variables. `coops.infrastructure.resolve_tenant_from_settings` is the
  translator that adds "check `TENANT_MODE` (and `COOPS_ORG`/`GITHUB_ORG`
  for `'single'`)", chaining the domain's diagnosis; `coops-bronze` uses
  it, so the CLI's errors keep naming the settings to check.
- Tenancy model, first half of issue
  [#92](https://github.com/danrleypereira/CoOps/issues/92): a tenant is no
  longer a GitHub organization. `TenantId` is an opaque slug we assign
  (`unb-mds`), trimmed but never re-cased — two spellings are two tenants, so
  the id survives an organization rename. The case-insensitivity rule about
  GitHub org names (trim + lower-case, from #68) moved to the new
  `ProviderAccount(provider, org_id)`, whose equality and hash are the
  `(provider, org_id)` pair: the same org name on two providers is two
  accounts, never one merged identity and never a dict-key/set collision. The
  new `Tenant(id, accounts)` holds them (non-empty, no duplicates), and
  `resolve_tenant` implements `TENANT_MODE=single` — one tenant with one
  GitHub account resolved from `COOPS_ORG`, with the slug bootstrapped from
  the normalised login so raw-capture directories and raw-layer documents
  keep their on-disk identity. `coops-bronze` resolves its tenant through it,
  so the CLI is unchanged. `TENANT_MODE=multi` raises `NotImplementedError`
  until the tenant registry lands. Entities carrying `ProviderAccount` plus
  the provider's `external_id` (#21) follow in the second half.
- Silver reads Bronze per-repository files instead of the `_all` aggregates
  (issue [#170](https://github.com/danrleypereira/CoOps/issues/170), step 1).
  `members_statistics`, `contribution_metrics`, `collaboration_networks` and
  `temporal_analysis` — the four processors that read only
  `issues_all`/`prs_all`/`commits_all`/`issue_events_all` — now load through
  one shared reader, `coops.silver.bronze_input.load_family`, built on
  `coops.bronze.files.bronze_records` (#156), which excludes the aggregate
  and the derived `_with_stats` copies at enumeration time. No output shape
  changed and no field was added or removed; the aggregates are still
  written (their removal is a later step of #170). Verified over the
  `fga-eps-mds` corpus: per-repository files are an exact multiset match of
  the aggregates (20,090 / 16,531 / 130,186 / 298,395 records), and the
  full Silver + Gold output differs from the aggregate-based run only in
  run timestamps and the order of equal-key records.

### Added
- mypy in CI (issue [#91](https://github.com/danrleypereira/CoOps/issues/91)):
  the compile-time half of the port contract. Phase 1's ports are
  `typing.Protocol`s, which are checked statically — `isinstance` against a
  `@runtime_checkable` Protocol only verifies that method *names* exist — so
  an adapter drifting from a port (missing `tenant` parameter, wrong return
  type) passed every test and failed only in production. `strict = true` in
  `[tool.mypy]` (`pyproject.toml`), scoped to `src/coops/domain` and
  `src/coops/github` (the issue's `providers/` is the `github/` adapter
  package); the pre-ports layers are excluded because a strict run over them
  starts at 348 errors — the follow-up widens as Phases 2 and 3 move code
  behind ports. Runs in `python-unit-tests.yaml` as its own step. Both
  scoped packages were already strict-clean (0 errors before, 0 after); the
  guard was proven to fail by checking a deliberately non-conforming
  scratch adapter: mypy reports the missing-`tenant` and wrong-return-type
  drift that `isinstance` accepts.
- `coops.bronze.files` (issue [#156](https://github.com/danrleypereira/CoOps/issues/156)):
  one place that knows how `data/bronze/` is named, so callers stop
  re-deriving it. `bronze_files` / `bronze_repos` / `bronze_records` enumerate a
  family with its aggregate excluded at source, and an unknown family **raises**
  naming the valid ones rather than returning empty — `bronze_records(path,
  "commit")` must not glob `commit_*.json`, match nothing and report a confident
  zero. Replaces four ad-hoc call sites: three spellings of the guard in
  `generate_members_ai.py` and an unguarded `structure_*.json` glob in
  `file_language_analysis.py`.

  Measuring `fga-eps-mds` said two of those guards were dead. **Only one was.**
  `"issue_events" in name` is unreachable by construction (`issues_*.json`
  cannot match `issue_events_*.json`; the prefixes diverge at character six).
  But `"_with_stats" in name` excluded nothing only because the current
  extractor stopped writing those files — an earlier version produced them as
  enriched copies sitting beside the originals, 142 of them still recorded in
  `data/bronze/structure_2025-2-Squad-01.json` at 4507f9a, and dropping the
  guard would double-count every repository that has one. It is kept, matched
  as a suffix rather than a substring, since the substring form also deleted a
  repository legitimately named `with_stats_repo`. Verified over the corpus:
  all four aggregates hold *exactly* their per-repository totals (commits
  130,186, issue_events 298,395, issues 20,090, prs 16,531), which is what
  proves they are duplicates rather than supplements — the premise
  [#170](https://github.com/danrleypereira/CoOps/issues/170) depends on.
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
- `coops.domain.ports.source_port` (issue [#22](https://github.com/danrleypereira/CoOps/issues/22)):
  the tenant-scoped `SourcePort` — `fetch_repositories` / `fetch_members` /
  `fetch_commits` / `fetch_issues` / `fetch_pull_requests` / `fetch_tree` —
  returning **domain models**, never provider payloads, so `application/`,
  `silver/` and `gold/` need zero changes when the GitLab adapter (#49)
  lands and #26 moves Bronze onto it. A `TenantId` is the first, required
  parameter of every method and implementations scope every read to it;
  there is no method that addresses records without one. Decisions the
  issue left open, written into the module docstring: the streaming
  methods return `Iterator` (measured: 130,186 commits in one real
  organization — a `list` would force every adapter to materialise that);
  **incrementality is adapter-internal** (no `since` parameter — #110's
  watermarks are per-branch timestamps, a numeric event id, `updated_at`
  bounds and head SHAs, which one neutral parameter cannot express and
  GitHub-shaped cursors would leak); `fetch_tree` is addressed by
  `(tenant, repository, branch=None→default)` and returns one complete
  `FileTree`; provider conditions cross as `SourceError` subclasses
  (`SourceUnavailableError` / `SourceAccessError` /
  `SourceNotFoundError`), never the provider library's own exceptions,
  while a malformed address stays a caller bug (`ValueError`);
  repositories are addressed by bare name and `validate_repo_name`
  rejects path separators, making the provider's `owner/repo` form
  unrepresentable through the port. Verified read-only against the real
  corpus via `scripts/source_port_corpus_check.py`: 486 repositories,
  1,412 members, 130,186 commits, 20,090 issues, 16,531 pull requests and
  486 trees mapped with **0 failures** (`*_all.json` aggregates excluded
  by construction). Nothing consumes the port yet; no existing caller
  changed.
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
  channel identifies (`Commit.author: Actor | None`, the 1,038 commits of
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
  1,038 real commits; `Actor.resolve` still refuses an empty identity —
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
- The REST fallback inside `coops.utils.github_api`'s GraphQL extraction (issue
  [#203](https://github.com/danrleypereira/CoOps/issues/203)): commits fetched
  after the circuit breaker trips now carry the same author node the GraphQL
  path produces — `name`, `email`, `date` from `commit.author`, and the
  account link only from the REST `author` object (`login`, `id`). The old
  fallback kept `user.login` alone and let the git `name` stand in as that
  login when the commit had no linked account, so an address-bearing commit
  reached `_sanitize_commit` with no email to hash (no `author_email_hash`,
  hence unattributable — 2,818 commits in the measured corpus) and unlinked
  commits got a fabricated `login` that was never a GitHub account. Bronze
  records from the fallback are now indistinguishable from GraphQL ones.
- `coops.github.mapper.map_commit_rest` (issue [#168](https://github.com/danrleypereira/CoOps/issues/168)):
  Bronze records no longer map to commits the analytics cannot attribute.
  Two fallbacks, both mirroring what Bronze itself writes
  (`coops.bronze.commits`):
  - `committed_at` now falls back to `commit.author.date` when the record
    carries no `commit.committer` at all — the pre-#128 Bronze shape, which
    made the mapper fail on 100% of one corpus's records (28,244/28,244)
    with `Commit requires a non-empty committed_at`. `Commit`'s guard still
    raises when neither date exists.
  - the author's `login` (and `id`, when present) now falls back to
    `commit.author` when the top level carries no account link — the
    post-sanitize Bronze shape, where `_sanitize_commit` moves the account
    link inside `commit.author` and leaves no top-level `author` at all
    (measured: 0 top-level logins in either corpus; 27,206 of 28,244
    local-run and 123,562 of 130,186 fga records carry one inside). The
    top level still wins when both are present. Before, every local-run
    record mapped with `author=None` (its git names are null too) —
    records surviving, not attributing; after, 27,206 of 28,244 local-run
    records attribute (the remaining 1,038 carry no identifier on any
    channel), and fga attribution rises from 130,114 (git names) to
    130,168, with the 123,562 login-carrying records re-keyed from shared
    git names to account logins.
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
