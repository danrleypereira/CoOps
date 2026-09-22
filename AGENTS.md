# AGENTS.md

CoOps is a GitHub-organization collaboration dashboard: a Python Medallion ETL
(Bronze extraction → Silver analytics → Gold KPIs) plus a React dashboard
published on GitHub Pages. This file is what an agent needs before its first
change; the details live in [`docs/`](docs/).

| Topic | File |
|---|---|
| Pipeline, package layout, data flow | [docs/architecture.md](docs/architecture.md) |
| Setup, commands, secrets, local runs | [docs/development.md](docs/development.md) |
| Test suites, CI, how PRs are validated | [docs/testing.md](docs/testing.md) |
| Vocabulary and data shapes | [docs/domain.md](docs/domain.md) |
| Human-facing contribution rules | [CONTRIBUTING.md](CONTRIBUTING.md) (Portuguese) |

## Five things that are easy to get wrong

1. **Dependencies are managed with uv**, locked in `uv.lock`: `uv sync`, then
   `uv run <cmd>`. There is no `requirements.txt`, no Poetry, no `pytest.ini`
   and no `.coveragerc` — pytest and coverage are configured in `pyproject.toml`.
2. **The package is `coops` under `src/`.** Import `from coops.utils.github_api
   import ...`; the ETL runs through the console commands (`coops-bronze`,
   `coops-silver`, `coops-gold`, `coops-aggregate`, `coops-registry`), not
   through file paths.
3. **The ETL takes no credentials on the command line.** `GITHUB_TOKEN` and
   `GITHUB_ORG` come from the environment, `.env` or `.secrets` through
   `coops.infrastructure.Settings`.
4. **GitHub Actions is disabled on `danrleypereira/CoOps` by design.** CI and
   the pipeline run in the organization fork `unb-mds/CoOps`; a PR gets no
   checks upstream. See [docs/testing.md](docs/testing.md).
5. **Everything under `data/` is pipeline output**, committed by bots in the
   fork. Don't hand-edit it, and don't commit what a local run leaves there.

## Commands

```bash
uv sync                      # install (Python >= 3.10)
uv run pytest                # backend suite
uv run coops-bronze --cache  # then coops-silver, coops-gold, coops-aggregate, coops-registry
cd dashboard && npm ci && npm run test:coverage   # frontend (Node 20 or 22)
```

The ETL reads and writes `./data` in the current directory. From the repository
root it overwrites tracked registry files, so run it from a scratch directory
with `uv run --project <repo> ...`.

## Conventions

- **Conventional Commits** (`feat:`, `fix:`, `docs:`, `ci:`, `test:`, …).
- **No `Co-Authored-By` trailers for AI assistants.** Human co-authors stay.
- Update `CHANGELOG.md` under `[Unreleased]` for user-visible changes.
- GPL-3.0-or-later.
- Open the PR as a draft, fill in `.github/PULL_REQUEST_TEMPLATE.md` (its
  **Organization validation** section is where the validation output goes),
  validate it locally with `gh act`, then mark it ready —
  [docs/TESTING_PULL_REQUESTS.md](docs/TESTING_PULL_REQUESTS.md) and
  [docs/local-actions.md](docs/local-actions.md).
