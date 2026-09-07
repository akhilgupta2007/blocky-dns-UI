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
        <tr>
          <td>
            <div style="font-family: monospace; font-weight: 600; color: var(--text-main);">
              ${r.domain}
              ${r.is_wildcard ? `<span class="pill" style="background: rgba(6, 182, 212, 0.15); color: var(--accent-cyan); margin-left: 6px;">Wildcard</span>` : ""}
            </div>
          </td>
          <td><code style="color: var(--accent-green);">${r.ip_address}</code></td>
          <td><span style="font-family: monospace; font-size: 0.78rem; color: var(--text-muted);">${r.record_type}</span></td>
          <td>
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
