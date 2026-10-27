import { useEffect, useState, type FormEvent } from 'react'

import { apiFetch } from './api'

interface PolicyOption {
  id: string
  policy_number: string
  status: string
  start_date: string
  end_date: string
  coverage_limit: string
  deductible_amount: string
  covered_equipment_ids: string[]
}

interface EquipmentOption {
  id: string
  category: string
  description: string
}

interface RegistrationOptionsResponse {
  policies: PolicyOption[]
  equipment: EquipmentOption[]
}

interface CreatedClaimResponse {
  id: string
  reference: string
  status: string
  sources?: string[]
}

interface ClaimRegistrationPanelProps {
  token: string
  role: string
  onUnauthorized: () => void
  onRegistered: (claimId: string) => void
}

function parseErrorDetail(text: string): string | null {
  try {
    const body: unknown = JSON.parse(text)
    if (typeof body === 'object' && body !== null && 'detail' in body) {
      if (typeof body.detail === 'string') {
        return body.detail
      }
      if (Array.isArray(body.detail) && body.detail.length > 0) {
        const first = body.detail[0] as { msg?: string }
        if (typeof first?.msg === 'string') {
          return first.msg
        }
      }
    }
  } catch {
    return null
  }
  return null
}

export default function ClaimRegistrationPanel({
  token,
  role,
  onUnauthorized,
  onRegistered,
}: ClaimRegistrationPanelProps) {
  const [policies, setPolicies] = useState<PolicyOption[]>([])
  const [equipment, setEquipment] = useState<EquipmentOption[]>([])
  const [policyNumber, setPolicyNumber] = useState('')
  const [equipmentId, setEquipmentId] = useState('')
  const [incidentDate, setIncidentDate] = useState('2026-10-15')
  const [amountClaimed, setAmountClaimed] = useState('')
  const [incidentDescription, setIncidentDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [createdReference, setCreatedReference] = useState<string | null>(null)

  useEffect(() => {
    if (role !== 'POLICYHOLDER') {
      return
    }
    let cancelled = false
    const loadOptions = async () => {
      try {
        const response = await apiFetch('/api/claims/options', {}, token)
        if (cancelled) return
        if (response.status === 401) {
          onUnauthorized()
          return
        }
        if (!response.ok) {
          return
        }
        const data = (await response.json()) as RegistrationOptionsResponse
        if (cancelled) return
        setPolicies(data.policies ?? [])
        setEquipment(data.equipment ?? [])
        if (data.policies?.length > 0) {
          setPolicyNumber((current) => current || data.policies[0].policy_number)
        }
        if (data.equipment?.length > 0) {
          setEquipmentId((current) => current || data.equipment[0].id)
        }
      } catch {
        // Keep manual inputs available if options cannot be preloaded
      }
    }
    void loadOptions()
    return () => {
      cancelled = true
    }
  }, [token, role, onUnauthorized])

  if (role !== 'POLICYHOLDER') {
    return null
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmedPolicy = policyNumber.trim()
    const trimmedEquipment = equipmentId.trim()
    const trimmedDescription = incidentDescription.trim()
    const trimmedAmount = amountClaimed.trim()

    if (!trimmedPolicy || !trimmedEquipment || !incidentDate || !trimmedDescription || !trimmedAmount) {
      setError('Complete all required claim registration fields.')
      return
    }

    setSubmitting(true)
    setError(null)
    setCreatedReference(null)

    try {
      const response = await apiFetch(
        '/api/claims',
        {
          method: 'POST',
          body: JSON.stringify({
            policy_number: trimmedPolicy,
            equipment_id: trimmedEquipment,
            incident_date: incidentDate,
            incident_description: trimmedDescription,
            amount_claimed: trimmedAmount,
          }),
        },
        token,
      )

      if (response.status === 401) {
        onUnauthorized()
        return
      }

      if (!response.ok) {
        const detail = parseErrorDetail(await response.text())
        setError(detail ?? 'Could not register claim. Check policy, equipment, and incident details.')
        return
      }

      const created = (await response.json()) as CreatedClaimResponse
      setCreatedReference(created.reference)
      setAmountClaimed('')
      setIncidentDescription('')
      onRegistered(created.id)
    } catch {
      setError('API unreachable')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="es-card">
      <div className="es-card-header">
        <h2>Register new claim (simulated PolicyCenter &amp; BillingCenter checks)</h2>
      </div>

      <form className="es-registration-form" onSubmit={handleSubmit}>
        <div className="es-form-grid">
          <div className="es-field-group">
            <label htmlFor="claim-policy-number">Policy</label>
            {policies.length > 0 ? (
              <select
                id="claim-policy-number"
                value={policyNumber}
                onChange={(event) => setPolicyNumber(event.target.value)}
                disabled={submitting}
              >
                {policies.map((pol) => (
                  <option key={pol.id} value={pol.policy_number}>
                    {pol.policy_number} ({pol.status}, {pol.start_date} to {pol.end_date})
                  </option>
                ))}
              </select>
            ) : (
              <input
                id="claim-policy-number"
                type="text"
                value={policyNumber}
                onChange={(event) => setPolicyNumber(event.target.value)}
                placeholder="e.g. DEMO-POL-0001"
                disabled={submitting}
                required
              />
            )}
          </div>

          <div className="es-field-group">
            <label htmlFor="claim-equipment-id">Covered equipment</label>
            {equipment.length > 0 ? (
              <select
                id="claim-equipment-id"
                value={equipmentId}
                onChange={(event) => setEquipmentId(event.target.value)}
                disabled={submitting}
              >
                {equipment.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.description} ({item.category})
                  </option>
                ))}
              </select>
            ) : (
              <input
                id="claim-equipment-id"
                type="text"
                value={equipmentId}
                onChange={(event) => setEquipmentId(event.target.value)}
                placeholder="Equipment UUID"
                disabled={submitting}
                required
              />
            )}
          </div>

          <div className="es-field-group">
            <label htmlFor="claim-incident-date">Incident date</label>
            <input
              id="claim-incident-date"
              type="date"
              value={incidentDate}
              onChange={(event) => setIncidentDate(event.target.value)}
              disabled={submitting}
              required
            />
          </div>

          <div className="es-field-group">
            <label htmlFor="claim-amount-claimed">Amount claimed</label>
            <input
              id="claim-amount-claimed"
              type="number"
              step="0.01"
              min="0.01"
              value={amountClaimed}
              onChange={(event) => setAmountClaimed(event.target.value)}
              placeholder="0.00"
              disabled={submitting}
              required
            />
          </div>
        </div>

        <div className="es-field-group">
          <label htmlFor="claim-incident-description">Incident description</label>
          <input
            id="claim-incident-description"
            type="text"
            maxLength={2000}
            value={incidentDescription}
            onChange={(event) => setIncidentDescription(event.target.value)}
            placeholder="Describe the equipment breakdown and operational impact"
            disabled={submitting}
            required
          />
        </div>

        <button type="submit" disabled={submitting}>
          {submitting ? 'Registering claim…' : 'Register claim'}
        </button>
      </form>

      {error !== null && <p role="alert">{error}</p>}
      {createdReference !== null && (
        <p role="status">
          Registered claim <strong>{createdReference}</strong> (simulated PolicyCenter,
          BillingCenter, and ClaimCenter checks passed).
        </p>
      )}
    </section>
  )
}

