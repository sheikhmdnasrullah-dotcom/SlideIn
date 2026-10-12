# UX Patterns & Design Language

> This document defines the visual and interaction language for Acquisition OS.
> The product should feel premium, calm, intelligent, fast, modern, confident, enterprise-grade.

---

## 1. Design principles

1. **Hierarchy over clutter.** Important things should feel important.
2. **Whitespace is a feature.** Generous padding, clear sections.
3. **Typography-first.** Excellent type scale, clear hierarchy.
4. **Subtle motion.** Meaningful transitions, not decoration.
5. **Intelligent empty states.** Every empty state guides the user.
6. **Command palette.** Global `Cmd+K` for navigation and actions.
7. **Keyboard shortcuts.** Power-user efficiency.
8. **Contextual actions.** Actions appear where relevant, not in giant toolbars.
9. **Real-time, naturally.** Updates appear without refresh.
10. **No fake badges.** "AI" badges only where AI is genuinely involved.

---

## 2. Color system

```css
:root {
    /* Neutrals */
    --gray-50: #f8f9fa;
    --gray-100: #f1f3f5;
    --gray-200: #e9ecef;
    --gray-300: #dee2e6;
    --gray-400: #ced4da;
    --gray-500: #adb5bd;
    --gray-600: #6c757d;
    --gray-700: #495057;
    --gray-800: #343a40;
    --gray-900: #212529;

    /* Brand (configurable per org) */
    --brand-primary: #0f4c81;       /* Deep navy */
    --brand-secondary: #3b82f6;     /* Blue */
    --brand-accent: #10b981;        /* Green - for positive signals */
    --brand-warning: #f59e0b;       /* Amber - for attention */
    --brand-danger: #ef4444;        /* Red - for critical */
    --brand-success: #10b981;       /* Green - for success */

    /* Semantic */
    --bg-primary: #ffffff;
    --bg-secondary: #f8f9fa;
    --bg-tertiary: #f1f3f5;
    --text-primary: #212529;
    --text-secondary: #6c757d;
    --text-tertiary: #adb5bd;
    --border: #e9ecef;
    --border-hover: #ced4da;

    /* Shadows */
    --shadow-sm: 0 1px 2px 0 rgba(0,0,0,0.05);
    --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1);
    --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1);
}
```

**Constraints:**
- No rainbow charts.
- No meaningless gradients.
- Maximum 3 levels of elevation.
- No bright colors for non-semantic elements.

---

## 3. Typography

```css
:root {
    /* Type scale */
    --text-xs: 0.75rem;    /* 12px */
    --text-sm: 0.875rem;   /* 14px */
    --text-base: 1rem;     /* 16px */
    --text-lg: 1.125rem;   /* 18px */
    --text-xl: 1.25rem;    /* 20px */
    --text-2xl: 1.5rem;    /* 24px */
    --text-3xl: 1.875rem;  /* 30px */
    --text-4xl: 2.25rem;   /* 36px */

    /* Font weights */
    --font-normal: 400;
    --font-medium: 500;
    --font-semibold: 600;
    --font-bold: 700;

    /* Line heights */
    --leading-tight: 1.25;
    --leading-normal: 1.5;
    --leading-relaxed: 1.75;

    /* Font families */
    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
}
```

**Rules:**
- Maximum 3 font weights per screen.
- Never more than 4 type sizes per component.
- Use tabular numbers for metrics.

---

## 4. Spacing

```css
:root {
    --space-1: 0.25rem;   /* 4px */
    --space-2: 0.5rem;    /* 8px */
    --space-3: 0.75rem;   /* 12px */
    --space-4: 1rem;      /* 16px */
    --space-5: 1.5rem;    /* 24px */
    --space-6: 2rem;      /* 32px */
    --space-8: 3rem;      /* 48px */
    --space-10: 4rem;     /* 64px */
    --space-12: 6rem;     /* 96px */
}
```

---

## 5. Components

### Buttons

```css
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-sm);
    font-weight: var(--font-medium);
    border-radius: 0.375rem;
    border: 1px solid transparent;
    cursor: pointer;
    transition: all 150ms ease;
}

.btn-primary {
    background-color: var(--brand-primary);
    color: white;
}
.btn-primary:hover {
    background-color: var(--brand-secondary);
}

.btn-secondary {
    background-color: white;
    color: var(--text-primary);
    border-color: var(--border);
}
.btn-secondary:hover {
    background-color: var(--bg-secondary);
}

.btn-ghost {
    background-color: transparent;
    color: var(--text-secondary);
}
.btn-ghost:hover {
    background-color: var(--bg-secondary);
    color: var(--text-primary);
}
```

### Cards

```css
.card {
    background-color: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    padding: var(--space-5);
    box-shadow: var(--shadow-sm);
    transition: box-shadow 150ms ease;
}

.card:hover {
    box-shadow: var(--shadow-md);
}
```

### Tables

```css
.table-container {
    width: 100%;
    overflow-x: auto;
    border: 1px solid var(--border);
    border-radius: 0.5rem;
}

.table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
}

.table th {
    text-align: left;
    padding: var(--space-3) var(--space-4);
    font-weight: var(--font-medium);
    color: var(--text-secondary);
    background-color: var(--bg-secondary);
    border-bottom: 1px solid var(--border);
}

.table td {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--border);
}

.table tr:last-child td {
    border-bottom: none;
}

.table tr:hover td {
    background-color: var(--bg-secondary);
}
```

### Timeline

```css
.timeline {
    position: relative;
    padding-left: var(--space-6);
}

.timeline::before {
    content: '';
    position: absolute;
    left: 0.375rem;
    top: 0;
    bottom: 0;
    width: 2px;
    background-color: var(--border);
}

.timeline-item {
    position: relative;
    padding-bottom: var(--space-5);
}

.timeline-item::before {
    content: '';
    position: absolute;
    left: calc(-1 * var(--space-6) + 0.25rem);
    top: 0.25rem;
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background-color: var(--brand-secondary);
}

.timeline-item.buying-signal::before {
    background-color: var(--brand-success);
}

.timeline-item.objection::before {
    background-color: var(--brand-warning);
}

.timeline-item.intent::before {
    background-color: var(--brand-primary);
}
```

---

## 6. Key screens

### Command Center

```
┌─────────────────────────────────────────────────────────────┐
│  Acquisition OS                                    John ▼  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Good morning, John                                         │
│  Your acquisition system worked overnight.                  │
│  ─────────────────────────────────────────                 │
│  12 new opportunities discovered                            │
│  4 high-fit prospects researched                             │
│  7 borrower conversations active                             │
│  2 prospects showing strong intent                           │
│  1 meeting booked                                            │
│  3 conversations need your attention                         │
│  ─────────────────────────────────────────                 │
│                                                             │
│  TODAY'S PRIORITIES                                         │
│                                                             │
│  ① Sarah — ready to discuss financing                       │
│     → Review conversation                                   │
│     Strong purchase intent + active conversation             │
│                                                             │
│  ② Mike — asked about refinance options                     │
│     → AI drafted response                                   │
│     Question answered by AI, awaiting your approval          │
│                                                             │
│  ③ 4 prospects — high fit, not contacted                    │
│     → Review outreach                                       │
│     Research complete, awaiting your review                  │
│                                                             │
│  ─────────────────────────────────────────                 │
│                                                             │
│  SYSTEM ACTIVITY                                            │
│  ✓ Published today's article                                │
│  ✓ Generated LinkedIn post                                  │
│  ✓ Updated calculator funnel                                │
│  ✓ Followed up with 8 opportunities                         │
│  ✓ Detected 2 new buying signals                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Pipeline view

```
┌─────────────────────────────────────────────────────────────┐
│  Pipeline                                              [+]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  DISCOVERED (12)                                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                   │
│  │  John    │ │  Sarah   │ │  Mike    │                   │
│  │  72      │ │  85      │ │  68      │                   │
│  │  →       │ │  →       │ │  →       │                   │
│  └──────────┘ └──────────┘ └──────────┘                   │
│                                                             │
│  RESEARCHED (8)                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                   │
│  │  Lisa    │ │  Tom     │ │  Amy     │                   │
│  │  91      │ │  77      │ │  83      │                   │
│  │  →       │ │  →       │ │  →       │                   │
│  └──────────┘ └──────────┘ └──────────┘                   │
│                                                             │
│  QUALIFIED (15)                                             │
│  ...                                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Opportunity Profile

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back to Pipeline           John Smith               [...]│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Opportunity Score  82                                      │
│  State              QUALIFIED → BOOKING                     │
│                                                             │
│  PERSON                                                     │
│  Name          John Smith                                   │
│  Email         john@example.com                             │
│  Phone         +1-555-0123                                  │
│  Location      Austin, TX                                   │
│                                                             │
│  FIT                                                        │
│  ICP Match         25/25                                    │
│  Location Match    20/20                                    │
│  Timeframe         15/15                                    │
│  Property Range    10/10                                    │
│  Segment           First-time buyer                         │
│  ─────────────────────────────────────                     │
│  Total             70/100                                   │
│                                                             │
│  INTENT                                                      │
│  Level             High                                     │
│  Signals:                                                    │
│    • Planning to buy within 3 months                        │
│    • Downloaded affordability report                        │
│    • Asked about rate lock                                  │
│                                                             │
│  CONVERSATION                                                │
│  ┌─────────────────────────────────────────────┐           │
│  │  BUYING SIGNAL                              │           │
│  │  "Planning to buy within 3 months."         │           │
│  │                                              │           │
│  │  AI RECOMMENDATION                          │           │
│  │  Answer question → provide relevant          │           │
│  │  resource → offer consultation.              │           │
│  └─────────────────────────────────────────────┘           │
│                                                             │
│  NEXT BEST ACTION                                            │
│  Send calendar invitation                                    │
│  Strong purchase intent + active conversation + defined      │
│  timeframe                                                   │
│                                                             │
│  WHY 82?                                                     │
│  +25 ICP match                                               │
│  +20 location match                                          │
│  +15 purchase timeframe                                      │
│  +10 calculator engagement                                   │
│  +10 reply intent                                            │
│  +7 property value match                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Conversation Intelligence

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back to Opportunity    Conversation with John Smith      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  State: ENGAGED                                             │
│  Intent: HIGH                                               │
│  Advisor: John Smith                                        │
│                                                             │
│  ─────────────────────────────────────────                 │
│                                                             │
│  Sep 28, 2026                                               │
│  ─────────────────────────────────────────                 │
│  OUTBOUND (AI-assisted)                                     │
│  Subject: Austin first-time buyer programs — quick question │
│                                                             │
│  Hi John,                                                   │
│                                                             │
│  I saw you recently started looking at homes in Austin...   │
│                                                             │
│  ─────────────────────────────────────────                 │
│                                                             │
│  Sep 29, 2026                                               │
│  ─────────────────────────────────────────                 │
│  INBOUND                                                   │
│                                                             │
│  "Planning to buy within 3 months."                         │
│                                                             │
│  ┌─────────────────────────────────────────────┐           │
│  │  BUYING SIGNAL                              │           │
│  │  "Planning to buy within 3 months."         │           │
│  │                                              │           │
│  │  OBJECTION                                  │           │
│  │  "Concerned about monthly payment."         │           │
│  │                                              │           │
│  │  QUESTION                                   │           │
│  │  "Do I need 20% down?"                     │           │
│  └─────────────────────────────────────────────┘           │
│                                                             │
│  ─────────────────────────────────────────                 │
│                                                             │
│  Sep 29, 2026                                               │
│  ─────────────────────────────────────────                 │
│  OUTBOUND (AI draft, approved by John)                      │
│                                                             │
│  Hi John,                                                   │
│                                                             │
│  Great question! Down payment assistance programs...        │
│                                                             │
│  [View full conversation]                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Design system tokens (summary)

```json
{
    "colors": {
        "brand": {
            "primary": "#0f4c81",
            "secondary": "#3b82f6",
            "accent": "#10b981",
            "warning": "#f59e0b",
            "danger": "#ef4444"
        },
        "neutral": {
            "bg-primary": "#ffffff",
            "bg-secondary": "#f8f9fa",
            "text-primary": "#212529",
            "text-secondary": "#6c757d",
            "border": "#e9ecef"
        }
    },
    "typography": {
        "font-sans": "'Inter', -apple-system, sans-serif",
        "font-mono": "'JetBrains Mono', monospace",
        "type-scale": {
            "xs": "0.75rem",
            "sm": "0.875rem",
            "base": "1rem",
            "lg": "1.125rem",
            "xl": "1.25rem",
            "2xl": "1.5rem",
            "3xl": "1.875rem",
            "4xl": "2.25rem"
        }
    },
    "spacing": {
        "1": "0.25rem",
        "2": "0.5rem",
        "3": "0.75rem",
        "4": "1rem",
        "5": "1.5rem",
        "6": "2rem",
        "8": "3rem",
        "10": "4rem",
        "12": "6rem"
    },
    "shadows": {
        "sm": "0 1px 2px 0 rgba(0,0,0,0.05)",
        "md": "0 4px 6px -1px rgba(0,0,0,0.1)",
        "lg": "0 10px 15px -3px rgba(0,0,0,0.1)"
    }
}
```

---

*End of UX Patterns & Design Language*
