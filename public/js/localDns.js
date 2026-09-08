async function loadLocalDns() {
  try {
    const records = await apiRequest("/api/local-dns");
    if (!records) return;

    const tbody = document.getElementById("localDnsTableBody");
    if (!tbody) return;

    if (records.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-dim); padding: 20px;">No local DNS mappings configured.</td></tr>`;
      return;
    }

    tbody.innerHTML = records.map(r => {
      const targetId = r.id != null ? r.id : r.domain;
      return `
        <tr class="localdns-card-row">
          <!-- MOBILE VIEW -->
          <td class="mobile-only">
            <div class="localdns-card-header">
              <div style="font-family: monospace; font-weight: 700; color: var(--text-main); font-size: 0.92rem; word-break: break-all;">
                ${r.domain}
                ${r.is_wildcard ? `<span class="pill" style="background: rgba(6, 182, 212, 0.15); color: var(--accent-cyan); margin-left: 6px; font-size: 0.68rem;">Wildcard</span>` : ""}
              </div>
              <button class="btn btn-danger btn-sm" onclick="window.handleDeleteLocalDns('${targetId}', '${r.domain}')" style="padding: 3px 8px; font-size: 0.78rem;">✕</button>
            </div>
            <div class="localdns-target-box" style="margin-top: 8px;">
              <code style="color: var(--accent-green); font-size: 0.84rem; font-weight: 600;">${r.ip_address}</code>
              <span class="pill" style="background: rgba(255, 255, 255, 0.06); font-family: monospace; font-size: 0.72rem;">${r.record_type}</span>
            </div>
          </td>

          <!-- DESKTOP VIEW -->
          <td class="desktop-only">
            <div style="font-family: monospace; font-weight: 600; color: var(--text-main);">
              ${r.domain}
              ${r.is_wildcard ? `<span class="pill" style="background: rgba(6, 182, 212, 0.15); color: var(--accent-cyan); margin-left: 6px;">Wildcard</span>` : ""}
            </div>
          </td>
          <td class="desktop-only"><code style="color: var(--accent-green);">${r.ip_address}</code></td>
          <td class="desktop-only"><span style="font-family: monospace; font-size: 0.78rem; color: var(--text-muted);">${r.record_type}</span></td>
          <td class="desktop-only">
            <button class="btn btn-danger btn-sm" onclick="window.handleDeleteLocalDns('${targetId}', '${r.domain}')">✕ Remove</button>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Error loading local DNS:", err);
  }
}

async function handleAddLocalDns(event) {
  event.preventDefault();
  const domain = document.getElementById("localDomain").value.trim();
  const ipAddress = document.getElementById("localIp").value.trim();
  const btn = event.target ? event.target.querySelector("button[type='submit']") : null;
  if (btn && window.setButtonLoading) {
    window.setButtonLoading(btn, true, "Registering...");
  }

  try {
    const res = await apiRequest("/api/local-dns/add", {
      method: "POST",
      body: JSON.stringify({ domain, ip_address: ipAddress })
    });
    if (res && res.success) {
      showToast(`Added local DNS mapping: ${domain} -> ${ipAddress}`);
      document.getElementById("localDomain").value = "";
      document.getElementById("localIp").value = "";
      await loadLocalDns();
    }
  } catch (err) {
    showToast(`Failed to add record: ${err.message}`, "error");
    console.error(err);
  } finally {
    if (btn && window.setButtonLoading) {
      window.setButtonLoading(btn, false);
    }
  }
}

async function handleDeleteLocalDns(idOrDomain, domainName) {
  const label = domainName || idOrDomain;
  try {
    const res = await apiRequest(`/api/local-dns/${encodeURIComponent(idOrDomain)}`, { method: "DELETE" });
    if (res && res.success) {
      showToast(`Removed local DNS record: ${label}`);
      await loadLocalDns();
    }
  } catch (err) {
    showToast(`Failed to remove record: ${err.message}`, "error");
    console.error(err);
  }
}

// Bind explicitly to window scope to ensure HTML onclick handlers resolve
window.loadLocalDns = loadLocalDns;
window.handleAddLocalDns = handleAddLocalDns;
window.handleDeleteLocalDns = handleDeleteLocalDns;
