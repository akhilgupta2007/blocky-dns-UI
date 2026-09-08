// App State & Routing
let currentView = "dashboard";
let pendingRequests = 0;

function updateRequestIndicator(delta, method = "GET", endpoint = "") {
  pendingRequests = Math.max(0, pendingRequests + delta);

  let bar = document.getElementById("globalProgressBar");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "globalProgressBar";
    bar.className = "global-progress-bar";
    document.body.appendChild(bar);
  }

  let pill = document.getElementById("actionStatusPill");
  if (!pill) {
    pill = document.createElement("div");
    pill.id = "actionStatusPill";
    pill.className = "action-status-pill";
    pill.innerHTML = `<div class="action-status-spinner"></div><span id="actionStatusText">Applying changes...</span>`;
    document.body.appendChild(pill);
  }

  if (pendingRequests > 0) {
    document.body.classList.add("is-busy");
    bar.classList.remove("done");
    bar.classList.add("loading");

    const isMutating = ["POST", "PUT", "DELETE", "PATCH"].includes((method || "").toUpperCase());
    if (isMutating) {
      let msg = "Processing request...";
      const ep = endpoint || "";
      if (ep.includes("/control/pause")) msg = "Pausing DNS protection...";
      else if (ep.includes("/control/enable")) msg = "Resuming DNS shield...";
      else if (ep.includes("refresh")) msg = "Compiling & reloading all blocklists...";
      else if (ep.includes("/blocklists/toggle")) msg = "Updating blocklist...";
      else if (ep.includes("/blocklists/add")) msg = "Adding blocklist subscription...";
      else if (ep.includes("/rules/add")) msg = "Compiling domain rule...";
      else if (ep.includes("/rules/delete")) msg = "Removing domain rule...";
      else if (ep.includes("/rules/import-adguard")) msg = "Parsing & importing rules...";
      else if (ep.includes("/services/toggle")) msg = "Updating blocked service...";
      else if (ep.includes("/local-dns/add")) msg = "Registering local DNS record...";
      else if (ep.includes("/local-dns/delete")) msg = "Removing local DNS record...";
      else if (ep.includes("/routing/add")) msg = "Saving SmartDNS routing rule...";
      else if (ep.includes("/routing/delete")) msg = "Removing routing rule...";
      else if (ep.includes("/upstreams/add")) msg = "Saving upstream resolver...";
      else if (ep.includes("/tools/benchmark")) msg = "Measuring upstream round-trip latency...";
      else if (ep.includes("/tools/diagnostic")) msg = "Testing domain query...";
      else if (ep.includes("/tools/dnssec-inspect")) msg = "Validating DNSSEC cryptography...";
      else if (ep.includes("restart-engine")) msg = "Restarting Blocky engine...";
      else if (ep.includes("/auth/change-password")) msg = "Updating password...";
      else if (ep.includes("/control/settings")) msg = "Synchronizing configuration...";
      else if (ep.includes("/tools/caching")) msg = "Saving cache & prefetch settings...";
      else if (ep.includes("/tools/integration")) msg = "Saving integration architecture...";

      document.getElementById("actionStatusText").textContent = msg;
      pill.classList.add("active");
    }
  } else {
    document.body.classList.remove("is-busy");
    bar.classList.remove("loading");
    bar.classList.add("done");
    pill.classList.remove("active");
    setTimeout(() => {
      if (pendingRequests === 0) {
        bar.classList.remove("loading", "done");
      }
    }, 450);
  }
}

function setButtonLoading(btn, isLoading, loadingText = "Saving...") {
  if (!btn) return;
  if (isLoading) {
    btn.dataset.origHtml = btn.innerHTML;
    btn.classList.add("is-loading");
    btn.disabled = true;
    btn.innerHTML = `<span class="btn-spinner"></span> ${loadingText}`;
  } else {
    btn.classList.remove("is-loading");
    btn.disabled = false;
    if (btn.dataset.origHtml) {
      btn.innerHTML = btn.dataset.origHtml;
      delete btn.dataset.origHtml;
    }
  }
}
window.setButtonLoading = setButtonLoading;

async function apiRequest(endpoint, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  updateRequestIndicator(1, method, endpoint);
  try {
    const res = await fetch(endpoint, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      }
    });

    if (res.status === 401) {
      document.cookie = "blockydns_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
      window.location.href = "/login";
      return null;
    }

    let data;
    const text = await res.text();
    try {
      data = JSON.parse(text);
    } catch (jsonErr) {
      data = { detail: text || `HTTP ${res.status} ${res.statusText}` };
    }

    if (!res.ok) {
      throw new Error(data.detail || `Request failed with HTTP status ${res.status}`);
    }
    return data;
  } catch (err) {
    showToast(err.message, "error");
    throw err;
  } finally {
    updateRequestIndicator(-1, method, endpoint);
  }
}

function showToast(message, type = "success") {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span>${type === "success" ? "✅" : "⚠️"}</span>
    <span>${message}</span>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 250);
  }, 3500);
}

function toggleMobileSidebar() {
  const sidebar = document.querySelector(".sidebar");
  const backdrop = document.getElementById("sidebarBackdrop");
  if (sidebar) sidebar.classList.toggle("mobile-open");
  if (backdrop) backdrop.classList.toggle("active");
}

function closeMobileSidebar() {
  const sidebar = document.querySelector(".sidebar");
  const backdrop = document.getElementById("sidebarBackdrop");
  if (sidebar) sidebar.classList.remove("mobile-open");
  if (backdrop) backdrop.classList.remove("active");
}

window.toggleMobileSidebar = toggleMobileSidebar;
window.closeMobileSidebar = closeMobileSidebar;

let currentProtectionTab = "adlists";
let currentRoutingTab = "localDns";
let currentSettingsTab = "resolvers";

function switchView(viewName, subTab = null) {
  closeMobileSidebar();

  // Resolve aliases
  let canonicalView = viewName;
  let targetSubTab = subTab;

  if (viewName === "blocklists" || viewName === "protection") {
    canonicalView = "protection";
    if (!targetSubTab) targetSubTab = currentProtectionTab || "adlists";
  } else if (viewName === "blockedServices") {
    canonicalView = "protection";
    targetSubTab = "blockedServices";
  } else if (viewName === "localDns") {
    canonicalView = "routing";
    targetSubTab = "localDns";
  } else if (viewName === "tools") {
    canonicalView = "settings";
    targetSubTab = "tools";
  } else if (viewName === "routing") {
    if (!targetSubTab) targetSubTab = currentRoutingTab || "localDns";
  } else if (viewName === "settings") {
    if (!targetSubTab) targetSubTab = currentSettingsTab || "resolvers";
  }

  currentView = canonicalView;

  // Update Desktop & Mobile Nav items
  document.querySelectorAll(".nav-item, .bottom-nav-item").forEach(el => el.classList.remove("active"));

  const navSuffix = canonicalView.charAt(0).toUpperCase() + canonicalView.slice(1);
  const activeNav = document.getElementById("nav" + navSuffix);
  const activeBottomNav = document.getElementById("bottomNav" + navSuffix);
  if (activeNav) activeNav.classList.add("active");
  if (activeBottomNav) activeBottomNav.classList.add("active");

  // Support legacy nav item IDs if present
  if (viewName === "blocklists") {
    const legacyNav = document.getElementById("navBlocklists");
    if (legacyNav) legacyNav.classList.add("active");
  }

  // Update Sections
  document.querySelectorAll(".view-section").forEach(el => el.classList.remove("active"));
  const activeSection = document.getElementById("view" + navSuffix);
  if (activeSection) activeSection.classList.add("active");

  // Activate subtab if applicable
  if (canonicalView === "protection" && targetSubTab) {
    switchProtectionSubTab(targetSubTab, false);
  } else if (canonicalView === "routing" && targetSubTab) {
    switchRoutingSubTab(targetSubTab, false);
  } else if (canonicalView === "settings" && targetSubTab) {
    switchSettingsSubTab(targetSubTab, false);
  }

  // Trigger view-specific loads
  if (canonicalView === "dashboard") loadDashboard();
  if (canonicalView === "queryLog") refreshQueryLogs();
  if (canonicalView === "protection") {
    if (targetSubTab === "blockedServices") {
      loadBlockedServices();
    } else {
      loadBlocklistsAndRules();
    }
  }
  if (canonicalView === "devices") loadDevices();
  if (canonicalView === "routing") {
    if (targetSubTab === "smartDns") {
      loadRouting();
    } else {
      loadLocalDns();
    }
  }
  if (canonicalView === "settings") {
    if (targetSubTab === "tools") {
      loadToolsInfo();
    } else {
      loadSettingsView();
    }
  }
}

function switchProtectionSubTab(tabName, shouldLoad = true) {
  currentProtectionTab = tabName;
  document.querySelectorAll("#viewProtection .subnav-pill").forEach(p => p.classList.remove("active"));
  document.querySelectorAll("#viewProtection .sub-pane").forEach(p => p.classList.remove("active"));

  const btn = document.getElementById("subtabBtn" + tabName.charAt(0).toUpperCase() + tabName.slice(1));
  const pane = document.getElementById("subpane" + tabName.charAt(0).toUpperCase() + tabName.slice(1));
  if (btn) btn.classList.add("active");
  if (pane) pane.classList.add("active");

  if (shouldLoad) {
    if (tabName === "blockedServices") {
      loadBlockedServices();
    } else {
      loadBlocklistsAndRules();
    }
  }
}

function switchRoutingSubTab(tabName, shouldLoad = true) {
  currentRoutingTab = tabName;
  document.querySelectorAll("#viewRouting .subnav-pill").forEach(p => p.classList.remove("active"));
  document.querySelectorAll("#viewRouting .sub-pane").forEach(p => p.classList.remove("active"));

  const btn = document.getElementById("subtabBtn" + tabName.charAt(0).toUpperCase() + tabName.slice(1));
  const pane = document.getElementById("subpane" + tabName.charAt(0).toUpperCase() + tabName.slice(1));
  if (btn) btn.classList.add("active");
  if (pane) pane.classList.add("active");

  if (shouldLoad) {
    if (tabName === "localDns") {
      loadLocalDns();
    } else if (tabName === "smartDns") {
      loadRouting();
    }
  }
}

function switchSettingsSubTab(tabName, shouldLoad = true) {
  currentSettingsTab = tabName;
  document.querySelectorAll("#viewSettings .subnav-pill").forEach(p => p.classList.remove("active"));
  document.querySelectorAll("#viewSettings .sub-pane").forEach(p => p.classList.remove("active"));

  const btn = document.getElementById("subtabBtn" + tabName.charAt(0).toUpperCase() + tabName.slice(1));
  const pane = document.getElementById("subpane" + tabName.charAt(0).toUpperCase() + tabName.slice(1));
  if (btn) btn.classList.add("active");
  if (pane) pane.classList.add("active");

  if (shouldLoad) {
    if (tabName === "tools") {
      loadToolsInfo();
    } else {
      loadSettingsView();
    }
  }
}

window.switchView = switchView;
window.switchProtectionSubTab = switchProtectionSubTab;
window.switchRoutingSubTab = switchRoutingSubTab;
window.switchSettingsSubTab = switchSettingsSubTab;

function pauseBlockingPrompt() {
  document.getElementById("pauseModal").classList.add("active");
}

function closePauseModal() {
  document.getElementById("pauseModal").classList.remove("active");
}

async function executePause(duration) {
  closePauseModal();
  try {
    const res = await apiRequest("/api/control/pause", {
      method: "POST",
      body: JSON.stringify({ duration })
    });
    if (res && res.success) {
      showToast(`DNS Shield paused for ${duration} (Cache flushed)`);
      updateBlockingBadge(false);
    }
  } catch (err) {
    console.error(err);
  }
}

async function triggerListRefresh() {
  const btn = document.getElementById("btnRefreshAll");
  if (btn && window.setButtonLoading) {
    window.setButtonLoading(btn, true, "Compiling...");
  } else if (btn) {
    btn.disabled = true;
  }
  showToast("Recompiling and refreshing all blocklists...");
  try {
    const res = await apiRequest("/api/blocklists/refresh", { method: "POST" });
    if (res && res.success) {
      showToast("All blocklists reloaded successfully!");
      loadDashboard();
    }
  } catch (err) {
    console.error(err);
  } finally {
    if (btn && window.setButtonLoading) {
      window.setButtonLoading(btn, false);
    } else if (btn) {
      btn.disabled = false;
    }
  }
}

function updateBlockingBadge(active) {
  const badge = document.getElementById("blockingStatusBadge");
  const text = document.getElementById("blockingStatusText");
  if (active) {
    badge.className = "status-badge";
    text.textContent = "Blocking Active";
  } else {
    badge.className = "status-badge paused";
    text.textContent = "Blocking Paused";
  }
}

async function handleLogout() {
  await apiRequest("/api/auth/logout", { method: "POST" });
  window.location.href = "/login";
}

document.addEventListener("DOMContentLoaded", () => {
  // Check auth user
  fetch("/api/auth/status")
    .then(r => r.json())
    .then(d => {
      if (!d.authenticated) {
        document.cookie = "blockydns_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
        window.location.href = "/login";
      } else if (d.user) {
        const userEl = document.getElementById("sidebarUsername");
        if (userEl) userEl.textContent = d.user;
      }
    })
    .catch(() => {
      document.cookie = "blockydns_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
      window.location.href = "/login";
    });

  // Initial load
  loadDashboard();
  // Auto-refresh summary every 10s
  setInterval(() => {
    if (currentView === "dashboard") loadDashboard();
  }, 10000);
});
