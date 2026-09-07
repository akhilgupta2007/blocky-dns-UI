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
    let url = `/api/logs?page=${logCurrentPage}&limit=${logLimit}&search=${encodeURIComponent(search)}&client_ip=${encodeURIComponent(clientIp)}&status=${encodeURIComponent(status)}&include_ptr=${includePtr}`;
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

function renderLogRow(r) {
  const iconMap = { tv: "📺", laptop: "💻", phone: "📱", tablet: "📱", iot: "💡", server: "🖥️", printer: "🖨️", device: "🔌" };
  const icon = iconMap[r.client_icon] || "🔌";
  let pillClass = "resolved";
  if (r.response_type === "BLOCKED") pillClass = "blocked";
  else if (r.response_type === "CACHED") pillClass = "cached";

  const localTimeStr = formatLocalIsoTimestamp(r.request_ts);

  // Format resolved answer IP address
  let answerHtml = `<span style="color: var(--text-dim); font-size: 0.8rem;">-</span>`;
  if (r.response_type === "BLOCKED") {
    answerHtml = `<span style="color: var(--accent-red); font-family: monospace; font-size: 0.8rem; font-weight: 600;">0.0.0.0</span>`;
  } else if (r.answer && r.answer.trim()) {
    answerHtml = `<code style="color: var(--accent-cyan); font-size: 0.8rem; word-break: break-all; font-weight: 500;">${r.answer.trim()}</code>`;
  }

  const qType = r.question_type || "A";

  return `
    <tr id="log-row-${r.id || 'live'}" style="transition: background 0.5s ease;">
      <td style="color: var(--text-muted); font-size: 0.82rem; font-family: monospace; white-space: nowrap;" title="Raw timestamp: ${r.request_ts}">${localTimeStr}</td>
      <td>
        <div style="display: flex; align-items: center; gap: 6px;">
          <span>${icon}</span>
          <span style="font-weight: 600;">${r.client_name || r.client_ip}</span>
        </div>
        <div style="font-size: 0.72rem; color: var(--text-dim); font-family: monospace;">${r.client_ip}</div>
      </td>
      <td>
        <div style="display: flex; align-items: center; gap: 6px;">
          <span style="font-family: monospace; font-weight: 600; word-break: break-all; color: var(--text-main);">${r.question}</span>
          <span class="pill" style="font-size: 0.65rem; padding: 1px 5px; background: rgba(255,255,255,0.06); text-transform: uppercase;">${qType}</span>
        </div>
        ${r.reason ? `<div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 2px;">${r.reason}</div>` : ""}
      </td>
      <td>${answerHtml}</td>
      <td><span class="pill ${pillClass}">${r.response_type}</span></td>
      <td style="color: var(--text-muted); font-size: 0.82rem;">${r.duration_ms}ms</td>
      <td>
        <div style="display: flex; gap: 6px; align-items: center;">
          <button class="btn btn-secondary btn-sm" onclick="window.openWhoisModal('${r.question}')" title="Inspect WHOIS & Domain Intelligence" style="padding: 3px 8px; font-size: 0.75rem;">ℹ️ Whois</button>
          <button class="btn btn-secondary btn-sm" onclick="quickAddRule('whitelist', '${r.question}')" title="Whitelist domain" style="padding: 3px 8px; font-size: 0.75rem;">✓ Allow</button>
          <button class="btn btn-danger btn-sm" onclick="quickAddRule('blacklist', '${r.question}')" title="Blacklist domain" style="padding: 3px 8px; font-size: 0.75rem;">✕ Block</button>
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
      if (status !== "ALL" && log.response_type !== status) return;

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



