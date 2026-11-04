import { useEffect, useState } from 'react'
import { apiFetch } from './api'

interface QuoteLine {
  label: string
  amount: string
}

interface QuoteItem {
  id: string
  equipment_category: string
  equipment_description: string
  sum_insured: string | number
  age_years: number
  cover: string
  total: string | number
  lines: QuoteLine[]
  status: string
  created_at?: string
}

interface ComparePanelProps {
  token: string
  onUnauthorized: () => void
}

function isQuoteLine(value: unknown): value is QuoteLine {
  return (
    typeof value === 'object' &&
    value !== null &&
    'label' in value &&
    typeof (value as Record<string, unknown>).label === 'string' &&
    'amount' in value &&
    typeof (value as Record<string, unknown>).amount === 'string'
  )
}

function isQuoteItem(value: unknown): value is QuoteItem {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const obj = value as Record<string, unknown>
  return (
    typeof obj.id === 'string' &&
    typeof obj.equipment_category === 'string' &&
    typeof obj.equipment_description === 'string' &&
    (typeof obj.sum_insured === 'string' || typeof obj.sum_insured === 'number') &&
    typeof obj.age_years === 'number' &&
    typeof obj.cover === 'string' &&
    (typeof obj.total === 'string' || typeof obj.total === 'number') &&
    Array.isArray(obj.lines) &&
    obj.lines.every(isQuoteLine) &&
    typeof obj.status === 'string'
  )
}

function isQuoteList(value: unknown): value is QuoteItem[] {
  return Array.isArray(value) && value.every(isQuoteItem)
}

export default function ComparePanel({ token, onUnauthorized }: ComparePanelProps) {
  const [loadingQuotes, setLoadingQuotes] = useState(true)
  const [quotes, setQuotes] = useState<QuoteItem[]>([])
  const [listError, setListError] = useState<string | null>(null)

  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [comparing, setComparing] = useState(false)
  const [compareError, setCompareError] = useState<string | null>(null)
  const [comparedQuotes, setComparedQuotes] = useState<QuoteItem[] | null>(null)

  useEffect(() => {
    let active = true

    const fetchQuotes = async () => {
      setLoadingQuotes(true)
      setListError(null)

      try {
        const res = await apiFetch('/api/quotes', {}, token)
        if (!active) {
          return
        }

        if (res.status === 401) {
          onUnauthorized()
          return
        }

        if (!res.ok) {
          setListError('Failed to load quotes.')
          return
        }

        const data: unknown = await res.json()
        if (!active) {
          return
        }

        if (isQuoteList(data)) {
          setQuotes(data)
        } else {
          setListError('Unexpected format for quote list.')
        }
      } catch {
        if (active) {
          setListError('API unreachable')
        }
      } finally {
        if (active) {
          setLoadingQuotes(false)
        }
      }
    }

    void fetchQuotes()

    return () => {
      active = false
    }
  }, [token, onUnauthorized])

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((item) => item !== id)
      }
      if (prev.length >= 3) {
        return prev
      }
      return [...prev, id]
    })
  }

  const handleCompare = async () => {
    if (selectedIds.length < 2 || selectedIds.length > 3) {
      return
    }
    setComparing(true)
    setCompareError(null)

    const query = selectedIds
      .map((id) => `ids=${encodeURIComponent(id)}`)
      .join('&')

    try {
      const res = await apiFetch(`/api/quotes/compare?${query}`, {}, token)

      if (res.status === 401) {
        onUnauthorized()
        return
      }

      if (!res.ok) {
        let detail = 'Failed to compare quotes.'
        try {
          const body: unknown = await res.json()
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
        setCompareError(detail)
        return
      }

      const data: unknown = await res.json()
      if (isQuoteList(data)) {
        setComparedQuotes(data)
      } else {
        setCompareError('Unexpected response format from quote comparison.')
      }
    } catch {
      setCompareError('API unreachable')
    } finally {
      setComparing(false)
    }
  }

  const allLineLabels: string[] = []
  if (comparedQuotes !== null) {
    for (const q of comparedQuotes) {
      for (const line of q.lines) {
        if (!allLineLabels.includes(line.label)) {
          allLineLabels.push(line.label)
        }
      }
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <section className="es-card">
        <div className="es-card-header">
          <h2>Compare Saved Quotes</h2>
        </div>
        <p style={{ margin: '0 0 12px 0', color: 'var(--text-muted, #6b7280)' }}>
          Select 2 or 3 saved quotes to compare them side by side.
        </p>

        {loadingQuotes && <p>Loading your saved quotes…</p>}

        {listError !== null && (
          <p role="alert" className="es-error">
            {listError}
          </p>
        )}

        {!loadingQuotes && listError === null && quotes.length === 0 && (
          <p>No saved quotes found for your business.</p>
        )}

        {!loadingQuotes && quotes.length > 0 && (
          <div>
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                marginBottom: '16px',
              }}
            >
              {quotes.map((q) => {
                const isSelected = selectedIds.includes(q.id)
                const disabled = !isSelected && selectedIds.length >= 3

                return (
                  <label
                    key={q.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      padding: '8px 12px',
                      border: '1px solid var(--border-color, #e5e7eb)',
                      borderRadius: '6px',
                      cursor: disabled ? 'not-allowed' : 'pointer',
                      opacity: disabled ? 0.6 : 1,
                      backgroundColor: isSelected ? 'var(--bg-accent, #f0f9ff)' : 'transparent',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      disabled={disabled}
                      onChange={() => toggleSelect(q.id)}
                    />
                    <span>
                      <strong>{q.equipment_description}</strong> ({q.equipment_category}) —{' '}
                      Cover: {q.cover}, Sum Insured: {String(q.sum_insured)}, Total:{' '}
                      <strong>{String(q.total)}</strong> ({q.status})
                    </span>
                  </label>
                )
              })}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <button
                type="button"
                className="es-btn-primary"
                onClick={() => void handleCompare()}
                disabled={selectedIds.length < 2 || selectedIds.length > 3 || comparing}
              >
                {comparing
                  ? 'Comparing…'
                  : `Compare ${selectedIds.length} Quote${selectedIds.length === 1 ? '' : 's'}`}
              </button>
              <span style={{ fontSize: '0.9em', color: 'var(--text-muted, #6b7280)' }}>
                {selectedIds.length} of 3 selected (minimum 2)
              </span>
            </div>
          </div>
        )}

        {compareError !== null && (
          <p role="alert" className="es-error" style={{ marginTop: '12px' }}>
            {compareError}
          </p>
        )}
      </section>

      {comparedQuotes !== null && (
        <section className="es-card">
          <div className="es-card-header">
            <h2>Side-by-Side Comparison</h2>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table
              className="es-table"
              style={{ width: '100%', borderCollapse: 'collapse', marginTop: '8px' }}
            >
              <thead>
                <tr style={{ borderBottom: '2px solid var(--border-color, #e5e7eb)' }}>
                  <th style={{ textAlign: 'left', padding: '10px 12px', width: '220px' }}>
                    Attribute / Line
                  </th>
                  {comparedQuotes.map((q, idx) => (
                    <th key={q.id} style={{ textAlign: 'left', padding: '10px 12px' }}>
                      Quote {idx + 1}
                      <div
                        style={{
                          fontSize: '0.85em',
                          fontWeight: 'normal',
                          color: 'var(--text-muted, #6b7280)',
                        }}
                      >
                        {q.equipment_description}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr style={{ borderBottom: '1px solid var(--border-color, #e5e7eb)' }}>
                  <td style={{ padding: '8px 12px', fontWeight: 'bold' }}>Equipment Category</td>
                  {comparedQuotes.map((q) => (
                    <td key={q.id} style={{ padding: '8px 12px' }}>
                      {q.equipment_category}
                    </td>
                  ))}
                </tr>
                <tr style={{ borderBottom: '1px solid var(--border-color, #e5e7eb)' }}>
                  <td style={{ padding: '8px 12px', fontWeight: 'bold' }}>Sum Insured</td>
                  {comparedQuotes.map((q) => (
                    <td key={q.id} style={{ padding: '8px 12px' }}>
                      {String(q.sum_insured)}
                    </td>
                  ))}
                </tr>
                <tr style={{ borderBottom: '1px solid var(--border-color, #e5e7eb)' }}>
                  <td style={{ padding: '8px 12px', fontWeight: 'bold' }}>Age (Years)</td>
                  {comparedQuotes.map((q) => (
                    <td key={q.id} style={{ padding: '8px 12px' }}>
                      {q.age_years}
                    </td>
                  ))}
                </tr>
                <tr style={{ borderBottom: '1px solid var(--border-color, #e5e7eb)' }}>
                  <td style={{ padding: '8px 12px', fontWeight: 'bold' }}>Cover Level</td>
                  {comparedQuotes.map((q) => (
                    <td key={q.id} style={{ padding: '8px 12px' }}>
                      {q.cover}
                    </td>
                  ))}
                </tr>

                {allLineLabels.map((label) => (
                  <tr
                    key={label}
                    style={{ borderBottom: '1px solid var(--border-color, #e5e7eb)' }}
                  >
                    <td style={{ padding: '8px 12px' }}>{label}</td>
                    {comparedQuotes.map((q) => {
                      const found = q.lines.find((l) => l.label === label)
                      return (
                        <td key={q.id} style={{ padding: '8px 12px' }}>
                          {found ? found.amount : '—'}
                        </td>
                      )
                    })}
                  </tr>
                ))}

                <tr
                  style={{
                    borderTop: '2px solid var(--border-color, #e5e7eb)',
                    backgroundColor: 'var(--bg-accent, #f8fafc)',
                  }}
                >
                  <td style={{ padding: '10px 12px', fontWeight: 'bold', fontSize: '1.05em' }}>
                    Total
                  </td>
                  {comparedQuotes.map((q) => (
                    <td
                      key={q.id}
                      style={{
                        padding: '10px 12px',
                        fontWeight: 'bold',
                        fontSize: '1.05em',
                        color: 'var(--primary-color, #2563eb)',
                      }}
                    >
                      {String(q.total)}
                    </td>
                  ))}
                </tr>
                <tr style={{ borderBottom: '1px solid var(--border-color, #e5e7eb)' }}>
                  <td style={{ padding: '8px 12px', fontWeight: 'bold' }}>Status</td>
                  {comparedQuotes.map((q) => (
                    <td key={q.id} style={{ padding: '8px 12px' }}>
                      {q.status}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}

