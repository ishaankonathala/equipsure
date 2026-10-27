import { useState } from 'react'

import { apiFetch } from './api'

interface AssistantAnswer {
  answer: string
  cited_clause_ids: string[]
  advisory_only: true
}

interface AssistantPanelProps {
  token: string
  onUnauthorized: () => void
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isAssistantAnswer(value: unknown): value is AssistantAnswer {
  return (
    typeof value === 'object' &&
    value !== null &&
    'answer' in value &&
    typeof value.answer === 'string' &&
    'cited_clause_ids' in value &&
    isStringArray(value.cited_clause_ids) &&
    'advisory_only' in value &&
    value.advisory_only === true
  )
}

async function readDetail(response: Response): Promise<string | null> {
  const text = await response.text()
  try {
    const payload: unknown = JSON.parse(text)
    if (
      typeof payload === 'object' &&
      payload !== null &&
      'detail' in payload &&
      typeof payload.detail === 'string'
    ) {
      return payload.detail
    }
  } catch {
    return null
  }
  return null
}

function AssistantPanel({ token, onUnauthorized }: AssistantPanelProps) {
  const [question, setQuestion] = useState('')
  const [isAsking, setIsAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [answer, setAnswer] = useState<AssistantAnswer | null>(null)

  const ask = async () => {
    const trimmedQuestion = question.trim()
    if (!trimmedQuestion || isAsking) {
      return
    }

    setIsAsking(true)
    setError(null)
    setAnswer(null)

    try {
      const response = await apiFetch(
        '/api/assistant/ask',
        {
          method: 'POST',
          body: JSON.stringify({ question: trimmedQuestion }),
        },
        token,
      )

      if (response.status === 401) {
        onUnauthorized()
        return
      }
      if (response.status === 422) {
        setError(
          (await readDetail(response)) ??
            'The assistant could not answer that question.',
        )
        return
      }
      if (response.status === 503) {
        setError('AI provider unavailable. Try again later.')
        return
      }
      if (!response.ok) {
        setError('Request failed.')
        return
      }

      const payload: unknown = await response.json()
      if (!isAssistantAnswer(payload)) {
        setError('Request failed.')
        return
      }
      setAnswer(payload)
    } catch {
      setError('API unreachable')
    } finally {
      setIsAsking(false)
    }
  }

  return (
    <section className="es-card">
      <div className="es-card-header">
        <h2>Policy assistant (simulated, advisory only)</h2>
      </div>
      <div className="es-inline-form">
        <div className="es-field-grow">
          <label htmlFor="assistant-question">Question</label>
          <input
            id="assistant-question"
            type="text"
            maxLength={500}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
        </div>
        <button
          type="button"
          className="es-btn-primary"
          onClick={ask}
          disabled={isAsking || question.trim().length === 0}
        >
          {isAsking ? 'Asking…' : 'Ask'}
        </button>
      </div>

      {error !== null && <p role="alert">{error}</p>}
      {answer !== null && (
        <div className="es-assistant-answer">
          <p>{answer.answer}</p>
          <p>Cited clauses: {answer.cited_clause_ids.join(', ')}</p>
          <p>Advisory only: yes</p>
        </div>
      )}
    </section>
  )
}

export default AssistantPanel