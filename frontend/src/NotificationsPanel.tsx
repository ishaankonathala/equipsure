import { useEffect, useState } from 'react'
import { apiFetch } from './api'

interface Notification {
  id: string
  claim_id: string | null
  kind: string
  message: string
  read_at: string | null
  created_at: string
}

interface NotificationsPanelProps {
  token: string
  onUnauthorized: () => void
}

export default function NotificationsPanel({ token, onUnauthorized }: NotificationsPanelProps) {
  const [items, setItems] = useState<Notification[]>([])
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const response = await apiFetch('/api/notifications', {}, token)
        if (cancelled) return
        if (response.status === 401) {
          onUnauthorized()
          return
        }
        if (!response.ok) {
          setError('Could not load notifications.')
          return
        }
        const data = (await response.json()) as Notification[]
        if (cancelled) return
        setItems(data)
        setError(null)
      } catch {
        if (!cancelled) setError('API unreachable')
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [token, onUnauthorized, refreshKey])

  const markRead = async (id: string) => {
    try {
      const response = await apiFetch(`/api/notifications/${id}/read`, { method: 'PATCH' }, token)
      if (response.status === 401) {
        onUnauthorized()
        return
      }
      if (!response.ok) {
        setError('Could not mark notification as read.')
        return
      }
      setRefreshKey((key) => key + 1)
    } catch {
      setError('API unreachable')
    }
  }

  return (
    <section className="es-card">
      <div className="es-card-header">
        <h2>Notifications</h2>
      </div>
      {error && <p role="alert">{error}</p>}
      {items.length === 0 && !error && <p>No notifications.</p>}
      <ul className="es-list">
        {items.map((item) => (
          <li key={item.id}>
            <p>{item.message}</p>
            <p>
              {item.read_at ? 'Read' : 'Unread'} · {new Date(item.created_at).toLocaleString()}
            </p>
            {!item.read_at && (
              <button
                type="button"
                className="es-btn-primary"
                onClick={() => markRead(item.id)}
              >
                Mark as read
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}