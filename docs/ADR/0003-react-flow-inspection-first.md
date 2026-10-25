# ADR-0003: React Flow — inspection first, editor second

Status: accepted (2026-10-26).

## Context
React Flow was proposed for the visual workflow editor. The npm dependency
`@xyflow/react` v12 (MIT core) is already present in marketing-site.

## Decision
MVP slice renders persisted workflow definitions read-only (custom nodes:
trigger/agent/tool/condition/approval/output with execution status). Editing is
enabled only after the visual<->execution mapping is proven for the supported
node subset. Validation (required inputs, type compatibility, cycles,
approval gates) runs server-side on the persisted definition; invalid graphs
never execute.

## Consequences
The visual layer can never diverge from execution: one persisted definition,
one mapping, one executor (LangGraph service).
