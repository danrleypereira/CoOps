# Running a phase

How a phase gets implemented, tested against real data, and merged. Read
[development-data.md](development-data.md) first — it covers where the data
comes from and what must not be written to.

## The shape

```
issue PR  ->  phase/<epic>-<slug>  ->  main
```

Issue PRs target the **phase branch**, never `main`. The phase merges to `main`
once consolidated and verified. Exception: a tooling or docs PR touching nothing
under `src/`, `data/` or `dashboard/` may go direct — but check first whether the
file differs between the two branches, or the merge silently reverts the phase's
newer version.

### `Closes #N` does not work here

A PR merged into a phase branch has its `Closes` keyword **ignored and spent**,
so the issue never closes — not then, and not on the eventual merge to `main`.
Write `Refs #N` and close by hand with evidence. This is how the tracker reached
84 open issues whose work had already shipped.

## Implementing

Heavy lifting goes to opencode agents; see the `opencode-agents` skill. Two
things the measurements here keep confirming:

- **Split anything large.** Dispatch cost grows with the *square* of the step
  count — two 50-step runs cost about half of one 100-step run. A brief that
  replaces 18 call sites across 7 modules is three dispatches, not one.
- **A prohibition in a brief is a preference, not a guardrail.** Agents have
  ignored explicit, capitalised instructions — opening draft PRs, editing fenced
  files. If something must not happen, verify it afterwards rather than trusting
  the prompt.

Every PR is gated by the agent who did **not** dispatch it. Approval is for a
**commit**: if the head moves, the approval is void and the gate runs again.

## Verifying against real data

A green suite says the code does what its tests expect. It does not say the
pipeline still produces correct data. That needs a regeneration.

### 1. Derive from the frozen snapshot

```bash
cd ~/.local/share/coops/snapshots
sha256sum -c coops-raw-<stamp>.tar.gz.sha256      # never skip
mkdir -p /var/tmp/coops-work
tar -xzf coops-raw-<stamp>.tar.gz -C /var/tmp/coops-work
cp -r /var/tmp/coops-fga/data /var/tmp/coops-work/data   # seed, so BEFORE means something
```

Seeding matters: a from-scratch tree has no previous state, so "did the defect
go away" has nothing to compare against.

### 2. Run the layers

```bash
COOPS_WORK=/var/tmp/coops-work \
REQUIRE_MARKERS="<symbols this run depends on>" \
REQUIRE_ANCESTOR="<commit whose work this run needs>" \
REQUIRE_BASELINE="<the defect being removed>" \
  ./regen-all-layers.sh
```

The guards are the point. `REQUIRE_ANCESTOR` refuses a run against a head that
predates the fix — otherwise the run reproduces the defect in fresh data and
reports success. `REQUIRE_BASELINE` refuses unless the defect is *present to
begin with*, because "clean afterwards" proves nothing if it was clean before.

`coops-registry` runs **last and is not optional**: the manifests are generated
by scanning the layers, so skipping it leaves them advertising files that no
longer exist.

### 3. Check the medallions

```bash
uv run python scripts/verify_medallion.py --self-test          # controls first
uv run python scripts/verify_medallion.py --root /var/tmp/coops-work
```

**Run `--self-test` first, every time.** It plants a defect for each check and
confirms the check rejects it. A check that has never failed proves nothing, and
this script exists because the regeneration script spent three iterations
enforcing a baseline and never checking the outcome.

Exit codes: `0` pass, `1` a layer fails an invariant, `2` a check could not run
or a control did not fire. **`2` is not a weaker `1`** — it means the instrument
is broken, not the data.

### 4. Read the numbers, not the verdict

The regeneration prints per-layer addresses and record counts. Both matter, and
for opposite reasons:

- **Records must not fall** in Bronze — a drop means data was dropped.
- **Records falling in Silver is ambiguous.** Once identity merging lands
  (#171), a correct run produces *fewer* Silver records, and the criterion must
  measure the fall against the number of merged identities rather than fail it
  outright.
- "Fewer addresses" alone is exactly as consistent with having destroyed the
  data as with having cleaned it. That is why both are reported.

### Known non-determinisms — not regressions

- `_metadata.extracted_at`, `updated_at`, `generated_at` differ between any two
  runs.
- Record **order** within a file changed at #170 (per-repository files are read
  filename-sorted). Values must not.
- The first run after #188 shifts `account_age_days`, `maturity_score` and
  `status` once, from "age today" to "age at capture".

## Merging the phase

1. Regeneration passes, or its failures are understood and attributed.
2. `verify_medallion.py` green, with `--self-test` green.
3. Full suite and `mypy` green **on the merged result**, not on the branch — two
   branches can each be green and their merge red.
4. Close by hand every issue whose `Closes` was spent on the phase branch. The
   running list lives as a comment on the phase epic. **Do not generate it from
   the commit log**: commits cite PR numbers, not issue numbers, so a
   `git log --grep` sweep misses work that shipped.

## Predictions

State what a run should produce **before** it runs, in a place that survives —
the issue, or the bus. It is the only way to tell a result that confirms
something from a result you explained afterwards.

And say which *quantity* you are predicting. A prediction about identity merging
is not a prediction about record counts, and stating one as the other produces a
wrong prediction from correct reasoning.
