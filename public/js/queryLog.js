let logCurrentPage = 1;
const logLimit = 50;
let logTotalPages = 1;

function formatLocalIsoTimestamp(ts) {
  if (!ts) return "-";
  try {
    let s = String(ts).trim();
    if (s.includes(" ") && !s.includes("T")) {
      s = s.replace(" ", "T");
    }
    // Truncate sub-millisecond nanoseconds (e.g. .31585109 -> .315)
    s = s.replace(/(\.\d{3})\d+/, "$1");
    // Append Z if no timezone indicator exists and looks like UTC
    if (!s.endsWith("Z") && !s.includes("+") && !s.match(/-\d{2}:\d{2}$/)) {
      s += "Z";
    }
    const d = new Date(s);
    if (isNaN(d.getTime())) return ts;

    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const hours = String(d.getHours()).padStart(2, "0");
    const minutes = String(d.getMinutes()).padStart(2, "0");
    const seconds = String(d.getSeconds()).padStart(2, "0");

    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  } catch (err) {
    return ts;
  }
}

function handleDateRangeChange() {
  const select = document.getElementById("logDateRangeSelect");
  const customBox = document.getElementById("customDateRangeBox");
  if (customBox) {
    customBox.style.display = (select && select.value === "custom") ? "flex" : "none";
  }
  handleLogFilterChange();
}

async function updateRetentionBadge() {
  try {
    const settings = await apiRequest("/api/control/settings");
    if (settings && settings.log_retention_days) {
      const el = document.getElementById("logRetentionDaysLabel");
      if (el) {
        const d = parseInt(settings.log_retention_days, 10);
        el.textContent = d === 1 ? "24 Hours (1 Day)" : `${d} Days`;
      }
    }
  } catch (err) {}
}

async function refreshQueryLogs() {
  await loadRoutingRulesCache(true);
  const search = document.getElementById("logSearchInput")?.value.trim() || "";
  const clientIp = document.getElementById("logDeviceSelect")?.value || "";
  const status = document.getElementById("logStatusSelect")?.value || "ALL";

  // Compute date range timestamps
  const dateRange = document.getElementById("logDateRangeSelect")?.value || "all";
  let fromTs = "";
  let toTs = "";

  if (dateRange === "1h") {
    fromTs = new Date(Date.now() - 3600 * 1000).toISOString();
  } else if (dateRange === "24h") {
    fromTs = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
  } else if (dateRange === "7d") {
    fromTs = new Date(Date.now() - 7 * 24 * 3600 * 1000).toISOString();
  } else if (dateRange === "30d") {
    fromTs = new Date(Date.now() - 30 * 24 * 3600 * 1000).toISOString();
  } else if (dateRange === "custom") {
    const fromVal = document.getElementById("logDateFrom")?.value;
    const toVal = document.getElementById("logDateTo")?.value;
    if (fromVal) fromTs = new Date(fromVal).toISOString();
    if (toVal) toTs = new Date(toVal).toISOString();
  }

  try {
    const includePtr = document.getElementById("logIncludePtrCheck")?.checked || false;
    let url = `/api/logs?page=${logCurrentPage}&limit=${logLimit}&search=${encodeURIComponent(search)}&client_ip=${encodeURIComponent(clientIp)}&status=${encodeURIComponent(status)}&response_type=${encodeURIComponent(status)}&include_ptr=${includePtr}`;
    if (fromTs) url += `&from_ts=${encodeURIComponent(fromTs)}`;
    if (toTs) url += `&to_ts=${encodeURIComponent(toTs)}`;

    const data = await apiRequest(url);
    if (!data) return;

    logTotalPages = data.total_pages || 1;
    document.getElementById("logPaginationInfo").textContent = `Showing page ${data.page} of ${logTotalPages} (${data.total_records.toLocaleString()} total queries)`;

    document.getElementById("btnPrevPage").disabled = logCurrentPage <= 1;
    document.getElementById("btnNextPage").disabled = logCurrentPage >= logTotalPages;

    const tbody = document.getElementById("queryLogsTableBody");
    if (!data.records || data.records.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 24px;">No matching query logs found.</td></tr>`;
      return;
    }

    if (data.records.length > 0) {
      const highestId = Math.max(...data.records.map(r => r.id || 0));
      if (highestId > maxStreamLogId) maxStreamLogId = highestId;
    }

    tbody.innerHTML = data.records.map(renderLogRow).join("");

    // Populate device filter dropdown if empty
    populateDeviceFilter();
    updateRetentionBadge();
  } catch (err) {
    console.error("Error loading query logs:", err);
  }
}


async function populateDeviceFilter() {
  const select = document.getElementById("logDeviceSelect");
  if (select.children.length > 1) return;
  try {
    const devices = await apiRequest("/api/devices");
    if (devices) {
      devices.forEach(d => {
        const opt = document.createElement("option");
        opt.value = d.client_ip;
        opt.textContent = `${d.friendly_name || d.hostname || d.client_ip} (${d.client_ip})`;
        select.appendChild(opt);
      });
    }
  } catch (err) {}
}

function handleLogFilterChange() {
  logCurrentPage = 1;
  refreshQueryLogs();
}

function changeLogPage(delta) {
  const newPage = logCurrentPage + delta;
  if (newPage >= 1 && newPage <= logTotalPages) {
    logCurrentPage = newPage;
    refreshQueryLogs();
  }
}

async function quickAddRule(type, domain) {
  try {
    const res = await apiRequest("/api/rules/add", {
      method: "POST",
      body: JSON.stringify({
        rule_type: type,
        domain: domain,
        comment: `Added from Query Log`
      })
    });
    if (res && res.success) {
      showToast(`Added ${domain} to ${type}`);
      refreshQueryLogs();
    }
  } catch (err) {
    console.error(err);
  }
}

async function handlePruneLogs() {
  try {
    const res = await apiRequest("/api/logs/prune", { method: "POST" });
    if (res && res.success) {
      showToast(`Pruned ${res.pruned_count} old records`);
      refreshQueryLogs();
    }
  } catch (err) {
    showToast(`Failed to prune logs: ${err.message}`, "error");
    console.error(err);
  }
}

// Global Filter Navigation Helpers
function viewAllQueries() {
  switchView('queryLog');
  const search = document.getElementById("logSearchInput");
  if (search) search.value = "";
  const dev = document.getElementById("logDeviceSelect");
  if (dev) dev.value = "";
  const stat = document.getElementById("logStatusSelect");
  if (stat) stat.value = "ALL";
  const dateRange = document.getElementById("logDateRangeSelect");
  if (dateRange) dateRange.value = "all";
  const customBox = document.getElementById("customDateRangeBox");
  if (customBox) customBox.style.display = "none";
  const fromInput = document.getElementById("logDateFrom");
  if (fromInput) fromInput.value = "";
  const toInput = document.getElementById("logDateTo");
  if (toInput) toInput.value = "";
  logCurrentPage = 1;
  refreshQueryLogs();
}


function filterLogsByStatus(status) {
  switchView('queryLog');
  const stat = document.getElementById("logStatusSelect");
  if (stat) stat.value = status;
  const search = document.getElementById("logSearchInput");
  if (search) search.value = "";
  const dev = document.getElementById("logDeviceSelect");
  if (dev) dev.value = "";
  logCurrentPage = 1;
  refreshQueryLogs();
}

function filterLogsByClient(clientIp) {
  switchView('queryLog');
  const dev = document.getElementById("logDeviceSelect");
  if (dev) {
    let opt = Array.from(dev.options).find(o => o.value === clientIp);
    if (!opt) {
      opt = document.createElement("option");
      opt.value = clientIp;
      opt.textContent = clientIp;
      dev.appendChild(opt);
    }
    dev.value = clientIp;
  }
  const search = document.getElementById("logSearchInput");
  if (search) search.value = "";
  const stat = document.getElementById("logStatusSelect");
  if (stat) stat.value = "ALL";
  logCurrentPage = 1;
  refreshQueryLogs();
}

function filterLogsByDomain(domain) {
  switchView('queryLog');
  const search = document.getElementById("logSearchInput");
  if (search) search.value = domain;
  const dev = document.getElementById("logDeviceSelect");
  if (dev) dev.value = "";
  const stat = document.getElementById("logStatusSelect");
  if (stat) stat.value = "ALL";
  logCurrentPage = 1;
  refreshQueryLogs();
}

// Live Streaming SSE Logic
let liveStreamSource = null;
let maxStreamLogId = 0;

function toggleIpExpansion(uid, btn) {
  const el = document.getElementById(uid);
  if (!el) return;
  const isHidden = el.style.display === "none" || !el.style.display;
  if (isHidden) {
    el.style.display = "flex";
    btn.innerHTML = `▲ collapse`;
    btn.classList.add("expanded");
  } else {
    el.style.display = "none";
    const count = el.dataset.count || "";
    btn.innerHTML = `+${count} more`;
    btn.classList.remove("expanded");
  }
}
window.toggleIpExpansion = toggleIpExpansion;

function formatResolvedAnswer(answerStr, responseType, rowId) {
  if (responseType === "BLOCKED") {
    return `<span style="color: var(--accent-red); font-family: monospace; font-size: 0.78rem; font-weight: 600;">0.0.0.0</span>`;
  }

  if (!answerStr || !answerStr.trim()) {
    return `<span style="color: var(--text-dim); font-size: 0.8rem;">-</span>`;
  }

  // Split multiple IPs / answers by comma, semicolon, space, or newline
  const parts = answerStr
    .split(/[\s,;]+/)
    .map(p => p.trim())
    .filter(Boolean);

  if (parts.length === 0) {
    return `<span style="color: var(--text-dim); font-size: 0.8rem;">-</span>`;
  }

  const firstIp = parts[0];

  if (parts.length === 1) {
    return `<code class="ip-badge-single" style="color: var(--accent-cyan); font-family: monospace; font-size: 0.78rem; font-weight: 500; word-break: break-all;">${firstIp}</code>`;
  }

  const remainingCount = parts.length - 1;
  const uid = `ips-${rowId || Math.random().toString(36).substring(2, 9)}`;

  return `
    <div class="resolved-ip-cell" style="display: inline-flex; flex-direction: column; gap: 4px; align-items: flex-start; max-width: 100%;">
      <div style="display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap;">
        <code style="color: var(--accent-cyan); font-family: monospace; font-size: 0.78rem; font-weight: 500; word-break: break-all;">${firstIp}</code>
        <button type="button" class="btn-ip-expand" onclick="toggleIpExpansion('${uid}', this)" title="Click to view all ${parts.length} resolved records" style="background: rgba(6, 182, 212, 0.12); color: var(--accent-cyan); border: 1px solid rgba(6, 182, 212, 0.35); border-radius: 4px; padding: 1px 6px; font-size: 0.7rem; font-weight: 600; cursor: pointer; transition: all 0.15s ease; user-select: none; white-space: nowrap;">
          +${remainingCount} more
        </button>
      </div>
      <div id="${uid}" data-count="${remainingCount}" style="display: none; flex-direction: column; gap: 4px; background: rgba(13, 19, 33, 0.98); border: 1px solid var(--border-cyan); border-radius: 6px; padding: 6px 10px; margin-top: 3px; max-height: 140px; max-width: 260px; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.7); z-index: 20;">
        ${parts.map((ip, idx) => `
          <div style="display: flex; align-items: center; gap: 6px; font-family: monospace; font-size: 0.74rem; color: ${idx === 0 ? 'var(--accent-cyan)' : 'var(--text-muted)'};">
            <span style="color: var(--text-dim); font-size: 0.65rem; min-width: 16px;">#${idx + 1}</span>
            <span style="word-break: break-all;">${ip}</span>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

let cachedRoutingRules = [];

async function loadRoutingRulesCache(force = false) {
  if (!force && cachedRoutingRules.length > 0) return cachedRoutingRules;
  try {
    const data = await apiRequest("/api/routing");
    if (Array.isArray(data)) {
      cachedRoutingRules = data
        .filter(r => r.enabled !== 0 && r.enabled !== "0" && r.enabled !== false && r.enabled !== "false")
        .map(r => {
          let pat = (r.domain_pattern || "").trim().toLowerCase();
          pat = pat.replace(/^\*\./, "").replace(/^\./, "").replace(/\.$/, "");
          return {
            pattern: pat,
            resolver: r.resolver || "",
            tag: r.tag || ""
          };
        })
        .filter(r => r.pattern && r.resolver);
    }
  } catch (e) {
    console.warn("Failed to load routing rules cache:", e);
  }
  return cachedRoutingRules;
}
window.loadRoutingRulesCache = loadRoutingRulesCache;

// Pre-load routing rules immediately in background
try { loadRoutingRulesCache(); } catch (e) {}

function formatQueryReason(reason, responseType, question) {
  if (!reason && !responseType) return "";
  const type = (responseType || "").toUpperCase().trim();
  const raw = (reason || "").trim();

  // 1. BLOCKED & REBIND
  if (type === "BLOCKED" || type === "REBIND") {
    if (type === "REBIND") return "Blocked by: DNS Rebinding Protection";
    if (!raw || raw === "BLOCKED") return "Blocked by deny list";
    
    // Check if raw is like "BLOCKED (list_name)" or "BLOCKED (regex)"
    const match = raw.match(/^BLOCKED\s*\((.+)\)$/i);
    if (match) {
      return `Blocked by: ${match[1].trim()}`;
    }
    if (raw.toLowerCase().startsWith("blocked by:")) {
      return raw;
    }
    return `Blocked by: ${raw}`;
  }

  // 2. RESOLVED
  if (type === "RESOLVED") {
    if (!raw) return "";
    // Check if raw is like "RESOLVED (https://dns.quad9.net/dns-query)"
    const match = raw.match(/^RESOLVED\s*\((.+)\)$/i);
    if (match) {
      return `Upstream: ${match[1].trim()}`;
    }
    if (raw === "RESOLVED") return "";
    return `Upstream: ${raw}`;
  }

  // 3. CONDITIONAL (Domain Routing)
  if (type === "CONDITIONAL") {
    // A. Check if raw already has enriched resolver like "CONDITIONAL (tcp-tls:... [Tag])"
    const match = raw.match(/^CONDITIONAL\s*\((.+)\)$/i);
    if (match) {
      return `Upstream: ${match[1].trim()}`;
    }
    // B. Fallback: match domain question against active routing rules
    if (question && cachedRoutingRules.length > 0) {
      const q = question.toLowerCase().trim().replace(/\.$/, "");
      const matched = cachedRoutingRules.find(r => q === r.pattern || q.endsWith("." + r.pattern));
      if (matched) {
        const tagPart = matched.tag ? ` [${matched.tag}]` : "";
        return `Upstream: ${matched.resolver}${tagPart}`;
      }
    }
    if (raw && raw !== "CONDITIONAL") {
      return `Upstream: ${raw}`;
    }
    return "Domain Routing (Custom Upstream)";
  }

  // 4. CACHED
  if (type === "CACHED") {
    // If reason is just CACHED or empty, don't show any redundant text
    if (!raw || raw.toUpperCase() === "CACHED" || raw.toLowerCase() === "cache hit") {
      return "";
    }
    return raw;
  }

  // 5. CUSTOMDNS
  if (type === "CUSTOMDNS") {
    return "Local DNS record";
  }

  // 6. HOSTSFILE
  if (type === "HOSTSFILE") {
    return "Hosts file entry";
  }

  // Fallback for any other types
  if (!raw || raw.toUpperCase() === type) return "";
  return raw;
}

function renderLogRow(r) {
  const iconMap = { tv: "📺", laptop: "💻", phone: "📱", tablet: "📱", iot: "💡", server: "🖥️", printer: "🖨️", device: "🔌" };
  const icon = iconMap[r.client_icon] || "🔌";
  let pillClass = "resolved";
  if (r.response_type === "BLOCKED") pillClass = "blocked";
  else if (r.response_type === "CACHED") pillClass = "cached";

  const localTimeStr = formatLocalIsoTimestamp(r.request_ts);
  const answerHtml = formatResolvedAnswer(r.answer, r.response_type, r.id);
  const qType = r.question_type || "A";
  const reasonText = formatQueryReason(r.reason, r.response_type, r.question);
  const isBlockedType = (r.response_type === "BLOCKED" || r.response_type === "REBIND");
  const reasonColor = isBlockedType ? "var(--accent-red)" : "var(--text-dim)";

  return `
    <tr id="log-row-${r.id || 'live'}" class="query-log-row" style="transition: background 0.3s ease;">
      <td class="col-time desktop-only" style="color: var(--text-muted); font-size: 0.82rem; font-family: monospace; white-space: nowrap;" title="Raw timestamp: ${r.request_ts}">${localTimeStr}</td>
      <td class="col-client">
        <div class="client-cell-content">
          <div style="display: flex; align-items: center; gap: 6px;">
            <span>${icon}</span>
            <span style="font-weight: 600;">${r.client_name || r.client_ip}</span>
            <span class="client-ip-sub" style="font-size: 0.72rem; color: var(--text-dim); font-family: monospace;">(${r.client_ip})</span>
          </div>
          <div class="mobile-card-meta">
            <span>${localTimeStr}</span>
            <span style="color: var(--accent-cyan); margin-left: 6px;">⚡ ${r.duration_ms}ms</span>
          </div>
        </div>
      </td>
      <td class="col-domain">
        <div class="domain-cell-content">
          <div class="domain-header-line">
            <div style="display: flex; align-items: center; gap: 6px; min-width: 0;">
              <span class="domain-text">${r.question}</span>
              <span class="pill pill-qtype" style="font-size: 0.65rem; padding: 1px 5px; background: rgba(255,255,255,0.06); text-transform: uppercase;">${qType}</span>
            </div>
            <span class="pill ${pillClass} mobile-status-tag">${r.response_type}</span>
          </div>
          ${reasonText ? `<div class="block-reason-text" style="font-size: 0.72rem; color: ${reasonColor}; margin-top: 2px;">${reasonText}</div>` : ""}
        </div>
      </td>
      <td class="col-answer">
        <div class="answer-cell-content">
          <span class="mobile-field-tag">Resolved IP:</span>
          ${answerHtml}
        </div>
      </td>
      <td class="col-status desktop-only"><span class="pill ${pillClass}">${r.response_type}</span></td>
      <td class="col-latency desktop-only" style="color: var(--text-muted); font-size: 0.82rem;">⚡ ${r.duration_ms}ms</td>
      <td class="col-actions">
        <div class="actions-button-group">
          <button class="btn btn-secondary btn-sm" onclick="window.openWhoisModal('${r.question}')" title="Inspect WHOIS & Domain Intelligence">ℹ️ Whois</button>
          <button class="btn btn-secondary btn-sm btn-allow" onclick="quickAddRule('whitelist', '${r.question}')" title="Whitelist domain">✓ Allow</button>
          <button class="btn btn-danger btn-sm btn-block" onclick="quickAddRule('blacklist', '${r.question}')" title="Blacklist domain">✕ Block</button>
        </div>
      </td>
    </tr>
  `;
}

function toggleLiveStream() {
  const btn = document.getElementById("btnToggleLiveStream");
  const dot = document.getElementById("liveStreamPulseDot");
  const txt = document.getElementById("liveStreamBtnText");

  if (liveStreamSource) {
    liveStreamSource.close();
    liveStreamSource = null;
    if (dot) dot.style.display = "none";
    if (txt) txt.textContent = "🔴 Live Stream";
    if (btn) {
      btn.classList.remove("btn-cyan");
      btn.classList.add("btn-secondary");
    }
    showToast("Live query streaming paused");
    return;
  }

  // If user is on an older page, jump to page 1 for streaming
  if (logCurrentPage !== 1) {
    logCurrentPage = 1;
    refreshQueryLogs();
  }

  if (dot) dot.style.display = "inline-block";
  if (txt) txt.textContent = "⏸️ Pause Stream";
  if (btn) {
    btn.classList.remove("btn-secondary");
    btn.classList.add("btn-cyan");
  }

  const includePtr = document.getElementById("logIncludePtrCheck")?.checked || false;
  const streamUrl = `/api/logs/stream?last_id=${maxStreamLogId}&include_ptr=${includePtr}`;
  liveStreamSource = new EventSource(streamUrl);

  liveStreamSource.onmessage = function(event) {
    try {
      const log = JSON.parse(event.data);
      if (!log || !log.id) return;
      if (log.id > maxStreamLogId) maxStreamLogId = log.id;

      // Filter check against active UI filters
      const search = document.getElementById("logSearchInput")?.value.trim().toLowerCase() || "";
      const clientIp = document.getElementById("logDeviceSelect")?.value || "";
      const status = document.getElementById("logStatusSelect")?.value || "ALL";

      if (!includePtr) {
        const q = (log.question || "").toLowerCase();
        if (q.includes(".in-addr.arpa") || q.includes(".ip6.arpa") || log.response_type === "SPECIAL" || (log.reason || "").toLowerCase().includes("special")) {
          return;
        }
      }

      if (search && !log.question.toLowerCase().includes(search) && !log.client_ip.includes(search) && !(log.client_name || "").toLowerCase().includes(search)) {
        return;
      }
      if (clientIp && log.client_ip !== clientIp) return;
      if (status !== "ALL") {
        if (status === "BLOCKED") {
          if (log.response_type !== "BLOCKED" && log.response_type !== "REBIND") return;
        } else if (log.response_type !== status) {
          return;
        }
      }

      const tbody = document.getElementById("queryLogsTableBody");
      if (!tbody) return;

      const emptyRow = tbody.querySelector("td[colspan='7']");
      if (emptyRow) tbody.innerHTML = "";

      const tempContainer = document.createElement("tbody");
      tempContainer.innerHTML = renderLogRow(log);
      const newRow = tempContainer.firstElementChild;
      newRow.style.backgroundColor = "rgba(56, 189, 248, 0.12)";

      tbody.insertBefore(newRow, tbody.firstChild);

      // Fade highlight after 1.5s
      setTimeout(() => {
        newRow.style.backgroundColor = "";
      }, 1500);

      // Keep max 50 items visible
      while (tbody.children.length > logLimit) {
        tbody.removeChild(tbody.lastChild);
      }
    } catch (e) {
      console.error("Error processing stream message:", e);
    }
  };

  liveStreamSource.onerror = function(err) {
    console.warn("Live stream disconnected, auto-reconnecting...", err);
  };

  showToast("Live stream connected! Incoming queries will appear in real time.");
}

async function openWhoisModal(domain) {
  let cleanDomain = (domain || "").trim().toLowerCase();
  if (cleanDomain.startsWith("*.")) cleanDomain = cleanDomain.substring(2);
  cleanDomain = cleanDomain.replace(/\.$/, "");

  const modal = document.getElementById("whoisModal");
  const modalDomain = document.getElementById("whoisModalDomain");
  const content = document.getElementById("whoisModalContent");
  const whoisLink = document.getElementById("whoisExtLink");
  const vtLink = document.getElementById("vtExtLink");
  const ghosteryLink = document.getElementById("ghosteryExtLink");

  if (!modal || !content) return;

  modalDomain.textContent = cleanDomain;
  if (whoisLink) whoisLink.href = `https://www.whois.com/whois/${cleanDomain}`;
  if (vtLink) vtLink.href = `https://www.virustotal.com/gui/domain/${cleanDomain}`;
  if (ghosteryLink) ghosteryLink.href = `https://www.ghostery.com/whotracksme/search?q=${encodeURIComponent(cleanDomain)}`;

  modal.classList.add("active");

  content.innerHTML = `
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 30px; gap: 12px;">
      <div class="action-status-spinner" style="width: 28px; height: 28px; border-width: 3px;"></div>
      <span style="font-size: 0.85rem; color: var(--text-muted);">Querying WHOIS & RDAP intelligence for <strong>${cleanDomain}</strong>...</span>
    </div>
  `;

  try {
    const data = await apiRequest(`/api/tools/whois?domain=${encodeURIComponent(cleanDomain)}`);
    if (!data) return;

    if (ghosteryLink) ghosteryLink.href = data.whotracksme_url || `https://www.ghostery.com/whotracksme/search?q=${encodeURIComponent(cleanDomain)}`;

    const ipsHtml = (data.resolved_ips && data.resolved_ips.length > 0)
      ? data.resolved_ips.map(ip => `<code style="color: var(--accent-cyan); font-size: 0.8rem; background: rgba(255,255,255,0.04); padding: 2px 6px; border-radius: 4px;">${ip}</code>`).join(" ")
      : `<span style="color: var(--text-dim); font-size: 0.82rem;">None detected</span>`;

    const nsHtml = (data.nameservers && data.nameservers.length > 0)
      ? data.nameservers.map(ns => `<span class="pill" style="font-size: 0.72rem; background: rgba(255,255,255,0.05); font-family: monospace;">${ns}</span>`).join(" ")
      : `<span style="color: var(--text-dim); font-size: 0.82rem;">Not available</span>`;

    const statusHtml = (data.status && data.status.length > 0)
      ? data.status.map(st => `<span class="pill" style="font-size: 0.7rem; background: rgba(16, 185, 129, 0.12); color: var(--accent-green);">${st}</span>`).join(" ")
      : "";

    content.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 14px;">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; background: rgba(255,255,255,0.02); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-glass);">
          <div>
            <div style="font-size: 0.74rem; color: var(--text-dim); text-transform: uppercase; font-weight: 600;">Registrar</div>
            <div style="font-weight: 600; font-size: 0.9rem; color: var(--text-main); margin-top: 2px;">${data.registrar || "Not public or ccTLD"}</div>
          </div>
          <div>
            <div style="font-size: 0.74rem; color: var(--text-dim); text-transform: uppercase; font-weight: 600;">Registered Date</div>
            <div style="font-family: monospace; font-size: 0.85rem; color: var(--text-muted); margin-top: 2px;">${data.creation_date || "Unknown"}</div>
          </div>
          <div>
            <div style="font-size: 0.74rem; color: var(--text-dim); text-transform: uppercase; font-weight: 600;">Expiration Date</div>
            <div style="font-family: monospace; font-size: 0.85rem; color: var(--text-muted); margin-top: 2px;">${data.expiration_date || "Unknown"}</div>
          </div>
          <div>
            <div style="font-size: 0.74rem; color: var(--text-dim); text-transform: uppercase; font-weight: 600;">Quick Rule Action</div>
            <div style="display: flex; gap: 6px; margin-top: 4px;">
              <button class="btn btn-secondary btn-sm" style="padding: 2px 8px; font-size: 0.75rem;" onclick="quickAddRule('whitelist', '${cleanDomain}'); closeWhoisModal();">✓ Allow</button>
              <button class="btn btn-danger btn-sm" style="padding: 2px 8px; font-size: 0.75rem;" onclick="quickAddRule('blacklist', '${cleanDomain}'); closeWhoisModal();">✕ Block</button>
            </div>
          </div>
        </div>

        <!-- Ghostery WhoTracks.Me Tracker Intelligence Card -->
        <div style="background: rgba(99, 102, 241, 0.05); padding: 11px 14px; border-radius: var(--radius-md); border: 1px solid rgba(99, 102, 241, 0.22); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
          <div style="display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 1.25rem;">👻</span>
            <div>
              <div style="font-size: 0.83rem; font-weight: 600; color: #c7d2fe;">Ghostery WhoTracks.Me Tracker Intelligence</div>
              <div style="font-size: 0.74rem; color: var(--text-dim);">
                ${data.apex_domain && data.apex_domain !== cleanDomain ? `Root Domain: <strong>${data.apex_domain}</strong> &bull; ` : ''}Analyze ad pixels & tracking telemetry
              </div>
            </div>
          </div>
          <div style="display: flex; gap: 6px;">
            <a href="${data.whotracksme_url || `https://www.ghostery.com/whotracksme/websites/${cleanDomain}`}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="font-size: 0.75rem; padding: 4px 10px; color: #a5b4fc; border-color: rgba(99, 102, 241, 0.4); text-decoration: none;" title="View Ghostery website tracker profile">
              Website Profile &nearr;
            </a>
            <a href="${data.whotracksme_search_url || `https://www.ghostery.com/whotracksme/search?q=${cleanDomain}`}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="font-size: 0.75rem; padding: 4px 10px; color: #a5b4fc; border-color: rgba(99, 102, 241, 0.4); text-decoration: none;" title="Search Ghostery tracker database">
              Search &nearr;
            </a>
          </div>
        </div>

        <div style="background: rgba(255,255,255,0.02); padding: 12px 14px; border-radius: var(--radius-md); border: 1px solid var(--border-glass);">
          <div style="font-size: 0.74rem; color: var(--text-dim); text-transform: uppercase; font-weight: 600; margin-bottom: 6px;">Live Resolved IP Addresses</div>
          <div style="display: flex; flex-wrap: wrap; gap: 6px;">${ipsHtml}</div>
        </div>

        <div style="background: rgba(255,255,255,0.02); padding: 12px 14px; border-radius: var(--radius-md); border: 1px solid var(--border-glass);">
          <div style="font-size: 0.74rem; color: var(--text-dim); text-transform: uppercase; font-weight: 600; margin-bottom: 6px;">Authoritative Nameservers</div>
          <div style="display: flex; flex-wrap: wrap; gap: 6px;">${nsHtml}</div>
        </div>

        ${statusHtml ? `
        <div>
          <div style="font-size: 0.74rem; color: var(--text-dim); text-transform: uppercase; font-weight: 600; margin-bottom: 6px;">Registry Status Flags</div>
          <div style="display: flex; flex-wrap: wrap; gap: 4px;">${statusHtml}</div>
        </div>` : ""}
      </div>
    `;
  } catch (err) {
    content.innerHTML = `
      <div style="padding: 20px; text-align: center; color: var(--accent-amber);">
        <div style="font-size: 1.5rem; margin-bottom: 8px;">⚠️</div>
        <div style="font-size: 0.9rem; font-weight: 600;">WHOIS Lookup Unavailable</div>
        <div style="font-size: 0.8rem; color: var(--text-dim); margin-top: 4px;">${err.message || "Domain registry did not return public RDAP data"}</div>
        <p style="font-size: 0.78rem; color: var(--text-muted); margin-top: 12px;">You can view the full record directly using the WHOIS.com button below.</p>
      </div>
    `;
  }
}

function closeWhoisModal() {
  const modal = document.getElementById("whoisModal");
  if (modal) modal.classList.remove("active");
}

// Bind explicitly to window scope
window.refreshQueryLogs = refreshQueryLogs;
window.handlePruneLogs = handlePruneLogs;
window.quickAddRule = quickAddRule;
window.filterLogsByDomain = filterLogsByDomain;
window.filterLogsByClient = filterLogsByClient;
window.filterLogsByStatus = filterLogsByStatus;
window.viewAllQueries = viewAllQueries;
window.toggleLiveStream = toggleLiveStream;
window.changeLogPage = changeLogPage;
window.openWhoisModal = openWhoisModal;
window.closeWhoisModal = closeWhoisModal;



