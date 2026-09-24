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

BRONZE_FAMILIES = ("commits", "prs", "issues", "issue_events", "structure", "repo")
AGGREGATES = tuple(f"{f}_all.json" for f in ("commits", "prs", "issues", "issue_events"))


@dataclass
class Result:
    name: str
    layer: str
    passed: bool
    detail: str
    control_fired: bool | None = None


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def add(self, r: Result) -> None:
        self.results.append(r)

    @property
    def exit_code(self) -> int:
        if any(r.control_fired is False for r in self.results):
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
# silver
# --------------------------------------------------------------------------


def check_member_ids_distinct(silver: Path, rep: Report) -> None:
    """Two members must never share an id: that is one person counted once."""
    path = silver / "members_statistics.json"
    if not path.exists():
        rep.add(Result("member-ids-distinct", "silver", False, "members_statistics.json absent", control_fired=False))
        return
    ids = [r.get("id") for r in read_records(path) if r.get("id") is not None]
    if not ids:
        rep.add(Result("member-ids-distinct", "silver", False, "no member carries an id", control_fired=False))
        return
    dupes = len(ids) - len(set(ids))
    rep.add(Result("member-ids-distinct", "silver", dupes == 0, f"{len(ids):,} members, {dupes} duplicate ids"))


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

    silver = tmp / "silver"
    silver.mkdir(parents=True, exist_ok=True)
    (silver / "members_statistics.json").write_text(
        json.dumps([{"id": "a", "name": "Unknown contributor (x)"}, {"id": "a", "name": "Unknown contributor (y)"},
                    {"id": "b", "name": "0" * 64}]), encoding="utf-8")
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
    if (data / "bronze").is_dir():
        check_no_aggregates(data / "bronze", rep)
        check_every_author_hashed(data / "bronze", rep)
    if (data / "silver").is_dir():
        check_member_ids_distinct(data / "silver", rep)
        check_no_unknown_labels(data / "silver", rep)
        check_hash_never_a_label(data / "silver", rep)

    if not rep.results:
        print("  no layers found to check", file=sys.stderr)
        return 2

    width = max(len(r.name) for r in rep.results)
    for r in rep.results:
        if r.control_fired is False:
            status = "BROKEN"
        elif r.passed:
            status = "PASS  "
        else:
            status = "FAIL  "
        print(f"  {status}  {r.layer:<7} {r.name:<{width}}  {r.detail}")

    code = rep.exit_code
    print()
    print({0: "  all checks passed",
           1: "  a layer does not hold an invariant",
           2: "  a check could not run — the instrument is broken, not the data"}[code])
    if code == 0:
        print("  (run --self-test to confirm these checks can fail at all)")
    return code


if __name__ == "__main__":
    sys.exit(main())
