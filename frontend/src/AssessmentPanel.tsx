import { useState } from 'react'

import { apiFetch } from './api'

interface AssessmentResult {
  summary: string
  cited_clause_ids: string[]
  missing_items: string[]
  inconsistencies: string[]
  recommendation: string
  advisory_only: true
}

interface AssessmentPanelProps {
  claimId: string
  token: string
  role: string
  onUnauthorized: () => void
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isAssessmentResult(value: unknown): value is AssessmentResult {
  return (
    typeof value === 'object' &&
    value !== null &&
    'summary' in value &&
    typeof value.summary === 'string' &&
    'cited_clause_ids' in value &&
    isStringArray(value.cited_clause_ids) &&
    'missing_items' in value &&
    isStringArray(value.missing_items) &&
    'inconsistencies' in value &&
    isStringArray(value.inconsistencies) &&
    'recommendation' in value &&
    typeof value.recommendation === 'string' &&
    'advisory_only' in value &&
    value.advisory_only === true
  )
}

function AssessmentPanel({
  claimId,
  token,
  role,
  onUnauthorized,
}: AssessmentPanelProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [assessment, setAssessment] = useState<AssessmentResult | null>(null)

  if (role !== 'OPS' && role !== 'ADMIN') {
    return null
  }

  const requestAssessment = async () => {
    setIsLoading(true)
    setError(null)
    setAssessment(null)

    try {
      const response = await apiFetch(
        `/api/claims/${claimId}/assessment`,
        { method: 'POST' },
        token,
      )

      if (response.status === 401) {
        onUnauthorized()
        return
      }
      if (response.status === 403) {
        setError('Your role cannot request assessments.')
        return
      }
      if (response.status === 404) {
        setError('Claim not found or not visible to you.')
        return
      }
      if (response.status === 503) {
        setError('AI provider unavailable. Try again later.')
        return
      }
      if (!response.ok) {
        setError('Assessment failed.')
        return
      }

      const payload: unknown = await response.json()
      if (!isAssessmentResult(payload)) {
        setError('Assessment failed.')
        return
      }
      setAssessment(payload)
    } catch {
      setError('API unreachable')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <section>
      <h2>AI assessment (simulated, advisory only)</h2>
      <button type="button" onClick={requestAssessment} disabled={isLoading}>
        {isLoading ? 'Requesting assessment…' : 'Request assessment'}
      </button>
      {error !== null && <p role="alert">{error}</p>}
      {assessment !== null && (
        <dl>
          <div>
            <dt>Summary</dt>
            <dd>{assessment.summary}</dd>
          </div>
          <div>
            <dt>Cited clause ids</dt>
            <dd>{assessment.cited_clause_ids.join(', ') || 'None'}</dd>
          </div>
          <div>
            <dt>Missing items</dt>
            <dd>{assessment.missing_items.join(', ') || 'None'}</dd>
          </div>
          <div>
            <dt>Inconsistencies</dt>
            <dd>{assessment.inconsistencies.join(', ') || 'None'}</dd>
          </div>
          <div>
            <dt>Recommendation</dt>
            <dd>{assessment.recommendation}</dd>
          </div>
          <div>Advisory only: yes</div>
        </dl>
      )}
    </section>
  )
}

export default AssessmentPanel