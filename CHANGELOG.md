# Changelog

All notable changes to CoOps are documented in this file.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and
the project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
  organization in `unb-mds/CoOps` before review.

### Changed
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

### Fixed
- `dashboard/package-lock.json` was missing most dev dependencies, so
  `npm ci` failed; `@testing-library/dom` (a required peer of
  `@testing-library/react`) is now declared.

### Removed
- `sys.path` manipulation hacks in `src/` modules and `tests/conftest.py`.
- Legacy `fetch_issues.py` GitHub code path (standalone `requests` client, own
  headers, `GH_TOKEN`, no pagination/retry, wrote to `src/data/extractions/`)
  along with its tests and the `save-issues.yaml` workflow — superseded by the
  Bronze layer (`coops/bronze/issues.py`); its output had no consumers.

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
