# Testing a pull request before review

CoOps extracts data from real GitHub organizations, and unit tests alone
don't prove that an extraction works. So every PR that touches the pipeline,
its workflows or its packaging is validated in the organization fork
**[`unb-mds/CoOps`](https://github.com/unb-mds/CoOps)** before it is marked
*Ready for review* on the main repository
**[`danrleypereira/CoOps`](https://github.com/danrleypereira/CoOps)**.

```
branch in unb-mds/CoOps ──► draft PR to danrleypereira/CoOps
        │
        ├─ 1. local checks (tests + capped local run)
        ├─ 2. "Validate Pipeline (manual)" workflow in unb-mds/CoOps
        ├─ 3. paste the run link in the PR, mark it Ready for review
        │
maintainer: reviews, re-runs validation if needed, approves, merges
```

## Roles

| Who | Does |
|---|---|
| Author | Pushes the branch to `unb-mds/CoOps`, opens a **draft** PR, runs steps 1–3 |
| Maintainer | Reviews the code, checks the validation run, approves and merges into `danrleypereira/CoOps` |

## 0. One-time setup

```bash
gh repo clone unb-mds/CoOps && cd CoOps
git remote add upstream https://github.com/danrleypereira/CoOps.git
uv sync
cp EXAMPLE.secrets .secrets        # set GITHUB_TOKEN and GITHUB_ORG=unb-mds
```

You need push access to `unb-mds/CoOps`. If you don't have it, ask a
maintainer, or run the same workflow in your own fork of an organization you
control.

## 1. Branch and draft PR

```bash
git fetch upstream && git switch -c feat/<issue>-<topic> upstream/main
# ...commit...
git push -u origin feat/<issue>-<topic>

gh pr create --draft --repo danrleypereira/CoOps \
  --head unb-mds:feat/<issue>-<topic> --base main
```

Opening the PR as a draft signals that it is not validated yet.

> GitHub Actions is currently disabled in `danrleypereira/CoOps`, so no checks
> appear on the PR there. All CI for a PR runs in the fork, in step 3.

## 2. Local checks

```bash
uv run pytest

# Capped run against the real organization (under a minute).
# The commands write to ./data and ./cache, so run them from a scratch
# directory instead of your checkout.
REPO=$PWD
mkdir -p /tmp/coops-run && cd /tmp/coops-run
export GITHUB_TOKEN=$(gh auth token) GITHUB_ORG=unb-mds
uv run --project "$REPO" coops-bronze --max-repos 3 --max-issues 20 --max-prs 20 \
  --max-commits-per-repo 50 --skip-structure
uv run --project "$REPO" coops-silver
uv run --project "$REPO" coops-gold
uv run --project "$REPO" coops-aggregate
uv run --project "$REPO" coops-registry
jq '.organization_health' data/gold/executive_dashboard.json
cd "$REPO"
```

If the frontend changed, also run `cd dashboard && npm run test:coverage`.

## 3. Validate in the organization fork

The **Validate Pipeline (manual)** workflow
(`.github/workflows/validate-pipeline.yaml`) runs the test suite and then the
whole pipeline (Bronze → Silver → Gold → Aggregate → Registry, optionally the
AI analysis) against a real organization. It **does not commit or push**.
The generated `data/` is uploaded as an artifact, so it is safe to run on the
PR branch itself.

### From the GitHub UI

`unb-mds/CoOps` → **Actions** → **Validate Pipeline (manual)** → **Run
workflow** → pick your branch (not `main`) → adjust the inputs → **Run
workflow**. The run uses the workflow file and code of the branch you pick;
the fork's `main` only has the file so GitHub lets you dispatch it, and a run
on `main` fails until upstream ships the `coops` package.

### From the gh CLI

```bash
BRANCH=$(git branch --show-current)
SHA=$(git rev-parse HEAD)              # must already be pushed

gh workflow run validate-pipeline.yaml --repo unb-mds/CoOps --ref "$BRANCH" \
  -f org=unb-mds -f max_repos=3 -f max_issues=20 -f max_prs=20

# follow the run for this exact commit (it takes a few seconds to appear)
sleep 10
RUN_ID=$(gh run list --repo unb-mds/CoOps --workflow validate-pipeline.yaml \
  --commit "$SHA" --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --repo unb-mds/CoOps --exit-status
gh run view "$RUN_ID" --repo unb-mds/CoOps --json url --jq .url   # paste this in the PR

# inspect the generated data locally
gh run download "$RUN_ID" --repo unb-mds/CoOps --dir /tmp/coops-artifact

# the regular CI workflows (Python version matrix, frontend tests)
for w in python-unit-tests.yaml python-integration-tests.yaml; do
  gh workflow run "$w" --repo unb-mds/CoOps --ref "$BRANCH"
done
sleep 10
gh run list --repo unb-mds/CoOps --commit "$SHA" \
  --json workflowName,status,conclusion,url --jq '.[] | [.workflowName, .status, .conclusion, .url] | @tsv'
```

> Known issue: the **Frontend Tests** jobs fail at `npm ci` on `main` too,
> because `dashboard/package-lock.json` is out of sync with `package.json`
> (npm on Node 20 reports the missing `@testing-library/*` entries; npm on
> Node 22 crashes with `Cannot read properties of null (reading 'edgesOut')`),
> and the first failure cancels the other job. Until a PR regenerates the
> lockfile, a PR that doesn't touch `dashboard/` only needs the Python jobs of
> *Unit Tests* to pass.

### Inputs

| Input | Default | Notes |
|---|---|---|
| `org` | repo variable `COOPS_ORG`, else the repo owner | Must be an organization |
| `max_repos` / `max_issues` / `max_prs` / `max_commits_per_repo` | 3 / 20 / 20 / 50 | Blank = no cap (full extraction, slow) |
| `since` | blank | ISO-8601, limits commit history |
| `skip_structure` | `true` | Structure extraction is slow |
| `run_ai` | `false` | Needs the `GEMINI_API_KEY` secret in the fork |

Optional repository settings in `unb-mds/CoOps`: variable `COOPS_ORG`,
secret `COOPS_GITHUB_TOKEN` (a PAT, to see private members/repos) and secret
`GEMINI_API_KEY`.

The generated `data/` is uploaded as the artifact `pipeline-data-<run id>`
(kept 7 days). The fork is public, so anyone signed in to GitHub can download
it: that is fine for public organization data. When `COOPS_GITHUB_TOKEN` is
set (it can read private data), the upload is skipped.

What a green run means: the tests passed, every command exited 0, and the
**Check outputs** step found every expected Bronze/Silver/Gold/registry file
as valid JSON, with at least one repository extracted. The run summary lists
each file with its record count.

> Which workflow to use: `validate-pipeline.yaml` is for PRs.
> `bronze-extract.yaml` and the Silver/Gold workflows it chains are the
> production pipeline: they **commit data to the branch they run on** and
> `bronze-extract.yaml` also runs daily. Don't dispatch them on a PR branch,
> and keep them disabled in the fork unless you want the fork's `main` to
> receive data commits.

> GitHub only dispatches workflows whose file exists on the repository's
> default branch; the run itself uses the file from `--ref`. If your PR adds
> a new dispatchable workflow, a maintainer first registers it in the fork
> through a small PR to `unb-mds/CoOps` `main` containing only that file
> (this is how `validate-pipeline.yaml` itself was bootstrapped). Until the
> file reaches upstream, the fork's `main` is ahead of upstream by that
> commit, which is why the sync in step 5 uses `--force`. Alternatively,
> test with `gh act` locally (see [RUNNING_LOCALLY.md](../RUNNING_LOCALLY.md)).

## 4. Mark the PR ready

Add the run links (validation, unit tests, integration tests) to the
**Organization validation** section of the PR description, then:

```bash
gh pr ready <number> --repo danrleypereira/CoOps
```

Push new commits? Re-run step 3 and update the link: the validation must
match the PR's latest commit.

## 5. Maintainer: approve and merge

```bash
PR=<number>
read -r HEAD_SHA HEAD_REF < <(gh pr view "$PR" --repo danrleypereira/CoOps \
  --json headRefOid,headRefName --jq '"\(.headRefOid) \(.headRefName)"')

# every run for the PR's latest commit: Validate Pipeline must be a success,
# and so must Python Integration Tests and the Python jobs of Unit Tests
gh run list --repo unb-mds/CoOps --commit "$HEAD_SHA" \
  --json workflowName,conclusion,url --jq '.[] | [.workflowName, .conclusion, .url] | @tsv'

# missing? run them yourself (step 3)
gh workflow run validate-pipeline.yaml --repo unb-mds/CoOps --ref "$HEAD_REF" -f org=unb-mds

gh pr review "$PR" --repo danrleypereira/CoOps --approve
gh pr merge "$PR" --repo danrleypereira/CoOps --squash
```

The branch lives in `unb-mds/CoOps`, so delete it there after the merge,
then sync the fork so the next PRs start from the new `main`:

```bash
git push origin --delete "$HEAD_REF"
gh repo sync unb-mds/CoOps --source danrleypereira/CoOps --branch main
```

`gh repo sync` refuses when the fork's `main` has commits upstream doesn't
have. The only expected case is a workflow registration commit (see the note
in step 3) whose file has now reached upstream: check with
`gh api repos/danrleypereira/CoOps/compare/main...unb-mds:CoOps:main --jq '.ahead_by, [.files[].filename]'`
and, if that's all it is, re-run the sync with `--force`. `--force` resets
the fork's `main` to upstream, discarding anything else merged there, so run
the same compare command afterwards and expect `ahead_by` to be `0`.
