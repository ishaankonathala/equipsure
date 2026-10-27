import { useState } from 'react'
import { apiFetch } from './api'

const ALLOWED_NEXT: Record<string, string[]> = {
  SUBMITTED: ['UNDER_VERIFICATION', 'WITHDRAWN'],
  UNDER_VERIFICATION: ['DOCUMENTS_REQUIRED', 'UNDER_REVIEW', 'WITHDRAWN'],
  DOCUMENTS_REQUIRED: ['UNDER_VERIFICATION', 'WITHDRAWN'],
  UNDER_REVIEW: ['INVESTIGATION_ASSIGNED', 'DECISION_PENDING', 'WITHDRAWN'],
  INVESTIGATION_ASSIGNED: ['DECISION_PENDING', 'WITHDRAWN'],
  DECISION_PENDING: ['APPROVED', 'REJECTED', 'WITHDRAWN'],
  APPROVED: [],
  REJECTED: ['CLOSED'],
  SETTLEMENT_IN_PROGRESS: [],
  SETTLED: ['CLOSED'],
  CLOSED: [],
  WITHDRAWN: [],
}

const OPEN_POLICYHOLDER_STATUSES = new Set([
  'SUBMITTED',
  'UNDER_VERIFICATION',
  'DOCUMENTS_REQUIRED',
  'UNDER_REVIEW',
  'INVESTIGATION_ASSIGNED',
  'DECISION_PENDING',
])

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

  const isOfficer = role === 'OPS' || role === 'ADMIN'
  const isPolicyholder = role === 'POLICYHOLDER'

  if (!isOfficer && !isPolicyholder) {
    return null
  }

  const submitTransition = async (chosenTarget: string) => {
    const trimmed = explanation.trim()
    if (!chosenTarget || !trimmed) {
      setMessage(
        isPolicyholder
          ? 'Enter a reason to withdraw this claim.'
          : 'Choose a next status and enter an explanation.',
      )
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      const response = await apiFetch(
        `/api/claims/${encodeURIComponent(claimId)}/status`,
        {
          method: 'POST',
          body: JSON.stringify({
            target_status: chosenTarget,
            explanation: trimmed,
          }),
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
        const body = (await response.json().catch(() => null)) as {
          detail?: string
        } | null
        setMessage(
          body?.detail ??
            'That status change is not allowed from the current status.',
        )
        return
      }
      if (!response.ok) {
        setMessage('Status change failed.')
        return
      }
      setTarget('')
      setExplanation('')
      setMessage(
        chosenTarget === 'WITHDRAWN' ? 'Claim withdrawn.' : 'Status updated.',
      )
      onChanged()
    } catch {
      setMessage('API unreachable')
    } finally {
      setBusy(false)
    }
  }

  if (isPolicyholder) {
    const canWithdraw = OPEN_POLICYHOLDER_STATUSES.has(status)
    return (
      <section className="es-card">
        <div className="es-card-header">
          <h2>Withdraw claim</h2>
        </div>
        <p>Current status: {status}</p>
        {!canWithdraw ? (
          <p>
            Claims in {status} status can no longer be withdrawn by the
            policyholder.
          </p>
        ) : (
          <>
            <div className="es-field-group">
              <label htmlFor="withdraw-explanation">Withdrawal reason </label>
              <input
                id="withdraw-explanation"
                type="text"
                maxLength={500}
                placeholder="e.g. Repair covered under manufacturer warranty"
                value={explanation}
                onChange={(event) => setExplanation(event.target.value)}
                disabled={busy}
              />
            </div>
            <button
              type="button"
              className="es-btn-primary"
              onClick={() => void submitTransition('WITHDRAWN')}
              disabled={busy}
            >
              {busy ? 'Withdrawing…' : 'Withdraw claim'}
            </button>
          </>
        )}
        {message && <p role="status">{message}</p>}
      </section>
    )
  }

  const options = ALLOWED_NEXT[status] ?? []
  const isSettlementManaged =
    status === 'APPROVED' || status === 'SETTLEMENT_IN_PROGRESS'

  return (
    <section className="es-card">
      <div className="es-card-header">
        <h2>Change status (OPS)</h2>
      </div>
      <p>Current status: {status}</p>
      {options.length === 0 ? (
        <p>
          {isSettlementManaged
            ? 'Use the Settlement tracking panel to initiate or complete settlement for this claim.'
            : `No further status changes are possible from ${status}.`}
        </p>
      ) : (
        <>
          <div className="es-field-group">
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
          <div className="es-field-group">
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
          <button
            type="button"
            className="es-btn-primary"
            onClick={() => void submitTransition(target)}
            disabled={busy}
          >
            {busy ? 'Saving…' : 'Change status'}
          </button>
        </>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  )
}
