// App State & Routing
let currentView = "dashboard";
let pendingRequests = 0;

function updateRequestIndicator(delta, method = "GET") {
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
      document.getElementById("actionStatusText").textContent = "Processing request...";
      pill.classList.add("active");
    }
  } else {
    document.body.classList.remove("is-busy");
    bar.classList.remove("loading");
    bar.classList.add("done");
    pill.classList.remove("active");
    setTimeout(() => {
      if (pendingRequests === 0) bar.classList.remove("done");
    }, 350);
  }
}

async function apiRequest(endpoint, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  updateRequestIndicator(1, method);
  try {
    const res = await fetch(endpoint, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      }
    });

    if (res.status === 401) {
      window.location.href = "/login";
      return null;
    }

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Request failed");
    }
    return data;
  } catch (err) {
    showToast(err.message, "error");
    throw err;
  } finally {
    updateRequestIndicator(-1, method);
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

function switchView(viewName) {
  currentView = viewName;

  // Update Nav items
  document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));
  const activeNav = document.getElementById("nav" + viewName.charAt(0).toUpperCase() + viewName.slice(1));
  if (activeNav) activeNav.classList.add("active");

  // Update Sections
  document.querySelectorAll(".view-section").forEach(el => el.classList.remove("active"));
  const activeSection = document.getElementById("view" + viewName.charAt(0).toUpperCase() + viewName.slice(1));
  if (activeSection) activeSection.classList.add("active");

  // Trigger view-specific loads
  if (viewName === "dashboard") loadDashboard();
  if (viewName === "queryLog") refreshQueryLogs();
  if (viewName === "blocklists") loadBlocklistsAndRules();
  if (viewName === "devices") loadDevices();
  if (viewName === "localDns") loadLocalDns();
  if (viewName === "routing") loadRouting();
  if (viewName === "tools") loadToolsInfo();
  if (viewName === "settings") loadSettingsView();
  if (viewName === "blockedServices") loadBlockedServices();
}

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
      showToast(`DNS Blocking paused for ${duration}`);
      updateBlockingBadge(false);
    }
  } catch (err) {
    console.error(err);
  }
}

async function triggerListRefresh() {
  const btn = document.getElementById("btnRefreshAll");
  if (btn) btn.disabled = true;
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
    if (btn) btn.disabled = false;
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
        window.location.href = "/login";
      } else if (d.user) {
        const userEl = document.getElementById("sidebarUsername");
        if (userEl) userEl.textContent = d.user;
      }
    });

  // Initial load
  loadDashboard();
  // Auto-refresh summary every 10s
  setInterval(() => {
    if (currentView === "dashboard") loadDashboard();
  }, 10000);
});
