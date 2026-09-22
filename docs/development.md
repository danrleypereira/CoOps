# Development

Setup, configuration and local runs. The long-form walkthrough (including
`act`) is [RUNNING_LOCALLY.md](../RUNNING_LOCALLY.md).

## Setup

```bash
uv sync                    # creates .venv and installs the project + dev group
uv run pytest              # verify
cd dashboard && npm ci     # Node 20 or 22
```

Python ≥ 3.10; uv downloads an interpreter if needed. Without uv:
`pip install -e . --group dev` (pip ≥ 25.1).

## Configuration

`coops.infrastructure.Settings` (pydantic-settings) reads, in this order of
precedence: environment variables, then `.secrets`, then `.env` — the later
file in `env_file=(".env", ".secrets")` wins. Copy `EXAMPLE.secrets`; both
files are git-ignored.

| Setting | Names accepted | Notes |
|---|---|---|
| GitHub token | `COOPS_GITHUB_TOKEN`, `GITHUB_TOKEN` | needed by Bronze only |
| Organization | `COOPS_ORG`, `GITHUB_ORG` | the org to extract |
| Gemini key | `GEMINI_API_KEY`, `GOOGLE_API_KEY` | optional; AI step is skipped without it |
| Gemini model | `GEMINI_MODEL` | defaults to `gemini-3.5-flash-lite` |

Rules worth knowing:

- The `COOPS_` name wins over the `GITHUB_` one **within the same source**;
  the environment always beats the files. GitHub refuses to store secrets or
  variables whose names start with `GITHUB_`, which is why the aliases exist.
- **An empty value counts as unset**, because an undefined Actions secret
  expands to `""`.
- Silver, Gold and the registry need no credentials at all.

In Actions, Bronze reads `secrets.COOPS_GITHUB_TOKEN` when present (a
fine-grained token, public repositories, organization *Members: Read-only*) and
falls back to the default token, which only sees public memberships. Pushing
data always uses the default token.

## Running the pipeline locally

The commands read and write `./data` and `./cache` in the current directory, so
run them from a scratch directory to keep the checkout clean:

```bash
REPO=$PWD
cd "$(mktemp -d)"
export GITHUB_TOKEN=$(gh auth token) GITHUB_ORG=unb-mds
uv run --project "$REPO" coops-bronze --max-repos 3 --max-issues 20 --max-prs 20 \
  --max-commits-per-repo 50 --skip-structure
uv run --project "$REPO" coops-silver
uv run --project "$REPO" coops-gold
uv run --project "$REPO" coops-aggregate
uv run --project "$REPO" coops-registry
```

Cap flags must be positive integers. `--max-issues` and `--max-prs` cap what is
kept per repository; pagination stops early only when **both** are set, so
capping one never truncates the other. `--max-repos` bounds how many pages of
the repository list are fetched, and the fork/blacklist filter then runs before
the cap is applied — so a cap can yield fewer repositories than requested.
`--skip-structure` skips repository trees, which is the slow part.

## Dashboard

```bash
cd dashboard
npm run dev              # http://localhost:5173
npm run test:coverage
npm run build:gh         # tsc -b && vite build, as the Pages deploy runs it
npm run lint             # not in CI; 319 pre-existing problems
```

To develop against a local extraction, set `VITE_USE_LOCAL_DATA=true` in
`dashboard/.env` and link the data: `mkdir -p dashboard/public && ln -s ../../data dashboard/public/data`.

**Changing dependencies:** regenerate the lockfile with npm 11
(`npx -y npm@11 install --package-lock-only`). npm 10 crashes on this dependency
tree with `Cannot read properties of null (reading 'edgesOut')`. `npm ci` with
npm 10, which CI uses, works fine.

## Running workflows locally with act

```bash
gh act workflow_dispatch -W .github/workflows/bronze-extract.yaml \
  -j extract-bronze-data --secret-file .secrets --var COOPS_ORG=<org> \
  --bind --container-options "--user $(id -u):$(id -g)" \
  --input max_repos=3 --input skip_structure=true
```

- `--secret-file` fills `secrets.*` only; the workflow reads the organization
  from the `COOPS_ORG` **variable**, so pass `--var COOPS_ORG=…` or it extracts
  the owner of your `origin` remote.
- Silver and Gold need `--bind`: their "Pull latest data files" step runs
  without the `if: ${{ !env.ACT }}` guard that Checkout has.
- The container runs as root, and `uv sync` inside it rewrites `.venv` for the
  container's interpreter; `sudo rm -rf .venv` afterwards if `uv run` complains.
