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
  shipped source — not a copy, not the whole suite at once. Removing everything
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
