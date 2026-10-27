import { useEffect, useState } from 'react'
import { apiFetch } from './api'

interface ClaimMessage {
  id: string
  author_role: string
  body: string
  created_at: string
}

interface MessagesPanelProps {
  claimId: string
  token: string
  onUnauthorized: () => void
}

export default function MessagesPanel({ claimId, token, onUnauthorized }: MessagesPanelProps) {
  const [messages, setMessages] = useState<ClaimMessage[]>([])
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const response = await apiFetch(`/api/claims/${claimId}/messages`, {}, token)
        if (cancelled) return
        if (response.status === 401) {
          onUnauthorized()
          return
        }
        if (!response.ok) {
          setError('Could not load messages.')
          return
        }
        const data = (await response.json()) as ClaimMessage[]
        if (cancelled) return
        setMessages(data)
        setError(null)
      } catch {
        if (!cancelled) setError('API unreachable')
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [claimId, token, onUnauthorized, refreshKey])

  const send = async () => {
    const body = draft.trim()
    if (!body) return
    setSending(true)
    setError(null)
    try {
      const response = await apiFetch(
        `/api/claims/${claimId}/messages`,
        { method: 'POST', body: JSON.stringify({ body }) },
        token,
      )
      if (response.status === 401) {
        onUnauthorized()
        return
      }
      if (response.status === 404) {
        setError('Claim not found or not visible to you.')
        return
      }
      if (response.status === 422) {
        setError('Message is empty or too long (2000 characters maximum).')
        return
      }
      if (!response.ok) {
        setError('Could not send message.')
        return
      }
      setDraft('')
      setRefreshKey((key) => key + 1)
    } catch {
      setError('API unreachable')
    } finally {
      setSending(false)
    }
  }

  return (
    <section>
      <h2>Messages</h2>
      {error && <p role="alert">{error}</p>}
      {messages.length === 0 && !error && <p>No messages yet.</p>}
      <ul>
        {messages.map((message) => (
          <li key={message.id}>
            <p>
              <strong>{message.author_role}</strong> · {new Date(message.created_at).toLocaleString()}
            </p>
            <p>{message.body}</p>
          </li>
        ))}
      </ul>
      <div>
        <label htmlFor="message-body">New message </label>
        <input
          id="message-body"
          type="text"
          maxLength={2000}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          disabled={sending}
        />
        <button type="button" onClick={send} disabled={sending || draft.trim() === ''}>
          {sending ? 'Sending…' : 'Send'}
        </button>
      </div>
    </section>
  )
}