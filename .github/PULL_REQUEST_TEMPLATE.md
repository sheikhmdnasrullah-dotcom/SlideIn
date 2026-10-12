# Pull request

## Problem addressed
<!-- Link issue(s) or describe the defect/task. -->

## Changes made
<!-- Files and behavior changed. One concern per PR. -->

## Testing performed
<!-- Exact commands + results. New/updated regression tests for behavior changes. -->
- [ ] `go build ./... && go vet ./... && go test ./...`
- [ ] `python3 -m unittest discover -s deliverability/tests -p "test_*.py"`
- [ ] `.venv/bin/python -m pytest kumomta-lab/tests -q`
- [ ] `bash scripts/check-secrets.sh`
- [ ] `./doctor` (for stack-affecting changes)

## Security implications
<!-- Auth, tenancy, sending behavior, secrets, SSRF, injection — or "none". -->

## Documentation changes
<!-- README/ROADMAP/CHANGELOG/docs updated as needed. -->

## Breaking changes
<!-- API, config, or behavior breaks — or "none". -->
