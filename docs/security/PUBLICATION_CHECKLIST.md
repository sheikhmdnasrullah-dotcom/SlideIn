# Publication Checklist

Preflight gate for making any part of this repository public. Nothing is
pushed, no visibility is changed, and no new remote is added until the
owner explicitly approves this checklist with a completed run attached.

## 1. Secret scan (must pass)

```bash
bash scripts/check-secrets.sh
```

- [ ] Script exits 0: no secret-bearing file tracked, no `BEGIN ... PRIVATE
      KEY` material in tracked files.
- [ ] `git ls-files` reviewed line by line: every tracked path is intended
      for publication.
- [ ] `.env.example` contains placeholders only (verified: no values).
- [ ] No credentials, tokens, session secrets, or private URLs in docs,
      comments, commit messages, or test fixtures.

## 2. Git history (must pass)

- [ ] `git log --all --stat` reviewed: no secret-bearing path ever tracked
      (a clean worktree is not proof of a clean history).
- [ ] Decision recorded for `refs/agents/*` checkpoint data (lead CSVs +
      session logs, local-only): strip the ref or keep local-only before
      any remote is added.
- [ ] Commit messages suitable for public history (current `main` messages
      are not — fresh publication history required).
- [ ] Publication uses a fresh history; the old local history stays
      local-only (owner approval required for the exact method).

## 3. Excluded from publication (must hold)

Never tracked, never pushed:

- `.env`, `*/config.json`, `*/config.production.json`,
  `warmup-engine/accounts.json`, `gophish-config-production.json`
- `*.db`, `*.log`, `*.pem`, `*.key`, `kumomta-lab/secrets/`
- Lead lists and prospect data: `*.csv`, `Leads to Mail/`,
  `conversations/`, `bash_events/`
- Nested repos (own history): `project/`, `workspace-app/`,
  `kumomta-src/`, `node_modules/`, venvs
- `config/kumomta_policy.lua` (dead header-forgery prototype, excluded
  by `.gitignore`)
- Owner/agent working docs: `AGENTS.md`, `CLAUDE.md`, `PROJECT_POLICY.md`,
  `CONVENTIONS.md`, `EMAIL_SENDING_POLICY.md`, `.aider*`, `.kilo/`, `.claude/`

Verify with: `git ls-files | grep -E '\.(db|log|pem|key|csv)$|\.env$|config\.json$|accounts\.json$'` returns nothing.

## 4. Operational details (review)

- [ ] VPS addresses, tunnel IDs, Grafana notes, and `ssh` strings in
      docs/code are intentional or redacted (see audit S8).
- [ ] Sender domains/profiles in examples are the owner's own public
      identities (acceptable) — no customer or third-party data.
- [ ] Screenshots/diagrams (if any) contain no secrets, customer records,
      private dashboards, or internal logs.

## 5. Tests and build (must pass)

```bash
go build ./... && go vet ./... && go test ./...
python3 -m unittest discover -s deliverability/tests -p "test_*.py"
.venv/bin/python -m pytest kumomta-lab/tests -q
bash scripts/check-secrets.sh
```

- [ ] All green; product-api suite green in CI (needs Postgres locally).
- [ ] No test sends real email by default (`verify_placement.py` and
      `verify_template.py` are never run without owner approval).

## 6. Publication mechanics (owner approval)

- [ ] Repository name, description, and license approved.
- [ ] Exact file list and exact commands for publication recorded.
- [ ] After push: verify URL, branch, README rendering, license display,
      and CI status.
