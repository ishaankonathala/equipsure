import { useState } from 'react'
import { apiFetch } from './api'

const ALLOWED_NEXT: Record<string, string[]> = {
  SUBMITTED: ['UNDER_VERIFICATION', 'WITHDRAWN'],
  UNDER_VERIFICATION: ['DOCUMENTS_REQUIRED', 'UNDER_REVIEW', 'WITHDRAWN'],
  DOCUMENTS_REQUIRED: ['UNDER_VERIFICATION', 'WITHDRAWN'],
  UNDER_REVIEW: ['INVESTIGATION_ASSIGNED', 'DECISION_PENDING', 'WITHDRAWN'],
  INVESTIGATION_ASSIGNED: ['DECISION_PENDING', 'WITHDRAWN'],
  DECISION_PENDING: ['APPROVED', 'REJECTED', 'WITHDRAWN'],
  APPROVED: ['SETTLEMENT_IN_PROGRESS'],
  REJECTED: ['CLOSED'],
  SETTLEMENT_IN_PROGRESS: ['SETTLED'],
  SETTLED: ['CLOSED'],
  CLOSED: [],
  WITHDRAWN: [],
}

interface ClaimStatusPanelProps {
  claimId: string
  status: string
  token: string
  role: string
  onUnauthorized: () => void
  onChanged: () => void
}

export default function ClaimStatusPanel({
  claimId,
  status,
  token,
  role,
  onUnauthorized,
  onChanged,
}: ClaimStatusPanelProps) {
  const [target, setTarget] = useState<string>('')
  const [explanation, setExplanation] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  if (role !== 'OPS' && role !== 'ADMIN') {
    return null
  }

  const options = ALLOWED_NEXT[status] ?? []

  const submit = async () => {
    const trimmed = explanation.trim()
    if (!target || !trimmed) {
      setMessage('Choose a next status and enter an explanation.')
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      const response = await apiFetch(
        `/api/claims/${claimId}/status`,
        {
          method: 'POST',
          body: JSON.stringify({ target_status: target, explanation: trimmed }),
        },
        token,
      )
      if (response.status === 401) {
        onUnauthorized()
        return
      }
      if (response.status === 403) {
        setMessage('Your role cannot change claim status.')
        return
      }
      if (response.status === 404) {
        setMessage('Claim not found or not visible to you.')
        return
      }
      if (response.status === 422) {
        setMessage('That status change is not allowed from the current status.')
        return
      }
      if (!response.ok) {
        setMessage('Status change failed.')
        return
      }
      setTarget('')
      setExplanation('')
      setMessage('Status updated.')
      onChanged()
    } catch {
      setMessage('API unreachable')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2>Change status (OPS)</h2>
      <p>Current status: {status}</p>
      {options.length === 0 ? (
        <p>No further status changes are possible from {status}.</p>
      ) : (
        <>
          <div>
            <label htmlFor="next-status">Next status </label>
            <select
              id="next-status"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              disabled={busy}
            >
              <option value="">Choose…</option>
              {options.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="status-explanation">Explanation </label>
            <input
              id="status-explanation"
              type="text"
              maxLength={500}
              value={explanation}
              onChange={(event) => setExplanation(event.target.value)}
              disabled={busy}
            />
          </div>
          <button type="button" onClick={submit} disabled={busy}>
            {busy ? 'Saving…' : 'Change status'}
          </button>
        </>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  )
}