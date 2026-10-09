/**
 * Agentic SRE Platform - Real-time Dashboard Controller
 */

const nodePositions = {
  "auth-service": { x: 120, y: 60 },
  "inventory-service": { x: 120, y: 150 },
  "payment-service": { x: 120, y: 240 },
  "order-service": { x: 380, y: 150 },
  "notification-service": { x: 620, y: 150 }
};

let ws = null;
let reconnectTimer = null;

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
  renderServicesGrid(data.services);
  renderActiveFaults(data.active_faults);
  renderIncidentBanner(data.incident, data.anomalies);
  renderAnomaliesList(data.anomalies);
  renderTopologySVG(data.services, data.edges);
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

  // Draw Edges
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

  // Draw Nodes
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
        injected_by: "sre-operator"
      })
    });
    if (!resp.ok) {
      const err = await resp.json();
      alert(`Fault injection failed: ${err.detail}`);
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
  } catch (err) {
    console.error("Clear fault error:", err);
  }
}

async function emergencyReset() {
  if (confirm("Reset and clear all active faults across the cluster?")) {
    try {
      await fetch("/api/v1/chaos/reset", { method: "POST" });
    } catch (err) {
      console.error("Emergency reset error:", err);
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initWebSocket();
  const form = document.getElementById("chaos-form");
  if (form) form.addEventListener("submit", handleInjectFault);
  const resetBtn = document.getElementById("btn-emergency-reset");
  if (resetBtn) resetBtn.addEventListener("click", emergencyReset);
});
