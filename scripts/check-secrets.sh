#!/usr/bin/env bash
# check-secrets.sh — fails if secret-bearing files or key material are tracked
# by git.
#
# PROJECT_POLICY §2.1: secrets live only in local config/.env files and must
# never enter git history. This script is run in CI and can be run locally:
#
#     bash scripts/check-secrets.sh
set -uo pipefail

fail=0

# Files that must never be tracked (they hold live credentials).
FORBIDDEN_FILES=(
  .env
  config.json
  config.local.json
  config.production.json
  gophish-config-production.json
  deliverability/config.json
  deliverability/config.local.json
  deliverability/config.production.json
  warmup-engine/config.json
  warmup-engine/config.production.json
  warmup-engine/accounts.json
  gophish_admin.key
)

for f in "${FORBIDDEN_FILES[@]}"; do
  if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
    echo "FAIL: secret-bearing file is tracked by git: $f"
    fail=1
  fi
done

# Any tracked .env.* file other than the example template.
while IFS= read -r f; do
  case "$f" in
    .env.example) ;;
    *)
      echo "FAIL: unexpected env file tracked by git: $f"
      fail=1
      ;;
  esac
done < <(git ls-files '.env*' 2>/dev/null)

# Private key material must never be committed.
if git grep -nI -- 'BEGIN [A-Z ]*PRIVATE KEY' -- . >/dev/null 2>&1; then
  echo "FAIL: private key material found in tracked files:"
  git grep -nI -- 'BEGIN [A-Z ]*PRIVATE KEY' -- .
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "OK: no secret files or key material tracked by git."
fi
exit "$fail"
