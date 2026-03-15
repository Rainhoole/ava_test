# AVA-Lite Frontend Merge Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the outdated `research-frontend/` in AVA_REAL with the refined AVA-Lite frontend, then verify it builds and renders correctly on localhost.

**Architecture:** The AVA-Lite frontend is an evolved version of the same codebase — same Next.js 14 + React 18 + Tailwind 3 stack, same component names, but with refactored hooks, structured report parsing, cleaned CSS, and dead code removed. We do a full replacement of `src/`, config files, and `public/`, then adapt env/port config to match AVA_REAL's backend (port 8000 for `research_agent_cowork`).

**Tech Stack:** Next.js 14, React 18, Tailwind 3, TypeScript 5

**Key difference to resolve:** AVA-Lite targets `localhost:8765` backend; AVA_REAL backend runs on `localhost:8000`. Auth is always-on in AVA_REAL but AVA-Lite supports `DISABLE_AUTH=true` for local demo — we keep both modes.

---

## Pre-Merge: Backup

### Task 0: Backup existing frontend

**Step 1: Create backup copy**

```powershell
Copy-Item -Recurse -Force "e:\Dev\Ava_FrontEnd\AVA_REAL\ava_production_fluxa-main\research_agent_cowork\research-frontend" "e:\Dev\Ava_FrontEnd\AVA_REAL\ava_production_fluxa-main\research_agent_cowork\research-frontend-backup"
```

---

## Phase 1: Replace Source Files

### Task 1: Replace `src/` directory

The entire `src/` directory is replaced. AVA-Lite has:
- `src/app/` — layout.tsx (next/font), page.tsx (runtime.ts import), workspace/page.tsx (hooks-based)
- `src/components/` — same 7 files + `logs/` subdir (LegacyLogMessage, StructuredLogMessage) + `report/` subdir (ReportMarkdown, ReportSections, ReportSidebar)
- `src/hooks/` — **NEW** (useBudgetFlow, useLogStream, usePaymentDetails, useReportViewer, useWorkspaceTasks)
- `src/lib/` — same 3 files (api, fluxa, utils) + **NEW** (logs, reportActions, reportParser, runtime)
- `src/types/` — same index.ts + html2pdf.d.ts

**Files:**
- Delete: `research-frontend/src/` (entire old src)
- Delete: `research-frontend/src/components/PaymentChat.tsx` (dead code, already removed in AVA-Lite)
- Copy from: `AVA/ava-lite/frontend/src/` → `research-frontend/src/`

**Step 1: Delete old src and copy new**

```powershell
Remove-Item -Recurse -Force "e:\Dev\Ava_FrontEnd\AVA_REAL\ava_production_fluxa-main\research_agent_cowork\research-frontend\src"
Copy-Item -Recurse "e:\Dev\Ava_FrontEnd\AVA\ava-lite\frontend\src" "e:\Dev\Ava_FrontEnd\AVA_REAL\ava_production_fluxa-main\research_agent_cowork\research-frontend\src"
```

**Step 2: Verify directory structure**

```powershell
Get-ChildItem -Recurse "e:\Dev\Ava_FrontEnd\AVA_REAL\ava_production_fluxa-main\research_agent_cowork\research-frontend\src" -Name
```

Expected: should show `app/`, `components/`, `components/logs/`, `components/report/`, `hooks/`, `lib/`, `types/`

---

### Task 2: Replace config files

**Files:**
- Overwrite: `research-frontend/next.config.js` (from AVA-Lite; keep port fallback as `8765` for now, change in Task 3)
- Overwrite: `research-frontend/package.json` (from AVA-Lite; includes `dev:repair` scripts + eslint devDep)
- Keep: `research-frontend/tailwind.config.ts` — identical, no change needed
- Keep: `research-frontend/postcss.config.js` — identical
- Keep: `research-frontend/tsconfig.json` — compare and keep AVA-Lite version if newer
- Overwrite: `research-frontend/vercel.json` — identical, no change needed

**Step 1: Copy config files**

```powershell
Copy-Item -Force "e:\Dev\Ava_FrontEnd\AVA\ava-lite\frontend\next.config.js" "e:\Dev\Ava_FrontEnd\AVA_REAL\ava_production_fluxa-main\research_agent_cowork\research-frontend\next.config.js"
Copy-Item -Force "e:\Dev\Ava_FrontEnd\AVA\ava-lite\frontend\package.json" "e:\Dev\Ava_FrontEnd\AVA_REAL\ava_production_fluxa-main\research_agent_cowork\research-frontend\package.json"
Copy-Item -Force "e:\Dev\Ava_FrontEnd\AVA\ava-lite\frontend\tsconfig.json" "e:\Dev\Ava_FrontEnd\AVA_REAL\ava_production_fluxa-main\research_agent_cowork\research-frontend\tsconfig.json"
Copy-Item -Force "e:\Dev\Ava_FrontEnd\AVA\ava-lite\frontend\.eslintrc.json" "e:\Dev\Ava_FrontEnd\AVA_REAL\ava_production_fluxa-main\research_agent_cowork\research-frontend\.eslintrc.json"
```

---

### Task 3: Adapt API port from 8765 → 8000

AVA-Lite's `next.config.js` defaults to `localhost:8765`. AVA_REAL backend runs on `localhost:8000`.

**Files:**
- Modify: `research-frontend/next.config.js` — change DEFAULT_LOCAL_API_URL
- Modify: `research-frontend/src/lib/runtime.ts` — change DEFAULT_LOCAL_API_URL

**Step 1: Edit next.config.js**

Change:
```js
const DEFAULT_LOCAL_API_URL = 'http://localhost:8765';
```
To:
```js
const DEFAULT_LOCAL_API_URL = 'http://localhost:8000';
```

**Step 2: Edit src/lib/runtime.ts**

Change:
```ts
export const DEFAULT_LOCAL_API_URL = 'http://localhost:8765';
```
To:
```ts
export const DEFAULT_LOCAL_API_URL = 'http://localhost:8000';
```

---

### Task 4: Copy public/ assets + dev scripts

**Files:**
- Copy: `AVA/ava-lite/frontend/public/demo/` → `research-frontend/public/demo/`
- Copy: `AVA/ava-lite/frontend/scripts/` → `research-frontend/scripts/`

**Step 1: Copy new public assets**

```powershell
Copy-Item -Recurse -Force "e:\Dev\Ava_FrontEnd\AVA\ava-lite\frontend\public\demo" "e:\Dev\Ava_FrontEnd\AVA_REAL\ava_production_fluxa-main\research_agent_cowork\research-frontend\public\demo"
```

**Step 2: Copy scripts directory**

```powershell
Copy-Item -Recurse -Force "e:\Dev\Ava_FrontEnd\AVA\ava-lite\frontend\scripts" "e:\Dev\Ava_FrontEnd\AVA_REAL\ava_production_fluxa-main\research_agent_cowork\research-frontend\scripts"
```

---

### Task 5: Create `.env.local` for local development

**Step 1: Create .env.local**

Create `research-frontend/.env.local` with:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_DISABLE_AUTH=true
NEXT_PUBLIC_LITE_MODE=true
```

This enables local demo mode (no real Fluxa auth needed to test UI).

---

## Phase 2: Install & Build

### Task 6: Clean install dependencies

**Step 1: Delete old node_modules and .next cache**

```powershell
cd e:\Dev\Ava_FrontEnd\AVA_REAL\ava_production_fluxa-main\research_agent_cowork\research-frontend
Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .next -ErrorAction SilentlyContinue
Remove-Item -Force package-lock.json -ErrorAction SilentlyContinue
```

**Step 2: Install**

```powershell
npm install
```

Expected: clean install, no peer dependency errors.

**Step 3: Build**

```powershell
npm run build
```

Expected: `next build` succeeds. If TypeScript errors appear, fix them in Phase 3.

---

## Phase 3: Fix & Verify

### Task 7: Fix any TypeScript / build errors

After `npm run build`, address any errors. Known potential issues:
- `Engine` type may still be referenced in old code (AVA-Lite removed Claude engine references)
- `ConfigResponse` interface was removed in AVA-Lite cleanup
- Import paths may need adjustment if any file references differ

**Step 1:** Run `npm run build` and capture errors.
**Step 2:** Fix each error file-by-file.
**Step 3:** Re-run `npm run build` until it succeeds.

---

### Task 8: Start dev server and verify display

**Step 1: Start dev server**

```powershell
cd e:\Dev\Ava_FrontEnd\AVA_REAL\ava_production_fluxa-main\research_agent_cowork\research-frontend
npm run dev:raw
```

(Use `dev:raw` since `dev` script depends on PowerShell `dev-safe.ps1` which may need path adjustment)

**Step 2: Open in browser**

Navigate to `http://localhost:3001`

**Verification checklist:**
- [ ] Landing page (`/`) loads — dark theme, Reforge logo, "Research, Refined" headline, blue wave dot art card
- [ ] "I'm a Human" / "I'm an Agent" toggle works
- [ ] "Enter" button navigates to `/workspace`
- [ ] `/workspace` loads — sidebar + main panel visible, dark theme with proper styling
- [ ] No unstyled/raw HTML (CSS loading correctly)
- [ ] No console errors related to missing modules
- [ ] If backend is not running: workspace shows empty state gracefully (no crash)

**Display issues to specifically check:**
- [ ] Font rendering: Inter for body, Instrument Serif for headings
- [ ] Tailwind custom colors working (brand blue `#45BFFF`, dark backgrounds)
- [ ] Report viewer layout (if you have demo data or backend running)
- [ ] Bottom action bar: `Report / Log / $amount / Budget` visible
- [ ] No duplicate TL;DR in report sections
- [ ] No bottom "Information Sources" card (moved to sidebar)

---

### Task 9: Adjust dev script paths (if needed)

If `npm run dev` (with `dev-safe.ps1`) fails due to path issues:

**Step 1:** Edit `scripts/dev-safe.ps1` to ensure paths work from the new location.

**Step 2:** Verify `npm run dev` works (safe start with cache cleanup).

---

## Phase 4: Commit

### Task 10: Commit the merge

```powershell
cd e:\Dev\Ava_FrontEnd\AVA_REAL\ava_production_fluxa-main
git add research_agent_cowork/research-frontend/
git commit -m "feat(frontend): merge ava-lite frontend — hooks refactor, report parser, CSS cleanup, dead code removal"
```

---

## Summary of Changes

| Category | What changes |
|---|---|
| **Deleted** | `PaymentChat.tsx` (dead), 519 lines dead CSS, dead utils/fluxa/api functions |
| **Added** | 5 hooks, 3 report sub-components, 2 log sub-components, reportParser.ts, runtime.ts, logs.ts, reportActions.ts |
| **Refactored** | workspace/page.tsx (inline → hooks), layout.tsx (link tags → next/font), globals.css (1182 → 663 lines) |
| **Config** | next.config.js (extracted DEFAULT_LOCAL_API_URL), package.json (dev:repair scripts), .eslintrc.json |
| **Port** | Default API changed from 8765 → 8000 to match AVA_REAL backend |
