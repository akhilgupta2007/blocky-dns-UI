async function loadSettingsView() {
  try {
    // 1. Upstreams
    const data = await apiRequest("/api/upstreams");
    if (data) {
      document.getElementById("toggleStrictMode").checked = data.strict_encrypted_mode;
      const ipv6Toggle = document.getElementById("toggleBlockIpv6");
      if (ipv6Toggle) ipv6Toggle.checked = data.block_ipv6;
      const strategySelect = document.getElementById("selectUpstreamStrategy");
      if (strategySelect && data.strategy) {
        strategySelect.value = data.strategy;
      }
      renderUpstreams(data.upstreams);
    }

    // 2. Settings (retention & router IP)
    const settings = await apiRequest("/api/control/settings");
    if (settings) {
      if (settings.log_retention_days) {
        document.getElementById("settingRetention").value = settings.log_retention_days;
      }
      if (settings.router_ip) {
        document.getElementById("settingRouterIp").value = settings.router_ip;
      }
      const logPtrCheck = document.getElementById("settingLogPtrQueries");
      if (logPtrCheck) {
        logPtrCheck.checked = settings.log_ptr_queries === "true";
      }
    }

    // 3. Blocky Integration Mode & API
    await loadIntegrationSettings();

    // 4. Caching & Prefetching
    await loadCachingSettings();

    // 5. DNSSEC & Privacy Shield
    await loadDnssecSettings();
  } catch (err) {
    console.error("Error loading settings view:", err);
  }

}

function renderUpstreams(upstreams) {
  const tbody = document.getElementById("upstreamsTableBody");
  if (!tbody) return;

  tbody.innerHTML = upstreams.map(u => {
    return `
      <tr>
        <td style="font-weight: 600;">
          ${u.name}
          ${u.is_custom ? `<span class="pill" style="margin-left: 6px; font-size: 0.7rem; background: rgba(168, 85, 247, 0.18); color: #c084fc;">Custom</span>` : ""}
        </td>
        <td><code style="font-size: 0.8rem; color: var(--accent-cyan); word-break: break-all;">${u.endpoint}</code></td>
        <td><span class="pill" style="background: rgba(255,255,255,0.06); text-transform: uppercase;">${u.protocol}</span></td>
        <td>
          ${(u.last_latency_ms != null && u.last_latency_ms > 0)
            ? `<span style="font-family: monospace; font-size: 0.82rem; font-weight: 600; color: var(--accent-green); display: inline-flex; align-items: center; gap: 4px;" title="Measured round-trip latency"><span>⚡</span> ${Math.round(u.last_latency_ms)} ms</span>`
            : `<span style="color: var(--text-dim); font-size: 0.76rem;">Pending</span>`}
        </td>
        <td>
          <label class="switch">
            <input type="checkbox" ${u.enabled ? "checked" : ""} onchange="handleToggleUpstream(${u.id}, this.checked)">
            <span class="slider"></span>
          </label>
        </td>
        <td style="text-align: right;">
          ${u.is_custom ? `<button class="btn btn-icon" title="Delete custom resolver" onclick="handleDeleteUpstream(${u.id}, '${u.name.replace(/'/g, "\\'")}')" style="color: var(--accent-red); padding: 4px 8px;">✕</button>` : ""}
        </td>
      </tr>
    `;
  }).join("");
}

async function handleDeleteUpstream(id, name) {
  try {
    const res = await apiRequest(`/api/upstreams/${id}`, { method: "DELETE" });
    if (res && res.success) {
      showToast(`Removed custom upstream: ${name}`);
      await loadSettingsView();
    }
  } catch (err) {
    showToast(`Failed to remove upstream: ${err.message}`, "error");
    console.error(err);
  }
}

async function handleRestartEngine(btnElement) {
  const btn = btnElement || document.getElementById("btnReloadEngine") || document.querySelector("button[onclick*='handleRestartEngine']");
  const origHtml = btn ? btn.innerHTML : "🔄 Reload Engine";

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span style="display: inline-block; animation: spinAction 0.75s linear infinite; margin-right: 5px;">🔄</span> Reloading...`;
  }
  showToast("Restarting Blocky DNS Engine to apply all changes...");

  try {
    const res = await apiRequest("/api/control/restart-engine", { method: "POST" });
    if (res && res.restarted) {
      showToast("✅ Blocky Engine restarted! Active resolvers updated.");
      if (btn) btn.innerHTML = `✅ Reloaded!`;
    } else {
      const msg = (res && (res.reason || res.error || res.status))
        ? `Config synchronized (${res.reason || res.error || res.status})`
        : "Config synchronized. Please restart container if not in Docker.";
      showToast(msg, "warning");
      if (btn) btn.innerHTML = `⚠️ Config Synced`;
    }
  } catch (err) {
    showToast(`Failed to restart engine: ${err.message}`, "error");
    if (btn) btn.innerHTML = `⚠️ Error`;
    console.error("handleRestartEngine error:", err);
  } finally {
    setTimeout(() => {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = origHtml;
      }
    }, 2500);
  }
}

async function handleToggleBlockIpv6(input) {
  try {
    const res = await apiRequest("/api/upstreams/block-ipv6", {
      method: "POST",
      body: JSON.stringify({ enabled: input.checked })
    });
    if (res && res.success) {
      showToast(input.checked ? "🚫 IPv6 Resolutions Blocked (AAAA dropped & hints stripped)" : "IPv6 Resolutions Allowed");
      loadSettingsView();
    }
  } catch (err) {
    console.error(err);
  }
}

async function handleToggleStrictMode(input) {
  try {
    const res = await apiRequest("/api/upstreams/strict-mode", {
      method: "POST",
      body: JSON.stringify({ enabled: input.checked })
    });
    if (res && res.success) {
      showToast(input.checked ? "🔒 Strict Encrypted DNS Mode Active (DoH/DoT only)" : "Strict Encrypted Mode Disabled");
      loadSettingsView();
    }
  } catch (err) {
    console.error(err);
  }
}

async function handleChangeStrategy(strategy) {
  try {
    const res = await apiRequest("/api/upstreams/strategy", {
      method: "POST",
      body: JSON.stringify({ strategy: strategy })
    });
    if (res && res.success) {
      const labels = {
        parallel_best: "⚡ Parallel Best (Fastest responder wins)",
        strict: "📋 Strict (List order with backup failover)",
        random: "🔒 Random (Single resolver / Privacy)"
      };
      showToast(`Strategy updated: ${labels[strategy] || strategy}`);
    }
  } catch (err) {
    console.error(err);
  }
}

async function handleToggleUpstream(id, enabled) {
  try {
    await apiRequest("/api/upstreams/toggle", {
      method: "POST",
      body: JSON.stringify({ id, enabled })
    });
    showToast(enabled ? "Upstream enabled & synchronized" : "Upstream disabled & synchronized");
  } catch (err) {
    console.error(err);
  }
}

async function handleAddUpstream(event) {
  event.preventDefault();
  const name = document.getElementById("newUpstreamName").value.trim();
  const endpoint = document.getElementById("newUpstreamEndpoint").value.trim();
  const protocol = document.getElementById("newUpstreamProtocol").value;

  try {
    const res = await apiRequest("/api/upstreams/add", {
      method: "POST",
      body: JSON.stringify({ name, endpoint, protocol })
    });
    if (res && res.success) {
      showToast(`Added custom upstream: ${name}`);
      document.getElementById("newUpstreamName").value = "";
      document.getElementById("newUpstreamEndpoint").value = "";
      loadSettingsView();
    }
  } catch (err) {
    console.error(err);
  }
}

async function handleSaveSettings(event) {
  event.preventDefault();
  const retention = parseInt(document.getElementById("settingRetention").value, 10);
  const routerIp = document.getElementById("settingRouterIp").value.trim();
  const logPtr = document.getElementById("settingLogPtrQueries")?.checked || false;

  try {
    const res = await apiRequest("/api/control/settings", {
      method: "POST",
      body: JSON.stringify({
        log_retention_days: retention,
        router_ip: routerIp,
        log_ptr_queries: logPtr
      })
    });
    if (res && res.success) {
      showToast("System settings saved & Blocky config synchronized!");
    }
  } catch (err) {
    console.error(err);
  }
}

async function downloadBackup() {
  try {
    window.location.href = "/api/backup/export";
    showToast("Backup configuration exported!");
  } catch (err) {
    console.error(err);
  }
}

async function uploadBackup(event) {
  const file = event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/backup/import", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast("Backup restored successfully!");
      loadSettingsView();
    } else {
      showToast(data.detail || "Restore failed", "error");
    }
  } catch (err) {
    console.error(err);
    showToast("Restore failed: " + err.message, "error");
  }
}

async function handleChangePassword(event) {
  event.preventDefault();
  const currentPassword = document.getElementById("currentPassword").value;
  const newPassword = document.getElementById("newPassword").value;

  try {
    const res = await apiRequest("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
    });
    if (res && res.success) {
      showToast("Password updated successfully!");
      document.getElementById("currentPassword").value = "";
      document.getElementById("newPassword").value = "";
    }
  } catch (err) {
    console.error(err);
  }
}

function openPasswordModal() {
  const modal = document.getElementById("passwordModal");
  if (modal) {
    modal.style.display = "flex";
    const cur = document.getElementById("modalCurrentPassword");
    if (cur) cur.focus();
  }
}

function closePasswordModal() {
  const modal = document.getElementById("passwordModal");
  if (modal) {
    modal.style.display = "none";
    const cur = document.getElementById("modalCurrentPassword");
    if (cur) cur.value = "";
    const np = document.getElementById("modalNewPassword");
    if (np) np.value = "";
    const cp = document.getElementById("modalConfirmPassword");
    if (cp) cp.value = "";
  }
}

async function handleModalChangePassword(event) {
  event.preventDefault();
  const currentPassword = document.getElementById("modalCurrentPassword").value;
  const newPassword = document.getElementById("modalNewPassword").value;
  const confirmPassword = document.getElementById("modalConfirmPassword").value;

  if (newPassword !== confirmPassword) {
    showToast("New passwords do not match!", "error");
    return;
  }
  if (newPassword.length < 6) {
    showToast("Password must be at least 6 characters!", "error");
    return;
  }

  try {
    const res = await apiRequest("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
    });
    if (res && res.success) {
      showToast("🔑 Admin password updated successfully!");
      closePasswordModal();
    }
  } catch (err) {
    console.error(err);
  }
}

async function handleAutoSortUpstreams() {
  try {
    showToast("Re-ordering upstreams by lowest latency...");
    const res = await apiRequest("/api/upstreams/auto-sort", { method: "POST" });
    if (res && res.success) {
      showToast("⚡ Upstreams synchronized & auto-sorted by lowest latency!");
      loadSettingsView();
    }
  } catch (err) {
    console.error(err);
  }
}

// ----------------------------------------------------
// Blocky Engine Integration (All-in-One vs Existing Server)
// ----------------------------------------------------
async function loadIntegrationSettings() {
  try {
    const data = await apiRequest("/api/control/integration");
    if (!data) return;

    const mode = data.integration_mode || "all-in-one";
    const radios = document.getElementsByName("integrationModeRadio");
    radios.forEach(r => {
      r.checked = (r.value === mode);
    });

    const apiUrlInput = document.getElementById("settingBlockyApiUrl");
    if (apiUrlInput) apiUrlInput.value = data.blocky_api_url || "http://localhost:4000";

    const configPathInput = document.getElementById("settingBlockyConfigPath");
    if (configPathInput) configPathInput.value = data.blocky_config_path || "/app/config/config.yml";

    // Update connection badge
    const badge = document.getElementById("blockyIntegrationBadge");
    if (badge) {
      if (data.status && data.status.online) {
        badge.textContent = `● Connected (${mode === "all-in-one" ? "Internal" : "External"})`;
        badge.style.background = "rgba(16, 185, 129, 0.15)";
        badge.style.color = "var(--accent-green)";
      } else {
        badge.textContent = `● Offline / Unreachable`;
        badge.style.background = "rgba(239, 68, 68, 0.15)";
        badge.style.color = "var(--accent-red)";
      }
    }

    toggleIntegrationModeUI();
  } catch (err) {
    console.error("Error loading integration settings:", err);
  }
}

function toggleIntegrationModeUI() {
  const selectedMode = document.querySelector('input[name="integrationModeRadio"]:checked')?.value || "all-in-one";
  const fields = document.getElementById("existingBlockyConfigFields");
  const labelAllInOne = document.getElementById("labelModeAllInOne");
  const labelExisting = document.getElementById("labelModeExisting");

  if (selectedMode === "existing") {
    if (fields) fields.style.display = "block";
    if (labelExisting) {
      labelExisting.style.borderColor = "var(--accent-green)";
      labelExisting.style.background = "rgba(16, 185, 129, 0.08)";
    }
    if (labelAllInOne) {
      labelAllInOne.style.borderColor = "var(--border)";
      labelAllInOne.style.background = "var(--bg-card)";
    }
  } else {
    if (fields) fields.style.display = "none";
    if (labelAllInOne) {
      labelAllInOne.style.borderColor = "var(--accent-green)";
      labelAllInOne.style.background = "rgba(16, 185, 129, 0.08)";
    }
    if (labelExisting) {
      labelExisting.style.borderColor = "var(--border)";
      labelExisting.style.background = "var(--bg-card)";
    }
  }
}

async function handleTestBlockyConnection() {
  const apiUrlInput = document.getElementById("settingBlockyApiUrl");
  const apiUrl = apiUrlInput ? apiUrlInput.value.trim() : "http://localhost:4000";
  const btn = document.getElementById("btnTestBlocky");
  const resultBox = document.getElementById("blockyTestResult");

  if (!apiUrl) {
    showToast("Please enter a Blocky API URL to test!", "error");
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ Testing...";
  }

  try {
    const res = await apiRequest("/api/control/test-integration", {
      method: "POST",
      body: JSON.stringify({ blocky_api_url: apiUrl })
    });

    if (resultBox) {
      resultBox.style.display = "block";
      if (res && res.online) {
        resultBox.style.background = "rgba(16, 185, 129, 0.12)";
        resultBox.style.border = "1px solid var(--accent-green)";
        resultBox.style.color = "var(--accent-green)";
        resultBox.innerHTML = `
          <strong>✅ Connection Successful!</strong><br>
          <span style="color: var(--text-muted); font-size: 0.78rem;">
            Response latency: <strong>${res.latency_ms}ms</strong> | Blocking: <strong>${res.blocking_enabled ? "Enabled" : "Paused"}</strong> | Endpoint verified.
          </span>
        `;
        showToast(`Target Blocky API is online! (${res.latency_ms}ms)`);
      } else {
        resultBox.style.background = "rgba(239, 68, 68, 0.12)";
        resultBox.style.border = "1px solid var(--accent-red)";
        resultBox.style.color = "var(--accent-red)";
        resultBox.innerHTML = `
          <strong>❌ Connection Failed!</strong><br>
          <span style="color: var(--text-muted); font-size: 0.78rem;">
            ${res.error || "Unable to reach endpoint"}. Ensure the host/IP is reachable on port 4000 and firewall permits traffic.
          </span>
        `;
        showToast("Connection to Blocky instance failed!", "error");
      }
    }
  } catch (err) {
    console.error("Test error:", err);
    if (resultBox) {
      resultBox.style.display = "block";
      resultBox.style.background = "rgba(239, 68, 68, 0.12)";
      resultBox.style.border = "1px solid var(--accent-red)";
      resultBox.style.color = "var(--accent-red)";
      resultBox.textContent = `❌ Error testing connection: ${err.message || err}`;
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "⚡ Test Connection";
    }
  }
}

async function handleSaveIntegration(event) {
  event.preventDefault();
  const mode = document.querySelector('input[name="integrationModeRadio"]:checked')?.value || "all-in-one";
  const apiUrl = (document.getElementById("settingBlockyApiUrl")?.value || "").trim();
  const configPath = (document.getElementById("settingBlockyConfigPath")?.value || "").trim();

  try {
    const res = await apiRequest("/api/control/integration", {
      method: "POST",
      body: JSON.stringify({
        integration_mode: mode,
        blocky_api_url: apiUrl || "http://localhost:4000",
        blocky_config_path: configPath || "/app/config/config.yml"
      })
    });

    if (res && res.success) {
      showToast(`🧩 Integration architecture updated (${mode})!`);
      loadIntegrationSettings();
    }
  } catch (err) {
    console.error(err);
  }
}

// Caching & Optimistic Prefetching Logic
async function loadCachingSettings() {
  try {
    const data = await apiRequest("/api/control/caching");
    if (!data) return;

    const toggleCache = document.getElementById("toggleCachingEnabled");
    if (toggleCache) toggleCache.checked = data.caching_enabled;

    const minTtl = document.getElementById("settingCacheMinTtl");
    if (minTtl) minTtl.value = data.cache_min_ttl;

    const maxTtl = document.getElementById("settingCacheMaxTtl");
    if (maxTtl) maxTtl.value = data.cache_max_ttl;

    const negTtl = document.getElementById("settingCacheNegTtl");
    if (negTtl) negTtl.value = data.cache_neg_ttl;

    const togglePrefetch = document.getElementById("togglePrefetchingEnabled");
    if (togglePrefetch) togglePrefetch.checked = data.prefetching_enabled;

    const prefetchThresh = document.getElementById("settingPrefetchThreshold");
    if (prefetchThresh) prefetchThresh.value = data.prefetch_threshold;
  } catch (err) {
    console.error("Error loading caching settings:", err);
  }
}

async function handleSaveCachingSettings(event) {
  event.preventDefault();
  const cachingEnabled = document.getElementById("toggleCachingEnabled")?.checked ?? true;
  const minTtl = parseInt(document.getElementById("settingCacheMinTtl")?.value || "300", 10);
  const maxTtl = parseInt(document.getElementById("settingCacheMaxTtl")?.value || "86400", 10);
  const negTtl = parseInt(document.getElementById("settingCacheNegTtl")?.value || "1800", 10);
  const prefetchingEnabled = document.getElementById("togglePrefetchingEnabled")?.checked ?? true;
  const prefetchThreshold = parseInt(document.getElementById("settingPrefetchThreshold")?.value || "5", 10);

  try {
    const res = await apiRequest("/api/control/caching", {
      method: "POST",
      body: JSON.stringify({
        caching_enabled: cachingEnabled,
        cache_min_ttl: minTtl,
        cache_max_ttl: maxTtl,
        cache_neg_ttl: negTtl,
        prefetching_enabled: prefetchingEnabled,
        prefetch_threshold: prefetchThreshold
      })
    });

    if (res && res.success) {
      showToast("⚡ High-Speed Caching & Prefetching settings saved!");
      loadCachingSettings();
    }
  } catch (err) {
    console.error("Failed to save caching settings:", err);
  }
}

// DNSSEC & Privacy Shield Logic
async function loadDnssecSettings() {
  try {
    const data = await apiRequest("/api/control/dnssec");
    if (!data) return;

    const toggleDnssec = document.getElementById("toggleDnssecEnabled");
    if (toggleDnssec) toggleDnssec.checked = data.dnssec_enabled;

    const toggleEcs = document.getElementById("toggleAnonymizeEcs");
    if (toggleEcs) toggleEcs.checked = data.edns_anonymize_ecs;
  } catch (err) {
    console.error("Error loading DNSSEC settings:", err);
  }
}

async function handleToggleDnssec(input) {
  const ecs = document.getElementById("toggleAnonymizeEcs")?.checked ?? true;
  try {
    const res = await apiRequest("/api/control/dnssec", {
      method: "POST",
      body: JSON.stringify({
        dnssec_enabled: input.checked,
        edns_anonymize_ecs: ecs
      })
    });

    if (res && res.success) {
      showToast(input.checked ? "🔒 DNSSEC Cryptographic Validation Enabled" : "DNSSEC Validation Disabled");
      loadDnssecSettings();
    }
  } catch (err) {
    console.error("Failed to update DNSSEC:", err);
  }
}

async function handleToggleEcs(input) {
  const dnssec = document.getElementById("toggleDnssecEnabled")?.checked ?? true;
  try {
    const res = await apiRequest("/api/control/dnssec", {
      method: "POST",
      body: JSON.stringify({
        dnssec_enabled: dnssec,
        edns_anonymize_ecs: input.checked
      })
    });

    if (res && res.success) {
      showToast(input.checked ? "🛡️ EDNS Client Subnet Anonymized (ECS IP stripped)" : "EDNS Client Subnet Forwarding Allowed");
      loadDnssecSettings();
    }
  } catch (err) {
    console.error("Failed to update ECS:", err);
  }
}

// Bind explicitly to window scope
window.loadSettingsView = loadSettingsView;
window.handleDeleteUpstream = handleDeleteUpstream;
window.handleToggleUpstream = handleToggleUpstream;
window.handleRestartEngine = handleRestartEngine;
window.handleAddUpstream = handleAddUpstream;
window.handleSaveSettings = handleSaveSettings;
window.handleSaveIntegration = handleSaveIntegration;
window.handleToggleCaching = handleToggleCaching;
window.handleSaveCachingConfig = handleSaveCachingConfig;
window.handleToggleDnssec = handleToggleDnssec;
window.handleToggleEcs = handleToggleEcs;



