import { useState, useMemo } from 'react'
import { Check } from 'lucide-react'
import api from '../../../lib/api'
import { updateStoredUser } from '../../../lib/auth'
import { Button, FeedbackToast, FormField, InlineAlert, GlassPanel, PasswordInput } from '../../../components'
import { useBranding } from '../../../hooks/useBranding'
import { apiErrorMessage, extractApiFieldErrors } from '../../../lib/formErrors'

export default function PasswordChangePage({ user, onPasswordChanged }) {
  const { branding } = useBranding()
  const [form, setForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  })
  const [fieldErrors, setFieldErrors] = useState({})
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  const reqChecks = useMemo(() => {
    const localpart = user?.email ? user.email.split('@')[0].toLowerCase() : ''
    return {
      length: form.new_password.length >= 12,
      upper: /[A-Z]/.test(form.new_password),
      lower: /[a-z]/.test(form.new_password),
      digit: /[0-9]/.test(form.new_password),
      special: /[^a-zA-Z0-9]/.test(form.new_password),
      notEmail: !localpart || localpart.length < 3 || !form.new_password.toLowerCase().includes(localpart),
    }
  }, [form.new_password, user?.email])

  const handleSubmit = async (event) => {
    event.preventDefault()
    setFieldErrors({})
    setError('')
    setSuccess('')

    if (!form.current_password) {
      const msg = 'Current password is required.'
      setFieldErrors({ current_password: msg })
      setError(msg)
      return
    }
    if (form.new_password.length < 12) {
      const msg = 'New password must be at least 12 characters.'
      setFieldErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!/[A-Z]/.test(form.new_password)) {
      const msg = 'New password must contain at least one uppercase letter.'
      setFieldErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!/[a-z]/.test(form.new_password)) {
      const msg = 'New password must contain at least one lowercase letter.'
      setFieldErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!/[0-9]/.test(form.new_password)) {
      const msg = 'New password must contain at least one number.'
      setFieldErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!/[^a-zA-Z0-9]/.test(form.new_password)) {
      const msg = 'New password must contain at least one special character.'
      setFieldErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!reqChecks.notEmail) {
      const msg = 'New password must not contain parts of your email address.'
      setFieldErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (form.new_password !== form.confirm_password) {
      const msg = 'New password and confirmation do not match.'
      setFieldErrors({ confirm_password: msg })
      setError(msg)
      return
    }

    setLoading(true)
    try {
      await api.post('/auth/change-password', {
        current_password: form.current_password,
        new_password: form.new_password,
      })
      const updatedUser = { ...user, must_change_password: false }
      updateStoredUser({ must_change_password: false })
      setSuccess(`Password updated. You can now use the full ${branding.app_name} workspace.`)
      onPasswordChanged?.(updatedUser)
    } catch (err) {
      const extracted = extractApiFieldErrors(err)
      const message = apiErrorMessage(err, 'Unable to change password.')
      if (!extracted.new_password && message && message.toLowerCase().includes('password')) {
        extracted.new_password = message
      }
      setFieldErrors(extracted)
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen aurora-bg flex items-center justify-center p-4">
      <GlassPanel className="w-full max-w-lg">
        <div className="mb-6">
          <h1 className="page-title mb-2">Change Temporary Password</h1>
          <p className="text-slate-600 dark:text-slate-400 text-sm">
            {user?.full_name || user?.email}, your administrator-created account is protected behind a mandatory first-login password change.
          </p>
        </div>

        <FeedbackToast type="success" message={success} onDismiss={() => setSuccess('')} />
        <InlineAlert type="error" className="mb-4" onDismiss={() => { setError(''); setFieldErrors({}); }}>
          {error}
        </InlineAlert>

        <form onSubmit={handleSubmit} className="space-y-4">
          <FormField id="temporary-password" label="Temporary Password" required error={fieldErrors.current_password}>
            <PasswordInput
              id="temporary-password"
              value={form.current_password}
              onChange={(e) => {
                setForm({ ...form, current_password: e.target.value })
                if (fieldErrors.current_password) {
                  setFieldErrors((prev) => ({ ...prev, current_password: '' }))
                }
                if (error) setError('')
              }}
              wrapperClassName="mt-1"
              required
              autoComplete="current-password"
            />
          </FormField>
          <FormField id="new-password" label="New Password" required error={fieldErrors.new_password}>
            <PasswordInput
              id="new-password"
              value={form.new_password}
              onChange={(e) => {
                setForm({ ...form, new_password: e.target.value })
                if (fieldErrors.new_password) {
                  setFieldErrors((prev) => ({ ...prev, new_password: '' }))
                }
                if (error) setError('')
              }}
              wrapperClassName="mt-1"
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
              <li className={`flex items-center gap-1.5 transition-colors ${!reqChecks.notEmail ? 'text-rose-600 dark:text-rose-400 font-medium' : (form.new_password && reqChecks.notEmail ? 'text-emerald-700 dark:text-emerald-400 font-medium' : 'text-slate-600 dark:text-slate-400')}`}>
                <Check className={`h-3.5 w-3.5 shrink-0 transition-colors ${!reqChecks.notEmail ? 'text-rose-600 dark:text-rose-400' : (form.new_password && reqChecks.notEmail ? 'text-emerald-700 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-400')}`} />
                <span>Must not contain parts of your email address</span>
              </li>
            </ul>
          </div>

          <FormField id="confirm-new-password" label="Confirm New Password" required error={fieldErrors.confirm_password}>
            <PasswordInput
              id="confirm-new-password"
              value={form.confirm_password}
              onChange={(e) => {
                setForm({ ...form, confirm_password: e.target.value })
                if (fieldErrors.confirm_password) {
                  setFieldErrors((prev) => ({ ...prev, confirm_password: '' }))
                }
                if (error) setError('')
              }}
              wrapperClassName="mt-1"
              required
              autoComplete="new-password"
            />
          </FormField>
          <Button type="submit" loading={loading} className="w-full">
            Update Password
          </Button>
        </form>
      </GlassPanel>
    </div>
  )
}
