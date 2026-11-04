import { useEffect, useState } from 'react'
import { apiFetch } from './api'

interface DocumentFlagItem {
  document_id: string
  original_filename: string
  flags: string[]
  note?: string
}

interface ImageFlagsResponse {
  claim_id?: string
  documents?: DocumentFlagItem[]
  items?: DocumentFlagItem[]
  note: string
}

interface ImageFlagsPanelProps {
  claimId: string
  token: string
  onUnauthorized: () => void
}

function isImageFlagsResponse(value: unknown): value is ImageFlagsResponse {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const obj = value as Record<string, unknown>
  if (typeof obj.note !== 'string') {
    return false
  }
  const docs = obj.documents ?? obj.items
  if (!Array.isArray(docs)) {
    return false
  }
  return docs.every((item) => {
    if (typeof item !== 'object' || item === null) {
      return false
    }
    const docObj = item as Record<string, unknown>
    return (
      typeof docObj.document_id === 'string' &&
      typeof docObj.original_filename === 'string' &&
      Array.isArray(docObj.flags) &&
      docObj.flags.every((f) => typeof f === 'string')
    )
  })
}

export default function ImageFlagsPanel({
  claimId,
  token,
  onUnauthorized,
}: ImageFlagsPanelProps) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<ImageFlagsResponse | null>(null)

  useEffect(() => {
    let active = true

    const fetchFlags = async () => {
      setLoading(true)
      setError(null)

      try {
        const response = await apiFetch(
          `/api/claims/${encodeURIComponent(claimId)}/image-flags`,
          {},
          token,
        )

        if (!active) {
          return
        }

        if (response.status === 401) {
          onUnauthorized()
          return
        }

        if (!response.ok) {
          let detail = 'Failed to load image flags.'
          try {
            const body: unknown = await response.json()
            if (
              typeof body === 'object' &&
              body !== null &&
              'detail' in body &&
              typeof (body as Record<string, unknown>).detail === 'string'
            ) {
              detail = (body as Record<string, unknown>).detail as string
            }
          } catch {
            // ignore non-json
          }
          setError(detail)
          return
        }

        const payload: unknown = await response.json()
        if (!active) {
          return
        }

        if (isImageFlagsResponse(payload)) {
          setData(payload)
        } else {
          setError('Unexpected response format from image flags API.')
        }
      } catch {
        if (active) {
          setError('API unreachable')
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    void fetchFlags()

    return () => {
      active = false
    }
  }, [claimId, token, onUnauthorized])

  const docs = data?.documents ?? data?.items ?? []

  return (
    <section className="es-card">
      <div className="es-card-header">
        <h2>Photo Integrity & Flags (OPS)</h2>
      </div>

      {loading && <p>Loading image flags…</p>}

      {error !== null && (
        <p role="alert" className="es-error">
          {error}
        </p>
      )}

      {!loading && error === null && data !== null && (
        <>
          {docs.length === 0 ? (
            <p>No photo documents uploaded for this claim.</p>
          ) : (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                marginTop: '8px',
              }}
            >
              {docs.map((doc) => (
                <div
                  key={doc.document_id}
                  style={{
                    padding: '8px 12px',
                    border: '1px solid var(--border-color, #e5e7eb)',
                    borderRadius: '6px',
                  }}
                >
                  <p style={{ margin: '0 0 6px 0', fontWeight: 'bold' }}>
                    {doc.original_filename}
                  </p>

                  {doc.flags.length === 0 ? (
                    <p style={{ margin: 0, color: 'var(--text-muted, #6b7280)' }}>
                      No flags{doc.note ? ` (${doc.note})` : ''}
                    </p>
                  ) : (
                    <ul
                      style={{
                        margin: 0,
                        paddingLeft: '20px',
                        color: 'var(--status-err-text, #dc2626)',
                      }}
                    >
                      {doc.flags.map((flag, idx) => (
                        <li key={idx}>
                          <span>{flag}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}

          <p
            style={{
              fontStyle: 'italic',
              marginTop: '16px',
              marginBottom: 0,
              fontSize: '0.9em',
              color: 'var(--text-muted, #6b7280)',
            }}
          >
            {data.note}
          </p>
        </>
      )}
    </section>
  )
}

