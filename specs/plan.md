# DEX Studio — E2E Test Plan

**Seed:** `seed.spec.ts` (auth setup — password set + login + storage state)

---

## 1. Smoke Tests — All Pages Load

**Seed:** `seed.spec.ts`

Verify every route returns 200 with correct title and page structure.

| # | Route | Expected Title | Key Elements |
|---|-------|---------------|--------------|
| 1.1 | `/` | Hub — my-project — DEX Studio | nav sidebar, hub cards |
| 1.2 | `/data/pipelines` | Pipelines — DEX Studio | pipeline table, run buttons |
| 1.3 | `/data/transforms` | Transforms — Data — DEX Studio | transform list |
| 1.4 | `/data/streaming` | Streaming — Data — DEX Studio | stream status cards |
| 1.5 | `/data/watermarks` | Watermarks — DEX Studio | watermark table, cursor info |
| 1.6 | `/data/backfill` | Backfill — Ingest — DEX Studio | backfill form |
| 1.7 | `/intelligence/playground` | Playground — Intelligence — DEX Studio | query input, model selector |
| 1.8 | `/intelligence/models` | Models — Intelligence — DEX Studio | model list, register button |
| 1.9 | `/intelligence/predictions` | Predictions — Intelligence — DEX Studio | prediction form |
| 1.10 | `/system/status` | System Status — my-project — DEX Studio | status indicators, uptime |
| 1.11 | `/system/components` | Components — System — DEX Studio | component cards, health badges |
| 1.12 | `/system/alerting` | Alerting — System — DEX Studio | alert config form |
| 1.13 | `/system/compaction` | Compaction — System — DEX Studio | compaction settings |
| 1.14 | `/system/settings` | Settings — DEX Studio | dex.yaml config toggles |
| 1.15 | `/system/runs` | Runs — DEX Studio | run history table |

## 2. Navigation — Sidebar Links Work

**Seed:** `seed.spec.ts`

1. Click each navigation section header in the sidebar
2. Verify the section expands/collapses
3. Click each nav link
4. Verify the page loads with correct title

## 3. Hub Page — Dashboard Cards

**Seed:** `seed.spec.ts`

1. Navigate to `/`
2. Verify the page title contains "Hub"
3. Verify sidebar navigation is visible with all main sections
4. Verify hub cards/stats are present

## 4. Pipelines Page — Pipeline List

**Seed:** `seed.spec.ts`

1. Navigate to `/data/pipelines`
2. Verify the page title contains "Pipelines"
3. Verify the pipeline table or empty state is rendered
4. Verify the "New Pipeline" or action button is present

## 5. Playground — AI Query Form

**Seed:** `seed.spec.ts`

1. Navigate to `/intelligence/playground`
2. Verify the page title contains "Playground"
3. Verify the query input textarea is present
4. Verify the model selector or submit button is present
5. Verify the conversation history section exists

## 6. Settings — Configuration Toggles

**Seed:** `seed.spec.ts`

1. Navigate to `/system/settings`
2. Verify the page title contains "Settings"
3. Verify scheduler enable/disable toggle appears
4. Verify the form can submit

## 7. Runs — Run History

**Seed:** `seed.spec.ts`

1. Navigate to `/system/runs`
2. Verify the page title contains "Runs"
3. Verify the run history table or empty state is present
4. Verify any filter/search controls are present
