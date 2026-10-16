# SlideIn — Design System Specification

> **Authority note (2026-10-16):** This root file is a high-level summary created before the engagement capability was documented.
> Where it differs from `docs/` (canonical layout, ADR-0002), **`docs/` prevails**. Figures marked as targets here (placement %, latency, price/cost,
> thresholds) are **proposals, not confirmed requirements**. Prospect Engagement (reply → chat/voice → meeting booking):
> `docs/product/PROSPECT_ENGAGEMENT.md`.


> **Version:** 1.0.0  
> **Source of Truth:** Replicated completely from SlideIn Venture (`slidein-venture` / `sv to tanim.social`)  
> **Aesthetic Philosophy:** Minimal · Premium · Editorial · Technical · Architectural · Systematic  
> **Reference Benchmarks:** Linear, Apple, Stripe, Raycast, Vercel, Attio  

---

## 1. Visual Philosophy & Core Feeling

The SlideIn SaaS Command Hub shares the exact visual design system and tone architecture as the SlideIn Venture marketing site. It reads like a **precision technical instrument** and **product blueprint**, not a generic SaaS dashboard.

### What it IS:
- **Architectural & Blueprint:** Hairlines, fine measurement ticks, mono coordinates, structural section rules (`01 — Label`).
- **Warm Editorial Contrast:** Natural paper-derived grounds and warm graphite, never harsh digital black or sterile pure white.
- **Micro-Engineered Typography:** Display optical sizing, balanced line wrapping, negative display tracking, tabular figures for all data.
- **Restrained Color Density:** The brand orange is an accent that occupies ~1% of any viewport — never a loud splash or dominant field.

### What it is NOT:
- ❌ No generic startup templates or purple/cyan gradients.
- ❌ No unmotivated glassmorphism or floating neon blurs.
- ❌ No emoji used as interface icons (use hugeicons / lucide with 1.5px stroke).
- ❌ Never `#FFFFFF` or `#000000` anywhere, even inside hairlines or shadows.

---

## 2. Color System: OKLCH & The Tone Contract

All colors are defined in **OKLCH** for perceptual uniformity. Hex and HSL ramps drift unevenly across mid-tones; OKLCH ensures the material reads consistently across all lighting conditions.

### 2.1 The Brand Orange Contract (Hue 42.28)
`--color-brand` is derived directly from `#FF6200` converted to OKLCH:
$$\text{#FF6200} \longrightarrow \text{oklch}(0.6908 \;\; 0.2074 \;\; 42.28)$$

The hue **42.28** is held strictly constant across every derived token. There is never a "second orange".

| Token | OKLCH Value | Role & Contrast Rating |
|---|---|---|
| `--color-brand` | `oklch(0.691 0.207 42.28)` | Brand fill & graphic strokes. 2.73:1 on paper (Fails text AA). 6.22:1 on graphite. |
| `--color-brand-hi` | `oklch(0.700 0.198 42.28)` | Orange text on dark/graphite surfaces (6.47:1 — passes AA). |
| `--color-signal` | `oklch(0.563 0.168 42.28)` | Orange text on light surfaces (4.50:1 — passes AA). |
| `--color-signal-deep` | `oklch(0.542 0.163 42.28)` | Orange text on `paper-100` panels (clears AA). |
| `--color-signal-deeper`| `oklch(0.522 0.158 42.28)` | Orange text on `paper-200` wells (clears AA). |
| `--color-ember` | `oklch(0.380 0.120 42.28)` | Dark borders & pressed states. Never text. |
| `--color-brand-soft` | `oklch(0.691 0.207 42.28 / 8%)` | Subtle orange tinted backgrounds. |

### 2.2 Neutral Ramps: Paper, Ink, and Ash

#### Paper Ramp (Light Surfaces & Wells)
- `--color-paper-25`: `oklch(0.978 0.004 85)` — Highest light; raised cards.
- `--color-paper-50`: `oklch(0.968 0.006 85)` — Base page fill.
- `--color-paper-100`: `oklch(0.945 0.008 84)` — Inset wells, nested cards.
- `--color-paper-200`: `oklch(0.915 0.010 83)` — Code blocks, terminal ground.
- `--color-bone-300`: `oklch(0.868 0.012 82)` — Structural hairlines & dividers.
- `--color-bone-400`: `oklch(0.790 0.014 80)` — Disabled affordances, placeholder tokens.

#### Ink Ramp (Dark Surfaces & Light Text)
- `--color-slate-500`: `oklch(0.545 0.016 75)` — Secondary text on light panels (4.52:1 AA).
- `--color-slate-600`: `oklch(0.470 0.018 74)` — High-contrast body copy on light panels.
- `--color-graphite-700`: `oklch(0.290 0.013 72)` — Raised card on dark bands.
- `--color-graphite-800`: `oklch(0.235 0.012 70)` — Dark panel tint.
- `--color-graphite-900`: `oklch(0.185 0.011 68)` — Dark section base.
- `--color-ink`: `oklch(0.155 0.010 66)` — Primary text on light panels (17.83:1).
- `--color-ink-deep`: `oklch(0.115 0.009 64)` — Darkest surface in the entire application.

#### Ash Ramp (Muted Text on Dark Surfaces)
- `--color-ash-200`: `oklch(0.850 0.010 80)` — Primary text on dark surfaces.
- `--color-ash-300`: `oklch(0.780 0.010 80)` — Secondary text on `graphite-900` (8.48:1).
- `--color-ash-400`: `oklch(0.720 0.010 80)` — Muted text on `ink-deep` (8.20:1).
- `--color-ash-500`: `oklch(0.620 0.012 80)` — De-emphasized labels on dark surfaces.

---

## 3. The Two Immutable Rules of Contrast

### Rule 1: `--accent` vs. `--accent-vivid`
The full-chroma brand orange (`--color-brand` / `--accent-vivid`) reaches only **2.73:1** against paper. It fails WCAG AA text contrast at **any size**, including 64px display headlines.
- **For any text element:** Always use `--accent` (or `--color-flame` / `--text-accent`), which resolves to `signal` (light) or `brand-hi` (dark) to guarantee $\ge 4.5:1$ contrast.
- **For fills, badges, and strokes only:** Use `--accent-vivid`.

### Rule 2: `--faint` is NOT a text tier
`--faint` reaches only 1.76:1 on paper-50. It is reserved strictly for non-text affordances (decorative ticks, disabled borders, icons). If setting text, use `--muted`.

---

## 4. The Two-Axis Architecture: Theme × Tone

| Axis | Values | Managed By | Purpose |
|---|---|---|---|
| **Theme** | `day` · `night` | `.dark` class on `<html>` | Macro canvas material: Warm Paper vs. Graphite Ink. |
| **Tone** | `base` · `raised` · `anchor` · `terminal` | `<Section tone="...">` | Band value rhythm. Decides depth relative to sibling sections. |

### Component Contract Names
Components must consume semantic tokens rather than raw colors or Tailwind dark modifiers:
- `--surface`: Raised card fill on the active band.
- `--surface-2`: Inset well inside a card.
- `--on-surface`: Primary text and hairline ink.
- `--muted`: Secondary text ($\ge 4.5:1$).
- `--faint`: Non-text structural marks (ticks, frames).
- `--rule` / `--rule-strong`: Hairline and border dividers.
- `--accent`: The contrast-compliant orange text token.
- `--accent-vivid`: The solid orange fill/stroke token.
- `--status-live`: Precision green for active/delivering states.
- `--status-warn`: Amber for rate limits / warmup warnings.
- `--status-danger`: Coral/red for hard bounces / circuit breaker triggers.

---

## 5. Typography

SlideIn employs a 3-register typographic hierarchy:

| Level | Typeface | CSS Role Class | Usage |
|---|---|---|---|
| **Editorial Display** | Fraunces (variable) | `.font-display-xl/-md/-sm` | High-impact metrics, section headlines, brand wordmark |
| **Interface / Body** | Switzer / Geist Sans | `.font-body` | Form fields, tables, body paragraphs, buttons |
| **Technical Metadata**| Monospace | `.font-label` | Coordinates, IDs, timestamps, tabular metrics |

### Typographic Rules:
1. **Fraunces Optical Sizing (`opsz`):** Display sizes use `opsz` 24–72 with zero softness (`SOFT 0`) for crispness.
2. **Tabular Figures:** All counts, rates, dates, and currency values must include `font-variant-numeric: tabular-nums`.
3. **No Raw Tracking:** Apply role classes (`.font-label`, `.font-body`), never ad-hoc `tracking-[0.2em]`.

---

## 6. Brand Wordmark & System Primitives

### 6.1 The Wordmark (Live Text Lockup)
SlideIn does **not** use an icon logo. The identity is a live-text wordmark:
```tsx
<span className="wordmark">
  <span className="wordmark-name">SlideIn</span>
  <span className="wordmark-qualifier">OS</span>
</span>
```
- **Wordmark Name:** Set in Fraunces display serif, kerned tightly (`-0.022em`), colored with `--on-surface`.
- **Qualifier:** Set in monospace uppercase, widely tracked (`var(--tracking-label)`), colored with `--accent`, optically raised onto the serif's x-height (`translateY(-0.34em)`).

### 6.2 Architectural System Primitives
- **`MonoLabel`:** Technical metadata chip formatted in uppercase mono.
- **`SectionRule`:** Structural divider following `NN — Label` on the left, a hairline rule, and a right-aligned coordinate.
- **`CornerBrackets`:** 10px blueprint corner brackets framing critical cards.
- **`Ticks`:** Precision measurement tick marks along card edges.
- **`.btn-premium`:** Tactile button with subtle elevation, light sweep, and physical press states. Card radius is 8px–12px for dense console views.

---

## 7. Engagement Surfaces (chat, booking, notifications, handoff)

Future customer-facing engagement screens follow this system and the marketing `design-system.md`. Open brand decisions (client vs SlideIn brand, logo-file vs wordmark conflict, tone of voice, chat pattern):
`docs/product/PROSPECT_ENGAGEMENT.md` §10 and `docs/project/OPEN_QUESTIONS.md` §E. Outreach/reply emails stay plain text.
