import { useState, useEffect, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { KeyRound, CheckCircle, AlertTriangle, Check } from 'lucide-react'
import api from '../../../lib/api'
import { ROUTES } from '../../../config/routes'
import { Button, FormField, InlineAlert, GlassPanel, PasswordInput } from '../../../components'
import { useBranding } from '../../../hooks/useBranding'
import { apiErrorMessage, extractApiFieldErrors } from '../../../lib/formErrors'

export default function ResetPasswordPage() {
  const { branding } = useBranding()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token')

  const [isValidating, setIsValidating] = useState(true)
  const [userEmail, setUserEmail] = useState('')
  const [validationError, setValidationError] = useState('')

  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [success, setSuccess] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const reqChecks = useMemo(() => {
    const localpart = userEmail ? userEmail.split('@')[0].toLowerCase() : ''
    return {
      length: newPassword.length >= 12,
      upper: /[A-Z]/.test(newPassword),
      lower: /[a-z]/.test(newPassword),
      digit: /[0-9]/.test(newPassword),
      special: /[^a-zA-Z0-9]/.test(newPassword),
      notEmail: !localpart || localpart.length < 3 || !newPassword.toLowerCase().includes(localpart),
    }
  }, [newPassword, userEmail])

  useEffect(() => {
    if (!token) {
      setIsValidating(false)
      setValidationError('No reset token provided. Please request a new password reset link.')
      return
    }

    const validateToken = async () => {
      try {
        const res = await api.post('/auth/reset-password/validate', { token })
        setUserEmail(res.data?.data?.email || '')
      } catch (err) {
        setValidationError(
          err.response?.data?.message || 'Password reset token is invalid or has expired.'
        )
      } finally {
        setIsValidating(false)
      }
    }

    validateToken()
  }, [token])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setFieldErrors({})

    if (!newPassword) {
      const msg = 'New password is required.'
      setFieldErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (newPassword.length < 12) {
      const msg = 'Password must be at least 12 characters.'
      setFieldErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!/[A-Z]/.test(newPassword)) {
      const msg = 'Password must contain at least one uppercase letter.'
      setFieldErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!/[a-z]/.test(newPassword)) {
      const msg = 'Password must contain at least one lowercase letter.'
      setFieldErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!/[0-9]/.test(newPassword)) {
      const msg = 'Password must contain at least one number.'
      setFieldErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!/[^a-zA-Z0-9]/.test(newPassword)) {
      const msg = 'Password must contain at least one special character.'
      setFieldErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!reqChecks.notEmail) {
      const msg = 'Password must not contain parts of your email address.'
      setFieldErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (newPassword !== confirmPassword) {
      const msg = 'Passwords do not match.'
      setFieldErrors({ confirm_password: msg })
      setError(msg)
      return
    }

    setIsSubmitting(true)
    try {
      await api.post('/auth/reset-password', {
        token,
        new_password: newPassword,
      })
      setSuccess(true)
    } catch (err) {
      const extracted = extractApiFieldErrors(err)
      const message = apiErrorMessage(
        err,
        'Failed to reset password. The link may have expired or does not meet policy requirements.'
      )
      if (!extracted.new_password && message && message.toLowerCase().includes('password')) {
        extracted.new_password = message
      }
      setFieldErrors(extracted)
      setError(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen aurora-bg flex items-center justify-center p-4">
      <GlassPanel className="w-full max-w-md">
        <div className="mb-6 flex items-start gap-3">
          <div className="rounded-md border border-brand-border bg-brand-surface p-2 text-brand-primary">
            <KeyRound strokeWidth={1.7} className="h-6 w-6" />
          </div>
          <div>
            <h1 className="page-title text-xl font-bold">Reset Password</h1>
            <p className="text-slate-400 text-sm mt-1">
              {branding.app_name} Account Security
            </p>
          </div>
        </div>

        {isValidating ? (
          <div className="text-center py-8 text-sm text-slate-400">
            Validating reset token...
          </div>
        ) : validationError ? (
          <div className="space-y-4">
            <div className="alert-danger flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{validationError}</span>
            </div>
            <Button
              onClick={() => navigate(ROUTES.LOGIN)}
              className="w-full"
              variant="outline"
            >
              Return to Login
            </Button>
          </div>
        ) : success ? (
          <div className="space-y-4 text-center py-4">
            <div className="mx-auto w-12 h-12 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center">
              <CheckCircle className="h-6 w-6" />
            </div>
            <h2 className="text-lg font-semibold text-slate-100">
              Password Reset Complete
            </h2>
            <p className="text-sm text-slate-400">
              Your password has been successfully updated. You can now sign in with your new password.
            </p>
            <Button
              onClick={() => navigate(ROUTES.LOGIN)}
              className="w-full"
            >
              Sign In Now
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {userEmail && (
              <p className="text-xs text-slate-400 mb-2">
                Resetting password for: <span className="font-semibold text-slate-200">{userEmail}</span>
              </p>
            )}

            <InlineAlert type="error" className="mb-4" onDismiss={() => { setError(''); setFieldErrors({}); }}>
              {error}
            </InlineAlert>

            <FormField id="new-password" label="New Password" required error={fieldErrors.new_password}>
              <PasswordInput
                id="new-password"
                value={newPassword}
                onChange={(e) => {
                  setNewPassword(e.target.value)
                  if (fieldErrors.new_password) {
                    setFieldErrors((prev) => ({ ...prev, new_password: '' }))
                  }
                  if (error) setError('')
                }}
                placeholder="At least 12 characters"
                required
                autoComplete="new-password"
                autoFocus
              />
            </FormField>

            <FormField id="confirm-password" label="Confirm New Password" required error={fieldErrors.confirm_password}>
              <PasswordInput
                id="confirm-password"
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value)
                  if (fieldErrors.confirm_password) {
                    setFieldErrors((prev) => ({ ...prev, confirm_password: '' }))
                  }
                  if (error) setError('')
                }}
                placeholder="Re-enter new password"
                required
                autoComplete="new-password"
              />
            </FormField>

            <div className="text-xs bg-slate-50 border border-slate-200 dark:bg-slate-800/40 dark:border-slate-700/50 p-3.5 rounded-md space-y-2">
              <p className="font-semibold text-slate-700 dark:text-slate-300">Password Requirements:</p>
              <ul className="space-y-1.5 text-slate-600 dark:text-slate-400">
                <li className={`flex items-center gap-1.5 transition-colors ${reqChecks.length ? 'text-emerald-700 dark:text-emerald-400 font-medium' : 'text-slate-600 dark:text-slate-400'}`}>
                  <Check className={`h-3.5 w-3.5 shrink-0 transition-colors ${reqChecks.length ? 'text-emerald-700 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-400'}`} />
                  <span>Minimum 12 characters</span>
                </li>
                <li className={`flex items-center gap-1.5 transition-colors ${reqChecks.upper && reqChecks.lower ? 'text-emerald-700 dark:text-emerald-400 font-medium' : 'text-slate-600 dark:text-slate-400'}`}>
                  <Check className={`h-3.5 w-3.5 shrink-0 transition-colors ${reqChecks.upper && reqChecks.lower ? 'text-emerald-700 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-400'}`} />
                  <span>At least one uppercase and one lowercase letter</span>
                </li>
                <li className={`flex items-center gap-1.5 transition-colors ${reqChecks.digit && reqChecks.special ? 'text-emerald-700 dark:text-emerald-400 font-medium' : 'text-slate-600 dark:text-slate-400'}`}>
                  <Check className={`h-3.5 w-3.5 shrink-0 transition-colors ${reqChecks.digit && reqChecks.special ? 'text-emerald-700 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-400'}`} />
                  <span>At least one digit and one special character</span>
                </li>
                <li className={`flex items-center gap-1.5 transition-colors ${!reqChecks.notEmail ? 'text-rose-600 dark:text-rose-400 font-medium' : (newPassword && reqChecks.notEmail ? 'text-emerald-700 dark:text-emerald-400 font-medium' : 'text-slate-600 dark:text-slate-400')}`}>
                  <Check className={`h-3.5 w-3.5 shrink-0 transition-colors ${!reqChecks.notEmail ? 'text-rose-600 dark:text-rose-400' : (newPassword && reqChecks.notEmail ? 'text-emerald-700 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-400')}`} />
                  <span>Must not contain parts of your email address</span>
                </li>
              </ul>
            </div>

            <Button type="submit" loading={isSubmitting} className="w-full">
              {isSubmitting ? 'Resetting...' : 'Set New Password'}
            </Button>
          </form>
        )}
      </GlassPanel>
    </div>
  )
}
