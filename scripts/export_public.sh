#!/usr/bin/env bash
# Build a sanitized, fresh-history export of this repository for public release.
#
# Why: publishing the working repository would expose its history and the
# operator's own domains. This script exports the current commit only, removes
# excluded paths, rewrites private values to placeholders, scans the result and
# starts a brand-new history. The working repository is never modified.
#
# Usage: scripts/export_public.sh <output-dir> [map-file]
#   map-file  default: ~/.slidein-export.map  (kept OUTSIDE the repository)
#             one "real-value=>placeholder" per line, '#' for comments.
set -euo pipefail

OUT="${1:?usage: $0 <output-dir> [map-file]}"
MAP="${2:-$HOME/.slidein-export.map}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

[ -f "$MAP" ] || { echo "error: map file not found: $MAP" >&2; exit 2; }
[ -z "$(git status --porcelain --untracked-files=no --ignore-submodules=all)" ] || { echo "error: commit or stash tracked changes first" >&2; exit 2; }
if [ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then echo "error: $OUT exists and is not empty" >&2; exit 2; fi
mkdir -p "$OUT"

echo "[1/6] exporting HEAD (no history)"
git archive HEAD | tar -x -C "$OUT"

echo "[2/6] removing excluded paths"
while IFS= read -r pat; do
  case "$pat" in ''|'#'*) continue ;; esac
  # shellcheck disable=SC2086
  (cd "$OUT" && rm -rf $pat) || true
done < scripts/export_excludes.txt

echo "[3/6] rewriting private values"
# Longest keys first so a domain is replaced before any shorter substring of it.
MAP_SORTED="$(mktemp)"; trap 'rm -f "$MAP_SORTED"' EXIT
grep -vE '^\s*(#|$)' "$MAP" | awk -F'=>' '{ print length($1) "\t" $0 }' | sort -rn | cut -f2- > "$MAP_SORTED"
export MAP_SORTED
find "$OUT" -type f -not -path '*/.git/*' -print0 | while IFS= read -r -d '' f; do
  grep -Iq . "$f" 2>/dev/null || continue            # skip binary and empty files
  perl -i -pe '
    BEGIN { open(M, "<", $ENV{MAP_SORTED}) or die; while (<M>) { chomp; my ($k,$v)=split(/=>/,$_,2); push @m,[$k,$v]; } }
    for my $p (@m) { my ($k,$v)=@$p; s/\Q$k\E/$v/g; }
    # Personal mailboxes -> placeholder (keep documented seed/test examples).
    s/([A-Za-z0-9._%+-]+)\@(gmail\.com|yahoo\.com|outlook\.com|hotmail\.com|icloud\.com|[A-Za-z0-9.-]+\.ac\.[a-z]{2})/($1 =~ m{^(seed[\w.]*|test|alex\.borrower|%)$}) ? "$1\@$2" : "person\@example.com"/ge;
  ' "$f"
done

echo "[4/6] verifying no mapped value survived"
LEFT=0
while IFS= read -r line; do
  key="${line%%=>*}"
  if grep -RIlF -- "$key" "$OUT" >/dev/null 2>&1; then echo "  LEAK: '$key' still present" >&2; LEFT=1; fi
done < "$MAP_SORTED"
[ "$LEFT" -eq 0 ] || { echo "error: private values remain in export" >&2; exit 3; }

echo "[5/6] scanning for secrets (gitleaks, no git history)"
if command -v gitleaks >/dev/null 2>&1; then
  gitleaks detect --no-git --no-banner --redact --source "$OUT" -c "$ROOT/.gitleaks.toml"
else
  echo "  warning: gitleaks not installed; skipped" >&2
fi

echo "[6/6] creating a fresh single-commit history"
git -C "$OUT" init -q -b main
git -C "$OUT" add -A
git -C "$OUT" -c user.name="Slidein Venture" -c user.email="noreply@users.noreply.github.com" \
  commit -q -m "Initial public release"
echo "done: $OUT"
