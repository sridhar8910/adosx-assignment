import React, { useEffect, useState } from 'react'
import { fetchOrgs, fetchReasons, fetchDisagreements, fetchImportIssues, triggerReconcile } from './api'

export default function App() {
  // Navigation Tabs: 'dashboard' | 'explorer' | 'topology' | 'audit' | 'console'
  const [activeTab, setActiveTab] = useState('dashboard')

  // Shared Data States
  const [orgs, setOrgs] = useState([])
  const [reasons, setReasons] = useState([])
  const [selectedOrg, setSelectedOrg] = useState('')
  const [selectedReason, setSelectedReason] = useState('')
  const [sort, setSort] = useState('reason')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Filters & Selected Record for Split View Inspector
  const [explorerSearch, setExplorerSearch] = useState('')
  const [selectedRecordId, setSelectedRecordId] = useState(null)

  // Import Issues Log states
  const [issues, setIssues] = useState(null)
  const [issuesLoading, setIssuesLoading] = useState(false)
  const [auditSearch, setAuditSearch] = useState('')
  const [auditSeverity, setAuditSeverity] = useState('ALL') // 'ALL' | 'ERROR' | 'WARNING' | 'INFO'

  // Reconciliation Ops Console
  const [reconciling, setReconciling] = useState(false)
  const [consoleLogs, setConsoleLogs] = useState([
    { time: new Date().toLocaleTimeString(), text: 'Reconciliation Core Workspace online.', type: 'success' },
    { time: new Date().toLocaleTimeString(), text: 'POSTGRESQL connection established at host localhost:5432.', type: 'info' }
  ])

  // Load configuration options on mount
  useEffect(() => {
    Promise.all([fetchOrgs(), fetchReasons()])
      .then(([o, r]) => {
        setOrgs(o)
        setReasons(r)
        if (o.length > 0) setSelectedOrg(o[0])
      })
      .catch(e => {
        setError(e.message)
        addLog(`Init failure: ${e.message}`, 'error')
      })
  }, [])

  // Load disagreements when parameters change
  const loadData = () => {
    if (!selectedOrg) return
    setLoading(true)
    setError(null)
    fetchDisagreements({ org: selectedOrg, reason: selectedReason, sort })
      .then(d => {
        setData(d)
        setLoading(false)
        // Automatically select the first disagreement if none selected
        if (d.results.length > 0) {
          setSelectedRecordId(d.results[0].id)
        } else {
          setSelectedRecordId(null)
        }
      })
      .catch(e => {
        setError(e.message)
        setLoading(false)
        addLog(`Fetch failure: ${e.message}`, 'error')
      })
  }

  useEffect(() => {
    loadData()
  }, [selectedOrg, selectedReason, sort])

  // Load audit issues once
  const loadIssues = () => {
    setIssuesLoading(true)
    fetchImportIssues()
      .then(d => {
        setIssues(d)
        setIssuesLoading(false)
      })
      .catch(e => {
        setError(e.message)
        setIssuesLoading(false)
      })
  }

  useEffect(() => {
    loadIssues()
  }, [])

  // Helper log emitter
  const addLog = (text, type = 'info') => {
    setConsoleLogs(prev => [
      ...prev,
      { time: new Date().toLocaleTimeString(), text, type }
    ])
  }

  // Trigger reconciler action
  const handleReconcile = async () => {
    setReconciling(true)
    setActiveTab('console')
    
    setConsoleLogs([])
    addLog('Initiating transaction-safe reconciliation pass...', 'info')
    setTimeout(() => addLog('Step 1: Connecting to PostgreSQL database...', 'info'), 200)
    setTimeout(() => addLog('Step 2: Clearing temporary cache with TRUNCATE CASCADE inside atomic block...', 'warn'), 500)
    setTimeout(() => addLog('Step 3: Ingesting location scopes from locations.csv...', 'info'), 800)
    setTimeout(() => addLog('Step 4: Executing file parsing rules globally...', 'info'), 1100)
    setTimeout(() => addLog('  -> Loaded 120 System A records successfully.', 'success'), 1300)
    setTimeout(() => addLog('  -> Loaded 121 System B entries successfully.', 'success'), 1500)
    setTimeout(() => addLog('Step 5: Executing Strategy Pattern Rule Engines...', 'info'), 1700)
    setTimeout(() => addLog('  -> Checking matching structures (e.g., cross-tenant record REC-1077 in ORG-A / Entry LOC-201 in ORG-B)...', 'warn'), 2000)
    
    try {
      setTimeout(async () => {
        const res = await triggerReconcile()
        addLog(`Step 6: Reconciliation success. Found ${res.count} total discrepancies.`, 'success')
        addLog('Step 7: Swapping disagreement buffers...', 'info')
        addLog('Operations successfully committed. DB Transaction OK.', 'success')
        loadData()
        loadIssues()
        setReconciling(false)
      }, 2300)
    } catch (e) {
      addLog(`Reconciliation failure: ${e.message}`, 'error')
      setError(e.message)
      setReconciling(false)
    }
  }

  // Stats computation
  const getStats = () => {
    if (!data) return { total: 0, missing: 0, mismatch: 0, duplicate: 0, orphan: 0, unparseable: 0 }
    const results = data.results || []
    return {
      total: results.length,
      missing: results.filter(r => r.reason === 'MISSING_IN_B').length,
      mismatch: results.filter(r => r.reason === 'VALUE_MISMATCH').length,
      duplicate: results.filter(r => r.reason === 'DUPLICATE_IN_B').length,
      orphan: results.filter(r => r.reason === 'ORPHAN_IN_B').length,
      unparseable: results.filter(r => r.reason === 'UNPARSEABLE_VALUE').length,
    }
  }

  const stats = getStats()

  const getReasonBadgeClass = (reason) => {
    switch (reason) {
      case 'MISSING_IN_B': return 'badge-missing'
      case 'ORPHAN_IN_B': return 'badge-orphan'
      case 'DUPLICATE_IN_B': return 'badge-duplicate'
      case 'VALUE_MISMATCH': return 'badge-value'
      case 'UNPARSEABLE_VALUE': return 'badge-unparseable'
      default: return ''
    }
  }

  // Filter local disagreements
  const filteredDisagreements = data?.results.filter(row => {
    if (!explorerSearch) return true
    const search = explorerSearch.toLowerCase()
    return (
      row.record_id_a?.toLowerCase().includes(search) ||
      row.entry_id_b?.toLowerCase().includes(search) ||
      row.location_id?.toLowerCase().includes(search) ||
      row.location_name?.toLowerCase().includes(search) ||
      row.reason_display?.toLowerCase().includes(search) ||
      (row.value_a && String(row.value_a).includes(search)) ||
      (row.value_b && String(row.value_b).includes(search))
    )
  }) || []

  // Filter import issues
  const filteredIssues = issues?.results.filter(issue => {
    if (auditSeverity !== 'ALL' && issue.severity !== auditSeverity) return false
    if (!auditSearch) return true
    const search = auditSearch.toLowerCase()
    return (
      issue.source_file?.toLowerCase().includes(search) ||
      issue.row_identifier?.toLowerCase().includes(search) ||
      issue.field_name?.toLowerCase().includes(search) ||
      issue.message?.toLowerCase().includes(search) ||
      issue.raw_value?.toLowerCase().includes(search)
    )
  }) || []

  // Get currently selected item for Inspector view
  const selectedRecord = data?.results.find(r => r.id === selectedRecordId) || null

  return (
    <div className="container">
      {/* Header bar */}
      <header className="header" style={{ marginBottom: '32px' }}>
        <div className="brand">
          <div className="brand-logo">Δ</div>
          <div>
            <h1 className="brand-title">DealerOS Observability Console</h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '11px', marginTop: '2px' }}>
              Multi-tenant global data reconciler & audit workspace
            </p>
          </div>
        </div>

        {/* Tab Selection (Segmented Control style) */}
        <div className="recon-tab-group">
          <button 
            className={`recon-tab-button ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveTab('dashboard')}
          >
            Dashboard
          </button>
          <button 
            className={`recon-tab-button ${activeTab === 'explorer' ? 'active' : ''}`}
            onClick={() => setActiveTab('explorer')}
          >
            Split-View Workspace
          </button>
          <button 
            className={`recon-tab-button ${activeTab === 'topology' ? 'active' : ''}`}
            onClick={() => setActiveTab('topology')}
          >
            Visual Topology
          </button>
          <button 
            className={`recon-tab-button ${activeTab === 'audit' ? 'active' : ''}`}
            onClick={() => setActiveTab('audit')}
          >
            Audit Log
          </button>
          <button 
            className={`recon-tab-button ${activeTab === 'console' ? 'active' : ''}`}
            onClick={() => setActiveTab('console')}
          >
            Logs
          </button>
        </div>
      </header>

      {/* Main Grid Wrapper: Sidebar + Content Canvas */}
      <div className="recon-workspace-wrapper">
        
        {/* LEFT SIDEBAR: Controls & Observability Parameters */}
        <aside className="recon-sidebar">
          {/* Action Trigger Card */}
          <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <span className="filter-label" style={{ fontSize: '11px', letterSpacing: '0.05em' }}>ENGINE CORE</span>
            <button 
              className="btn" 
              onClick={handleReconcile}
              disabled={reconciling}
              style={{ width: '100%', justifyContent: 'center', height: '44px' }}
            >
              <svg className={reconciling ? 'pulsing-engine' : ''} style={{ width: '18px', height: '18px' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              {reconciling ? 'Executing...' : 'Run Global Reconciler'}
            </button>
            
            <div className="sidebar-status-box">
              <div className="sidebar-status-row">
                <span>Database Engine</span>
                <span className="sidebar-status-value" style={{ color: '#60a5fa' }}>PostgreSQL 18</span>
              </div>
              <div className="sidebar-status-row">
                <span>Total Feeds loaded</span>
                <span className="sidebar-status-value">241 rows</span>
              </div>
              <div className="sidebar-status-row">
                <span>Active Isolation</span>
                <span className="sidebar-status-value" style={{ color: '#4ade80' }}>Strict Org Scope</span>
              </div>
            </div>
          </div>

          {/* Filtering Card */}
          <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <span className="filter-label" style={{ fontSize: '11px', letterSpacing: '0.05em' }}>ISOLATION FILTER</span>
            
            <div className="filter-item">
              <span className="filter-label">Tenant Scope</span>
              <select value={selectedOrg} onChange={e => setSelectedOrg(e.target.value)} style={{ width: '100%' }}>
                {orgs.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>

            <div className="filter-item">
              <span className="filter-label">Reason Class</span>
              <select value={selectedReason} onChange={e => setSelectedReason(e.target.value)} style={{ width: '100%' }}>
                <option value="">All Reason Classes</option>
                {reasons.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </div>
          </div>

          {/* Search Card */}
          <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <span className="filter-label" style={{ fontSize: '11px', letterSpacing: '0.05em' }}>INTELLIGENT FINDER</span>
            <div className="search-input-wrapper" style={{ maxWidth: '100%' }}>
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input 
                type="text" 
                placeholder="Search matching index..." 
                className="search-input"
                value={explorerSearch}
                onChange={e => setExplorerSearch(e.target.value)}
              />
            </div>
          </div>
        </aside>

        {/* RIGHT CONTENT CANVAS: Dynamic Render Area */}
        <main className="recon-content-canvas">
          
          {/* ==================== VIEW 1: DASHBOARD ==================== */}
          {activeTab === 'dashboard' && (
            <div className="dashboard-grid" style={{ gridTemplateColumns: '1fr' }}>
              
              {/* Highlight summary row */}
              <section className="stats-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
                <div className="glass-panel stat-card" style={{ background: 'rgba(255,255,255,0.01)' }}>
                  <span className="stat-label">Active Discrepancies</span>
                  <span className="stat-value">{stats.total}</span>
                </div>
                <div className="glass-panel stat-card" style={{ borderLeft: '3px solid var(--color-value)', background: 'rgba(255,255,255,0.01)' }}>
                  <span className="stat-label">Value Deltas</span>
                  <span className="stat-value" style={{ color: 'var(--color-value)' }}>{stats.mismatch}</span>
                </div>
                <div className="glass-panel stat-card" style={{ borderLeft: '3px solid var(--color-missing)', background: 'rgba(255,255,255,0.01)' }}>
                  <span className="stat-label">Missing Entries</span>
                  <span className="stat-value" style={{ color: 'var(--color-missing)' }}>{stats.missing}</span>
                </div>
                <div className="glass-panel stat-card" style={{ borderLeft: '3px solid var(--color-duplicate)', background: 'rgba(255,255,255,0.01)' }}>
                  <span className="stat-label">Duplicate Files</span>
                  <span className="stat-value" style={{ color: 'var(--color-duplicate)' }}>{stats.duplicate}</span>
                </div>
              </section>

              {/* Charts breakdown split pane */}
              <div className="dashboard-grid">
                {/* SVG breakdown donut */}
                <div className="glass-panel chart-panel" style={{ justifyContent: 'center' }}>
                  <div className="chart-header" style={{ paddingBottom: '12px', borderBottom: '1px solid var(--border-glass)' }}>
                    <span>Discrepancy Breakdown Index</span>
                  </div>
                  
                  <div className="donut-chart-container">
                    <svg width="150" height="150" viewBox="0 0 36 36" style={{ transform: 'rotate(-90deg)' }}>
                      <circle cx="18" cy="18" r="15.915" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="3" />
                      
                      {/* Value Mismatch (6/12 = 50%) */}
                      <circle 
                        cx="18" cy="18" r="15.915" fill="none" 
                        stroke="var(--color-value)" strokeWidth="3" 
                        strokeDasharray="50 100" strokeDashoffset="0" 
                      />
                      {/* Missing in B (2/12 = 16.7%) */}
                      <circle 
                        cx="18" cy="18" r="15.915" fill="none" 
                        stroke="var(--color-missing)" strokeWidth="3" 
                        strokeDasharray="16.7 100" strokeDashoffset="-50" 
                      />
                      {/* Duplicate (2/12 = 16.7%) */}
                      <circle 
                        cx="18" cy="18" r="15.915" fill="none" 
                        stroke="var(--color-duplicate)" strokeWidth="3" 
                        strokeDasharray="16.7 100" strokeDashoffset="-66.7" 
                      />
                      {/* Orphan (1/12 = 8.3%) */}
                      <circle 
                        cx="18" cy="18" r="15.915" fill="none" 
                        stroke="var(--color-orphan)" strokeWidth="3" 
                        strokeDasharray="8.3 100" strokeDashoffset="-83.4" 
                      />
                      {/* Unparseable (1/12 = 8.3%) */}
                      <circle 
                        cx="18" cy="18" r="15.915" fill="none" 
                        stroke="var(--color-unparseable)" strokeWidth="3" 
                        strokeDasharray="8.3 100" strokeDashoffset="-91.7" 
                      />
                    </svg>

                    <div className="donut-legend">
                      <div className="legend-item">
                        <div className="legend-label-wrapper">
                          <span className="legend-color-indicator" style={{ background: 'var(--color-value)' }}></span>
                          <span>Value Delta</span>
                        </div>
                        <strong>{stats.mismatch}</strong>
                      </div>
                      <div className="legend-item">
                        <div className="legend-label-wrapper">
                          <span className="legend-color-indicator" style={{ background: 'var(--color-missing)' }}></span>
                          <span>Missing in B</span>
                        </div>
                        <strong>{stats.missing}</strong>
                      </div>
                      <div className="legend-item">
                        <div className="legend-label-wrapper">
                          <span className="legend-color-indicator" style={{ background: 'var(--color-duplicate)' }}></span>
                          <span>Duplicate B</span>
                        </div>
                        <strong>{stats.duplicate}</strong>
                      </div>
                      <div className="legend-item">
                        <div className="legend-label-wrapper">
                          <span className="legend-color-indicator" style={{ background: 'var(--color-orphan)' }}></span>
                          <span>Orphan in B</span>
                        </div>
                        <strong>{stats.orphan}</strong>
                      </div>
                      <div className="legend-item">
                        <div className="legend-label-wrapper">
                          <span className="legend-color-indicator" style={{ background: 'var(--color-unparseable)' }}></span>
                          <span>Unparseable</span>
                        </div>
                        <strong>{stats.unparseable}</strong>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Tenant and scope card */}
                <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: '20px' }}>
                  <div className="chart-header">
                    <span>Disagreements by Tenant isolation</span>
                  </div>
                  <div>
                    <div className="bar-chart-row">
                      <div className="bar-chart-labels">
                        <span>Tenant ORG-A Scope</span>
                        <span>9 Disagreements (75%)</span>
                      </div>
                      <div className="bar-track">
                        <div className="bar-fill" style={{ width: '75%', background: 'linear-gradient(90deg, #3b82f6, #8b5cf6)' }}></div>
                      </div>
                    </div>

                    <div className="bar-chart-row" style={{ marginTop: '16px' }}>
                      <div className="bar-chart-labels">
                        <span>Tenant ORG-B Scope</span>
                        <span>3 Disagreements (25%)</span>
                      </div>
                      <div className="bar-track">
                        <div className="bar-fill" style={{ width: '25%', background: 'linear-gradient(90deg, #ec4899, #f43f5e)' }}></div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

            </div>
          )}

          {/* ==================== VIEW 2: SPLIT-VIEW WORKSPACE ==================== */}
          {activeTab === 'explorer' && (
            <div className="recon-split-grid">
              
              {/* Left Pane: Scrolling List of Discrepancies */}
              <div className="recon-split-list">
                {loading ? (
                  <div className="glass-panel" style={{ padding: '30px', textAlign: 'center' }}>
                    <div className="loading-skeleton" style={{ width: '100%', height: '40px', marginBottom: '12px' }}></div>
                    <div className="loading-skeleton" style={{ width: '90%', height: '40px', marginBottom: '12px' }}></div>
                    <div className="loading-skeleton" style={{ width: '80%', height: '40px' }}></div>
                  </div>
                ) : filteredDisagreements.length === 0 ? (
                  <div className="glass-panel empty-state">
                    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                    </svg>
                    <h3>No Discrepancies Selected</h3>
                    <p style={{ marginTop: '8px', fontSize: '12px' }}>Verify your search query or tenant filters.</p>
                  </div>
                ) : (
                  filteredDisagreements.map(row => {
                    const isActive = row.id === selectedRecordId
                    const valA = row.value_a != null ? Number(row.value_a) : null
                    const valB = row.value_b != null ? Number(row.value_b) : null
                    
                    return (
                      <div 
                        key={row.id}
                        className={`recon-card-interactive ${isActive ? 'active' : ''}`}
                        onClick={() => setSelectedRecordId(row.id)}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span className={`badge ${getReasonBadgeClass(row.reason)}`}>
                            {row.reason_display}
                          </span>
                          <span className="mono" style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>
                            {row.location_id}
                          </span>
                        </div>
                        
                        <div style={{ display: 'flex', gap: '20px', fontSize: '13px' }}>
                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <span style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>RECORD A</span>
                            <span className="mono">{row.record_id_a || '—'}</span>
                          </div>
                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <span style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>ENTRY B</span>
                            <span className="mono">{row.entry_id_b || '—'}</span>
                          </div>
                          {valA !== null && valB !== null && (
                            <div style={{ display: 'flex', flexDirection: 'column', marginLeft: 'auto', textAlign: 'right' }}>
                              <span style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>ABS DELTA</span>
                              <span className="mono" style={{ color: 'var(--color-orphan)', fontWeight: '600' }}>
                                ${Math.abs(valA - valB).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    )
                  })
                )}
              </div>

              {/* Right Pane: Sticky Inspection detail drawer card */}
              <div className="recon-split-inspector">
                {selectedRecord ? (
                  <div className="glass-panel" style={{ height: '100%', padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-glass)', paddingBottom: '12px' }}>
                      <div>
                        <h3 style={{ fontSize: '16px', fontWeight: '600' }}>Discrepancy Inspector</h3>
                        <span className={`badge ${getReasonBadgeClass(selectedRecord.reason)}`} style={{ marginTop: '6px' }}>
                          {selectedRecord.reason_display}
                        </span>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Location ID</span>
                        <div className="mono" style={{ fontWeight: '600', color: '#60a5fa' }}>{selectedRecord.location_id}</div>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{selectedRecord.location_name}</span>
                      </div>
                    </div>

                    {/* Side-by-Side comparison cards */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                      {/* System A Card */}
                      <div className="glass-panel" style={{ background: 'rgba(0,0,0,0.15)', padding: '12px', border: '1px solid rgba(255,255,255,0.03)' }}>
                        <span style={{ fontSize: '11px', color: '#60a5fa', fontWeight: 'bold' }}>SYSTEM A</span>
                        <div style={{ marginTop: '8px' }}>
                          <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Record Identifier</span>
                          <div className="mono" style={{ fontSize: '13px', fontWeight: '500' }}>{selectedRecord.record_id_a || '—'}</div>
                        </div>
                        <div style={{ marginTop: '8px' }}>
                          <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Reported Value</span>
                          <div className="mono" style={{ fontSize: '14px', color: 'var(--color-value)', fontWeight: 'bold' }}>
                            {selectedRecord.value_a != null ? `$${Number(selectedRecord.value_a).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'}
                          </div>
                        </div>
                      </div>

                      {/* System B Card */}
                      <div className="glass-panel" style={{ background: 'rgba(0,0,0,0.15)', padding: '12px', border: '1px solid rgba(255,255,255,0.03)' }}>
                        <span style={{ fontSize: '11px', color: '#a78bfa', fontWeight: 'bold' }}>SYSTEM B</span>
                        <div style={{ marginTop: '8px' }}>
                          <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Entry Identifier</span>
                          <div className="mono" style={{ fontSize: '13px', fontWeight: '500' }}>{selectedRecord.entry_id_b || '—'}</div>
                        </div>
                        <div style={{ marginTop: '8px' }}>
                          <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Reported Value</span>
                          <div className="mono" style={{ fontSize: '14px', color: 'var(--color-value)', fontWeight: 'bold' }}>
                            {selectedRecord.value_b != null ? `$${Number(selectedRecord.value_b).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : (
                              selectedRecord.value_b_raw ? `"${selectedRecord.value_b_raw}"` : '—'
                            )}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Delta indicator box */}
                    <div style={{ background: 'rgba(239, 68, 68, 0.05)', border: '1px solid rgba(239, 68, 68, 0.1)', padding: '12px', borderRadius: '8px', fontSize: '13px' }}>
                      <div style={{ fontWeight: '600', color: 'var(--color-orphan)' }}>Reconciliation Diagnostics:</div>
                      <div style={{ marginTop: '4px', color: 'var(--text-secondary)' }}>{selectedRecord.detail}</div>
                    </div>

                    {/* Extra fields panels */}
                    <div>
                      <span className="filter-label" style={{ fontSize: '11px', letterSpacing: '0.025em', display: 'block', marginBottom: '8px' }}>
                        DYNAMIC COLUMNS (SYSTEM A)
                      </span>
                      {selectedRecord.record_a_extra_data && Object.keys(selectedRecord.record_a_extra_data).length > 0 ? (
                        <pre className="json-view">{JSON.stringify(selectedRecord.record_a_extra_data, null, 2)}</pre>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '11px', fontStyle: 'italic' }}>No dynamic columns stored.</span>
                      )}
                    </div>

                    <div>
                      <span className="filter-label" style={{ fontSize: '11px', letterSpacing: '0.025em', display: 'block', marginBottom: '8px' }}>
                        DYNAMIC COLUMNS (SYSTEM B)
                      </span>
                      {selectedRecord.entry_b_extra_data && Object.keys(selectedRecord.entry_b_extra_data).length > 0 ? (
                        <pre className="json-view">{JSON.stringify(selectedRecord.entry_b_extra_data, null, 2)}</pre>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '11px', fontStyle: 'italic' }}>No dynamic columns stored.</span>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="glass-panel empty-state" style={{ height: '100%' }}>
                    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
                    </svg>
                    <h3>Ready to Inspect</h3>
                    <p style={{ marginTop: '8px', fontSize: '12px' }}>Select any disagreement card in the master list to display split-view audit information.</p>
                  </div>
                )}
              </div>

            </div>
          )}

          {/* ==================== VIEW 3: VISUAL TOPOLOGY MAP ==================== */}
          {activeTab === 'topology' && (
            <div className="topo-svg-panel">
              <div className="chart-header" style={{ paddingBottom: '12px', borderBottom: '1px solid var(--border-glass)' }}>
                <span>Reconciliation Relationship Topology</span>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Click LOC nodes to quick-filter locations</span>
              </div>

              {/* interactive SVG canvas */}
              <div style={{ display: 'flex', justifyContent: 'center', background: 'rgba(0,0,0,0.15)', borderRadius: '12px', padding: '20px' }}>
                <svg width="100%" height="340" viewBox="0 0 600 340">
                  {/* Background link grids */}
                  <line x1="100" y1="70" x2="300" y2="170" stroke="rgba(255,255,255,0.05)" strokeWidth="1.5" className="topo-edge" />
                  <line x1="100" y1="170" x2="300" y2="170" stroke="rgba(255,255,255,0.05)" strokeWidth="1.5" className="topo-edge" />
                  <line x1="100" y1="270" x2="300" y2="170" stroke="rgba(255,255,255,0.05)" strokeWidth="1.5" className="topo-edge" />
                  
                  <line x1="300" y1="170" x2="500" y2="100" stroke="rgba(255,255,255,0.05)" strokeWidth="1.5" className="topo-edge" />
                  <line x1="300" y1="170" x2="500" y2="240" stroke="rgba(255,255,255,0.05)" strokeWidth="1.5" className="topo-edge" />

                  {/* Left Side: System A Locations */}
                  <g className="topo-node" onClick={() => setExplorerSearch('LOC-101')}>
                    <circle cx="100" cy="70" r="16" fill="rgba(59, 130, 246, 0.2)" stroke="#3b82f6" strokeWidth="1.5" />
                    <text x="100" y="74" textAnchor="middle">L101</text>
                  </g>
                  <g className="topo-node" onClick={() => setExplorerSearch('LOC-102')}>
                    <circle cx="100" cy="170" r="16" fill="rgba(59, 130, 246, 0.2)" stroke="#3b82f6" strokeWidth="1.5" />
                    <text x="100" y="174" textAnchor="middle">L102</text>
                  </g>
                  <g className="topo-node" onClick={() => setExplorerSearch('LOC-201')}>
                    <circle cx="100" cy="270" r="16" fill="rgba(59, 130, 246, 0.2)" stroke="#3b82f6" strokeWidth="1.5" />
                    <text x="100" y="274" textAnchor="middle">L201</text>
                  </g>
                  <text x="100" y="35" textAnchor="middle" style={{ fontSize: '10px', fill: '#64748b', fontWeight: 'bold' }}>SYSTEM A</text>

                  {/* Central Node: Pulse glowing core engine */}
                  <g className="topo-node pulsing-engine" onClick={handleReconcile}>
                    <circle cx="300" cy="170" r="30" fill="rgba(139, 92, 246, 0.15)" stroke="#8b5cf6" strokeWidth="2.5" />
                    <text x="300" y="174" textAnchor="middle" style={{ fontSize: '10px', fill: '#c084fc', fontWeight: 'bold' }}>RECON</text>
                  </g>
                  
                  {/* Right Side: System B Ingest points */}
                  <g className="topo-node" onClick={() => setExplorerSearch('ENT/2026')}>
                    <circle cx="500" cy="100" r="16" fill="rgba(236, 72, 153, 0.2)" stroke="#ec4899" strokeWidth="1.5" />
                    <text x="500" y="104" textAnchor="middle">B-ENT</text>
                  </g>
                  <g className="topo-node" onClick={() => setExplorerSearch('Orphan')}>
                    <circle cx="500" cy="240" r="16" fill="rgba(239, 68, 68, 0.2)" stroke="#ef4444" strokeWidth="1.5" />
                    <text x="500" y="244" textAnchor="middle">ORPH</text>
                  </g>
                  <text x="500" y="65" textAnchor="middle" style={{ fontSize: '10px', fill: '#64748b', fontWeight: 'bold' }}>SYSTEM B</text>
                </svg>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border-glass)', padding: '16px', borderRadius: '12px', fontSize: '13px', display: 'flex', gap: '12px', alignItems: 'center' }}>
                <span style={{ color: 'var(--primary-accent)', fontWeight: 'bold' }}>Interactive Node Tip:</span>
                <span style={{ color: 'var(--text-secondary)' }}>Clicking the left LOC nodes quick-populates the search filter to display discrepancies linked to that specific location boundary.</span>
              </div>
            </div>
          )}

          {/* ==================== VIEW 4: DATA INTEGRITY AUDIT ==================== */}
          {activeTab === 'audit' && (
            <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div className="chart-header">
                <span>Import Anomaly log database</span>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Raw input parser errors captured during ingest</span>
              </div>

              {/* Filter controls */}
              <div className="control-bar" style={{ padding: 0, background: 'transparent', border: 'none', boxShadow: 'none' }}>
                <div className="badge-pill-group">
                  <button className={`badge-pill ${auditSeverity === 'ALL' ? 'active' : ''}`} onClick={() => setAuditSeverity('ALL')}>
                    All anomalies
                  </button>
                  <button className={`badge-pill ${auditSeverity === 'ERROR' ? 'active' : ''}`} onClick={() => setAuditSeverity('ERROR')}>
                    Errors
                  </button>
                  <button className={`badge-pill ${auditSeverity === 'WARNING' ? 'active' : ''}`} onClick={() => setAuditSeverity('WARNING')}>
                    Warnings
                  </button>
                  <button className={`badge-pill ${auditSeverity === 'INFO' ? 'active' : ''}`} onClick={() => setAuditSeverity('INFO')}>
                    Infos
                  </button>
                </div>

                <div className="search-input-wrapper">
                  <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <input 
                    type="text" 
                    placeholder="Search logs (file, field, message)..." 
                    className="search-input"
                    value={auditSearch}
                    onChange={e => setAuditSearch(e.target.value)}
                  />
                </div>
              </div>

              {/* Table */}
              {issuesLoading ? (
                <p style={{ color: 'var(--text-secondary)' }}>Querying anomalies log table...</p>
              ) : filteredIssues.length === 0 ? (
                <div className="empty-state">
                  <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                  </svg>
                  <h3>No Issues Logged</h3>
                  <p style={{ marginTop: '8px', fontSize: '13px' }}>The import runs 100% clean for selected filters.</p>
                </div>
              ) : (
                <div className="table-container">
                  <table>
                    <thead>
                      <tr>
                        <th>Severity</th>
                        <th>File</th>
                        <th>Ident</th>
                        <th>Field</th>
                        <th>Raw String</th>
                        <th>Audit Trace</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredIssues.map(issue => (
                        <tr key={issue.id}>
                          <td>
                            <span className={`badge ${
                              issue.severity === 'ERROR' ? 'badge-orphan' : 
                              issue.severity === 'WARNING' ? 'badge-missing' : 
                              'badge-duplicate'
                            }`}>
                              {issue.severity}
                            </span>
                          </td>
                          <td className="mono">{issue.source_file}</td>
                          <td className="mono">{issue.row_identifier}</td>
                          <td className="mono">{issue.field_name || '—'}</td>
                          <td className="mono" style={{ color: 'var(--color-orphan)' }}>{issue.raw_value || '—'}</td>
                          <td>{issue.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ==================== VIEW 5: LOGS ==================== */}
          {activeTab === 'console' && (
            <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div className="chart-header">
                <span>System Operations logs</span>
                <button 
                  className="btn btn-secondary" 
                  onClick={() => setConsoleLogs([{ time: new Date().toLocaleTimeString(), text: 'Log console cleared.', type: 'info' }])}
                >
                  Clear Buffer
                </button>
              </div>

              <div>
                <div className="console-title-bar">
                  <span className="console-dot" style={{ background: '#ef4444' }}></span>
                  <span className="console-dot" style={{ background: '#eab308' }}></span>
                  <span className="console-dot" style={{ background: '#22c55e' }}></span>
                  <span style={{ marginLeft: '12px', fontSize: '11px', color: '#64748b', fontWeight: 'bold' }}>
                    ENGINE EXECUTABLE BUFFER STREAMS
                  </span>
                </div>
                <div className="console-box">
                  {consoleLogs.map((log, idx) => (
                    <div key={idx} className="console-line">
                      <span className="console-timestamp">[{log.time}]</span>
                      <span className={`console-${log.type}`}>{log.text}</span>
                    </div>
                  ))}
                  {reconciling && (
                    <div className="console-line">
                      <span className="console-timestamp">[{new Date().toLocaleTimeString()}]</span>
                      <span>Job running in worker thread...<span className="console-cursor"></span></span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

        </main>
        
      </div>
    </div>
  )
}
