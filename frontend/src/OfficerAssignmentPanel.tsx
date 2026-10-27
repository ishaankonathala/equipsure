import { useEffect, useState } from 'react'
import { apiFetch } from './api'

interface AssignableOfficer {
  id: string
  email: string
  full_name: string
  role: string
}

interface OfficerAssignmentPanelProps {
  claimId: string
  status: string
  assignedOfficerId?: string | null
  assignedOfficerName?: string | null
  assignedOfficerRole?: string | null
  assignedAt?: string | null
  token: string
  role: string
  onUnauthorized: () => void
  onAssigned: () => void
}

const TERMINAL_STATUSES = new Set([
  'REJECTED',
  'SETTLED',
  'CLOSED',
  'WITHDRAWN',
])

export default function OfficerAssignmentPanel({
  claimId,
  status,
  assignedOfficerId,
  assignedOfficerName,
  assignedOfficerRole,
  assignedAt,
  token,
  role,
  onUnauthorized,
  onAssigned,
}: OfficerAssignmentPanelProps) {
  const isOfficer = role === 'OPS' || role === 'ADMIN'
  const [officers, setOfficers] = useState<AssignableOfficer[]>([])
  const [selectedOfficerId, setSelectedOfficerId] = useState<string>(
    assignedOfficerId ?? '',
  )
  const [notes, setNotes] = useState('')
  const [moveToInvestigation, setMoveToInvestigation] = useState(true)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOfficer) {
      return
    }
    let cancelled = false
    const loadOfficers = async () => {
      try {
        const response = await apiFetch('/api/claims/officers', {}, token)
        if (cancelled) return
        if (response.status === 401) {
          onUnauthorized()
          return
        }
        if (!response.ok) {
          setLoadError('Could not load assignable officers.')
          return
        }
        const data = (await response.json()) as AssignableOfficer[]
        if (cancelled) return
        setOfficers(data)
        setLoadError(null)
        if (assignedOfficerId) {
          setSelectedOfficerId(assignedOfficerId)
        } else if (data.length > 0) {
          setSelectedOfficerId((prev) => prev || data[0].id)
        }
      } catch {
        if (!cancelled) {
          setLoadError('API unreachable')
        }
      }
    }
    void loadOfficers()
    return () => {
      cancelled = true
    }
  }, [isOfficer, token, assignedOfficerId, onUnauthorized])

  if (!isOfficer) {
    return null
  }

  const isTerminal = TERMINAL_STATUSES.has(status)

  const handleAssign = async () => {
    if (!selectedOfficerId) {
      setMessage('Select an officer or investigator to assign.')
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      const response = await apiFetch(
        `/api/claims/${encodeURIComponent(claimId)}/assignment`,
        {
          method: 'POST',
          body: JSON.stringify({
            officer_user_id: selectedOfficerId,
            notes: notes.trim() || null,
            move_to_investigation: moveToInvestigation,
          }),
        },
        token,
      )
      if (response.status === 401) {
        onUnauthorized()
        return
      }
      if (response.status === 403) {
        setMessage('Your role cannot assign claims.')
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
        setMessage(body?.detail ?? 'Assignment is not allowed for this claim.')
        return
      }
      if (!response.ok) {
        setMessage('Could not assign officer.')
        return
      }
      setNotes('')
      setMessage('Officer assignment saved.')
      onAssigned()
    } catch {
      setMessage('API unreachable')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="es-card">
      <div className="es-card-header">
        <h2>Officer &amp; investigator assignment (OPS)</h2>
      </div>
      <p>
        Current assignee:{' '}
        <strong>
          {assignedOfficerName
            ? `${assignedOfficerName}${assignedOfficerRole ? ` (${assignedOfficerRole})` : ''}`
            : 'Unassigned'}
        </strong>
        {assignedAt ? ` · Assigned ${new Date(assignedAt).toLocaleString()}` : ''}
      </p>
      {loadError && <p role="alert">{loadError}</p>}
      {isTerminal ? (
        <p>Assignment is locked because the claim is in {status} status.</p>
      ) : (
        <>
          <div className="es-field-group">
            <label htmlFor="assign-officer-select">Assign officer</label>
            <select
              id="assign-officer-select"
              value={selectedOfficerId}
              onChange={(event) => setSelectedOfficerId(event.target.value)}
              disabled={busy || officers.length === 0}
            >
              <option value="">Choose officer…</option>
              {officers.map((officer) => (
                <option key={officer.id} value={officer.id}>
                  {officer.full_name} ({officer.role} · {officer.email})
                </option>
              ))}
            </select>
          </div>
          <div className="es-field-group">
            <label htmlFor="assign-officer-notes">Assignment note (optional)</label>
            <input
              id="assign-officer-notes"
              type="text"
              maxLength={500}
              placeholder="e.g. Inspect commercial espresso boiler pressure assembly"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              disabled={busy}
            />
          </div>
          {status === 'UNDER_REVIEW' && (
            <div className="es-field-group">
              <label htmlFor="assign-move-investigation">
                <input
                  id="assign-move-investigation"
                  type="checkbox"
                  checked={moveToInvestigation}
                  onChange={(event) =>
                    setMoveToInvestigation(event.target.checked)
                  }
                  disabled={busy}
                />{' '}
                Advance status from UNDER_REVIEW to INVESTIGATION_ASSIGNED
              </label>
            </div>
          )}
          <button
            type="button"
            className="es-btn-primary"
            onClick={handleAssign}
            disabled={busy || officers.length === 0}
          >
            {busy ? 'Assigning…' : 'Assign officer'}
          </button>
        </>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  )
}

