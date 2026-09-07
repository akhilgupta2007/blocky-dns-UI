// 1-Click Blocked Services Logic

let allBlockedServices = [];
let currentCategoryFilter = "ALL";

async function loadBlockedServices() {
  try {
    const data = await apiRequest("/api/services");
    if (!data) return;

    allBlockedServices = data.services || [];

    // Update Nav Badge
    const navBadge = document.getElementById("blockedServicesNavBadge");
    if (navBadge) {
      navBadge.textContent = data.total_blocked_services || 0;
      navBadge.style.display = data.total_blocked_services > 0 ? "inline-block" : "none";
    }

    // Update Section Summary Badge
    const summaryBadge = document.getElementById("servicesBlockedSummaryBadge");
    if (summaryBadge) {
      summaryBadge.textContent = `${data.total_blocked_services || 0} Blocked (${data.total_blocked_domains || 0} Domains)`;
    }

    renderServicesGrid();
  } catch (err) {
    console.error("Failed to load blocked services:", err);
  }
}

function filterServicesCategory(cat) {
  currentCategoryFilter = cat;

  // Update category pill styles
  const pills = document.querySelectorAll("#serviceCategoryPills .category-pill");
  pills.forEach(btn => {
    if (btn.dataset.cat === cat) {
      btn.className = "btn btn-sm btn-primary category-pill active";
    } else {
      btn.className = "btn btn-sm btn-secondary category-pill";
    }
  });

  renderServicesGrid();
}

function renderServicesGrid() {
  const container = document.getElementById("servicesGridContainer");
  if (!container) return;

  const filtered = currentCategoryFilter === "ALL"
    ? allBlockedServices
    : allBlockedServices.filter(s => s.category === currentCategoryFilter);

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--text-dim);">
        No services found in category "${currentCategoryFilter}".
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(s => {
    const isBlocked = s.enabled;
    const domainCount = (s.domains || []).length;
    const domainPreview = (s.domains || []).slice(0, 3).join(", ") + (domainCount > 3 ? ` +${domainCount - 3} more` : "");

    return `
      <div class="card" style="display: flex; flex-direction: column; justify-content: space-between; border-left: 3px solid ${isBlocked ? '#ef4444' : 'var(--border-accent)'}; transition: all 0.2s ease;">
        <div>
          <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 8px;">
            <div style="display: flex; align-items: center; gap: 10px;">
              <span style="font-size: 1.6rem; line-height: 1;">${s.icon || "🌐"}</span>
              <div>
                <strong style="font-size: 0.95rem; color: var(--text-main); display: block;">${s.name}</strong>
                <span class="pill" style="font-size: 0.7rem; padding: 1px 6px; background: rgba(255, 255, 255, 0.05); color: var(--text-muted); border: 1px solid var(--border);">
                  ${s.category}
                </span>
              </div>
            </div>

            <label class="switch" title="${isBlocked ? 'Click to Unblock' : 'Click to Block'}">
              <input type="checkbox" ${isBlocked ? "checked" : ""} onchange="toggleService('${s.id}', this.checked)">
              <span class="slider"></span>
            </label>
          </div>

          <p style="font-size: 0.76rem; color: var(--text-dim); margin-top: 6px; margin-bottom: 10px; word-break: break-all; font-family: monospace;" title="${(s.domains || []).join(', ')}">
            ${domainPreview}
          </p>
        </div>

        <div style="display: flex; align-items: center; justify-content: space-between; padding-top: 8px; border-top: 1px solid var(--border-glass); font-size: 0.74rem;">
          <span style="color: ${isBlocked ? '#ef4444' : 'var(--accent-green)'}; font-weight: 500;">
            ${isBlocked ? "🚫 BLOCKED ACROSS NETWORK" : "✅ ALLOWED"}
          </span>
          <span style="color: var(--text-dim);">${domainCount} domains</span>
        </div>
      </div>
    `;
  }).join("");
}

async function toggleService(serviceId, enabled) {
  try {
    const res = await apiRequest("/api/services/toggle", {
      method: "POST",
      body: JSON.stringify({ service_id: serviceId, enabled: enabled })
    });

    if (res && res.success) {
      showToast(`${res.service_name || serviceId} is now ${enabled ? "BLOCKED 🚫" : "ALLOWED ✅"}`);
      // Refresh local state and summary counters
      await loadBlockedServices();
    }
  } catch (err) {
    showToast(`Failed to update service: ${err.message}`, "error");
    await loadBlockedServices(); // Revert toggle UI
  }
}

async function handleBulkServices(enabled) {
  const cat = currentCategoryFilter;

  try {
    const res = await apiRequest("/api/services/bulk", {
      method: "POST",
      body: JSON.stringify({ category: cat, enabled: enabled })
    });

    if (res && res.success) {
      showToast(`${res.updated_count} services ${enabled ? "BLOCKED 🚫" : "UNBLOCKED ✅"}. Engine compiled.`);
      await loadBlockedServices();
    }
  } catch (err) {
    showToast(`Bulk update failed: ${err.message}`, "error");
  }
}

// Bind explicitly to window scope
window.loadBlockedServices = loadBlockedServices;
window.toggleService = toggleService;
window.handleBulkServices = handleBulkServices;
window.filterServicesCategory = filterServicesCategory;
