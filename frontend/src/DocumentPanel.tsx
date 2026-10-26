import { useEffect, useState } from 'react'
import { apiFetch } from './api'

const DOCUMENT_TYPES = [
  'INVOICE',
  'REPAIR_ESTIMATE',
  'PHOTO',
  'MAINTENANCE_RECORD',
  'PURCHASE_RECORD',
  'OTHER',
] as const

interface Checklist {
  required: string[]
  present: string[]
  missing: string[]
  complete: boolean
}

interface UploadedDocument {
  original_filename: string
  document_type: string
}

interface ErrorBody {
  detail?: string
}

interface DocumentPanelProps {
  claimId: string
  token: string
  onUnauthorized: () => void
}

function parseErrorDetail(text: string): string | undefined {
  try {
    const body = JSON.parse(text) as ErrorBody
    return typeof body.detail === 'string' ? body.detail : undefined
  } catch {
    return undefined
  }
}

export default function DocumentPanel({
  claimId,
  token,
  onUnauthorized,
}: DocumentPanelProps) {
  const [checklist, setChecklist] = useState<Checklist | null>(null)
  const [checklistError, setChecklistError] = useState<string | null>(null)
  const [docType, setDocType] = useState<string>('INVOICE')
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      try {
        const response = await apiFetch(
          `/api/claims/${claimId}/checklist`,
          {},
          token,
        )
        if (cancelled) return
        if (response.status === 401) {
          onUnauthorized()
          return
        }
        if (!response.ok) {
          setChecklistError('Could not load checklist.')
          return
        }
        const data = (await response.json()) as Checklist
        if (cancelled) return
        setChecklist(data)
        setChecklistError(null)
      } catch {
        if (!cancelled) setChecklistError('API unreachable')
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [claimId, token, onUnauthorized, refreshKey])

  const upload = async () => {
    if (!file) return
    setUploading(true)
    setMessage(null)
    try {
      const form = new FormData()
      form.append('document_type', docType)
      form.append('file', file)
      const response = await apiFetch(
        `/api/claims/${claimId}/documents`,
        { method: 'POST', body: form },
        token,
      )
      if (response.status === 401) {
        onUnauthorized()
        return
      }
      if (response.ok) {
        const doc = (await response.json()) as UploadedDocument
        setMessage(`Uploaded ${doc.original_filename} as ${doc.document_type}.`)
        setFile(null)
        setRefreshKey((key) => key + 1)
        return
      }
      const detail = parseErrorDetail(await response.text())
      if (response.status === 404) {
        setMessage('Claim not found or not visible to you.')
      } else if (response.status === 413) {
        setMessage('File is too large (limit is 10 MB).')
      } else if (response.status === 422) {
        setMessage(
          detail ?? 'File was rejected: type not allowed or contents do not match.',
        )
      } else {
        setMessage('Upload failed.')
      }
    } catch {
      setMessage('API unreachable')
    } finally {
      setUploading(false)
    }
  }

  return (
    <section>
      <h2>Documents (simulated data)</h2>

      {checklistError && <p role="alert">{checklistError}</p>}
      {checklist && (
        <>
          <p>Required: {checklist.required.join(', ')}</p>
          <p>
            Present:{' '}
            {checklist.present.length ? checklist.present.join(', ') : 'none'}
          </p>
          <p>
            {checklist.complete
              ? 'Complete'
              : `Missing: ${checklist.missing.join(', ')}`}
          </p>
        </>
      )}

      <div>
        <label htmlFor="doc-type">Document type </label>
        <select
          id="doc-type"
          value={docType}
          onChange={(event) => setDocType(event.target.value)}
          disabled={uploading}
        >
          {DOCUMENT_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>

      <div>
        <input
          type="file"
          accept="application/pdf,image/jpeg,image/png"
          disabled={uploading}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </div>

      <button type="button" onClick={upload} disabled={!file || uploading}>
        {uploading ? 'Uploading…' : 'Upload'}
      </button>

      {message && <p role="status">{message}</p>}
    </section>
  )
}