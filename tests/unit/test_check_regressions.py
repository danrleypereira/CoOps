"""Unit tests for scripts/check_regressions.py — the gate's decision rules.

The real ruff/mypy are replaced by deterministic fakes (one finding per
``# ruff-finding`` / ``# mypy-error`` marker line), and every comparison runs
against a throwaway git repository built in ``tmp_path``: fast, offline, and
independent of what the checkout happens to contain. The fakes emit absolute
paths the way ruff 0.16 does, so the arm-relativization is exercised too.

These tests pin the DECISIONS: which delta fails, which passes, and which
troubles are exit 2 (could not run) rather than exit 0. The end-to-end proof
that the real gate fails on real regressions is the script's own
``--self-test``, run as an integration test.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_regressions.py"

_spec = importlib.util.spec_from_file_location("check_regressions", SCRIPT)
check_regressions = importlib.util.module_from_spec(_spec)
sys.modules["check_regressions"] = check_regressions  # dataclasses needs it resolvable
_spec.loader.exec_module(check_regressions)

PYPROJECT = '[project]\nname = "tiny"\nversion = "0"\nrequires-python = ">=3.10"\n'

# ---------------------------------------------------------------------------
# fake tools: one finding per marker line, absolute paths like ruff 0.16
# ---------------------------------------------------------------------------

FAKE_RUFF = """#!/usr/bin/env python3
import json
import os
import pathlib
import sys

if "--version" in sys.argv:
    print("ruff 0.0.0-fake")
    sys.exit(0)

log = os.environ.get("GATE_TOOL_LOG")
if log:
    with open(log, "a") as fh:
        fh.write("ruff argv=%r\\n" % (sys.argv[1:],))

findings = []
for target in [a for a in sys.argv[1:] if not a.startswith("-")]:
    p = pathlib.Path(target)
    if not p.is_dir():
        continue
    for py in sorted(p.rglob("*.py")):
        n = sum(1 for line in py.read_text().splitlines() if "# ruff-finding" in line)
        findings.extend({"filename": str(py.resolve()), "code": "F401"} for _ in range(n))
print(json.dumps(findings))
sys.exit(1 if findings else 0)
"""

FAKE_MYPY = """#!/usr/bin/env python3
import os
import pathlib
import sys

if "--version" in sys.argv:
    print("mypy 0.0.0-fake")
    sys.exit(0)

log = os.environ.get("GATE_TOOL_LOG")
if log:
    with open(log, "a") as fh:
        fh.write("mypy argv=%r\\n" % (sys.argv[1:],))

sys.stderr.write("/dev/null: No [mypy] section in config file\\n")
count = 0
p = pathlib.Path(sys.argv[-1])
if p.is_dir():
    for py in sorted(p.rglob("*.py")):
        for i, line in enumerate(py.read_text().splitlines(), 1):
            if "# mypy-error" in line:
                print("%s:%d: error: planted assignment error [assignment]" % (py, i))
                count += 1
print("Found %d errors in 1 file (checked 3 source files)" % count)
sys.exit(1 if count else 0)
"""


@pytest.fixture(scope="session")
def fake_tools(tmp_path_factory):
    """(ruff, mypy) executables that report the planted marker lines."""
    directory = tmp_path_factory.mktemp("fake-tools")
    ruff = directory / "ruff"
    ruff.write_text(FAKE_RUFF)
    ruff.chmod(0o755)
    mypy = directory / "mypy"
    mypy.write_text(FAKE_MYPY)
    mypy.chmod(0o755)
    return ruff, mypy


# ---------------------------------------------------------------------------
# a throwaway repository to compare refs in
# ---------------------------------------------------------------------------


def _issues(ruff_markers: int = 0, mypy_markers: int = 0) -> str:
    lines = ["def fetch(url):", "    return url", ""]
    lines += [f"R{i} = 1  # ruff-finding" for i in range(ruff_markers)]
    lines += [f"M{i} = 2  # mypy-error" for i in range(mypy_markers)]
    return "\n".join(lines) + "\n"


def _github(ruff_markers: int = 0) -> str:
    lines = ["def get():", "    return 1", ""]
    lines += [f"G{i} = 1  # ruff-finding" for i in range(ruff_markers)]
    return "\n".join(lines) + "\n"


def tiny_repo_files(
    issues: str | None = None, github: str | None = None, extra: dict[str, str] | None = None
) -> dict[str, str]:
    files = {
        "pyproject.toml": PYPROJECT,
        "src/coops/__init__.py": "",
        "src/coops/bronze/__init__.py": "",
        "src/coops/bronze/issues.py": issues if issues is not None else _issues(),
        "src/coops/utils/__init__.py": "",
        "src/coops/utils/github_api.py": github if github is not None else _github(),
        "tests/__init__.py": "",
        "tests/test_tiny.py": "def test_ok():\n    assert True\n",
    }
    if extra:
        files.update(extra)
    return files


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(
    tmp_path: Path, base_files: dict[str, str], head_files: dict[str, str] | None = None
) -> Path:
    repo = tmp_path / "repo"
    for rel, content in base_files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "gate@example.invalid")
    _git(repo, "config", "user.name", "Gate Test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "tag", "base")
    if head_files is not None:
        for rel, content in head_files.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "head")
        _git(repo, "tag", "head")
    return repo


def run_gate(
    fake_tools,
    repo: Path,
    base: str = "base",
    head: str | None = "head",
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    ruff, mypy = fake_tools
    env = os.environ.copy()
    env["COOPS_REGRESSION_RUFF"] = str(ruff)
    env["COOPS_REGRESSION_MYPY"] = str(mypy)
    if env_extra:
        env.update(env_extra)
    cmd = [sys.executable, str(SCRIPT), "--repo", str(repo), "--base", base]
    if head is not None:
        cmd += ["--head", head]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120, check=False)


# ---------------------------------------------------------------------------
# rule (a): a pre-existing file with MORE findings at head fails
# ---------------------------------------------------------------------------


def test_ruff_regression_in_preexisting_file_fails(fake_tools, tmp_path):
    repo = make_repo(tmp_path, tiny_repo_files(), tiny_repo_files(issues=_issues(ruff_markers=2)))
    proc = run_gate(fake_tools, repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "src/coops/bronze/issues.py: 0 → 2 (+2)" in proc.stdout
    assert "GATE: FAIL" in proc.stdout


def test_mypy_regression_attributed_to_the_mypy_block(fake_tools, tmp_path):
    repo = make_repo(tmp_path, tiny_repo_files(), tiny_repo_files(issues=_issues(mypy_markers=3)))
    proc = run_gate(fake_tools, repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    line = "src/coops/bronze/issues.py: 0 → 3 (+3)"
    assert line in proc.stdout
    assert proc.stdout.index("mypy:") < proc.stdout.index(line)


def test_aggregate_total_falls_yet_the_gate_fails(fake_tools, tmp_path):
    """The Phase 1 shape, distilled: the total improves, a file regressed.

    issues.py goes 3 ruff findings → 0 (better), github_api.py goes 0 → 1
    (worse). The total falls 3 → 1; an aggregate gate passes; this gate
    must fail and name only the file that got worse.
    """
    repo = make_repo(
        tmp_path,
        tiny_repo_files(issues=_issues(ruff_markers=3)),
        tiny_repo_files(issues=_issues(), github=_github(ruff_markers=1)),
    )
    proc = run_gate(fake_tools, repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "src/coops/utils/github_api.py: 0 → 1 (+1)" in proc.stdout
    assert "issues.py" not in proc.stdout  # better is not a regression, and not named


# ---------------------------------------------------------------------------
# rule (b): a NEW file with any finding fails
# ---------------------------------------------------------------------------


def test_new_file_with_findings_fails_under_both_tools(fake_tools, tmp_path):
    new_module = "def broken():\n    X = 1  # ruff-finding\n    Y = 2  # mypy-error\n"
    repo = make_repo(
        tmp_path,
        tiny_repo_files(),
        tiny_repo_files(extra={"src/coops/bronze/new_thing.py": new_module}),
    )
    proc = run_gate(fake_tools, repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "NEW WITH FINDINGS" in proc.stdout
    assert proc.stdout.count("src/coops/bronze/new_thing.py: new at head") == 2  # ruff + mypy


# ---------------------------------------------------------------------------
# what must PASS
# ---------------------------------------------------------------------------


def test_identical_arms_pass(fake_tools, tmp_path):
    """Default --head is HEAD; an unchanged tree is not a regression."""
    repo = make_repo(tmp_path, tiny_repo_files())
    proc = run_gate(fake_tools, repo, head=None)  # --head omitted → HEAD == base
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "GATE: PASS" in proc.stdout


def test_file_that_gets_better_passes_and_is_not_named(fake_tools, tmp_path):
    repo = make_repo(
        tmp_path, tiny_repo_files(issues=_issues(ruff_markers=2, mypy_markers=2)), tiny_repo_files()
    )
    proc = run_gate(fake_tools, repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "issues.py" not in proc.stdout
    assert "1 file(s) improved at head" in proc.stdout


# ---------------------------------------------------------------------------
# exit 2: the gate could not run — never a pass
# ---------------------------------------------------------------------------


def test_missing_tool_binary_is_exit_2(fake_tools, tmp_path):
    repo = make_repo(tmp_path, tiny_repo_files())
    proc = run_gate(fake_tools, repo, env_extra={"COOPS_REGRESSION_RUFF": "/nonexistent/ruff"})
    assert proc.returncode == 2
    assert "COULD NOT RUN" in proc.stderr


def test_unresolvable_ref_is_exit_2(fake_tools, tmp_path):
    repo = make_repo(tmp_path, tiny_repo_files())
    proc = run_gate(fake_tools, repo, base="no-such-ref")
    assert proc.returncode == 2
    assert "COULD NOT RUN" in proc.stderr


def test_crashing_ruff_is_exit_2(fake_tools, tmp_path, tmp_path_factory):
    crasher_dir = tmp_path_factory.mktemp("crashing-ruff")
    crasher = crasher_dir / "ruff"
    crasher.write_text(
        "#!/usr/bin/env python3\nimport sys\n"
        "if '--version' in sys.argv:\n    print('ruff 0.0.0-fake')\n"
        "else:\n    sys.exit(2)\n"
    )
    crasher.chmod(0o755)
    repo = make_repo(tmp_path, tiny_repo_files())
    proc = run_gate(fake_tools, repo, env_extra={"COOPS_REGRESSION_RUFF": str(crasher)})
    assert proc.returncode == 2
    assert "COULD NOT RUN" in proc.stderr


def test_tree_without_src_is_exit_2(fake_tools, tmp_path):
    repo = make_repo(tmp_path, {"pyproject.toml": PYPROJECT})
    proc = run_gate(fake_tools, repo)
    assert proc.returncode == 2
    assert "COULD NOT RUN" in proc.stderr


# ---------------------------------------------------------------------------
# the invocations themselves — pin the deliberate choices
# ---------------------------------------------------------------------------


def test_mypy_ignores_the_pyproject_scope(fake_tools, tmp_path):
    """The Phase 1 blind spot, pinned: the gate's mypy must be config-free.

    If someone "fixes" this to the repo config, pyproject's scope (domain/
    github/storage) hides bronze/ and silver/ again and this test goes red.
    """
    log = tmp_path / "tool.log"
    repo = make_repo(tmp_path, tiny_repo_files())
    proc = run_gate(fake_tools, repo, head=None, env_extra={"GATE_TOOL_LOG": str(log)})
    assert proc.returncode == 0
    mypy_calls = [line for line in log.read_text().splitlines() if line.startswith("mypy")]
    assert mypy_calls, "the fake mypy was never invoked"
    argv = mypy_calls[0]
    assert "'--config-file', '/dev/null'" in argv
    assert "src/coops" in argv


def test_ruff_checks_src_and_tests_with_the_pinned_flags(fake_tools, tmp_path):
    log = tmp_path / "tool.log"
    repo = make_repo(tmp_path, tiny_repo_files())
    run_gate(fake_tools, repo, head=None, env_extra={"GATE_TOOL_LOG": str(log)})
    ruff_calls = [line for line in log.read_text().splitlines() if line.startswith("ruff")]
    assert ruff_calls, "the fake ruff was never invoked"
    argv = ruff_calls[0]
    assert "'check'" in argv
    assert "'src'" in argv and "'tests'" in argv


# ---------------------------------------------------------------------------
# the pure pieces: path relativization, mypy parsing, the delta rules
# ---------------------------------------------------------------------------


def test_relativize_handles_absolute_and_relative_paths(tmp_path):
    arm = tmp_path / "arm"
    arm.mkdir()
    absolutize = check_regressions._relativize
    assert absolutize(str((arm / "src" / "a.py").resolve()), arm) == "src/a.py"
    assert absolutize("src/b.py", arm) == "src/b.py"
    assert absolutize("/elsewhere/c.py", arm) == "/elsewhere/c.py"


def test_mypy_line_counter_ignores_notes_and_summaries():
    text = (
        "/dev/null: No [mypy] section in config file\n"
        "src/coops/bronze/issues.py:41: error: incompatible assignment [assignment]\n"
        "src/coops/bronze/issues.py:42:7: error: with a column [arg-type]\n"
        "note: See https://mypy.readthedocs.io/en/stable/running_mypy.html\n"
        "Found 2 errors in 1 file (checked 62 source files)\n"
    )
    assert check_regressions._count_mypy_lines(text) == Counter({"src/coops/bronze/issues.py": 2})


def test_compare_tool_rules():
    base = check_regressions.ArmReading(
        Counter({"stays.py": 1, "worse.py": 2, "better.py": 5}),
        {"stays.py", "worse.py", "better.py"},
    )
    head = check_regressions.ArmReading(
        Counter({"stays.py": 1, "worse.py": 4, "better.py": 3, "new.py": 2}),
        {"stays.py", "worse.py", "better.py", "new.py"},
    )
    delta = check_regressions.compare_tool("ruff", base, head)
    assert delta.regressed == [("worse.py", 2, 4)]
    assert delta.new_with_findings == [("new.py", 2)]
    assert delta.improved == [("better.py", 5, 3)]
    assert delta.ok is False
    assert (delta.base_total, delta.head_total) == (8, 10)


def test_clean_preexisting_file_regressing_is_rule_a_not_new():
    """The Phase 1 ruff shape: github_api.py had 0 findings at base, +19 at head.

    A Counter alone cannot tell "existed, clean" from "did not exist"; the
    file sets can, and the difference is a REGRESSION, not a new file.
    """
    base = check_regressions.ArmReading(Counter(), {"src/coops/utils/github_api.py"})
    head = check_regressions.ArmReading(
        Counter({"src/coops/utils/github_api.py": 19}), {"src/coops/utils/github_api.py"}
    )
    delta = check_regressions.compare_tool("ruff", base, head)
    assert delta.regressed == [("src/coops/utils/github_api.py", 0, 19)]
    assert delta.new_with_findings == []


def test_file_improving_to_zero_is_still_counted_as_improved():
    """A file fixed to zero findings leaves head.counts entirely — the walk
    must run over the file domains or the improvement silently vanished."""
    base = check_regressions.ArmReading(Counter({"a.py": 2}), {"a.py"})
    head = check_regressions.ArmReading(Counter(), {"a.py"})
    delta = check_regressions.compare_tool("ruff", base, head)
    assert delta.improved == [("a.py", 2, 0)]
    assert delta.ok is True


def test_compare_tool_new_file_with_no_findings_is_not_reported():
    base = check_regressions.ArmReading(Counter({"a.py": 1}), {"a.py"})
    head = check_regressions.ArmReading(Counter({"a.py": 1}), {"a.py", "clean_new.py"})
    delta = check_regressions.compare_tool("mypy", base, head)
    assert delta.ok is True


def test_verdict_is_pass_only_when_no_file_regressed():
    ok = check_regressions.compare_tool(
        "ruff",
        check_regressions.ArmReading(Counter({"a.py": 3}), {"a.py"}),
        check_regressions.ArmReading(Counter({"a.py": 1}), {"a.py"}),
    )
    assert check_regressions.verdict([ok])[0] == 0
    bad = check_regressions.compare_tool(
        "ruff",
        check_regressions.ArmReading(Counter(), set()),
        check_regressions.ArmReading(Counter({"b.py": 1}), {"b.py"}),
    )
    assert check_regressions.verdict([bad])[0] == 1
