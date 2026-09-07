async function populateRoutingPresetsAndTable() {
  const select = document.getElementById("routingPresetSelect");
  const tbody = document.getElementById("routingUpstreamsTableBody");
  const countBadge = document.getElementById("routingResolversCount");

  try {
    const data = await apiRequest("/api/upstreams");
    const upstreams = (data && data.upstreams) ? data.upstreams : [];

    // 1. Populate Preset Selector Dropdown
    if (select) {
      let html = `<option value="">-- Quick Preset / Select Resolver --</option>`;

      if (upstreams.length > 0) {
        html += `<optgroup label="⚡ All Configured DNS Resolvers">`;
        for (const u of upstreams) {
          const customBadge = u.is_custom ? " (Custom)" : "";
          const protoUpper = (u.protocol || "doh").toUpperCase();
          const latStr = (u.last_latency_ms != null && u.last_latency_ms > 0) ? ` [⚡ ${Math.round(u.last_latency_ms)}ms]` : "";
          html += `<option value="${u.endpoint}|${u.name}">${u.name}${customBadge} [${protoUpper}]${latStr} - ${u.endpoint}</option>`;
        }
        html += `</optgroup>`;
      }

      html += `
        <optgroup label="🌍 Geo-Bypass & Regional Presets">
          <option value="https://uk.dns.mullvad.net/dns-query|UK Geo-Bypass">Mullvad UK DoH (United Kingdom)</option>
          <option value="https://dns.quad9.net/dns-query|Swiss Uncensored">Quad9 Swiss DoH (Switzerland)</option>
          <option value="198.51.100.4|SmartDNS US">SmartDNS US Proxy (United States)</option>
          <option value="https://security.cloudflare-dns.com/dns-query|Cloudflare US">Cloudflare US (Security)</option>
        </optgroup>
      `;

      select.innerHTML = html;
    }

    // 2. Populate Configured & Custom DNS Resolvers Catalog Table
    if (tbody) {
      if (upstreams.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 18px;">No upstream resolvers configured.</td></tr>`;
      } else {
        tbody.innerHTML = upstreams.map(u => {
          const isCustom = Boolean(u.is_custom);
          const protoUpper = (u.protocol || "doh").toUpperCase();
          const lat = (u.last_latency_ms != null && u.last_latency_ms > 0)
            ? `${Math.round(u.last_latency_ms)} ms`
            : null;
          const latBadge = lat
            ? `<span style="font-family: monospace; font-size: 0.82rem; font-weight: 600; color: var(--accent-green); display: inline-flex; align-items: center; gap: 4px;" title="Measured benchmark round-trip latency"><span>⚡</span> ${lat}</span>`
            : `<span style="font-size: 0.74rem; color: var(--text-dim);" title="Not benchmarked yet">Pending</span>`;

          const typeBadge = isCustom
            ? `<span class="pill" style="background: rgba(168, 85, 247, 0.2); color: #c084fc; font-size: 0.72rem; border: 1px solid rgba(168, 85, 247, 0.4);">Custom</span>`
            : `<span class="pill" style="background: rgba(100, 116, 139, 0.15); color: var(--text-dim); font-size: 0.72rem;">System</span>`;
          const statusBadge = `
            <div style="display: flex; align-items: center; gap: 8px;">
              <label class="switch" title="Toggle as general network-wide upstream resolver">
                <input type="checkbox" ${u.enabled ? "checked" : ""} onchange="window.handleToggleRoutingUpstream(${u.id}, this.checked)">
                <span class="slider"></span>
              </label>
              <span style="font-size: 0.74rem; font-weight: 500; color: ${u.enabled ? 'var(--accent-green)' : 'var(--text-dim)'};">${u.enabled ? 'Active' : 'Disabled'}</span>
            </div>
          `;

          return `
            <tr>
              <td>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="font-weight: 600; color: var(--text-main);">${u.name}</span>
                </div>
              </td>
              <td><code style="font-family: monospace; font-size: 0.8rem; color: var(--accent-cyan); word-break: break-all;">${u.endpoint}</code></td>
              <td><span class="pill" style="background: rgba(255, 255, 255, 0.06); font-size: 0.72rem; text-transform: uppercase;">${protoUpper}</span></td>
              <td>${latBadge}</td>
              <td>${typeBadge}</td>
              <td>${statusBadge}</td>
              <td style="text-align: right;">
                <div style="display: flex; gap: 6px; justify-content: flex-end; align-items: center;">
                  <button type="button" class="btn btn-secondary btn-sm" onclick="window.useResolverForRoute('${u.endpoint.replace(/'/g, "\\'")}', '${u.name.replace(/'/g, "\\'")}')" style="font-size: 0.75rem; padding: 3px 8px;" title="Use this resolver in routing rule above">
                    + Use in Route
                  </button>
                  ${isCustom ? `<button type="button" class="btn btn-danger btn-sm" onclick="window.handleDeleteRoutingUpstream(${u.id}, '${u.name.replace(/'/g, "\\'")}')" style="padding: 3px 8px; font-size: 0.75rem;" title="Delete custom resolver">✕</button>` : ""}
                </div>
              </td>
            </tr>
          `;
        }).join("");
      }
    }

    if (countBadge) {
      const customCount = upstreams.filter(u => u.is_custom).length;
      countBadge.textContent = `${upstreams.length} Resolvers${customCount > 0 ? ` (${customCount} Custom)` : ""}`;
    }
  } catch (err) {
    console.error("Error populating routing presets & upstreams table:", err);
  }
}

function toggleAddCustomDnsForm() {
  const box = document.getElementById("routingAddCustomDnsBox");
  if (!box) return;
  box.style.display = (box.style.display === "none" || !box.style.display) ? "block" : "none";
  if (box.style.display === "block") {
    const input = document.getElementById("quickDnsName");
    if (input) input.focus();
  }
}

async function handleAddRoutingCustomDns(event) {
  event.preventDefault();
  const name = document.getElementById("quickDnsName").value.trim();
  const endpoint = document.getElementById("quickDnsEndpoint").value.trim();
  const protocol = document.getElementById("quickDnsProtocol").value;

  try {
    const res = await apiRequest("/api/upstreams/add", {
      method: "POST",
      body: JSON.stringify({ name, endpoint, protocol })
    });
    if (res && res.success) {
      showToast(`Added custom resolver: ${name}`);
      document.getElementById("quickDnsName").value = "";
      document.getElementById("quickDnsEndpoint").value = "";
      toggleAddCustomDnsForm();
      await populateRoutingPresetsAndTable();
    }
  } catch (err) {
    showToast(`Failed to add custom resolver: ${err.message}`, "error");
    console.error(err);
  }
}

function useResolverForRoute(endpoint, name) {
  const input = document.getElementById("routingResolver");
  if (input) {
    input.value = endpoint;
    input.focus();
  }
  const select = document.getElementById("routingPresetSelect");
  if (select) {
    const opt = Array.from(select.options).find(o => o.value.startsWith(endpoint));
    if (opt) select.value = opt.value;
  }
  const domainInput = document.getElementById("routingDomain");
  if (domainInput) {
    domainInput.focus();
  }
  showToast(`Selected ${name} for domain routing`);
  const form = document.querySelector("#viewRouting form");
  if (form) form.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function handleDeleteRoutingUpstream(id, name) {
  if (!confirm(`Are you sure you want to remove custom resolver "${name}"?`)) return;
  try {
    const res = await apiRequest(`/api/upstreams/${id}`, { method: "DELETE" });
    if (res && res.success) {
      showToast(`Removed custom resolver: ${name}`);
      await populateRoutingPresetsAndTable();
    }
  } catch (err) {
    showToast(`Failed to remove resolver: ${err.message}`, "error");
    console.error(err);
  }
}

async function loadRouting() {
  await populateRoutingPresetsAndTable();
  try {
    const routings = await apiRequest("/api/routing");
    if (!routings) return;

    const tbody = document.getElementById("routingTableBody");
    if (!tbody) return;

    if (routings.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 20px;">No domain routing rules configured.</td></tr>`;
      return;
    }

    tbody.innerHTML = routings.map(r => {
      const targetId = r.id != null ? r.id : r.domain_pattern;
      return `
        <tr>
          <td><code style="font-weight: 600; color: var(--text-main);">${r.domain_pattern}</code></td>
          <td><span style="font-family: monospace; font-size: 0.82rem; color: var(--accent-cyan);">${r.resolver}</span></td>
          <td><span class="pill" style="background: rgba(139, 92, 246, 0.15); color: var(--accent-violet);">${r.tag}</span></td>
          <td>
            <label class="switch">
              <input type="checkbox" ${r.enabled ? "checked" : ""} onchange="window.handleToggleRouting(${r.id}, this.checked)">
              <span class="slider"></span>
            </label>
          </td>
          <td>
            <button class="btn btn-danger btn-sm" onclick="window.handleDeleteRouting('${targetId}', '${r.domain_pattern}')">✕ Remove</button>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Error loading routing rules:", err);
  }
}

function applyRoutingPreset() {
  const select = document.getElementById("routingPresetSelect");
  if (!select || !select.value) return;
  const [resolver, tag] = select.value.split("|");
  const resolverInput = document.getElementById("routingResolver");
  if (resolverInput) resolverInput.value = resolver;
}

async function handleAddRouting(event) {
  event.preventDefault();
  const domainPattern = document.getElementById("routingDomain").value.trim();
  const resolver = document.getElementById("routingResolver").value.trim();
  const select = document.getElementById("routingPresetSelect");
  let tag = "Geo-Bypass";
  if (select.value && select.value.includes("|")) {
    tag = select.value.split("|")[1];
  }

  try {
    const res = await apiRequest("/api/routing/add", {
      method: "POST",
      body: JSON.stringify({
        domain_pattern: domainPattern,
        resolver: resolver,
        tag: tag
      })
    });
    if (res && res.success) {
      showToast(`Routed ${domainPattern} -> ${resolver}`);
      document.getElementById("routingDomain").value = "";
      document.getElementById("routingResolver").value = "";
      await loadRouting();
    }
  } catch (err) {
    showToast(`Failed to add routing rule: ${err.message}`, "error");
    console.error(err);
  }
}

async function handleToggleRouting(id, enabled) {
  try {
    await apiRequest("/api/routing/toggle", {
      method: "POST",
      body: JSON.stringify({ id, enabled })
    });
    showToast(enabled ? "Routing rule enabled" : "Routing rule disabled");
  } catch (err) {
    showToast(`Failed to toggle rule: ${err.message}`, "error");
    console.error(err);
  }
}

async function handleDeleteRouting(idOrPattern, label) {
  const displayLabel = label || idOrPattern;
  try {
    const res = await apiRequest(`/api/routing/${encodeURIComponent(idOrPattern)}`, { method: "DELETE" });
    if (res && res.success) {
      showToast(`Routing rule deleted: ${displayLabel}`);
      await loadRouting();
    }
  } catch (err) {
    showToast(`Failed to delete routing: ${err.message}`, "error");
    console.error(err);
  }
}

async function handleToggleRoutingUpstream(id, enabled) {
  try {
    const res = await apiRequest("/api/upstreams/toggle", {
      method: "POST",
      body: JSON.stringify({ id, enabled })
    });
    if (res && res.success) {
      showToast(enabled ? "Upstream activated for network-wide resolution" : "Upstream disabled from general pool (available for custom routing)");
      await populateRoutingPresetsAndTable();
    }
  } catch (err) {
    showToast(`Failed to toggle upstream: ${err.message}`, "error");
    console.error(err);
    await populateRoutingPresetsAndTable();
  }
}

// Bind explicitly to window scope
window.loadRouting = loadRouting;
window.populateRoutingPresetsAndTable = populateRoutingPresetsAndTable;
window.toggleAddCustomDnsForm = toggleAddCustomDnsForm;
window.handleAddRoutingCustomDns = handleAddRoutingCustomDns;
window.useResolverForRoute = useResolverForRoute;
window.handleDeleteRoutingUpstream = handleDeleteRoutingUpstream;
window.handleToggleRoutingUpstream = handleToggleRoutingUpstream;
window.applyRoutingPreset = applyRoutingPreset;
window.handleAddRouting = handleAddRouting;
window.handleToggleRouting = handleToggleRouting;
window.handleDeleteRouting = handleDeleteRouting;
