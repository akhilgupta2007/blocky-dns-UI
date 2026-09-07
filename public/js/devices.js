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

      return `
        <tr>
          <td><span style="font-size: 1.3rem;">${icon}</span></td>
          <td><code style="color: var(--accent-cyan); font-weight: 600;">${d.client_ip}</code></td>
          <td style="color: var(--text-muted); font-size: 0.85rem;">${d.hostname || "<span style='color: var(--text-dim)'>Unknown</span>"}</td>
          <td>
            <input type="text" class="form-input" style="padding: 4px 8px; font-size: 0.85rem; width: 180px;" 
              value="${d.friendly_name || ''}" 
              placeholder="Set Nickname..."
              onchange="saveDeviceNickname('${d.client_ip}', this.value, '${d.icon}', '${d.group_name || 'default'}')">
          </td>
          <td>
            <span class="pill" style="background: rgba(255,255,255,0.06); font-family: monospace;">${d.group_name || 'default'}</span>
          </td>
          <td style="font-weight: 600;">${(d.total_queries || 0).toLocaleString()}</td>
          <td><span class="pill blocked">${pct}%</span></td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="triggerDevicePtr('${d.client_ip}')" title="Query Router PTR">🔍 PTR</button>
            <button class="btn btn-secondary btn-sm" onclick="deleteDevice('${d.client_ip}')" title="Remove Device" style="color: #f87171; margin-left: 4px;">✕</button>
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

