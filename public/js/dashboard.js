// ==========================================================
// BLOCKYDNS COMMAND CENTER DASHBOARD (OPTION A)
// ==========================================================

let cachedTimelineData = null;
let cachedSummaryData = null;
let pauseCountdownInterval = null;
let pauseSecondsRemaining = 0;

async function loadDashboard() {
  try {
    const summary = await apiRequest("/api/stats/summary");
    if (!summary) return;
    cachedSummaryData = summary;

    // Update KPIs
    const totalEl = document.getElementById("kpiTotalQueries");
    const blockedEl = document.getElementById("kpiBlockedQueries");
    const pctEl = document.getElementById("kpiBlockedPct");
    const devicesEl = document.getElementById("kpiActiveDevices");
    const rulesEl = document.getElementById("kpiActiveRules");
    const latencyEl = document.getElementById("kpiLatencyText");

    if (totalEl) totalEl.textContent = summary.total_queries_24h.toLocaleString();
    if (blockedEl) blockedEl.textContent = summary.blocked_queries_24h.toLocaleString();
    if (pctEl) pctEl.textContent = `${summary.blocked_percent}%`;
    if (devicesEl) devicesEl.textContent = summary.active_devices_count;
    if (rulesEl) rulesEl.textContent = summary.active_rules_count.toLocaleString();
    if (latencyEl) latencyEl.textContent = `${summary.upstream_latency_ms}ms via Encrypted DoH`;

    // Synchronize Pause Protection status
    syncProtectionStatusUI(summary.blocking_enabled);
    if (typeof updateBlockingBadge === "function") {
      updateBlockingBadge(summary.blocking_enabled);
    }

    // Donut Query Distribution Chart
    drawDonutChart(summary.query_distribution, summary.total_queries_24h, summary.blocked_queries_24h);

    // Timeline Area Chart
    const timeline = await apiRequest("/api/stats/timeline");
    if (timeline) drawTimelineChart(timeline);

    // Top Blocked Domains
    const topDomains = await apiRequest("/api/stats/top-domains");
    if (topDomains && topDomains.top_blocked) {
      renderTopBlocked(topDomains.top_blocked);
    }

    // Client Device Breakdown
    const topDevices = await apiRequest("/api/stats/top-devices");
    if (topDevices) {
      renderDashboardDevices(topDevices);
    }
  } catch (err) {
    console.error("Error loading dashboard:", err);
  }
}

// ----------------------------------------------------------
// PAUSE DNS FILTERING LOGIC
// ----------------------------------------------------------
async function handlePauseBlocking(duration, clickedBtn) {
  const activeBtn = clickedBtn || (window.event && window.event.target ? window.event.target.closest("button") : null);
  if (activeBtn) {
    activeBtn.classList.add("is-pausing");
  }
  try {
    const res = await apiRequest("/api/control/pause", {
      method: "POST",
      body: JSON.stringify({ duration: duration })
    });

    if (res && res.success) {
      const isPermanent = !duration || duration === "permanent";
      showToast(`DNS Shield paused ${isPermanent ? 'indefinitely' : `for ${duration}`} (Cache flushed)`);

      // Calculate countdown seconds
      if (isPermanent) {
        startPauseTimer(null);
      } else {
        let seconds = 300; // default 5m
        if (duration === "1m") seconds = 60;
        else if (duration === "10m") seconds = 600;
        else if (duration === "30m") seconds = 1800;
        else if (duration === "1h") seconds = 3600;
        startPauseTimer(seconds);
      }

      syncProtectionStatusUI(false);
      if (typeof updateBlockingBadge === "function") {
        updateBlockingBadge(false);
      }
    } else {
      showToast("Failed to pause protection", "error");
    }
  } catch (err) {
    console.error("Error pausing DNS protection:", err);
    showToast("Error communicating with DNS engine", "error");
  } finally {
    if (activeBtn) {
      activeBtn.classList.remove("is-pausing");
    }
  }
}

async function handleResumeBlocking() {
  const btnResume = document.getElementById("btnResumeProtection");
  if (btnResume && window.setButtonLoading) {
    window.setButtonLoading(btnResume, true, "Resuming...");
  }
  try {
    const res = await apiRequest("/api/control/enable", { method: "POST" });
    if (res && res.success) {
      clearInterval(pauseCountdownInterval);
      pauseCountdownInterval = null;
      showToast("DNS Protection resumed (Shield Active)");
      syncProtectionStatusUI(true);
      if (typeof updateBlockingBadge === "function") {
        updateBlockingBadge(true);
      }
      setTimeout(loadDashboard, 1000);
    } else {
      showToast("Failed to resume protection", "error");
    }
  } catch (err) {
    console.error("Error resuming DNS protection:", err);
    showToast("Error communicating with DNS engine", "error");
  } finally {
    if (btnResume && window.setButtonLoading) {
      window.setButtonLoading(btnResume, false);
    }
  }
}

function startPauseTimer(totalSeconds) {
  clearInterval(pauseCountdownInterval);
  const badge = document.getElementById("pauseCountdownBadge");
  if (!badge) return;

  if (totalSeconds === null) {
    badge.style.display = "inline-flex";
    badge.textContent = "⏸ Paused Indefinitely";
    return;
  }

  pauseSecondsRemaining = totalSeconds;
  badge.style.display = "inline-flex";
  updateTimerDisplay();

  pauseCountdownInterval = setInterval(() => {
    pauseSecondsRemaining--;
    if (pauseSecondsRemaining <= 0) {
      clearInterval(pauseCountdownInterval);
      pauseCountdownInterval = null;
      syncProtectionStatusUI(true);
      showToast("Pause expired. DNS Protection re-enabled automatically.");
      loadDashboard();
    } else {
      updateTimerDisplay();
    }
  }, 1000);

  function updateTimerDisplay() {
    const mins = Math.floor(pauseSecondsRemaining / 60);
    const secs = pauseSecondsRemaining % 60;
    badge.textContent = `⏸ Paused (${mins}:${secs < 10 ? '0' : ''}${secs})`;
  }
}

function syncProtectionStatusUI(active) {
  const dot = document.getElementById("shieldStatusDot");
  const text = document.getElementById("shieldStatusText");
  const resumeBtn = document.getElementById("btnResumeProtection");
  const countdownBadge = document.getElementById("pauseCountdownBadge");

  if (active) {
    if (dot) {
      dot.className = "shield-pulse-dot";
    }
    if (text) text.textContent = "Shield Active";
    if (resumeBtn) resumeBtn.style.display = "none";
    if (countdownBadge) countdownBadge.style.display = "none";
    clearInterval(pauseCountdownInterval);
    pauseCountdownInterval = null;
  } else {
    if (dot) {
      dot.className = "shield-pulse-dot paused";
    }
    if (text) text.textContent = "Protection Paused";
    if (resumeBtn) resumeBtn.style.display = "inline-flex";
    if (countdownBadge && !pauseCountdownInterval && countdownBadge.style.display === "none") {
      countdownBadge.style.display = "inline-flex";
      countdownBadge.textContent = "⏸ Paused";
    }
  }
}

// ----------------------------------------------------------
// INTERACTIVE DONUT CHART (QUERY BREAKDOWN)
// ----------------------------------------------------------
function drawDonutChart(queryDist, totalQueries, blockedQueries) {
  const canvas = document.getElementById("queryDonutChart");
  const legend = document.getElementById("donutLegend");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const size = 135;

  canvas.width = Math.round(size * dpr);
  canvas.height = Math.round(size * dpr);
  canvas.style.width = size + "px";
  canvas.style.height = size + "px";

  if (ctx.resetTransform) ctx.resetTransform();
  else ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.scale(dpr, dpr);

  const cx = size / 2;
  const cy = size / 2;
  const outerRadius = 56;
  const innerRadius = 38;

  // Build slices data
  let resolvedCount = 0;
  let blockedCount = blockedQueries || 0;
  let cachedCount = 0;
  let otherCount = 0;

  if (queryDist && typeof queryDist === "object") {
    resolvedCount = queryDist["RESOLVED"] || 0;
    cachedCount = queryDist["CACHED"] || 0;
    blockedCount = queryDist["BLOCKED"] || blockedCount;
    // local/special
    for (const [k, v] of Object.entries(queryDist)) {
      if (!["RESOLVED", "BLOCKED", "CACHED"].includes(k)) {
        otherCount += v;
      }
    }
  } else {
    resolvedCount = Math.max(totalQueries - blockedCount, 0);
  }

  const calcTotal = Math.max(resolvedCount + blockedCount + cachedCount + otherCount, 1);

  const slices = [
    { label: "DoH Resolved", count: resolvedCount, color: "#10b981", pct: Math.round((resolvedCount / calcTotal) * 100) },
    { label: "Ads Blocked", count: blockedCount, color: "#ef4444", pct: Math.round((blockedCount / calcTotal) * 100) },
    { label: "RAM Cached", count: cachedCount, color: "#06b6d4", pct: Math.round((cachedCount / calcTotal) * 100) },
    { label: "Local / Other", count: otherCount, color: "#8b5cf6", pct: Math.round((otherCount / calcTotal) * 100) },
  ].filter(s => s.count > 0 || calcTotal === 1);

  // If completely empty, show default placeholder ring
  if (calcTotal <= 1 && totalQueries === 0) {
    ctx.clearRect(0, 0, size, size);
    ctx.beginPath();
    ctx.arc(cx, cy, outerRadius, 0, 2 * Math.PI);
    ctx.arc(cx, cy, innerRadius, 2 * Math.PI, 0, true);
    ctx.fillStyle = "rgba(255, 255, 255, 0.05)";
    ctx.fill();

    ctx.fillStyle = "#64748b";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("No Data", cx, cy);

    if (legend) {
      legend.innerHTML = `
        <div class="donut-legend-item">
          <span class="donut-legend-label"><span class="donut-color-dot" style="background: #10b981;"></span>Resolved</span>
          <strong>0%</strong>
        </div>
        <div class="donut-legend-item">
          <span class="donut-legend-label"><span class="donut-color-dot" style="background: #ef4444;"></span>Blocked</span>
          <strong>0%</strong>
        </div>
      `;
    }
    return;
  }

  ctx.clearRect(0, 0, size, size);
  let currentAngle = -Math.PI / 2;

  slices.forEach(slice => {
    const sliceAngle = (slice.count / calcTotal) * (2 * Math.PI);
    ctx.beginPath();
    ctx.arc(cx, cy, outerRadius, currentAngle, currentAngle + sliceAngle);
    ctx.arc(cx, cy, innerRadius, currentAngle + sliceAngle, currentAngle, true);
    ctx.closePath();
    ctx.fillStyle = slice.color;
    ctx.fill();

    currentAngle += sliceAngle;
  });

  // Center text (Block percentage or Shield state)
  const blockPct = Math.round((blockedCount / calcTotal) * 100);
  ctx.fillStyle = "#f8fafc";
  ctx.font = "bold 15px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(`${blockPct}%`, cx, cy - 6);

  ctx.fillStyle = "#64748b";
  ctx.font = "9px sans-serif";
  ctx.fillText("BLOCKED", cx, cy + 10);

  // Render legend
  if (legend) {
    legend.innerHTML = slices.map(s => `
      <div class="donut-legend-item" title="${s.count.toLocaleString()} queries">
        <span class="donut-legend-label">
          <span class="donut-color-dot" style="background: ${s.color};"></span>
          <span>${s.label}</span>
        </span>
        <strong style="color: ${s.color}; font-family: monospace;">${s.pct}%</strong>
      </div>
    `).join("");
  }
}

// ----------------------------------------------------------
// TOP BLOCKED DOMAINS LIST
// ----------------------------------------------------------
function renderTopBlocked(blockedList) {
  const container = document.getElementById("topBlockedList");
  if (!container) return;

  if (blockedList.length === 0) {
    container.innerHTML = `<div style="color: var(--text-dim); font-size: 0.85rem; padding: 12px;">No blocked queries recorded yet.</div>`;
    return;
  }

  const maxCount = Math.max(...blockedList.map(b => b.count), 1);
  container.innerHTML = blockedList.slice(0, 6).map(b => {
    const pct = Math.round((b.count / maxCount) * 100);
    return `
      <div onclick="filterLogsByDomain('${b.domain}')" style="cursor: pointer; padding: 4px 0; border-radius: 4px; transition: background 0.15s ease;" title="Click to view queries for ${b.domain}" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
        <div style="display: flex; justify-content: space-between; font-size: 0.84rem; margin-bottom: 4px;">
          <span style="font-family: monospace; color: var(--text-main);">${b.domain}</span>
          <span style="color: var(--accent-red); font-weight: 600;">${b.count.toLocaleString()}</span>
        </div>
        <div style="height: 6px; background: rgba(255,255,255,0.05); border-radius: var(--radius-full); overflow: hidden;">
          <div style="height: 100%; width: ${pct}%; background: linear-gradient(90deg, var(--accent-red), #dc2626); border-radius: var(--radius-full);"></div>
        </div>
      </div>
    `;
  }).join("");
}

// ----------------------------------------------------------
// CLIENT DEVICE ACTIVITY BREAKDOWN (DESKTOP & MOBILE STACKED)
// ----------------------------------------------------------
function renderDashboardDevices(devices) {
  const tbody = document.getElementById("dashboardDevicesTable");
  if (!tbody) return;

  if (devices.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 20px;">No active devices discovered yet.</td></tr>`;
    return;
  }

  const iconMap = {
    tv: "📺", laptop: "💻", phone: "📱", tablet: "📱", iot: "💡", server: "🖥️", printer: "🖨️", device: "🔌"
  };

  tbody.innerHTML = devices.map(d => {
    const icon = iconMap[d.icon] || "🔌";
    return `
      <tr class="dashboard-device-card" onclick="filterLogsByClient('${d.client_ip}')" style="cursor: pointer;" title="Click to filter Query Log for ${d.name} (${d.client_ip})">
        <td class="col-device-name">
          <div class="dash-device-top">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 1.15rem;">${icon}</span>
              <span style="font-weight: 600; color: var(--text-main); font-size: 0.88rem;">${d.name}</span>
              <code class="client-ip-sub" style="font-size: 0.74rem; color: var(--accent-cyan); font-family: monospace;">(${d.client_ip})</code>
            </div>
            <span class="pill blocked mobile-status-tag" style="font-size: 0.72rem;">${d.blocked_percent}% Blocked</span>
          </div>
        </td>
        <td class="col-device-ip desktop-only">
          <code style="color: var(--accent-cyan); font-family: monospace; font-size: 0.8rem;">${d.client_ip}</code>
        </td>
        <td class="col-device-total desktop-only" style="font-weight: 600;">${d.total_queries.toLocaleString()}</td>
        <td class="col-device-blocked desktop-only" style="color: var(--accent-red); font-weight: 600;">${d.blocked_queries.toLocaleString()}</td>
        <td class="col-device-pct desktop-only">
          <span class="pill blocked" style="font-size: 0.74rem;">${d.blocked_percent}%</span>
        </td>
        <td class="col-device-mobile-stats" style="display: none;">
          <div class="dash-device-stats">
            <span>📊 Total: <strong style="color: var(--text-main);">${d.total_queries.toLocaleString()}</strong></span>
            <span style="color: var(--accent-red);">🚫 Blocked: <strong>${d.blocked_queries.toLocaleString()}</strong></span>
          </div>
          <div style="height: 5px; background: rgba(255,255,255,0.06); border-radius: var(--radius-full); overflow: hidden; margin-top: 6px;">
            <div style="height: 100%; width: ${d.blocked_percent}%; background: linear-gradient(90deg, var(--accent-red), #dc2626); border-radius: var(--radius-full);"></div>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

// ----------------------------------------------------------
// PURE CANVAS 2D SMOOTH AREA CHART (24H TRAFFIC)
// ----------------------------------------------------------
function drawTimelineChart(data) {
  if (data && Array.isArray(data)) cachedTimelineData = data;
  else data = cachedTimelineData;

  const canvas = document.getElementById("timelineChart");
  if (!canvas) return;
  const container = canvas.parentElement;
  if (!container) return;

  const rect = container.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const displayWidth = Math.max(Math.floor(rect.width || container.clientWidth || 300), 260);
  const displayHeight = 220;

  // Internal resolution scaled by DPR for retina clarity
  canvas.width = Math.round(displayWidth * dpr);
  canvas.height = Math.round(displayHeight * dpr);
  canvas.style.width = displayWidth + "px";
  canvas.style.height = displayHeight + "px";

  const ctx = canvas.getContext("2d");
  if (ctx.resetTransform) ctx.resetTransform();
  else ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.scale(dpr, dpr);

  const w = displayWidth;
  const h = displayHeight;
  ctx.clearRect(0, 0, w, h);

  if (!data || data.length === 0) {
    ctx.fillStyle = "#64748b";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No queries recorded in the last 24 hours.", w / 2, h / 2);
    return;
  }

  const padding = { top: 20, right: 16, bottom: 28, left: 34 };
  const graphW = w - padding.left - padding.right;
  const graphH = h - padding.top - padding.bottom;

  const maxVal = Math.max(...data.map(d => d.total), 10);
  const stepX = graphW / Math.max(data.length - 1, 1);

  // Background Grid Lines
  ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = padding.top + (graphH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(w - padding.right, y);
    ctx.stroke();

    const val = Math.round(maxVal - (maxVal / 4) * i);
    ctx.fillStyle = "#64748b";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(val > 999 ? (val / 1000).toFixed(1) + "k" : val, padding.left - 6, y + 3);
  }

  function getCoord(idx, val) {
    const x = padding.left + idx * stepX;
    const y = padding.top + graphH - (val / maxVal) * graphH;
    return { x, y };
  }

  function drawCurve(key, strokeColor, fillColor) {
    ctx.beginPath();
    const first = getCoord(0, data[0][key]);
    ctx.moveTo(first.x, first.y);

    for (let i = 0; i < data.length - 1; i++) {
      const p0 = getCoord(i, data[i][key]);
      const p1 = getCoord(i + 1, data[i + 1][key]);
      const mx = (p0.x + p1.x) / 2;
      ctx.bezierCurveTo(mx, p0.y, mx, p1.y, p1.x, p1.y);
    }

    if (fillColor) {
      ctx.lineTo(padding.left + (data.length - 1) * stepX, padding.top + graphH);
      ctx.lineTo(padding.left, padding.top + graphH);
      ctx.closePath();
      ctx.fillStyle = fillColor;
      ctx.fill();
    } else {
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 2.5;
      ctx.stroke();
    }
  }

  // Gradient for Total (Cyan neon)
  const gradTotal = ctx.createLinearGradient(0, padding.top, 0, h - padding.bottom);
  gradTotal.addColorStop(0, "rgba(6, 182, 212, 0.35)");
  gradTotal.addColorStop(1, "rgba(6, 182, 212, 0.0)");
  drawCurve("total", null, gradTotal);
  drawCurve("total", "#06b6d4", null);

  // Gradient for Blocked (Red neon)
  const gradBlocked = ctx.createLinearGradient(0, padding.top, 0, h - padding.bottom);
  gradBlocked.addColorStop(0, "rgba(239, 68, 68, 0.45)");
  gradBlocked.addColorStop(1, "rgba(239, 68, 68, 0.0)");
  drawCurve("blocked", null, gradBlocked);
  drawCurve("blocked", "#ef4444", null);

  // Time labels with responsive interval
  ctx.fillStyle = "#64748b";
  ctx.font = "10px sans-serif";
  ctx.textAlign = "center";
  const numLabels = w < 480 ? 4 : (w < 768 ? 6 : 8);
  const labelInterval = Math.max(Math.floor(data.length / numLabels), 1);
  data.forEach((d, i) => {
    if (i % labelInterval === 0 || i === data.length - 1) {
      const x = padding.left + i * stepX;
      ctx.fillText(d.hour, x, h - 8);
    }
  });
}

// Window resize listener
let resizeChartDebounce = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeChartDebounce);
  resizeChartDebounce = setTimeout(() => {
    if (typeof currentView !== "undefined" && currentView === "dashboard") {
      if (cachedTimelineData) drawTimelineChart(cachedTimelineData);
      if (cachedSummaryData) drawDonutChart(cachedSummaryData.query_distribution, cachedSummaryData.total_queries_24h, cachedSummaryData.blocked_queries_24h);
    }
  }, 120);
});

// Window scope exports
window.loadDashboard = loadDashboard;
window.handlePauseBlocking = handlePauseBlocking;
window.handleResumeBlocking = handleResumeBlocking;
window.drawTimelineChart = drawTimelineChart;
window.drawDonutChart = drawDonutChart;
