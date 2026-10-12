# SLIDEIN DEVELOPMENT GUIDE & LOCAL SETUP

> **Local Development Workflow, Commands, and Conventions**  
> Status: Authoritative Guide  
> Version: 1.0.0

---

## 1. System Requirements & Runtimes

- **Node.js:** v20.x or v22.x (with `npm` / `npx`)
- **Python:** 3.10+ (with `venv`)
- **Docker & Docker Compose:** For running local lab MTA, sink MX, and databases
- **Go:** 1.22+ (for campaign engine)

---

## 2. Quickstart: Running Slidein Locally

### Step 1: Clone & Environment Configuration
```bash
cd "workspace-app"
cp .env.example .env.local
# Ensure required local API keys and database endpoints are populated
```

### Step 2: Start Local Infrastructure & Lab Services
From repository root:
```bash
# Boots local KumoMTA lab, Sink MX, and Mailpit
docker compose -f docker-compose.local.yml up -d

# Start local deliverability daemon (:8088)
python3 deliverability/server.py &
```

### Step 3: Start the Next.js Operational Console
```bash
cd workspace-app
npm install
npm run dev
# Dashboard opens on http://localhost:3000 (or :3001)
```

---

## 3. Core Development Commands

| Task | Command | Directory |
|---|---|---|
| Run Next.js console | `npm run dev` | `workspace-app/` |
| Build Next.js console | `npm run build` | `workspace-app/` |
| Lint codebase | `npm run lint` | `workspace-app/` |
| Run E2E Playwright tests | `npx playwright test` | `workspace-app/` |
| Run Deliverability tests | `python3 -m unittest discover deliverability/tests` | Root |
| Inspect Lab MTA Status | `curl http://localhost:8029/api/admin/status` | Root |
| Verify Local Deliverability | `python3 test_slidein_platform.py` | Root |

---

## 4. Coding Conventions & Quality Rules

1. **TypeScript Strictness:** No explicit `any` without documented reason. Use typed schemas (`zod`).
2. **Server-Side Security:** Never trust client-provided IDs. Always resolve tenant ID from authenticated session.
3. **Component Reusability:** Reuse shadcn / `@base-ui/react` primitives from `components/ui/`.
4. **No Direct Database Writes from Untrusted Agents:** Agent outputs must be validated by domain schemas before persistence.
