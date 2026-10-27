import { useEffect, useState } from 'react'
import { apiFetch } from './api'

interface ClaimHistoryEvent {
  id: number
  claim_id: string
  old_status: string | null
  new_status: string
  source: string
  actor_user_id: string | null
  is_system: boolean
  explanation: string
  created_at: string
}

interface ClaimHistoryPanelProps {
  claimId: string
  token: string
  refreshKey?: number
  onUnauthorized: () => void
}

function formatSourceLabel(source: string, isSystem: boolean): string {
  if (isSystem || source === 'SYSTEM') {
    return 'System automated'
  }
  if (source === 'OPS') {
    return 'Claim Officer (OPS)'
  }
  if (source === 'ADMIN') {
    return 'Administrator (ADMIN)'
  }
  if (source === 'POLICYHOLDER') {
    return 'Policyholder'
  }
  return source
}

export default function ClaimHistoryPanel({
  claimId,
  token,
  refreshKey = 0,
  onUnauthorized,
}: ClaimHistoryPanelProps) {
  const [events, setEvents] = useState<ClaimHistoryEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const response = await apiFetch(
          `/api/claims/${encodeURIComponent(claimId)}/history`,
          {},
          token,
        )
        if (cancelled) return
        if (response.status === 401) {
          onUnauthorized()
          return
        }
        if (response.status === 403) {
          setError('Your role is not permitted to view claim status history.')
          setEvents([])
          return
        }
        if (response.status === 404) {
          setError('Claim history not found or not visible to you.')
          setEvents([])
          return
        }
        if (!response.ok) {
          setError('Could not load claim status history.')
          setEvents([])
          return
        }
        const payload = (await response.json()) as ClaimHistoryEvent[]
        if (cancelled) return
        setEvents(payload)
      } catch {
        if (!cancelled) {
          setError('API unreachable')
          setEvents([])
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
    <section className="es-card">
      <div className="es-card-header">
        <div>
          <h2>Claim status history</h2>
          <p className="es-advisory-note">
            Chronological append-only audit log from claim_events
          </p>
        </div>
        <span className="es-status-chip">
          {events.length} {events.length === 1 ? 'event' : 'events'}
        </span>
      </div>

      {loading && <p role="status">Loading claim history…</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !error && events.length === 0 && (
        <p>No status history events recorded for this claim.</p>
      )}

      {!loading && !error && events.length > 0 && (
        <ol className="es-timeline">
          {events.map((event) => (
            <li
              key={event.id}
              className={
                event.is_system
                  ? 'es-timeline-item es-timeline-item--system'
                  : 'es-timeline-item'
              }
            >
              <div className="es-timeline-header">
                <div className="es-timeline-transition">
                  <span className="es-status-chip">
                    {event.old_status ?? 'INITIAL'} → {event.new_status}
                  </span>
                  <span
                    className={
                      event.is_system
                        ? 'es-actor-badge es-actor-badge--system'
                        : 'es-actor-badge'
                    }
                  >
                    {formatSourceLabel(event.source, event.is_system)}
                  </span>
                </div>
                <time className="es-timeline-time" dateTime={event.created_at}>
                  {new Date(event.created_at).toLocaleString()}
                </time>
              </div>
              <p className="es-timeline-explanation">{event.explanation}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

