#!/usr/bin/env python3
"""A per-file regression gate: BASE vs HEAD, under ruff and mypy.

    uv run python scripts/check_regressions.py --base <ref> [--head <ref>]
    uv run python scripts/check_regressions.py --self-test

Why this exists
---------------
Phase 1 shipped to main believing it was clean. Measured afterwards, it had
added +69 ruff findings in files that already existed at the base commit and
+37 mypy errors in 7 pre-existing files. Both were invisible to the checks
that "passed":

* ruff was not configured, pinned or run anywhere — every "lint passes"
  claim used whichever ruff happened to be on PATH, or none. It is now
  pinned in the dev group and behaviour-pinned in ``[tool.ruff]``.
* "mypy clean" meant 21 of 62 files: pyproject.toml scopes mypy to
  domain/github/storage, so a regression in bronze/ or silver/ is invisible
  by construction — bronze/issues.py went 0 → 10 with no configured run
  ever seeing it.

An aggregate total cannot detect this. Phase 1's net mypy count *fell*
236 → 139 while seven files got worse; overall ruff density *improved*
37.9 → 25.4 findings per 1k lines. Both statements are true and both hide
the regression. Only a per-file comparison answers the question being asked.

What gates — read this before "fixing" this script
--------------------------------------------------
Only the DELTA between base and head, per file:

* (a) a file that existed at base has MORE findings at head → regression
* (b) a file that is NEW at head and has ANY finding → regression

Absolute counts are NOT gated and must stay ungated. The pre-ports layers
carry hundreds of findings today and that is fine: they are pre-existing
debt, and separate work pays it down. A gate that asserted zero could never
be introduced and could never merge Phase 2. If the totals below look
large, that is the instrument reporting honestly, not a finding.

How each tool is run
--------------------
* ruff: ``ruff check --no-cache --output-format json src tests`` — the same
  check a developer runs, with the pinned dev-group version; the JSON flag
  changes the output format, not one finding. ruff reads each arm's own
  pyproject.toml, exactly as it would in that tree.
* mypy: ``mypy --config-file /dev/null src/coops`` — deliberately ignoring
  pyproject.toml's [tool.mypy] scope, because that scope is exactly what
  hid the Phase 1 regressions. The configured scope is still correct for
  CI's own strict run over the Phase-1 port boundary; this gate is a
  different instrument asking a different question — "did any file get
  worse?" — and a scoped answer to that question is a wrong answer.

Both arms of every comparison use the SAME tool binaries, resolved from the
project venv (which is where the ruff pin lives — run this via ``uv run``),
so a tool change can never masquerade as a code change.

Each ref is materialized with ``git archive`` into a temporary directory —
never a clone, never a worktree, never a checkout (this environment is
disk-fenced) — and the pipeline is never run: ``data/`` is neither read nor
written.

Exit codes
----------
    0  no regression
    1  a file regressed (they are named above)
    2  the gate could not run — a tool missing, a ref unresolvable, a tool
       crashing

2 is not a weaker 1. "The gate found nothing" and "the gate cannot see"
are different answers, and only the first is a pass.

--self-test
-----------
A gate that cannot fail is decorative, so ``--self-test`` proves this one
can, with four controls — each must FIRE, and a control that does not fire
is itself a failure (exit 2):

1. plants one type error in src/coops/bronze/issues.py, a file the
   configured mypy scope EXCLUDES — the exact Phase 1 blind spot. The
   configured scope must not report it; the gate must fail on it.
2. plants findings in a NEW file → fails under rule (b).
3. an unchanged tree (two independent extractions of the same ref) →
   passes. Without this, a gate that fails on everything satisfies 1 and 2
   and blocks every PR.
4. a file that gets BETTER (fewer findings at head) → passes, and is not
   reported as a regression.

The tool binaries can be overridden with COOPS_REGRESSION_RUFF and
COOPS_REGRESSION_MYPY (used by the unit tests to substitute deterministic
fakes). Everything else should run through ``uv run``.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Exactly what the two instruments need is extracted from each ref: src/ and
# tests/ are what ruff checks, and pyproject.toml is included so ruff
# resolves the same requires-python inside an arm as outside it. Nothing
# else — not data/, not dashboard/ — is touched.
ARCHIVE_PATHS = ("src", "tests", "pyproject.toml")

RUFF_TARGETS = ("src", "tests")
MYPY_TARGET = "src/coops"

# See "How each tool is run" above: the missing config is the point, not an
# oversight. --no-error-summary only drops a line the parser ignores.
MYPY_ARGS = ("--config-file", "/dev/null", "--no-error-summary", MYPY_TARGET)

# mypy error lines look like
#   src/coops/bronze/issues.py:41: error: ...  [assignment]
# optionally with a column. `note:` and summary lines must not match.
_MYPY_ERROR_LINE = re.compile(r"^(?P<path>[^:\s]+):(?P<line>\d+)(?::\d+)?: error: ")

# Self-test plants. ctl 1 is the Phase 1 blind spot verbatim: a type error
# in a file the configured mypy scope excludes, chosen because the real
# issues.py went 0 → 10 unnoticed. The annotation-only plant produces no
# ruff finding, isolating the control to mypy.
CTL1_FILE = "src/coops/bronze/issues.py"
CTL1_PLANT = """

# --- check_regressions.py self-test, control 1: one type error in a file
# the configured mypy scope excludes. Only the config-free run can see it.
_selftest_secret: int = "phase one was believed clean"
"""

CTL2_FILE = "src/coops/bronze/selftest_planted_module.py"
CTL2_CONTENT = '''"""check_regressions.py self-test, control 2: a NEW file with findings."""

import os  # planted ruff F401: unused import

_selftest_value: int = "not an int"  # planted mypy: incompatible assignment
'''

# ctl 4 plants findings only the BASE arm carries, so the file gets BETTER
# at head — under both tools, to prove neither reports an improvement as a
# regression.
CTL4_PLANT = """

# --- check_regressions.py self-test, control 4: findings only the base arm
# carries. This file improves at head and must not be named as a regression.
import json as _selftest_json  # planted ruff F401: unused import
_selftest_better: int = "not an int"  # planted mypy: incompatible assignment
"""


class GateError(Exception):
    """The gate could not run. Exit 2 — never a pass."""


# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise GateError(f"could not execute {cmd[0]}: {exc}") from exc


def _git(repo: Path, args: list[str]) -> str:
    proc = _run(["git", *args], repo)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        hint = detail[0] if detail else f"git exited {proc.returncode}"
        raise GateError(f"git {' '.join(args)}: {hint}")
    return proc.stdout


def resolve_tool(name: str, env_var: str) -> str:
    """Find a tool binary: explicit override, then the venv, then PATH.

    The venv comes first in practice because the script runs under
    ``uv run``: sys.executable is the project venv's python and the ruff pin
    in the dev group is what sits next to it. An override that does not
    exist is a broken instrument, not a pass.
    """
    override = os.environ.get(env_var)
    if override:
        if Path(override).is_file():
            return override
        raise GateError(f"{env_var}={override} does not exist — {name} unavailable")
    sibling = Path(sys.executable).parent / name
    if sibling.is_file():
        return str(sibling)
    found = shutil.which(name)
    if found:
        return found
    raise GateError(
        f"{name} not found next to {sys.executable} or on PATH — run this script via `uv run`"
    )


def tool_version(binpath: str) -> str:
    proc = _run([binpath, "--version"], Path.cwd())
    if proc.returncode != 0:
        raise GateError(f"{binpath} --version exited {proc.returncode}")
    return (
        (proc.stdout or "").strip().splitlines()[0]
        if proc.stdout.strip()
        else f"{binpath} (version unknown)"
    )


def materialize(repo: Path, ref: str, dest: Path) -> str:
    """Extract `ref` (src, tests, pyproject.toml only) into `dest`.

    git archive reads the object database without a checkout; the working
    tree — and data/ inside it — is never touched.
    """
    resolved = _git(repo, ["rev-parse", "--verify", f"{ref}^{{commit}}"]).strip()
    tar_bytes = _git_bytes(repo, ["archive", "--format=tar", resolved, "--", *ARCHIVE_PATHS])
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:  # Python < 3.12 has no `filter`
            tar.extractall(dest)
    return resolved


def _git_bytes(repo: Path, args: list[str]) -> bytes:
    try:
        proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
    except OSError as exc:
        raise GateError(f"could not execute git: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="replace").strip().splitlines()
        hint = detail[0] if detail else f"git exited {proc.returncode}"
        raise GateError(f"git {' '.join(args)}: {hint}")
    return proc.stdout


# --------------------------------------------------------------------------
# the two instruments, one Counter per arm
# --------------------------------------------------------------------------


def _relativize(path: str, arm: Path) -> str:
    """Make a finding's path arm-relative.

    ruff 0.16 emits absolute filenames (its cwd is the arm); older releases
    emitted them relative. Base and head arms live in different temporary
    directories, so counting by the raw string would make every file at head
    look new — relativize before counting, or rule (b) fires on everything.
    """
    candidate = Path(path)
    if candidate.is_absolute():
        for root in (arm.resolve(), arm):
            try:
                candidate = candidate.relative_to(root)
                break
            except ValueError:
                continue
    return candidate.as_posix()


def ruff_per_file(ruff_bin: str, arm: Path) -> Counter[str]:
    """Findings per file, read with a rule set the measured tree cannot change.

    ``--isolated`` ignores every configuration file, and it is not optional.
    Without it ruff reads **each arm's own** ``[tool.ruff]``, so a change that
    narrows ``select`` shrinks the head arm's findings — and a real regression
    committed alongside that narrowing is hidden inside the shrink. The gate
    then certifies that nothing got worse because it was told to stop looking.
    Found by @curupira on #221 against the first version of this script.

    This is the symmetric treatment to mypy's ``--config-file /dev/null``
    below, for the same reason: **an instrument whose sensitivity is set by the
    thing it measures is not an instrument.** The repo's ``[tool.ruff]`` is
    still right for CI's own ``ruff check``; this is a different question,
    asked with a fixed rule set so the two arms are comparable at all.

    Consequence worth knowing: counts here are ruff's **defaults**, not the
    repo's configured set, so they will not match ``ruff check`` run by hand.
    That is intended — only the per-file delta between arms is meaningful.
    """
    targets = [t for t in RUFF_TARGETS if (arm / t).exists()]
    if "src" not in targets:
        raise GateError(f"no src/ in the extracted tree at {arm} — ruff has nothing to check")
    proc = _run(
        [ruff_bin, "check", "--isolated", "--no-cache", "--output-format", "json", *targets],
        arm,
    )
    if proc.returncode not in (0, 1):
        raise GateError(
            f"ruff exited {proc.returncode} in {arm}: {(proc.stderr or proc.stdout).strip()[:300]}"
        )
    try:
        findings = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise GateError(f"ruff output was not JSON: {exc}") from exc
    counts: Counter[str] = Counter()
    for item in findings:
        # `path` in some ruff releases, `filename` in others — accept both so
        # a bump degrades at the version pin, not silently here.
        path = item.get("path") or item.get("filename")
        if path:
            counts[_relativize(path, arm)] += 1
    return counts


def _count_mypy_lines(text: str) -> Counter[str]:
    """Count mypy `.../file.py:LINE[:COL]: error:` lines per file.

    `note:` lines, the config warning and the summary line do not match —
    only attributed errors count.
    """
    counts: Counter[str] = Counter()
    for line in text.splitlines():
        match = _MYPY_ERROR_LINE.match(line)
        if match:
            counts[Path(match.group("path")).as_posix()] += 1
    return counts


def mypy_per_file(mypy_bin: str, arm: Path) -> Counter[str]:
    if not (arm / MYPY_TARGET).is_dir():
        raise GateError(
            f"no {MYPY_TARGET}/ in the extracted tree at {arm} — mypy has nothing to check"
        )
    proc = _run([mypy_bin, *MYPY_ARGS], arm)
    if proc.returncode == 2:
        raise GateError(f"mypy crashed in {arm}: {(proc.stderr or proc.stdout).strip()[:300]}")
    if proc.returncode not in (0, 1):
        raise GateError(
            f"mypy exited {proc.returncode} in {arm}: {(proc.stderr or proc.stdout).strip()[:300]}"
        )
    return _count_mypy_lines(proc.stdout or "")


def run_both(ruff_bin: str, mypy_bin: str, arm: Path) -> dict[str, ArmReading]:
    return {
        "ruff": ArmReading(ruff_per_file(ruff_bin, arm), _python_files(arm, RUFF_TARGETS)),
        "mypy": ArmReading(mypy_per_file(mypy_bin, arm), _python_files(arm, (MYPY_TARGET,))),
    }


@dataclass
class ArmReading:
    """One arm seen by one tool: per-file finding counts, and the file set.

    The file set matters as much as the counts: a Counter cannot tell a file
    that existed with zero findings from a file that did not exist, and the
    difference is exactly rules (a) vs (b) — github_api.py carried 0 ruff
    findings at the Phase 1 base and +19 at head, which is a REGRESSION in a
    pre-existing file, not a new file.
    """

    counts: Counter[str]
    files: set[str]


def _python_files(arm: Path, roots: tuple[str, ...]) -> set[str]:
    files: set[str] = set()
    for rel in roots:
        root = arm / rel
        if root.is_dir():
            for path in root.rglob("*.py"):
                files.add(path.relative_to(arm).as_posix())
    return files


# --------------------------------------------------------------------------
# the gate: per-file deltas only
# --------------------------------------------------------------------------


@dataclass
class ToolDelta:
    tool: str
    base_total: int
    head_total: int
    regressed: list[tuple[str, int, int]] = field(default_factory=list)  # rule (a)
    new_with_findings: list[tuple[str, int]] = field(default_factory=list)  # rule (b)
    improved: list[tuple[str, int, int]] = field(default_factory=list)  # not gated

    @property
    def ok(self) -> bool:
        return not self.regressed and not self.new_with_findings


def compare_tool(tool: str, base: ArmReading, head: ArmReading) -> ToolDelta:
    """Rules (a) and (b), and nothing else. Improvements never gate.

    Existence comes from the file sets, so a pre-existing file with zero
    findings that gains one is rule (a) — not a phantom "new file".
    """
    delta = ToolDelta(
        tool=tool, base_total=sum(base.counts.values()), head_total=sum(head.counts.values())
    )
    for path in sorted(base.files & head.files):
        base_count = base.counts.get(path, 0)
        head_count = head.counts.get(path, 0)
        if head_count > base_count:
            delta.regressed.append((path, base_count, head_count))  # rule (a)
        elif head_count < base_count:
            delta.improved.append((path, base_count, head_count))
    for path, head_count in sorted(head.counts.items()):
        if path not in base.files and head_count > 0:
            delta.new_with_findings.append((path, head_count))  # rule (b)
    return delta


def render(reports: list[ToolDelta]) -> list[str]:
    lines: list[str] = []
    for report in reports:
        lines.append(
            f"{report.tool}: {report.base_total} → {report.head_total} findings in total"
            f" (totals are context, never gated)"
        )
        for path, base, head in report.regressed:
            lines.append(f"  REGRESSED        {path}: {base} → {head} (+{head - base})")
        for path, head in report.new_with_findings:
            lines.append(f"  NEW WITH FINDINGS {path}: new at head, {head} finding(s)")
        if report.improved:
            lines.append(
                f"  ({len(report.improved)} file(s) improved at head — not gated, not a regression)"
            )
        if report.ok:
            lines.append("  no per-file regression")
    return lines


def compare_arms(
    base_readings: dict[str, ArmReading], head_readings: dict[str, ArmReading]
) -> list[ToolDelta]:
    return [
        compare_tool(tool, base_readings[tool], head_readings[tool]) for tool in ("ruff", "mypy")
    ]


def verdict(reports: list[ToolDelta]) -> tuple[int, str]:
    regressed = sum(len(r.regressed) for r in reports)
    new_bad = sum(len(r.new_with_findings) for r in reports)
    if regressed or new_bad:
        return 1, (
            f"GATE: FAIL — {regressed} file(s) regressed, {new_bad} new file(s) with findings"
        )
    return 0, (
        "GATE: PASS — no file got worse (only per-file deltas gate; absolute counts are not gated)"
    )


# --------------------------------------------------------------------------
# --self-test: prove the gate can fail
# --------------------------------------------------------------------------


def _copy_arm(src: Path, dest: Path) -> Path:
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".mypy_cache", ".ruff_cache"))
    return dest


def _plant(arm: Path, rel_path: str, text: str) -> None:
    target = arm / rel_path
    target.write_text(target.read_text() + text, encoding="utf-8")


def _named(reports: list[ToolDelta], rel_path: str) -> bool:
    return any(rel_path in line for line in render(reports))


def _mypy_configured_scope_counts(mypy_bin: str, arm: Path) -> Counter[str]:
    """mypy the way CI runs it: cwd inside the arm, pyproject scope applies.

    Bare `mypy` discovers arm/pyproject.toml, whose [tool.mypy] scopes the
    run to the port boundary and excludes bronze/ — the blind spot, shown
    from the other side.
    """
    proc = _run([mypy_bin], arm)
    if proc.returncode == 2:
        raise GateError(f"configured-scope mypy crashed: {(proc.stderr or '').strip()[:300]}")
    return _count_mypy_lines(proc.stdout or "")


def run_self_test(repo: Path, ruff_bin: str, mypy_bin: str) -> int:
    print(
        f"self-test on {repo} @ HEAD — each control must FIRE; "
        f"a control that does not fire is a failure"
    )
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str) -> None:
        print(f"  [{'FIRED ' if ok else 'FAILED'}] {label}: {detail}")
        if not ok:
            failures.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory(prefix="coops-gate-selftest-") as tmp:
        tmpdir = Path(tmp)
        print("  extracting HEAD twice and running both tools on each arm…")
        arm_a = tmpdir / "arm-a"
        arm_b = tmpdir / "arm-b"
        materialize(repo, "HEAD", arm_a)
        materialize(repo, "HEAD", arm_b)
        counts_a = run_both(ruff_bin, mypy_bin, arm_a)
        counts_b = run_both(ruff_bin, mypy_bin, arm_b)

        print(
            f"control 1 — planted type error in scope-excluded {CTL1_FILE} (the Phase 1 blind spot)"
        )
        mut1 = _copy_arm(arm_a, tmpdir / "ctl1")
        _plant(mut1, CTL1_FILE, CTL1_PLANT)
        counts_1 = run_both(ruff_bin, mypy_bin, mut1)
        reports_1 = compare_arms(counts_a, counts_1)
        base_mypy = counts_a["mypy"].counts.get(CTL1_FILE, 0)
        head_mypy = counts_1["mypy"].counts.get(CTL1_FILE, 0)
        # the mutation must land — otherwise the control below is vacuous
        check(
            "mutation landed (config-free mypy sees it)",
            head_mypy > base_mypy,
            f"{CTL1_FILE}: {base_mypy} → {head_mypy}",
        )
        # the configured scope must NOT see it — that is the blind spot
        scoped = _mypy_configured_scope_counts(mypy_bin, mut1)
        check(
            "configured mypy scope does not report the file",
            CTL1_FILE not in scoped,
            f"{CTL1_FILE} in configured-scope output: {scoped.get(CTL1_FILE, 0)} error(s)",
        )
        # and the gate must fail on it anyway, naming it under mypy only
        code1, _ = verdict(reports_1)
        ruff_regressed_itself = any(
            p == CTL1_FILE for p, _, _ in next(r for r in reports_1 if r.tool == "ruff").regressed
        )
        check(
            "gate fails and names it under mypy (rule a)",
            code1 == 1 and _named(reports_1, CTL1_FILE) and not ruff_regressed_itself,
            f"exit would be {code1}, mypy {base_mypy} → {head_mypy}, "
            f"ruff regression on the file: {ruff_regressed_itself}",
        )

        print(f"control 2 — findings planted in a NEW file {CTL2_FILE}")
        mut2 = _copy_arm(arm_a, tmpdir / "ctl2")
        (mut2 / CTL2_FILE).write_text(CTL2_CONTENT, encoding="utf-8")
        counts_2 = run_both(ruff_bin, mypy_bin, mut2)
        reports_2 = compare_arms(counts_a, counts_2)
        ruff_new = counts_2["ruff"].counts.get(CTL2_FILE, 0)
        mypy_new = counts_2["mypy"].counts.get(CTL2_FILE, 0)
        check(
            "mutation landed (both tools see the new file)",
            ruff_new > 0 and mypy_new > 0,
            f"ruff {ruff_new}, mypy {mypy_new} finding(s)",
        )
        code2, _ = verdict(reports_2)
        check(
            "gate fails and names it as new under BOTH tools (rule b)",
            code2 == 1 and _named(reports_2, CTL2_FILE),
            f"exit would be {code2}",
        )

        print("control 3 — unchanged tree (two independent extractions of HEAD)")
        reports_3 = compare_arms(counts_a, counts_b)
        code3, why3 = verdict(reports_3)
        check("identical arms pass", code3 == 0, why3)

        print(f"control 4 — {CTL1_FILE} gets BETTER at head (base arm carries the plants)")
        mut4 = _copy_arm(arm_a, tmpdir / "ctl4")
        _plant(mut4, CTL1_FILE, CTL4_PLANT)
        counts_4 = run_both(ruff_bin, mypy_bin, mut4)
        reports_4 = compare_arms(counts_4, counts_a)  # base = mutated, head = pristine
        improved_ruff = counts_4["ruff"].counts.get(CTL1_FILE, 0) > counts_a["ruff"].counts.get(
            CTL1_FILE, 0
        )
        improved_mypy = counts_4["mypy"].counts.get(CTL1_FILE, 0) > counts_a["mypy"].counts.get(
            CTL1_FILE, 0
        )
        check(
            "mutation landed (base arm really has more findings)",
            improved_ruff and improved_mypy,
            f"ruff {counts_4['ruff'].counts.get(CTL1_FILE, 0)} → "
            f"{counts_a['ruff'].counts.get(CTL1_FILE, 0)}, "
            f"mypy {counts_4['mypy'].counts.get(CTL1_FILE, 0)} → "
            f"{counts_a['mypy'].counts.get(CTL1_FILE, 0)}",
        )
        code4, _ = verdict(reports_4)
        check(
            "gate passes and the file is not named",
            code4 == 0 and not _named(reports_4, CTL1_FILE),
            f"exit would be {code4}",
        )

    if failures:
        print(f"SELF-TEST FAILED — {len(failures)} check(s) did not hold:")
        for failure in failures:
            print(f"  - {failure}")
        return 2
    print("SELF-TEST PASSED — all four controls fired; a green run of the gate means something")
    return 0


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def run_gate(repo: Path, base_ref: str, head_ref: str, ruff_bin: str, mypy_bin: str) -> int:
    with tempfile.TemporaryDirectory(prefix="coops-regression-gate-") as tmp:
        tmpdir = Path(tmp)
        base_dir = tmpdir / "base"
        head_dir = tmpdir / "head"
        base_sha = materialize(repo, base_ref, base_dir)
        head_sha = materialize(repo, head_ref, head_dir)
        base_counts = run_both(ruff_bin, mypy_bin, base_dir)
        head_counts = run_both(ruff_bin, mypy_bin, head_dir)

    print(f"regression gate: base {base_ref} ({base_sha[:12]}) → head {head_ref} ({head_sha[:12]})")
    print(f"instrument: {tool_version(ruff_bin)}, {tool_version(mypy_bin)}")
    print(
        "each ref was materialized with git archive into a temporary "
        "directory; the working tree and data/ were not touched"
    )
    print()
    reports = compare_arms(base_counts, head_counts)
    for line in render(reports):
        print(line)
    code, message = verdict(reports)
    print(message)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail when a file has more ruff or mypy findings at head "
        "than at base, or a new file has any. Only deltas gate."
    )
    parser.add_argument("--base", help="base ref (e.g. the merge-base or the parent phase)")
    parser.add_argument(
        "--head", default="HEAD", help="head ref (default: HEAD — uncommitted work is not examined)"
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=REPO_ROOT,
        help="repository to read refs from (default: this checkout)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the four controls that prove this gate can fail",
    )
    args = parser.parse_args()

    try:
        ruff_bin = resolve_tool("ruff", "COOPS_REGRESSION_RUFF")
        mypy_bin = resolve_tool("mypy", "COOPS_REGRESSION_MYPY")
        if args.self_test:
            if args.base:
                raise GateError("--self-test takes no --base (it compares HEAD against itself)")
            return run_self_test(args.repo, ruff_bin, mypy_bin)
        if not args.base:
            raise GateError("--base is required (or use --self-test)")
        return run_gate(args.repo, args.base, args.head, ruff_bin, mypy_bin)
    except GateError as exc:
        print(f"GATE: COULD NOT RUN (exit 2) — {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
