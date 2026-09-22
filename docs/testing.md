# Testing and CI

## Suites

```bash
uv run pytest                                   # 577 passing, 10 skipped
uv run pytest tests/unit                        # unit only
uv run pytest tests/unit/test_config.py::test_reads_github_names
cd dashboard && npm run test:coverage           # 1601 passing, coverage ~91%
```

Pytest options live in `[tool.pytest.ini_options]` in `pyproject.toml`:
`--cov=coops` and the coverage report flags are already there, and `testpaths`
covers `tests/unit` and `tests/integration`. Coverage omits `ai_analysis/` and
`cleanup_event_data.py`.

Tests must not touch the network, and they must not write into the checkout —
anything that runs a real processor does so in `tmp_path`.

## CI

**Actions is disabled on `danrleypereira/CoOps`.** Pull requests there get no
checks at all. Everything runs in the organization fork `unb-mds/CoOps`, whose
`main` also carries the pipeline's data commits.

| Workflow | Runs | Gate |
|---|---|---|
| `python-unit-tests.yaml` | Python 3.10, 3.11 · Node 20, 22 | backend coverage `--cov-fail-under=60` |
| `python-integration-tests.yaml` | Python 3.10, 3.11, 3.12 | none — the integration suite alone covers ~27%, so it reports coverage without a threshold |
| `validate-pipeline.yaml` | manual | see below |

Frontend lint is not in CI.

## Validating a pull request

`validate-pipeline.yaml` runs the test suite and then the whole pipeline against
a real organization, capped, **committing nothing** — the generated `data/` is
uploaded as an artifact instead. It is the only pipeline workflow safe to run on
a PR branch.

```bash
BRANCH=$(git branch --show-current)
gh workflow run validate-pipeline.yaml --repo unb-mds/CoOps --ref "$BRANCH" \
  -f org=unb-mds -f max_repos=3 -f skip_structure=false -f run_ai=true
for w in python-unit-tests.yaml python-integration-tests.yaml; do
  gh workflow run "$w" --repo unb-mds/CoOps --ref "$BRANCH"
done
```

Its **Check outputs** step fails when any dataset the dashboard reads is
missing, or when the member profiles or the repository list come back empty, so
a green run means the dashboard would have data. When `COOPS_GITHUB_TOKEN` is
set, the artifact upload is skipped, because artifacts of a public repository
are downloadable by anyone signed in.

The full author/maintainer flow — draft PR, local checks, validation runs,
marking ready, merging, syncing the fork — is
[TESTING_PULL_REQUESTS.md](TESTING_PULL_REQUESTS.md). Two rules from it worth
repeating: a validation run must exist for the PR's **latest** commit, and the
fork's `main` is synced by **merging** upstream, never by force, because a force
sync would delete its data commits.

## Known failures

- Dashboard `npm run lint`: 319 problems (315 errors), not gated.
- `validate-pipeline` without `COOPS_GITHUB_TOKEN` sees no organization members
  (they are concealed) and falls back to repository contributors; member counts
  differ between a token run and a default-token run.
