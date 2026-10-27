import { useEffect, useState } from 'react'
import { apiFetch } from './api'

interface PolicyVerification {
  source: string
  simulated: boolean
  passed: boolean
  policy_id: string
  policy_number: string | null
  status: string | null
  is_active: boolean
  start_date: string | null
  end_date: string | null
  incident_date_within_period: boolean
  equipment_id: string
  equipment_description: string | null
  equipment_category: string | null
  equipment_covered: boolean
  coverage_limit: string | null
  deductible_amount: string | null
  reasons: string[]
}

interface BillingVerification {
  source: string
  simulated: boolean
  passed: boolean
  account_status: string | null
  business_rule_result: string
  as_of: string
  premium_amount: string | null
  record_count: number
  reasons: string[]
}

interface ClaimVerificationResponse {
  claim_id: string
  claim_reference: string
  incident_date: string
  simulated: boolean
  simulation_notice: string
  overall_passed: boolean
  sources: string[]
  failures: string[]
  policy_verification: PolicyVerification
  billing_verification: BillingVerification
}

interface ClaimVerificationPanelProps {
  claimId: string
  token: string
  role: string
  refreshKey?: number
  onUnauthorized: () => void
}

export default function ClaimVerificationPanel({
  claimId,
  token,
  role,
  refreshKey = 0,
  onUnauthorized,
}: ClaimVerificationPanelProps) {
  const [data, setData] = useState<ClaimVerificationResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const isOfficer = role === 'OPS' || role === 'ADMIN'

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const response = await apiFetch(
          `/api/claims/${encodeURIComponent(claimId)}/verification`,
          {},
          token,
        )
        if (cancelled) return
        if (response.status === 401) {
          onUnauthorized()
          return
        }
        if (response.status === 403) {
          setError('Your role is not permitted to view policy and billing verification.')
          setData(null)
          return
        }
        if (response.status === 404) {
          setError('Claim verification not found or not visible to you.')
          setData(null)
          return
        }
        if (!response.ok) {
          setError('Could not load policy and billing verification.')
          setData(null)
          return
        }
        const payload = (await response.json()) as ClaimVerificationResponse
        if (cancelled) return
        setData(payload)
      } catch {
        if (!cancelled) {
          setError('API unreachable')
          setData(null)
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [claimId, token, refreshKey, onUnauthorized])

  return (
    <div className="es-verification-grid">
      <section className="es-card">
        <div className="es-card-header">
          <div>
            <h2>Policy verification (simulated PolicyCenter)</h2>
            <p className="es-advisory-note">
              Simulated local Guidewire PolicyCenter check (MOCK_POLICYCENTER)
            </p>
          </div>
          {data && (
            <span
              className={
                data.policy_verification.passed
                  ? 'es-status-badge'
                  : 'es-status-badge es-status-badge--error'
              }
            >
              {data.policy_verification.passed ? 'Policy verified' : 'Check failed'}
            </span>
          )}
        </div>

        {loading && <p role="status">Running simulated PolicyCenter checks…</p>}
        {error && <p role="alert">{error}</p>}

        {!loading && !error && data && (
          <>
            <dl className="es-dl-grid">
              <div>
                <dt>Policy number</dt>
                <dd>{data.policy_verification.policy_number ?? 'Not found'}</dd>
              </div>
              <div>
                <dt>Policy status</dt>
                <dd>
                  {data.policy_verification.status
                    ? `${data.policy_verification.status} (${
                        data.policy_verification.is_active ? 'Active' : 'Inactive'
                      })`
                    : 'Missing'}
                </dd>
              </div>
              <div>
                <dt>Coverage period</dt>
                <dd>
                  {data.policy_verification.start_date &&
                  data.policy_verification.end_date
                    ? `${data.policy_verification.start_date} to ${data.policy_verification.end_date}`
                    : 'Unavailable'}
                </dd>
              </div>
              <div>
                <dt>Incident within period</dt>
                <dd>
                  {data.policy_verification.incident_date_within_period
                    ? `Yes (${data.incident_date})`
                    : `No (${data.incident_date})`}
                </dd>
              </div>
              <div>
                <dt>Equipment covered</dt>
                <dd>
                  {data.policy_verification.equipment_covered ? 'Yes' : 'No'}
                  {data.policy_verification.equipment_description
                    ? ` — ${data.policy_verification.equipment_description}`
                    : ''}
                </dd>
              </div>
              <div>
                <dt>Coverage limit / Deductible</dt>
                <dd>
                  {data.policy_verification.coverage_limit &&
                  data.policy_verification.deductible_amount
                    ? `$${data.policy_verification.coverage_limit} / $${data.policy_verification.deductible_amount} deductible`
                    : 'Unavailable'}
                </dd>
              </div>
            </dl>

            {data.policy_verification.reasons.length > 0 && (
              <div className="es-verification-reasons" role="alert">
                <strong>Policy verification issues:</strong>
                <ul>
                  {data.policy_verification.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
            )}

            {isOfficer && (
              <p className="es-advisory-note">
                Officer audit source: <code>{data.policy_verification.source}</code> ·
                Equipment category:{' '}
                {data.policy_verification.equipment_category ?? 'Unknown'}
              </p>
            )}
          </>
        )}
      </section>

      <section className="es-card">
        <div className="es-card-header">
          <div>
            <h2>Billing verification (simulated BillingCenter)</h2>
            <p className="es-advisory-note">
              Simulated local Guidewire BillingCenter check (MOCK_BILLINGCENTER)
            </p>
          </div>
          {data && (
            <span
              className={
                data.billing_verification.passed
                  ? 'es-status-badge'
                  : 'es-status-badge es-status-badge--error'
              }
            >
              {data.billing_verification.passed ? 'Account eligible' : 'Ineligible'}
            </span>
          )}
        </div>

        {loading && <p role="status">Running simulated BillingCenter checks…</p>}
        {error && <p role="alert">{error}</p>}

        {!loading && !error && data && (
          <>
            <dl className="es-dl-grid">
              <div>
                <dt>Account status</dt>
                <dd>{data.billing_verification.account_status ?? 'No records'}</dd>
              </div>
              <div>
                <dt>Business-rule result</dt>
                <dd>{data.billing_verification.business_rule_result}</dd>
              </div>
              <div>
                <dt>Evaluated as of</dt>
                <dd>{data.billing_verification.as_of}</dd>
              </div>
              <div>
                <dt>Annual policy premium</dt>
                <dd>
                  {data.billing_verification.premium_amount
                    ? `$${data.billing_verification.premium_amount}`
                    : 'Unavailable'}
                </dd>
              </div>
              {isOfficer && (
                <div>
                  <dt>Billing periods checked</dt>
                  <dd>{data.billing_verification.record_count}</dd>
                </div>
              )}
              <div>
                <dt>Overall verification</dt>
                <dd>
                  {data.overall_passed
                    ? 'All policy & billing checks passed'
                    : 'Failed one or more checks'}
                </dd>
              </div>
            </dl>

            {data.billing_verification.reasons.length > 0 && (
              <div className="es-verification-reasons" role="alert">
                <strong>Billing verification issues:</strong>
                <ul>
                  {data.billing_verification.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
            )}

            {isOfficer && (
              <p className="es-advisory-note">
                Officer audit source: <code>{data.billing_verification.source}</code> ·
                Read-only check; does not auto-transition claim status.
              </p>
            )}
          </>
        )}
      </section>
    </div>
  )
}

