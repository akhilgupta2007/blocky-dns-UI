let activeRuleTab = "whitelist";

async function loadBlocklistsAndRules() {
  try {
    // 1. Load Blocklists
    const lists = await apiRequest("/api/blocklists");
    if (lists) renderBlocklists(lists);

    // 2. Load Custom Rules
    const rules = await apiRequest("/api/rules");
    if (rules) renderRules(rules);
  } catch (err) {
    console.error("Error loading blocklists/rules:", err);
  }
}

function renderBlocklists(lists) {
  const container = document.getElementById("curatedCatalogList");
  if (!container) return;

  container.innerHTML = lists.map(l => {
    return `
      <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: var(--bg-input); border-radius: var(--radius-md); border: 1px solid var(--border-glass);">
        <div style="flex: 1; padding-right: 12px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-weight: 600; font-size: 0.92rem;">${l.name}</span>
            <span style="font-size: 0.72rem; color: var(--text-dim);">${l.category}</span>
          </div>
          <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">
            <span>${(l.rule_count || 0).toLocaleString()} rules</span> &bull; 
            <span style="font-family: monospace; opacity: 0.7;">${l.url.substring(0, 45)}...</span>
          </div>
        </div>

        <div style="display: flex; align-items: center; gap: 12px;">
          <label class="switch">
            <input type="checkbox" ${l.enabled ? "checked" : ""} onchange="window.handleToggleList(${l.id}, this.checked)">
            <span class="slider"></span>
          </label>
          <button class="btn btn-danger btn-sm" onclick="window.handleDeleteList(${l.id})" title="Remove Blocklist">✕</button>
        </div>
      </div>
    `;
  }).join("");
}

async function handleToggleList(id, enabled) {
  try {
    await apiRequest("/api/blocklists/toggle", {
      method: "POST",
      body: JSON.stringify({ id, enabled })
    });
    showToast(enabled ? "Blocklist activated" : "Blocklist deactivated");
  } catch (err) {
    showToast(`Toggle failed: ${err.message}`, "error");
    console.error(err);
  }
}

async function handleAddBlocklist(event) {
  event.preventDefault();
  const name = document.getElementById("newListName").value.trim();
  const url = document.getElementById("newListUrl").value.trim();

  try {
    const res = await apiRequest("/api/blocklists/add", {
      method: "POST",
      body: JSON.stringify({ name, url, category: "Custom" })
    });
    if (res && res.success) {
      showToast(`Added blocklist: ${name}`);
      document.getElementById("newListName").value = "";
      document.getElementById("newListUrl").value = "";
      await loadBlocklistsAndRules();
    }
  } catch (err) {
    showToast(`Failed to add blocklist: ${err.message}`, "error");
    console.error(err);
  }
}

async function handleDeleteList(id) {
  try {
    const res = await apiRequest(`/api/blocklists/${id}`, { method: "DELETE" });
    if (res && res.success) {
      showToast("Blocklist removed");
      await loadBlocklistsAndRules();
    }
  } catch (err) {
    showToast(`Failed to remove blocklist: ${err.message}`, "error");
    console.error(err);
  }
}

let allCachedRules = [];
let ruleSearchFilter = "";

function switchRuleTab(tab) {
  activeRuleTab = tab;
  const wlBtn = document.getElementById("tabWhitelistBtn");
  const blBtn = document.getElementById("tabBlacklistBtn");
  if (wlBtn) wlBtn.className = tab === "whitelist" ? "btn btn-primary btn-sm" : "btn btn-secondary btn-sm";
  if (blBtn) blBtn.className = tab === "blacklist" ? "btn btn-primary btn-sm" : "btn btn-secondary btn-sm";
  renderRules(allCachedRules);
}

function filterRulesList(query) {
  ruleSearchFilter = (query || "").trim().toLowerCase();
  renderRules(allCachedRules);
}

function renderRules(rules) {
  if (rules && Array.isArray(rules)) allCachedRules = rules;
  const tbody = document.getElementById("customRulesTableBody");
  const countBadge = document.getElementById("rulesCountBadge");
  if (!tbody) return;

  const currentTabRules = allCachedRules.filter(r => r.rule_type === activeRuleTab);

  if (countBadge) {
    countBadge.textContent = `${currentTabRules.length} ${activeRuleTab === 'whitelist' ? 'Allowed' : 'Blocked'}`;
  }

  let filtered = currentTabRules;
  if (ruleSearchFilter) {
    filtered = filtered.filter(r =>
      (r.domain && r.domain.toLowerCase().includes(ruleSearchFilter)) ||
      (r.comment && r.comment.toLowerCase().includes(ruleSearchFilter))
    );
  }

  if (filtered.length === 0) {
    const msg = ruleSearchFilter
      ? `No ${activeRuleTab} rules matching "${ruleSearchFilter}".`
      : `No custom ${activeRuleTab} rules added yet.`;
    tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-dim); padding: 24px;">${msg}</td></tr>`;
    return;
  }

  const isWhitelist = activeRuleTab === "whitelist";

  tbody.innerHTML = filtered.map(r => {
    const target = r.id != null ? r.id : r.domain;
    const typeColor = isWhitelist ? "var(--accent-green)" : "var(--accent-red)";
    const typeBadge = isWhitelist
      ? `<span class="pill" style="background: rgba(16, 185, 129, 0.15); color: var(--accent-green); font-size: 0.72rem;">Whitelist</span>`
      : `<span class="pill" style="background: rgba(239, 68, 68, 0.15); color: var(--accent-red); font-size: 0.72rem;">Blacklist</span>`;

    let scopeBadge = `<span style="color: var(--text-dim); font-size: 0.75rem;">Exact</span>`;
    if (r.is_wildcard) {
      scopeBadge = `<span class="pill" style="background: rgba(168, 85, 247, 0.15); color: #c084fc; font-size: 0.7rem;">Wildcard</span>`;
    } else if (r.is_regex) {
      scopeBadge = `<span class="pill" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-size: 0.7rem;">Regex</span>`;
    }

    const note = r.comment
      ? `<span style="font-size: 0.78rem; color: var(--text-muted);">${r.comment}</span>`
      : `<span style="font-size: 0.78rem; color: var(--text-dim);">-</span>`;

    return `
      <tr>
        <td>
          <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <span style="font-size: 0.8rem;">${isWhitelist ? '🟢' : '🔴'}</span>
            <code style="font-family: monospace; font-size: 0.84rem; font-weight: 600; color: ${typeColor}; word-break: break-all;">
              ${r.domain}
            </code>
            ${scopeBadge}
          </div>
        </td>
        <td>${typeBadge}</td>
        <td>${note}</td>
        <td style="text-align: right;">
          <button type="button" class="btn btn-icon" onclick="window.handleDeleteRule('${target}')" style="color: var(--accent-red); padding: 4px 8px; font-size: 0.85rem;" title="Delete rule">
            ✕
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

async function handleAddRule(event) {
  event.preventDefault();
  const domain = document.getElementById("newRuleDomain").value.trim();

  try {
    const res = await apiRequest("/api/rules/add", {
      method: "POST",
      body: JSON.stringify({ rule_type: activeRuleTab, domain })
    });
    if (res && res.success) {
      showToast(`Added ${domain} to ${activeRuleTab}`);
      document.getElementById("newRuleDomain").value = "";
      await loadBlocklistsAndRules();
    }
  } catch (err) {
    showToast(`Failed to add rule: ${err.message}`, "error");
    console.error(err);
  }
}

async function handleDeleteRule(idOrDomain) {
  try {
    const res = await apiRequest(`/api/rules/${encodeURIComponent(idOrDomain)}`, { method: "DELETE" });
    if (res && res.success) {
      showToast("Rule deleted");
      await loadBlocklistsAndRules();
    }
  } catch (err) {
    showToast(`Failed to delete rule: ${err.message}`, "error");
    console.error(err);
  }
}

function openImportRulesModal() {
  const modal = document.getElementById("importRulesModal");
  if (modal) {
    modal.classList.add("active");
    const ta = document.getElementById("importRulesTextarea");
    if (ta) ta.focus();
  }
}

function closeImportRulesModal() {
  const modal = document.getElementById("importRulesModal");
  if (modal) modal.classList.remove("active");
}

async function submitImportRules() {
  const ta = document.getElementById("importRulesTextarea");
  const defaultSelect = document.getElementById("importRulesDefaultType");
  const btn = document.getElementById("btnSubmitImportRules");
  if (!ta) return;

  const text = ta.value.trim();
  if (!text) {
    showToast("Please paste one or more rules to import", "warning");
    return;
  }

  const defaultType = defaultSelect ? defaultSelect.value : "blacklist";
  const origBtnText = btn ? btn.innerHTML : "Import & Apply Rules";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span style="display: inline-block; animation: spinAction 0.75s linear infinite; margin-right: 5px;">🔄</span> Importing...`;
  }

  try {
    const res = await apiRequest("/api/rules/import", {
      method: "POST",
      body: JSON.stringify({ rules_text: text, default_type: defaultType })
    });

    if (res && res.success) {
      showToast(`✅ Imported ${res.added_whitelist} Whitelist and ${res.added_blacklist} Blacklist rules!`);
      ta.value = "";
      closeImportRulesModal();
      await loadBlocklistsAndRules();
    }
  } catch (err) {
    showToast(`Import failed: ${err.message}`, "error");
    console.error("submitImportRules error:", err);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origBtnText;
    }
  }
}

// Bind explicitly to window scope
window.loadBlocklistsAndRules = loadBlocklistsAndRules;
window.renderBlocklists = renderBlocklists;
window.handleToggleList = handleToggleList;
window.handleAddBlocklist = handleAddBlocklist;
window.handleDeleteList = handleDeleteList;
window.switchRuleTab = switchRuleTab;
window.renderRules = renderRules;
window.handleAddRule = handleAddRule;
window.handleDeleteRule = handleDeleteRule;
window.openImportRulesModal = openImportRulesModal;
window.closeImportRulesModal = closeImportRulesModal;
window.submitImportRules = submitImportRules;
window.filterRulesList = filterRulesList;
