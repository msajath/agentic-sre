import React, { useState, useEffect, useCallback } from 'react';
import './index.css';
import AuthScreen from './AuthScreen.jsx';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || window.location.origin).replace(/\/$/, "");
const roleNames = { ADMIN: "admin", SRE_LEAD: "lead", OPERATOR: "operator", VIEWER: "viewer" };

const nodePositions = {
  "auth-service": { x: 120, y: 55 },
  "inventory-service": { x: 120, y: 150 },
  "payment-service": { x: 120, y: 245 },
  "order-service": { x: 380, y: 150 },
  "notification-service": { x: 620, y: 150 }
};

export default function App() {
  const theme = 'humanized';
  const [role, setRole] = useState('anonymous');
  const [token, setToken] = useState(null);
  const [username, setUsername] = useState('');
  const [apiError, setApiError] = useState('');
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
  const [legacyAudit, setLegacyAudit] = useState(null);

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
  const [investigationRuns, setInvestigationRuns] = useState([]);
  const [investigationLoading, setInvestigationLoading] = useState(false);
  const [postmortem, setPostmortem] = useState(null);

  // Chaos Form
  const [chaosService, setChaosService] = useState('payment-service');
  const [chaosType, setChaosType] = useState('LATENCY');
  const [chaosMagnitude, setChaosMagnitude] = useState(1.0);
  const [chaosDuration, setChaosDuration] = useState(30);
  const [chaosStatusMsg, setChaosStatusMsg] = useState(null);

  // Modals & Utilities
  const [modalConfig, setModalConfig] = useState(null);
  const [showTourModal, setShowTourModal] = useState(false);
  const [show403Screen, setShow403Screen] = useState(false);

  // 1. Theme Management
  useEffect(() => {
    document.body.setAttribute('data-theme', theme);
  }, [theme]);

  const clearSession = useCallback(() => {
    setToken(null); setRole('anonymous'); setUsername('');
    window.history.replaceState(null, '', '/login');
    setServices([]); setEdges([]); setIncident(null); setDiagnosis(null);
    setActiveFaults([]); setIncidentsList([]); setRemediationPlans([]); setAuditLogs([]);
    setAiAnalysis(null); setSelectedIncidentDetail(null); setAuditVerification(null);
    setInvestigationRuns([]); setInvestigationLoading(false); setPostmortem(null);
    setLegacyAudit(null);
    setBenchmarkData({ metrics: null, scenarios: [] }); setSelectedScenarioReplay(null);
    setKnowledgeDocs([]); setRagSearchResults(null); setAgentsList([]);
    setServicesCatalog([]); setPlatformSettings(null);
  }, []);

  const getAuthHeaders = useCallback(() => ({
    'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }), [token]);

  const apiFetch = useCallback(async (path, options = {}) => {
    try {
      const response = await fetch(`${API_BASE}${path}`, { ...options, headers: { ...getAuthHeaders(), ...options.headers } });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        if (response.status === 401) clearSession();
        const detail = Array.isArray(error.detail) ? error.detail.map(item => item.msg).join('; ') : error.detail;
        throw new Error(detail || `Request failed (${response.status})`);
      }
      setApiError('');
      return response;
    } catch (error) { setApiError(error.message); throw error; }
  }, [getAuthHeaders, clearSession]);

  const handleAuthenticated = (data) => {
    clearSession();
    window.history.replaceState(null, '', '/');
    setRole(roleNames[data.role]);
    setUsername(data.username);
    setToken(data.access_token);
    setApiError('');
    setShow403Screen(false);
  };

  useEffect(() => {
    if (!token) return;
    let socket;
    let retry;
    let stopped = false;
    const url = new URL('/ws/dashboard', API_BASE);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    const connect = () => {
      socket = new WebSocket(url);
      socket.onopen = () => socket.send(JSON.stringify({ access_token: token }));
      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'TELEMETRY_SNAPSHOT') {
            setWsStatus('STREAM LIVE'); setServices(data.services || []); setEdges(data.edges || []);
            setIncident(data.incident || null); setDiagnosis(data.diagnosis || null); setActiveFaults(data.active_faults || []);
          }
        } catch (error) { setApiError(`Telemetry parse error: ${error.message}`); }
      };
      socket.onclose = (event) => {
        if (stopped) return;
        setWsStatus('RECONNECTING');
        if (event.code === 1008) { clearSession(); return; }
        retry = setTimeout(connect, 2000);
      };
    };
    connect();
    return () => { stopped = true; clearTimeout(retry); if (socket) socket.close(); };
  }, [token, clearSession]);

  // 4. Data Fetch Handlers
  const fetchIncidents = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/incidents`);
      if (res.ok) setIncidentsList(await res.json());
    } catch (e) { console.error(e); }
  }, [apiFetch]);

  const fetchInvestigationRuns = useCallback(async (incidentId) => {
    if (!incidentId) { setInvestigationRuns([]); return; }
    try {
      const res = await apiFetch(`/api/v1/ai/investigations/${encodeURIComponent(incidentId)}`);
      setInvestigationRuns(await res.json());
    } catch (error) { console.error(error); }
  }, [apiFetch]);

  useEffect(() => {
    if (token && activeTab === 'incidents') {
      const incidentId = selectedIncidentDetail?.incident_id || incident?.incident_id;
      const timer = setTimeout(() => fetchInvestigationRuns(incidentId), 0);
      return () => clearTimeout(timer);
    }
  }, [token, activeTab, selectedIncidentDetail?.incident_id, incident?.incident_id, fetchInvestigationRuns]);

  const fetchRemediationPlans = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/remediation/plans`);
      if (res.ok) setRemediationPlans(await res.json());
    } catch (e) { console.error(e); }
  }, [apiFetch]);

  const fetchAuditLogs = useCallback(async () => {
    try {
      const [logs, legacy] = await Promise.all([
        apiFetch(`/api/v1/audit/logs?limit=50`).then(res => res.json()),
        apiFetch(`/api/v1/audit/legacy?limit=50`).then(res => res.json()),
      ]);
      setAuditLogs(logs); setLegacyAudit(legacy); setAuditVerification(null);
    } catch (e) { console.error(e); }
  }, [apiFetch]);

  const fetchActiveFaults = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/chaos/faults`);
      if (res.ok) setActiveFaults(await res.json());
    } catch (e) { console.error(e); }
  }, [apiFetch]);

  const fetchBenchmarks = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/evaluations/benchmarks`);
      if (res.ok) setBenchmarkData(await res.json());
    } catch (e) { console.error(e); }
  }, [apiFetch]);

  const fetchKnowledge = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/knowledge/documents`);
      if (res.ok) setKnowledgeDocs(await res.json());
    } catch (e) { console.error(e); }
  }, [apiFetch]);

  const fetchAgents = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/agents`);
      if (res.ok) setAgentsList(await res.json());
    } catch (e) { console.error(e); }
  }, [apiFetch]);

  const fetchServicesCatalog = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/services/catalog`);
      if (res.ok) setServicesCatalog(await res.json());
    } catch (e) { console.error(e); }
  }, [apiFetch]);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/settings`);
      if (res.ok) setPlatformSettings(await res.json());
    } catch (e) { console.error(e); }
  }, [apiFetch]);

  // Sync on tab change
  useEffect(() => {
    if (!token) return;
    const sync = () => {
    if (activeTab === 'incidents') fetchIncidents();
    else if (activeTab === 'approvals') fetchRemediationPlans();
    else if (activeTab === 'evaluations') fetchBenchmarks();
    else if (activeTab === 'services') fetchServicesCatalog();
    else if (activeTab === 'agents') fetchAgents();
    else if (activeTab === 'knowledge') fetchKnowledge();
    else if (activeTab === 'chaos') fetchActiveFaults();
    else if (activeTab === 'audit') fetchAuditLogs();
    else if (activeTab === 'settings') fetchSettings();
    };
    // Schedule external synchronization after navigation; cancel queued work on tab changes.
    const timer = setTimeout(sync, 0);
    return () => clearTimeout(timer);
  }, [token, activeTab, fetchIncidents, fetchRemediationPlans, fetchBenchmarks, fetchServicesCatalog, fetchAgents, fetchKnowledge, fetchActiveFaults, fetchAuditLogs, fetchSettings]);

  // Modal helpers
  const openModal = (config) => setModalConfig(config);
  const closeModal = () => setModalConfig(null);

  // RBAC Permission Check
  const requireRole = (allowedRoles, _actionName) => {
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
      const resp = await apiFetch(`/api/v1/chaos/inject`, {
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
      await apiFetch(`/api/v1/chaos/faults/${serviceName}?fault_type=${faultType}`, { method: "DELETE" });
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
          await apiFetch(`/api/v1/chaos/reset`, { method: "POST" });
          fetchActiveFaults();
          fetchAuditLogs();
          closeModal();
        } catch (err) { console.error(err); closeModal(); }
      }
    });
  };

  // Evaluation Replay Action
  const handleReplayBenchmark = async (scenarioId) => {
    setReplayLoading(true);
    try {
      const res = await apiFetch(`/api/v1/evaluations/replay/${scenarioId}`, { method: "POST" });
      if (res.ok) {
        const rep = await res.json();
        setSelectedScenarioReplay(rep);
        fetchBenchmarks();
      }
    } catch (e) { console.error(e); }
    finally { setReplayLoading(false); }
  };

  // Local Runbook Search
  const handleSearchRag = async (e) => {
    e.preventDefault();
    if (!ragQuery.trim()) return;
    try {
      const res = await apiFetch(`/api/v1/knowledge/search?query=${encodeURIComponent(ragQuery)}`);
      if (res.ok) setRagSearchResults(await res.json());
    } catch (e) { console.error(e); }
  };

  // Remediation Approval / Rejection
  const handleApprovePlan = async (planId) => {
    if (!requireRole(['admin', 'lead'], 'Approve Remediation Plan')) return;
    try {
      const res = await apiFetch(`/api/v1/remediation/plans/${planId}/approve`, {
        method: "POST",
        headers: getAuthHeaders(),
        body: JSON.stringify({ reason: `Approved by ${username}` })
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
          const res = await apiFetch(`/api/v1/remediation/plans/${planId}/reject`, {
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
    if (!requireRole(['admin', 'lead', 'operator'], 'Diagnose incident')) return;
    const incId = selectedIncidentDetail?.incident_id || incident?.incident_id;
    if (!incId) { setApiError('Select an existing incident before running diagnosis.'); return; }
    setAiLoading(true);
    try {
      const res = await apiFetch(`/api/v1/ai/analyze-incident/${incId}`, {
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

  const handleRunInvestigation = async () => {
    if (!requireRole(['admin', 'lead', 'operator'], 'Run investigation')) return;
    const incidentId = selectedIncidentDetail?.incident_id || incident?.incident_id;
    if (!incidentId) { setApiError('Select an incident to investigate.'); return; }
    setInvestigationLoading(true);
    try {
      const res = await apiFetch(`/api/v1/ai/stream-investigation/${encodeURIComponent(incidentId)}`);
      const body = await res.text();
      const messages = body.split('\n').filter(line => line.startsWith('data: '))
        .map(line => JSON.parse(line.slice(6)));
      const failure = messages.find(message => message.type === 'WORKFLOW_ERROR');
      if (failure) throw new Error(failure.message);
      await fetchInvestigationRuns(incidentId);
    } catch (error) { setApiError(error.message); }
    finally { setInvestigationLoading(false); }
  };

  const handleLoadPostmortem = async () => {
    const incidentId = selectedIncidentDetail?.incident_id || incident?.incident_id;
    if (!incidentId) return;
    try {
      const res = await apiFetch(`/api/v1/incidents/${encodeURIComponent(incidentId)}/postmortem`);
      setPostmortem(await res.json());
    } catch (error) { console.error(error); }
  };

  const handleProposePlan = async () => {
    if (!requireRole(['admin', 'lead', 'operator'], 'Propose remediation')) return;
    if (!aiAnalysis?.incidentId) return;
    try {
      await apiFetch(`/api/v1/remediation/auto-propose/${aiAnalysis.incidentId}`, { method: 'POST' });
      await fetchRemediationPlans(); setActiveTab('approvals');
    } catch (error) { console.error(error); }
  };

  // Calculations
  const healthySvcCount = services.filter(s => s.status === 'HEALTHY').length;
  const avgP95 = services.length > 0 ? services.reduce((acc, s) => acc + (s.p95_latency_ms || 0), 0) / services.length : 0;
  const avgError = services.length > 0 ? services.reduce((acc, s) => acc + (s.error_rate || 0), 0) / services.length : 0;

  if (!token) return <AuthScreen apiBase={API_BASE} onAuthenticated={handleAuthenticated} />;

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
              <p>Simulated incident management with human-approved recovery</p>
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

            <span className="account-name">{username} ({role})</span>
            <button className="btn btn-secondary" onClick={clearSession}>Sign out</button>

            <button 
              className="btn btn-danger" 
              style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }} 
              onClick={handleEmergencyReset}
              title="Cancel all active chaos experiments"
            >
              Emergency Reset
            </button>


            <div className={`pill-badge ${wsStatus === 'STREAM LIVE' ? 'pill-healthy' : 'pill-critical'}`}>
              <span className="pill-dot"></span>
              <span>{wsStatus}</span>
            </div>
          </div>
        </div>

        {/* Top Navigation Bar with All 10 Platform Sections */}
        <nav className="nav-tabs-bar" aria-label="Platform sections">
          {[
            { id: 'overview', label: 'Overview', badge: null, core: true },
            { id: 'incidents', label: 'Incidents', badge: incident ? '1' : null, core: true },
            { id: 'approvals', label: 'Approvals', badge: remediationPlans.filter(p => p.state === 'PENDING_APPROVAL').length || null, core: true },
            { id: 'evaluations', label: 'Evaluations', badge: null, core: true },
            { id: 'services', label: 'Services', badge: null },
            { id: 'agents', label: 'Workflow', badge: agentsList.length || null },
            { id: 'knowledge', label: 'Runbooks', badge: null },
            { id: 'chaos', label: 'Chaos', badge: activeFaults.length || null },
            { id: 'audit', label: 'Audit Log', badge: null },
            { id: 'settings', label: 'Settings', badge: null }
          ].map(tab => (
            <button
              key={tab.id}
              className={`nav-tab-btn ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => { setShow403Screen(false); setActiveTab(tab.id); }}
              aria-current={activeTab === tab.id ? 'page' : undefined}
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

      {apiError && <div role="alert" style={{padding: '1rem 2rem', color: '#ef4444'}}>{apiError}</div>}
      {/* Active Incident Broadcast Banner */}
      {incident && (
        <div className="incident-banner active" style={{ margin: '1rem 2rem 0 2rem' }}>
          <div className="incident-banner-header">
            <div className="incident-title-row">
              <span className={`badge badge-${incident.severity}`}>{incident.severity} · {incident.state}</span>
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
            {incident.description} | Candidate service: <strong>{incident.root_cause_service || 'Unconfirmed'}</strong> | Affected services: <em>{(incident.affected_services || []).join(', ') || 'Under review'}</em>
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
              <button className="btn btn-primary" onClick={clearSession}>Sign in with another account</button>
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
                    <div className="stat-label">Healthy simulated services</div>
                    <div className="stat-val-row">
                      <span className="stat-val">{healthySvcCount} / {services.length}</span>
                      <span className="stat-sub">Healthy</span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Mean service p95 latency</div>
                    <div className="stat-val-row">
                      <span className="stat-val">{Math.round(avgP95)} ms</span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Mean service error rate</div>
                    <div className="stat-val-row">
                      <span className="stat-val" style={{color: avgError > 0.05 ? 'var(--status-critical)' : 'inherit'}}>
                        {(avgError * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Injected faults</div>
                    <div className="stat-val-row">
                      <span className="stat-val" style={{color: activeFaults.length ? 'var(--status-critical)' : 'inherit'}}>
                        {activeFaults.length}
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
                        <marker id="arrow" viewBox="0 0 10 10" refX="26" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                          <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--topology-line, #94a3b8)" />
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
                            stroke="var(--topology-line, #94a3b8)" strokeWidth="1.8" strokeDasharray="4,4" markerEnd="url(#arrow)" 
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
                            <text y="4" textAnchor="middle" fill="var(--text-primary)" fontSize="9" fontWeight="700" fontFamily="var(--font-sans)">
                              {svcName.split('-')[0].slice(0, 4).toUpperCase()}
                            </text>
                            <text y="32" textAnchor="middle" fill="var(--text-muted)" fontSize="10" fontWeight="600" fontFamily="var(--font-sans)">
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
                            <span>{Math.round(svc.p95_latency_ms)} ms</span>
                          </div>
                          <div className="metric-bar-track">
                            <div className="metric-bar-fill" style={{ width: `${Math.min(100, (svc.p95_latency_ms / 600) * 100)}%`, background: svc.p95_latency_ms > 400 ? 'var(--status-critical)' : 'var(--status-healthy)' }} />
                          </div>
                        </div>
                        <div className="metric-bar-group">
                          <div className="metric-bar-header">
                            <span>Error Rate</span>
                            <span>{(svc.error_rate * 100).toFixed(1)}%</span>
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
                            <button type="button"
                              key={inc.incident_id} 
                              onClick={() => { setSelectedIncidentDetail(inc); setAiAnalysis(null); setInvestigationRuns([]); setPostmortem(null); }}
                              aria-pressed={selectedIncidentDetail?.incident_id === inc.incident_id}
                              className="incident-list-item"
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
                                  <span style={{fontWeight: 700, color: 'var(--accent-primary)', fontSize: '0.8rem'}}>{inc.incident_id}</span>
                                  <span style={{fontWeight: 600, fontSize: '0.82rem', marginLeft: '0.4rem'}}>{inc.title}</span>
                                </div>
                                <span className={`badge badge-${inc.state === 'RESOLVED' ? 'HEALTHY' : 'CRITICAL'}`}>{inc.state}</span>
                              </div>
                              <div style={{fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '0.35rem'}}>
                                Root Cause: <strong>{inc.root_cause_service || 'Triage Pending'}</strong> | Severity: <strong>{inc.severity}</strong>
                              </div>
                            </button>
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
                          <div style={{fontSize: '0.9rem', fontWeight: 700, color: 'var(--status-critical)'}}>
                            Target: {diagnosis.root_cause_service}
                          </div>
                          <div style={{marginTop: '0.3rem', fontSize: '0.78rem', color: 'var(--text-secondary)'}}>
                            {diagnosis.explanation}
                          </div>
                          <div style={{marginTop: '0.35rem', fontSize: '0.72rem', color: 'var(--text-muted)'}}>
                            Blast Radius: {(diagnosis.cascading_symptoms || []).join(', ') || 'Isolated'}
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
                          <div style={{fontSize: '0.92rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.4rem'}}>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="2"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8z"/><path d="M12 6v6l4 2"/></svg>
                            Incident diagnosis
                          </div>
                          <div style={{fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.15rem'}}>
                            Heuristic diagnosis from simulated telemetry
                          </div>
                        </div>
                        <button 
                          className="btn btn-purple" 
                          style={{padding: '0.3rem 0.75rem', fontSize: '0.75rem'}}
                          disabled={aiLoading || (!incident && !selectedIncidentDetail)}
                          onClick={handleRunAiDiagnosis}
                        >
                          {aiLoading ? 'Diagnosing…' : 'Quick diagnosis'}
                        </button>
                      </div>

                      <div style={{padding: '0.5rem 0'}}>
                        {aiLoading ? (
                          <div style={{padding: '2.5rem', textAlign: 'center', color: '#c4b5fd', fontSize: '0.85rem'}}>
                            <div>Traversing topology DAG & synthesizing containment strategy...</div>
                          </div>
                        ) : aiAnalysis ? (
                          <div style={{background: 'var(--ai-panel-bg)', border: '1px solid var(--ai-panel-border)', borderRadius: 'var(--radius-md)', padding: '1.25rem'}}>
                            <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem'}}>
                              <div>
                                <div style={{fontSize: '0.7rem', color: 'var(--accent-purple)', textTransform: 'uppercase', fontWeight: 700}}>Root Cause Hypothesis</div>
                                <div style={{fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: '0.15rem'}}>
                                  {aiAnalysis.root_cause_service}
                                </div>
                              </div>
                              <span style={{background: 'rgba(124, 58, 237, 0.1)', color: 'var(--accent-purple)', fontWeight: 700, fontSize: '0.72rem', padding: '0.2rem 0.55rem', borderRadius: '4px', border: '1px solid rgba(124, 58, 237, 0.25)'}}>
                                {Math.round((aiAnalysis.confidence ?? 0) * 100)}% Heuristic Score
                              </span>
                            </div>

                            <div style={{marginBottom: '0.85rem'}}>
                              <div style={{fontSize: '0.72rem', color: 'var(--accent-purple)', fontWeight: 700, marginBottom: '0.35rem', textTransform: 'uppercase'}}>Diagnostic explanation</div>
                              <div style={{background: 'var(--ai-cot-bg)', border: '1px solid var(--ai-cot-border)', borderRadius: 'var(--radius-sm)', padding: '0.75rem', fontSize: '0.74rem', color: 'var(--ai-cot-text)', maxHeight: '150px', overflowY: 'auto'}}>
                                {(aiAnalysis.explanation || '').split('; ').map((step, idx) => (
                                  <div key={idx} style={{marginBottom: '0.4rem', lineHeight: '1.5'}}>
                                    <span style={{color: 'var(--accent-purple)', fontWeight: 700}}>{step.includes(']') ? step.split(']')[0].replace('[', '') : `Step ${idx+1}`}</span>: {step.includes(']') ? step.split(']')[1] : step}
                                  </div>
                                ))}
                              </div>
                            </div>

                            <button className="btn btn-primary" onClick={handleProposePlan} disabled={!aiAnalysis.incidentId || aiAnalysis.evidence_status === 'INSUFFICIENT_EVIDENCE' || !aiAnalysis.confidence}>Propose remediation</button>
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
                            Select an incident and run a quick diagnosis. If telemetry is healthy, the result will ask for fresh evidence.
                          </div>
                        )}
                      </div>
                    </div>
                    <section className="investigation-panel" aria-labelledby="investigation-heading">
                      <div className="investigation-heading-row">
                        <div>
                          <h2 id="investigation-heading">Investigation trace</h2>
                          <p>Review the decisions and tool calls saved for this incident.</p>
                        </div>
                        <button className="btn btn-primary" onClick={handleRunInvestigation}
                          disabled={investigationLoading || (!incident && !selectedIncidentDetail)}>
                          {investigationLoading ? 'Investigating…' : 'Run investigation'}
                        </button>
                      </div>
                      {investigationRuns.length ? (
                        <div className="run-detail">
                          <div className="run-status-row">
                            <span className={`run-status run-status-${investigationRuns[0].status.toLowerCase()}`}>{investigationRuns[0].status.replaceAll('_', ' ')}</span>
                            <span>Run {investigationRuns[0].run_id.slice(0, 8)} · {new Date(investigationRuns[0].started_at).toLocaleString()}</span>
                          </div>
                          <ol className="trace-steps">
                            {investigationRuns[0].state.execution_trace.map((step, index) => (
                              <li key={`${step.node}-${index}`}>
                                <div><strong>{step.node.replaceAll('_', ' ')}</strong><span>{step.status.replaceAll('_', ' ')}</span></div>
                                <p>{step.thought_process}</p>
                                {step.tools_called.length > 0 && <small>{step.tools_called.length} typed tool calls</small>}
                              </li>
                            ))}
                          </ol>
                          {investigationRuns[0].status === 'NEEDS_EVIDENCE' && <p className="evidence-notice">No current anomaly supports a restart. Collect fresh telemetry, then investigate again.</p>}
                        </div>
                      ) : <p className="investigation-empty">Select an incident and run an investigation to see its saved decisions and tool calls.</p>}
                    </section>
                    {['RESOLVED', 'CLOSED'].includes(selectedIncidentDetail?.state || incident?.state) && (
                      <section className="postmortem-panel" aria-labelledby="postmortem-heading">
                        <div className="investigation-heading-row">
                          <div>
                            <h2 id="postmortem-heading">Incident report</h2>
                            <p>Generated from the saved simulation timeline and verification result.</p>
                          </div>
                          <button className="btn btn-secondary" onClick={handleLoadPostmortem}>View report</button>
                        </div>
                        {postmortem && (
                          <div className="postmortem-detail">
                            <p><strong>Impact:</strong> {postmortem.affected_services.join(', ') || 'Unknown'}. {postmortem.impact_note}</p>
                            <p><strong>Cause candidate:</strong> {postmortem.root_cause_candidate || 'Unconfirmed'}. {postmortem.causality_note}</p>
                            <p><strong>Recovery:</strong> {postmortem.recovery_verification || 'No verified recovery note was recorded.'}</p>
                            <h3>Decision timeline</h3>
                            <ol>{postmortem.timeline.map(event => <li key={event.event_id}>{new Date(event.timestamp).toLocaleString()} — {event.action}</li>)}</ol>
                          </div>
                        )}
                      </section>
                    )}
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
                      const statusColor = p.state === 'VERIFIED_SUCCESSFUL' ? 'HEALTHY' : (p.state === 'REJECTED' || ['FAILED_ROLLBACK', 'FAILED_VERIFICATION', 'EXECUTION_FAILED'].includes(p.state) ? 'CRITICAL' : 'DEGRADED');
                      return (
                        <div key={p.plan_id} style={{background: 'var(--bg-surface-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '1rem', marginBottom: '0.85rem'}}>
                          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                            <div>
                              <span style={{fontWeight: 700, color: 'var(--accent-primary)', fontSize: '0.82rem'}}>{p.plan_id}</span>
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
                        {benchmarkData.metrics?.root_cause_top1_accuracy != null ? `${(benchmarkData.metrics.root_cause_top1_accuracy * 100).toFixed(1)}%` : 'Not measured'}
                      </span>
                      <span className="stat-sub">Target &gt; 90%</span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Recommended Action Match</div>
                    <div className="stat-val-row">
                      <span className="stat-val" style={{color: '#10b981'}}>
                        {benchmarkData.metrics?.tool_selection_accuracy != null ? `${(benchmarkData.metrics.tool_selection_accuracy * 100).toFixed(1)}%` : 'Not measured'}
                      </span>
                      <span className="stat-sub">Allowlist Gated</span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Harness Diagnosis Time</div>
                    <div className="stat-val-row">
                      <span className="stat-val">
                        {benchmarkData.metrics?.mean_time_to_diagnose_sec != null ? `${benchmarkData.metrics.mean_time_to_diagnose_sec.toFixed(4)}s` : 'Not measured'}
                      </span>
                      <span className="stat-sub">Automated</span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Unsafe Action Rate</div>
                    <div className="stat-val-row">
                      <span className="stat-val" style={{color: '#10b981'}}>Not measured</span>
                      <span className="stat-sub">Requires separate safety evaluation</span>
                    </div>
                  </div>
                </div>

                {/* Benchmark Scenarios Replay Table */}
                <div className="card">
                  <div className="card-header">
                    <div>
                      <div className="card-title-group">
                        <h2>Simulation Benchmark Scenarios</h2>
                      </div>
                      <div className="card-subtitle">Isolated synthetic cycles. Timings measure harness execution, not production MTTD or MTTR.</div>
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
                            <td style={{padding: '0.75rem 0.6rem'}}>{s.target_service}</td>
                            <td style={{padding: '0.75rem 0.6rem', color: 'var(--accent-purple)'}}>{s.expected_action}</td>
                            <td style={{padding: '0.75rem 0.6rem'}}>{s.mttd_sec == null ? 'Not run' : `${s.mttd_sec.toFixed(4)}s`}</td>
                            <td style={{padding: '0.75rem 0.6rem', color: '#10b981', fontWeight: 700}}>{s.accuracy_score == null ? 'Not run' : `${(s.accuracy_score * 100).toFixed(0)}%`}</td>
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
                      <span className={`badge ${selectedScenarioReplay.status === "PASSED" ? "badge-HEALTHY" : "badge-CRITICAL"}`}>{selectedScenarioReplay.status}</span>
                    </div>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', fontSize: '0.8rem', padding: '0.5rem 0'}}>
                      <div style={{background: 'var(--bg-surface-elevated)', padding: '0.85rem', borderRadius: 'var(--radius-md)'}}>
                        <div style={{fontWeight: 700, color: '#a78bfa', marginBottom: '0.35rem'}}>Diagnosis Evaluation</div>
                        <div>Target Service: <strong>{selectedScenarioReplay.target_service}</strong></div>
                        <div>Root Cause Match: <strong style={{color: '#10b981'}}>{selectedScenarioReplay.diagnosis_result.top1_match ? "Matched" : "Mismatch"}</strong></div>
                        <div>Heuristic Score: <strong>{(selectedScenarioReplay.diagnosis_result.confidence * 100).toFixed(1)}%</strong></div>
                        <div>Evidence Items Collected: <strong>{selectedScenarioReplay.diagnosis_result.evidence_count} anomaly signals</strong></div>
                        <div>Harness diagnosis time: <strong>{selectedScenarioReplay.diagnosis_result.mttd_sec}s</strong></div>
                      </div>
                      <div style={{background: 'var(--bg-surface-elevated)', padding: '0.85rem', borderRadius: 'var(--radius-md)'}}>
                        <div style={{fontWeight: 700, color: '#a78bfa', marginBottom: '0.35rem'}}>Remediation & Safety Evaluation</div>
                        <div>Proposed Action: <code style={{color: 'var(--accent-primary)'}}>{selectedScenarioReplay.remediation_result.proposed_action}</code></div>
                        <div>Recovery: <strong>{selectedScenarioReplay.remediation_result.recovered ? "Healthy after simulated recovery" : "Failed"}</strong></div>
                        <div>Approval and safety workflow: <strong>Not measured by this harness</strong></div>
                        <div>Harness recovery time: <strong>{selectedScenarioReplay.remediation_result.mttr_sec}s</strong></div>
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
                      <h2>Sequential Investigation Workflow</h2>
                    </div>
                    <div className="card-subtitle">Four implemented stages with optional Ollama narration and a human approval checkpoint</div>
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
            {/* 7. LOCAL RUNBOOKS */}
            {/* ========================================================================= */}
            {activeTab === 'knowledge' && (
              <div>
                {/* Search Bar */}
                <div className="card">
                  <div className="card-header">
                    <div>
                      <div className="card-title-group">
                        <h2>Local Operational Runbooks</h2>
                      </div>
                      <div className="card-subtitle">Search saved runbook content by matching words; results quote the stored text.</div>
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
                      Search Runbooks
                    </button>
                  </form>

                  {ragSearchResults && (
                    <div style={{marginTop: '1rem', background: 'rgba(59, 130, 246, 0.05)', border: '1px solid rgba(59, 130, 246, 0.2)', borderRadius: 'var(--radius-md)', padding: '0.85rem'}}>
                      <div style={{fontSize: '0.75rem', fontWeight: 700, color: '#93c5fd', marginBottom: '0.5rem'}}>
                        Retrieved {ragSearchResults.citations.length} Runbook Matches:
                      </div>
                      {ragSearchResults.citations.map((c, idx) => (
                        <div key={idx} style={{marginBottom: '0.5rem', fontSize: '0.75rem', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.4rem'}}>
                          <div style={{display: 'flex', justifyContent: 'space-between'}}>
                            <span style={{fontWeight: 600, color: '#f8fafc'}}>{c.doc_title}</span>
                            <span style={{color: '#10b981'}}>{(c.similarity_score * 100).toFixed(0)}% Query Term Match</span>
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
                            <span style={{fontSize: '0.75rem', color: 'var(--accent-primary)', fontWeight: 600}}>{doc.id}</span>
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
                        <option value="LATENCY">LATENCY (Simulate slow downstream API)</option>
                        <option value="ERROR_STORM">ERROR_STORM (Simulate 500 error cascade)</option>
                        <option value="RESOURCE_SATURATION">RESOURCE_SATURATION (Simulate heavy thread load)</option>
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
                          <div style={{fontSize: '0.82rem', fontWeight: 700, color: 'var(--status-critical)'}}>
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
                    <div className="card-subtitle">Persisted hash-chained log entries with tamper verification</div>
                  </div>
                  <div style={{display: 'flex', gap: '0.5rem'}}>
                    <button className="btn btn-secondary" onClick={fetchAuditLogs} style={{fontSize: '0.75rem'}}>Refresh</button>
                    <button className="btn btn-primary" onClick={async () => {
                      const res = await apiFetch(`/api/v1/audit/verify`);
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
                      {auditVerification.is_valid ? `✔ AUDIT CHAIN VERIFIED (${auditVerification.total_entries} entries intact)` : '⚠ AUDIT CHAIN VERIFICATION FAILED'}
                    </span>
                    <button className="btn btn-secondary" style={{padding: '0.1rem 0.4rem', fontSize: '0.68rem'}} onClick={() => setAuditVerification(null)}>Dismiss</button>
                  </div>
                )}

                {legacyAudit?.summary && (
                  <details style={{margin: '0.5rem 0 1rem', padding: '0.75rem 1rem', borderRadius: 'var(--radius-md)', background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)'}}>
                    <summary style={{cursor: 'pointer', color: '#fbbf24', fontWeight: 600}}>
                      {legacyAudit.summary.archived_records} legacy audit records preserved as unverified history
                    </summary>
                    <p style={{fontSize: '0.8rem', color: 'var(--text-muted)'}}>The earlier audit chain failed verification. Its original records are archived separately and are excluded from the active chain verification above. Showing up to 50 archived records.</p>
                    <div style={{maxHeight: '260px', overflowY: 'auto'}}>
                      {legacyAudit.records.map(({record}) => (
                        <div key={record.log_id} style={{padding: '0.5rem 0', borderBottom: '1px solid var(--border-subtle)', fontSize: '0.75rem'}}>
                          <strong>{record.actor}</strong> · {record.action_summary}
                          <div style={{color: 'var(--text-dim)'}}>{record.timestamp} · {record.target_resource} · Unverified</div>
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                <div style={{maxHeight: '520px', overflowY: 'auto'}}>
                  {auditLogs.map(l => (
                    <div key={l.entry_id || l.entry_hash} style={{padding: '0.65rem 0.85rem', borderBottom: '1px solid var(--border-subtle)', display: 'grid', gridTemplateColumns: '120px 140px 1fr 140px', gap: '0.75rem', alignItems: 'center', fontSize: '0.75rem'}}>
                      <div style={{color: 'var(--text-dim)', fontSize: '0.7rem'}}>{new Date(l.timestamp).toLocaleTimeString()}</div>
                      <div><strong style={{color: '#93c5fd'}}>{l.actor}</strong> <span style={{color: 'var(--text-dim)'}}>({l.actor_role})</span></div>
                      <div>
                        <div style={{color: 'var(--text-primary)', fontWeight: 600}}>{l.action_summary}</div>
                        <div style={{color: 'var(--text-muted)', fontSize: '0.7rem'}}>Target: <code>{l.target_resource}</code></div>
                      </div>
                      <div style={{fontSize: '0.68rem', color: 'var(--text-dim)', textAlign: 'right'}}>{l.entry_hash ? `${l.entry_hash.slice(0, 10)}...` : 'N/A'}</div>
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
                        <div>🟡 <strong>Medium Risk</strong>: Simulated recovery actions require a lead or administrator approval.</div>
                        <div>🔴 <strong>High Risk</strong>: Threshold updates require an administrator; live cluster actions are unavailable.</div>
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

      {/* Onboarding Tour Modal */}
      {showTourModal && (
        <div className="modal-backdrop open">
          <div className="modal-dialog" style={{maxWidth: '560px'}}>
            <h3 style={{fontWeight: 700, fontSize: '1.1rem', color: '#ede9fe', marginBottom: '0.5rem'}}>
              Welcome to Agentic SRE Sentinel Platform
            </h3>
            <p style={{fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.85rem'}}>
              This console demonstrates incident workflows using synthetic services. It does not execute actions on a Kubernetes cluster:
            </p>
            <div style={{fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.4rem'}}>
              <div>🔹 <strong>Overview</strong>: Real-time SVG dependency topology and golden signals telemetry.</div>
              <div>🔹 <strong>Incidents</strong>: Incident lifecycle with Root Cause Analysis (RCA) and deterministic diagnosis.</div>
              <div>🔹 <strong>Approvals</strong>: Human-in-the-loop safety barrier for rollback and restart operations.</div>
              <div>🔹 <strong>Evaluations</strong>: Isolated benchmarks with measured harness timings and root cause matches.</div>
              <div>🔹 <strong>Services & Agents</strong>: Microservice catalog and multi-agent hierarchy.</div>
              <div>🔹 <strong>Knowledge & Audit</strong>: Saved local runbooks and cryptographic SHA-256 ledger.</div>
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
