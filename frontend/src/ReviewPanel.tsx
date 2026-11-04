import { useState } from 'react'
import { apiFetch } from './api'

interface ReviewExplanationResponse {
  summary: string
  checks_commentary: string[]
  stated_amount: string
  advisory_only: boolean
}

interface ReviewDecisionResponse {
  claim_id: string
  new_status: string
  explanation: string
}

interface ReviewPanelProps {
  claimId: string
  role: string
  token: string
  onUnauthorized: () => void
  onChanged: () => void
}

function isReviewExplanationResponse(
  value: unknown,
): value is ReviewExplanationResponse {
  return (
    typeof value === 'object' &&
    value !== null &&
    'summary' in value &&
    typeof value.summary === 'string' &&
    'checks_commentary' in value &&
    Array.isArray(value.checks_commentary) &&
    value.checks_commentary.every((item) => typeof item === 'string') &&
    'stated_amount' in value &&
    typeof value.stated_amount === 'string' &&
    'advisory_only' in value &&
    typeof value.advisory_only === 'boolean'
  )
}

function isReviewDecisionResponse(
  value: unknown,
): value is ReviewDecisionResponse {
  return (
    typeof value === 'object' &&
    value !== null &&
    'claim_id' in value &&
    typeof value.claim_id === 'string' &&
    'new_status' in value &&
    typeof value.new_status === 'string' &&
    'explanation' in value &&
    typeof value.explanation === 'string'
  )
}

export default function ReviewPanel({
  claimId,
  role,
  token,
  onUnauthorized,
  onChanged,
}: ReviewPanelProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [explanation, setExplanation] =
    useState<ReviewExplanationResponse | null>(null)
  const [approvedAmount, setApprovedAmount] = useState('')
  const [reason, setReason] = useState('')

  if (role !== 'OPS' && role !== 'ADMIN') {
    return null
  }

  const fetchExplanation = async () => {
    setBusy(true)
    setError(null)
    setStatusMessage(null)

    try {
      const response = await apiFetch(
        `/api/claims/${encodeURIComponent(claimId)}/review-explanation`,
        { method: 'POST' },
        token,
      )

      if (response.status === 401) {
        onUnauthorized()
        return
      }
      if (response.status === 403) {
        setError('Your role cannot make this decision.')
        return
      }
      if (response.status === 422) {
        let detailText: string | null = null
        try {
          const body: unknown = await response.json()
          if (
            typeof body === 'object' &&
            body !== null &&
            'detail' in body &&
            typeof body.detail === 'string'
          ) {
            detailText = body.detail
          }
        } catch {
          // ignore
        }
        setError(detailText ?? 'The decision was not accepted.')
        return
      }
      if (!response.ok) {
        let detailText: string | null = null
        try {
          const body: unknown = await response.json()
          if (
            typeof body === 'object' &&
            body !== null &&
            'detail' in body &&
            typeof body.detail === 'string'
          ) {
            detailText = body.detail
          }
        } catch {
          // ignore
        }
        setError(detailText ?? 'Could not load review explanation.')
        return
      }

      const payload: unknown = await response.json()
      if (isReviewExplanationResponse(payload)) {
        setExplanation(payload)
        setApprovedAmount(payload.stated_amount)
      } else {
        setError('Unexpected explanation response.')
      }
    } catch {
      setError('API unreachable')
    } finally {
      setBusy(false)
    }
  }

  const handleDecision = async (decision: 'APPROVE' | 'REJECT') => {
    setBusy(true)
    setError(null)
    setStatusMessage(null)

    const payload =
      decision === 'APPROVE'
        ? {
            decision: 'APPROVE',
            approved_amount: approvedAmount.trim() || undefined,
            reason: reason.trim() || undefined,
          }
        : {
            decision: 'REJECT',
            reason: reason.trim() || undefined,
          }

    try {
      const response = await apiFetch(
        `/api/claims/${encodeURIComponent(claimId)}/review-decision`,
        {
          method: 'POST',
          body: JSON.stringify(payload),
        },
        token,
      )

      if (response.status === 401) {
        onUnauthorized()
        return
      }
      if (response.status === 403) {
        setError('Your role cannot make this decision.')
        return
      }
      if (response.status === 422) {
        let detailText: string | null = null
        try {
          const body: unknown = await response.json()
          if (
            typeof body === 'object' &&
            body !== null &&
            'detail' in body &&
            typeof body.detail === 'string'
          ) {
            detailText = body.detail
          }
        } catch {
          // ignore
        }
        setError(detailText ?? 'The decision was not accepted.')
        return
      }
      if (!response.ok) {
        setError('The decision was not accepted.')
        return
      }

      const data: unknown = await response.json()
      if (isReviewDecisionResponse(data)) {
        setStatusMessage(`Decision recorded: ${data.new_status}`)
      } else {
        setStatusMessage(`Decision recorded: ${decision}`)
      }
      onChanged()
    } catch {
      setError('API unreachable')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="es-card">
      <div className="es-card-header">
        <h2>Policy Review & Decision (OPS)</h2>
      </div>

      <button
        type="button"
        className="es-btn-primary"
        onClick={() => void fetchExplanation()}
        disabled={busy}
      >
        {busy ? 'Loading explanation…' : 'Get AI explanation'}
      </button>

      {explanation !== null && (
        <>
          {explanation.checks_commentary.length > 0 && (
            <div className="es-field-group">
              <label>Rule Checks</label>
              <ul
                style={{
                  listStyle: 'none',
                  paddingLeft: 0,
                  margin: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                }}
              >
                {explanation.checks_commentary.map((check, index) => (
                  <li
                    key={index}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                    }}
                  >
                    <span
                      aria-hidden="true"
                      style={{
                        color: check.startsWith('FAIL')
                          ? 'var(--status-err-text, #dc2626)'
                          : 'var(--status-ok-text, #16a34a)',
                        fontWeight: 'bold',
                      }}
                    >
                      {check.startsWith('FAIL') ? '✗' : '✓'}
                    </span>
                    <span>{check}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="es-field-group">
            <label>AI Explanation</label>
            <p style={{ margin: 0 }}>{explanation.summary}</p>
          </div>

          <div className="es-field-group">
            <label>Suggested Amount</label>
            <p style={{ margin: 0 }}>
              <strong>{explanation.stated_amount}</strong>
            </p>
          </div>

          <div className="es-field-group">
            <label htmlFor="review-approved-amount">Approved Amount</label>
            <input
              id="review-approved-amount"
              type="text"
              value={approvedAmount}
              onChange={(e) => setApprovedAmount(e.target.value)}
              disabled={busy}
            />
          </div>

          <div className="es-field-group">
            <label htmlFor="review-decision-reason">Reason</label>
            <input
              id="review-decision-reason"
              type="text"
              value={reason}
              placeholder="Required for rejection or if amount differs from suggestion"
              onChange={(e) => setReason(e.target.value)}
              disabled={busy}
            />
          </div>

          <div
            style={{
              display: 'flex',
              gap: '10px',
              marginTop: '4px',
              flexWrap: 'wrap',
            }}
          >
            <button
              type="button"
              className="es-btn-primary"
              onClick={() => void handleDecision('APPROVE')}
              disabled={busy}
            >
              {busy ? 'Processing…' : 'Approve'}
            </button>
            <button
              type="button"
              className="es-btn-danger"
              onClick={() => void handleDecision('REJECT')}
              disabled={busy}
            >
              {busy ? 'Processing…' : 'Reject'}
            </button>
          </div>
        </>
      )}

      {error !== null && <p role="alert">{error}</p>}
      {statusMessage !== null && <p role="status">{statusMessage}</p>}
    </section>
  )
}
