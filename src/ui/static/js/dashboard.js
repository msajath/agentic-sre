/**
 * Agentic SRE Platform - Humanized Console Controller
 * Designed with Senior UI/UX Architecture Standards
 */

const nodePositions = {
  "auth-service": { x: 120, y: 55 },
  "inventory-service": { x: 120, y: 150 },
  "payment-service": { x: 120, y: 245 },
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
let latestDiagnosis = null;

// Modal dialog promise resolver
let activeModalConfirm = null;

/* ==============================================================================
 * AUTHENTICATION & HEADERS
 * ============================================================================== */
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
      fetchIncidents();
      fetchAuditLogs();
      fetchRemediationPlans();
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

/* ==============================================================================
 * MODAL SYSTEM (REPLACES BROWSER PROMPT & ALERT)
 * ============================================================================== */
function showModal({ title, description, inputLabel = null, defaultValue = "", confirmText = "Confirm", isDanger = false }) {
  return new Promise((resolve) => {
    const backdrop = document.getElementById("custom-modal");
    const titleEl = document.getElementById("modal-title");
    const descEl = document.getElementById("modal-description");
    const inputGroup = document.getElementById("modal-input-group");
    const inputLabelEl = document.getElementById("modal-input-label");
    const inputEl = document.getElementById("modal-input");
    const confirmBtn = document.getElementById("modal-btn-confirm");
    const cancelBtn = document.getElementById("modal-btn-cancel");

    titleEl.innerText = title;
    descEl.innerText = description;

    if (inputLabel) {
      inputGroup.style.display = "block";
      inputLabelEl.innerText = inputLabel;
      inputEl.value = defaultValue;
    } else {
      inputGroup.style.display = "none";
      inputEl.value = "";
    }

    confirmBtn.innerText = confirmText;
    confirmBtn.className = isDanger ? "btn btn-danger" : "btn btn-primary";

    backdrop.classList.add("open");

    const cleanup = () => {
      backdrop.classList.remove("open");
      confirmBtn.onclick = null;
      cancelBtn.onclick = null;
    };

    confirmBtn.onclick = () => {
      const val = inputLabel ? inputEl.value : true;
      cleanup();
      resolve(val);
    };

    cancelBtn.onclick = () => {
      cleanup();
      resolve(null);
    };
  });
}

/* ==============================================================================
 * WEBSOCKET & TELEMETRY STREAM
 * ============================================================================== */
function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;
  
  const statusEl = document.getElementById("connection-status");
  const streamPill = document.getElementById("stream-pill");

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    statusEl.innerText = "STREAM LIVE";
    streamPill.className = "pill-badge pill-healthy";
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
    streamPill.className = "pill-badge pill-critical";
    reconnectTimer = setTimeout(initWebSocket, 2000);
  };

  ws.onerror = (err) => {
    console.error("WebSocket error:", err);
  };
}

function updateDashboard(data) {
  currentIncidentCandidate = data.incident;
  latestDiagnosis = data.diagnosis;

  updateSummaryStats(data.services);
  renderIncidentBanner(data.incident);
  renderServicesGrid(data.services);
  renderTopologySVG(data.services, data.edges);
  renderDiagnosisReport(data.diagnosis);
  renderActiveFaults(data.active_faults);
}

function updateSummaryStats(services) {
  if (!services || services.length === 0) return;

  const totalSvc = services.length;
  const healthySvc = services.filter(s => s.status === "HEALTHY").length;
  const countEl = document.getElementById("stat-services-count");
  if (countEl) countEl.innerText = `${healthySvc} / ${totalSvc}`;

  const avgP95 = services.reduce((acc, s) => acc + (s.p95_latency_ms || 0), 0) / totalSvc;
  const latencyEl = document.getElementById("stat-latency");
  if (latencyEl) latencyEl.innerText = `${Math.round(avgP95)} ms`;

  const avgError = services.reduce((acc, s) => acc + (s.error_rate || 0), 0) / totalSvc;
  const errorEl = document.getElementById("stat-error-rate");
  if (errorEl) {
    errorEl.innerText = `${(avgError * 100).toFixed(1)}%`;
    errorEl.style.color = avgError > 0.05 ? "var(--status-critical)" : (avgError > 0.01 ? "var(--status-degraded)" : "var(--text-primary)");
  }

  const healthScore = Math.max(0, 100 - (avgError * 300) - (avgP95 > 500 ? 15 : 0));
  const healthEl = document.getElementById("stat-health-score");
  if (healthEl) {
    healthEl.innerText = `${healthScore.toFixed(1)}%`;
    healthEl.style.color = healthScore > 90 ? "var(--status-healthy)" : (healthScore > 75 ? "var(--status-degraded)" : "var(--status-critical)");
  }
}

/* ==============================================================================
 * INCIDENT BANNER & CATALOG
 * ============================================================================== */
function renderIncidentBanner(incident) {
  const banner = document.getElementById("incident-banner");
  const tabBadge = document.getElementById("incident-counter-badge");
  if (!banner) return;

  if (!incident) {
    banner.classList.remove("active");
    if (tabBadge) tabBadge.style.display = "none";
    return;
  }

  banner.classList.add("active");
  if (tabBadge) {
    tabBadge.style.display = "inline-block";
    tabBadge.innerText = "1";
  }

  const titleEl = document.getElementById("incident-title");
  const descEl = document.getElementById("incident-desc");
  const rcEl = document.getElementById("incident-root-cause");
  const brEl = document.getElementById("incident-blast-radius");

  if (titleEl) titleEl.innerText = incident.title || "Correlated Anomaly Storm";
  if (descEl) descEl.innerText = incident.description || "Multi-service cascading latency detected by telemetry stream.";
  if (rcEl) rcEl.innerText = incident.root_cause_service || "Detecting root cause...";
  if (brEl) brEl.innerText = (incident.affected_services || []).join(", ") || "Isolated";
}

async function escalateActiveIncident() {
  if (!currentIncidentCandidate) {
    await showModal({
      title: "No Active Incident",
      description: "Cluster telemetry is currently healthy with zero anomalies.",
      confirmText: "OK"
    });
    return;
  }

  try {
    const url = `/api/v1/incidents?title=${encodeURIComponent(currentIncidentCandidate.title)}&description=${encodeURIComponent(currentIncidentCandidate.description)}&severity=${currentIncidentCandidate.severity}&root_cause_service=${encodeURIComponent(currentIncidentCandidate.root_cause_service || '')}`;
    const res = await fetch(url, { method: "POST", headers: getAuthHeaders() });
    if (res.ok) {
      await showModal({
        title: "Incident Logged",
        description: "Incident has been recorded in the persistent catalog.",
        confirmText: "Done"
      });
      fetchIncidents();
      fetchAuditLogs();
    } else {
      const err = await res.json();
      await showModal({ title: "Escalation Error", description: err.detail, confirmText: "Dismiss", isDanger: true });
    }
  } catch (err) {
    console.error("Escalate error:", err);
  }
}

async function fetchIncidents() {
  const container = document.getElementById("incidents-container");
  if (!container) return;

  try {
    const res = await fetch("/api/v1/incidents");
    if (!res.ok) return;
    const incidents = await res.json();

    if (incidents.length === 0) {
      container.innerHTML = `<div style="font-size: 0.8rem; color: var(--text-muted); padding: 1rem; text-align: center;">No recorded incidents in catalog.</div>`;
      return;
    }

    container.innerHTML = incidents.map(inc => {
      let actionsHtml = '';
      if (inc.state === "DETECTED") {
        actionsHtml = `<button class="btn btn-secondary" style="padding: 0.2rem 0.55rem; font-size: 0.72rem;" onclick="handleIncidentTransition('${inc.incident_id}', 'ACKNOWLEDGED')">Acknowledge</button>`;
      } else if (inc.state === "ACKNOWLEDGED") {
        actionsHtml = `<button class="btn btn-secondary" style="padding: 0.2rem 0.55rem; font-size: 0.72rem;" onclick="handleIncidentTransition('${inc.incident_id}', 'INVESTIGATING')">Investigate</button>`;
      } else if (inc.state === "INVESTIGATING") {
        actionsHtml = `<button class="btn btn-primary" style="padding: 0.2rem 0.55rem; font-size: 0.72rem;" onclick="handleIncidentTransition('${inc.incident_id}', 'RESOLVED')">Resolve</button>`;
      }

      return `
        <div style="background: var(--bg-surface-elevated); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 0.85rem; margin-bottom: 0.6rem;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
              <span style="font-family: var(--font-mono); font-weight: 700; color: #93c5fd; font-size: 0.8rem;">${inc.incident_id}</span>
              <span style="font-weight: 600; font-size: 0.82rem; margin-left: 0.4rem;">${inc.title}</span>
            </div>
            <span class="badge badge-${inc.state === 'RESOLVED' ? 'HEALTHY' : 'CRITICAL'}">${inc.state}</span>
          </div>

          <div style="font-size: 0.74rem; color: var(--text-muted); margin-top: 0.35rem;">
            Root Cause: <strong style="color: var(--text-primary);">${inc.root_cause_service || 'N/A'}</strong> | Blast: ${(inc.affected_services || []).join(', ') || 'Isolated'}
          </div>

          <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.6rem; pt: 0.4rem; border-top: 1px solid var(--border-subtle); padding-top: 0.4rem;">
            <div style="font-size: 0.7rem; color: var(--text-dim);">${new Date(inc.updated_at).toLocaleTimeString()}</div>
            <div style="display: flex; gap: 0.4rem;">${actionsHtml}</div>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error("Fetch incidents failed:", err);
  }
}

async function handleIncidentTransition(incidentId, targetState) {
  const reason = await showModal({
    title: `Transition Incident ${incidentId}`,
    description: `Move incident state to ${targetState}. Enter rationale for audit history:`,
    inputLabel: "Audit Rationale",
    defaultValue: "SRE operator triaged and updated lifecycle state",
    confirmText: "Update State"
  });

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
      await showModal({ title: "Transition Rejected", description: err.detail, confirmText: "Dismiss", isDanger: true });
    }
  } catch (err) {
    console.error("Transition failed:", err);
  }
}

/* ==============================================================================
 * TELEMETRY GRID & TOPOLOGY
 * ============================================================================== */
function renderServicesGrid(services) {
  const container = document.getElementById("services-grid");
  if (!container || !services) return;

  container.innerHTML = services.map(svc => {
    const errorPct = (svc.error_rate * 100).toFixed(1);
    const cpuPct = Math.round(svc.cpu_usage_pct || 15);
    const p95 = Math.round(svc.p95_latency_ms || 20);

    const errorFillColor = svc.error_rate > 0.05 ? "var(--status-critical)" : (svc.error_rate > 0.01 ? "var(--status-degraded)" : "var(--status-healthy)");
    const cpuFillColor = cpuPct > 80 ? "var(--status-critical)" : (cpuPct > 60 ? "var(--status-degraded)" : "var(--accent-primary)");

    return `
      <div class="service-card ${svc.status}">
        <div class="service-card-header">
          <span class="service-title">${svc.service_name}</span>
          <span class="badge badge-${svc.status}">${svc.status}</span>
        </div>

        <!-- Error Rate Bar -->
        <div class="metric-bar-group">
          <div class="metric-bar-header">
            <span>Error Rate</span>
            <span class="metric-bar-val" style="color: ${errorFillColor}">${errorPct}%</span>
          </div>
          <div class="metric-bar-track">
            <div class="metric-bar-fill" style="width: ${Math.min(100, svc.error_rate * 100 * 5)}%; background-color: ${errorFillColor};"></div>
          </div>
        </div>

        <!-- CPU Bar -->
        <div class="metric-bar-group">
          <div class="metric-bar-header">
            <span>CPU Saturation</span>
            <span class="metric-bar-val" style="color: ${cpuFillColor}">${cpuPct}%</span>
          </div>
          <div class="metric-bar-track">
            <div class="metric-bar-fill" style="width: ${cpuPct}%; background-color: ${cpuFillColor};"></div>
          </div>
        </div>

        <!-- Latency & Throughput Row -->
        <div class="service-stats-compact">
          <span>p95: <strong>${p95}ms</strong></span>
          <span>Avg: <strong>${Math.round(svc.avg_latency_ms || 10)}ms</strong></span>
          <span>Req: <strong>${Math.round(svc.throughput_rps || 0)}/s</strong></span>
        </div>

        ${svc.active_faults && svc.active_faults.length > 0 ? `
          <div style="margin-top: 0.5rem; font-size: 0.7rem; color: #f87171; background: rgba(239, 68, 68, 0.1); padding: 0.2rem 0.4rem; border-radius: var(--radius-xs); font-family: var(--font-mono);">
            Disrupted: ${svc.active_faults.join(', ')}
          </div>
        ` : ''}
      </div>
    `;
  }).join('');
}

function renderTopologySVG(services, edges) {
  const svg = document.getElementById("topology-svg");
  if (!svg || !services) return;

  const statusMap = {};
  services.forEach(s => { statusMap[s.service_name] = s.status; });

  let html = `<defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="24" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#475569" />
    </marker>
  </defs>`;

  (edges || []).forEach(e => {
    const src = nodePositions[e.source];
    const tgt = nodePositions[e.target];
    if (src && tgt) {
      html += `
        <line x1="${src.x}" y1="${src.y}" x2="${tgt.x}" y2="${tgt.y}" 
              stroke="#334155" stroke-width="1.8" stroke-dasharray="4,4" marker-end="url(#arrow)" />
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
          <circle r="26" fill="none" stroke="${color}" stroke-width="1.5" opacity="0.5">
            <animate attributeName="r" values="22;30;22" dur="2s" repeatCount="indefinite"/>
            <animate attributeName="opacity" values="0.6;0.1;0.6" dur="2s" repeatCount="indefinite"/>
          </circle>
        ` : ''}
        <circle r="18" fill="#131b2e" stroke="${color}" stroke-width="2.5" />
        <text y="4" text-anchor="middle" fill="#f8fafc" font-size="9" font-weight="700" font-family="JetBrains Mono, monospace">
          ${svcName.split('-')[0].slice(0, 4).toUpperCase()}
        </text>
        <text y="32" text-anchor="middle" fill="#94a3b8" font-size="10" font-weight="600" font-family="Plus Jakarta Sans, sans-serif">
          ${svcName}
        </text>
      </g>
    `;
  });

  svg.innerHTML = html;
}

/* ==============================================================================
 * TOPOLOGICAL RCA & ROOT CAUSE DIAGNOSIS
 * ============================================================================== */
function renderDiagnosisReport(diag) {
  const container = document.getElementById("diagnosis-content");
  const badge = document.getElementById("rca-confidence-badge");
  if (!container || !badge) return;

  if (!diag) {
    badge.className = "badge badge-HEALTHY";
    badge.innerText = "STANDBY";
    container.innerHTML = `
      <div style="font-size: 0.8rem; color: var(--text-muted); padding: 0.75rem 0;">
        Cluster healthy. Multi-service correlation standing by for anomalous telemetry signals.
      </div>
    `;
    return;
  }

  const confidencePct = Math.round(diag.confidence_score * 100);
  badge.className = "badge badge-CRITICAL";
  badge.innerText = `${confidencePct}% CONFIDENCE`;

  container.innerHTML = `
    <div style="background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: var(--radius-md); padding: 0.85rem; margin-bottom: 0.5rem;">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <span style="font-weight: 700; color: #fca5a5; font-size: 0.88rem;">
          Root Cause: <strong style="font-family: var(--font-mono);">${diag.root_cause_service}</strong>
        </span>
        <span style="font-size: 0.72rem; color: var(--text-muted); font-family: var(--font-mono);">
          Delay: ${diag.evidence ? diag.evidence.cascade_delay_ms.toFixed(1) : '0'}ms
        </span>
      </div>

      <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.4rem;">
        Causal Path: <span style="font-family: var(--font-mono); color: var(--text-primary);">${(diag.evidence && diag.evidence.causal_path ? diag.evidence.causal_path.join(' ➔ ') : diag.root_cause_service)}</span>
      </div>

      <div style="font-size: 0.72rem; color: #fef08a; margin-top: 0.25rem;">
        Cascading Symptoms: ${(diag.cascading_symptoms || []).join(', ') || 'None (Isolated)'}
      </div>

      ${diag.recommended_remediation_intent ? `
        <div style="font-size: 0.74rem; color: #93c5fd; margin-top: 0.5rem; pt: 0.35rem; border-top: 1px solid rgba(255,255,255,0.06);">
          Intent: ${diag.recommended_remediation_intent}
        </div>
      ` : ''}
    </div>
  `;
}

/* ==============================================================================
 * AGENTIC AI REASONING ASSISTANT
 * ============================================================================== */
async function fetchAiStatus() {
  const modelBadge = document.getElementById("ai-model-badge");
  if (!modelBadge) return;

  try {
    const res = await fetch("/api/v1/ai/status");
    if (res.ok) {
      const data = await res.json();
      modelBadge.innerText = data.engine;
    }
  } catch (err) {
    console.warn("AI status check warning:", err);
  }
}

async function runAiDiagnosis() {
  const container = document.getElementById("ai-reasoning-container");
  const triggerBtn = document.getElementById("btn-trigger-ai");
  if (!container) return;

  const incId = (currentIncidentCandidate && currentIncidentCandidate.incident_id) || `INC-${Date.now().toString().slice(-4)}`;

  if (triggerBtn) {
    triggerBtn.disabled = true;
    triggerBtn.innerText = "Synthesizing...";
  }

  container.innerHTML = `
    <div style="padding: 2rem; text-align: center; color: #c4b5fd; font-size: 0.85rem;">
      <div style="margin-bottom: 0.5rem;">Multi-Agent Synthesis in Progress</div>
      <div style="font-size: 0.75rem; color: var(--text-muted);">Traversing topology DAG, evaluating heuristic rules, and formulating containment strategy...</div>
    </div>
  `;

  try {
    const res = await fetch(`/api/v1/ai/analyze-incident/${incId}`, {
      method: "POST",
      headers: getAuthHeaders()
    });

    if (res.ok) {
      const data = await res.json();
      renderAiHypothesis(data, incId);
    } else {
      const err = await res.json();
      container.innerHTML = `<div style="color: #f87171; font-size: 0.8rem; padding: 1rem;">Reasoning failed: ${err.detail}</div>`;
    }
  } catch (err) {
    console.error("AI diagnosis error:", err);
    container.innerHTML = `<div style="color: #f87171; font-size: 0.8rem; padding: 1rem;">Connection error: ${err.message}</div>`;
  } finally {
    if (triggerBtn) {
      triggerBtn.disabled = false;
      triggerBtn.innerText = "Run AI Diagnosis";
    }
  }
}

function renderAiHypothesis(data, incId) {
  const container = document.getElementById("ai-reasoning-container");
  if (!container) return;

  const explanationParts = (data.explanation || "").split("; ");
  const confidencePct = Math.round((data.confidence || 0.95) * 100);

  container.innerHTML = `
    <div style="background: rgba(139, 92, 246, 0.05); border: 1px solid rgba(139, 92, 246, 0.2); border-radius: var(--radius-md); padding: 1rem;">
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem;">
        <div>
          <div style="font-size: 0.7rem; color: #a78bfa; text-transform: uppercase; font-weight: 700; letter-spacing: 0.04em;">Root Cause Hypothesis</div>
          <div style="font-size: 1.1rem; font-weight: 800; color: #f8fafc; font-family: var(--font-mono); margin-top: 0.15rem;">
            ${data.root_cause_service}
          </div>
        </div>
        <div style="text-align: right;">
          <span style="background: rgba(139, 92, 246, 0.15); color: #c4b5fd; font-weight: 700; font-size: 0.72rem; padding: 0.15rem 0.5rem; border-radius: var(--radius-xs); border: 1px solid rgba(139, 92, 246, 0.3);">
            ${confidencePct}% AI Confidence
          </span>
          <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.25rem;">Blast: ${(data.blast_radius || []).join(', ') || 'Isolated'}</div>
        </div>
      </div>

      <!-- Chain-of-Thought Trace -->
      <div style="margin-bottom: 0.85rem;">
        <div style="font-size: 0.72rem; color: #a78bfa; font-weight: 700; margin-bottom: 0.35rem; text-transform: uppercase;">
          Multi-Step Chain-of-Thought Reasoning
        </div>
        <div style="background: rgba(0, 0, 0, 0.35); border-radius: var(--radius-sm); padding: 0.6rem; font-family: var(--font-mono); font-size: 0.72rem; color: #cbd5e1; max-height: 140px; overflow-y: auto;">
          ${explanationParts.map(step => `
            <div class="cot-step-item">
              <span class="cot-step-badge">${step.split(']')[0].replace('[', '') || 'Step'}</span>
              <span>${step.includes(']') ? step.split(']')[1] : step}</span>
            </div>
          `).join('')}
        </div>
      </div>

      <!-- Mitigation Procedure -->
      <div style="margin-bottom: 0.85rem;">
        <div style="font-size: 0.72rem; color: #a78bfa; font-weight: 700; margin-bottom: 0.35rem; text-transform: uppercase;">
          Synthesized Mitigation Procedure
        </div>
        <div style="display: flex; flex-direction: column; gap: 0.35rem;">
          ${(data.mitigation_steps || []).map(step => `
            <div style="font-size: 0.75rem; color: var(--text-secondary); display: flex; align-items: flex-start; gap: 0.4rem;">
              <span style="color: #10b981; font-weight: 700;">✓</span>
              <span>${step}</span>
            </div>
          `).join('')}
        </div>
      </div>

      <!-- Proposed Remediation Action -->
      <div style="display: flex; justify-content: space-between; align-items: center; pt: 0.6rem; border-top: 1px solid rgba(139, 92, 246, 0.2); padding-top: 0.6rem;">
        <span style="font-size: 0.76rem; color: var(--text-secondary);">
          Recommended Action: <strong style="color: #93c5fd; font-family: var(--font-mono);">${data.recommended_action}</strong>
        </span>
        <button class="btn btn-purple" style="padding: 0.3rem 0.8rem; font-size: 0.75rem;" onclick="proposeSpecificPlan('${data.root_cause_service}', '${data.recommended_action}', '${incId}')">
          Propose Action
        </button>
      </div>
    </div>
  `;
}

async function proposeSpecificPlan(serviceName, actionType, incId) {
  try {
    const res = await fetch("/api/v1/remediation/propose", {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({
        incident_id: incId,
        target_service: serviceName,
        action_type: actionType,
        parameters: { reason: "Formulated by Agentic AI Reasoning Orchestrator" }
      })
    });
    if (res.ok) {
      await showModal({
        title: "Remediation Plan Queued",
        description: `Plan [${actionType} on ${serviceName}] has been proposed and sent to the approval gateway.`,
        confirmText: "View Gateway"
      });
      fetchRemediationPlans();
      fetchAuditLogs();
    } else {
      const err = await res.json();
      await showModal({ title: "Proposal Failed", description: err.detail, confirmText: "Dismiss", isDanger: true });
    }
  } catch (err) {
    console.error("Propose plan error:", err);
  }
}

/* ==============================================================================
 * REMEDIATION APPROVAL GATEWAY
 * ============================================================================== */
async function fetchRemediationPlans() {
  const container = document.getElementById("remediation-plans-container");
  if (!container) return;

  try {
    const res = await fetch("/api/v1/remediation/plans");
    if (!res.ok) return;
    const plans = await res.json();

    if (plans.length === 0) {
      container.innerHTML = `<div style="font-size: 0.8rem; color: var(--text-muted); padding: 1rem; text-align: center;">No active or past remediation plans.</div>`;
      return;
    }

    container.innerHTML = plans.map(p => {
      let actionButtons = '';
      if (p.state === "PENDING_APPROVAL") {
        actionButtons = `
          <button class="btn btn-primary" style="padding: 0.2rem 0.6rem; font-size: 0.72rem;" onclick="approvePlan('${p.plan_id}')">
            Approve & Execute
          </button>
          <button class="btn btn-secondary" style="padding: 0.2rem 0.6rem; font-size: 0.72rem;" onclick="rejectPlan('${p.plan_id}')">
            Reject
          </button>
        `;
      }

      const statusColor = p.state === 'VERIFIED_SUCCESSFUL' ? 'HEALTHY' : (p.state === 'REJECTED' || p.state === 'FAILED_ROLLBACK' ? 'CRITICAL' : 'DEGRADED');

      return `
        <div style="background: var(--bg-surface-elevated); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 0.85rem; margin-bottom: 0.6rem;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
              <span style="font-family: var(--font-mono); font-weight: 700; color: #93c5fd; font-size: 0.8rem;">${p.plan_id}</span>
              <span style="font-weight: 600; font-size: 0.82rem; margin-left: 0.4rem;">${p.action_type}</span>
              <span style="color: var(--text-muted); font-size: 0.78rem;">on <strong>${p.target_service}</strong></span>
            </div>
            <span class="badge badge-${statusColor}">${p.state}</span>
          </div>

          <div style="font-size: 0.74rem; color: var(--text-muted); margin-top: 0.35rem;">
            Blast Radius: <strong>${(p.safety_blast_radius || []).join(', ') || 'Isolated'}</strong> | Proposed by: <em>${p.proposed_by}</em>
          </div>

          ${p.recovery_verification_notes ? `
            <div style="margin-top: 0.4rem; font-size: 0.72rem; color: #86efac; background: rgba(34, 197, 94, 0.1); padding: 0.3rem 0.5rem; border-radius: var(--radius-sm);">
              ✔ ${p.recovery_verification_notes}
            </div>
          ` : ''}

          ${actionButtons ? `
            <div style="display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 0.6rem; pt: 0.4rem; border-top: 1px solid var(--border-subtle); padding-top: 0.4rem;">
              ${actionButtons}
            </div>
          ` : ''}
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error("Fetch plans error:", err);
  }
}

async function proposeAutoRemediation() {
  const rootSvc = (currentIncidentCandidate && currentIncidentCandidate.root_cause_service) || (latestDiagnosis && latestDiagnosis.root_cause_service) || "payment-service";
  const incId = (currentIncidentCandidate && currentIncidentCandidate.incident_id) || `INC-${Date.now().toString().slice(-4)}`;

  try {
    const res = await fetch("/api/v1/remediation/propose", {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({
        incident_id: incId,
        target_service: rootSvc,
        action_type: "RESTART_SERVICE",
        parameters: { reason: "RCA-recommended automated restart & fault clearance" }
      })
    });
    if (res.ok) {
      await showModal({
        title: "Plan Proposed",
        description: `Automated remediation plan queued for [${rootSvc}]. Awaiting human SRE Lead approval.`,
        confirmText: "OK"
      });
      fetchRemediationPlans();
      fetchAuditLogs();
    } else {
      const err = await res.json();
      await showModal({ title: "Proposal Failed", description: err.detail, confirmText: "Dismiss", isDanger: true });
    }
  } catch (err) {
    console.error("Propose remediation error:", err);
  }
}

async function approvePlan(planId) {
  const reason = await showModal({
    title: `Approve Remediation Plan ${planId}`,
    description: "Authenticated SRE Lead Gate: Enter approval rationale to trigger execution and post-recovery verification.",
    inputLabel: "Approval Rationale",
    defaultValue: "Approved after reviewing dependency graph, metrics, and safety blast radius",
    confirmText: "Approve & Execute"
  });

  if (!reason) return;

  try {
    const res = await fetch(`/api/v1/remediation/plans/${planId}/approve`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({ reason })
    });
    if (res.ok) {
      const plan = await res.json();
      await showModal({
        title: "Remediation Executed & Verified",
        description: `Plan status: ${plan.state}.\n\nVerification notes: ${plan.recovery_verification_notes}`,
        confirmText: "Done"
      });
      fetchRemediationPlans();
      fetchIncidents();
      fetchAuditLogs();
    } else {
      const err = await res.json();
      await showModal({ title: "Approval Denied", description: err.detail, confirmText: "Dismiss", isDanger: true });
    }
  } catch (err) {
    console.error("Approve error:", err);
  }
}

async function rejectPlan(planId) {
  const reason = await showModal({
    title: `Reject Plan ${planId}`,
    description: "Enter rejection reason:",
    inputLabel: "Rejection Reason",
    defaultValue: "Declined by SRE Lead after evaluating risk profile",
    confirmText: "Reject Plan",
    isDanger: true
  });

  if (!reason) return;

  try {
    const res = await fetch(`/api/v1/remediation/plans/${planId}/reject`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({ reason })
    });
    if (res.ok) {
      fetchRemediationPlans();
      fetchAuditLogs();
    } else {
      const err = await res.json();
      await showModal({ title: "Rejection Failed", description: err.detail, confirmText: "Dismiss", isDanger: true });
    }
  } catch (err) {
    console.error("Reject error:", err);
  }
}

/* ==============================================================================
 * CHAOS CONTROLLER
 * ============================================================================== */
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
      await showModal({ title: "Fault Injection Failed", description: err.detail, confirmText: "Dismiss", isDanger: true });
    } else {
      fetchAuditLogs();
    }
  } catch (err) {
    console.error("Fault inject request error:", err);
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
  const confirmed = await showModal({
    title: "Emergency Chaos Reset",
    description: "Are you sure you want to cancel and clear all active faults across the entire cluster?",
    confirmText: "Reset All Faults",
    isDanger: true
  });

  if (confirmed) {
    try {
      await fetch("/api/v1/chaos/reset", { method: "POST" });
      fetchAuditLogs();
    } catch (err) {
      console.error("Emergency reset error:", err);
    }
  }
}

function renderActiveFaults(faults) {
  const container = document.getElementById("active-faults-list");
  if (!container) return;

  if (!faults || faults.length === 0) {
    container.innerHTML = `<div style="font-size: 0.8rem; color: var(--text-muted); padding: 1rem; text-align: center;">No active chaos faults currently disrupting the cluster.</div>`;
    return;
  }

  container.innerHTML = faults.map(f => `
    <div style="background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: var(--radius-md); padding: 0.75rem; margin-bottom: 0.5rem; display: flex; justify-content: space-between; align-items: center;">
      <div>
        <div style="font-family: var(--font-mono); font-size: 0.82rem; font-weight: 700; color: #fca5a5;">
          ${f.service_name} ➔ ${f.fault_type}
        </div>
        <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.2rem;">
          Magnitude: ${f.magnitude} | Injected by: ${f.injected_by}
        </div>
      </div>
      <button class="btn btn-secondary" style="padding: 0.2rem 0.55rem; font-size: 0.72rem;" onclick="clearFault('${f.service_name}', '${f.fault_type}')">
        Clear
      </button>
    </div>
  `).join('');
}

/* ==============================================================================
 * AUDIT LEDGER & TAMPER SCANNER
 * ============================================================================== */
async function fetchAuditLogs() {
  const container = document.getElementById("audit-ledger-container");
  if (!container) return;

  try {
    const res = await fetch("/api/v1/audit/logs?limit=25");
    if (!res.ok) return;
    const logs = await res.json();

    container.innerHTML = logs.map(l => `
      <div style="padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--border-subtle); display: grid; grid-template-columns: 140px 140px 1fr 140px; gap: 0.75rem; align-items: center; font-size: 0.75rem;">
        <div style="font-family: var(--font-mono); color: var(--text-dim); font-size: 0.7rem;">
          ${new Date(l.timestamp).toLocaleTimeString()}
        </div>
        <div>
          <span style="font-weight: 700; color: #93c5fd; font-size: 0.72rem;">${l.actor}</span>
          <span style="color: var(--text-dim); font-size: 0.68rem;">(${l.actor_role})</span>
        </div>
        <div>
          <div style="color: var(--text-primary); font-weight: 600;">${l.action_summary}</div>
          <div style="color: var(--text-muted); font-size: 0.7rem;">Target: <code style="font-family: var(--font-mono);">${l.target_resource}</code></div>
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-dim); text-align: right;" title="SHA-256: ${l.entry_hash}">
          ${l.entry_hash.slice(0, 10)}...
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error("Fetch audit logs error:", err);
  }
}

async function verifyAuditChain() {
  const auditStatusEl = document.getElementById("audit-status");
  const auditPillEl = document.getElementById("audit-pill");

  try {
    const res = await fetch("/api/v1/audit/verify");
    if (res.ok) {
      const rep = await res.json();
      if (rep.is_valid) {
        if (auditStatusEl) auditStatusEl.innerText = "LEDGER VERIFIED";
        if (auditPillEl) auditPillEl.className = "pill-badge pill-healthy";
        await showModal({
          title: "Cryptographic Chain Verified",
          description: `All ${rep.total_entries} blocks verified successfully.\nGenesis block intact. Backward SHA-256 pointers confirmed.`,
          confirmText: "OK"
        });
      } else {
        if (auditStatusEl) auditStatusEl.innerText = "TAMPER DETECTED";
        if (auditPillEl) auditPillEl.className = "pill-badge pill-critical";
        await showModal({
          title: "Cryptographic Verification Alert",
          description: `Tampering detected!\n\nBlock ID: ${rep.tampered_entry_id}\nMessage: ${rep.message}`,
          confirmText: "Dismiss",
          isDanger: true
        });
      }
    }
  } catch (err) {
    console.error("Audit verification error:", err);
  }
}

/* ==============================================================================
 * TABS & DOM INITIALIZATION
 * ============================================================================== */
document.addEventListener("DOMContentLoaded", () => {
  authenticate("operator");
  initWebSocket();
  fetchAiStatus();

  // Tab switching
  const tabButtons = document.querySelectorAll(".nav-tab-btn");
  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTabId = btn.getAttribute("data-tab");
      
      tabButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      document.querySelectorAll(".tab-content").forEach(tc => tc.classList.remove("active"));
      const targetContent = document.getElementById(targetTabId);
      if (targetContent) targetContent.classList.add("active");
    });
  });

  // Banner shortcut to AI tab
  const bannerAiBtn = document.getElementById("btn-banner-ai");
  if (bannerAiBtn) {
    bannerAiBtn.addEventListener("click", () => {
      const incidentTabBtn = document.querySelector('[data-tab="tab-incidents"]');
      if (incidentTabBtn) incidentTabBtn.click();
      runAiDiagnosis();
    });
  }

  // Event handlers
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

  const proposeBtn = document.getElementById("btn-propose-remediation");
  if (proposeBtn) proposeBtn.addEventListener("click", proposeAutoRemediation);

  const refreshPlansBtn = document.getElementById("btn-refresh-plans");
  if (refreshPlansBtn) refreshPlansBtn.addEventListener("click", fetchRemediationPlans);

  const triggerAiBtn = document.getElementById("btn-trigger-ai");
  if (triggerAiBtn) triggerAiBtn.addEventListener("click", runAiDiagnosis);
});
