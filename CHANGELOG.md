# Changelog

All notable changes to CoOps are documented in this file.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and
the project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
