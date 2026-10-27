import { useEffect, useState } from 'react'
import { apiFetch } from './api'

interface SettlementRecord {
  id: string
  claim_id: string
  settlement_reference: string
  amount: string
  currency: string
  status: string
  notes: string | null
  created_by_user_id: string
  settled_at: string | null
  created_at: string
  updated_at: string
  source: string
  simulated: boolean
}

interface SettlementEnvelope {
  claim_id: string
  claim_reference: string
  claim_status: string
  simulated: boolean
  simulation_notice: string
  supported_currencies: string[]
  default_currency: string
  settlement: SettlementRecord | null
}

interface SettlementPanelProps {
  claimId: string
  status: string
  defaultAmountClaimed: string
  token: string
  role: string
  refreshKey?: number
  onUnauthorized: () => void
  onChanged: () => void
}

const CURRENCY_SYMBOLS: Record<string, string> = {
  INR: '₹',
  USD: '$',
  EUR: '€',
  GBP: '£',
}

function formatCurrencyAmount(currency: string, amount: string): string {
  const symbol = CURRENCY_SYMBOLS[currency] ?? `${currency} `
  return `${symbol}${amount} (${currency})`
}

export default function SettlementPanel({
  claimId,
  status,
  defaultAmountClaimed,
  token,
  role,
  refreshKey = 0,
  onUnauthorized,
  onChanged,
}: SettlementPanelProps) {
  const isOfficer = role === 'OPS' || role === 'ADMIN'
  const [envelope, setEnvelope] = useState<SettlementEnvelope | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [amount, setAmount] = useState(defaultAmountClaimed)
  const [currency, setCurrency] = useState('INR')
  const [notes, setNotes] = useState('')
  const [markSettled, setMarkSettled] = useState(false)
  const [completionNotes, setCompletionNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const loadSettlement = async () => {
      try {
        const response = await apiFetch(
          `/api/claims/${encodeURIComponent(claimId)}/settlement`,
          {},
          token,
        )
        if (cancelled) return
        if (response.status === 401) {
          onUnauthorized()
          return
        }
        if (response.status === 404) {
          setLoadError('Settlement tracking not found or not visible to you.')
          return
        }
        if (!response.ok) {
          setLoadError('Could not load settlement tracking.')
          return
        }
        const data = (await response.json()) as SettlementEnvelope
        if (cancelled) return
        setEnvelope(data)
        setLoadError(null)
        if (data.default_currency) {
          setCurrency((prev) => prev || data.default_currency)
        }
      } catch {
        if (!cancelled) {
          setLoadError('API unreachable')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    void loadSettlement()
    return () => {
      cancelled = true
    }
  }, [claimId, token, refreshKey, onUnauthorized])

  const handleRecordSettlement = async () => {
    const trimmedAmount = amount.trim()
    if (!trimmedAmount || Number(trimmedAmount) <= 0) {
      setActionMessage('Enter a valid positive settlement amount.')
      return
    }
    setBusy(true)
    setActionMessage(null)
    try {
      const response = await apiFetch(
        `/api/claims/${encodeURIComponent(claimId)}/settlement`,
        {
          method: 'POST',
          body: JSON.stringify({
            amount: trimmedAmount,
            currency,
            notes: notes.trim() || null,
            mark_settled: markSettled,
          }),
        },
        token,
      )
      if (response.status === 401) {
        onUnauthorized()
        return
      }
      if (response.status === 403) {
        setActionMessage('Your role cannot record settlements.')
        return
      }
      if (response.status === 404) {
        setActionMessage('Claim not found or not visible to you.')
        return
      }
      if (response.status === 422) {
        const body = (await response.json().catch(() => null)) as {
          detail?: string
        } | null
        setActionMessage(
          body?.detail ?? 'Settlement could not be recorded for this claim.',
        )
        return
      }
      if (!response.ok) {
        setActionMessage('Could not record settlement.')
        return
      }
      const data = (await response.json()) as SettlementEnvelope
      setEnvelope(data)
      setNotes('')
      setActionMessage('Simulated settlement recorded.')
      onChanged()
    } catch {
      setActionMessage('API unreachable')
    } finally {
      setBusy(false)
    }
  }

  const handleCompleteSettlement = async () => {
    setBusy(true)
    setActionMessage(null)
    try {
      const response = await apiFetch(
        `/api/claims/${encodeURIComponent(claimId)}/settlement`,
        {
          method: 'PATCH',
          body: JSON.stringify({
            notes: completionNotes.trim() || null,
          }),
        },
        token,
      )
      if (response.status === 401) {
        onUnauthorized()
        return
      }
      if (response.status === 403) {
        setActionMessage('Your role cannot complete settlements.')
        return
      }
      if (response.status === 404) {
        setActionMessage('Settlement record not found.')
        return
      }
      if (response.status === 422) {
        const body = (await response.json().catch(() => null)) as {
          detail?: string
        } | null
        setActionMessage(
          body?.detail ?? 'Settlement completion is not allowed right now.',
        )
        return
      }
      if (!response.ok) {
        setActionMessage('Could not complete settlement.')
        return
      }
      const data = (await response.json()) as SettlementEnvelope
      setEnvelope(data)
      setCompletionNotes('')
      setActionMessage('Simulated settlement marked as SETTLED.')
      onChanged()
    } catch {
      setActionMessage('API unreachable')
    } finally {
      setBusy(false)
    }
  }

  const settlement = envelope?.settlement ?? null
  const currencies = envelope?.supported_currencies ?? [
    'INR',
    'USD',
    'EUR',
    'GBP',
  ]
  const canCreateSettlement =
    isOfficer &&
    settlement === null &&
    (status === 'APPROVED' || status === 'SETTLEMENT_IN_PROGRESS')
  const canCompleteSettlement =
    isOfficer &&
    settlement !== null &&
    settlement.status === 'IN_PROGRESS' &&
    status === 'SETTLEMENT_IN_PROGRESS'

  return (
    <section className="es-card">
      <div className="es-card-header">
        <h2>Settlement tracking (MOCK_CLAIMCENTER · simulated)</h2>
      </div>
      <p className="es-muted-note">
        {envelope?.simulation_notice ??
          'Simulated local Guidewire ClaimCenter settlement tracking (MOCK_CLAIMCENTER). No real payment or external transfer is executed.'}
      </p>

      {loading && <p role="status">Loading settlement tracking…</p>}
      {loadError && <p role="alert">{loadError}</p>}

      {!loading && !loadError && settlement !== null && (
        <dl className="es-dl-grid">
          <div>
            <dt>Settlement reference</dt>
            <dd>{settlement.settlement_reference}</dd>
          </div>
          <div>
            <dt>Settlement status</dt>
            <dd>
              <span className="es-status-chip">{settlement.status}</span>
            </dd>
          </div>
          <div>
            <dt>Approved payout amount</dt>
            <dd>{formatCurrencyAmount(settlement.currency, settlement.amount)}</dd>
          </div>
          <div>
            <dt>Initiated at</dt>
            <dd>{new Date(settlement.created_at).toLocaleString()}</dd>
          </div>
          <div>
            <dt>Settled at</dt>
            <dd>
              {settlement.settled_at
                ? new Date(settlement.settled_at).toLocaleString()
                : 'In progress'}
            </dd>
          </div>
          <div>
            <dt>Adapter source</dt>
            <dd>{settlement.source} (simulated)</dd>
          </div>
          {settlement.notes && (
            <div>
              <dt>Settlement notes</dt>
              <dd>{settlement.notes}</dd>
            </div>
          )}
        </dl>
      )}

      {!loading && !loadError && settlement === null && (
        <p>
          No settlement record has been created for this claim yet (current claim
          status: <strong>{status}</strong>).
        </p>
      )}

      {canCreateSettlement && (
        <div className="es-subform">
          <h3>Initiate simulated settlement (OPS)</h3>
          <div className="es-field-group">
            <label htmlFor="settlement-currency">Currency</label>
            <select
              id="settlement-currency"
              value={currency}
              onChange={(event) => setCurrency(event.target.value)}
              disabled={busy}
            >
              {currencies.map((code) => (
                <option key={code} value={code}>
                  {code} ({CURRENCY_SYMBOLS[code] ?? code})
                </option>
              ))}
            </select>
          </div>
          <div className="es-field-group">
            <label htmlFor="settlement-amount">
              Settlement amount ({CURRENCY_SYMBOLS[currency] ?? currency})
            </label>
            <input
              id="settlement-amount"
              type="number"
              step="0.01"
              min="0.01"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              disabled={busy}
            />
          </div>
          <div className="es-field-group">
            <label htmlFor="settlement-notes">Settlement notes (optional)</label>
            <input
              id="settlement-notes"
              type="text"
              maxLength={1000}
              placeholder="e.g. Approved replacement unit payout less policy deductible"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              disabled={busy}
            />
          </div>
          <div className="es-field-group">
            <label htmlFor="settlement-mark-settled">
              <input
                id="settlement-mark-settled"
                type="checkbox"
                checked={markSettled}
                onChange={(event) => setMarkSettled(event.target.checked)}
                disabled={busy}
              />{' '}
              Complete settlement immediately (advance status to SETTLED)
            </label>
          </div>
          <button
            type="button"
            className="es-btn-primary"
            onClick={handleRecordSettlement}
            disabled={busy}
          >
            {busy ? 'Recording…' : 'Record simulated settlement'}
          </button>
        </div>
      )}

      {canCompleteSettlement && (
        <div className="es-subform">
          <h3>Complete in-progress settlement (OPS)</h3>
          <div className="es-field-group">
            <label htmlFor="settlement-complete-notes">
              Completion notes (optional)
            </label>
            <input
              id="settlement-complete-notes"
              type="text"
              maxLength={1000}
              placeholder="e.g. Simulated NEFT/RTGS disbursement batch completed"
              value={completionNotes}
              onChange={(event) => setCompletionNotes(event.target.value)}
              disabled={busy}
            />
          </div>
          <button
            type="button"
            className="es-btn-primary"
            onClick={handleCompleteSettlement}
            disabled={busy}
          >
            {busy ? 'Completing…' : 'Mark settlement as SETTLED'}
          </button>
        </div>
      )}

      {actionMessage && <p role="status">{actionMessage}</p>}
    </section>
  )
}

