async function loadDevices() {
  try {
    const devices = await apiRequest("/api/devices");
    if (!devices) return;

    const tbody = document.getElementById("devicesTableBody");
    if (!tbody) return;

    if (devices.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-dim); padding: 24px;">No client devices discovered yet.</td></tr>`;
      return;
    }

    const iconMap = { tv: "📺", laptop: "💻", phone: "📱", tablet: "📱", iot: "💡", server: "🖥️", printer: "🖨️", device: "🔌" };

    tbody.innerHTML = devices.map(d => {
      const icon = iconMap[d.icon] || "🔌";
      const pct = d.total_queries > 0 ? Math.round((d.blocked_queries / d.total_queries) * 100) : 0;
      const safeIp = escapeHtml(d.client_ip);
      const safeHost = escapeHtml(d.hostname || "");
      const safeFriendly = escapeHtml(d.friendly_name || "");
      const safeDisplayName = escapeHtml(d.friendly_name || d.hostname || d.client_ip);
      const safeGroup = escapeHtml(d.group_name || "default");
      const safeIcon = escapeHtml(d.icon || "device");

      return `
        <tr class="device-card-row">
          <!-- MOBILE VIEW CARD -->
          <td class="mobile-only">
            <div class="device-card-header">
              <div class="device-title-box">
                <span>${icon}</span>
                <span style="font-weight: 700; color: var(--text-main);">${safeDisplayName}</span>
              </div>
              <span class="pill" style="background: rgba(255,255,255,0.08); font-family: monospace; font-size: 0.72rem;">${safeGroup}</span>
            </div>
            <div style="display: flex; align-items: center; justify-content: space-between; font-size: 0.8rem; margin-top: 4px;">
              <code style="color: var(--accent-cyan); font-weight: 600; font-family: monospace;">${safeIp}</code>
              <span style="color: var(--text-dim); font-size: 0.76rem;">${safeHost || 'Unknown Host'}</span>
            </div>
            <div class="device-stats-grid" style="margin-top: 8px;">
              <div>
                <span style="font-size: 0.72rem; color: var(--text-dim); display: block;">Total Queries</span>
                <strong style="color: var(--text-main); font-size: 0.88rem;">${(d.total_queries || 0).toLocaleString()}</strong>
              </div>
              <div>
                <span style="font-size: 0.72rem; color: var(--text-dim); display: block;">Blocked Rate</span>
                <span class="pill blocked" style="font-size: 0.72rem; padding: 1px 6px;">${pct}%</span>
              </div>
            </div>
            <div class="device-actions-row" style="margin-top: 10px;">
              <input type="text" class="form-input" style="flex: 1; font-size: 0.82rem; padding: 6px 8px;" 
                value="${safeFriendly}" 
                placeholder="Set Nickname..."
                data-ip="${safeIp}" data-icon="${safeIcon}" data-group="${safeGroup}"
                onchange="saveDeviceNickname(this.dataset.ip, this.value, this.dataset.icon, this.dataset.group)">
              <button class="btn btn-secondary btn-sm" data-ip="${safeIp}" onclick="triggerDevicePtr(this.dataset.ip)" title="Query Router PTR">🔍 PTR</button>
              <button class="btn btn-danger btn-sm" data-ip="${safeIp}" onclick="deleteDevice(this.dataset.ip)" title="Remove Device">✕</button>
            </div>
          </td>

          <!-- DESKTOP VIEW CELLS -->
          <td class="desktop-only"><span style="font-size: 1.3rem;">${icon}</span></td>
          <td class="desktop-only"><code style="color: var(--accent-cyan); font-weight: 600;">${safeIp}</code></td>
          <td class="desktop-only" style="color: var(--text-muted); font-size: 0.85rem;">${safeHost || "<span style='color: var(--text-dim)'>Unknown</span>"}</td>
          <td class="desktop-only">
            <input type="text" class="form-input" style="padding: 4px 8px; font-size: 0.85rem; width: 180px;" 
              value="${safeFriendly}" 
              placeholder="Set Nickname..."
              data-ip="${safeIp}" data-icon="${safeIcon}" data-group="${safeGroup}"
              onchange="saveDeviceNickname(this.dataset.ip, this.value, this.dataset.icon, this.dataset.group)">
          </td>
          <td class="desktop-only">
            <span class="pill" style="background: rgba(255,255,255,0.06); font-family: monospace;">${safeGroup}</span>
          </td>
          <td class="desktop-only" style="font-weight: 600;">${(d.total_queries || 0).toLocaleString()}</td>
          <td class="desktop-only"><span class="pill blocked">${pct}%</span></td>
          <td class="desktop-only">
            <button class="btn btn-secondary btn-sm" data-ip="${safeIp}" onclick="triggerDevicePtr(this.dataset.ip)" title="Query Router PTR">🔍 PTR</button>
            <button class="btn btn-secondary btn-sm" data-ip="${safeIp}" onclick="deleteDevice(this.dataset.ip)" title="Remove Device" style="color: #f87171; margin-left: 4px;">✕</button>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Error loading devices:", err);
  }
}

async function saveDeviceNickname(clientIp, friendlyName, icon, groupName) {
  try {
    await apiRequest("/api/devices/update", {
      method: "POST",
      body: JSON.stringify({
        client_ip: clientIp,
        friendly_name: friendlyName,
        icon: icon,
        group_name: groupName
      })
    });
    showToast(`Updated name for ${clientIp}`);
  } catch (err) {
    console.error(err);
  }
}

async function triggerDevicePtr(clientIp) {
  try {
    await apiRequest(`/api/devices/resolve-ptr/${clientIp}`, { method: "POST" });
    showToast(`Dispatched reverse PTR query for ${clientIp}`);
    setTimeout(loadDevices, 1500);
  } catch (err) {
    console.error(err);
  }
}

async function deleteDevice(clientIp) {
  try {
    const res = await apiRequest(`/api/devices/${encodeURIComponent(clientIp)}`, { method: "DELETE" });
    showToast(`Removed device ${clientIp}`);
    await loadDevices();
  } catch (err) {
    showToast(`Failed to remove device: ${err.message}`, "error");
    console.error(err);
  }
}

async function clearDemoDevices() {
  try {
    const res = await apiRequest("/api/devices/clear-demo", { method: "POST" });
    showToast(res.message || "Demo devices and logs cleared!");
    await loadDevices();
    if (typeof window.loadDashboard === "function") window.loadDashboard();
    if (typeof window.refreshQueryLogs === "function") window.refreshQueryLogs();
  } catch (err) {
    showToast(`Failed to clear demo devices: ${err.message}`, "error");
    console.error(err);
  }
}

// Bind explicitly to window scope
window.loadDevices = loadDevices;
window.saveDeviceNickname = saveDeviceNickname;
window.triggerDevicePtr = triggerDevicePtr;
window.deleteDevice = deleteDevice;
window.clearDemoDevices = clearDemoDevices;

