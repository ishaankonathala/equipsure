import { useState, type FormEvent } from 'react'

import { apiFetch } from './api'
import type { LoginResponse } from './types'

interface LoginProps {
  onLogin: (token: string) => void
}

function isLoginResponse(value: unknown): value is LoginResponse {
  return (
    typeof value === 'object' &&
    value !== null &&
    'access_token' in value &&
    typeof value.access_token === 'string' &&
    'token_type' in value &&
    typeof value.token_type === 'string' &&
    'expires_in' in value &&
    typeof value.expires_in === 'number'
  )
}

function Login({ onLogin }: LoginProps) {
  const [email, setEmail] = useState('cafe.owner@equipsure.demo')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      let response: Response
      try {
        response = await apiFetch('/api/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        })
      } catch {
        setError('API unreachable')
        return
      }

      if (!response.ok) {
        setError('Sign-in failed. Check the password.')
        return
      }

      try {
        const payload: unknown = await response.json()
        if (isLoginResponse(payload)) {
          onLogin(payload.access_token)
        } else {
          setError('Sign-in failed. Check the password.')
        }
      } catch {
        setError('Sign-in failed. Check the password.')
      }
    } finally {
      setPassword('')
      setIsSubmitting(false)
    }
  }

  return (
    <div className="es-login-layout">
      <aside className="es-login-overview">
        <div className="es-login-overview-body">
          <span className="es-eyebrow">Commercial Equipment Insurance</span>
          <h2 className="es-login-heading">Equipment protection, made simpler</h2>
          <p className="es-login-description">
            Review café machinery breakdown claims, verify repair documentation,
            and consult clause-cited policy guidance for commercial espresso
            systems, grinders, refrigeration units, and food-service equipment.
          </p>
        </div>
        <figure className="es-equipment-figure">
          <img
            className="es-equipment-image"
            src="https://images.unsplash.com/photo-1553801088-0933f7ce7706?auto=format&fit=crop&w=1000&q=80"
            alt="Commercial stainless-steel espresso machine in a café"
            loading="lazy"
          />
          <figcaption className="es-equipment-caption">
            Covered equipment classes include commercial espresso machines,
            grinders, refrigeration, ovens, and dishwashers (simulated data).
          </figcaption>
        </figure>
      </aside>

      <form className="es-login-card" onSubmit={handleSubmit}>
        <div className="es-login-card-header">
          <h2>Sign in</h2>
          <p>Select a demo account to access the claims workspace.</p>
        </div>

        <div className="es-field-group">
          <label htmlFor="demo-account">Demo account</label>
          <select
            id="demo-account"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          >
            <option value="cafe.owner@equipsure.demo">
              Café owner (cafe.owner@equipsure.demo)
            </option>
            <option value="ops.officer@equipsure.demo">
              OPS officer (ops.officer@equipsure.demo)
            </option>
          </select>
        </div>

        <div className="es-field-group">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Signing in…' : 'Sign in'}
        </button>
        {error !== null && <p role="alert">{error}</p>}
      </form>
    </div>
  )
}

export default Login