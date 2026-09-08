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
          <option value="tcp-tls:common.dot.dns.yandex.net:853|Yandex DoT">Yandex DNS DoT (TLS Port 853)</option>
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
            <tr class="upstream-catalog-card-row">
              <!-- MOBILE VIEW -->
              <td class="mobile-only">
                <div class="upstream-card-header">
                  <span style="font-weight: 700; color: var(--text-main); font-size: 0.92rem;">${u.name}</span>
                  <div style="display: flex; align-items: center; gap: 6px;">
                    <span class="pill" style="background: rgba(255, 255, 255, 0.06); font-size: 0.68rem; text-transform: uppercase;">${protoUpper}</span>
                    ${typeBadge}
                  </div>
                </div>
                <div class="upstream-details-box" style="margin-top: 8px;">
                  <code style="font-family: monospace; font-size: 0.78rem; color: var(--accent-cyan); word-break: break-all;">${u.endpoint}</code>
                  <div class="upstream-controls-line">
                    <div>${latBadge}</div>
                    ${statusBadge}
                  </div>
                </div>
                <div style="display: flex; gap: 8px; margin-top: 10px;">
                  <button type="button" class="btn btn-secondary btn-sm" onclick="window.useResolverForRoute('${u.endpoint.replace(/'/g, "\\'")}', '${u.name.replace(/'/g, "\\'")}')" style="flex: 1; font-size: 0.8rem; padding: 6px;" title="Use this resolver in routing rule above">
                    + Use in Route
                  </button>
                  ${isCustom ? `<button type="button" class="btn btn-danger btn-sm" onclick="window.handleDeleteRoutingUpstream(${u.id}, '${u.name.replace(/'/g, "\\'")}')" style="padding: 6px 12px; font-size: 0.8rem;" title="Delete custom resolver">✕</button>` : ""}
                </div>
              </td>

              <!-- DESKTOP VIEW -->
              <td class="desktop-only">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="font-weight: 600; color: var(--text-main);">${u.name}</span>
                </div>
              </td>
              <td class="desktop-only"><code style="font-family: monospace; font-size: 0.8rem; color: var(--accent-cyan); word-break: break-all;">${u.endpoint}</code></td>
              <td class="desktop-only"><span class="pill" style="background: rgba(255, 255, 255, 0.06); font-size: 0.72rem; text-transform: uppercase;">${protoUpper}</span></td>
              <td class="desktop-only">${latBadge}</td>
              <td class="desktop-only">${typeBadge}</td>
              <td class="desktop-only">${statusBadge}</td>
              <td class="desktop-only" style="text-align: right;">
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
  const btn = event.target ? event.target.querySelector("button[type='submit']") : null;
  if (btn && window.setButtonLoading) {
    window.setButtonLoading(btn, true, "Adding...");
  }

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
  } finally {
    if (btn && window.setButtonLoading) {
      window.setButtonLoading(btn, false);
    }
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
        <tr class="routing-card-row">
          <!-- MOBILE VIEW -->
          <td class="mobile-only">
            <div class="routing-card-header">
              <code style="font-weight: 700; color: var(--text-main); font-size: 0.9rem; word-break: break-all;">${r.domain_pattern}</code>
              <div style="display: flex; align-items: center; gap: 8px;">
                <label class="switch">
                  <input type="checkbox" ${r.enabled ? "checked" : ""} onchange="window.handleToggleRouting(${r.id}, this.checked)">
                  <span class="slider"></span>
                </label>
                <button class="btn btn-danger btn-sm" onclick="window.handleDeleteRouting('${targetId}', '${r.domain_pattern}')" style="padding: 3px 8px; font-size: 0.78rem;">✕</button>
              </div>
            </div>
            <div class="routing-resolver-box" style="margin-top: 8px;">
              <span style="font-size: 0.72rem; color: var(--text-dim);">Dedicated Upstream Resolver:</span>
              <span style="font-family: monospace; font-size: 0.8rem; color: var(--accent-cyan); word-break: break-all;">${r.resolver}</span>
              <div style="margin-top: 4px;">
                <span class="pill" style="background: rgba(139, 92, 246, 0.15); color: var(--accent-violet); font-size: 0.7rem;">${r.tag}</span>
              </div>
            </div>
          </td>

          <!-- DESKTOP VIEW -->
          <td class="desktop-only"><code style="font-weight: 600; color: var(--text-main);">${r.domain_pattern}</code></td>
          <td class="desktop-only"><span style="font-family: monospace; font-size: 0.82rem; color: var(--accent-cyan);">${r.resolver}</span></td>
          <td class="desktop-only"><span class="pill" style="background: rgba(139, 92, 246, 0.15); color: var(--accent-violet);">${r.tag}</span></td>
          <td class="desktop-only">
            <label class="switch">
              <input type="checkbox" ${r.enabled ? "checked" : ""} onchange="window.handleToggleRouting(${r.id}, this.checked)">
              <span class="slider"></span>
            </label>
          </td>
          <td class="desktop-only">
            <button class="btn btn-danger btn-sm" onclick="window.handleDeleteRouting('${targetId}', '${r.domain_pattern}')">✕ Remove</button>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Error loading routing rules:", err);
  }
}

function detectAndNormalizeResolver(val) {
  let ep = (val || "").trim();
  if (!ep) return { endpoint: "", protocol: "udp" };

  if (ep.startsWith("tls://") || ep.startsWith("dot://")) {
    let host = ep.split("://")[1].replace(/\/.*$/, "");
    if (!host.includes(":")) host += ":853";
    return { endpoint: `tcp-tls:${host}`, protocol: "dot" };
  }
  if (ep.startsWith("tcp-tls:")) {
    let host = ep.substring("tcp-tls:".length).replace(/\/.*$/, "");
    if (!host.includes(":")) host += ":853";
    return { endpoint: `tcp-tls:${host}`, protocol: "dot" };
  }
  if (ep.startsWith("udp://") || ep.startsWith("udp:")) {
    return { endpoint: ep.replace(/^udp:\/\//, "").replace(/^udp:/, ""), protocol: "udp" };
  }

  const cleanHost = ep.replace(/^https?:\/\//, "").split("/")[0].split(":")[0];
  const hasPort853 = ep.includes(":853");
  const hasDotInHost = cleanHost.toLowerCase().includes(".dot.") || cleanHost.toLowerCase().startsWith("dot.");

  if (hasPort853 || hasDotInHost) {
    let port = "853";
    const netloc = ep.replace(/^https?:\/\//, "").split("/")[0];
    if (netloc.includes(":")) {
      const p = netloc.split(":")[1];
      if (/^\d+$/.test(p)) port = p;
    }
    return { endpoint: `tcp-tls:${cleanHost}:${port}`, protocol: "dot" };
  }

  // Pure IP
  if (/^(\d{1,3}\.){3}\d{1,3}(:\d+)?$/.test(ep)) {
    if (ep.includes(":853")) {
      return { endpoint: `tcp-tls:${ep.split(":")[0]}:853`, protocol: "dot" };
    }
    return { endpoint: ep, protocol: "udp" };
  }

  // HTTPS or hostname
  if (!ep.startsWith("http://") && !ep.startsWith("https://")) {
    ep = `https://${ep}`;
  }
  if (!ep.replace(/^https?:\/\//, "").includes("/")) {
    ep = `${ep}/dns-query`;
  }
  return { endpoint: ep, protocol: "doh" };
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
  let rawResolver = document.getElementById("routingResolver").value.trim();
  const select = document.getElementById("routingPresetSelect");
  const btn = event.target ? event.target.querySelector("button[type='submit']") : null;
  if (btn && window.setButtonLoading) {
    window.setButtonLoading(btn, true, "Routing...");
  }
  let tag = "Geo-Bypass";
  if (select.value && select.value.includes("|")) {
    tag = select.value.split("|")[1];
  }

  // Auto-detect and normalize endpoint on client side
  const detected = detectAndNormalizeResolver(rawResolver);
  const resolverToSubmit = detected.endpoint || rawResolver;

  try {
    const res = await apiRequest("/api/routing/add", {
      method: "POST",
      body: JSON.stringify({
        domain_pattern: domainPattern,
        resolver: resolverToSubmit,
        tag: tag
      })
    });
    if (res && res.success) {
      const finalResolver = res.normalized_resolver || resolverToSubmit;
      showToast(`Routed ${domainPattern} -> ${finalResolver}`);
      document.getElementById("routingDomain").value = "";
      document.getElementById("routingResolver").value = "";
      await loadRouting();
      if (window.loadRoutingRulesCache) window.loadRoutingRulesCache(true);
    }
  } catch (err) {
    showToast(`Failed to add routing rule: ${err.message}`, "error");
    console.error(err);
  } finally {
    if (btn && window.setButtonLoading) {
      window.setButtonLoading(btn, false);
    }
  }
}

async function handleToggleRouting(id, enabled) {
  try {
    await apiRequest("/api/routing/toggle", {
      method: "POST",
      body: JSON.stringify({ id, enabled })
    });
    showToast(enabled ? "Routing rule enabled" : "Routing rule disabled");
    if (window.loadRoutingRulesCache) window.loadRoutingRulesCache(true);
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
      if (window.loadRoutingRulesCache) window.loadRoutingRulesCache(true);
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
