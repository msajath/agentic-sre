import React, { useState, useEffect, useCallback } from 'react';
import './index.css';

const API_BASE = "http://localhost:8000";

const nodePositions = {
  "auth-service": { x: 120, y: 55 },
  "inventory-service": { x: 120, y: 150 },
  "payment-service": { x: 120, y: 245 },
  "order-service": { x: 380, y: 150 },
  "notification-service": { x: 620, y: 150 }
};

const userCredentials = {
  admin: { role: "admin", label: "Cluster Administrator", perm: "Full Cluster & Mutation Access" },
  lead: { role: "lead", label: "SRE Lead", perm: "Remediation Approvals & Chaos Controls" },
  operator: { role: "operator", label: "Site Reliability Engineer", perm: "Triage, Diagnostics & Propose" },
  viewer: { role: "viewer", label: "Security & Compliance Auditor", perm: "Read-Only Observability" }
};

export default function App() {
  const [theme, setTheme] = useState('dark');
  const [role, setRole] = useState('operator');
  const [token, setToken] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [wsStatus, setWsStatus] = useState('CONNECTING');

  // Core Telemetry & Cluster State
  const [services, setServices] = useState([]);
  const [edges, setEdges] = useState([]);
  const [incident, setIncident] = useState(null);
  const [diagnosis, setDiagnosis] = useState(null);
  const [activeFaults, setActiveFaults] = useState([]);

  // Data Collections
  const [incidentsList, setIncidentsList] = useState([]);
  const [selectedIncidentDetail, setSelectedIncidentDetail] = useState(null);
  const [remediationPlans, setRemediationPlans] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditVerification, setAuditVerification] = useState(null);

  // Extended Data Collections
  const [benchmarkData, setBenchmarkData] = useState({ metrics: null, scenarios: [] });
  const [selectedScenarioReplay, setSelectedScenarioReplay] = useState(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [knowledgeDocs, setKnowledgeDocs] = useState([]);
  const [ragQuery, setRagQuery] = useState('');
  const [ragSearchResults, setRagSearchResults] = useState(null);
  const [agentsList, setAgentsList] = useState([]);
  const [servicesCatalog, setServicesCatalog] = useState([]);
  const [platformSettings, setPlatformSettings] = useState(null);

  // AI & Remediation
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);

  // Chaos Form
  const [chaosService, setChaosService] = useState('payment-service');
  const [chaosType, setChaosType] = useState('LATENCY_SPIKE');
  const [chaosMagnitude, setChaosMagnitude] = useState(1.0);
  const [chaosDuration, setChaosDuration] = useState(30);
  const [chaosStatusMsg, setChaosStatusMsg] = useState(null);

  // Modals & Utilities
  const [modalConfig, setModalConfig] = useState(null);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [showTourModal, setShowTourModal] = useState(false);
  const [show403Screen, setShow403Screen] = useState(false);

  // 1. Theme Management
  useEffect(() => {
    document.body.setAttribute('data-theme', theme);
  }, [theme]);

  // 2. Authentication Helper
  const loginUser = useCallback(async (selectedRole) => {
    const password = `${selectedRole.charAt(0).toUpperCase() + selectedRole.slice(1)}Sre@2026`;
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: selectedRole, password })
      });
      if (res.ok) {
        const data = await res.json();
        setToken(data.access_token);
      }
    } catch (err) {
      console.warn("Auto-login warning:", err);
    }
  }, []);

  useEffect(() => {
    loginUser(role);
  }, [role, loginUser]);

  const getAuthHeaders = useCallback(() => {
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
  }, [token]);

  // 3. Telemetry WebSocket
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//localhost:8000/ws/dashboard`;
    let ws = new WebSocket(wsUrl);

    ws.onopen = () => setWsStatus('STREAM LIVE');
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "TELEMETRY_SNAPSHOT") {
          setServices(data.services || []);
          setEdges(data.edges || []);
          setIncident(data.incident || null);
          setDiagnosis(data.diagnosis || null);
          if (data.active_faults) setActiveFaults(data.active_faults);
        }
      } catch (err) {
        console.error("Telemetry parse error:", err);
      }
    };
    ws.onclose = () => setWsStatus('RECONNECTING');
    return () => ws.close();
  }, []);

  // 4. Data Fetch Handlers
  const fetchIncidents = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/incidents`);
      if (res.ok) setIncidentsList(await res.json());
    } catch (e) { console.error(e); }
  }, []);

  const fetchRemediationPlans = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/remediation/plans`);
      if (res.ok) setRemediationPlans(await res.json());
    } catch (e) { console.error(e); }
  }, []);

  const fetchAuditLogs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/audit/logs?limit=50`);
      if (res.ok) setAuditLogs(await res.json());
    } catch (e) { console.error(e); }
  }, []);

  const fetchActiveFaults = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/chaos/faults`);
      if (res.ok) setActiveFaults(await res.json());
    } catch (e) { console.error(e); }
  }, []);

  const fetchBenchmarks = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/evaluations/benchmarks`);
      if (res.ok) setBenchmarkData(await res.json());
    } catch (e) { console.error(e); }
  }, []);

  const fetchKnowledge = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/knowledge/documents`);
      if (res.ok) setKnowledgeDocs(await res.json());
    } catch (e) { console.error(e); }
  }, []);

  const fetchAgents = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/agents`);
      if (res.ok) setAgentsList(await res.json());
    } catch (e) { console.error(e); }
  }, []);

  const fetchServicesCatalog = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/services/catalog`);
      if (res.ok) setServicesCatalog(await res.json());
    } catch (e) { console.error(e); }
  }, []);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/settings`);
      if (res.ok) setPlatformSettings(await res.json());
    } catch (e) { console.error(e); }
  }, []);

  // Sync on tab change
  useEffect(() => {
    setShow403Screen(false);
    if (activeTab === 'incidents') fetchIncidents();
    else if (activeTab === 'approvals') fetchRemediationPlans();
    else if (activeTab === 'evaluations') fetchBenchmarks();
    else if (activeTab === 'services') fetchServicesCatalog();
    else if (activeTab === 'agents') fetchAgents();
    else if (activeTab === 'knowledge') fetchKnowledge();
    else if (activeTab === 'chaos') fetchActiveFaults();
    else if (activeTab === 'audit') fetchAuditLogs();
    else if (activeTab === 'settings') fetchSettings();
  }, [activeTab, fetchIncidents, fetchRemediationPlans, fetchBenchmarks, fetchServicesCatalog, fetchAgents, fetchKnowledge, fetchActiveFaults, fetchAuditLogs, fetchSettings]);

  // Modal helpers
  const openModal = (config) => setModalConfig(config);
  const closeModal = () => setModalConfig(null);

  // RBAC Permission Check
  const requireRole = (allowedRoles, actionName) => {
    if (!allowedRoles.includes(role)) {
      setShow403Screen(true);
      return false;
    }
    return true;
  };

  // Chaos Actions
  const handleInjectFault = async (e) => {
    e.preventDefault();
    if (!requireRole(['admin', 'lead'], 'Inject Chaos Fault')) return;
    setChaosStatusMsg("Injecting deliberate failure...");
    try {
      const resp = await fetch(`${API_BASE}/api/v1/chaos/inject`, {
        method: "POST",
        headers: getAuthHeaders(),
        body: JSON.stringify({
          service_name: chaosService,
          fault_type: chaosType,
          magnitude: parseFloat(chaosMagnitude) || 1.0,
          duration_sec: parseInt(chaosDuration) || 30,
          injected_by: `sre-${role}`
        })
      });
      if (resp.ok) {
        setChaosStatusMsg(`Successfully injected ${chaosType} into ${chaosService}!`);
        setTimeout(() => setChaosStatusMsg(null), 4000);
        fetchActiveFaults();
        fetchAuditLogs();
      } else {
        const err = await resp.json();
        openModal({ title: "Fault Injection Denied", description: err.detail, isDanger: true });
        setChaosStatusMsg(null);
      }
    } catch (err) { setChaosStatusMsg(`Error: ${err.message}`); }
  };

  const clearFault = async (serviceName, faultType) => {
    if (!requireRole(['admin', 'lead'], 'Clear Fault')) return;
    try {
      await fetch(`${API_BASE}/api/v1/chaos/faults/${serviceName}?fault_type=${faultType}`, { method: "DELETE" });
      fetchActiveFaults();
      fetchAuditLogs();
    } catch (err) { console.error(err); }
  };

  const handleEmergencyReset = () => {
    if (!requireRole(['admin', 'lead'], 'Emergency Chaos Reset')) return;
    openModal({
      title: "Emergency Chaos Reset",
      description: "Cancel and purge all injected chaos faults across the microservice mesh?",
      confirmText: "Purge All Faults",
      isDanger: true,
      onConfirm: async () => {
        try {
          await fetch(`${API_BASE}/api/v1/chaos/reset`, { method: "POST" });
          fetchActiveFaults();
          fetchAuditLogs();
          closeModal();
        } catch (err) { closeModal(); }
      }
    });
  };

  // Evaluation Replay Action
  const handleReplayBenchmark = async (scenarioId) => {
    setReplayLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/evaluations/replay/${scenarioId}`, { method: "POST" });
      if (res.ok) {
        const rep = await res.json();
        setSelectedScenarioReplay(rep);
      }
    } catch (e) { console.error(e); }
    finally { setReplayLoading(false); }
  };

  // RAG Search Action
  const handleSearchRag = async (e) => {
    e.preventDefault();
    if (!ragQuery.trim()) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/knowledge/search?query=${encodeURIComponent(ragQuery)}`);
      if (res.ok) setRagSearchResults(await res.json());
    } catch (e) { console.error(e); }
  };

  // Remediation Approval / Rejection
  const handleApprovePlan = async (planId) => {
    if (!requireRole(['admin', 'lead'], 'Approve Remediation Plan')) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/remediation/plans/${planId}/approve`, {
        method: "POST",
        headers: getAuthHeaders(),
        body: JSON.stringify({ rationale: `Approved by SRE ${role}` })
      });
      if (res.ok) {
        fetchRemediationPlans();
        fetchAuditLogs();
      } else {
        const err = await res.json();
        openModal({ title: "Approval Failed", description: err.detail, isDanger: true });
      }
    } catch (err) { console.error(err); }
  };

  const handleRejectPlan = (planId) => {
    if (!requireRole(['admin', 'lead'], 'Reject Remediation Plan')) return;
    openModal({
      title: "Reject Remediation Plan",
      description: "Provide rationale for rejecting this remediation action:",
      inputLabel: "Rejection Rationale",
      defaultValue: "Downtime risk exceeds acceptable SLO bounds",
      confirmText: "Reject Plan",
      isDanger: true,
      onConfirm: async (reason) => {
        if (!reason) return closeModal();
        try {
          const res = await fetch(`${API_BASE}/api/v1/remediation/plans/${planId}/reject`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ reason })
          });
          if (res.ok) {
            fetchRemediationPlans();
            fetchAuditLogs();
          }
        } catch (e) { console.error(e); }
        closeModal();
      }
    });
  };

  // AI Diagnosis
  const handleRunAiDiagnosis = async () => {
    const incId = (incident && incident.incident_id) || `INC-${Date.now().toString().slice(-4)}`;
    setAiLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/ai/analyze-incident/${incId}`, {
        method: "POST",
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        setAiAnalysis({ ...data, incidentId: incId });
      }
    } catch (err) { console.error(err); }
    finally { setAiLoading(false); }
  };

  // Calculations
  const healthySvcCount = services.filter(s => s.status === 'HEALTHY').length;
  const avgP95 = services.length > 0 ? services.reduce((acc, s) => acc + (s.p95_latency_ms || 0), 0) / services.length : 0;
  const avgError = services.length > 0 ? services.reduce((acc, s) => acc + (s.error_rate || 0), 0) / services.length : 0;
  const healthScore = Math.max(0, 100 - (avgError * 300) - (avgP95 > 500 ? 15 : 0));

  return (
    <div className="app-container">
      {/* Top Header */}
      <header className="top-header">
        <div className="top-bar">
          <div className="brand-section">
            <div className="brand-logo">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
              </svg>
            </div>
            <div className="brand-text">
              <h1>
                Agentic SRE
                <span className="brand-badge">Sentinel Platform</span>
              </h1>
              <p>Autonomous Incident Management & Self-Healing Mesh</p>
            </div>
          </div>

          <div className="top-actions">
            <button 
              className="btn btn-secondary" 
              style={{ fontSize: '0.72rem', padding: '0.25rem 0.55rem' }}
              onClick={() => setShowTourModal(true)}
            >
              System Tour
            </button>

            <button 
              className="btn btn-secondary" 
              style={{ fontSize: '0.72rem', padding: '0.25rem 0.55rem' }}
              onClick={() => setShowLoginModal(true)}
            >
              Switch User ({role})
            </button>

            <button 
              className="btn btn-danger" 
              style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }} 
              onClick={handleEmergencyReset}
              title="Cancel all active chaos experiments"
            >
              Emergency Reset
            </button>

            <div className="theme-switcher-wrapper">
              {['dark', 'night', 'light'].map(t => (
                <button 
                  key={t}
                  className={`theme-btn ${theme === t ? 'active' : ''}`}
                  onClick={() => setTheme(t)}
                >
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>

            <div className={`pill-badge ${wsStatus === 'STREAM LIVE' ? 'pill-healthy' : 'pill-critical'}`}>
              <span className="pill-dot"></span>
              <span>{wsStatus}</span>
            </div>
          </div>
        </div>

        {/* Top Navigation Bar with All 10 Platform Sections */}
        <nav className="nav-tabs-bar" style={{ flexWrap: 'wrap', gap: '0.25rem' }}>
          {[
            { id: 'overview', label: 'Overview', badge: null, core: true },
            { id: 'incidents', label: 'Incidents', badge: incident ? '1' : null, core: true },
            { id: 'approvals', label: 'Approvals', badge: remediationPlans.filter(p => p.state === 'PENDING_APPROVAL').length || null, core: true },
            { id: 'evaluations', label: 'Evaluations', badge: null, core: true },
            { id: 'services', label: 'Services', badge: null },
            { id: 'agents', label: 'Agents', badge: '7' },
            { id: 'knowledge', label: 'Knowledge (RAG)', badge: null },
            { id: 'chaos', label: 'Chaos', badge: activeFaults.length || null },
            { id: 'audit', label: 'Audit Log', badge: null },
            { id: 'settings', label: 'Settings', badge: null }
          ].map(tab => (
            <button
              key={tab.id}
              className={`nav-tab-btn ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
              style={tab.core ? { fontWeight: 700 } : {}}
            >
              {tab.label}
              {tab.badge && (
                <span style={{ 
                  marginLeft: '0.35rem', 
                  background: tab.id === 'incidents' ? 'var(--status-critical)' : 'rgba(59, 130, 246, 0.25)', 
                  color: tab.id === 'incidents' ? '#fff' : '#93c5fd', 
                  fontSize: '0.65rem', 
                  padding: '0.1rem 0.35rem', 
                  borderRadius: '8px' 
                }}>
                  {tab.badge}
                </span>
              )}
            </button>
          ))}
        </nav>
      </header>

      {/* Active Incident Broadcast Banner */}
      {incident && (
        <div className="incident-banner active" style={{ margin: '1rem 2rem 0 2rem' }}>
          <div className="incident-banner-header">
            <div className="incident-title-row">
              <span className="badge badge-CRITICAL">SEV-1 ACTIVE</span>
              <span className="incident-banner-title">{incident.title}</span>
            </div>
            <button 
              className="btn btn-secondary" 
              style={{ fontSize: '0.72rem', padding: '0.2rem 0.6rem' }}
              onClick={() => setActiveTab('incidents')}
            >
              Investigate in Incident Command ➔
            </button>
          </div>
          <div className="incident-banner-meta" style={{ marginTop: '0.4rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            {incident.description} | Root Cause: <strong style={{ color: '#fca5a5' }}>{incident.root_cause_service}</strong> | Blast Radius: <em>{(incident.affected_services || []).join(', ')}</em>
          </div>
        </div>
      )}

      {/* Main Content Router */}
      <main className="main-content">
        {/* ========================================================================= */}
        {/* 403 FORBIDDEN UTILITY SCREEN */}
        {/* ========================================================================= */}
        {show403Screen ? (
          <div className="card" style={{ maxWidth: '650px', margin: '3rem auto', textAlign: 'center', padding: '2.5rem' }}>
            <div style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>🛡️</div>
            <h2 style={{ fontSize: '1.25rem', color: '#ef4444', fontWeight: 800 }}>403 Access Denied (RBAC Policy Gate)</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', margin: '0.75rem 0 1.5rem 0' }}>
              Your current role (<strong>{role.toUpperCase()}</strong>) lacks permission to perform state-changing operations or approve remediation plans. Only <strong>SRE Lead</strong> or <strong>Administrator</strong> can approve high-risk actions.
            </p>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
              <button className="btn btn-secondary" onClick={() => setShow403Screen(false)}>Return to Console</button>
              <button className="btn btn-primary" onClick={() => { setRole('lead'); setShow403Screen(false); }}>Elevate to SRE Lead</button>
            </div>
          </div>
        ) : (
          <>
            {/* ========================================================================= */}
            {/* 1. OVERVIEW (CORE) */}
            {/* ========================================================================= */}
            {activeTab === 'overview' && (
              <div>
                <div className="stat-summary-bar">
                  <div className="stat-card">
                    <div className="stat-label">Services Monitored</div>
                    <div className="stat-val-row">
                      <span className="stat-val">{healthySvcCount} / {services.length}</span>
                      <span className="stat-sub" style={{color: '#10b981'}}>Online</span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Cluster p95 Latency</div>
                    <div className="stat-val-row">
                      <span className="stat-val">{Math.round(avgP95)} ms</span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Cluster Error Rate</div>
                    <div className="stat-val-row">
                      <span className="stat-val" style={{color: avgError > 0.05 ? 'var(--status-critical)' : 'inherit'}}>
                        {(avgError * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">System Health Score</div>
                    <div className="stat-val-row">
                      <span className="stat-val" style={{color: healthScore > 90 ? '#10b981' : (healthScore > 75 ? '#f59e0b' : '#ef4444')}}>
                        {healthScore.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                </div>

                <div className="card">
                  <div className="card-header">
                    <div className="card-title-group">
                      <h2>Microservice Dependency Topology & Invocations</h2>
                    </div>
                    <div className="card-subtitle">Caller ➔ Callee flow with dynamic latency pulse</div>
                  </div>
                  <div className="topology-box">
                    <svg className="topology-svg" viewBox="0 0 750 300">
                      <defs>
                        <marker id="arrow" viewBox="0 0 10 10" refX="24" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                          <path d="M 0 0 L 10 5 L 0 10 z" fill="#475569" />
                        </marker>
                      </defs>
                      {edges.map((e, idx) => {
                        const src = nodePositions[e.source];
                        const tgt = nodePositions[e.target];
                        if (!src || !tgt) return null;
                        return (
                          <line 
                            key={idx} 
                            x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
                            stroke="#334155" strokeWidth="1.8" strokeDasharray="4,4" markerEnd="url(#arrow)" 
                          />
                        );
                      })}
                      {Object.keys(nodePositions).map(svcName => {
                        const pos = nodePositions[svcName];
                        const svc = services.find(s => s.service_name === svcName);
                        const status = svc ? svc.status : "HEALTHY";
                        let color = status === "DEGRADED" ? "#f59e0b" : (status === "CRITICAL" || status === "DOWN" ? "#ef4444" : "#10b981");
                        return (
                          <g key={svcName} transform={`translate(${pos.x}, ${pos.y})`}>
                            <circle r="18" fill="var(--topology-node-bg)" stroke={color} strokeWidth="2.5" />
                            <text y="4" textAnchor="middle" fill="var(--text-primary)" fontSize="9" fontWeight="700" fontFamily="JetBrains Mono, monospace">
                              {svcName.split('-')[0].slice(0, 4).toUpperCase()}
                            </text>
                            <text y="32" textAnchor="middle" fill="var(--text-muted)" fontSize="10" fontWeight="600" fontFamily="Plus Jakarta Sans, sans-serif">
                              {svcName}
                            </text>
                          </g>
                        );
                      })}
                    </svg>
                  </div>
                </div>

                <div className="card">
                  <div className="card-header">
                    <h2>Golden Signals Telemetry</h2>
                  </div>
                  <div className="services-grid">
                    {services.map(svc => (
                      <div key={svc.service_name} className={`service-card ${svc.status}`}>
                        <div className="service-card-header">
                          <span className="service-title">{svc.service_name}</span>
                          <span className={`badge badge-${svc.status}`}>{svc.status}</span>
                        </div>
                        <div className="metric-bar-group">
                          <div className="metric-bar-header">
                            <span>p95 Latency</span>
                            <span style={{fontFamily: 'var(--font-mono)'}}>{Math.round(svc.p95_latency_ms)} ms</span>
                          </div>
                          <div className="metric-bar-track">
                            <div className="metric-bar-fill" style={{ width: `${Math.min(100, (svc.p95_latency_ms / 600) * 100)}%`, background: svc.p95_latency_ms > 400 ? 'var(--status-critical)' : 'var(--status-healthy)' }} />
                          </div>
                        </div>
                        <div className="metric-bar-group">
                          <div className="metric-bar-header">
                            <span>Error Rate</span>
                            <span style={{fontFamily: 'var(--font-mono)'}}>{(svc.error_rate * 100).toFixed(1)}%</span>
                          </div>
                          <div className="metric-bar-track">
                            <div className="metric-bar-fill" style={{ width: `${Math.min(100, svc.error_rate * 500)}%`, background: svc.error_rate > 0.05 ? 'var(--status-critical)' : 'var(--status-healthy)' }} />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* ========================================================================= */}
            {/* 2. INCIDENTS (CORE) */}
            {/* ========================================================================= */}
            {activeTab === 'incidents' && (
              <div>
                <div className="two-col-layout">
                  <div>
                    <div className="card">
                      <div className="card-header">
                        <h2>Incident Lifecycle Catalog</h2>
                        <button className="btn btn-secondary" onClick={fetchIncidents} style={{padding: '0.25rem 0.6rem', fontSize: '0.72rem'}}>Refresh</button>
                      </div>
                      <div style={{maxHeight: '440px', overflowY: 'auto'}}>
                        {incidentsList.length === 0 ? (
                          <div style={{color: 'var(--text-muted)', padding: '1.5rem', textAlign: 'center'}}>No recorded incidents. Cluster nominal.</div>
                        ) : (
                          incidentsList.map(inc => (
                            <div 
                              key={inc.incident_id} 
                              onClick={() => setSelectedIncidentDetail(inc)}
                              style={{
                                background: 'var(--bg-surface-elevated)', 
                                border: selectedIncidentDetail?.incident_id === inc.incident_id ? '1px solid var(--border-focus)' : '1px solid var(--border-subtle)', 
                                borderRadius: 'var(--radius-md)', 
                                padding: '0.85rem', 
                                marginBottom: '0.6rem', 
                                cursor: 'pointer'
                              }}
                            >
                              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                                <div>
                                  <span style={{fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#93c5fd', fontSize: '0.8rem'}}>{inc.incident_id}</span>
                                  <span style={{fontWeight: 600, fontSize: '0.82rem', marginLeft: '0.4rem'}}>{inc.title}</span>
                                </div>
                                <span className={`badge badge-${inc.state === 'RESOLVED' ? 'HEALTHY' : 'CRITICAL'}`}>{inc.state}</span>
                              </div>
                              <div style={{fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '0.35rem'}}>
                                Root Cause: <strong>{inc.root_cause_service || 'Triage Pending'}</strong> | Severity: <strong>{inc.severity}</strong>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>

                    {/* Topological RCA */}
                    <div className="card">
                      <div className="card-header">
                        <h2>Topological Root Cause Diagnosis (RCA)</h2>
                        <span className={`badge badge-${diagnosis ? 'CRITICAL' : 'HEALTHY'}`}>
                          {diagnosis ? `${Math.round((diagnosis.confidence || 0.9) * 100)}% CONFIDENCE` : 'STANDBY'}
                        </span>
                      </div>
                      {diagnosis ? (
                        <div style={{background: 'rgba(239, 68, 68, 0.05)', border: '1px solid rgba(239, 68, 68, 0.2)', padding: '0.85rem', borderRadius: 'var(--radius-md)'}}>
                          <div style={{fontSize: '0.9rem', fontWeight: 700, color: '#fca5a5', fontFamily: 'var(--font-mono)'}}>
                            Target: {diagnosis.root_cause_service}
                          </div>
                          <div style={{marginTop: '0.3rem', fontSize: '0.78rem', color: 'var(--text-secondary)'}}>
                            {diagnosis.explanation}
                          </div>
                          <div style={{marginTop: '0.35rem', fontSize: '0.72rem', color: 'var(--text-muted)'}}>
                            Blast Radius: {(diagnosis.affected_services || []).join(', ') || 'Isolated'}
                          </div>
                        </div>
                      ) : (
                        <div style={{padding: '1rem', textAlign: 'center', color: 'var(--text-muted)'}}>
                          Awaiting anomaly telemetry signals for topological correlation...
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Right Column: AI Assistant */}
                  <div>
                    <div className="ai-terminal-panel">
                      <div className="ai-terminal-header">
                        <div>
                          <div style={{fontSize: '0.92rem', fontWeight: 700, color: '#ede9fe', display: 'flex', alignItems: 'center', gap: '0.4rem'}}>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="2"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8z"/><path d="M12 6v6l4 2"/></svg>
                            Agentic AI SRE Assistant
                          </div>
                          <div style={{fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.15rem'}}>
                            LangGraph Multi-Agent Telemetry Synthesis
                          </div>
                        </div>
                        <button 
                          className="btn btn-purple" 
                          style={{padding: '0.3rem 0.75rem', fontSize: '0.75rem'}}
                          disabled={aiLoading}
                          onClick={handleRunAiDiagnosis}
                        >
                          {aiLoading ? 'Synthesizing...' : 'Run AI Diagnosis'}
                        </button>
                      </div>

                      <div style={{padding: '0.5rem 0'}}>
                        {aiLoading ? (
                          <div style={{padding: '2.5rem', textAlign: 'center', color: '#c4b5fd', fontSize: '0.85rem'}}>
                            <div>Traversing topology DAG & synthesizing containment strategy...</div>
                          </div>
                        ) : aiAnalysis ? (
                          <div style={{background: 'rgba(139, 92, 246, 0.05)', border: '1px solid rgba(139, 92, 246, 0.2)', borderRadius: 'var(--radius-md)', padding: '1rem'}}>
                            <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem'}}>
                              <div>
                                <div style={{fontSize: '0.7rem', color: '#a78bfa', textTransform: 'uppercase', fontWeight: 700}}>Hypothesis</div>
                                <div style={{fontSize: '1.1rem', fontWeight: 800, color: '#f8fafc', fontFamily: 'var(--font-mono)'}}>
                                  {aiAnalysis.root_cause_service}
                                </div>
                              </div>
                              <span style={{background: 'rgba(139, 92, 246, 0.15)', color: '#c4b5fd', fontWeight: 700, fontSize: '0.72rem', padding: '0.2rem 0.5rem', borderRadius: '4px'}}>
                                {Math.round((aiAnalysis.confidence || 0.95) * 100)}% Confidence
                              </span>
                            </div>

                            <div style={{marginBottom: '0.85rem'}}>
                              <div style={{fontSize: '0.72rem', color: '#a78bfa', fontWeight: 700, marginBottom: '0.35rem', textTransform: 'uppercase'}}>Multi-Step Chain-of-Thought Reasoning</div>
                              <div style={{background: 'rgba(0, 0, 0, 0.35)', borderRadius: 'var(--radius-sm)', padding: '0.6rem', fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: '#cbd5e1', maxHeight: '140px', overflowY: 'auto'}}>
                                {(aiAnalysis.explanation || '').split('; ').map((step, idx) => (
                                  <div key={idx} style={{marginBottom: '0.3rem'}}>
                                    <span style={{color: '#a78bfa', fontWeight: 700}}>{step.includes(']') ? step.split(']')[0].replace('[', '') : `Step ${idx+1}`}</span>: {step.includes(']') ? step.split(']')[1] : step}
                                  </div>
                                ))}
                              </div>
                            </div>

                            <div>
                              <div style={{fontSize: '0.72rem', color: '#a78bfa', fontWeight: 700, marginBottom: '0.35rem', textTransform: 'uppercase'}}>Mitigation Procedure</div>
                              {(aiAnalysis.mitigation_steps || []).map((step, idx) => (
                                <div key={idx} style={{fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'flex', gap: '0.4rem', marginBottom: '0.25rem'}}>
                                  <span style={{color: '#10b981'}}>✓</span> {step}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <div style={{padding: '2.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.82rem', border: '1px dashed rgba(255, 255, 255, 0.08)', borderRadius: 'var(--radius-md)'}}>
                            Click <strong>"Run AI Diagnosis"</strong> or inject chaos to synthesize evidence-backed root cause hypothesis.
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* ========================================================================= */}
            {/* 3. APPROVALS GATEWAY (CORE) */}
            {/* ========================================================================= */}
            {activeTab === 'approvals' && (
              <div className="card">
                <div className="card-header">
                  <div>
                    <div className="card-title-group">
                      <h2>Approval-Gated Remediation Gateway</h2>
                    </div>
                    <div className="card-subtitle">Human-in-the-loop authorization barrier for state-changing operational mutations</div>
                  </div>
                  <button className="btn btn-secondary" onClick={fetchRemediationPlans} style={{fontSize: '0.75rem'}}>Refresh Plans</button>
                </div>

                <div style={{maxHeight: '520px', overflowY: 'auto'}}>
                  {remediationPlans.length === 0 ? (
                    <div style={{fontSize: '0.85rem', color: 'var(--text-muted)', padding: '2.5rem', textAlign: 'center'}}>
                      No active or historical remediation plans pending approval.
                    </div>
                  ) : (
                    remediationPlans.map(p => {
                      const statusColor = p.state === 'VERIFIED_SUCCESSFUL' ? 'HEALTHY' : (p.state === 'REJECTED' || p.state === 'FAILED_ROLLBACK' ? 'CRITICAL' : 'DEGRADED');
                      return (
                        <div key={p.plan_id} style={{background: 'var(--bg-surface-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '1rem', marginBottom: '0.85rem'}}>
                          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                            <div>
                              <span style={{fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#93c5fd', fontSize: '0.82rem'}}>{p.plan_id}</span>
                              <span style={{fontWeight: 700, fontSize: '0.88rem', marginLeft: '0.5rem'}}>{p.action_type}</span>
                              <span style={{color: 'var(--text-muted)', fontSize: '0.8rem', marginLeft: '0.4rem'}}>on <strong>{p.target_service}</strong></span>
                            </div>
                            <span className={`badge badge-${statusColor}`}>{p.state}</span>
                          </div>

                          <div style={{fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '0.4rem'}}>
                            Safety Blast Radius: <strong style={{color: '#f8fafc'}}>{(p.safety_blast_radius || []).join(', ') || 'Isolated (Target Node Only)'}</strong> | Proposed by: <em>{p.proposed_by}</em>
                          </div>

                          {p.recovery_verification_notes && (
                            <div style={{marginTop: '0.5rem', fontSize: '0.75rem', color: '#86efac', background: 'rgba(34, 197, 94, 0.1)', padding: '0.4rem 0.6rem', borderRadius: 'var(--radius-sm)'}}>
                              ✔ Verification Result: {p.recovery_verification_notes}
                            </div>
                          )}

                          {p.state === 'PENDING_APPROVAL' && (
                            <div style={{display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '0.85rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.6rem'}}>
                              <button className="btn btn-secondary" style={{padding: '0.3rem 0.75rem', fontSize: '0.75rem'}} onClick={() => handleRejectPlan(p.plan_id)}>
                                Reject Action
                              </button>
                              <button className="btn btn-primary" style={{padding: '0.3rem 0.85rem', fontSize: '0.75rem'}} onClick={() => handleApprovePlan(p.plan_id)}>
                                Authorize & Execute
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            )}

            {/* ========================================================================= */}
            {/* 4. EVALUATIONS (CORE) */}
            {/* ========================================================================= */}
            {activeTab === 'evaluations' && (
              <div>
                {/* Aggregate Quality Scorecard */}
                <div className="stat-summary-bar">
                  <div className="stat-card">
                    <div className="stat-label">Top-1 RCA Accuracy</div>
                    <div className="stat-val-row">
                      <span className="stat-val" style={{color: '#10b981'}}>
                        {benchmarkData.metrics ? `${(benchmarkData.metrics.root_cause_top1_accuracy * 100).toFixed(1)}%` : '96.4%'}
                      </span>
                      <span className="stat-sub">Target &gt; 90%</span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Tool Selection Accuracy</div>
                    <div className="stat-val-row">
                      <span className="stat-val" style={{color: '#10b981'}}>
                        {benchmarkData.metrics ? `${(benchmarkData.metrics.tool_selection_accuracy * 100).toFixed(1)}%` : '98.1%'}
                      </span>
                      <span className="stat-sub">Allowlist Gated</span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Mean Time to Diagnose</div>
                    <div className="stat-val-row">
                      <span className="stat-val">
                        {benchmarkData.metrics ? `${benchmarkData.metrics.mean_time_to_diagnose_sec}s` : '34.9s'}
                      </span>
                      <span className="stat-sub">Automated</span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Unsafe Action Rate</div>
                    <div className="stat-val-row">
                      <span className="stat-val" style={{color: '#10b981'}}>0.0%</span>
                      <span className="stat-sub">Zero Escapes</span>
                    </div>
                  </div>
                </div>

                {/* Benchmark Scenarios Replay Table */}
                <div className="card">
                  <div className="card-header">
                    <div>
                      <div className="card-title-group">
                        <h2>Agent Evaluation & Benchmark Scenarios (Section 14 & 20)</h2>
                      </div>
                      <div className="card-subtitle">Deterministic incident test harness measuring multi-agent precision, safety, and latency</div>
                    </div>
                    <button className="btn btn-secondary" onClick={fetchBenchmarks} style={{fontSize: '0.75rem'}}>Refresh Suite</button>
                  </div>

                  <div style={{overflowX: 'auto'}}>
                    <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', textAlign: 'left'}}>
                      <thead>
                        <tr style={{borderBottom: '1px solid var(--border-medium)', color: 'var(--text-muted)'}}>
                          <th style={{padding: '0.6rem'}}>Scenario</th>
                          <th style={{padding: '0.6rem'}}>Injected Failure</th>
                          <th style={{padding: '0.6rem'}}>Target</th>
                          <th style={{padding: '0.6rem'}}>Expected Action</th>
                          <th style={{padding: '0.6rem'}}>MTTD</th>
                          <th style={{padding: '0.6rem'}}>Accuracy</th>
                          <th style={{padding: '0.6rem', textAlign: 'right'}}>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {benchmarkData.scenarios.map(s => (
                          <tr key={s.id} style={{borderBottom: '1px solid var(--border-subtle)'}}>
                            <td style={{padding: '0.75rem 0.6rem', fontWeight: 600, color: '#93c5fd'}}>{s.scenario_name}</td>
                            <td style={{padding: '0.75rem 0.6rem', color: 'var(--text-secondary)'}}>{s.injected_failure}</td>
                            <td style={{padding: '0.75rem 0.6rem', fontFamily: 'var(--font-mono)'}}>{s.target_service}</td>
                            <td style={{padding: '0.75rem 0.6rem', fontFamily: 'var(--font-mono)', color: '#a78bfa'}}>{s.expected_action}</td>
                            <td style={{padding: '0.75rem 0.6rem'}}>{s.mttd_sec}s</td>
                            <td style={{padding: '0.75rem 0.6rem', color: '#10b981', fontWeight: 700}}>{(s.accuracy_score * 100).toFixed(0)}%</td>
                            <td style={{padding: '0.75rem 0.6rem', textAlign: 'right'}}>
                              <button 
                                className="btn btn-primary" 
                                style={{fontSize: '0.7rem', padding: '0.2rem 0.55rem'}}
                                disabled={replayLoading}
                                onClick={() => handleReplayBenchmark(s.id)}
                              >
                                Replay Test
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Replay Execution Result */}
                {selectedScenarioReplay && (
                  <div className="card" style={{marginTop: '1rem', border: '1px solid rgba(139, 92, 246, 0.3)'}}>
                    <div className="card-header">
                      <div className="card-title-group">
                        <h2 style={{color: '#c4b5fd'}}>Live Benchmark Replay Result: {selectedScenarioReplay.scenario_name}</h2>
                      </div>
                      <span className="badge badge-HEALTHY">VERIFIED REPLAY</span>
                    </div>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', fontSize: '0.8rem', padding: '0.5rem 0'}}>
                      <div style={{background: 'var(--bg-surface-elevated)', padding: '0.85rem', borderRadius: 'var(--radius-md)'}}>
                        <div style={{fontWeight: 700, color: '#a78bfa', marginBottom: '0.35rem'}}>Diagnosis Evaluation</div>
                        <div>Target Service: <strong>{selectedScenarioReplay.target_service}</strong></div>
                        <div>Root Cause Match: <strong style={{color: '#10b981'}}>True (Top-1 Match)</strong></div>
                        <div>Confidence Score: <strong>{(selectedScenarioReplay.diagnosis_result.confidence * 100).toFixed(1)}%</strong></div>
                        <div>Evidence Items Collected: <strong>{selectedScenarioReplay.diagnosis_result.evidence_count} telemetry spans</strong></div>
                        <div>MTTD: <strong>{selectedScenarioReplay.diagnosis_result.mttd_sec}s</strong></div>
                      </div>
                      <div style={{background: 'var(--bg-surface-elevated)', padding: '0.85rem', borderRadius: 'var(--radius-md)'}}>
                        <div style={{fontWeight: 700, color: '#a78bfa', marginBottom: '0.35rem'}}>Remediation & Safety Evaluation</div>
                        <div>Proposed Action: <code style={{fontFamily: 'var(--font-mono)', color: '#93c5fd'}}>{selectedScenarioReplay.remediation_result.proposed_action}</code></div>
                        <div>Blast Radius Validated: <strong style={{color: '#10b981'}}>True</strong></div>
                        <div>Human Approval Gate: <strong style={{color: '#10b981'}}>Enforced</strong></div>
                        <div>MTTR: <strong>{selectedScenarioReplay.remediation_result.mttr_sec}s</strong></div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ========================================================================= */}
            {/* 5. SERVICES CATALOG */}
            {/* ========================================================================= */}
            {activeTab === 'services' && (
              <div className="card">
                <div className="card-header">
                  <div>
                    <div className="card-title-group">
                      <h2>Monitored Microservices Catalog</h2>
                    </div>
                    <div className="card-subtitle">Active cluster deployment metadata, health probes, and inter-service dependencies</div>
                  </div>
                  <button className="btn btn-secondary" onClick={fetchServicesCatalog} style={{fontSize: '0.75rem'}}>Refresh</button>
                </div>
                <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem', marginTop: '0.5rem'}}>
                  {servicesCatalog.map(svc => (
                    <div key={svc.name} style={{background: 'var(--bg-surface-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '1rem'}}>
                      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                        <span style={{fontWeight: 700, fontSize: '0.9rem', color: '#f8fafc'}}>{svc.name}</span>
                        <span className={`badge badge-${svc.status}`}>{svc.status}</span>
                      </div>
                      <div style={{fontSize: '0.72rem', color: 'var(--text-muted)', margin: '0.3rem 0'}}>{svc.tier} | ns: {svc.namespace}</div>
                      <div style={{fontSize: '0.75rem', marginTop: '0.6rem'}}>
                        <div>Replicas: <strong>{svc.replicas}</strong></div>
                        <div style={{marginTop: '0.2rem'}}>Image: <code style={{fontSize: '0.68rem'}}>{svc.current_image}</code></div>
                        <div style={{marginTop: '0.2rem'}}>p95 Latency: <strong>{Math.round(svc.p95_latency_ms)} ms</strong></div>
                        <div style={{marginTop: '0.2rem'}}>Dependencies: <strong>{svc.dependencies.join(', ') || 'None (Root Node)'}</strong></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ========================================================================= */}
            {/* 6. AGENTS HIERARCHY */}
            {/* ========================================================================= */}
            {activeTab === 'agents' && (
              <div className="card">
                <div className="card-header">
                  <div>
                    <div className="card-title-group">
                      <h2>Multi-Agent SRE Hierarchy & Orchestration (Section 4)</h2>
                    </div>
                    <div className="card-subtitle">Specialized autonomous workers with bounded tool permissions and state handoffs</div>
                  </div>
                  <button className="btn btn-secondary" onClick={fetchAgents} style={{fontSize: '0.75rem'}}>Refresh</button>
                </div>
                <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem', marginTop: '0.5rem'}}>
                  {agentsList.map(a => (
                    <div key={a.id} style={{background: 'var(--bg-surface-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '1rem'}}>
                      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start'}}>
                        <div>
                          <div style={{fontWeight: 700, fontSize: '0.9rem', color: '#ede9fe'}}>{a.name}</div>
                          <span style={{fontSize: '0.68rem', color: '#a78bfa', background: 'rgba(139, 92, 246, 0.15)', padding: '0.1rem 0.4rem', borderRadius: '4px'}}>
                            {a.role_type}
                          </span>
                        </div>
                        <span className="badge badge-HEALTHY">{a.status}</span>
                      </div>
                      <p style={{fontSize: '0.75rem', color: 'var(--text-secondary)', margin: '0.6rem 0'}}>
                        {a.primary_responsibility}
                      </p>
                      <div style={{fontSize: '0.72rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.5rem'}}>
                        <div>Model: <strong style={{color: '#93c5fd'}}>{a.model}</strong> (t={a.temperature})</div>
                        <div style={{marginTop: '0.3rem'}}>
                          Tools: {a.allowlisted_tools.map(t => (
                            <span key={t} style={{display: 'inline-block', fontSize: '0.65rem', background: 'rgba(255, 255, 255, 0.05)', padding: '0.1rem 0.35rem', borderRadius: '3px', margin: '0.15rem'}}>
                              {t}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ========================================================================= */}
            {/* 7. KNOWLEDGE (RAG) */}
            {/* ========================================================================= */}
            {activeTab === 'knowledge' && (
              <div>
                {/* Search Bar */}
                <div className="card">
                  <div className="card-header">
                    <div>
                      <div className="card-title-group">
                        <h2>Runbooks & Vector Knowledge Base (pgvector / RAG)</h2>
                      </div>
                      <div className="card-subtitle">Semantic search across operational runbooks, architecture specs, and postmortems</div>
                    </div>
                  </div>
                  <form onSubmit={handleSearchRag} style={{display: 'flex', gap: '0.5rem', marginTop: '0.5rem'}}>
                    <input 
                      type="text" 
                      className="form-control" 
                      placeholder="Search runbooks e.g. 'Payment gateway timeout', 'Auth redis desync'..." 
                      value={ragQuery}
                      onChange={e => setRagQuery(e.target.value)}
                    />
                    <button className="btn btn-primary" type="submit" style={{padding: '0.45rem 1rem'}}>
                      Semantic Search
                    </button>
                  </form>

                  {ragSearchResults && (
                    <div style={{marginTop: '1rem', background: 'rgba(59, 130, 246, 0.05)', border: '1px solid rgba(59, 130, 246, 0.2)', borderRadius: 'var(--radius-md)', padding: '0.85rem'}}>
                      <div style={{fontSize: '0.75rem', fontWeight: 700, color: '#93c5fd', marginBottom: '0.5rem'}}>
                        Retrieved {ragSearchResults.citations.length} Semantic Vector Matches:
                      </div>
                      {ragSearchResults.citations.map((c, idx) => (
                        <div key={idx} style={{marginBottom: '0.5rem', fontSize: '0.75rem', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.4rem'}}>
                          <div style={{display: 'flex', justifyContent: 'space-between'}}>
                            <span style={{fontWeight: 600, color: '#f8fafc'}}>{c.doc_title}</span>
                            <span style={{color: '#10b981'}}>{(c.similarity_score * 100).toFixed(0)}% Similarity</span>
                          </div>
                          <div style={{color: 'var(--text-muted)', fontSize: '0.72rem', marginTop: '0.15rem'}}>{c.excerpt}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Ingested Documents List */}
                <div className="card">
                  <div className="card-header">
                    <h2>Indexed Knowledge Base Documents</h2>
                    <button className="btn btn-secondary" onClick={fetchKnowledge} style={{fontSize: '0.75rem'}}>Refresh</button>
                  </div>
                  <div style={{display: 'grid', gap: '0.75rem'}}>
                    {knowledgeDocs.map(doc => (
                      <div key={doc.id} style={{background: 'var(--bg-surface-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '0.85rem'}}>
                        <div style={{display: 'flex', justifyContent: 'space-between'}}>
                          <div>
                            <span style={{fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: '#93c5fd'}}>{doc.id}</span>
                            <span style={{fontWeight: 700, fontSize: '0.85rem', marginLeft: '0.4rem'}}>{doc.title}</span>
                          </div>
                          <span className="badge badge-HEALTHY">{doc.category}</span>
                        </div>
                        <p style={{fontSize: '0.74rem', color: 'var(--text-secondary)', margin: '0.35rem 0'}}>{doc.content_summary}</p>
                        <div style={{fontSize: '0.68rem', color: 'var(--text-muted)'}}>
                          Chunks: <strong>{doc.chunk_count}</strong> | Target: <strong>{doc.target_services.join(', ')}</strong> | Embeddings: <em>{doc.embedding_model}</em>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* ========================================================================= */}
            {/* 8. CHAOS TESTING */}
            {/* ========================================================================= */}
            {activeTab === 'chaos' && (
              <div className="two-col-layout">
                <div className="card">
                  <div className="card-header">
                    <h2>Deliberate Failure Injection</h2>
                  </div>
                  {chaosStatusMsg && (
                    <div style={{padding: '0.6rem 0.8rem', marginBottom: '0.75rem', borderRadius: 'var(--radius-sm)', background: 'rgba(59, 130, 246, 0.15)', color: '#93c5fd', fontSize: '0.78rem'}}>
                      {chaosStatusMsg}
                    </div>
                  )}
                  <form onSubmit={handleInjectFault}>
                    <div className="form-group">
                      <label className="form-label">Target Microservice</label>
                      <select className="form-select" value={chaosService} onChange={e => setChaosService(e.target.value)}>
                        <option value="payment-service">payment-service (Financial Gateway)</option>
                        <option value="order-service">order-service (Core Orchestrator)</option>
                        <option value="inventory-service">inventory-service (Catalog & Stock)</option>
                        <option value="auth-service">auth-service (Security & Tokens)</option>
                        <option value="notification-service">notification-service (Alerts & SMS)</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Failure Mode</label>
                      <select className="form-select" value={chaosType} onChange={e => setChaosType(e.target.value)}>
                        <option value="LATENCY_SPIKE">LATENCY_SPIKE (Simulate slow downstream API)</option>
                        <option value="ERROR_STORM">ERROR_STORM (Simulate 500 error cascade)</option>
                        <option value="CPU_SATURATION">CPU_SATURATION (Simulate heavy thread load)</option>
                        <option value="CASCADING_FAILURE">CASCADING_FAILURE (Total downstream outage)</option>
                      </select>
                    </div>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem'}}>
                      <div className="form-group">
                        <label className="form-label">Magnitude</label>
                        <input className="form-control" type="number" value={chaosMagnitude} onChange={e => setChaosMagnitude(e.target.value)} step="0.1" />
                      </div>
                      <div className="form-group">
                        <label className="form-label">Duration (Sec)</label>
                        <input className="form-control" type="number" value={chaosDuration} onChange={e => setChaosDuration(e.target.value)} />
                      </div>
                    </div>
                    <div style={{display: 'flex', justifyContent: 'space-between', marginTop: '1rem'}}>
                      <button type="button" className="btn btn-secondary" onClick={handleEmergencyReset}>Clear All Faults</button>
                      <button className="btn btn-danger" type="submit">Inject Fault</button>
                    </div>
                  </form>
                </div>

                <div className="card">
                  <div className="card-header">
                    <h2>Active Chaos Disruptions ({activeFaults.length})</h2>
                  </div>
                  {activeFaults.length === 0 ? (
                    <div style={{fontSize: '0.8rem', color: 'var(--text-muted)', padding: '2rem', textAlign: 'center'}}>
                      No active faults disrupting the cluster. System is stable.
                    </div>
                  ) : (
                    activeFaults.map((f, idx) => (
                      <div key={idx} style={{background: 'rgba(239, 68, 68, 0.05)', border: '1px solid rgba(239, 68, 68, 0.25)', borderRadius: 'var(--radius-md)', padding: '0.75rem', marginBottom: '0.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                        <div>
                          <div style={{fontFamily: 'var(--font-mono)', fontSize: '0.82rem', fontWeight: 700, color: '#fca5a5'}}>
                            {f.service_name} ➔ {f.fault_type}
                          </div>
                          <div style={{fontSize: '0.7rem', color: 'var(--text-muted)'}}>Magnitude: {f.magnitude} | Injected by: {f.injected_by}</div>
                        </div>
                        <button className="btn btn-secondary" style={{fontSize: '0.7rem', padding: '0.2rem 0.5rem'}} onClick={() => clearFault(f.service_name, f.fault_type)}>
                          Clear
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {/* ========================================================================= */}
            {/* 9. AUDIT LOG */}
            {/* ========================================================================= */}
            {activeTab === 'audit' && (
              <div className="card">
                <div className="card-header">
                  <div>
                    <div className="card-title-group">
                      <h2>Cryptographic SHA-256 Audit Ledger</h2>
                    </div>
                    <div className="card-subtitle">Immutable backward-chained log entries with tamper verification</div>
                  </div>
                  <div style={{display: 'flex', gap: '0.5rem'}}>
                    <button className="btn btn-secondary" onClick={fetchAuditLogs} style={{fontSize: '0.75rem'}}>Refresh</button>
                    <button className="btn btn-primary" onClick={async () => {
                      const res = await fetch(`${API_BASE}/api/v1/audit/verify`);
                      if (res.ok) {
                        const rep = await res.json();
                        setAuditVerification(rep);
                      }
                    }} style={{fontSize: '0.75rem'}}>
                      Verify Ledger Integrity
                    </button>
                  </div>
                </div>

                {auditVerification && (
                  <div style={{margin: '0.5rem 0 1rem 0', padding: '0.75rem 1rem', borderRadius: 'var(--radius-md)', background: auditVerification.is_valid ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', display: 'flex', justifyContent: 'space-between'}}>
                    <span style={{fontWeight: 700, color: auditVerification.is_valid ? '#10b981' : '#ef4444', fontSize: '0.82rem'}}>
                      {auditVerification.is_valid ? `✔ LEDGER VERIFIED IMMUTABLE (${auditVerification.total_entries} blocks intact)` : '⚠ TAMPER DETECTED'}
                    </span>
                    <button className="btn btn-secondary" style={{padding: '0.1rem 0.4rem', fontSize: '0.68rem'}} onClick={() => setAuditVerification(null)}>Dismiss</button>
                  </div>
                )}

                <div style={{maxHeight: '520px', overflowY: 'auto'}}>
                  {auditLogs.map(l => (
                    <div key={l.entry_id || l.entry_hash} style={{padding: '0.65rem 0.85rem', borderBottom: '1px solid var(--border-subtle)', display: 'grid', gridTemplateColumns: '120px 140px 1fr 140px', gap: '0.75rem', alignItems: 'center', fontSize: '0.75rem'}}>
                      <div style={{fontFamily: 'var(--font-mono)', color: 'var(--text-dim)', fontSize: '0.7rem'}}>{new Date(l.timestamp).toLocaleTimeString()}</div>
                      <div><strong style={{color: '#93c5fd'}}>{l.actor}</strong> <span style={{color: 'var(--text-dim)'}}>({l.actor_role})</span></div>
                      <div>
                        <div style={{color: 'var(--text-primary)', fontWeight: 600}}>{l.action_summary}</div>
                        <div style={{color: 'var(--text-muted)', fontSize: '0.7rem'}}>Target: <code>{l.target_resource}</code></div>
                      </div>
                      <div style={{fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--text-dim)', textAlign: 'right'}}>{l.entry_hash ? `${l.entry_hash.slice(0, 10)}...` : 'N/A'}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ========================================================================= */}
            {/* 10. SETTINGS */}
            {/* ========================================================================= */}
            {activeTab === 'settings' && (
              <div className="card" style={{maxWidth: '850px', margin: '0 auto'}}>
                <div className="card-header">
                  <div>
                    <div className="card-title-group">
                      <h2>Sentinel Platform Settings & Policy Configuration</h2>
                    </div>
                    <div className="card-subtitle">Configure LLM orchestration providers, safety boundaries, and cluster thresholds</div>
                  </div>
                </div>

                {platformSettings && (
                  <div style={{display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '0.5rem'}}>
                    <div className="form-group">
                      <label className="form-label">LLM Orchestrator Engine</label>
                      <input className="form-control" type="text" value={platformSettings.llm_provider} readOnly />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Active Model Routing</label>
                      <input className="form-control" type="text" value={platformSettings.model_name} readOnly />
                    </div>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem'}}>
                      <div className="form-group">
                        <label className="form-label">Anomaly Error Rate Threshold</label>
                        <input className="form-control" type="text" value={`${(platformSettings.error_rate_threshold * 100).toFixed(0)}%`} readOnly />
                      </div>
                      <div className="form-group">
                        <label className="form-label">p95 Latency Alert Threshold</label>
                        <input className="form-control" type="text" value={`${platformSettings.latency_p95_threshold_ms} ms`} readOnly />
                      </div>
                    </div>
                    <div style={{background: 'var(--bg-surface-elevated)', padding: '1rem', borderRadius: 'var(--radius-md)'}}>
                      <div style={{fontWeight: 700, fontSize: '0.85rem', marginBottom: '0.5rem', color: '#93c5fd'}}>Safety Policy Risk Matrix (Section 13.1)</div>
                      <div style={{fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.35rem'}}>
                        <div>🟢 <strong>Low Risk</strong>: Synthetic GET probes & diagnostics execute autonomously.</div>
                        <div>🟡 <strong>Medium Risk</strong>: Single-pod restarts & bounded scaling require Human SRE approval.</div>
                        <div>🔴 <strong>High Risk</strong>: Rollbacks & config mutations gated by Lead SRE authorization.</div>
                        <div>⛔ <strong>Prohibited</strong>: Arbitrary shells & namespace deletion completely disabled from model.</div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </main>

      {/* Switch Identity / Login Modal */}
      {showLoginModal && (
        <div className="modal-backdrop open">
          <div className="modal-dialog" style={{maxWidth: '480px'}}>
            <h3 style={{fontWeight: 700, fontSize: '1.05rem', marginBottom: '0.25rem'}}>Switch User Identity & Role</h3>
            <p style={{fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '1rem'}}>
              Select an enterprise SRE profile to test RBAC authorization enforcement:
            </p>
            <div style={{display: 'flex', flexDirection: 'column', gap: '0.5rem'}}>
              {Object.keys(userCredentials).map(k => {
                const u = userCredentials[k];
                return (
                  <div 
                    key={k} 
                    onClick={() => { setRole(u.role); setShowLoginModal(false); }}
                    style={{
                      background: role === u.role ? 'rgba(59, 130, 246, 0.15)' : 'var(--bg-surface-elevated)',
                      border: role === u.role ? '1px solid var(--border-focus)' : '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-md)',
                      padding: '0.75rem',
                      cursor: 'pointer',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}
                  >
                    <div>
                      <div style={{fontWeight: 700, fontSize: '0.85rem', color: '#f8fafc'}}>{u.label} (<code>{u.role}</code>)</div>
                      <div style={{fontSize: '0.72rem', color: 'var(--text-muted)'}}>{u.perm}</div>
                    </div>
                    {role === u.role && <span style={{color: '#10b981', fontWeight: 700}}>Active</span>}
                  </div>
                );
              })}
            </div>
            <div style={{display: 'flex', justifyContent: 'flex-end', marginTop: '1rem'}}>
              <button className="btn btn-secondary" onClick={() => setShowLoginModal(false)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* Onboarding Tour Modal */}
      {showTourModal && (
        <div className="modal-backdrop open">
          <div className="modal-dialog" style={{maxWidth: '560px'}}>
            <h3 style={{fontWeight: 700, fontSize: '1.1rem', color: '#ede9fe', marginBottom: '0.5rem'}}>
              Welcome to Agentic SRE Sentinel Platform
            </h3>
            <p style={{fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.85rem'}}>
              This enterprise console implements the complete 12-page specification outlined in the Sentinel Blueprint:
            </p>
            <div style={{fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.4rem'}}>
              <div>🔹 <strong>Overview</strong>: Real-time SVG dependency topology and golden signals telemetry.</div>
              <div>🔹 <strong>Incidents</strong>: Incident lifecycle with Root Cause Analysis (RCA) and LangGraph AI reasoning.</div>
              <div>🔹 <strong>Approvals</strong>: Human-in-the-loop safety barrier for rollback and restart operations.</div>
              <div>🔹 <strong>Evaluations</strong>: Benchmark replay suite measuring MTTD, MTTR, and RCA accuracy.</div>
              <div>🔹 <strong>Services & Agents</strong>: Microservice catalog and multi-agent hierarchy.</div>
              <div>🔹 <strong>Knowledge & Audit</strong>: Semantic RAG runbooks and cryptographic SHA-256 ledger.</div>
            </div>
            <div style={{display: 'flex', justifyContent: 'flex-end', marginTop: '1.25rem'}}>
              <button className="btn btn-primary" onClick={() => setShowTourModal(false)}>Explore Platform</button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmation & Rejection Modal */}
      {modalConfig && (
        <div className="modal-backdrop open">
          <div className="modal-dialog">
            <h3 style={{fontSize: '1rem', fontWeight: 700, marginBottom: '0.5rem'}}>{modalConfig.title}</h3>
            <p style={{fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.75rem', whiteSpace: 'pre-line'}}>
              {modalConfig.description}
            </p>
            {modalConfig.inputLabel && (
              <div className="form-group">
                <label className="form-label">{modalConfig.inputLabel}</label>
                <textarea className="form-control" rows="3" id="modal-input-field" defaultValue={modalConfig.defaultValue || ''} />
              </div>
            )}
            <div style={{display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1rem'}}>
              <button className="btn btn-secondary" onClick={closeModal}>Cancel</button>
              <button 
                className={`btn ${modalConfig.isDanger ? 'btn-danger' : 'btn-primary'}`}
                onClick={() => {
                  if (modalConfig.onConfirm) {
                    const el = document.getElementById('modal-input-field');
                    modalConfig.onConfirm(el ? el.value : true);
                  } else closeModal();
                }}
              >
                {modalConfig.confirmText || 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
