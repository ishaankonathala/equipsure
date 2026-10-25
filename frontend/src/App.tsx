import { useEffect, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

type ApiStatus =
  | { state: 'loading' }
  | { state: 'ok'; service: string }
  | { state: 'error'; message: string }

function App() {
  const [status, setStatus] = useState<ApiStatus>({ state: 'loading' })

  useEffect(() => {
    let isCurrent = true

    const checkApi = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/health`)
        if (!response.ok) {
          if (isCurrent) {
            setStatus({ state: 'error', message: `HTTP ${response.status}` })
          }
          return
        }

        const payload: unknown = await response.json()
        if (
          typeof payload === 'object' &&
          payload !== null &&
          'status' in payload &&
          payload.status === 'ok' &&
          'service' in payload &&
          typeof payload.service === 'string'
        ) {
          if (isCurrent) {
            setStatus({ state: 'ok', service: payload.service })
          }
        } else if (isCurrent) {
          setStatus({ state: 'error', message: 'Unexpected health response' })
        }
      } catch (error: unknown) {
        if (isCurrent) {
          setStatus({
            state: 'error',
            message: error instanceof Error ? error.message : String(error),
          })
        }
      }
    }

    void checkApi()
    return () => {
      isCurrent = false
    }
  }, [])

  let statusText: string
  if (status.state === 'loading') {
    statusText = 'Checking API…'
  } else if (status.state === 'ok') {
    statusText = `API status: ok (${status.service})`
  } else {
    statusText = `API unreachable: ${status.message}`
  }

  return (
    <main>
      <h1>EquipSure</h1>
      <p>Simulated data only. Advisory tools are not decisions.</p>
      <p role="status">{statusText}</p>
    </main>
  )
}

export default App
