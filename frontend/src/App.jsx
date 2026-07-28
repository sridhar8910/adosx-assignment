import React, { useEffect, useState } from 'react'
import { fetchOrgs, fetchReasons, fetchDisagreements, fetchImportIssues, triggerReconcile } from './api'

export default function App() {
  const [orgs, setOrgs] = useState([])
  const [reasons, setReasons] = useState([])
  const [selectedOrg, setSelectedOrg] = useState('')
  const [selectedReason, setSelectedReason] = useState('')
  const [sort, setSort] = useState('reason')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [reconciling, setReconciling] = useState(false)
  const [reconcileSuccess, setReconcileSuccess] = useState(null)
  
  // Expanded rows state (keeps track of which disagreement IDs are expanded)
  const [expandedRows, setExpandedRows] = useState(new Set())

  // Import issues section
  const [showIssues, setShowIssues] = useState(false)
  const [issues, setIssues] = useState(null)
  const [issuesLoading, setIssuesLoading] = useState(false)

  // Load orgs and reasons on mount
  useEffect(() => {
    Promise.all([fetchOrgs(), fetchReasons()])
      .then(([o, r]) => {
        setOrgs(o)
        setReasons(r)
        if (o.length > 0) setSelectedOrg(o[0])
      })
      .catch(e => setError(e.message))
  }, [])

  // Fetch disagreements when filters change
  const loadData = () => {
    if (!selectedOrg) return
    setLoading(true)
    setError(null)
    fetchDisagreements({ org: selectedOrg, reason: selectedReason, sort })
      .then(d => {
        setData(d)
        setLoading(false)
      })
      .catch(e => {
        setError(e.message)
        setLoading(false)
      })
  }

  useEffect(() => {
    loadData()
  }, [selectedOrg, selectedReason, sort])

  // Fetch import issues
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

  const handleShowIssues = () => {
    setShowIssues(s => !s)
    if (!issues && !issuesLoading) {
      loadIssues()
    }
  }

  // Run reconciliation
  const handleReconcile = async () => {
    setReconciling(true)
    setReconcileSuccess(null)
    try {
      const res = await triggerReconcile()
      setReconcileSuccess(`Reconciliation completed. Found ${res.count} disagreement(s).`)
      loadData()
      if (showIssues) {
        loadIssues()
      }
      setTimeout(() => setReconcileSuccess(null), 5000)
    } catch (e) {
      setError(e.message)
    } finally {
      setReconciling(false)
    }
  }

  // Toggle row expansion
  const toggleRow = (id) => {
    const next = new Set(expandedRows)
    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
    }
    setExpandedRows(next)
  }

  function toggleSort(field) {
    setSort(prev => prev === field ? `-${field}` : field)
  }

  // Compute stat cards for current data
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

  return (
    <div className="container">
      {/* Upper header */}
      <header className="header">
        <div className="brand">
          <div className="brand-logo">Δ</div>
          <h1 className="brand-title">DealerOS Reconciliation</h1>
        </div>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          {reconcileSuccess && (
            <span style={{ color: '#10b981', fontSize: '13px', fontWeight: '500' }}>
              ✓ {reconcileSuccess}
            </span>
          )}
          <button 
            className="btn" 
            onClick={handleReconcile}
            disabled={reconciling}
          >
            {reconciling ? 'Running...' : 'Re-run Reconciliation'}
          </button>
        </div>
      </header>

      {/* Summary stats grid */}
      <section className="stats-grid">
        <div className="glass-panel stat-card">
          <span className="stat-label">Total Disagreements</span>
          <span className="stat-value">{stats.total}</span>
        </div>
        <div className="glass-panel stat-card" style={{ borderLeft: '3px solid var(--color-value)' }}>
          <span className="stat-label">Value Mismatches</span>
          <span className="stat-value" style={{ color: 'var(--color-value)' }}>{stats.mismatch}</span>
        </div>
        <div className="glass-panel stat-card" style={{ borderLeft: '3px solid var(--color-missing)' }}>
          <span className="stat-label">Missing in B</span>
          <span className="stat-value" style={{ color: 'var(--color-missing)' }}>{stats.missing}</span>
        </div>
        <div className="glass-panel stat-card" style={{ borderLeft: '3px solid var(--color-duplicate)' }}>
          <span className="stat-label">Duplicate in B</span>
          <span className="stat-value" style={{ color: 'var(--color-duplicate)' }}>{stats.duplicate}</span>
        </div>
        <div className="glass-panel stat-card" style={{ borderLeft: '3px solid var(--color-orphan)' }}>
          <span className="stat-label">Orphans in B</span>
          <span className="stat-value" style={{ color: 'var(--color-orphan)' }}>{stats.orphan}</span>
        </div>
      </section>

      {/* Filter and settings bar */}
      <section className="glass-panel control-bar">
        <div className="filters-group">
          <div className="filter-item">
            <span className="filter-label">Tenant Org</span>
            <select value={selectedOrg} onChange={e => setSelectedOrg(e.target.value)}>
              {orgs.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>

          <div className="filter-item">
            <span className="filter-label">Reconcile Reason</span>
            <select value={selectedReason} onChange={e => setSelectedReason(e.target.value)}>
              <option value="">All Reasons</option>
              {reasons.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </div>
        </div>

        <div style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
          Showing <strong>{stats.total}</strong> active disagreement record(s) for <strong>{selectedOrg}</strong>
        </div>
      </section>

      {error && (
        <div className="glass-panel" style={{ borderLeft: '4px solid var(--color-orphan)', background: 'rgba(239,68,68,0.05)' }}>
          <span style={{ color: 'var(--color-orphan)', fontWeight: '600' }}>Error:</span> {error}
        </div>
      )}

      {/* Disagreements table */}
      <section className="glass-panel" style={{ padding: '0px' }}>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th onClick={() => toggleSort('reason')}>
                  Disagreement Reason {sort === 'reason' ? '▲' : sort === '-reason' ? '▼' : ''}
                </th>
                <th>Record A</th>
                <th>Entry B</th>
                <th>Location</th>
                <th style={{ textAlign: 'right' }} onClick={() => toggleSort('value_a')}>
                  Value A {sort === 'value_a' ? '▲' : sort === '-value_a' ? '▼' : ''}
                </th>
                <th style={{ textAlign: 'right' }} onClick={() => toggleSort('value_b')}>
                  Value B {sort === 'value_b' ? '▲' : sort === '-value_b' ? '▼' : ''}
                </th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '40px' }}>
                    <div className="loading-skeleton" style={{ width: '100%', height: '24px', marginBottom: '8px' }}></div>
                    <div className="loading-skeleton" style={{ width: '80%', height: '24px', marginBottom: '8px' }}></div>
                    <div className="loading-skeleton" style={{ width: '60%', height: '24px' }}></div>
                  </td>
                </tr>
              ) : !data || data.results.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ padding: '0px' }}>
                    <div className="empty-state">
                      <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                      </svg>
                      <h3>No Disagreements Found</h3>
                      <p style={{ marginTop: '8px', fontSize: '13px' }}>System A and System B are fully in sync for the active filters.</p>
                    </div>
                  </td>
                </tr>
              ) : (
                data.results.map(row => {
                  const isExpanded = expandedRows.has(row.id)
                  const valA = row.value_a != null ? Number(row.value_a) : null
                  const valB = row.value_b != null ? Number(row.value_b) : null
                  
                  // Compute difference
                  let delta = null
                  if (valA !== null && valB !== null) {
                    delta = Math.abs(valA - valB)
                  }

                  return (
                    <React.Fragment key={row.id}>
                      <tr 
                        className={`table-row ${isExpanded ? 'expanded-row' : ''}`}
                        onClick={() => toggleRow(row.id)}
                      >
                        <td>
                          <span className={`badge ${getReasonBadgeClass(row.reason)}`}>
                            {row.reason_display}
                          </span>
                        </td>
                        <td className="mono">{row.record_id_a || '—'}</td>
                        <td className="mono">
                          {row.entry_id_b || '—'}
                          {row.record_ref_raw && row.record_ref_raw !== row.record_id_a && (
                            <div style={{ color: 'var(--text-secondary)', fontSize: '11px', marginTop: '2px' }}>
                              Ref: {row.record_ref_raw}
                            </div>
                          )}
                        </td>
                        <td className="mono">
                          {row.location_id}
                          <div style={{ color: 'var(--text-secondary)', fontSize: '11px', marginTop: '2px' }}>
                            {row.location_name}
                          </div>
                        </td>
                        <td className="mono" style={{ textAlign: 'right' }}>
                          {valA !== null ? `$${valA.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'}
                        </td>
                        <td className="mono" style={{ textAlign: 'right' }}>
                          {valB !== null ? (
                            `$${valB.toLocaleString('en-US', { minimumFractionDigits: 2 })}`
                          ) : row.value_b_raw ? (
                            <span style={{ color: 'var(--color-orphan)' }}>{row.value_b_raw}</span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td>
                          <button className="btn btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }}>
                            {isExpanded ? 'Hide Info' : 'Inspect'}
                          </button>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr>
                          <td colSpan={7} style={{ padding: '0px', background: 'rgba(0,0,0,0.15)' }}>
                            <div className="detail-drawer">
                              
                              {/* Left Column: System A Record */}
                              <div className="drawer-column">
                                <h4 className="drawer-column-title">System A Record Details</h4>
                                {row.record_id_a ? (
                                  <div className="detail-grid">
                                    <span className="detail-label">Record ID:</span>
                                    <span className="detail-value mono">{row.record_id_a}</span>
                                    
                                    <span className="detail-label">Location:</span>
                                    <span className="detail-value">{row.location_id} ({row.location_name})</span>
                                    
                                    <span className="detail-label">Value:</span>
                                    <span className="detail-value mono">
                                      {valA !== null ? `$${valA.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'}
                                    </span>

                                    {/* Extra data / Dynamic columns (1 lakh support) */}
                                    <span className="detail-label" style={{ gridColumn: '1 / -1', marginTop: '8px' }}>
                                      Dynamic Columns / Extra Data:
                                    </span>
                                    <div style={{ gridColumn: '1 / -1' }}>
                                      {row.record_a_extra_data && Object.keys(row.record_a_extra_data).length > 0 ? (
                                        <pre className="json-view">
                                          {JSON.stringify(row.record_a_extra_data, null, 2)}
                                        </pre>
                                      ) : (
                                        <span style={{ color: 'var(--text-muted)', fontSize: '12px', fontStyle: 'italic' }}>
                                          No extra columns in System A.
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                ) : (
                                  <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '13px' }}>
                                    No System A record associated with this entry.
                                  </div>
                                )}
                              </div>

                              {/* Right Column: System B Entry */}
                              <div className="drawer-column">
                                <h4 className="drawer-column-title">System B Entry Details</h4>
                                {row.entry_id_b ? (
                                  <div className="detail-grid">
                                    <span className="detail-label">Entry ID:</span>
                                    <span className="detail-value mono">{row.entry_id_b}</span>
                                    
                                    <span className="detail-label">Record Ref (Raw):</span>
                                    <span className="detail-value mono">{row.record_ref_raw || '—'}</span>

                                    <span className="detail-label">Value:</span>
                                    <span className="detail-value mono">
                                      {valB !== null ? `$${valB.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : (
                                        row.value_b_raw ? `Unparseable: "${row.value_b_raw}"` : '—'
                                      )}
                                    </span>

                                    <span className="detail-label">Details/Difference:</span>
                                    <span className="detail-value">
                                      {row.detail}
                                      {delta !== null && (
                                        <div>
                                          <span className="delta-label delta-mismatch">
                                            Delta: ${delta.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                                          </span>
                                        </div>
                                      )}
                                    </span>

                                    {/* Extra data / Dynamic columns (1 lakh support) */}
                                    <span className="detail-label" style={{ gridColumn: '1 / -1', marginTop: '8px' }}>
                                      Dynamic Columns / Extra Data:
                                    </span>
                                    <div style={{ gridColumn: '1 / -1' }}>
                                      {row.entry_b_extra_data && Object.keys(row.entry_b_extra_data).length > 0 ? (
                                        <pre className="json-view">
                                          {JSON.stringify(row.entry_b_extra_data, null, 2)}
                                        </pre>
                                      ) : (
                                        <span style={{ color: 'var(--text-muted)', fontSize: '12px', fontStyle: 'italic' }}>
                                          No extra columns in System B.
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                ) : (
                                  <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '13px' }}>
                                    No System B entry associated with this record.
                                  </div>
                                )}
                              </div>

                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Import Issues panel */}
      <section className="glass-panel import-issues-log">
        <button 
          className="btn btn-secondary" 
          onClick={handleShowIssues}
          style={{ width: '100%', justifyContent: 'space-between' }}
        >
          <span>{showIssues ? '▼' : '▶'} Import Anomaly & Data Audit Logs</span>
          <span className="badge badge-unparseable">
            {issues ? issues.count : 'View'} Issues
          </span>
        </button>

        {showIssues && (
          <div style={{ marginTop: '20px' }}>
            {issuesLoading ? (
              <p style={{ color: 'var(--text-secondary)' }}>Loading logs...</p>
            ) : !issues || issues.results.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>No data import anomalies detected. Cleaner imports!</p>
            ) : (
              <div className="table-container" style={{ marginTop: '12px' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Severity</th>
                      <th>Source File</th>
                      <th>Row Ident</th>
                      <th>Field</th>
                      <th>Raw Value</th>
                      <th>Resolution Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {issues.results.map(issue => (
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
      </section>
    </div>
  )
}
