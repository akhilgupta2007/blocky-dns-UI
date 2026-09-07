async function loadDashboard() {
  try {
    const summary = await apiRequest("/api/stats/summary");
    if (!summary) return;

    // Update KPIs
    document.getElementById("kpiTotalQueries").textContent = summary.total_queries_24h.toLocaleString();
    document.getElementById("kpiBlockedQueries").textContent = summary.blocked_queries_24h.toLocaleString();
    document.getElementById("kpiBlockedPct").textContent = `${summary.blocked_percent}%`;
    document.getElementById("kpiActiveDevices").textContent = summary.active_devices_count;
    document.getElementById("kpiActiveRules").textContent = summary.active_rules_count.toLocaleString();
    document.getElementById("kpiLatencyText").textContent = `${summary.upstream_latency_ms}ms via Encrypted DoH`;

    updateBlockingBadge(summary.blocking_enabled);

    // Timeline Chart
    const timeline = await apiRequest("/api/stats/timeline");
    if (timeline) drawTimelineChart(timeline);

    // Top Domains
    const topDomains = await apiRequest("/api/stats/top-domains");
    if (topDomains && topDomains.top_blocked) {
      renderTopBlocked(topDomains.top_blocked);
    }

    // Top Devices
    const topDevices = await apiRequest("/api/stats/top-devices");
    if (topDevices) {
      renderDashboardDevices(topDevices);
    }
  } catch (err) {
    console.error("Error loading dashboard:", err);
  }
}

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
          <span style="color: var(--accent-red); font-weight: 600;">${b.count}</span>
        </div>
        <div style="height: 6px; background: rgba(255,255,255,0.05); border-radius: var(--radius-full); overflow: hidden;">
          <div style="height: 100%; width: ${pct}%; background: linear-gradient(90deg, var(--accent-red), #dc2626); border-radius: var(--radius-full);"></div>
        </div>
      </div>
    `;
  }).join("");
}

function renderDashboardDevices(devices) {
  const tbody = document.getElementById("dashboardDevicesTable");
  if (!tbody) return;

  if (devices.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim);">No devices active yet.</td></tr>`;
    return;
  }

  tbody.innerHTML = devices.map(d => {
    const iconMap = {
      tv: "📺", laptop: "💻", phone: "📱", tablet: "📱", iot: "💡", server: "🖥️", printer: "🖨️", device: "🔌"
    };
    const icon = iconMap[d.icon] || "🔌";
    return `
      <tr onclick="filterLogsByClient('${d.client_ip}')" style="cursor: pointer;" title="Click to view requests from ${d.name} (${d.client_ip})">
        <td>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 1.1rem;">${icon}</span>
            <span style="font-weight: 600;">${d.name}</span>
          </div>
        </td>
        <td><code style="color: var(--accent-cyan);">${d.client_ip}</code></td>
        <td style="font-weight: 600;">${d.total_queries.toLocaleString()}</td>
        <td style="color: var(--accent-red); font-weight: 600;">${d.blocked_queries.toLocaleString()}</td>
        <td><span class="pill blocked">${d.blocked_percent}%</span></td>
      </tr>
    `;
  }).join("");
}

// Pure Canvas 2D Smooth Area Chart
function drawTimelineChart(data) {
  const canvas = document.getElementById("timelineChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);

  if (!data || data.length === 0) {
    ctx.fillStyle = "#64748b";
    ctx.font = "14px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No queries recorded in past 24 hours", w / 2, h / 2);
    return;
  }

  const padding = { top: 20, right: 20, bottom: 30, left: 40 };
  const chartW = w - padding.left - padding.right;
  const chartH = h - padding.top - padding.bottom;

  const maxVal = Math.max(...data.map(d => d.total), 10);

  // Draw Grid lines
  ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 0; i <= 4; i++) {
    const y = padding.top + (chartH / 4) * i;
    ctx.moveTo(padding.left, y);
    ctx.lineTo(w - padding.right, y);

    const val = Math.round(maxVal - (maxVal / 4) * i);
    ctx.fillStyle = "#64748b";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(val.toString(), padding.left - 8, y + 3);
  }
  ctx.stroke();

  const stepX = chartW / Math.max(data.length - 1, 1);

  // Helper to draw smooth path
  function drawCurve(prop, strokeColor, fillColor) {
    ctx.beginPath();
    data.forEach((d, i) => {
      const x = padding.left + i * stepX;
      const y = padding.top + chartH - (d[prop] / maxVal) * chartH;
      if (i === 0) ctx.moveTo(x, y);
      else {
        const prevX = padding.left + (i - 1) * stepX;
        const prevY = padding.top + chartH - (data[i - 1][prop] / maxVal) * chartH;
        const cpX1 = prevX + (x - prevX) / 2;
        const cpX2 = cpX1;
        ctx.bezierCurveTo(cpX1, prevY, cpX2, y, x, y);
      }
    });

    if (fillColor) {
      ctx.lineTo(padding.left + (data.length - 1) * stepX, padding.top + chartH);
      ctx.lineTo(padding.left, padding.top + chartH);
      ctx.closePath();
      ctx.fillStyle = fillColor;
      ctx.fill();
    } else {
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 2.5;
      ctx.stroke();
    }
  }

  // Gradient for Total (Violet)
  const gradTotal = ctx.createLinearGradient(0, padding.top, 0, h - padding.bottom);
  gradTotal.addColorStop(0, "rgba(139, 92, 246, 0.35)");
  gradTotal.addColorStop(1, "rgba(139, 92, 246, 0.0)");
  drawCurve("total", null, gradTotal);
  drawCurve("total", "#8b5cf6", null);

  // Gradient for Blocked (Green)
  const gradBlocked = ctx.createLinearGradient(0, padding.top, 0, h - padding.bottom);
  gradBlocked.addColorStop(0, "rgba(16, 185, 129, 0.45)");
  gradBlocked.addColorStop(1, "rgba(16, 185, 129, 0.0)");
  drawCurve("blocked", null, gradBlocked);
  drawCurve("blocked", "#10b981", null);

  // Time labels
  ctx.fillStyle = "#64748b";
  ctx.font = "10px sans-serif";
  ctx.textAlign = "center";
  const labelInterval = Math.max(Math.floor(data.length / 6), 1);
  data.forEach((d, i) => {
    if (i % labelInterval === 0 || i === data.length - 1) {
      const x = padding.left + i * stepX;
      ctx.fillText(d.hour, x, h - 8);
    }
  });
}

// Bind explicitly to window scope
window.loadDashboard = loadDashboard;
window.renderTimelineChart = renderTimelineChart;
