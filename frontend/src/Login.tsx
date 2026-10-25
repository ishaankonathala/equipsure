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
    <form onSubmit={handleSubmit}>
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

      <label htmlFor="password">Password</label>
      <input
        id="password"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        required
      />

      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Signing in…' : 'Sign in'}
      </button>
      {error !== null && <p role="alert">{error}</p>}
    </form>
  )
}

export default Login