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

interface ClaimDocumentMetadata {
  id: string
  claim_id: string
  document_type: string
  original_filename: string
  content_type: string
  size_bytes: number
  uploaded_at: string
}

interface ErrorBody {
  detail?: string
}

interface DocumentPanelProps {
  claimId: string
  token: string
  onUnauthorized: () => void
  onUploaded?: () => void
}

function parseErrorDetail(text: string): string | undefined {
  try {
    const body = JSON.parse(text) as ErrorBody
    return typeof body.detail === 'string' ? body.detail : undefined
  } catch {
    return undefined
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

export default function DocumentPanel({
  claimId,
  token,
  onUnauthorized,
  onUploaded,
}: DocumentPanelProps) {
  const [checklist, setChecklist] = useState<Checklist | null>(null)
  const [checklistError, setChecklistError] = useState<string | null>(null)
  const [documents, setDocuments] = useState<ClaimDocumentMetadata[]>([])
  const [docsLoading, setDocsLoading] = useState(true)
  const [docsError, setDocsError] = useState<string | null>(null)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [docType, setDocType] = useState<string>('INVOICE')
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      setDocsLoading(true)
      try {
        const encodedClaimId = encodeURIComponent(claimId)
        const [checklistRes, docsRes] = await Promise.all([
          apiFetch(`/api/claims/${encodedClaimId}/checklist`, {}, token),
          apiFetch(`/api/claims/${encodedClaimId}/documents`, {}, token),
        ])
        if (cancelled) return
        if (checklistRes.status === 401 || docsRes.status === 401) {
          onUnauthorized()
          return
        }

        if (!checklistRes.ok) {
          setChecklistError('Could not load checklist.')
        } else {
          const data = (await checklistRes.json()) as Checklist
          if (!cancelled) {
            setChecklist(data)
            setChecklistError(null)
          }
        }

        if (docsRes.status === 403) {
          setDocsError('Your role is not permitted to view uploaded documents.')
          setDocuments([])
        } else if (docsRes.status === 404) {
          setDocsError('Claim documents not found or not visible to you.')
          setDocuments([])
        } else if (!docsRes.ok) {
          setDocsError('Could not load uploaded documents.')
          setDocuments([])
        } else {
          const docList = (await docsRes.json()) as ClaimDocumentMetadata[]
          if (!cancelled) {
            setDocuments(docList)
            setDocsError(null)
          }
        }
      } catch {
        if (!cancelled) {
          setChecklistError('API unreachable')
          setDocsError('API unreachable')
        }
      } finally {
        if (!cancelled) {
          setDocsLoading(false)
        }
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
        onUploaded?.()
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

  const downloadDocument = async (doc: ClaimDocumentMetadata) => {
    setDownloadingId(doc.id)
    setDownloadError(null)
    try {
      const response = await apiFetch(
        `/api/claims/${encodeURIComponent(claimId)}/documents/${encodeURIComponent(doc.id)}`,
        {},
        token,
      )
      if (response.status === 401) {
        onUnauthorized()
        return
      }
      if (response.status === 404) {
        setDownloadError(`Document "${doc.original_filename}" could not be found.`)
        return
      }
      if (!response.ok) {
        setDownloadError(`Could not download "${doc.original_filename}".`)
        return
      }

      const blob = await response.blob()
      const objectUrl = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = doc.original_filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(objectUrl)
    } catch {
      setDownloadError('API unreachable')
    } finally {
      setDownloadingId(null)
    }
  }

  return (
    <section className="es-card">
      <div className="es-card-header">
        <h2>Documents (simulated data)</h2>
        <span className="es-status-chip">
          {documents.length} {documents.length === 1 ? 'file' : 'files'}
        </span>
      </div>

      {checklistError && <p role="alert">{checklistError}</p>}
      {checklist && (
        <div className="es-checklist-box">
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
        </div>
      )}

      <div className="es-documents-list-section">
        <h3 className="es-subheading">Uploaded evidence</h3>
        {docsLoading && <p role="status">Loading uploaded documents…</p>}
        {docsError && <p role="alert">{docsError}</p>}
        {downloadError && <p role="alert">{downloadError}</p>}
        {!docsLoading && !docsError && documents.length === 0 && (
          <p className="es-advisory-note">No documents uploaded for this claim yet.</p>
        )}
        {!docsLoading && !docsError && documents.length > 0 && (
          <ul className="es-document-list">
            {documents.map((doc) => (
              <li key={doc.id} className="es-document-item">
                <div className="es-document-meta">
                  <div className="es-document-title-row">
                    <strong>{doc.original_filename}</strong>
                    <span className="es-status-chip">{doc.document_type}</span>
                  </div>
                  <span className="es-advisory-note">
                    {formatFileSize(doc.size_bytes)} · Uploaded{' '}
                    {new Date(doc.uploaded_at).toLocaleString()}
                  </span>
                </div>
                <button
                  type="button"
                  className="es-btn-secondary"
                  disabled={downloadingId === doc.id}
                  onClick={() => void downloadDocument(doc)}
                >
                  {downloadingId === doc.id ? 'Downloading…' : 'Download'}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="es-field-group">
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

      <div className="es-field-group">
        <input
          type="file"
          accept="application/pdf,image/jpeg,image/png"
          disabled={uploading}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </div>

      <button
        type="button"
        className="es-btn-primary"
        onClick={upload}
        disabled={!file || uploading}
      >
        {uploading ? 'Uploading…' : 'Upload'}
      </button>

      {message && <p role="status">{message}</p>}
    </section>
  )
}
