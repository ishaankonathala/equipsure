import { useEffect, useState } from 'react'
import { apiFetch } from './api'

interface ClaimRow {
  id: string
  reference: string
  status: string
  incident_date: string
  amount_claimed: string
}

interface ClaimListProps {
  token: string
  refreshKey?: number
  onUnauthorized: () => void
  onSelect: (claimId: string) => void
}

export default function ClaimList({
  token,
  refreshKey = 0,
  onUnauthorized,
  onSelect,
}: ClaimListProps) {
  const [claims, setClaims] = useState<ClaimRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const response = await apiFetch('/api/claims', {}, token)
        if (cancelled) return
        if (response.status === 401) {
          onUnauthorized()
          return
        }
        if (!response.ok) {
          setError('Could not load claims.')
          return
        }
        const data = (await response.json()) as ClaimRow[]
        if (cancelled) return
        setClaims(data)
        setError(null)
      } catch {
        if (!cancelled) setError('API unreachable')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [token, refreshKey, onUnauthorized])

  return (
    <section className="es-card">
      <div className="es-card-header">
        <h2>Your claims</h2>
      </div>
      {loading && <p role="status">Loading claims…</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !error && claims.length === 0 && <p>No claims yet.</p>}
      {claims.length > 0 && (
        <div className="es-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Reference</th>
                <th>Status</th>
                <th>Incident date</th>
                <th>Amount claimed</th>
              </tr>
            </thead>
            <tbody>
              {claims.map((claim) => (
                <tr key={claim.id} onClick={() => onSelect(claim.id)}>
                  <td>
                    <button type="button" onClick={() => onSelect(claim.id)}>
                      {claim.reference}
                    </button>
                  </td>
                  <td>
                    <span className="es-status-chip">{claim.status}</span>
                  </td>
                  <td>{claim.incident_date}</td>
                  <td>{claim.amount_claimed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}