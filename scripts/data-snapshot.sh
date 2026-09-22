#!/usr/bin/env bash
#
# CoOps — Collaboration & Ops Metrics Dashboard
# Copyright (C) 2026 CoOps Contributors
# Licensed under the GNU General Public License v3.0 (or later). See LICENSE.
#
# data-snapshot.sh — keep the raw GitHub API corpus local and reusable across
# git worktrees, as a compressed snapshot.
#
# A full Bronze→Silver→Gold extraction fetches ~1.4 GB of raw GitHub API
# responses into `cache/` and ~200 MB of derived JSON into `data/`, and takes
# about an hour of rate-limited calls. Re-fetching in every new worktree is
# unacceptable, so this script packs the corpus once and restores it elsewhere.
#
# The corpus (the two directories `cache/` and `data/`) is NEVER committed to
# git — the project is moving off committing pipeline output. It is kept
# locally as a timestamped, checksummed tarball in a single shared location
# outside any worktree.
#
# ---------------------------------------------------------------------------
# Snapshot location
# ---------------------------------------------------------------------------
# Snapshots live in a fixed directory OUTSIDE every git worktree, so all
# worktrees on the machine share one copy:
#
#   $COOPS_SNAPSHOT_DIR            if set, else
#   $XDG_DATA_HOME/coops/snapshots if XDG_DATA_HOME is set, else
#   ~/.local/share/coops/snapshots
#
# Nothing under the repository needs to be git-ignored for this location
# because it is not inside the repository. `cache/` and `data/` themselves are
# git-ignored in the repository's .gitignore.
#
# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------
#   pack [--source <dir>]     Create a timestamped .tar.gz of cache/ + data/
#                             (default source: the current directory), with a
#                             SHA-256 checksum recorded alongside it.
#   unpack [--into <dir>]     Restore the NEWEST snapshot into a target
#                             directory (default: the current worktree).
#                             Refuses to overwrite a non-empty cache/ or data/
#                             unless --force is given, and refuses a corrupt
#                             archive.
#   list                      Show available snapshots with size and age.
#   verify <snapshot>         Check integrity (checksum + archive structure)
#                             without extracting.
#
# Environment:
#   COOPS_SNAPSHOT_DIR   Override the snapshot directory (see above).
#
# Exit codes: 0 ok · 1 operational error (missing/corrupt corpus, etc.) ·
#             2 usage error.
#
# Requires GNU coreutils (sha256sum, tar, gzip, stat, find, du) and bash ≥ 4.

set -euo pipefail

# --- Configuration -----------------------------------------------------------

readonly SNAPSHOT_DIR="${COOPS_SNAPSHOT_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/coops/snapshots}"
readonly PREFIX="coops-corpus"
readonly CORPUS_DIRS=(cache data)

# --- Output helpers ----------------------------------------------------------

info() { printf '%s\n' "$*"; }

warn() { printf 'warning: %s\n' "$*" >&2; }

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

usage() {
  awk 'NR >= 2 { if ($0 ~ /^#/) { sub(/^# ?/, ""); print } else { exit } }' "$0"
  exit 2
}

# --- Corpus helpers ----------------------------------------------------------

# Prints 0 (success) when the path exists and unpack would need --force to
# replace it: i.e. it is a non-directory (file/symlink), or a non-empty
# directory. Returns non-zero when the path is absent or an empty directory.
needs_force() {
  local path="$1"
  [[ -e "$path" || -L "$path" ]] || return 1
  [[ -d "$path" ]] || return 0
  [[ -n "$(ls -A "$path" 2>/dev/null)" ]]
}

# --- Snapshot listing --------------------------------------------------------

# Prints full paths to *.tar.gz files in SNAPSHOT_DIR, newest (by mtime) first.
sorted_snapshots() {
  local dir="$1" f
  local -a all=()
  shopt -s nullglob
  for f in "$dir"/*.tar.gz; do
    all+=("$f")
  done
  shopt -u nullglob
  (( ${#all[@]} > 0 )) || return 0
  for f in "${all[@]}"; do
    printf '%s\t%s\n' "$(stat -c %Y "$f")" "$f"
  done | sort -rn | cut -f2-
}

newest_snapshot() {
  local -a snaps=()
  local s
  while IFS= read -r s; do
    [[ -n "$s" ]] && snaps+=("$s")
  done < <(sorted_snapshots "$SNAPSHOT_DIR")
  if (( ${#snaps[@]} == 0 )); then
    die "no snapshots found in $SNAPSHOT_DIR — run 'pack' first"
  fi
  printf '%s\n' "${snaps[0]}"
}

# Resolve a snapshot argument that may be a bare name or a path.
resolve_snapshot() {
  local arg="$1"
  case "$arg" in
    */*) printf '%s\n' "$arg" ;;
    *)   printf '%s\n' "$SNAPSHOT_DIR/$arg" ;;
  esac
}

# Human-readable age from an epoch-seconds timestamp.
human_age() {
  local then="$1" now secs d h m s
  now="$(date +%s)"
  secs=$(( now - then ))
  (( secs < 0 )) && secs=0
  d=$(( secs / 86400 )); secs=$(( secs % 86400 ))
  h=$(( secs / 3600 ));  secs=$(( secs % 3600 ))
  m=$(( secs / 60 ));    s=$(( secs % 60 ))
  if (( d > 0 )); then
    printf '%dd %dh' "$d" "$h"
  elif (( h > 0 )); then
    printf '%dh %dm' "$h" "$m"
  elif (( m > 0 )); then
    printf '%dm %ds' "$m" "$s"
  else
    printf '%ds' "$s"
  fi
}

# --- Subcommands -------------------------------------------------------------

cmd_pack() {
  local source="."
  while (( $# > 0 )); do
    case "$1" in
      --source)
        shift
        (( $# > 0 )) || die "--source requires a directory"
        source="$1"
        ;;
      *)
        die "unknown argument for pack: $1"
        ;;
    esac
    shift
  done

  source="$(cd "$source" && pwd)" || die "cannot access source directory: $source"

  local d
  for d in "${CORPUS_DIRS[@]}"; do
    [[ -d "$source/$d" ]] || die "source has no $d/ directory: $source"
  done

  mkdir -p "$SNAPSHOT_DIR" || die "cannot create snapshot directory: $SNAPSHOT_DIR"

  local stamp name final tmp
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  name="${PREFIX}-${stamp}.tar.gz"
  final="$SNAPSHOT_DIR/$name"
  tmp="$SNAPSHOT_DIR/.tmp.${name}.$$"

  rm -f "$tmp"
  if ! tar -czf "$tmp" -C "$source" "${CORPUS_DIRS[@]}"; then
    rm -f "$tmp"
    die "failed to create archive from $source"
  fi

  # Fail closed: refuse to publish an archive that is not a readable tar.gz.
  if ! tar -tzf "$tmp" >/dev/null 2>&1; then
    rm -f "$tmp"
    die "created archive failed validation: $tmp"
  fi

  mv "$tmp" "$final" || { rm -f "$tmp"; die "failed to move archive into place"; }

  # Record a SHA-256 checksum next to the archive, keyed by basename so the
  # pair can be moved together and still verify.
  if ! ( cd "$SNAPSHOT_DIR" && sha256sum "$name" > "$name.sha256" ); then
    rm -f "$final"
    die "failed to write checksum for $final"
  fi

  info "packed: $final"
  info "checksum: $final.sha256"
}

cmd_unpack() {
  local into="." force=0
  while (( $# > 0 )); do
    case "$1" in
      --into)
        shift
        (( $# > 0 )) || die "--into requires a directory"
        into="$1"
        ;;
      --force)
        force=1
        ;;
      *)
        die "unknown argument for unpack: $1"
        ;;
    esac
    shift
  done

  local snap
  snap="$(newest_snapshot)"

  # Verify integrity first; refuse a corrupt archive outright.
  verify_archive "$snap" || die "refusing to unpack corrupt archive: $snap"

  mkdir -p "$into" || die "cannot create target directory: $into"

  # Refuse before touching anything when cache/ or data/ would be overwritten.
  local d
  for d in "${CORPUS_DIRS[@]}"; do
    if needs_force "$into/$d" && (( force == 0 )); then
      die "$into/$d already exists and is non-empty — pass --force to replace it"
    fi
  done

  # Extract into a staging directory first, then move each corpus directory into
  # place, so a failure can never leave a half-extracted tree behind.
  local staging
  staging="$(mktemp -d "$into/.coops-unpack.XXXXXX")" \
    || die "cannot create staging directory in $into"

  if ! tar -xzf "$snap" -C "$staging"; then
    rm -rf "$staging"
    die "failed to extract $snap"
  fi

  for d in "${CORPUS_DIRS[@]}"; do
    if [[ ! -d "$staging/$d" ]]; then
      rm -rf "$staging"
      die "archive $snap has no top-level $d/ directory"
    fi
  done

  for d in "${CORPUS_DIRS[@]}"; do
    rm -rf "$into/$d"
    mv "$staging/$d" "$into/$d" \
      || { rm -rf "$staging"; die "failed to move $d into $into"; }
  done

  rm -rf "$staging"
  info "unpacked: $snap -> $into"
}

cmd_list() {
  if [[ ! -d "$SNAPSHOT_DIR" ]]; then
    info "no snapshots found (directory does not exist: $SNAPSHOT_DIR)"
    return 0
  fi

  local found=0 s
  while IFS= read -r s; do
    [[ -n "$s" ]] || continue
    found=1
    printf '%-38s %10s %10s\n' \
      "$(basename "$s")" \
      "$(du -h "$s" | cut -f1)" \
      "$(human_age "$(stat -c %Y "$s")")"
  done < <(sorted_snapshots "$SNAPSHOT_DIR")

  if (( found == 0 )); then
    info "no snapshots found in $SNAPSHOT_DIR"
  fi
}

cmd_verify() {
  (( $# >= 1 )) || die "verify requires a snapshot name or path"
  local snap
  snap="$(resolve_snapshot "$1")"
  verify_archive "$snap" || exit 1
  info "ok: $snap"
}

# Checks a snapshot's recorded checksum and archive structure. Returns non-zero
# on any failure (with a message); extracts nothing.
verify_archive() {
  local snap="$1" checksum dir base
  [[ -f "$snap" ]] || { printf 'error: snapshot not found: %s\n' "$snap" >&2; return 1; }

  checksum="${snap}.sha256"
  [[ -f "$checksum" ]] || { printf 'error: checksum file missing: %s\n' "$checksum" >&2; return 1; }

  dir="$(dirname "$snap")"
  base="$(basename "$snap")"
  if ! ( cd "$dir" && sha256sum -c "$base.sha256" ); then
    printf 'error: checksum mismatch — snapshot is corrupt: %s\n' "$snap" >&2
    return 1
  fi

  if ! tar -tzf "$snap" >/dev/null 2>&1; then
    printf 'error: not a valid tar.gz archive: %s\n' "$snap" >&2
    return 1
  fi
}

# --- Dispatch ----------------------------------------------------------------

cmd="${1:-}"
shift || true

case "$cmd" in
  pack)   cmd_pack "$@" ;;
  unpack) cmd_unpack "$@" ;;
  list)   cmd_list "$@" ;;
  verify) cmd_verify "$@" ;;
  -h|--help|help) usage ;;
  "") usage ;;
  *) die "unknown subcommand: $cmd" ;;
esac
