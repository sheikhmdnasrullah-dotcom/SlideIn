# ECC installation record

ECC (`affaan-m/ECC`) is installed as a project-local engineering toolkit, not a prospect-research dependency.

- **Version:** 2.2.3
- **Revision:** `f3904009440af24f00617343910ee89714df8be3`
- **License:** MIT
- **Source:** `saas/external/ECC`
- **Kimi installation:** `saas/.kimi-code`
- **Install command:** `node external/ECC/scripts/ecc.js install --profile full --target kimi` from `saas`
- **Dependency install:** `npm ci --ignore-scripts --no-audit --no-fund` in `saas/external/ECC`
- **Supply-chain IOC scan:** passed; 229 files inspected
- **Doctor command:** `node external/ECC/scripts/ecc.js doctor --target kimi` from `saas`
- **Doctor result:** `Status: OK`, no issues; `checked=1, ok=1, warnings=0, errors=0`

The full-profile install completed 530 project-local operations. The Kimi adapter selected supported modules and skipped unsupported ones; the complete source remains vendored for inspection. No global hooks, model settings, authentication, or external provider configuration was changed.

ECC describes 71 agents, 311 skills, 97 commands, hooks, memory, and AgentShield. These are engineering resources—not 523 prospect tools. Its guidance to use subagents is not universally applicable; current user/project instructions take precedence. ECC must not enter per-prospect research fan-out, live sending, or a new customer dashboard.
