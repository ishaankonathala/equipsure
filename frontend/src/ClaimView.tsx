import { useState, type FormEvent } from 'react'

import { apiFetch } from './api'
import AssessmentPanel from './AssessmentPanel'
import DocumentPanel from './DocumentPanel'
import type { ClaimSummary } from './types'

interface ClaimViewProps {
  token: string
  claimId: string
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
  role,
  onClaimIdChange,
  onUnauthorized,
}: ClaimViewProps) {
  const [loadState, setLoadState] = useState<LoadState>('idle')
  const [claim, setClaim] = useState<ClaimSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const id = claimId.trim()
    if (!id) {
      setClaim(null)
      setError('Enter a claim id.')
      return
    }

    setLoadState('loading')
    setClaim(null)
    setError(null)

    try {
      const response = await apiFetch(
        `/api/claims/${encodeURIComponent(id)}`,
        {},
        token,
      )
      if (response.status === 401) {
        onUnauthorized()
        return
      }
      if (response.status === 404) {
        setError('Claim not found or not visible to you.')
        return
      }
      if (!response.ok) {
        setError('Could not load claim.')
        return
      }

      const payload: unknown = await response.json()
      if (!isClaimSummary(payload)) {
        setError('Could not load claim.')
        return
      }
      setClaim(payload)
      setLoadState('loaded')
    } catch {
      setError('API unreachable')
    } finally {
      setLoadState((current) => (current === 'loading' ? 'idle' : current))
    }
  }

  return (
    <section>
      <form onSubmit={handleSubmit}>
        <label htmlFor="claim-id">Claim id</label>
        <input
          id="claim-id"
          type="text"
          value={claimId}
          onChange={(event) => onClaimIdChange(event.target.value)}
        />
        <button type="submit" disabled={loadState === 'loading'}>
          Load claim
        </button>
      </form>

      {loadState === 'loading' && <p role="status">Loading claim…</p>}
      {error !== null && <p role="alert">{error}</p>}

      {claim !== null && (
        <>
          <section>
            <h2>Claim (simulated data)</h2>
            <dl>
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
          <DocumentPanel
            claimId={claim.id}
            token={token}
            onUnauthorized={onUnauthorized}
          />
          <AssessmentPanel
            claimId={claim.id}
            token={token}
            role={role}
            onUnauthorized={onUnauthorized}
          />
        </>
      )}
    </section>
  )
}

export default ClaimView