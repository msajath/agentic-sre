/**
 * Agentic SRE Platform - Real-time Dashboard Controller (Sprint 2)
 */

const nodePositions = {
  "auth-service": { x: 120, y: 60 },
  "inventory-service": { x: 120, y: 150 },
  "payment-service": { x: 120, y: 240 },
  "order-service": { x: 380, y: 150 },
  "notification-service": { x: 620, y: 150 }
};

const userCredentials = {
  admin: "AdminSre@2026",
  lead: "LeadSre@2026",
  operator: "OperatorSre@2026",
  viewer: "ViewerSre@2026"
};

let currentToken = null;
let currentRole = "operator";
let ws = null;
let reconnectTimer = null;
let currentIncidentCandidate = null;

// Authenticate and acquire scoped JWT
async function authenticate(username = "operator") {
  const password = userCredentials[username] || "OperatorSre@2026";
  try {
    const res = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    if (res.ok) {
      const data = await res.json();
      currentToken = data.access_token;
      currentRole = data.role;
      console.log(`[Auth] Switched identity to: ${username} (${currentRole})`);
      fetchIncidents();
      fetchAuditLogs();
    }
  } catch (err) {
    console.error("[Auth] Login error:", err);
  }
}

function getAuthHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (currentToken) {
    headers["Authorization"] = `Bearer ${currentToken}`;
  }
  return headers;
}

function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;
  
  const statusEl = document.getElementById("connection-status");
  const dotEl = document.getElementById("connection-dot");

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    statusEl.innerText = "STREAM LIVE";
    dotEl.style.backgroundColor = "var(--status-healthy)";
    if (reconnectTimer) clearTimeout(reconnectTimer);
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "TELEMETRY_SNAPSHOT") {
        updateDashboard(data);
      }
    } catch (err) {
      console.error("Failed to parse websocket message:", err);
    }
  };

  ws.onclose = () => {
    statusEl.innerText = "RECONNECTING";
    dotEl.style.backgroundColor = "var(--status-critical)";
    reconnectTimer = setTimeout(initWebSocket, 2000);
  };

  ws.onerror = (err) => {
    console.error("WebSocket encountered error:", err);
  };
}

function updateDashboard(data) {
  currentIncidentCandidate = data.incident;
  renderServicesGrid(data.services);
  renderActiveFaults(data.active_faults);
  renderIncidentBanner(data.incident, data.anomalies);
  renderAnomaliesList(data.anomalies);
  renderDiagnosisReport(data.diagnosis);
  renderTopologySVG(data.services, data.edges);
}

function renderDiagnosisReport(diag) {
  const badge = document.getElementById("rca-confidence-badge");
  const content = document.getElementById("diagnosis-content");
  if (!badge || !content) return;

  if (!diag) {
    badge.innerText = "STANDBY (HEALTHY)";
    badge.className = "status-badge badge-HEALTHY";
    content.innerHTML = `
      <div style="font-size: 0.8rem; color: var(--text-dim); padding: 0.5rem 0;">
        Cluster healthy. Awaiting anomalous signals to trigger correlation...
      </div>
    `;
    return;
  }

  badge.innerText = `CONFIDENCE: ${(diag.confidence_score * 100).toFixed(0)}%`;
  badge.className = "status-badge badge-CRITICAL";

  let hopsHtml = '';
  if (diag.causal_chain && diag.causal_chain.length > 0) {
    hopsHtml = diag.causal_chain.map(h => `
      <div style="font-size: 0.75rem; background: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.25); border-radius: var(--radius-sm); padding: 0.4rem 0.6rem; margin-top: 0.35rem;">
        <strong>${h.from_service}</strong> ──► <strong>${h.to_service}</strong>
        <div style="color: var(--text-muted); font-size: 0.7rem;">${h.impact_description}</div>
      </div>
    `).join('');
  } else {
    hopsHtml = `<div style="font-size: 0.75rem; color: var(--text-muted);">Root cause isolated with no upstream cascade.</div>`;
  }

  content.innerHTML = `
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 0.75rem;">
      <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: var(--radius-sm); padding: 0.6rem;">
        <div style="font-size: 0.7rem; color: #fca5a5; font-weight: 700; text-transform: uppercase;">Diagnosed Root Cause</div>
        <div style="font-size: 1rem; font-weight: 800; color: #f87171; font-family: monospace;">${diag.root_cause_service}</div>
        <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.2rem;">Metric: ${diag.evidence.root_cause_metric}</div>
      </div>
      <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: var(--radius-sm); padding: 0.6rem;">
        <div style="font-size: 0.7rem; color: #fde68a; font-weight: 700; text-transform: uppercase;">Cascading Symptoms</div>
        <div style="font-size: 0.95rem; font-weight: 700; color: #fbbf24; font-family: monospace;">
          ${diag.cascading_symptoms.length > 0 ? diag.cascading_symptoms.join(', ') : 'None (Isolated)'}
        </div>
        <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.2rem;">Cascade Delay: ${diag.evidence.cascade_delay_ms} ms</div>
      </div>
    </div>

    <div style="margin-bottom: 0.75rem;">
      <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted);">Causal Propagation Chain</div>
      ${hopsHtml}
    </div>

    <div style="background: rgba(99, 102, 241, 0.12); border: 1px solid rgba(99, 102, 241, 0.3); border-radius: var(--radius-sm); padding: 0.6rem;">
      <div style="font-size: 0.7rem; color: #c7d2fe; font-weight: 700; text-transform: uppercase;">Recommended Remediation Intent</div>
      <div style="font-size: 0.8rem; font-weight: 600; color: #e0e7ff; margin-top: 0.2rem;">${diag.recommended_remediation_intent}</div>
    </div>
  `;
}

function renderServicesGrid(services) {
  const container = document.getElementById("services-grid");
  if (!container) return;

  container.innerHTML = services.map(svc => `
    <div class="service-card ${svc.status}">
      <div class="service-header">
        <span class="service-name">${svc.service_name}</span>
        <span class="status-badge badge-${svc.status}">${svc.status}</span>
      </div>
      <div class="metric-row">
        <span>Error Rate:</span>
        <span class="metric-val" style="color: ${svc.error_rate > 0.05 ? 'var(--status-critical)' : 'inherit'}">
          ${(svc.error_rate * 100).toFixed(1)}%
        </span>
      </div>
      <div class="metric-row">
        <span>p95 Latency:</span>
        <span class="metric-val" style="color: ${svc.p95_latency_ms > 800 ? 'var(--status-degraded)' : 'inherit'}">
          ${svc.p95_latency_ms.toFixed(0)} ms
        </span>
      </div>
      <div class="metric-row">
        <span>Avg Latency:</span>
        <span class="metric-val">${svc.avg_latency_ms.toFixed(0)} ms</span>
      </div>
      <div class="metric-row">
        <span>CPU / Mem:</span>
        <span class="metric-val">${svc.cpu_usage_pct}% / ${svc.memory_usage_pct}%</span>
      </div>
      ${svc.active_faults && svc.active_faults.length > 0 ? `
        <div style="margin-top: 0.5rem; font-size: 0.72rem; color: #f87171; font-weight: 600;">
          ⚠ Fault: ${svc.active_faults.join(', ')}
        </div>
      ` : ''}
    </div>
  `).join('');
}

function renderActiveFaults(faults) {
  const container = document.getElementById("active-faults-list");
  if (!container) return;

  if (!faults || faults.length === 0) {
    container.innerHTML = `<div style="font-size: 0.8rem; color: var(--text-dim); padding: 0.5rem 0;">No active chaos faults injected.</div>`;
    return;
  }

  container.innerHTML = faults.map(f => `
    <div class="fault-item">
      <div>
        <strong>${f.service_name}</strong> - <span>${f.fault_type}</span>
        <div style="font-size: 0.7rem; color: var(--text-dim);">Mag: ${f.magnitude} | By: ${f.injected_by}</div>
      </div>
      <button class="btn btn-secondary" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;" onclick="clearFault('${f.service_name}', '${f.fault_type}')">
        Clear
      </button>
    </div>
  `).join('');
}

function renderIncidentBanner(incident, anomalies) {
  const banner = document.getElementById("incident-banner");
  if (!banner) return;

  if (!incident) {
    banner.classList.remove("active");
    return;
  }

  banner.classList.add("active");
  document.getElementById("incident-title").innerText = incident.title;
  document.getElementById("incident-desc").innerText = incident.description;
  document.getElementById("incident-root-cause").innerText = incident.root_cause_service || "Correlating...";
  document.getElementById("incident-blast-radius").innerText = (incident.affected_services || []).join(", ");
}

function renderAnomaliesList(anomalies) {
  const container = document.getElementById("anomalies-list");
  if (!container) return;

  if (!anomalies || anomalies.length === 0) {
    container.innerHTML = `<div style="font-size: 0.8rem; color: var(--text-dim);">Cluster healthy. Zero anomalous signals.</div>`;
    return;
  }

  container.innerHTML = anomalies.map(a => `
    <div class="anomaly-card ${a.severity}">
      <div style="display: flex; justify-content: space-between; font-weight: 600;">
        <span>${a.service_name}</span>
        <span style="font-size: 0.7rem; color: ${a.severity === 'CRITICAL' ? 'var(--status-critical)' : 'var(--status-degraded)'}">
          ${a.severity}
        </span>
      </div>
      <div style="font-size: 0.75rem; margin-top: 0.2rem; color: var(--text-muted);">${a.description}</div>
    </div>
  `).join('');
}

function renderTopologySVG(services, edges) {
  const svg = document.getElementById("topology-svg");
  if (!svg) return;

  const statusMap = {};
  services.forEach(s => { statusMap[s.service_name] = s.status; });

  let html = `<defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
    </marker>
    <filter id="glow-red">
      <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
      <feMerge>
        <feMergeNode in="coloredBlur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>`;

  edges.forEach(e => {
    const src = nodePositions[e.source];
    const tgt = nodePositions[e.target];
    if (src && tgt) {
      html += `
        <line x1="${src.x}" y1="${src.y}" x2="${tgt.x}" y2="${tgt.y}" 
              stroke="#334155" stroke-width="2" stroke-dasharray="4,4" marker-end="url(#arrow)" />
      `;
    }
  });

  Object.keys(nodePositions).forEach(svcName => {
    const pos = nodePositions[svcName];
    const status = statusMap[svcName] || "HEALTHY";
    let color = "#10b981";
    if (status === "DEGRADED") color = "#f59e0b";
    if (status === "CRITICAL" || status === "DOWN") color = "#ef4444";

    const isDistressed = status === "CRITICAL" || status === "DOWN";

    html += `
      <g transform="translate(${pos.x}, ${pos.y})">
        ${isDistressed ? `
          <circle r="28" fill="none" stroke="${color}" stroke-width="2" opacity="0.6">
            <animate attributeName="r" values="24;36;24" dur="1.5s" repeatCount="indefinite"/>
            <animate attributeName="opacity" values="0.8;0.1;0.8" dur="1.5s" repeatCount="indefinite"/>
          </circle>
        ` : ''}
        <circle r="22" fill="#1e293b" stroke="${color}" stroke-width="3" filter="${isDistressed ? 'url(#glow-red)' : 'none'}" />
        <text y="4" text-anchor="middle" fill="#f8fafc" font-size="10" font-weight="700">
          ${svcName.split('-')[0].toUpperCase()}
        </text>
        <text y="38" text-anchor="middle" fill="#94a3b8" font-size="10" font-weight="600">
          ${svcName}
        </text>
      </g>
    `;
  });

  svg.innerHTML = html;
}

// Sprint 2: Incidents Management
async function fetchIncidents() {
  const container = document.getElementById("incidents-container");
  if (!container) return;

  try {
    const res = await fetch("/api/v1/incidents");
    if (!res.ok) return;
    const incidents = await res.json();

    if (incidents.length === 0) {
      container.innerHTML = `<div style="font-size: 0.8rem; color: var(--text-dim); padding: 0.5rem 0;">No recorded incidents in catalog.</div>`;
      return;
    }

    container.innerHTML = incidents.map(inc => {
      let actionsHtml = '';
      if (inc.state === "DETECTED") {
        actionsHtml = `<button class="btn btn-secondary" style="padding: 0.15rem 0.5rem; font-size: 0.7rem;" onclick="transitionIncident('${inc.incident_id}', 'ACKNOWLEDGED')">Acknowledge</button>`;
      } else if (inc.state === "ACKNOWLEDGED") {
        actionsHtml = `<button class="btn btn-secondary" style="padding: 0.15rem 0.5rem; font-size: 0.7rem;" onclick="transitionIncident('${inc.incident_id}', 'INVESTIGATING')">Investigate</button>`;
      } else if (inc.state === "INVESTIGATING") {
        actionsHtml = `<button class="btn btn-primary" style="padding: 0.15rem 0.5rem; font-size: 0.7rem;" onclick="transitionIncident('${inc.incident_id}', 'RESOLVED')">Resolve</button>`;
      }

      return `
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.75rem; margin-bottom: 0.5rem;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
              <span style="font-weight: 700; color: #a5b4fc; font-size: 0.85rem;">${inc.incident_id}</span>
              <span style="font-size: 0.8rem; margin-left: 0.5rem;">${inc.title}</span>
            </div>
            <span class="status-badge badge-${inc.state === 'RESOLVED' ? 'HEALTHY' : 'CRITICAL'}">${inc.state}</span>
          </div>
          <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.3rem;">
            Root Cause: <strong>${inc.root_cause_service || 'N/A'}</strong> | Blast: ${(inc.affected_services || []).join(', ')}
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem;">
            <div style="font-size: 0.7rem; color: var(--text-dim);">Updated: ${new Date(inc.updated_at).toLocaleTimeString()}</div>
            <div style="display: flex; gap: 0.4rem;">${actionsHtml}</div>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error("Fetch incidents failed:", err);
  }
}

async function transitionIncident(incidentId, targetState) {
  const reason = prompt(`Enter reason for transitioning ${incidentId} to ${targetState}:`, `SRE operator triaged incident`);
  if (!reason) return;

  try {
    const res = await fetch(`/api/v1/incidents/${incidentId}/state`, {
      method: "PATCH",
      headers: getAuthHeaders(),
      body: JSON.stringify({ target_state: targetState, reason })
    });
    if (res.ok) {
      fetchIncidents();
      fetchAuditLogs();
    } else {
      const err = await res.json();
      alert(`Transition rejected: ${err.detail}`);
    }
  } catch (err) {
    console.error("Transition failed:", err);
  }
}

async function escalateActiveIncident() {
  if (!currentIncidentCandidate) {
    alert("No active incident candidate currently detected.");
    return;
  }

  try {
    const url = `/api/v1/incidents?title=${encodeURIComponent(currentIncidentCandidate.title)}&description=${encodeURIComponent(currentIncidentCandidate.description)}&severity=${currentIncidentCandidate.severity}&root_cause_service=${encodeURIComponent(currentIncidentCandidate.root_cause_service || '')}`;
    const res = await fetch(url, {
      method: "POST",
      headers: getAuthHeaders()
    });
    if (res.ok) {
      alert("Incident successfully logged in persistent catalog!");
      fetchIncidents();
      fetchAuditLogs();
    } else {
      const err = await res.json();
      alert(`Escalation failed: ${err.detail}`);
    }
  } catch (err) {
    console.error("Escalate failed:", err);
  }
}

// Sprint 2: Cryptographic Audit Ledger
async function fetchAuditLogs() {
  const container = document.getElementById("audit-ledger-container");
  if (!container) return;

  try {
    const res = await fetch("/api/v1/audit/logs?limit=15");
    if (!res.ok) return;
    const logs = await res.json();

    container.innerHTML = logs.map(l => `
      <div style="padding: 0.4rem 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.05);">
        <div style="display: flex; justify-content: space-between; color: var(--text-muted);">
          <span>${l.actor} [${l.actor_role}]</span>
          <span>${new Date(l.timestamp).toLocaleTimeString()}</span>
        </div>
        <div style="color: var(--text-main); font-weight: 600; margin: 0.15rem 0;">${l.action_summary}</div>
        <div style="color: #6366f1; font-size: 0.65rem; word-break: break-all;">
          🔗 ${l.entry_hash.substring(0, 24)}...
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error("Fetch audit logs failed:", err);
  }
}

async function verifyAuditChain() {
  try {
    const res = await fetch("/api/v1/audit/verify");
    if (res.ok) {
      const report = await res.json();
      const statusEl = document.getElementById("audit-status");
      if (report.is_valid) {
        statusEl.innerText = `LEDGER VERIFIED (${report.total_entries} BLOCKS)`;
        statusEl.style.color = "var(--status-healthy)";
        alert(`Cryptographic Verification Succeeded:\n• Valid: ${report.is_valid}\n• Total Blocks: ${report.total_entries}\n• Genesis Verified: ${report.genesis_verified}\n• Message: ${report.message}`);
      } else {
        statusEl.innerText = "CHAIN TAMPERED";
        statusEl.style.color = "var(--status-critical)";
        alert(`WARNING: Tampering Detected in block ${report.tampered_entry_id}!`);
      }
    }
  } catch (err) {
    console.error("Verify audit chain failed:", err);
  }
}

// Inject Chaos Fault
async function handleInjectFault(e) {
  e.preventDefault();
  const service_name = document.getElementById("fault-service").value;
  const fault_type = document.getElementById("fault-type").value;
  const magnitude = parseFloat(document.getElementById("fault-magnitude").value) || 1.0;
  const duration_sec = parseInt(document.getElementById("fault-duration").value) || 30;

  try {
    const resp = await fetch("/api/v1/chaos/inject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        service_name,
        fault_type,
        magnitude,
        duration_sec,
        injected_by: `sre-${currentRole.toLowerCase()}`
      })
    });
    if (!resp.ok) {
      const err = await resp.json();
      alert(`Fault injection failed: ${err.detail}`);
    } else {
      fetchAuditLogs();
    }
  } catch (err) {
    console.error("Fault injection request failed:", err);
  }
}

async function clearFault(serviceName, faultType) {
  try {
    await fetch(`/api/v1/chaos/faults/${serviceName}?fault_type=${faultType}`, {
      method: "DELETE"
    });
    fetchAuditLogs();
  } catch (err) {
    console.error("Clear fault error:", err);
  }
}

async function emergencyReset() {
  if (confirm("Reset and clear all active faults across the cluster?")) {
    try {
      await fetch("/api/v1/chaos/reset", { method: "POST" });
      fetchAuditLogs();
    } catch (err) {
      console.error("Emergency reset error:", err);
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  authenticate("operator");
  initWebSocket();

  const form = document.getElementById("chaos-form");
  if (form) form.addEventListener("submit", handleInjectFault);
  
  const resetBtn = document.getElementById("btn-emergency-reset");
  if (resetBtn) resetBtn.addEventListener("click", emergencyReset);

  const roleSelect = document.getElementById("user-role-select");
  if (roleSelect) {
    roleSelect.addEventListener("change", (e) => {
      authenticate(e.target.value);
    });
  }

  const escalateBtn = document.getElementById("btn-escalate-incident");
  if (escalateBtn) escalateBtn.addEventListener("click", escalateActiveIncident);

  const refreshIncBtn = document.getElementById("btn-refresh-incidents");
  if (refreshIncBtn) refreshIncBtn.addEventListener("click", fetchIncidents);

  const verifyAuditBtn = document.getElementById("btn-verify-audit");
  if (verifyAuditBtn) verifyAuditBtn.addEventListener("click", verifyAuditChain);

  const auditPill = document.getElementById("audit-pill");
  if (auditPill) auditPill.addEventListener("click", verifyAuditChain);
});
