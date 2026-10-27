import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { apiFetch } from './api'
import AssessmentPanel from './AssessmentPanel'
import ClaimHistoryPanel from './ClaimHistoryPanel'
import ClaimStatusPanel from './ClaimStatusPanel'
import ClaimVerificationPanel from './ClaimVerificationPanel'
import DocumentPanel from './DocumentPanel'
import MessagesPanel from './MessagesPanel'
import type { ClaimSummary } from './types'

interface ClaimViewProps {
  token: string
  claimId: string
  loadTrigger?: number
  role: string
  onClaimIdChange: (claimId: string) => void
  onUnauthorized: () => void
}

type LoadState = 'idle' | 'loading' | 'loaded'

function isClaimSummary(value: unknown): value is ClaimSummary {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    typeof value.id === 'string' &&
    'reference' in value &&
    typeof value.reference === 'string' &&
    'business_id' in value &&
    typeof value.business_id === 'string' &&
    'policy_id' in value &&
    typeof value.policy_id === 'string' &&
    'equipment_id' in value &&
    typeof value.equipment_id === 'string' &&
    'status' in value &&
    typeof value.status === 'string' &&
    'incident_date' in value &&
    typeof value.incident_date === 'string' &&
    'amount_claimed' in value &&
    typeof value.amount_claimed === 'string'
  )
}

function ClaimView({
  token,
  claimId,
  loadTrigger = 0,
  role,
  onClaimIdChange,
  onUnauthorized,
}: ClaimViewProps) {
  const [loadState, setLoadState] = useState<LoadState>('idle')
  const [claim, setClaim] = useState<ClaimSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [detailRefreshKey, setDetailRefreshKey] = useState(0)

  const fetchClaim = useCallback(
    async (id: string): Promise<ClaimSummary | null> => {
      const response = await apiFetch(
        `/api/claims/${encodeURIComponent(id)}`,
        {},
        token,
      )
      if (response.status === 401) {
        onUnauthorized()
        return null
      }
      if (response.status === 403) {
        setError('Your role is not permitted to view this claim.')
        return null
      }
      if (response.status === 404) {
        setError('Claim not found or not visible to you.')
        return null
      }
      if (!response.ok) {
        setError('Could not load claim.')
        return null
      }
      const payload: unknown = await response.json()
      if (!isClaimSummary(payload)) {
        setError('Could not load claim.')
        return null
      }
      return payload
    },
    [token, onUnauthorized],
  )

  const loadClaimById = useCallback(
    async (rawId: string) => {
      const id = rawId.trim()
      if (!id) {
        setClaim(null)
        setError('Enter a claim id.')
        return
      }

      setLoadState('loading')
      setClaim(null)
      setError(null)

      try {
        const loaded = await fetchClaim(id)
        if (loaded !== null) {
          setClaim(loaded)
          setDetailRefreshKey((key) => key + 1)
          setLoadState('loaded')
        }
      } catch {
        setError('API unreachable')
      } finally {
        setLoadState((current) => (current === 'loading' ? 'idle' : current))
      }
    },
    [fetchClaim],
  )

  useEffect(() => {
    const id = claimId.trim()
    if (loadTrigger === 0 || !id) {
      return
    }
    let cancelled = false
    const run = async () => {
      try {
        const loaded = await fetchClaim(id)
        if (cancelled) return
        if (loaded !== null) {
          setClaim(loaded)
          setError(null)
          setDetailRefreshKey((key) => key + 1)
          setLoadState('loaded')
        }
      } catch {
        if (!cancelled) {
          setError('API unreachable')
        }
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [loadTrigger, claimId, fetchClaim])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await loadClaimById(claimId)
  }

  const refreshClaim = async () => {
    if (claim === null) return
    try {
      const loaded = await fetchClaim(claim.id)
      if (loaded !== null) {
        setClaim(loaded)
        setDetailRefreshKey((key) => key + 1)
      }
    } catch {
      setError('API unreachable')
    }
  }

  return (
    <section className="es-workspace-section">
      <div className="es-card">
        <form className="es-inline-form" onSubmit={handleSubmit}>
          <div className="es-field-grow">
            <label htmlFor="claim-id">Claim id</label>
            <input
              id="claim-id"
              type="text"
              value={claimId}
              onChange={(event) => onClaimIdChange(event.target.value)}
            />
          </div>
          <button type="submit" disabled={loadState === 'loading'}>
            Load claim
          </button>
        </form>

        {loadState === 'loading' && <p role="status">Loading claim…</p>}
        {error !== null && <p role="alert">{error}</p>}
      </div>

      {claim !== null && (
        <>
          <section className="es-card">
            <div className="es-card-header">
              <h2>Claim (simulated data)</h2>
            </div>
            <dl className="es-dl-grid">
              <div>
                <dt>Reference</dt>
                <dd>{claim.reference}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{claim.status}</dd>
              </div>
              <div>
                <dt>Incident date</dt>
                <dd>{claim.incident_date}</dd>
              </div>
              <div>
                <dt>Amount claimed</dt>
                <dd>{claim.amount_claimed}</dd>
              </div>
              <div>
                <dt>Equipment id</dt>
                <dd>{claim.equipment_id}</dd>
              </div>
              <div>
                <dt>Policy id</dt>
                <dd>{claim.policy_id}</dd>
              </div>
            </dl>
          </section>

          <ClaimVerificationPanel
            claimId={claim.id}
            token={token}
            role={role}
            refreshKey={detailRefreshKey}
            onUnauthorized={onUnauthorized}
          />

          <ClaimHistoryPanel
            claimId={claim.id}
            token={token}
            refreshKey={detailRefreshKey}
            onUnauthorized={onUnauthorized}
          />

          <div className="es-panels-grid">
            <ClaimStatusPanel
              claimId={claim.id}
              status={claim.status}
              token={token}
              role={role}
              onUnauthorized={onUnauthorized}
              onChanged={refreshClaim}
            />
            <DocumentPanel
              claimId={claim.id}
              token={token}
              onUnauthorized={onUnauthorized}
              onUploaded={refreshClaim}
            />
            <AssessmentPanel
              claimId={claim.id}
              token={token}
              role={role}
              onUnauthorized={onUnauthorized}
            />
            <MessagesPanel
              claimId={claim.id}
              token={token}
              onUnauthorized={onUnauthorized}
            />
          </div>
        </>
      )}
    </section>
  )
}

export default ClaimView
