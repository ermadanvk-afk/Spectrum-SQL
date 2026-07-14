import React, { useState } from 'react'
import { Sparkles, KeyRound, User, Eye, EyeOff } from 'lucide-react'

function Auth({ onLoginSuccess }) {
  const [isRegister, setIsRegister] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('Purchase Manager')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setMessage('')
    setLoading(true)

    // Using relative paths to support proxying in both dev and production (Nginx)
    const url = isRegister ? '/api/auth/register' : '/api/auth/login'

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(isRegister ? { username, password, role } : { username, password })
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'Something went wrong')
      }

      if (isRegister) {
        setMessage('Registration successful! Please log in.')
        setIsRegister(false)
        setPassword('')
        setShowPassword(false)
      } else {
        if (data.access_token) {
          onLoginSuccess(data.access_token, data.role)
        } else {
          throw new Error('No access token returned by the server')
        }
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      display: 'flex',
      height: '100vh',
      width: '100vw',
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: '#111',
      color: '#fff',
      fontFamily: 'Inter, system-ui, sans-serif'
    }}>
      <div style={{
        width: '100%',
        maxWidth: '400px',
        padding: '40px 32px',
        borderRadius: '16px',
        backgroundColor: '#1b1b1b',
        boxShadow: '0 12px 40px rgba(0,0,0,0.5)',
        border: '1px solid #2d2d2d',
        margin: '16px'
      }}>
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '32px',
          textAlign: 'center'
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '60px',
            height: '60px',
            borderRadius: '50%',
            backgroundColor: 'rgba(217, 119, 87, 0.1)',
            marginBottom: '8px'
          }}>
            <Sparkles size={32} style={{ color: '#d97757' }} />
          </div>
          <h2 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, letterSpacing: '-0.02em' }}>
            {isRegister ? 'Get Started' : 'Welcome Back'}
          </h2>
          <p style={{ fontSize: '0.9rem', color: '#888', margin: 0 }}>
            {isRegister ? 'Create an account to use the ERP Co-Pilot' : 'Log in to access your ERP Co-Pilot'}
          </p>
        </div>

        {error && (
          <div style={{
            padding: '12px 16px',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
            color: '#fca5a5',
            borderRadius: '8px',
            fontSize: '0.85rem',
            marginBottom: '20px',
            lineHeight: '1.4'
          }}>
            {error}
          </div>
        )}

        {message && (
          <div style={{
            padding: '12px 16px',
            backgroundColor: 'rgba(34, 197, 94, 0.1)',
            border: '1px solid rgba(34, 197, 94, 0.2)',
            color: '#86efac',
            borderRadius: '8px',
            fontSize: '0.85rem',
            marginBottom: '20px',
            lineHeight: '1.4'
          }}>
            {message}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <label style={{ fontSize: '0.85rem', color: '#aaa', fontWeight: 500 }}>Username</label>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <User size={18} style={{ position: 'absolute', left: '12px', color: '#555' }} />
              <input
                type="text"
                required
                placeholder="Enter your username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                style={{
                  width: '100%',
                  padding: '12px 12px 12px 40px',
                  borderRadius: '8px',
                  border: '1px solid #333',
                  backgroundColor: '#0d0d0d',
                  color: '#fff',
                  fontSize: '0.95rem',
                  outline: 'none',
                  boxSizing: 'border-box',
                  transition: 'border-color 0.2s'
                }}
              />
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <label style={{ fontSize: '0.85rem', color: '#aaa', fontWeight: 500 }}>Password</label>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <KeyRound size={18} style={{ position: 'absolute', left: '12px', color: '#555' }} />
              <input
                type={showPassword ? 'text' : 'password'}
                required
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{
                  width: '100%',
                  padding: '12px 40px 12px 40px',
                  borderRadius: '8px',
                  border: '1px solid #333',
                  backgroundColor: '#0d0d0d',
                  color: '#fff',
                  fontSize: '0.95rem',
                  outline: 'none',
                  boxSizing: 'border-box',
                  transition: 'border-color 0.2s'
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: 'absolute',
                  right: '12px',
                  background: 'none',
                  border: 'none',
                  color: '#555',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  padding: 0
                }}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {isRegister && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '0.85rem', color: '#aaa', fontWeight: 500 }}>Role</label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                style={{
                  width: '100%',
                  padding: '12px',
                  borderRadius: '8px',
                  border: '1px solid #333',
                  backgroundColor: '#0d0d0d',
                  color: '#fff',
                  fontSize: '0.95rem',
                  outline: 'none',
                  boxSizing: 'border-box',
                  transition: 'border-color 0.2s',
                  appearance: 'none' /* Optional: hides default browser dropdown arrow on some OS */
                }}
              >
                <option value="Purchase Manager">Purchase Manager</option>
                <option value="Warehouse Manager">Warehouse Manager</option>
                <option value="Purchase Executive">Purchase Executive</option>
              </select>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              padding: '14px',
              borderRadius: '8px',
              border: 'none',
              backgroundColor: '#d97757',
              color: '#fff',
              fontSize: '1rem',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'background-color 0.2s, opacity 0.2s',
              marginTop: '8px',
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              opacity: loading ? 0.7 : 1
            }}
          >
            {loading ? 'Processing...' : isRegister ? 'Sign Up' : 'Log In'}
          </button>
        </form>

        <div style={{ display: 'flex', justifyContent: 'center', marginTop: '24px', fontSize: '0.9rem' }}>
          <button
            type="button"
            onClick={() => { setIsRegister(!isRegister); setError(''); setMessage(''); }}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#d97757',
              cursor: 'pointer',
              textDecoration: 'none',
              fontWeight: 500
            }}
          >
            {isRegister ? 'Already have an account? Log In' : "Don't have an account? Sign Up"}
          </button>
        </div>
      </div>
    </div>
  )
}

export default Auth
