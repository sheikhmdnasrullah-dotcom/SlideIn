# SLIDEIN — UPDATED BRAND KIT & DESIGN STANDARDS

> **2026-10-26 implementation notice:** This document is not authorization for another workspace redesign. It conflicts with the current `slidein-app` implementation, which uses Inter Tight and copied hex/semantic tokens including pure white. Preserve the implemented orange/neutral editorial system while the token documentation is reconciled deliberately. Canonical product and architecture documents take precedence for current implementation work.

> **Document Class:** Historical Brand System Proposal  
> **Source of Truth:** Replicated from SlideIn Venture (`sv to tanim.social`) & Console Architecture  
> **Aesthetic Archetype:** Minimal · Architectural · Editorial · Technical · Blueprint  
> **Version:** 1.0.0  
> **Date:** 2026-10-16  

---

## 1. Brand Identity & Wordmark

SlideIn does **not** employ a generic icon mark or standalone symbol. The brand identity is a **live-text typographic wordmark**:

```tsx
<span className="wordmark">
  <span className="wordmark-name">SlideIn</span>
  <span className="wordmark-qualifier">OS</span>
</span>
```

### 1.1 Typographic Decisions
- **`wordmark-name` ("SlideIn"):**
  - Face: `Fraunces` variable display serif (`font-family: var(--font-display)`).
  - Optical settings: `opsz: 24`, `SOFT: 6`, `WONK: 0`.
  - Kerning: `-0.022em` tight display tracking.
  - Color: Consumes `--on-surface` (automatically inverts across day and night themes).
  - Optical overhang: `-0.02em` left margin compensation for the rounded 'S'.
- **`wordmark-qualifier` ("OS" or "Venture"):**
  - Face: Monospace (`font-family: var(--font-mono)`).
  - Treatment: Uppercase, wide tracking (`var(--tracking-label)`), scaled to `0.5em`.
  - Color: `--text-accent` / `--accent` (brand orange clearing AA contrast).
  - Optical alignment: Raised `translateY(-0.34em)` to sit precisely on the serif's x-height.

---

## 2. Color Palette & The OKLCH Tone Contract

All colors are defined strictly in **OKLCH** to prevent mid-tone saturation drift:

### 2.1 Brand Orange (Hue 42.28)
- Exact brand hex `#FF6200` converts to `oklch(0.6908 0.2074 42.28)`.
- **The Contrast Rule 1:**
  - `--color-brand` (`oklch(0.691 0.207 42.28)`) reaches only **2.73:1** against light paper. It is **STRICTLY PROHIBITED** for body and label text.
  - Text must consume `--accent` / `--text-accent`, which dynamically resolves to `--color-signal` (`oklch(0.563 0.168 42.28)`) on light panels (clearing 4.5:1 AA) and `--color-brand-hi` (`oklch(0.700 0.198 42.28)`) on dark graphite.
  - `--accent-vivid` is reserved strictly for graphic fills, active badges, and borders.

### 2.2 Neutral Ramps
- **Paper Ramp (Day Mode Surfaces):**
  - `--color-paper-25`: `oklch(0.978 0.004 85)` — Raised card surface.
  - `--color-paper-50`: `oklch(0.968 0.006 85)` — Base page fill.
  - `--color-paper-100`: `oklch(0.945 0.008 84)` — Inset well, table headers.
  - `--color-paper-200`: `oklch(0.915 0.010 83)` — Code blocks, terminal backgrounds.
  - `--color-bone-300`: `oklch(0.868 0.012 82)` — Structural hairlines and dividing rules.
- **Ink Ramp (Night Mode Surfaces & Dark Ink):**
  - `--color-slate-500`: `oklch(0.545 0.016 75)` — Secondary text on light panels.
  - `--color-slate-600`: `oklch(0.470 0.018 74)` — High-contrast body copy.
  - `--color-graphite-700`: `oklch(0.290 0.013 72)` — Raised card on dark bands.
  - `--color-graphite-900`: `oklch(0.185 0.011 68)` — Dark section base.
  - `--color-ink`: `oklch(0.155 0.010 66)` — Primary day text (17.83:1).
  - `--color-ink-deep`: `oklch(0.115 0.009 64)` — Darkest ground in the application.

### 2.3 Prohibition of Pure Black and White
- **Never** `#FFFFFF` or `#000000` anywhere in the application.
- The lightest allowable token is `paper-25`; the darkest is `ink-deep`.

---

## 3. Blueprint Primitives & Architectural Aesthetics

The UI avoids generic SaaS tropes in favor of precision technical cues:
- **`CornerBrackets`:** 10px hairline brackets framing critical cards and data displays.
- **`Ticks`:** Measurement tick marks along card edges.
- **`SectionRule`:** Dividers structured as `NN — Section Label` on the left, a 1px rule, and a right-aligned coordinate.
- **Button System:** `.btn-premium` featuring a tactile surface, subtle elevation, and rounded-md to rounded-lg corners (8px–12px console standard).
