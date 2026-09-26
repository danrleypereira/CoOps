"""Dedupe Bronze per-repository files by repository id, at the reader (#248).

Why this exists
---------------
A repository that is **renamed or recased** leaves its old per-repository
files on disk forever beside the current ones; the readers glob the family,
so both spellings are read and **the repository is counted twice in
published data**. Measured on the live pair: ``repo_2025-1-NoFluxoUNB.json``
and ``repo_2025-1-NoFluxoUnB.json`` both carry repository id ``957040204``,
and the published totals were doubled — commits 1,239 + 1,219, issues
117 + 109, prs 70 + 61, issue_events 1,414 + 1,336.

The #216 reconciliation *deletes* the orphan, and deletion is only safe when
the filtered listing positively asserts its own completeness — provenance
existing corpora do not carry, so that path is inert on them. This module
needs no provenance and deletes nothing, because the identity claim is
weaker and self-evident:

    **Two files whose repository id is the same are the same repository** —
    true whatever the listing says and whether or not it is complete.

The id comes from the ``repo_<name>.json`` sibling: that file is the GitHub
repository object and carries the stable ``id``. A family file
(``commits_<name>.json``, ``issues_<name>.json``, …) maps to an id only
through it — deliberately NOT through ``repositories_filtered.json``, whose
completeness is exactly what cannot be assumed.

The winner rule, and its precondition
-------------------------------------
For a shared id, keep the copy with the latest ``_metadata.extracted_at``.
That stamp is sound evidence because the current name is rewritten every
run while an orphan never is again, so the gap only widens — the live pair
is 7 days apart.

The rule has a precondition, enforced here: the stamps are mixed
(``2026-09-18T09:15:46.896528`` naive against
``2026-09-25T09:53:03.135878+00:00`` aware), a naive stamp carries its
*writer's* zone — UTC on CI, ``-0300`` on the workstation — so it is not
comparable at run granularity. Zone ambiguity is bounded at ~26h and
distinct Bronze runs sit ~1h apart, so:

* gap **> 48h** (``REFUSE_WITHIN``) → the orphan mechanism explains it →
  keep the latest;
* gap **<= 48h**, or a gap that cannot be established at all (a stamp
  missing or unparseable — an empty record file carries no ``_metadata``)
  → **REFUSE and report the pair**. An orphan that young is
  indistinguishable from concurrent duplicate generation, which is a
  different bug and must not be hidden by picking a winner.

Naive and aware stamps are compared on their UTC wall times (aware
converted, naive taken as written), which never raises ``TypeError`` and is
conclusive at this threshold: ±26h of zone error cannot move a 1h pair
above 48h, nor a 7-day pair below it.

What "refuse" means
-------------------
Keep BOTH copies counted, and report the pair. Never drop both, never halt
the pipeline: a visibly wrong number beats a silent guess, so the double
count persists — visibly — until someone acts. The refusal therefore has to
reach OUTPUT, not a log line alone: :meth:`DedupeReport.as_dict` names the
affected repository id and the record totals each copy contributes, and the
extraction run prints :meth:`DedupeReport.format_lines` and publishes
``data/bronze/dedupe.json`` beside the files it describes
(:func:`write_report`). A double-counted total that ships without saying it
is double-counted is the exact defect this module exists to fix.

Unmapped files
--------------
A family file whose ``repo_<name>.json`` sibling is missing (or carries no
readable id) cannot be mapped to an id. It is counted, KEPT, and named in
the report: dropping it under-counts and merging it guesses, and both are
wrong. The ``repo`` family maps through the file itself, so it cannot be
unmapped for want of a sibling — only for want of an id.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "REFUSE_WITHIN",
    "REPORT_FILENAME",
    "DedupeReport",
    "DedupeResult",
    "DuplicateGroup",
    "FileFacts",
    "UnmappedFile",
    "dedupe_paths",
    "write_report",
]

#: A gap strictly greater than this picks a winner; anything at or below it
#: (including a gap that cannot be established) refuses and keeps both.
#:
#: 48h sits far enough above the ~26h zone-ambiguity bound that measurement
#: error cannot flip a verdict, and far enough above the ~1h spacing of
#: distinct runs that concurrent duplicate generation can never read as an
#: orphan.
REFUSE_WITHIN = timedelta(hours=48)

#: Where the published report lives: beside the files it describes. The name
#: avoids every family prefix and the ``repo``/``pr``/``commit``/``event``
#: substrings the registry's categorizer matches on, so it is never swept
#: into a family category or a family glob.
REPORT_FILENAME = "dedupe.json"

#: Unmapped reasons, spelled once so the report and the tests agree.
REASON_NO_SIBLING = "no repo_{name}.json sibling to name its repository id"
REASON_SIBLING_NO_ID = "repo_{name}.json carries no readable repository id"
REASON_NO_ID = "carries no readable repository id"


@dataclass(frozen=True)
class FileFacts:
    """What the winner rule needed from one file, and what the report names.

    ``extracted_at`` is the raw ``_metadata.extracted_at`` string and
    ``records`` the record count the copy contributes to totals (a document
    counts as one); either is ``None`` when the payload could not be read.
    """

    name: str
    extracted_at: str | None
    records: int | None


@dataclass(frozen=True)
class DuplicateGroup:
    """One repository id held by more than one file of one family.

    ``gap`` is the span between the earliest and the latest stamp, or
    ``None`` when a stamp is missing or unparseable — which refuses, because
    the precondition cannot be established. ``winner`` names the kept copy
    and is ``None`` exactly when the group refused.
    """

    family: str
    repository_id: int
    files: tuple[FileFacts, ...]
    gap: timedelta | None
    refused: bool
    winner: str | None


@dataclass(frozen=True)
class UnmappedFile:
    """A family file that could not be keyed by repository id — kept and
    counted, never dropped."""

    family: str
    name: str
    reason: str


@dataclass(frozen=True)
class DedupeReport:
    """What deduping found, across one family or many, ready for output."""

    duplicates: tuple[DuplicateGroup, ...] = ()
    unmapped: tuple[UnmappedFile, ...] = ()

    @property
    def refused(self) -> tuple[DuplicateGroup, ...]:
        """Groups where no winner was picked: both copies stay counted."""
        return tuple(group for group in self.duplicates if group.refused)

    @property
    def deduped(self) -> tuple[DuplicateGroup, ...]:
        """Groups where a winner was picked: the losers are no longer read."""
        return tuple(group for group in self.duplicates if not group.refused)

    def merged(self, other: DedupeReport) -> DedupeReport:
        """Two reports as one, in (family, repository_id) order — a stable
        sort, so equal keys keep their (already deterministic) order."""
        return DedupeReport(
            duplicates=tuple(
                sorted(
                    (*self.duplicates, *other.duplicates),
                    key=lambda group: (group.family, group.repository_id),
                )
            ),
            unmapped=tuple(
                sorted(
                    (*self.unmapped, *other.unmapped),
                    key=lambda item: (item.family, item.name),
                )
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        """The report as JSON-serializable data, sorted so two runs over the
        same tree produce the same artifact (#172)."""
        return {
            "refused_duplicates": {
                "count": len(self.refused),
                "note": (
                    "each named repository is counted TWICE in this corpus: the "
                    "copies are at most 48h apart (or a stamp is unreadable), "
                    "which is indistinguishable from concurrent duplicate "
                    "generation, so no winner was picked"
                ),
                "groups": [
                    {
                        "family": group.family,
                        "repository_id": group.repository_id,
                        "gap_hours": _hours(group.gap),
                        "files": [
                            {
                                "file": facts.name,
                                "extracted_at": facts.extracted_at,
                                "records": facts.records,
                            }
                            for facts in group.files
                        ],
                    }
                    for group in self.refused
                ],
            },
            "deduped": {
                "count": len(self.deduped),
                "note": (
                    "one copy kept per repository id (the latest "
                    "_metadata.extracted_at); the superseded copies are no "
                    "longer read"
                ),
                "groups": [
                    {
                        "family": group.family,
                        "repository_id": group.repository_id,
                        "gap_hours": _hours(group.gap),
                        "kept": group.winner,
                        "superseded": [
                            {
                                "file": facts.name,
                                "extracted_at": facts.extracted_at,
                                "records": facts.records,
                            }
                            for facts in group.files
                            if facts.name != group.winner
                        ],
                    }
                    for group in self.deduped
                ],
            },
            "unmapped": {
                "count": len(self.unmapped),
                "note": (
                    "counted and kept: these files cannot be keyed by "
                    "repository id, so they are neither dropped nor merged"
                ),
                "files": [
                    {"family": item.family, "file": item.name, "reason": item.reason}
                    for item in self.unmapped
                ],
            },
        }

    def format_lines(self) -> list[str]:
        """The run-report lines: the zero case included, so silence is a
        choice someone made, not a path nobody exercised."""
        lines = [
            f"Bronze dedupe (by repository id, #248): {len(self.deduped)} duplicate "
            f"id(s) deduped, {len(self.refused)} REFUSED (still double-counted), "
            f"{len(self.unmapped)} unmapped file(s)"
        ]
        for group in self.deduped:
            kept = next(f for f in group.files if f.name == group.winner)
            losers = ", ".join(
                f"{f.name} ({f.extracted_at}, {_describe_records(f.records)})"
                for f in group.files
                if f.name != group.winner
            )
            lines.append(
                f"  [deduped: {group.family} id {group.repository_id} — kept "
                f"{kept.name} ({kept.extracted_at}, "
                f"{_describe_records(kept.records)}); superseded {losers}]"
            )
        for group in self.refused:
            both = " and ".join(
                f"{f.name} ({_describe_records(f.records)}, {f.extracted_at})"
                for f in group.files
            )
            apart = (
                f"{_hours(group.gap):g}h apart"
                if group.gap is not None
                else "a gap that cannot be established (a stamp is missing or unparseable)"
            )
            lines.append(
                f"  [REFUSED — BOTH KEPT AND DOUBLE-COUNTED: {group.family} id "
                f"{group.repository_id}: {both}, {apart}; at most 48h apart is "
                "indistinguishable from concurrent duplicate generation]"
            )
        for item in self.unmapped:
            lines.append(
                f"  [unmapped — counted and kept: {item.family}/{item.name}: "
                f"{item.reason}]"
            )
        return lines


@dataclass(frozen=True)
class DedupeResult:
    """The files a reader may still enumerate, and why any file is gone.

    ``kept`` holds the singleton files, the winners, every copy of a refused
    group and every unmapped file — sorted, so enumeration stays
    deterministic. The only files absent are the superseded losers.
    """

    kept: list[Path]
    report: DedupeReport


def _hours(gap: timedelta | None) -> float | None:
    return None if gap is None else round(gap.total_seconds() / 3600, 2)


def _describe_records(count: int | None) -> str:
    return "an unreadable payload" if count is None else f"{count} record(s)"


def _normalise_id(raw: Any) -> int | None:
    """A repository id as a comparable int, or None when the value is not one.

    GitHub ids are JSON numbers; a digits-only string is the same id spelled
    by hand (the domain model stringifies them too) and is coerced so the
    two spellings land in one group. Anything else is not an id.
    """
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


def _read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _map_to_id(bronze_dir: Path, family: str, path: Path) -> tuple[int | None, str | None]:
    """The repository id ``path`` maps to, and why when it cannot.

    Family files map through their ``repo_<name>.json`` sibling; the ``repo``
    family maps through the file itself. Unreadable is not an error here: a
    sibling that cannot be read is a sibling whose id cannot be known, which
    is the unmapped case, not a reason to stop counting the family file.
    """
    if family == "repo":
        try:
            payload = _read_json(path)
        except (OSError, ValueError):
            return None, REASON_NO_ID
        repository_id = _normalise_id(payload.get("id")) if isinstance(payload, dict) else None
        return (repository_id, None) if repository_id is not None else (None, REASON_NO_ID)

    stem = path.name[: -len(".json")]
    # The same prefix-slice repo_of applies ("<family>_" is a prefix here by
    # construction: these paths came from the family glob).
    repo_name = stem[len(family) + 1 :]
    sibling = bronze_dir / f"repo_{repo_name}.json"
    if not sibling.is_file():
        return None, REASON_NO_SIBLING.format(name=repo_name)
    try:
        payload = _read_json(sibling)
    except (OSError, ValueError):
        return None, REASON_SIBLING_NO_ID.format(name=repo_name)
    repository_id = _normalise_id(payload.get("id")) if isinstance(payload, dict) else None
    if repository_id is None:
        return None, REASON_SIBLING_NO_ID.format(name=repo_name)
    return repository_id, None


def _stamp_and_records(payload: Any) -> tuple[str | None, int | None]:
    """The extraction stamp and record count a payload carries.

    Mirrors the writer's shapes, of which there are THREE, not two:

    * a record family is a JSON list whose first element is the ``_metadata``
      sidecar (an empty list got none);
    * a document family written through ``save_json_data`` is one object with
      ``_metadata`` merged in;
    * ``structure_*.json`` is written by ``repository_structure.py``, which
      carries ``extracted_at`` as a **top-level** key beside ``owner``,
      ``repository``, ``branch``, ``sha``, ``tree`` and ``method``, and has no
      ``_metadata`` at all (#255).

    Missing the third shape did not corrupt anything — an unreadable stamp
    refuses, which is the safe direction — but it meant the structure family
    never deduped: both files of a recased pair stayed on the live corpus,
    reporting ``extracted_at=None, gap=None``, which is the exact harm #216
    exists to remove.

    ``_metadata`` wins when both are present: it is the envelope the writer
    added last.
    """
    if isinstance(payload, list):
        first = payload[0] if payload else None
        meta = first.get("_metadata") if isinstance(first, dict) else None
        if isinstance(meta, dict):
            stamp = meta.get("extracted_at")
            return (stamp if isinstance(stamp, str) else None), max(len(payload) - 1, 0)
        return None, len(payload)
    if isinstance(payload, dict):
        meta = payload.get("_metadata")
        stamp = meta.get("extracted_at") if isinstance(meta, dict) else None
        if not isinstance(stamp, str):
            # The third shape (#255): no envelope, stamp at the top level.
            stamp = payload.get("extracted_at")
        return (stamp if isinstance(stamp, str) else None), 1
    return None, None


def _facts(path: Path) -> FileFacts:
    try:
        stamp, records = _stamp_and_records(_read_json(path))
    except (OSError, ValueError):
        # The reader that owns this file (bronze_records) raises on a corrupt
        # family file; here the stamp is unprovable, which refuses rather
        # than guesses, and the count reports as unreadable.
        return FileFacts(name=path.name, extracted_at=None, records=None)
    return FileFacts(name=path.name, extracted_at=stamp, records=records)


def _parse_stamp(raw: str | None) -> datetime | None:
    """Parse a stamp as written, preserving awareness; None when unparseable.

    The trailing ``Z`` is normalised for ``fromisoformat``, which only
    accepts it from Python 3.11.
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _utc_wall(moment: datetime) -> datetime:
    """``moment`` as a naive UTC wall time, so naive and aware subtract.

    An aware stamp converts to its UTC wall time; a naive one is taken as
    written — its writer's local wall clock, ambiguous by at most the ~26h
    of the zone bound, which the 48h threshold is sized to dominate.
    """
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def dedupe_paths(
    bronze_dir: Path | str, family: str, paths: list[Path]
) -> DedupeResult:
    """Key per-repository ``paths`` of one ``family`` by repository id.

    Singletons, winners, refused groups and unmapped files are all kept;
    only a superseded loser — same id as its winner, more than
    ``REFUSE_WITHIN`` older — is left out. The result is sorted by filename
    so two runs enumerate identically (#172).
    """
    directory = Path(bronze_dir)
    kept: list[Path] = []
    unmapped: list[UnmappedFile] = []
    by_id: dict[int, list[Path]] = {}
    for path in sorted(paths):
        repository_id, reason = _map_to_id(directory, family, path)
        if repository_id is None:
            # Unmapped: counted and kept — dropping under-counts, merging
            # guesses. Named in the report so the gap is visible, not silent.
            unmapped.append(
                UnmappedFile(family=family, name=path.name, reason=reason or REASON_NO_ID)
            )
            kept.append(path)
        else:
            by_id.setdefault(repository_id, []).append(path)

    duplicates: list[DuplicateGroup] = []
    for repository_id in sorted(by_id):
        group = sorted(by_id[repository_id])
        if len(group) == 1:
            kept.extend(group)
            continue

        facts = [_facts(path) for path in group]
        # Every stamp must parse before any gap is believed: one unreadable
        # stamp leaves the precondition unprovable, which refuses.
        wall_times: list[datetime] = []
        for facts_item in facts:
            stamp = _parse_stamp(facts_item.extracted_at)
            if stamp is None:
                wall_times = []
                break
            wall_times.append(_utc_wall(stamp))
        gap = max(wall_times) - min(wall_times) if wall_times else None

        if gap is not None and gap > REFUSE_WITHIN:
            # The precondition holds: only the orphan mechanism explains a
            # gap this size, and the latest copy is the current name. A gap
            # over 48h cannot contain a tie, so the winner is unique.
            refused = False
            winner = group[wall_times.index(max(wall_times))]
            kept.append(winner)
        else:
            # At most 48h apart, or unprovable: concurrent duplicate
            # generation cannot be told from a young orphan, so no winner.
            refused = True
            winner = None
            kept.extend(group)
        duplicates.append(
            DuplicateGroup(
                family=family,
                repository_id=repository_id,
                files=tuple(facts),
                gap=gap,
                refused=refused,
                winner=None if winner is None else winner.name,
            )
        )

    return DedupeResult(
        kept=sorted(kept),
        report=DedupeReport(
            duplicates=tuple(
                sorted(
                    duplicates,
                    key=lambda group: (group.family, group.repository_id),
                )
            ),
            unmapped=tuple(sorted(unmapped, key=lambda item: (item.family, item.name))),
        ),
    )


def write_report(
    bronze_dir: Path | str, report: DedupeReport, path: Path | str | None = None
) -> Path:
    """Publish the report beside the files it describes.

    ``data/bronze/dedupe.json`` is committed with the corpus, so a
    double-counted total ships WITH the statement that it is double-counted,
    naming the repository ids and the per-copy totals involved. The
    ``generated_at`` stamp is aware UTC (#143's convention for persisted
    timestamps).
    """
    target = Path(path) if path is not None else Path(bronze_dir) / REPORT_FILENAME
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **report.as_dict(),
    }
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return target
