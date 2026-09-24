#!/usr/bin/env python3
"""Verify a regenerated medallion: does each layer hold what it should?

Run this after a phase regeneration, before merging the phase to main.

    uv run python scripts/verify_medallion.py --root /var/tmp/coops-work

Why this exists
---------------
The regeneration script enforces that a defect was *present* before a run. It
did not check that the defect was *gone* afterwards. Three separate times its
comments described a post-check that had never been written, so a run could
print "ALL LAYERS CLEAN" on criteria — address counts, record totals — with
nothing to do with the reason it was started.

A check that has never failed proves nothing, so **every check here carries a
control**: a synthetic input it must reject. `--self-test` runs the controls
alone and is the only evidence that a green run means anything.

Exit codes
----------
    0  every check passed, every control fired
    1  a check failed — the layer does not hold an invariant
    2  a check could not run, or a control did NOT fire (the instrument is broken)

2 is not a weaker 1. "The probe found nothing" and "the probe cannot see" are
different answers and only the first is a pass.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

# NOTE: there is deliberately no address check here. The corpus is open data
# held under university and Brazilian ethics-committee approval with participant
# consent, and the owner has ruled that addresses in it are expected rather than
# a defect. A verifier asserting otherwise would fail every phase gate on a
# non-issue and keep dragging a settled question back open.

UNKNOWN_LABEL_BASELINE = 1

# What identifies a record, per family. Without commits and issue_events here,
# the vanished check saw only issues and prs — 44 of the 55 records actually
# lost — and the 11 missing commits were invisible to the check written to find
# them (curupira, #200).
RECORD_KEY = {"commits": "sha", "issues": "number", "prs": "number", "issue_events": "id"}

BRONZE_FAMILIES = ("commits", "prs", "issues", "issue_events", "structure", "repo")
AGGREGATES = tuple(f"{f}_all.json" for f in ("commits", "prs", "issues", "issue_events"))


@dataclass
class Result:
    name: str
    layer: str
    passed: bool
    detail: str
    control_fired: bool | None = None
    skipped: bool = False


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def add(self, r: Result) -> None:
        self.results.append(r)

    @property
    def exit_code(self) -> int:
        # A skipped check IS a check that could not run, which this script's own
        # docstring defines as 2. Returning 0 made the message honest and the
        # GATE wrong: a human reads the SKIP line, a CI reads the code (caught
        # by curupira on #200, after the message-only fix).
        if any(r.control_fired is False or r.skipped for r in self.results):
            return 2
        return 1 if any(not r.passed for r in self.results) else 0


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def read_records(path: Path) -> Iterator[dict]:
    """Yield the dict records of one artifact, metadata sidecars excluded."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(payload, dict):
        yield payload
        return
    if isinstance(payload, list):
        for rec in payload:
            if isinstance(rec, dict) and "_metadata" not in rec:
                yield rec


def bronze_family_files(bronze: Path, family: str) -> list[Path]:
    """Per-repository files of a family: aggregates and derived copies excluded.

    Mirrors `coops.bronze.files.bronze_records` deliberately rather than
    importing it — a verifier that shares its enumeration with the code under
    test cannot catch an enumeration bug.
    """
    skip = f"{family}_all.json"
    return sorted(
        p
        for p in bronze.glob(f"{family}_*.json")
        if p.name != skip and not p.stem.endswith("_with_stats")
    )


# --------------------------------------------------------------------------
# bronze
# --------------------------------------------------------------------------


def check_no_aggregates(bronze: Path, rep: Report) -> None:
    found = [a for a in AGGREGATES if (bronze / a).exists()]
    rep.add(
        Result(
            "aggregates-removed",
            "bronze",
            not found,
            "none present" if not found else f"still on disk: {', '.join(found)}",
        )
    )


def check_every_author_hashed(bronze: Path, rep: Report) -> None:
    """#101/#189: a commit author with an email carries a hash, linked or not.

    Before #189 the hash was kept only for unlinked authors, so the login space
    and the hash space never co-occurred and nothing downstream could learn that
    a hash and a login belonged to one person.
    """
    login_no_hash = total = with_login = 0
    for path in bronze_family_files(bronze, "commits"):
        for rec in read_records(path):
            author = (rec.get("commit") or {}).get("author") or {}
            total += 1
            if author.get("login"):
                with_login += 1
                if not author.get("author_email_hash"):
                    login_no_hash += 1
    if total == 0 or with_login == 0:
        rep.add(
            Result(
                "every-author-hashed",
                "bronze",
                False,
                f"cannot see the corpus: {total} commits, {with_login} with a login",
                control_fired=False,
            )
        )
        return
    rep.add(
        Result(
            "every-author-hashed",
            "bronze",
            login_no_hash == 0,
            f"{login_no_hash:,} of {with_login:,} logged-in commits lack a hash",
        )
    )



# --------------------------------------------------------------------------
# staleness — the only check here that needs two corpora
# --------------------------------------------------------------------------


def check_no_record_reverted(bronze: Path, reference: Path, rep: Report) -> None:
    """No record may come back as an OLDER version than the reference holds.

    Found by curupira and confirmed by matinta on #199: 38 records (35 issues,
    3 prs) survived a regeneration with their `updated_at` moved *backwards*.

    This is invisible to every other check in this file, by construction. A
    missing record trips a count; a reverted one keeps the count identical and
    the content wrong. Counts cannot see it, invariants cannot see it, and the
    totals agree while the data is stale.

    It needs a reference corpus because "older" is only meaningful against a
    previous state — which is why this check takes `--reference` and the others
    do not.
    """
    reverted: list[tuple[str, str, str]] = []
    vanished: list[str] = []
    compared = 0

    def index(root: Path, family: str, key: str) -> dict[tuple[str, object], str | None]:
        out: dict[tuple[str, object], str | None] = {}
        for path in bronze_family_files(root, family):
            repo = path.stem[len(family) + 1 :]
            for rec in read_records(path):
                ident = rec.get(key)
                if ident is not None:
                    upd = rec.get("updated_at")
                    out[(repo, ident)] = upd if isinstance(upd, str) else None
        return out

    for family, key in RECORD_KEY.items():
        new_ix, ref_ix = index(bronze, family, key), index(reference, family, key)
        shared = set(new_ix) & set(ref_ix)
        compared += len(shared)
        for k in shared:
            a, b = new_ix[k], ref_ix[k]
            if a is not None and b is not None and a < b:
                reverted.append((f"{family}:{k[0]}#{k[1]}", b, a))
        # Comparing only shared keys makes a VANISHED record invisible: it is
        # absent from new_ix, so it is never examined. That is the larger half
        # of #199, and the check written to find it could not see it.
        for k in set(ref_ix) - set(new_ix):
            vanished.append(f"{family}:{k[0]}#{k[1]}")

    # Nothing comparable means the probe could not see either corpus — a
    # different answer from "nothing was wrong", and it must not read as a pass.
    if compared == 0:
        rep.add(Result("no-record-reverted", "bronze", False,
                       "no records comparable between the two corpora",
                       control_fired=False))
        return

    detail = f"{compared:,} records compared, {len(reverted)} reverted"
    if reverted:
        k, was, now = reverted[0]
        detail += f" (e.g. {k}: {was} -> {now})"
    rep.add(Result("no-record-reverted", "bronze", not reverted, detail))
    rep.add(
        Result(
            "no-record-vanished",
            "bronze",
            not vanished,
            f"{len(vanished)} records present in the reference and absent now"
            + (f" (e.g. {vanished[0]})" if vanished else ""),
        )
    )


# --------------------------------------------------------------------------
# silver
# --------------------------------------------------------------------------


def check_member_ids_distinct(silver: Path, rep: Report) -> None:
    """Two members must never share an id: that is one person counted once."""
    path = silver / "members_statistics.json"
    if not path.exists():
        rep.add(Result("member-ids-distinct", "silver", False, "members_statistics.json absent", control_fired=False))
        return
    records = list(read_records(path))
    ids = [r.get("id") for r in records if r.get("id") is not None]
    if not ids:
        rep.add(Result("member-ids-distinct", "silver", False, "no member carries an id", control_fired=False))
        return
    dupes = len(ids) - len(set(ids))
    rep.add(Result("member-ids-distinct", "silver", dupes == 0, f"{len(ids):,} members, {dupes} duplicate ids"))

    # Filtering to records that HAVE an id made this check blind to the ones
    # that do not. A member with no id cannot be joined to anything downstream,
    # so it is a defect rather than a row to skip. Found because this check
    # reported 1,723 members while the label check reported 1,724 on the same
    # file in the same run — one record with no id, no name and no commits.
    idless = len(records) - len(ids)
    rep.add(
        Result(
            "every-member-identified",
            "silver",
            idless == 0,
            f"{len(records):,} member records, {idless} with no id",
        )
    )


def check_no_unknown_labels(silver: Path, rep: Report) -> None:
    """#151: nobody is displayed as 'Unknown contributor'.

    Showing that label cost 230 people their names and made the dashboard
    useless for the thing it exists to do.
    """
    path = silver / "members_statistics.json"
    if not path.exists():
        rep.add(Result("no-unknown-labels", "silver", False, "members_statistics.json absent", control_fired=False))
        return
    records = list(read_records(path))
    if not records:
        rep.add(Result("no-unknown-labels", "silver", False, "no member records", control_fired=False))
        return
    bad = [r for r in records if isinstance(r.get("name"), str) and r["name"].startswith("Unknown contributor")]
    # #151 took these from 231 to 1. The residual is a contributor every one of
    # whose commit names was itself an address, so after blanking there is
    # genuinely nothing to display. Asserting zero would fail forever and be
    # ignored; the invariant that matters is that the count does not GROW.
    rep.add(
        Result(
            "unknown-labels-not-growing",
            "silver",
            len(bad) <= UNKNOWN_LABEL_BASELINE,
            f"{len(records):,} members, {len(bad)} unknown-labelled "
            f"(baseline {UNKNOWN_LABEL_BASELINE}, set by #151)",
        )
    )


def check_hash_never_a_label(silver: Path, rep: Report) -> None:
    """A 64-hex identity may key a member; it must never be shown as their name."""
    path = silver / "members_statistics.json"
    if not path.exists():
        rep.add(Result("hash-never-a-label", "silver", False, "members_statistics.json absent", control_fired=False))
        return
    hexish = re.compile(r"^[0-9a-f]{64}$")
    records = list(read_records(path))
    if not records:
        rep.add(Result("hash-never-a-label", "silver", False, "no member records", control_fired=False))
        return
    bad = [r for r in records if isinstance(r.get("name"), str) and hexish.match(r["name"])]
    rep.add(Result("hash-never-a-label", "silver", not bad, f"{len(bad)} members displayed as a hash"))


# --------------------------------------------------------------------------
# controls — each check must reject a synthetic input it should reject
# --------------------------------------------------------------------------


def run_controls(tmp: Path) -> list[Result]:
    """Prove each check can fail. A check that has never failed protects nothing."""
    out: list[Result] = []

    bronze = tmp / "bronze"
    bronze.mkdir(parents=True, exist_ok=True)
    (bronze / "commits_all.json").write_text("[]", encoding="utf-8")
    r = Report()
    check_no_aggregates(bronze, r)
    out.append(Result("aggregates-removed", "control", not r.results[0].passed,
                      "rejects an aggregate on disk" if not r.results[0].passed else "DID NOT FIRE"))
    (bronze / "commits_all.json").unlink()

    (bronze / "commits_x.json").write_text(
        json.dumps([{"commit": {"author": {"login": "someone", "name": "S"}}}]), encoding="utf-8")
    r = Report()
    check_every_author_hashed(bronze, r)
    out.append(Result("every-author-hashed", "control", not r.results[0].passed,
                      "rejects a logged-in commit with no hash" if not r.results[0].passed else "DID NOT FIRE"))

    ref = tmp / "ref"
    ref.mkdir(parents=True, exist_ok=True)
    (ref / "issues_r.json").write_text(
        json.dumps([{"number": 1, "updated_at": "2026-09-23T18:00:00Z"}]), encoding="utf-8")
    (bronze / "issues_r.json").write_text(
        json.dumps([{"number": 1, "updated_at": "2026-09-01T00:00:00Z"}]), encoding="utf-8")
    r = Report()
    check_no_record_reverted(bronze, ref, r)
    out.append(Result("no-record-reverted", "control", not r.results[0].passed,
                      "rejects a record that moved backwards" if not r.results[0].passed else "DID NOT FIRE"))

    # A vanished COMMIT, keyed by sha — the family the first version of this
    # check did not index at all, so nothing proved it could fail.
    (ref / "commits_r.json").write_text(
        json.dumps([{"sha": "deadbeef", "commit": {"author": {"login": "x"}}}]), encoding="utf-8")
    (bronze / "commits_r.json").write_text(json.dumps([]), encoding="utf-8")
    r = Report()
    check_no_record_reverted(bronze, ref, r)
    vanish = next((x for x in r.results if x.name == "no-record-vanished"), None)
    out.append(Result("no-record-vanished", "control", bool(vanish and not vanish.passed),
                      "rejects a vanished commit" if vanish and not vanish.passed else "DID NOT FIRE"))

    silver = tmp / "silver"
    silver.mkdir(parents=True, exist_ok=True)
    (silver / "members_statistics.json").write_text(
        json.dumps([{"id": "a", "name": "Unknown contributor (x)"}, {"id": "a", "name": "Unknown contributor (y)"},
                    {"id": "b", "name": "0" * 64}, {"name": "nobody"}]), encoding="utf-8")
    r = Report()
    check_member_ids_distinct(silver, r)
    fired = any(not x.passed for x in r.results if x.name == "every-member-identified")
    out.append(Result("every-member-identified", "control", fired,
                      "rejects a member with no id" if fired else "DID NOT FIRE"))

    for fn, label in ((check_member_ids_distinct, "member-ids-distinct"),
                      (check_no_unknown_labels, "unknown-labels-not-growing"),
                      (check_hash_never_a_label, "hash-never-a-label")):
        r = Report()
        fn(silver, r)
        out.append(Result(label, "control", not r.results[0].passed,
                          "rejects the planted defect" if not r.results[0].passed else "DID NOT FIRE"))

    return out


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path("/var/tmp/coops-work"),
                    help="corpus root holding data/bronze, data/silver, data/gold")
    ap.add_argument("--reference", type=Path, default=None,
                    help="a previous corpus root; enables the staleness check, which "
                         "cannot run without one")
    ap.add_argument("--self-test", action="store_true",
                    help="run only the controls: prove every check can fail")
    args = ap.parse_args()

    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            results = run_controls(Path(td))
        width = max(len(r.name) for r in results)
        for r in results:
            print(f"  {'FIRED ' if r.passed else 'SILENT'}  {r.name:<{width}}  {r.detail}")
        silent = [r for r in results if not r.passed]
        print(f"\n  {len(results) - len(silent)} of {len(results)} controls fired")
        if silent:
            print("  A control that does not fire means the check cannot detect its own defect.")
            return 2
        return 0

    data = args.root / "data"
    if not data.is_dir():
        print(f"  no data/ under {args.root}", file=sys.stderr)
        return 2

    rep = Report()
    # A layer that is absent must not be skipped into a pass. Caught by curupira
    # on #200: with data/bronze missing, every bronze check was skipped and the
    # run printed "all checks passed". Absence of a layer is an instrument
    # problem (rc 2), not a clean result.
    for layer in ("bronze", "silver"):
        if not (data / layer).is_dir():
            rep.add(Result(f"{layer}-present", layer, False,
                           f"data/{layer} is absent — its checks did not run",
                           control_fired=False))
    if (data / "bronze").is_dir():
        check_no_aggregates(data / "bronze", rep)
        check_every_author_hashed(data / "bronze", rep)
        if args.reference:
            check_no_record_reverted(data / "bronze", args.reference / "data" / "bronze", rep)
        else:
            # Without a reference these cannot run — and saying nothing would
            # let a corpus with records lost or reverted print "all checks
            # passed". Raised twice by curupira on #200; the missing-layer case
            # had the same shape and only half of it was fixed.
            for name in ("no-record-reverted", "no-record-vanished"):
                rep.add(Result(name, "bronze", True,
                               "NOT RUN — needs --reference <previous corpus root>",
                               skipped=True))
    if (data / "silver").is_dir():
        check_member_ids_distinct(data / "silver", rep)
        check_no_unknown_labels(data / "silver", rep)
        check_hash_never_a_label(data / "silver", rep)

    if not rep.results:
        print("  no layers found to check", file=sys.stderr)
        return 2

    width = max(len(r.name) for r in rep.results)
    for r in rep.results:
        if r.skipped:
            status = "SKIP  "
        elif r.control_fired is False:
            status = "BROKEN"
        elif r.passed:
            status = "PASS  "
        else:
            status = "FAIL  "
        print(f"  {status}  {r.layer:<7} {r.name:<{width}}  {r.detail}")

    skipped = [r for r in rep.results if r.skipped]
    code = rep.exit_code
    print()
    if skipped and not any(not r.passed and not r.skipped for r in rep.results):
        print(f"  all checks that RAN passed — {len(skipped)} did not run "
              f"({', '.join(r.name for r in skipped)})")
        print("  A phase gate needs --reference: without it, records lost or")
        print("  reverted since the last run are invisible to this script.")
        return code   # 2 — not a pass
    print({0: "  all checks passed",
           1: "  a layer does not hold an invariant",
           2: "  a check could not run — the instrument is broken, not the data"}[code])
    if code == 0:
        print("  (run --self-test to confirm these checks can fail at all)")
    return code


if __name__ == "__main__":
    sys.exit(main())
