# Local Setup — SlideIn

> Verified 2026-10-12 on macOS: `./dev` → `./doctor` FULLY OPERATIONAL.

## Prerequisites

Go (1.24+), Python 3.12+, Node.js 20+, Docker Desktop. No PostgreSQL needed
unless you run the product-API suite (CI covers that).

## Quickstart

```bash
./dev
```

This bootstraps: Docker daemon check → Go build (`gophish_local`) →
infrastructure (`docker-compose.local.yml`: Mailpit :1025/:8025, Redis
:6379, KumoMTA :2587/:8029) → Go API :3333 → Unified API :8088 → Next.js
workspace :3000 (falls back to :3001 if occupied) → `./doctor` health
diagnostic (exit 0 = operational). Stop with `./stop`.

## Health check

```bash
./doctor
```

Expect HEALTHY across toolchains, databases, Docker services, and backends;
PostgreSQL and Warmup Engine report DEGRADED unless you run them (normal).

## API keys (Unified API :8088)

All `/v1/*` routes and the dashboard UI require the workspace API key. Each
database gets a random key on first seed — nothing is hardcoded.

```bash
python3 deliverability/cli.py show-key            # print key (keep secret)
curl -H "X-API-Key: $(python3 deliverability/cli.py show-key)" \
  http://127.0.0.1:8088/v1/status
open "http://127.0.0.1:8088/?api_key=$(python3 deliverability/cli.py show-key)"
python3 deliverability/cli.py rotate-key          # old key stops working
```

## End-to-end verification

```bash
python3 test_e2e_local_flow.py     # gate → KumoMTA → Mailpit → SQLite trace
python3 test_slidein_platform.py   # full platform incl. DKIM + inbound AI
```

Both send only to the local Mailpit sink (dummy `.local` recipients).
Recorded results: `TESTING.md`.

## Test suites

Full matrix: `TESTING.md`. Quick check:

```bash
go test ./...
python3 -m unittest discover -s deliverability/tests -p "test_*.py"
```

## Troubleshooting

- **Port conflicts**: `docker rm -f slidein-kumomta slidein-mailpit` for stale
  containers; `pkill -f gophish_local` for a stuck Go backend (path-scope to
  this checkout when others run nearby).
- **Docker Daemon DOWN**: `open -a Docker`, wait ~15 s, `docker info`.
- **KumoMTA 535**: user `outbound`, password `local-dev-password` (local
  default; production uses `KUMO_AUTH_PASS`).
- **Mailpit empty**: `docker logs slidein-kumomta --tail 50`; check the
  `mailpit` container is healthy; confirm local policy routes to the sink.
