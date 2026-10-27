import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LockKeyhole, ShieldCheck, KeyRound, ArrowLeft } from 'lucide-react'
import api from '../../../lib/api'
import { setAuthData } from '../../../lib/auth'
import { resolvePostLoginRedirect } from '../../../lib/authRedirect'
import { Button, FormField, InlineAlert, Modal, PasswordInput } from '../../../components'
import { useBranding } from '../../../hooks/useBranding'

export function LoginModal({ open, onClose, onLogin, returnTo = null }) {
  const navigate = useNavigate()
  const { branding } = useBranding()

  // Form states
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [infoMessage, setInfoMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  // MFA Challenge states
  const [mfaChallengeToken, setMfaChallengeToken] = useState(null)
  const [mfaCode, setMfaCode] = useState('')
  const [useRecoveryCode, setUseRecoveryCode] = useState(false)

  // Forgot password states
  const [isForgotPassword, setIsForgotPassword] = useState(false)
  const [forgotEmail, setForgotEmail] = useState('')

  const handleResetState = () => {
    setError('')
    setInfoMessage('')
    setMfaChallengeToken(null)
    setMfaCode('')
    setUseRecoveryCode(false)
    setIsForgotPassword(false)
  }

  const handleModalClose = () => {
    handleResetState()
    onClose?.()
  }

  const handleLoginSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setInfoMessage('')
    setIsLoading(true)

    try {
      const res = await api.post('/auth/login', { email, password })
      const data = res.data.data

      if (data.mfa_required) {
        setMfaChallengeToken(data.challenge_token || data.mfa_challenge_token)
        setError('')
        return
      }

      setAuthData(data)
      onLogin?.(data.user)
      navigate(resolvePostLoginRedirect(data.user, returnTo), { replace: true })
    } catch (err) {
      setError(err.response?.data?.message || 'Invalid email or password')
    } finally {
      setIsLoading(false)
    }
  }

  const handleMfaVerifySubmit = async (event) => {
    event.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      const payload = useRecoveryCode
        ? { recovery_code: mfaCode.trim() }
        : { code: mfaCode.trim() }

      const res = await api.post('/auth/mfa/verify', payload, {
        headers: {
          Authorization: `Bearer ${mfaChallengeToken}`,
        },
      })
      const data = res.data.data
      setAuthData(data)
      onLogin?.(data.user)
      navigate(resolvePostLoginRedirect(data.user, returnTo), { replace: true })
    } catch (err) {
      setError(err.response?.data?.message || 'Verification failed. Please check your code.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleForgotPasswordSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setInfoMessage('')
    setIsLoading(true)

    try {
      const res = await api.post('/auth/forgot-password', { email: forgotEmail })
      setInfoMessage(
        res.data?.message ||
          'If this email is associated with an active account, password reset instructions have been sent.'
      )
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to process password reset request.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Modal
      open={open}
      title={
        mfaChallengeToken
          ? 'Two-Factor Authentication'
          : isForgotPassword
          ? 'Reset Your Password'
          : `Sign in to ${branding.app_name}`
      }
      description={
        mfaChallengeToken
          ? 'Enter the 6-digit code from your authenticator app or an 8-character recovery code.'
          : isForgotPassword
          ? 'Enter your account email to receive a password reset link.'
          : 'Use your provisioned internal DILG-PDMU account.'
      }
      onClose={handleModalClose}
      size="sm"
    >
      <div className="mb-5 flex items-start gap-3">
        <div className="rounded-md border border-brand-border bg-brand-surface p-2 text-brand-primary">
          {mfaChallengeToken ? (
            <ShieldCheck strokeWidth={1.7} className="h-5 w-5" />
          ) : isForgotPassword ? (
            <KeyRound strokeWidth={1.7} className="h-5 w-5" />
          ) : (
            <LockKeyhole strokeWidth={1.7} className="h-5 w-5" />
          )}
        </div>
        <p className="text-sm leading-6 text-brand-text-muted">
          {mfaChallengeToken
            ? 'Account protected by two-factor authentication. Please verify your identity.'
            : isForgotPassword
            ? 'Password reset links expire in 15 minutes and can only be used once.'
            : `Access is limited to authorized ${branding.app_name} users. Contact your administrator to request access.`}
        </p>
      </div>

      <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>
        {error}
      </InlineAlert>

      {infoMessage && (
        <div className="mb-4 rounded-md border border-brand-border bg-emerald-500/10 p-3 text-xs text-emerald-300">
          {infoMessage}
        </div>
      )}

      {mfaChallengeToken ? (
        <form onSubmit={handleMfaVerifySubmit} className="space-y-4">
          <FormField
            id="mfa-code"
            label={useRecoveryCode ? '8-Character Recovery Code' : '6-Digit Verification Code'}
          >
            <input
              id="mfa-code"
              type="text"
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
              className="input-field font-mono text-center tracking-widest text-lg"
              placeholder={useRecoveryCode ? 'xxxx-xxxx' : '000000'}
              required
              autoFocus
              maxLength={useRecoveryCode ? 16 : 6}
            />
          </FormField>

          <Button type="submit" loading={isLoading} className="w-full">
            {isLoading ? 'Verifying...' : 'Verify Code'}
          </Button>

          <div className="flex items-center justify-between text-xs pt-2">
            <button
              type="button"
              onClick={() => {
                setUseRecoveryCode(!useRecoveryCode)
                setMfaCode('')
                setError('')
              }}
              className="text-brand-primary hover:underline"
            >
              {useRecoveryCode ? 'Use authenticator app' : 'Use recovery code'}
            </button>
            <button
              type="button"
              onClick={() => {
                setMfaChallengeToken(null)
                setMfaCode('')
                setError('')
              }}
              className="text-brand-text-muted hover:text-brand-text"
            >
              Back to login
            </button>
          </div>
        </form>
      ) : isForgotPassword ? (
        <form onSubmit={handleForgotPasswordSubmit} className="space-y-4">
          <FormField id="forgot-email" label="Account Email">
            <input
              id="forgot-email"
              type="email"
              value={forgotEmail}
              onChange={(e) => setForgotEmail(e.target.value)}
              className="input-field"
              placeholder="user@example.gov.ph"
              required
              autoFocus
            />
          </FormField>

          <Button type="submit" loading={isLoading} className="w-full">
            {isLoading ? 'Sending...' : 'Send Reset Link'}
          </Button>

          <div className="text-center pt-2">
            <button
              type="button"
              onClick={() => {
                setIsForgotPassword(false)
                setError('')
                setInfoMessage('')
              }}
              className="inline-flex items-center gap-1.5 text-xs text-brand-primary hover:underline"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> Back to Sign In
            </button>
          </div>
        </form>
      ) : (
        <form onSubmit={handleLoginSubmit} className="space-y-4">
          <FormField id="login-email" label="Email">
            <input
              id="login-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="input-field"
              placeholder="admin@example.gov.ph"
              required
              autoFocus
            />
          </FormField>

          <FormField id="login-password" label="Password">
            <PasswordInput
              id="login-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter your password"
              required
              autoComplete="current-password"
            />
          </FormField>

          <div className="flex items-center justify-end">
            <button
              type="button"
              onClick={() => {
                setIsForgotPassword(true)
                setForgotEmail(email)
                setError('')
                setInfoMessage('')
              }}
              className="text-xs text-brand-primary hover:underline"
            >
              Forgot password?
            </button>
          </div>

          <Button type="submit" loading={isLoading} className="w-full">
            {isLoading ? 'Signing in...' : 'Sign In'}
          </Button>
        </form>
      )}
    </Modal>
  )
}
