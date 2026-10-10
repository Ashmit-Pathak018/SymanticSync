# SemanticSync — Design System

**Version:** 1.0

---

## Design Principles

1. **Semantic color:** Colors carry meaning — not decoration. Never use Danger red for success states.
2. **Token-first:** All colors, spacing, and typography are referenced via token names in code.
3. **Developer-density:** Information is dense; whitespace is earned by visual hierarchy, not default padding.
4. **Legibility:** Monospace for all values, IDs, SQL, and technical content.

---

## Color Tokens

### Core Palette

| Token Name | Hex | Usage |
|---|---|---|
| `primary` | `#315CFF` | CTA buttons, active nav items, links, focus rings |
| `nav` | `#111A3A` | Sidebar navigation background |
| `workspace` | `#F4F6FA` | Main content area background |
| `panel` | `#FFFFFF` | Cards, panels, modals |
| `border` | `#D8DEEA` | Borders, dividers, table lines |

### Semantic State Colors

| Token Name | Hex | Usage |
|---|---|---|
| `success` | `#2D9B62` | Resolved conflicts, valid policy, test passing |
| `warning` | `#C98A1B` | Pending conflicts, sync in progress, partial results |
| `danger` | `#D94B5B` | Flagged conflicts, validation errors, critical states |

### Text Colors

| Token Name | Hex | Usage |
|---|---|---|
| `text-primary` | `#1A1F36` | Main body text, headings |
| `text-secondary` | `#5A6075` | Labels, captions, metadata |
| `text-muted` | `#9AA0B2` | Placeholder text, disabled state |
| `text-inverse` | `#FFFFFF` | Text on dark backgrounds (nav, primary buttons) |

---

## Typography

### Font Stack

```css
/* UI Elements */
font-family: 'Inter', system-ui, -apple-system, sans-serif;

/* Code, SQL, IDs, Values */
font-family: 'JetBrains Mono', 'Fira Code', monospace;
```

### Type Scale

| Element | Size | Weight | Line Height |
|---|---|---|---|
| Page Title | 20px | 600 | 1.3 |
| Section Heading | 16px | 600 | 1.4 |
| Body | 14px | 400 | 1.5 |
| Caption / Label | 12px | 500 | 1.4 |
| Code | 13px | 400 | 1.6 |

---

## Spacing Scale

Uses a 4px base grid:

| Token | Value |
|---|---|
| `space-1` | 4px |
| `space-2` | 8px |
| `space-3` | 12px |
| `space-4` | 16px |
| `space-6` | 24px |
| `space-8` | 32px |

---

## Component Patterns

### Status Badges

Used for conflict status, sync state, and policy validation results:

```
┌──────────────────────┐
│ ✅ Resolved           │  → bg: success/10%, text: success, border: success/30%
│ ⏳ Pending            │  → bg: warning/10%, text: warning, border: warning/30%
│ 🔴 Flagged            │  → bg: danger/10%, text: danger, border: danger/30%
│ ✅ Valid              │  → success color
│ ❌ Invalid            │  → danger color
└──────────────────────┘
```

### Policy Selector Dropdown

```
[SUM ▼]
  ├── SUM      — INTEGER, REAL, NUMERIC
  ├── AVG      — INTEGER, REAL, NUMERIC
  ├── APPEND   — TEXT only
  ├── LWW      — Any type
  ├── REJECT   — Any type
  ├── MIN      — INTEGER, REAL, NUMERIC
  └── MAX      — INTEGER, REAL, NUMERIC
```

- Invalid selection → border turns `danger`, helper text appears
- Valid selection → border turns `success`, badge shows ✅ Valid

### Primary Button

```css
background: #315CFF
color: #FFFFFF
border-radius: 6px
padding: 8px 16px
font-weight: 600
font-size: 14px

hover: brightness(1.1)
active: brightness(0.95)
disabled: opacity 40%
```

### Conflict Card

```
┌────────────────────────────────────────────────┐  border: danger (flagged)
│ ⚡ products.quantity | row 1 | SUM              │  or success (resolved)
│ ──────────────────────────────────────────────  │
│ Base:  100        A: 115         B: 120         │  font: monospace
│ Resolved: 135     SUM additive delta merge      │
└────────────────────────────────────────────────┘
```

---

## Tailwind Configuration

```js
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: '#315CFF',
        nav: '#111A3A',
        workspace: '#F4F6FA',
        border: '#D8DEEA',
        success: '#2D9B62',
        warning: '#C98A1B',
        danger: '#D94B5B',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
};
```

---

## Icons

Use [Lucide Icons](https://lucide.dev/) — React library, consistent stroke weight.

| Icon | Usage |
|---|---|
| `<Database />` | Database entries |
| `<GitBranch />` | Replicas |
| `<Zap />` | Conflicts |
| `<RefreshCw />` | Sync |
| `<Terminal />` | SQL Console |
| `<BarChart2 />` | Benchmark |
| `<CheckCircle2 />` | Resolved |
| `<AlertCircle />` | Flagged / Error |
| `<Clock />` | Pending |

---

## Do / Don't

| ✅ Do | ❌ Don't |
|---|---|
| Use `danger` for error states | Use danger red for warnings |
| Monospace for values, IDs, SQL | Serif fonts anywhere |
| Use token names in Tailwind classes | Use raw hex in className |
| Keep sidebar width exactly 48px (icon) or 200px (expanded) | Arbitrary sidebar widths |
| Show validation inline immediately | Wait for form submission to show errors |
