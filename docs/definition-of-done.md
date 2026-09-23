# Definition of Done

What "done" means for a change in this repository. It is referenced by
`.opencode/agents/reviewer.md`, `.opencode/agents/tester.md`, `AGENTS.md` and the
pull request template, so that one standard is enforced everywhere rather than
re-argued per PR.

Reviewers enforce this. A change that misses it is *merge after fixes*, not
"approve with a note".

## Every change

- **Unit tests for the behaviour you changed.** Not for the paths that already
  worked. If you cannot name the regression a test would catch, you have not
  found the behaviour yet.
- **The suite passes, and you quote the counts** — `N passed, M skipped` — not
  the word "passes". See *Read the count, not the verdict* below.
- **Lint, format and type-check pass.** `ruff` for Python; `npm run lint`,
  `npm run format:check` and `tsc -b` for the dashboard. Run them locally; do
  not discover it in CI.
- **`CHANGELOG.md` updated** under `[Unreleased]` for anything user-visible,
  including a changed data shape — a new or removed field changes what the
  dashboard sees on the next run.
- **No new personal data reaches a published artifact.** Grep the *output*, not
  the code: a sweep for field names never finds an address sitting inside free
  text.
- **A projection that crosses a publish boundary selects the fields it uses.**
  Never spread a provider response and subtract (`{**issue}` minus a denylist):
  a whitelist is bounded by what we use, a denylist by what we have *noticed*.
  This applies to what gets published — **not** to the raw tier, which
  deliberately keeps what the provider sent.
- **A new field or output has a named consumer**, or an issue saying when it
  gets one. A value nothing reads is untested by construction: its tests assert
  that the writer ran, not that anything depends on the result.

## When the change crosses a boundary

- **Integration tests** wherever the change spans extraction ↔ store, API ↔
  database, or layer ↔ layer, and one can be written without a live third party.
  Fake at the boundary — replace the port, let the code under test run for real.
  Patching internal functions freezes the implementation and blocks refactoring.
- **Run it against something real** when it touches extraction, storage or
  serving: the smallest slice that exercises the path, from a scratch directory,
  and report the numbers you saw with a command anyone can repeat.
- **A workflow change is demonstrated, not reasoned about.** Run it (`gh act`,
  see [local-actions.md](local-actions.md)) against a tree where the step
  actually does its work. A shell step that stages nothing still exits 0, and
  `|| echo` turns a failure into a green job.

## Added as the capability lands

- **Contract tests** between the dashboard and the serving API once that API
  exists (#44). The shape is asserted from one source so the two cannot drift.
- **End-to-end tests** in a real browser once the dashboard runs on its own
  server (#62).
- **Performance budgets** once routes are split (#122) — an initial bundle size
  that fails the build when exceeded, so a regression is caught on the PR that
  causes it rather than months later.

## Why a denylist is not a sanitizer

**Scope first, because the two tiers want opposite things.** The raw tier keeps
the provider's response intact — including the personal fields — because it is
private, and because an address there is sometimes the only identifier a person
has (measured: 5.8% of commit authors have no account link). Stripping at
capture destroys attribution that cannot be recovered. That decision is #107 and
this section does not touch it.

What follows applies to a **projection that crosses a publish boundary**:
`data/bronze/` in fork-and-forget mode, the serving API's responses, and
published fixtures. Raw keeps; the projection selects.

Measured on this project, not asserted:

| Module | Approach | Outcome |
|---|---|---|
| `members.py` | explicit `PROFILE_FIELDS` whitelist | clean since it was written |
| issue events | explicit field selection | clean |
| `commits.py` | denylist + regex | three rounds — `email` keys, then `commit.verification`, then message trailers — and `author.name` still leaks |
| `issues.py` | `{**raw_object}` | everything the provider sends, including fields nobody has read |

Two facts make the denylist approach structurally unsound here:

1. **The leaking fields differ per organization.** In one org the addresses sat
   in `body` *and* `milestone.description`; in another, `body` only. They depend
   on what people typed and which optional provider fields happened to be
   populated — so the denylist you validated is not the denylist you deploy.
2. **Free text is not a field you can enumerate.** An address inside a commit
   message, a signature payload, an issue body or a display name is invisible to
   any sweep over key *names*. Three of this project's four leak channels were
   free text.

So when a published artifact is built from a provider response, the record is
constructed from named fields. Anything else is a promise to keep noticing.

## A test must be able to fail

This is the rule most often broken here, and the most expensive, because a test
that cannot fail costs runtime and buys false confidence.

- **Mutate per guard.** Delete or invert **each guard individually**, against the
  shipped source — not a copy, and not every guard at once. Mutating everything
  at once tells you the suite is not empty; it tells you nothing about any single
  guard.
- **Record which named tests fail**, never how many.
- A guard that can be removed with everything still green is undefended — *even
  when the code it guards is correct*. Correct-but-unguarded is not safe, it is
  safe-until-someone-refactors.
- A test's own fixtures can shadow the guard under test. If two guards can both
  answer a case, that case proves neither.

**Never adjust production code to make a test pass.** Fixing a bug the test
exposed is right, and you say so. Quietly changing the code until the assertion
goes green destroys the only signal the test carried.

## Read the count, not the verdict

`N passed` is meaningful only against the N you expected. A suite that stops
being collected — a mangled `describe`, a file renamed out of the glob, a test
file with its assertions removed — reports as **success**, with no error and no
warning. Read the suite count as well as the test count, and quote both, so the
next person can check them.

The same trap in general form: **absence is the dangerous answer.** A check that
finds nothing has not passed, it has told you nothing, until you have shown it
can find the thing. Before trusting an empty result, run the check against
something you know contains what you are looking for.

## A guard is proven by what did *not* happen

When a change makes something **fail closed**, the test must assert that the
guarded action **never occurred** — not merely that an error was raised. These
are different claims, and only the first one is the guarantee.

Measured on #129/#139: the dashboard fell back to a hardcoded organization when
`VITE_GITHUB_ORG` was unset, fetching one organization's data and presenting it
as another's. The fix fails closed, and the test that proves it asserts **no
request is issued**:

> `fails closed without VITE_GITHUB_ORG: NO FETCH`

A weaker test — "an error is surfaced" — would pass against an implementation
that fetched the data *and then* reported an error. That implementation still
transmits the request, still reaches the third party, still leaks whatever the
request carries. It would be a privacy hole wearing a correct error message,
and every assertion about it would be green.

So for any guard whose purpose is that something must not happen:

- Assert on the **absence of the effect** — the call not made, the file not
  written, the record not stored — using a spy, a mock that raises, or a
  transport that fails loudly if touched.
- A mock that returns empty is not enough. Returning nothing is
  indistinguishable from a legitimate empty result, so the test passes with the
  guard deleted.
- Then mutate: remove the guard and confirm **that named test** goes red.

### Prove the mutation landed before you trust its result

The mutation is an instrument, and it breaks the same way every other
instrument here breaks — quietly, reporting success.

Measured during #139's gate: a re-mutation of the `dataSource` guard reported
**18 passed**, which reads as *the guard survived removal* — an alarming and
completely false finding. The mutation had silently not applied: the pattern
targeted a constant assignment that did not exist on that head, where the guard
is a `throw`. A `sed` that matches nothing exits 0 and prints nothing. It was
caught only because it contradicted an earlier run — that is luck, not process.

So: **make the mutation fail loudly when it does not apply**, before running
the suite. A mutation that did not change the file is not a test of anything,
and its green result means the guard is undefended when in fact the guard was
never touched.

```sh
cp "$F" "$F.orig"
sed -i 's/<guard>/<broken>/' "$F"
cmp -s "$F.orig" "$F" && { echo "MUTATION DID NOT APPLY: $F"; exit 1; }
```

**And a green result still proves nothing until something goes red.** The
`cmp` check above confirms the mutation *applied*; it cannot tell you that you
ran the tests that would *catch* it. Measured two hours after this rule landed:
a mutation was applied correctly, `cmp` confirmed it, the run reported **8
passed** — and the guard looked undefended. The tests had been run from
`test_bronze_incremental.py` while the covering test lived in
`test_bronze_issues_projection.py`. Right mutation, wrong scope, green either
way.

So after mutating, **at least one test must fail somewhere**. Zero failures
across the run means the procedure is wrong before it means the guard is
missing — you are looking in the wrong place. Run the mutation against the
**every test in the project** rather than a chosen file: it is the one scope
that cannot be wrong, and it is the only way to distinguish *"nothing covers this"* from
*"nothing I ran covers this"*. Then name the test that went red.

**Printing the diff is not enough.** The failure being guarded against is a
person not noticing an absence — so a check whose output a tired reviewer
scrolls past has the same failure mode as the bug. The check must `exit 1`.

This document got that wrong on its first pass: it said *print the diff*, in the
section about instruments that fail quietly, one paragraph after the rule that a
control must be able to fail. The weak form is the easy one to write; that is
why it needs naming.

Related, when re-verifying a rebased or reworked change: an **identical patch is
not an identical result**. `git range-diff` showing `=` proves the diff replayed
unchanged; it says nothing about how that diff behaves against a base that
moved. Re-run the suite on the new head rather than inferring from the marker.

## Precedence needs two things present at once

A property test that generates each input kind **in isolation** can never find a
precedence bug, because precedence only exists when two kinds are present
together.

Measured on #146/#151. The identity fallback is `login -> author_email_hash ->
name`. A property check ran 500 synthetic hashes and several logins, and
confirmed exactly what it asked: every output unique, none empty, no shared
constant. All true. It generated no identity carrying **both** a hash and a real
name — the only shape where the ordering is observable. The chain shipped with
the hash outranking the name, and **230 contributors with perfectly good names
rendered as `Unknown contributor (a1b2c3d4)`** on the dashboard.

Measuring that impact took two attempts, which is its own lesson. The first
figure was 206, counted as the distinct name *strings* that disappeared. The
real number is **per identity**: 38 people carry more than one spelling of their
own name (`Druval Carvalho` / `Durval Carvalho`), so string-counting undercounts.
Count the entities affected, not the values that changed.

So when the code under test picks between alternatives, the fixture space has to
include the **combinations**, not just the members:

- For an `a or b or c` chain, test `a+b`, `b+c`, `a+c` and `a+b+c` — not only
  `a`, `b`, `c` alone. Each pair asserts which one wins.
- Say the winner out loud in the test name: `test_name_beats_hash_when_both_present`.
- Mutate by **swapping adjacent branches**, not by deleting one. Deleting a
  branch tests that the branch exists; swapping tests that the order is right,
  and only the second is the claim the code is making.

## A data migration needs two assertions, not one

When a change rewrites stored data, *"nothing was lost"* and *"nothing changed
that should not have"* are **different claims**, and a row count only makes the
first.

The regeneration behind #132 was gated on exactly that: addresses must reach
zero, and record counts must not fall. Both passed — addresses went 149 -> 0 and
`members_statistics.json` **grew** from 1,699 to 1,723 rows. Underneath, 230
identities kept their place and lost their name. Every criterion was green.

For a migration, assert on both axes:

- **Removal**: the thing being removed reaches zero, with a control proving the
  probe can still find it.
- **Preservation**: the values that were *not* the target are unchanged. Diff the
  old and new artifacts by key, and account for **every** difference — each one
  is either intended and explainable, or a defect. A delta you cannot name is
  not a rounding error.
- **Counts are the weakest of the three.** They catch deletion and nothing else.
  Here the count moved in the *reassuring* direction while the damage happened.

**An unexplained row *gain* is a finding, exactly like an unexplained loss.** The
+24 above read as "24 contributors rescued from being dropped". Decomposed
against the retained pre-migration file, it is two movements that happen to
nearly cancel:

```
+231  rows gained that carry a hash label
-207  rows lost that carried a plain name
----
 +24  net
```

231 identities now occupy 231 rows where 207 rows held them before — **24 merges
undone**. The old key was the name, and 16 name strings were each shared by
several distinct people (`CI/CD Bot` was six of them, `root` five). Nobody asked
where the extra rows came from, because rows appearing feels like a fix.
Explaining them is what revealed that the obvious repair — putting the name back
above the hash — would silently re-merge those people.

Note the shape of that decomposition: a net of +24 concealing movements of 231
and 207. **A small net delta is not evidence of a small change.** Two large
opposite movements are the normal case, not the exotic one, so decompose before
concluding anything from a total — and keep a copy of the pre-migration artifact,
because without it none of this is checkable after the fact.

## A two-arm comparison needs proof that the arms differ

A control proves the instrument can **see**. An arms-differ assert proves the
comparison can **discriminate**. Those are different properties, and only the
first was written down here — which is why two broken comparisons got through
on the same day.

Identical arms produce a clean, confident, symmetric result, and report it as a
finding.

Measured 2026-09-23, on a question about whether `main` blanks an
address-shaped `commit.author.name`. Two comparisons, two confident answers,
opposite conclusions:

- One imported the module from the **working tree** for both arms. `git
  checkout` does not move an already-importable package, so it tested `main`
  twice and reported the result as main-vs-phase.
- The other's end-to-end evidence — *4,068 raw cache files carry an address,
  zero Bronze files do* — was measured against a Bronze tree **regenerated
  hours earlier by the fix under test.** Correct probe, wrong subject.

So, before comparing:

```python
import hashlib, inspect
a = hashlib.sha256(inspect.getsource(inspect.getmodule(fn_a)).encode()).hexdigest()[:12]
b = hashlib.sha256(inspect.getsource(inspect.getmodule(fn_b)).encode()).hexdigest()[:12]
assert a != b, f"both arms resolve to the same module ({a})"
print(f"arm A {a}   arm B {b}")
```

**Hash the module, not the function.** A behavioural difference often lives in a
*callee*, which `inspect.getsource(fn)` does not capture — so a function-level
digest can match while the arms genuinely differ, and the assert then blocks a
valid comparison. In the case above, `_sanitize_commit` did differ between the
two branches (66 lines against 83), but the helper it gained, `_is_address`, is
**absent entirely** on one side: exactly the shape a caller-only hash would miss
had the call site been unchanged.

Print both digests, do not merely assert. And state the **provenance of the
data**: an artifact rewritten by the code under test is not evidence about that
code, however carefully it is then measured.

This failure recurred **three times in one session**, twice of them *while the
rule against it was being written* — once producing the original wrong answer,
once producing a review verdict on the very PR adding this section. Each time
the working tree happened to sit on one of the two branches, so an import
resolved to it and the other arm was read from a blob. Nobody was careless; the
mistake is invisible by construction, which is the whole argument for spending
two lines on the assert rather than remembering.

**When a comparison is contested, drop to one record.** Three exchanges of
disputed aggregates were ended by a single hand-built input, one call, and the
before and after printed. A count invites a reconciliation; an artifact does not.

## Tests that do not count

- Assertions on log text or printed output.
- `try/except` that turns a failure into a skip. If a dependency is genuinely
  unavailable, skip on that condition explicitly, naming it.
- Anything that reads or writes the working directory. A test whose result
  depends on whether `data/` happens to exist in the checkout is a bug in the
  test.
- Fixtures that assert what the code just did.
- A floor chosen so low it cannot be breached. Assertions grow, so a lagging
  floor is fine; files do not, so pin their real number.
