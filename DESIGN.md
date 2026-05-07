# DEX Studio — Design System

> Source of truth for visual design decisions. Token reference → [design-tokens.json](design-tokens.json). Live preview → [design-preview.html](design-preview.html).

______________________________________________________________________

## System Overview

DEX Studio is a self-hosted data/ML/AI control plane UI. The visual system is built on:

- **Reflex** (Python → React) — component model
- **Radix UI Themes** — semantic design tokens via `rx.theme(appearance="dark", accent_color="indigo", gray_color="slate", radius="medium")`
- **Fira Sans** — UI text (loaded via Google Fonts)
- **Fira Code** — monospace / code surfaces

The design language targets **developer-tool density**: information-rich tables and dashboards, not a marketing site. Reference points: Grafana, Linear, Vercel Dashboard.

______________________________________________________________________

## Color System

### Approach

All color values use **Radix UI semantic tokens** (`var(--gray-N)`, `var(--indigo-N)`, etc.). This gives automatic light/dark switching when `rx.theme(appearance=...)` changes, and AA-compliant contrast ratios at every step.

**Never hardcode hex values** in component code. The one exception is brand primary `#6366f1` for use outside Radix context (e.g. meta tags, og:image).

### Palette

| Role | Token | Use |
|------|-------|-----|
| Page background | `var(--gray-2)` | Content area |
| Sidebar/header | `var(--gray-1)` | Slightly lighter surface |
| Card surface | `var(--gray-2)` | Same as page — card defined by border |
| Border subtle | `var(--gray-4)` | Dividers, card outlines, sidebar edge |
| Border default | `var(--gray-6)` | Input outlines, stronger separators |
| Accent | `var(--indigo-9)` | Buttons, active states, icons |
| Accent hover | `var(--indigo-10)` | Hover on accent elements |
| Accent subtle | `var(--indigo-3)` | Icon container backgrounds |
| Text primary | `var(--gray-12)` | Headings |
| Text secondary | `var(--gray-11)` | Body, nav labels |
| Text muted | `var(--gray-9)` | Labels, metadata |
| Text faint | `var(--gray-7)` | Placeholders, disabled |
| Success | `var(--green-9)` | |
| Warning | `var(--amber-9)` | |
| Error | `var(--red-9)` | |

### Domain Colors

Each domain has a distinct accent for its icon/active states:

| Domain | Color | Token |
|--------|-------|-------|
| Data | Indigo | `var(--indigo-9)` |
| ML | Violet | `var(--violet-9)` |
| AI | Cyan | `var(--cyan-9)` |
| System | Orange | `var(--orange-9)` |
| Career | Teal | `var(--teal-9)` |

**Rule:** Domain color is used for icon tint and active nav indicator only. Card bodies, backgrounds, and text use neutral gray tokens regardless of domain.

______________________________________________________________________

## Typography

### Fonts

- **Fira Sans** — all UI text. Chosen because it's a developer-oriented humanist sans with optical balance at small sizes (11–14px). Regular (400), Medium (500), SemiBold (600), Bold (700) loaded.
- **Fira Code** — SQL console, code blocks, terminal output, pipeline YAML. Provides visual distinction for technical content.

**Bootstrap CSS is loaded but serves no purpose.** It was added during the NiceGUI era and should be removed — it adds ~30KB and can conflict with Radix resets.

### Scale (Radix size 1–8)

| Radix | px | Use |
|-------|----|-----|
| `size="1"` | 11px | Sub-labels, badge text, tiny metadata |
| `size="2"` | 13px | Table cells, nav sub-items, descriptions |
| `size="3"` | 14px | Default body text |
| `size="4"` | 16px | Slightly larger body, card titles |
| `size="5"` | 18px | Section headings (`page_shell` title) |
| `size="6"` | 20px | Metric card values |
| `size="7"` | 24px | Domain headings |
| `size="8"` | 30px | Hub title |

Heading weight: `weight="bold"` (700) for page titles, `weight="semibold"` (600) for section headings.

______________________________________________________________________

## Spacing

Radix's built-in numeric spacing scale maps to 4px base unit:

| Radix | px |
|-------|----|
| `1` | 4px |
| `2` | 8px |
| `3` | 12px |
| `4` | 16px |
| `5` | 20px |
| `6` | 24px |
| `8` | 32px |

**Convention in this codebase:**

- `padding="5"` on metric cards
- `padding="6"` on page content areas
- `padding_x="3"`, `padding_y="2"` on nav links
- `spacing="2"` on icon+label pairs, `spacing="4"` on form stacks

Do not mix Radix scale with hardcoded pixels in Reflex components.

______________________________________________________________________

## Border Radius

Radix radius scale with `radius="medium"` set globally:

| Token | px | Use |
|-------|----|-----|
| `var(--radius-1)` | 4px | Tiny chips, progress bars |
| `var(--radius-2)` | 6px | Icon containers, sub-nav active indicators |
| `var(--radius-3)` | 8px | Cards, modals, toasts |
| `var(--radius-4)` | 12px | Large cards (hub domain cards) |
| `9999px` | — | Pills, avatar circles |

______________________________________________________________________

## Motion

Keep animations purposeful. Only use on state changes the user triggered (open panel, submit form). Never animate on page load or scroll.

| Use case | Duration | Easing |
|----------|----------|--------|
| Hover state color/border | 120ms | linear |
| Nav link hover/active | 100–150ms | ease |
| Panel open/close | 200ms | ease-out-expo |
| Skeleton shimmer | 1500ms loop | ease-in-out |
| Streaming cursor blink | 1000ms step-end | — |

Motion CSS vars are defined in `design_tokens.py` but **are not injected** into the Reflex app (dead code). To activate them, add to `app.py`:

```python
app = rx.App(
    style={
        "--ease-out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
        "--duration-fast": "120ms",
        "--duration-normal": "200ms",
    }
)
```

______________________________________________________________________

## Component Conventions

### Cards

```python
# Standard metric card — use layout.metric_card(), not inline duplication
rx.box(
    ...,
    padding="5",
    background="var(--gray-2)",
    border="1px solid var(--gray-4)",
    border_radius="var(--radius-3)",
    _hover={
        "border_color": "var(--{accent}-6)",
        "box_shadow": "0 0 0 1px var(--{accent}-4), 0 2px 8px rgba(0,0,0,0.2)",
    },
    transition="all 0.15s ease",
)
```

### Sidebar Navigation

- Active domain: accent bg `var(--{accent}-2)`, accent text `var(--{accent}-11)`, icon bg `var(--{accent}-3)`
- Sub-nav active: 3px accent left bar + accent bg
- Hover: same accent-2 bg as active, no transform

### Page Shell

Every domain page uses `page_shell(title, *content)` from `layout.py`. The shell provides:

- Skip-to-main-content link (accessibility)
- Sidebar
- Sticky page header with breadcrumb + title
- Content area with `padding="6"`
- Toast overlay

### Empty States

Use the inline pattern (not the dead `empty_state.py` NiceGUI component):

```python
rx.center(
    rx.vstack(
        rx.icon("inbox", size=40, color="var(--gray-7)"),
        rx.text("No items found", weight="medium", color="var(--gray-10)"),
        rx.text("Descriptive sub-text.", size="2", color="var(--gray-8)"),
        align="center", spacing="2", padding_y="10",
    ),
)
```

### Status Badges

Use `layout.status_badge(value)` — maps status strings to Radix color schemes.

______________________________________________________________________

## Dead Code Inventory

18 component files in `src/dex_studio/components/` import `nicegui` and are **completely inert** in the Reflex app. Safe to delete.

| File | Replacement |
|------|-------------|
| `app_shell.py` | `layout.py:page_shell` |
| `badge.py` | `rx.badge()` + `layout.status_badge` |
| `breadcrumb.py` | `layout.py:page_shell(breadcrumb=...)` |
| `button.py` | `rx.button()` |
| `card.py` | `layout.py:metric_card` |
| `chat_message.py` | `copilot.py:_message_bubble` |
| `command_palette.py` | No Reflex equivalent yet |
| `data_table.py` | `rx.table.*` |
| `domain_sidebar.py` | `layout.py:sidebar` |
| `empty_state.py` | Inline pattern (see above) |
| `hub_nav.py` | No Reflex equivalent yet |
| `input.py` | `rx.input()`, `rx.text_area()` |
| `inspector_panel.py` | No Reflex equivalent yet |
| `metric_card.py` | `layout.py:metric_card` |
| `page_layout.py` | `layout.py:page_shell` |
| `status_badge.py` | `layout.py:status_badge` |
| `toast.py` | `layout.py:toast_overlay` |
| `tool_call_block.py` | No Reflex equivalent yet |

Also dead: `src/dex_studio/theme.py` and `src/dex_studio/design_tokens.py:inject_design_tokens()`.

______________________________________________________________________

## Visual Audit — Score: 57/100

> Source-only audit (dev server offline during scan).

| Dimension | Score | Finding |
|-----------|-------|---------|
| Color consistency | 7/10 | Radix semantic tokens used consistently in live code. Two dead parallel systems (`design_tokens.py` + `theme.py`) cause confusion but don't affect runtime. |
| Typography hierarchy | 6/10 | Fira Sans good choice. Radix size scale used but inconsistently — `ai_dashboard` uses `size="6"` for page heading, `data_dashboard` uses `size="3"` for a section header with no page-level heading. No enforced hierarchy contract. |
| Spacing rhythm | 7/10 | Mostly consistent Radix scale in live Reflex code. Dead NiceGUI code has hardcoded px values that don't affect runtime. |
| Component consistency | 3/10 | KPI cards have 3+ implementations (inline in `data_dashboard`, `_kpi_card` in `ai_dashboard`, `metric_card` in `layout.py`). Hub nav defined in dead NiceGUI code with no Reflex equivalent. |
| Responsive behavior | 2/10 | Sidebar hard-fixed at 220px, `margin_left="220px"` hardcoded on content, grid columns hardcoded (`columns="3"`). No breakpoints. Mobile is broken. |
| Dark mode | 7/10 | Dark-first, Radix handles semantic token inversion. Light mode tokens exist but no user toggle — `appearance="dark"` hardcoded in `app.py`. |
| Animation | 6/10 | Motion tokens defined but not injected (dead). Live code uses `transition="all 0.15s ease"` inline — functional but not systematized. |
| Accessibility | 4/10 | Skip-to-main in `page_shell` ✓. Focus ring CSS defined but not injected (dead). `rx.icon_button` calls in `copilot.py` have no `aria-label`. Domain hub cards have no keyboard affordance. |
| Information density | 7/10 | Clean layout hierarchy. Empty states present. Some pages (RAG eval, HITL) are near-empty stubs. |
| Polish | 8/10 | Card hover states ✓. Toast system ✓. Skeleton loaders ✓. Streaming cursor ✓. Spinner states ✓. |

______________________________________________________________________

## AI Slop Check

| Pattern | Location | Severity | Fix |
|---------|----------|----------|-----|
| Logo gradient | `layout.py:239` — `linear-gradient(135deg, var(--indigo-9), var(--violet-9))` on zap icon container | Medium | Replace with flat `var(--indigo-9)` background. The lightning bolt icon is already distinctive. |
| Bootstrap dead load | `app.py:stylesheets` — `bootstrap@5.3.3/dist/css/bootstrap.min.css` | High | Remove. Zero Bootstrap components used. Adds ~30KB, risks Radix reset conflicts. |
| Generic glow shadow token | `design_tokens.py:70` — `"shadow-glow": "0 0 20px rgba(99, 102, 241, 0.3)"` | Low | Not injected, so inert. Delete the token. |
| Indigo hover on all hub cards | `project_hub.py:24` — `"box_shadow": "0 4px 16px var(--indigo-4)"` for all 5 domain cards | Low | Use each domain's own color: `var(--{accent}-4)`. ML card should use violet, AI cyan, etc. |
| Dead component graveyard | 18 files in `src/dex_studio/components/` | High | Delete all 18. Not a visual issue but causes confusion about which component is canonical. |

______________________________________________________________________

## Recommended Actions

**Priority 1 — Cleanup (no visual impact):**

1. Delete the 18 dead NiceGUI component files
1. Remove Bootstrap from `app.py` stylesheets
1. Delete `inject_design_tokens()` from `design_tokens.py` or replace with `rx.GlobalStyle`

**Priority 2 — Consistency:**
4\. Create one canonical `dex_kpi_card()` in `layout.py`, replace 3+ inline variants
5\. Fix domain hub card hover to use per-domain accent color
6\. Add `aria-label` to all `rx.icon_button` calls in `copilot.py` and `layout.py`
7\. Wire motion tokens via `app.style` dict in `app.py`

**Priority 3 — Gaps:**
8\. Add dark/light toggle in system settings
9\. Implement Reflex hub nav strip (underline tabs) to replace dead NiceGUI `hub_nav.py`
10\. Add responsive sidebar (collapse to icon-only below 768px)
