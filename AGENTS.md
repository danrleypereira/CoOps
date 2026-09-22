# AGENTS.md

Guidance for AI coding agents working in this repository.

## Layout

Two independent projects in one repo:

- **Python ETL backend** (repo root): Medallion pipeline `src/` — Bronze → Silver → Gold — with tests in `tests/`.
- **React dashboard** (`dashboard/`): Vite + React 19 + D3 + TypeScript, tested with Vitest.

`data/` (bronze/silver/gold JSON), `data/master_registry.json`, and
`data/data_catalog.json` are **generated artifacts** committed back by GitHub Actions
bots. Don't hand-edit them; regenerate via the pipeline.

## Commands

Backend (from repo root):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

pytest                         # unit + integration (pytest.ini: -v --tb=short --maxfail=1)
pytest tests/unit
pytest tests/integration
pytest tests/unit/test_github_api_client.py::test_name   # single test
pytest --cov=src               # coverage; CI fails <60% (unit) / <70% (integration)
```

`tests/conftest.py` inserts `src/` into `sys.path`, so imports use flat package names
(`import utils.github_api`, `import silver.member_analytics`, `import gold.timeline_aggregation`).

Frontend (from `dashboard/`):

```bash
npm install
npm run dev              # http://localhost:5173
npm run test:coverage    # Vitest; 60% thresholds enforced in vitest.config.ts
npm run lint
npm run format
npm run build:gh         # production build (deploy-pages.yaml)
```

## ETL pipeline (manual, same order as CI)

```bash
python src/bronze_extract.py --token "$GITHUB_TOKEN" --org "$GITHUB_ORG" --cache --commits-method graphql
python src/silver_process.py --org "$GITHUB_ORG"
python src/gold_process.py --org "$GITHUB_ORG"
python src/registry_manager.py
```

Optional AI analysis (needs Gemini key; writes `data/silver/ai/members_ai.json`):

```bash
python -m src.ai_analysis.generate_members_ai          # add --test to limit to 3 members
```

## Secrets / env

- `.secrets` at repo root (gitignored; template in `EXAMPLE.secrets`) holds
  `GITHUB_TOKEN`, the org owner, and optional `GEMINI_API_KEY`. It is consumed by
  `act` (local workflow simulation) and by `src/ai_analysis/generate_members_ai.py`.
- The ETL entry scripts do **not** read `.secrets` — they take `--token` / `--org`
  CLI flags. CI passes `secrets.GITHUB_TOKEN` and `GITHUB_REPOSITORY_OWNER`.
- Frontend data source: `dashboard/src/services/dataSource.ts`. Default
  (`VITE_USE_LOCAL_DATA=false`) fetches from
  `raw.githubusercontent.com/<org>/<repo>/main/data`; set `VITE_USE_LOCAL_DATA=true`
  and copy `data/` into `dashboard/public/data/` to serve local files.

## CI / pipeline chain

- `bronze-extract.yaml` → `silver-process.yaml` → `gold-process.yaml` (then AI analysis
  if `GEMINI_API_KEY` secret set). Runs daily (cron 5 AM UTC), on push/PR to `main`,
  and `workflow_dispatch`; each step commits generated JSON back to the repo.
- `deploy-pages.yaml` builds `dashboard/` and publishes GitHub Pages.
- `gold-aggregate.yaml` is a separate dispatchable gold step that **rewrites
  `src/gold_aggregate.py` inline (heredoc)** before running it — the committed file is
  not what runs there. The chained gold step is `gold_process.py`.
- `start.yaml` and `save-issues.yaml` are legacy/manual-only.

## Conventions

- **Conventional Commits** required: `<type>(scope): description`. Branch prefixes
  `feat/`, `fix/`, `docs/`, `refactor/`, `chore/`, `hotfix/`. Squash merge; min 1
  approval; PR template in `.github/PULL_REQUEST_TEMPLATE.md`.
- License **GPL-3.0-or-later**; add the GPL header to new source files (see
  `CONTRIBUTING.md`).
- `CONTRIBUTING.md` and `desenvolvimento.md` are in **Portuguese**; `README.md` and
  `ARCHITECTURE.md` are in English.
- Coverage excludes: `.coveragerc` omits `src/ai_analysis/*`; `pytest.ini` omits
  `cleanup_event_data.py`.
