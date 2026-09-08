async function loadToolsInfo() {
  try {
    // 1. Rebinding status
    const rebinding = await apiRequest("/api/tools/rebinding-status");
    if (rebinding) {
      document.getElementById("toggleRebindingShield").checked = rebinding.shield_active;
    }

    // 2. TLS Info
    const tls = await apiRequest("/api/tools/tls-info");
    const tlsBox = document.getElementById("tlsInfoBox");
    if (tls && tls.active) {
      tlsBox.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 4px;">
          <div><strong>Status:</strong> <span style="color: var(--accent-green);">Active (Encrypted TLS 1.3)</span></div>
          <div><strong>Type:</strong> ${tls.is_self_signed ? "Auto-Generated High-Entropy Self-Signed Cert" : "Custom CA / Let's Encrypt"}</div>
          <div><strong>Subject:</strong> <code>${tls.subject}</code></div>
          <div><strong>Valid Until:</strong> ${tls.valid_to ? tls.valid_to.split("T")[0] : "Active"}</div>
          <div><strong>Protected SANs:</strong> <code>${(tls.sans || []).join(", ")}</code></div>
        </div>
      `;
    } else {
      tlsBox.innerHTML = `<span style="color: var(--accent-amber);">Plain HTTP active.</span>`;
    }

    // 3. Benchmark schedule info
    const sched = await apiRequest("/api/tools/benchmark-schedule");
    if (sched) {
      const select = document.getElementById("selectAutoBenchmark");
      if (select) select.value = String(sched.interval_hours);
      const timeSpan = document.getElementById("lastBenchmarkTime");
      if (timeSpan && sched.last_benchmark_timestamp) {
        timeSpan.textContent = `Last run: ${sched.last_benchmark_timestamp}`;
      }
    }

    // 4. Load configured upstreams and benchmark results immediately
    const benchData = await apiRequest("/api/tools/benchmark");
    if (benchData && benchData.results) {
      renderBenchmarkCards(benchData.results);
      if (benchData.last_benchmark_timestamp) {
        const timeSpan = document.getElementById("lastBenchmarkTime");
        if (timeSpan) timeSpan.textContent = `Last run: ${benchData.last_benchmark_timestamp}`;
      }
    }
  } catch (err) {
    console.error("Error loading tools info:", err);
  }
}

function renderBenchmarkCards(results) {
  const container = document.getElementById("benchmarkResultsContainer");
  if (!container) return;

  if (!results || results.length === 0) {
    container.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--text-dim);">No configured DNS upstream resolvers found in database.</div>`;
    return;
  }

  const validLats = results.map(r => r.latency_ms).filter(l => l != null && l > 0);
  const maxLat = validLats.length > 0 ? Math.max(...validLats, 30) : 100;

  container.innerHTML = results.map(r => {
    const lat = r.latency_ms;
    const isOnline = lat !== null && lat > 0;
    const pct = isOnline ? Math.min(Math.round((lat / maxLat) * 100), 100) : (r.status === "Pending Test" ? 0 : 100);
    const isBest = r.is_best;

    let statusColor = "var(--text-dim)";
    let statusText = r.status || "Pending Test";
    if (isOnline) {
      statusColor = "var(--accent-green)";
      statusText = `${lat} ms`;
    } else if (r.status && r.status !== "Pending Test") {
      statusColor = "var(--accent-red)";
    }

    return `
      <div style="padding: 12px 14px; background: var(--bg-input); border-radius: var(--radius-md); border: 1px solid ${isBest ? 'var(--border-accent)' : 'var(--border-glass)'};">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
          <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <span style="font-weight: 600; font-size: 0.9rem; color: var(--text-main);">${r.name}</span>
            ${r.is_custom ? `<span class="pill" style="background: rgba(168, 85, 247, 0.2); color: #c084fc; font-size: 0.72rem; border: 1px solid rgba(168, 85, 247, 0.4);">Custom</span>` : ""}
            ${r.enabled ? `<span class="pill" style="background: rgba(16, 185, 129, 0.15); color: var(--accent-green); font-size: 0.72rem;">Enabled</span>` : `<span class="pill" style="background: rgba(100, 116, 139, 0.2); color: var(--text-dim); font-size: 0.72rem;">Disabled</span>`}
            <span class="pill" style="background: rgba(255, 255, 255, 0.06); color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase;">${r.protocol}</span>
            ${isBest ? `<span class="pill" style="background: rgba(16, 185, 129, 0.2); color: var(--accent-green); font-weight: 600;">★ Fastest (${lat}ms)</span>` : ""}
          </div>
          <span style="font-family: monospace; font-size: 0.85rem; font-weight: 600; color: ${statusColor};">
            ${statusText}
          </span>
        </div>
        <div style="font-size: 0.75rem; color: var(--text-dim); font-family: monospace; margin-bottom: 8px;">
          ${r.endpoint}
        </div>
        <div style="height: 6px; background: rgba(255,255,255,0.05); border-radius: var(--radius-full); overflow: hidden;">
          <div style="height: 100%; width: ${pct}%; background: ${isBest ? 'linear-gradient(90deg, var(--accent-green), #059669)' : (isOnline ? 'linear-gradient(90deg, var(--accent-cyan), #0284c7)' : 'transparent')}; border-radius: var(--radius-full);"></div>
        </div>
      </div>
    `;
  }).join("");
}

async function handleUpdateAutoBenchmark(hours) {
  try {
    const res = await apiRequest("/api/tools/benchmark-schedule", {
      method: "POST",
      body: JSON.stringify({ interval_hours: parseInt(hours, 10) })
    });
    if (res && res.success) {
      const labels = {
        "24": "Daily (Every 24h - Recommended)",
        "12": "Every 12 Hours",
        "6": "Every 6 Hours",
        "0": "Disabled (Manual Only)"
      };
      showToast(`⏱️ Auto-benchmark set to: ${labels[hours] || hours + 'h'}`);
    }
  } catch (err) {
    console.error(err);
  }
}

async function runBenchmark() {
  const container = document.getElementById("benchmarkResultsContainer");
  const btn = document.getElementById("btnRunBenchmark");
  if (btn && window.setButtonLoading) {
    window.setButtonLoading(btn, true, "Testing...");
  } else if (btn) {
    btn.disabled = true;
  }
  if (container) {
    container.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--accent-cyan); display: flex; align-items: center; justify-content: center; gap: 8px;"><div class="action-status-spinner" style="width: 18px; height: 18px;"></div> Testing RTT latency across all candidate resolvers...</div>`;
  }

  try {
    const results = await apiRequest("/api/tools/benchmark", { method: "POST" });
    const list = Array.isArray(results) ? results : (results.results || []);
    renderBenchmarkCards(list);
    showToast("Benchmark completed!");
    const timeSpan = document.getElementById("lastBenchmarkTime");
    if (timeSpan) {
      const now = new Date();
      timeSpan.textContent = `Last run: Just now (${now.toLocaleTimeString()})`;
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

async function handleDiagnostic(event) {
  event.preventDefault();
  const domain = document.getElementById("diagnosticDomain").value.trim();
  const box = document.getElementById("diagnosticResultBox");
  const btn = event.target ? event.target.querySelector("button[type='submit']") : null;
  if (btn && window.setButtonLoading) {
    window.setButtonLoading(btn, true, "Testing...");
  }
  box.style.display = "block";
  box.innerHTML = `<div style="text-align: center; color: var(--accent-cyan); display: flex; align-items: center; justify-content: center; gap: 8px;"><div class="action-status-spinner" style="width: 16px; height: 16px;"></div> Resolving and checking rule matches for ${domain}...</div>`;

  try {
    const res = await apiRequest("/api/tools/diagnostic", {
      method: "POST",
      body: JSON.stringify({ domain: domain })
    });

    if (res) {
      const isBlocked = res.status === "BLOCKED";
      box.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 8px; font-size: 0.88rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-glass); padding-bottom: 8px;">
            <span style="font-weight: 600; font-size: 1rem; color: var(--text-main);">${res.domain}</span>
            <span class="pill ${isBlocked ? 'blocked' : 'resolved'}">${res.status}</span>
          </div>
          <div><strong>Resolved IP:</strong> <code style="color: var(--accent-cyan);">${res.resolved_ip}</code></div>
          <div><strong>Rule Match:</strong> <span style="color: ${isBlocked ? 'var(--accent-red)' : 'var(--accent-green)'}; font-weight: 500;">${res.rule_match}</span></div>
          <div><strong>Response Latency:</strong> <span style="color: var(--text-muted);">${res.latency_ms} ms</span></div>
        </div>
      `;
    }
  } catch (err) {
    console.error(err);
  } finally {
    if (btn && window.setButtonLoading) {
      window.setButtonLoading(btn, false);
    }
  }
}

async function handleToggleRebinding(input) {
  try {
    await apiRequest("/api/tools/rebinding-toggle", {
      method: "POST",
      body: JSON.stringify({ enabled: input.checked })
    });
    showToast(input.checked ? "DNS Rebinding Protection Shield enabled" : "Rebinding Shield disabled");
  } catch (err) {
    console.error(err);
  }
}

async function handleDnssecInspect(event) {
  event.preventDefault();
  const domain = document.getElementById("dnssecInspectDomain")?.value.trim();
  if (!domain) return;

  const btn = document.getElementById("btnDnssecInspect");
  const resultBox = document.getElementById("dnssecInspectResultBox");
  if (btn && window.setButtonLoading) {
    window.setButtonLoading(btn, true, "Inspecting...");
  } else if (btn) {
    btn.disabled = true;
  }
  if (resultBox) {
    resultBox.style.display = "block";
    resultBox.innerHTML = `<div style="text-align: center; color: var(--accent-cyan); padding: 12px; display: flex; align-items: center; justify-content: center; gap: 8px;"><div class="action-status-spinner" style="width: 16px; height: 16px;"></div> Querying DNSKEY, DS, and RRSIG records for ${domain}...</div>`;
  }

  try {
    const res = await apiRequest("/api/tools/dnssec-inspect", {
      method: "POST",
      body: JSON.stringify({ domain })
    });

    if (res && resultBox) {
      const isSecure = res.status === "SECURE";
      const isPartial = res.status === "PARTIAL";
      const badgeColor = isSecure ? "var(--accent-green)" : (isPartial ? "var(--accent-amber)" : "var(--text-muted)");
      const badgeBg = isSecure ? "rgba(16, 185, 129, 0.15)" : (isPartial ? "rgba(245, 158, 11, 0.15)" : "rgba(255, 255, 255, 0.08)");

      resultBox.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 12px; font-size: 0.88rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-glass); padding-bottom: 8px;">
            <div>
              <strong style="font-size: 1.05rem; color: var(--text-main);">${res.domain}</strong>
              <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 2px;">${res.summary}</div>
            </div>
            <span class="pill" style="background: ${badgeBg}; color: ${badgeColor}; font-weight: 700; font-size: 0.82rem; border: 1px solid ${badgeColor};">
              ${isSecure ? "🔒 " : ""}${res.status}
            </span>
          </div>

          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px;">
            <div style="padding: 10px; background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: 6px;">
              <span style="font-size: 0.74rem; color: var(--text-dim); display: block;">DNSKEY (Public Zone Key)</span>
              <strong style="color: ${res.has_dnskey ? 'var(--accent-green)' : 'var(--text-muted)'};">
                ${res.has_dnskey ? `✅ Present (${res.key_tags.length} keys)` : "❌ None"}
              </strong>
            </div>
            <div style="padding: 10px; background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: 6px;">
              <span style="font-size: 0.74rem; color: var(--text-dim); display: block;">DS (Parent TLD Delegation)</span>
              <strong style="color: ${res.has_ds ? 'var(--accent-green)' : 'var(--text-muted)'};">
                ${res.has_ds ? "✅ Validated at Parent" : "❌ None"}
              </strong>
            </div>
            <div style="padding: 10px; background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: 6px;">
              <span style="font-size: 0.74rem; color: var(--text-dim); display: block;">RRSIG (Crypto Signature)</span>
              <strong style="color: ${res.has_rrsig ? 'var(--accent-green)' : 'var(--text-muted)'};">
                ${res.has_rrsig ? `✅ Signed (${res.signatures.length} sigs)` : "❌ None"}
              </strong>
            </div>
          </div>

          ${res.details && res.details.length > 0 ? `
            <div style="margin-top: 4px;">
              <span style="font-size: 0.76rem; color: var(--text-dim); display: block; margin-bottom: 4px;">Diagnostic Chain Log:</span>
              <div style="background: rgba(0, 0, 0, 0.3); padding: 8px 12px; border-radius: 6px; font-family: monospace; font-size: 0.76rem; color: var(--text-muted); line-height: 1.6;">
                ${res.details.map(d => `<div>• ${d}</div>`).join("")}
              </div>
            </div>
          ` : ""}
        </div>
      `;
    }
  } catch (err) {
    if (resultBox) {
      resultBox.innerHTML = `<div style="color: var(--accent-red); padding: 10px;">Inspection failed: ${err.message || err}</div>`;
    }
  } finally {
    if (btn && window.setButtonLoading) {
      window.setButtonLoading(btn, false);
    } else if (btn) {
      btn.disabled = false;
    }
  }
}

// Bind explicitly to window scope
window.loadToolsInfo = loadToolsInfo;
window.handleUpdateAutoBenchmark = handleUpdateAutoBenchmark;
window.runBenchmark = runBenchmark;
window.handleDiagnostic = handleDiagnostic;
window.handleDnssecInspect = handleDnssecInspect;
window.runDiagnostic = handleDiagnostic;
window.inspectDnssec = handleDnssecInspect;

