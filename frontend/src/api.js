const BASE = '/api'

export async function fetchOrgs() {
  const res = await fetch(`${BASE}/orgs/`)
  if (!res.ok) throw new Error(`Failed to fetch orgs: ${res.status}`)
  return res.json()
}

export async function fetchReasons() {
  const res = await fetch(`${BASE}/reasons/`)
  if (!res.ok) throw new Error(`Failed to fetch reasons: ${res.status}`)
  return res.json()
}

export async function fetchDisagreements({ org, reason = '', sort = 'reason' }) {
  const params = new URLSearchParams({ org, sort })
  if (reason) params.set('reason', reason)
  const res = await fetch(`${BASE}/disagreements/?${params}`)
  if (!res.ok) throw new Error(`Failed to fetch disagreements: ${res.status}`)
  return res.json()
}

export async function fetchImportIssues() {
  const res = await fetch(`${BASE}/import-issues/`)
  if (!res.ok) throw new Error(`Failed to fetch import issues: ${res.status}`)
  return res.json()
}

export async function triggerReconcile() {
  const res = await fetch(`${BASE}/reconcile/`, { method: 'POST' })
  if (!res.ok) throw new Error(`Failed to trigger reconciliation: ${res.status}`)
  return res.json()
}
