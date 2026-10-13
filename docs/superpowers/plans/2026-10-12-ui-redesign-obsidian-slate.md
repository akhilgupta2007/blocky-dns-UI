# Obsidian Slate & Emerald UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul the BlockyDNS Hub user interface with a modern Obsidian Slate & Emerald design system, declutter the navigation and dashboard, eliminate GPU compositing bottlenecks, and replace unicode emojis with clean SVG icons while preserving 100% of existing functionality.

**Architecture:** Refactor CSS variables and card surface styles to a deep obsidian palette (`#0b0f17`) with solid high-performance cards, removing scrolling `backdrop-filter` repaints. Consolidate duplicate pause protection controls into a single interactive Header Shield Pod with popover controls. Restructure sidebar navigation into 4 logical functional pillars with direct sub-tab routing.

**Tech Stack:** Vanilla JavaScript, Semantic HTML5, Vanilla CSS3 (Custom Properties, Grid, Flexbox, SVG icons).

**Spec:** [`docs/superpowers/specs/2026-10-12-ui-redesign-obsidian-slate-design.md`](file:///c:/Users/akhil/OneDrive/Documents/antigravity/blocky-dns/docs/superpowers/specs/2026-10-12-ui-redesign-obsidian-slate-design.md)

## Global Constraints
- Target Palette: `#0b0f17` (Deep Obsidian base), `#111622` (Card surface), `#10b981` (Emerald active), `#0ea5e9` (Cyan action).
- No `backdrop-filter: blur(...)` on scrollable containers or `.card` elements; reserve strictly for sticky headers and modals.
- Ban `transition: all`; use composite-only transitions (`transform`, `opacity`, `border-color`).
- Enable `font-variant-numeric: tabular-nums` on all metric cards and data tables.
- Application version `v1.1.0` must visibly remain in the brand header and sidebar footer per Version Tracking Directive.
- All backend REST API endpoints and database models must remain 100% untouched and operational.

## Review Focus
1. Header Shield Pod popover toggles and closes when clicking outside or selecting a pause duration.
2. Direct sidebar navigation to sub-tabs (e.g. Adlists vs Custom Rules) correctly activates the appropriate `.sub-pane` and loads data.
3. Rapid pause/resume updates correctly synchronize status between the Header Shield Pod, countdown timer, and backend engine.
4. Long domain names in query logs truncate gracefully with ellipsis and show full domain on hover without breaking table layout.
5. Mobile navigation drawer opens and closes without viewport jump on screens below 768px.

---

### Task 1: CSS Design Tokens, Obsidian Surface Architecture & Compositing Overhaul

**Files:**
- Modify: `public/css/style.css:1-120` (Root variables and base styles)
- Modify: `public/css/style.css:315-340` (`.card` and hover transitions)
- Test: Manual DOM/CSS inspection and syntax validation

**Interfaces:**
- Consumes: CSS custom properties in `public/css/style.css`
- Produces: Obsidian Slate color tokens (`--bg-main`, `--bg-card`, `--accent-emerald`, `--inner-rim`), composite-only transitions, and tabular number utilities.

- [ ] **Step 1: Write test script to verify CSS tokens and absence of card blur**

Create scratch verification script `scratch/verify_css_tokens.py` checking that `--bg-main` is `#0b0f17`, `--bg-card` is `#111622`, `.card` does not contain `backdrop-filter`, and tabular numbers are defined.

- [ ] **Step 2: Run verification script to confirm it fails on current CSS**

Run: `python scratch/verify_css_tokens.py`  
Expected: FAIL with missing obsidian tokens or backdrop-filter detected in `.card`.

- [ ] **Step 3: Update `public/css/style.css` with Obsidian Slate tokens and optimized card rules**

Update `:root` variables:
- Set `--bg-main: #0b0f17;`
- Set `--bg-sidebar: #0e131f;`
- Set `--bg-card: #111622;`
- Set `--bg-card-hover: #161c2b;`
- Set `--bg-input: #0a0d14;`
- Add `--inner-rim: inset 0 1px 0 0 rgba(255, 255, 255, 0.06);`
- Update `.card` to use solid `--bg-card`, box-shadow with `--inner-rim`, remove `backdrop-filter: blur(16px);`, and replace `transition: all` with `transition: transform 150ms cubic-bezier(0.2, 0, 0, 1), border-color 150ms ease;`.
- Add global `font-variant-numeric: tabular-nums` to `table`, `.kpi-value`, and `.badge`.

- [ ] **Step 4: Run verification script to verify it passes**

Run: `python scratch/verify_css_tokens.py`  
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add public/css/style.css scratch/verify_css_tokens.py
git commit -m "style: apply Obsidian Slate design tokens and eliminate card blur repaints"
```

---

### Task 2: Header Shield Pod & Popover Component Implementation

**Files:**
- Modify: `public/index.html:84-110` (Top header structure)
- Modify: `public/css/style.css:215-280` (Header and Shield Pod styling)
- Modify: `public/js/app.js:379-395` (Status badge updates)
- Modify: `public/js/dashboard.js:139-195` (Shield status synchronization)
- Test: Scratch test for Shield Pod elements and click behavior

**Interfaces:**
- Consumes: `/api/control/pause`, `/api/control/enable`, `handlePauseBlocking`, `handleResumeBlocking`
- Produces: Header Shield Pod `#headerShieldPod` with interactive toggle `#btnShieldToggle`, countdown pill `#headerPauseCountdown`, and popover menu `#shieldPopoverMenu`.

- [ ] **Step 1: Write test verifying Header Shield Pod elements in index.html**

Create scratch test `scratch/verify_shield_pod.py` that parses `public/index.html` and asserts `#headerShieldPod`, `#btnShieldToggle`, `#shieldPopoverMenu`, and duration buttons exist in the header.

- [ ] **Step 2: Run test to verify failure**

Run: `python scratch/verify_shield_pod.py`  
Expected: FAIL with missing elements.

- [ ] **Step 3: Implement Header Shield Pod in `index.html`, `style.css`, and `app.js`**

1. In `public/index.html`:
   - Replace redundant header buttons (`#btnPause5m`, `#btnRefreshAll`, `#btnChangePassword`) with the **Header Shield Pod**:
     - Status pill with pulsing indicator, active label ("Shield Active"), and dropdown chevron.
     - Resume button and countdown badge for paused state.
     - Dropdown popover containing quick-pause options (1 min, 10 min, 30 min, 1 hour, Permanently) and Refresh Lists button.
   - Clean up top header right side to contain search bar and user profile dropdown.
2. In `public/css/style.css`:
   - Add styles for `.shield-pod`, `.shield-pod-popover`, `.shield-pod-btn`, and smooth popover fade-in.
3. In `public/js/app.js` and `public/js/dashboard.js`:
   - Wire popover toggle (`toggleShieldPopover()`), close on outside click.
   - Ensure `syncProtectionStatusUI(active)` and `startPauseTimer(seconds)` update both the header pod and dashboard counters.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scratch/verify_shield_pod.py`  
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add public/index.html public/css/style.css public/js/app.js public/js/dashboard.js scratch/verify_shield_pod.py
git commit -m "feat: implement unified Header Shield Pod and remove duplicate header buttons"
```

---

### Task 3: Dashboard View Decluttering & 4-Pillar Navigation Overhaul

**Files:**
- Modify: `public/index.html:26-55` (Sidebar navigation items)
- Modify: `public/index.html:115-140` (Dashboard view top section)
- Modify: `public/css/style.css:130-200` (Sidebar navigation group styling)
- Modify: `public/js/app.js:180-260` (`switchView` navigation handler)
- Test: Playwright / DOM verification script for 4-pillar navigation

**Interfaces:**
- Consumes: `switchView(viewName, subTab)`
- Produces: 4 navigation groups (*Monitor*, *Filtering*, *DNS & Network*, *System*) with direct subtab activation; clean dashboard without redundant pause bar.

- [ ] **Step 1: Write test script to verify 4-pillar navigation structure**

Create scratch test `scratch/verify_navigation_pillars.py` verifying all 4 pillar groups exist and dashboard top section no longer contains `.dashboard-action-bar`.

- [ ] **Step 2: Run test to verify failure**

Run: `python scratch/verify_navigation_pillars.py`  
Expected: FAIL with old nav structure detected.

- [ ] **Step 3: Update sidebar navigation and dashboard layout**

1. In `public/index.html`:
   - Add group headers: `Monitor`, `Filtering`, `DNS & Network`, `System`.
   - Update nav links to call `switchView(view, subTab)` for direct access.
   - Retain version badge `v1.1.0` in brand header and sidebar footer.
   - Remove redundant `.dashboard-action-bar` from `#viewDashboard` since all controls are now in the Header Shield Pod.
2. In `public/css/style.css`:
   - Add styles for `.nav-group-label` (subtle uppercase tracking, muted color).
   - Style active nav item with subtle emerald border indicator and background tint.
3. In `public/js/app.js`:
   - Update `switchView` to highlight corresponding group nav items when sub-tabs are selected.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scratch/verify_navigation_pillars.py`  
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add public/index.html public/css/style.css public/js/app.js scratch/verify_navigation_pillars.py
git commit -m "feat: restructure sidebar into 4 pillars and remove redundant dashboard pause banner"
```

---

### Task 4: SVG Iconography & Visual Polish

**Files:**
- Modify: `public/index.html` (Sub-nav buttons, action icons, and modals)
- Modify: `public/css/style.css` (SVG icon utilities and table formatting)
- Test: Verification script checking replacement of raw unicode emojis

**Interfaces:**
- Consumes: Standard inline SVGs (Heroicons / Lucide outline 1.5px stroke)
- Produces: Polished iconography across all buttons, segmented pills, and modals.

- [ ] **Step 1: Write test verifying unicode emoji removal**

Create scratch script `scratch/verify_svg_icons.py` that scans `public/index.html` for raw unicode emoji characters in nav items, buttons, and card headers.

- [ ] **Step 2: Run test to verify failure**

Run: `python scratch/verify_svg_icons.py`  
Expected: FAIL with multiple raw emoji instances detected.

- [ ] **Step 3: Replace emojis with inline SVG icons**

1. In `public/index.html`:
   - Replace emojis in segmented pill tabs (`subnav-segmented-bar` for Protection, Routing, Settings).
   - Replace emojis in buttons (Refresh, Import, Add, Export, Benchmark).
   - Replace emojis in modal dialog headers.
2. In `public/css/style.css`:
   - Add `.btn-svg` and `.icon-inline` helper classes for consistent 16px/18px stroke alignment.
   - Add table cell text truncation with `max-width: 280px`, `text-overflow: ellipsis`, and `overflow: hidden` for long domain names.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scratch/verify_svg_icons.py`  
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add public/index.html public/css/style.css scratch/verify_svg_icons.py
git commit -m "style: replace unicode emojis with clean SVG icons and add table domain truncation"
```

---

### Task 5: End-to-End Test Suite Execution & Verification

**Files:**
- Modify: `test_frontend_complete.py` (Update selectors for Header Shield Pod if needed)
- Test: Full Playwright frontend test suite

**Interfaces:**
- Consumes: Test server on port 3001
- Produces: Verified passing test suite with zero console errors and full feature coverage.

- [ ] **Step 1: Update `test_frontend_complete.py` test selectors**

Ensure the test exercises both the Header Shield Pod pause/resume workflow and navigation across the 4 pillars.

- [ ] **Step 2: Run `test_frontend_complete.py`**

Run: `python test_frontend_complete.py`  
Expected: All suites PASS with green checkmarks and no console errors.

- [ ] **Step 3: Run backend test suite for regression verification**

Run: `python test_backend.py`  
Expected: All backend tests PASS, verifying zero regression on backend APIs or database sync.

- [ ] **Step 4: Commit test updates and clean up scratch files**

```bash
git add test_frontend_complete.py
git rm -r scratch/
git commit -m "test: verify complete frontend and backend test suites on redesigned UI"
```
