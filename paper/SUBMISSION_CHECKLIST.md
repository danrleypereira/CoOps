# JOSS Submission Checklist — Action Items for Danrley

This file lives only on the `paper` branch. It tracks what still needs to
happen between now (2026-05-12) and pressing **Submit** at
<https://joss.theoj.org/papers/new>. Once the paper is accepted and the DOI
is assigned, delete this file (or move it to an internal doc).

---

## Done so far (as of 2026-05-13)

- [x] `prep/joss-submission` branch with CHANGELOG, English README, issue/PR
      templates, and Maintainership governance — opened as **PR #10**
      <https://github.com/danrleypereira/CoOps/pull/10>.
- [x] `paper` branch with `paper/paper.md` (1167 words, 7 JOSS-required
      sections), `paper/paper.bib` (17 entries), `paper/figures/` (5 figures),
      and `.github/workflows/paper-draft.yaml`.
- [x] Local PDF build verified via `openjournals/inara` — all 17 citations
      resolve, 5 figures render, 4 authors and 2 affiliations correct.

---

## Must do before opening the JOSS submission form

### 1. Merge PR #10 into `main`

Review and squash-merge <https://github.com/danrleypereira/CoOps/pull/10>.
After merge, `main` will contain the CHANGELOG, English README, and
governance updates that the paper references.

### 2. Tag `v1.0.0` on `main`

The paper points to `v1.0.0` as the submission baseline. Run **after** PR #10
is merged:

```bash
cd /home/jane/git/LabTech/CoOps/CoOps
git checkout main && git pull --ff-only origin main
git tag -a v1.0.0 -m "v1.0.0 - First stable release; JOSS submission baseline"
git push origin v1.0.0
gh release create v1.0.0 --title "CoOps v1.0.0" --notes-from-tag --verify-tag
```

### 3. Rebase the `paper` branch onto the merged `main`

After PR #10 lands, the `paper` branch will have a different ancestry than
the new `main`. Rebase or merge to keep histories clean:

```bash
git checkout paper
git pull --rebase origin main
# Resolve trivial conflicts if any (README and CHANGELOG should be identical)
git push --force-with-lease origin paper
```

### 4. ORCIDs — DONE

All three author ORCIDs are filled in `paper/paper.md`:

- **Danrley Willyan da Silva Pereira (UDF, corresponding):** `0009-0006-4982-3800`
- **Carla Silva Rocha Aguiar (UnB):** `0000-0003-3102-5166`
- **Kerlla de Souza Luz (UDF):** `0000-0002-2262-2324`

Pedro Druck (UnB) contributed code to the UnB instance of the dashboard but is
not a paper author; he is acknowledged in the Acknowledgements section.

### 5. Get each co-author's written agreement to be listed

JOSS requires that all listed authors have agreed to be co-authors and to be
accountable for the work. Send Carla and Kerlla a short note linking to
PR #10 and the rendered `paper.pdf` artifact from the
`Draft JOSS paper PDF` workflow run.

### 6. Verify the GitHub Action produces a green PDF

Visit <https://github.com/danrleypereira/CoOps/actions/workflows/paper-draft.yaml>
after the next push to `paper`. Download the `paper` artifact and open the
PDF — confirm the same rendering you see locally.

### 7. Verify 4 community/repo-state signals

Before submitting, double-check the JOSS pre-review will pass:

- `gh release view v1.0.0` returns the release (gate: tagged release).
- `gh pr list --state all` shows ≥ 4 merged PRs (we will have 8+ once #10
  merges).
- `gh issue list --state all` shows ≥ 1 issue (currently #1 closed).
- Latest commit on `main` is within 30 days of submission date.

---

## Strongly recommended — close the activity gap before submitting

CoOps had no commits between 2026-03-06 and 2026-05-12 (a ~2-month gap).
JOSS reviewers can see this and may flag the project as inactive. Land
**three** of the five items below over the next 2–4 weeks via real PRs.
Don't pad with empty commits — JOSS detects that.

### A. Open ≥ 5 GitHub issues from the artigo.tex future-work section

Use the new feature_request template. Suggested issues (from `artigo.tex`
line 463 and the README "Status" section):

1. _Expand support to other GitHub organization sizes (>500 repos)._
2. _Add code-quality metrics: cyclomatic complexity per file, branch
   coverage of analyzed projects._
3. _ML-based prediction of at-risk teams using historical Slope\_8w._
4. _Adapter for GitLab Issues/MRs (Bronze layer extension)._
5. _Configurable KPI weighting per institution in the Gold layer._

### B. Push backend coverage from 88 % → ≥ 95 %

Add tests under `tests/unit/test_gemini_ai.py` covering: (a) rate-limit
backoff path, (b) Gemini safety-filter fallback, (c) malformed JSON
response, (d) missing `GEMINI_API_KEY` graceful-degradation path. Real gap
identified in commit `f8e6901`.

### C. Split `ARCHITECTURE.md` per layer

Create `docs/architecture/{bronze,silver,gold}.md` linking to the existing
Mermaid diagrams under `docs/architecture/*.mmd`. Leave `ARCHITECTURE.md`
as a short index pointing at the three new docs.

### D. CLI ergonomics on `src/bronze_extract.py`

Add `argparse` flags: `--output-dir`, `--since`, `--dry-run`, `--version`.
Print proper `--help`. Document under `[Unreleased]` in `CHANGELOG.md`.

### E. Lint pass

`ruff check src/` and `eslint dashboard/src/`. Commit fixes per logical
file group. Title commits like `style(silver): apply ruff fixes`.

---

## Submission step — JOSS form fields

Once items 1–7 above are green:

1. Open <https://joss.theoj.org/papers/new> while signed in with your GitHub
   account.
2. Fill in:
   - **Repository URL:** `https://github.com/danrleypereira/CoOps`
   - **Branch with paper:** `paper`
   - **Software version:** `v1.0.0`
   - **Submitting author ORCID:** Danrley's (real value, not the placeholder)
   - **Languages:** Python, TypeScript
3. Submit. A pre-review issue opens at
   <https://github.com/openjournals/joss-reviews/>.
4. Editor pings within 1–4 weeks; reviewer feedback arrives as a checklist
   on the GitHub issue. Address each via PRs into `paper` (or `main` for
   code/docs fixes).
5. On acceptance: JOSS issues a DOI. Update the README "Citing CoOps"
   section, merge `paper` into `main`, optionally tag `v1.0.1`.

---

## Files created/modified in this session — quick reference

**On `prep/joss-submission` (PR #10, awaiting merge to `main`):**
- `CHANGELOG.md` (new)
- `README.md` (rewritten)
- `CONTRIBUTING.md` (Maintainership appended)
- `.github/ISSUE_TEMPLATE/bug_report.md` (new)
- `.github/ISSUE_TEMPLATE/feature_request.md` (new)
- `.github/PULL_REQUEST_TEMPLATE.md` (new)

**On `paper` (this branch):**
- `paper/paper.md` (1167 words, 7 sections)
- `paper/paper.bib` (17 entries)
- `paper/figures/{arquitetura-geral,dag-medalhao,pagina-inicial,rede-de-colaboracao,heatmap}.png`
- `.github/workflows/paper-draft.yaml`
- `.gitignore` (added `paper/paper.pdf` and `paper/jats/`)
- `paper/SUBMISSION_CHECKLIST.md` (this file)
