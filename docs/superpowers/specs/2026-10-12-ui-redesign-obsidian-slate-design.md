# Design Document: BlockyDNS Hub UI Redesign (Option 1: Obsidian Slate & Emerald)

**Date**: 2026-10-12  
**Topic**: Modern UI overhaul, Information Architecture decluttering, and performance optimization for BlockyDNS Hub.  
**Target Style**: Obsidian Slate & Emerald (High-density Cloudflare / Vercel engineering aesthetic).

---

## 1. Executive Summary & Goals

### 1.1 Goals
1. **Visual Modernization**: Upgrade from generic glassmorphism and neon glows to a high-density, professional dark engineering design system with deep matte obsidian surfaces, emerald/cyan signal accents, and crisp typography.
2. **Information Architecture Decluttering**:
   - Consolidate duplicate Pause Blocking controls into a single interactive **Header Shield Pod** with an integrated quick-timer popover.
   - Remove duplicate password change entry points from the header, retaining them in the user profile menu and Settings.
   - Reorganize the navigation sidebar into 4 logical functional pillars: *Monitor*, *Filtering & Rules*, *DNS & Network*, and *System & Tools*.
   - Replace raw unicode emojis with clean 1.5px SVG line icons.
3. **Performance & GPU Compositing Optimization**:
   - Eliminate `backdrop-filter: blur(...)` from repeating and scrolling cards, eliminating frame-drop bottlenecks on low-powered and mobile clients.
   - Replace `transition: all` with GPU composite-only properties (`transform`, `opacity`, `border-color`).
   - Implement `font-variant-numeric: tabular-nums` to eliminate number jitter during live query streaming.
4. **Zero Feature Loss & Strict Sync**: Preserve 100% of existing functionality, API contracts, and database models. Retain visible application version badge (`v1.1.0`) per project directives.

### 1.2 Non-Goals
- Modifying backend SQLite schemas or REST API endpoints (backend contracts remain identical).
- Rewriting JavaScript modules from scratch (all existing controller functions and event handlers are preserved).

---

## 2. Design System Tokens & Surfaces

### 2.1 Color Palette & Variables
```css
:root {
  /* Surfaces & Backgrounds */
  --bg-main: #0b0f17;                /* Deep Obsidian Base */
  --bg-sidebar: #0e131f;             /* Elevated Sidebar */
  --bg-card: #111622;                /* Solid Performance Surface */
  --bg-card-hover: #161c2b;          /* Interactive Hover Surface */
  --bg-input: #0a0d14;               /* Recessed Input Well */

  /* Borders & Hairlines */
  --border-subtle: rgba(255, 255, 255, 0.07);
  --border-card: rgba(255, 255, 255, 0.08);
  --border-hover: rgba(255, 255, 255, 0.16);
  --border-accent-emerald: rgba(16, 185, 129, 0.4);
  --border-accent-cyan: rgba(14, 165, 233, 0.4);

  /* Typography */
  --text-main: #f8fafc;              /* High-contrast crisp white */
  --text-muted: #94a3b8;             /* Slate 400 */
  --text-dim: #64748b;               /* Slate 500 */

  /* Signal Accents */
  --accent-emerald: #10b981;         /* Shield Active / Success */
  --accent-emerald-subtle: rgba(16, 185, 129, 0.12);
  --accent-cyan: #0ea5e9;            /* Network Telemetry / Action */
  --accent-cyan-subtle: rgba(14, 165, 233, 0.12);
  --accent-red: #ef4444;             /* Blocked / Destructive */
  --accent-red-subtle: rgba(239, 68, 68, 0.12);
  --accent-amber: #f59e0b;           /* Warning / Paused Status */

  /* Elevation & Geometry */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --radius-full: 9999px;

  /* Double-Bezel Inner Rim Highlight */
  --inner-rim: inset 0 1px 0 0 rgba(255, 255, 255, 0.06);
  --shadow-card: 0 4px 12px rgba(0, 0, 0, 0.4), var(--inner-rim);

  /* Compositor Easing */
  --ease-out: cubic-bezier(0.2, 0, 0, 1);
  --transition-fast: 150ms var(--ease-out);
}
```

### 2.2 Typography Specification
- **Primary Body & UI**: `Inter`, `-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, `Roboto`, sans-serif.
- **Numbers, IPs, Latencies, & Code**: `JetBrains Mono`, `SFMono-Regular`, `Consolas`, monospace.
- **Tabular Alignment**: Enable `font-variant-numeric: tabular-nums` globally on table rows, KPI values, and badges.

---

## 3. Layout & Navigation Architecture

### 3.1 Four-Pillar Sidebar Structure
The navigation is organized into functional categories with subtle uppercase category headers:
```html
<nav class="nav-menu">
  <!-- PILLAR 1: MONITOR -->
  <div class="nav-group-label">Monitor</div>
  <a id="navDashboard" class="nav-item active" onclick="switchView('dashboard')">
    <svg ...></svg> Overview
  </a>
  <a id="navQueryLog" class="nav-item" onclick="switchView('queryLog')">
    <svg ...></svg> Query Log
  </a>

  <!-- PILLAR 2: FILTERING & RULES -->
  <div class="nav-group-label">Filtering</div>
  <a id="navProtectionAdlists" class="nav-item" onclick="switchView('protection', 'adlists')">
    <svg ...></svg> Adlists & Subscriptions
  </a>
  <a id="navProtectionCustom" class="nav-item" onclick="switchView('protection', 'customRules')">
    <svg ...></svg> Custom Domain Rules
  </a>
  <a id="navProtectionServices" class="nav-item" onclick="switchView('protection', 'blockedServices')">
    <svg ...></svg> 1-Click App Blocker
    <span id="blockedServicesNavBadge" class="badge-mini">0</span>
  </a>

  <!-- PILLAR 3: DNS & NETWORK -->
  <div class="nav-group-label">DNS & Network</div>
  <a id="navSettingsResolvers" class="nav-item" onclick="switchView('settings', 'resolvers')">
    <svg ...></svg> Upstream Resolvers
  </a>
  <a id="navRoutingLocalDns" class="nav-item" onclick="switchView('routing', 'localDns')">
    <svg ...></svg> Local DNS & Homelab
  </a>
  <a id="navRoutingSmartDns" class="nav-item" onclick="switchView('routing', 'smartDns')">
    <svg ...></svg> Geo-Routing & SmartDNS
  </a>
  <a id="navDevices" class="nav-item" onclick="switchView('devices')">
    <svg ...></svg> Client Devices
  </a>

  <!-- PILLAR 4: SYSTEM & TOOLS -->
  <div class="nav-group-label">System</div>
  <a id="navSettingsEngine" class="nav-item" onclick="switchView('settings', 'engine')">
    <svg ...></svg> Engine & Cache
  </a>
  <a id="navSettingsTools" class="nav-item" onclick="switchView('settings', 'tools')">
    <svg ...></svg> Diagnostics & Tools
  </a>
</nav>
```

### 3.2 Top Header & Unified Shield Pod
Replaces the 3 redundant buttons with:
1. **Left**: Mobile menu toggle, brand text, version tag (`v1.1.0`), and TLS 1.3 indicator.
2. **Center/Status**: **Unified Shield Status Pod**:
   - When Active: `[ 🟢 Shield Active · 1.2M Blocked ▾ ]` (Pill button with pulse dot).
   - When Paused: `[ ⏸️ Paused (4:52) · Resume ▾ ]` with amber highlight and direct resume action.
   - Clicking opens a quick-pause dropdown with preset durations (`1 min`, `10 min`, `30 min`, `1 hour`, `Indefinitely`) and a Refresh Blocklists action.
3. **Right**:
   - Quick Search bar or jump trigger.
   - User Profile avatar dropdown with Change Password modal trigger and Logout.

---

## 4. Dashboard View Decluttering & Refinement
1. **Removal of Redundant Action Bar**: The 80px `.dashboard-action-bar` is eliminated. Its controls now live in the **Header Shield Pod**.
2. **High-Contrast KPI Cards**:
   - 4 cards: *Total Queries (24h)*, *Queries Blocked* (with % pill), *Active Devices*, and *Active Rules* (with latency indicator).
   - Styled with subtle inner-rim highlights, crisp value typography, and distinct hover states.
3. **Telemetry & Visualizations**:
   - Refined timeline volume chart with transparent gradient fill.
   - Donut breakdown chart with tabular legend.
   - Top Blocked Domains and Client Devices tables with monospaced tabular numerals.

---

## 5. Performance Engineering Guardrails
1. **Zero Blurs on Scrolling Content**:
   - Remove `backdrop-filter: blur(16px)` from `.card`, `.table-responsive`, and dashboard containers.
   - Restrict `backdrop-filter` strictly to fixed elements: the sticky `.top-header` and `.modal-overlay`.
2. **GPU Composite-Only Transitions**:
   - Ban `transition: all`.
   - Use explicit transitions on `transform`, `opacity`, and `border-color`.
3. **Tabular Numerals**:
   - Apply `font-variant-numeric: tabular-nums` to ensure log rows and live metrics never jump or reflow text layout during SSE streaming updates.

---

## 6. Implementation Plan & File Touch Points
- [`public/index.html`](file:///c:/Users/akhil/OneDrive/Documents/antigravity/blocky-dns/public/index.html):
  - Refactor navigation menu to the 4-pillar layout.
  - Implement Header Shield Pod with popover menu.
  - Remove dashboard duplicate pause bar.
  - Replace emojis with clean SVG icons across all sub-navs, buttons, and badges.
- [`public/css/style.css`](file:///c:/Users/akhil/OneDrive/Documents/antigravity/blocky-dns/public/css/style.css):
  - Update root variables for Obsidian Slate & Emerald palette.
  - Eliminate `backdrop-filter` from `.card` and scrollable containers.
  - Replace `transition: all` with composite-only transitions.
  - Add styles for the Header Shield Pod, popover, and tabular number utilities.
- [`public/js/app.js`](file:///c:/Users/akhil/OneDrive/Documents/antigravity/blocky-dns/public/js/app.js) & [`public/js/dashboard.js`](file:///c:/Users/akhil/OneDrive/Documents/antigravity/blocky-dns/public/js/dashboard.js):
  - Wire Header Shield Pod countdown and pause popover triggers to existing `handlePauseBlocking` and `handleResumeBlocking` functions.
  - Support direct navigation to subtabs from the 4-pillar sidebar items.

---

## 7. Verification & Testing Strategy
1. **Visual & Layout Inspection**: Confirm 4-pillar navigation switches views and subtabs smoothly without layout shifts.
2. **Protection Toggle Testing**: Verify pause (1m, 10m, 30m, 1h, permanent) and resume actions work correctly via the Header Shield Pod.
3. **Scroll Performance**: Verify smooth 60 FPS scrolling on all views without GPU compositing lag.
4. **Responsive Testing**: Verify mobile sidebar drawer and mobile navigation collapse cleanly below 768px.
5. **Version Tracking**: Verify `v1.1.0` remains visibly displayed in the brand header and sidebar footer.
