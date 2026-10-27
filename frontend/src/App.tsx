import { useEffect, useState } from 'react'
import { Link, Navigate, Outlet, Route, Routes, useNavigate } from 'react-router-dom'

import { apiFetch } from './api'
import AssistantPanel from './AssistantPanel'
import ClaimList from './ClaimList'
import ClaimView from './ClaimView'
import Login from './Login'
import NotificationsPanel from './NotificationsPanel'
import type { CurrentUser } from './types'

type ApiStatus =
  | { state: 'loading' }
  | { state: 'ok'; service: string }
  | { state: 'error'; message: string }

function isCurrentUser(value: unknown): value is CurrentUser {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    typeof value.id === 'string' &&
    'email' in value &&
    typeof value.email === 'string' &&
    'full_name' in value &&
    typeof value.full_name === 'string' &&
    'role' in value &&
    typeof value.role === 'string' &&
    'business_id' in value &&
    (typeof value.business_id === 'string' || value.business_id === null) &&
    'is_active' in value &&
    typeof value.is_active === 'boolean'
  )
}

function App() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<ApiStatus>({ state: 'loading' })
  const [token, setToken] = useState<string | null>(null)
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null)
  const [userError, setUserError] = useState<string | null>(null)
  const [claimId, setClaimId] = useState('')

  useEffect(() => {
    let isCurrent = true

    const checkApi = async () => {
      try {
        const response = await apiFetch('/api/health')
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

  useEffect(() => {
    if (token === null) {
      return
    }

    let isCurrent = true

    const loadCurrentUser = async () => {
      try {
        const response = await apiFetch('/api/auth/me', {}, token)
        if (response.status === 401) {
          if (isCurrent) {
            setToken(null)
            setCurrentUser(null)
          }
          return
        }
        if (!response.ok) {
          if (isCurrent) {
            setUserError(`HTTP ${response.status}`)
          }
          return
        }

        const payload: unknown = await response.json()
        if (isCurrent && isCurrentUser(payload)) {
          setCurrentUser(payload)
        } else if (isCurrent) {
          setUserError('Unexpected user response')
        }
      } catch (error: unknown) {
        if (isCurrent) {
          setUserError(error instanceof Error ? error.message : String(error))
        }
      }
    }

    void loadCurrentUser()
    return () => {
      isCurrent = false
    }
  }, [token])

  const handleLogout = () => {
    setToken(null)
    setCurrentUser(null)
    setUserError(null)
    setClaimId('')
    navigate('/login', { replace: true })
  }

  const handleLogin = (accessToken: string) => {
    setCurrentUser(null)
    setUserError(null)
    setToken(accessToken)
    navigate('/', { replace: true })
  }

  let statusText: string
  if (status.state === 'loading') {
    statusText = 'Checking API…'
  } else if (status.state === 'ok') {
    statusText = `API status: ok (${status.service})`
  } else {
    statusText = `API unreachable: ${status.message}`
  }

  const requireSession = (children: React.ReactNode) =>
    token === null ? <Navigate to="/login" replace /> : children

  return (
    <main>
      <h1>EquipSure</h1>
      <p>Simulated data only. Advisory tools are not decisions.</p>
      <p role="status">{statusText}</p>
      <Routes>
        <Route path="/login" element={<Login onLogin={handleLogin} />} />
        <Route
          element={
            requireSession(
              <section>
                {currentUser !== null ? (
                  <p>
                    Signed in as {currentUser.full_name} ({currentUser.role})
                  </p>
                ) : userError !== null ? (
                  <p role="alert">Unable to load user: {userError}</p>
                ) : (
                  <p role="status">Loading user…</p>
                )}
                <nav>
                  <Link to="/">Dashboard</Link>{' '}
                  <Link to="/notifications">Notifications</Link>{' '}
                  <button type="button" onClick={handleLogout}>
                    Logout
                  </button>
                </nav>
                <Outlet />
              </section>,
            )
          }
        >
          <Route
            path="/"
            element={
              <>
                <ClaimList
                  token={token ?? ''}
                  onUnauthorized={handleLogout}
                  onSelect={setClaimId}
                />
                <ClaimView
                  token={token ?? ''}
                  claimId={claimId}
                  role={currentUser?.role ?? ''}
                  onClaimIdChange={setClaimId}
                  onUnauthorized={handleLogout}
                />
                <AssistantPanel token={token ?? ''} onUnauthorized={handleLogout} />
              </>
            }
          />
          <Route
            path="/notifications"
            element={
              <NotificationsPanel token={token ?? ''} onUnauthorized={handleLogout} />
            }
          />
        </Route>
        <Route path="*" element={<Navigate to={token === null ? '/login' : '/'} replace />} />
      </Routes>
    </main>
  )
}

export default App