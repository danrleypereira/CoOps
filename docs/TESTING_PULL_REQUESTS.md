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
poetry install --extras dev
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

Opening the PR as a draft signals that it is not validated yet. CI (unit and
integration tests) runs on the PR in `danrleypereira/CoOps`.

## 2. Local checks

```bash
poetry run pytest

# Capped run against the real organization (a few seconds to a minute).
# Run it in a scratch directory: the commands write to ./data and ./cache.
mkdir -p /tmp/coops-run && cd /tmp/coops-run
GITHUB_TOKEN=$(gh auth token) GITHUB_ORG=unb-mds \
  poetry -C "$OLDPWD" run coops-bronze --max-repos 3 --max-issues 20 --max-prs 20 \
    --max-commits-per-repo 50 --skip-structure
poetry -C "$OLDPWD" run coops-silver
poetry -C "$OLDPWD" run coops-gold
poetry -C "$OLDPWD" run coops-aggregate
poetry -C "$OLDPWD" run coops-registry
jq '.organization_health' data/gold/executive_dashboard.json
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
workflow** → pick your branch → adjust the inputs → **Run workflow**.

### From the gh CLI

```bash
BRANCH=feat/<issue>-<topic>

gh workflow run validate-pipeline.yaml --repo unb-mds/CoOps --ref "$BRANCH" \
  -f org=unb-mds -f max_repos=3 -f max_issues=20 -f max_prs=20

# follow it
RUN_ID=$(gh run list --repo unb-mds/CoOps --workflow validate-pipeline.yaml \
  --branch "$BRANCH" --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --repo unb-mds/CoOps --exit-status

# inspect the generated data locally
gh run download "$RUN_ID" --repo unb-mds/CoOps --dir /tmp/coops-artifact
```

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

> A workflow can only be dispatched once its file is on the repository's
> default branch. If your PR is the one adding or renaming a dispatchable
> workflow, ask a maintainer to sync `unb-mds/CoOps` `main` first (or test
> with `gh act` locally, see [RUNNING_LOCALLY.md](../RUNNING_LOCALLY.md)).

## 4. Mark the PR ready

Add the run link to the **Organization validation** section of the PR
description, then:

```bash
gh pr ready <number> --repo danrleypereira/CoOps
```

Push new commits? Re-run step 3 and update the link: the validation must
match the PR's latest commit.

## 5. Maintainer: approve and merge

```bash
PR=<number>
gh pr checks "$PR" --repo danrleypereira/CoOps            # CI green
gh pr view "$PR" --repo danrleypereira/CoOps --json headRefOid,headRefName

# confirm a successful validation run exists for that exact commit
gh run list --repo unb-mds/CoOps --workflow validate-pipeline.yaml \
  --json headSha,conclusion,url --jq '.[] | select(.conclusion=="success")'

# or run it yourself
gh workflow run validate-pipeline.yaml --repo unb-mds/CoOps --ref <headRefName> -f org=unb-mds

gh pr review "$PR" --repo danrleypereira/CoOps --approve
gh pr merge "$PR" --repo danrleypereira/CoOps --squash --delete-branch
```

After merging, sync the fork so the next PRs start from the new `main`:

```bash
gh repo sync unb-mds/CoOps --source danrleypereira/CoOps --branch main
```
