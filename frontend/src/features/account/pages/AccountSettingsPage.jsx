import { useEffect, useState, useMemo } from 'react'
import { KeyRound, Save, Check, Bell, ShieldAlert } from 'lucide-react'
import { Button, FeedbackToast, FormField, GlassPanel, InlineAlert, PageHeader, PasswordInput } from '../../../components'
import { formatRole } from '../../../lib/formatters'
import { setUser as storeUser } from '../../../lib/auth'
import { apiErrorMessage, extractApiFieldErrors } from '../../../lib/formErrors'
import { useBranding } from '../../../hooks/useBranding'
import * as accountApi from '../api/accountApi'

const EMPTY_PASSWORD_FORM = {
  current_password: '',
  new_password: '',
  confirm_password: '',
}

const DEFAULT_PREFERENCES = {
  email_critical_alerts: true,
  email_deadline_reminders: true,
  email_review_reminders: true,
  email_workflow_notifications: true,
  email_daily_digest: false,
  in_app_critical_alerts: true,
  in_app_deadline_reminders: true,
  in_app_review_reminders: true,
  in_app_workflow_notifications: true,
}

function notifyStoredUserChanged() {
  window.dispatchEvent(new Event('comet:user-updated'))
}

export default function AccountSettingsPage() {
  const { branding } = useBranding()
  const [profile, setProfile] = useState(null)
  const [profileForm, setProfileForm] = useState({
    first_name: '',
    last_name: '',
  })
  const [passwordForm, setPasswordForm] = useState(EMPTY_PASSWORD_FORM)
  const [passwordErrors, setPasswordErrors] = useState({})
  const [prefs, setPrefs] = useState(DEFAULT_PREFERENCES)
  const [loading, setLoading] = useState(true)
  const [profileSaving, setProfileSaving] = useState(false)
  const [passwordSaving, setPasswordSaving] = useState(false)
  const [prefsSaving, setPrefsSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const passwordReqChecks = useMemo(() => {
    const localpart = profile?.email ? profile.email.split('@')[0].toLowerCase() : ''
    return {
      length: passwordForm.new_password.length >= 12,
      upper: /[A-Z]/.test(passwordForm.new_password),
      lower: /[a-z]/.test(passwordForm.new_password),
      digit: /[0-9]/.test(passwordForm.new_password),
      special: /[^a-zA-Z0-9]/.test(passwordForm.new_password),
      notEmail: !localpart || localpart.length < 3 || !passwordForm.new_password.toLowerCase().includes(localpart),
    }
  }, [passwordForm.new_password, profile?.email])

  useEffect(() => {
    let active = true
    async function loadProfile() {
      setLoading(true)
      setError('')
      try {
        const [profileResponse, prefsResponse] = await Promise.allSettled([
          accountApi.getAccountProfile(),
          accountApi.getNotificationPreferences(),
        ])
        if (!active) return

        if (profileResponse.status === 'fulfilled') {
          const loadedProfile = profileResponse.value?.data || profileResponse.value || {}
          setProfile(loadedProfile)
          setProfileForm({
            first_name: loadedProfile.first_name || '',
            last_name: loadedProfile.last_name || '',
          })
        } else {
          setError(profileResponse.reason?.response?.data?.message || 'Unable to load your account.')
        }

        if (prefsResponse.status === 'fulfilled') {
          const raw = prefsResponse.value
          const loadedPrefs = raw?.data || raw?.preferences || raw || {}
          setPrefs((current) => ({ ...current, ...loadedPrefs }))
        }
      } catch (requestError) {
        if (active) {
          setError(requestError.response?.data?.message || 'Unable to load your account.')
        }
      } finally {
        if (active) setLoading(false)
      }
    }
    loadProfile()
    return () => {
      active = false
    }
  }, [])

  async function handlePrefsSubmit(event) {
    event.preventDefault()
    setPrefsSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await accountApi.updateNotificationPreferences({
        email_critical_alerts: true,
        email_deadline_reminders: Boolean(prefs.email_deadline_reminders),
        email_review_reminders: Boolean(prefs.email_review_reminders),
        email_workflow_notifications: Boolean(prefs.email_workflow_notifications),
        email_daily_digest: Boolean(prefs.email_daily_digest),
        in_app_critical_alerts: true,
        in_app_deadline_reminders: Boolean(prefs.in_app_deadline_reminders),
        in_app_review_reminders: Boolean(prefs.in_app_review_reminders),
        in_app_workflow_notifications: Boolean(prefs.in_app_workflow_notifications),
      })
      const updatedPrefs = response?.data || response?.preferences
      if (updatedPrefs) {
        setPrefs((current) => ({ ...current, ...updatedPrefs }))
      }
      setMessage('Notification preferences updated successfully.')
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to update notification preferences.')
    } finally {
      setPrefsSaving(false)
    }
  }

  async function handleProfileSubmit(event) {
    event.preventDefault()
    const firstName = profileForm.first_name.trim()
    const lastName = profileForm.last_name.trim()
    if (!firstName || !lastName) {
      setError('First name and last name are required.')
      return
    }

    setProfileSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await accountApi.updateAccountProfile({
        first_name: firstName,
        last_name: lastName,
      })
      const updatedProfile = response.data
      setProfile(updatedProfile)
      setProfileForm({
        first_name: updatedProfile.first_name || '',
        last_name: updatedProfile.last_name || '',
      })
      storeUser(updatedProfile)
      notifyStoredUserChanged()
      setMessage('Account profile updated.')
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to update your account profile.')
    } finally {
      setProfileSaving(false)
    }
  }

  async function handlePasswordSubmit(event) {
    event.preventDefault()
    setPasswordErrors({})
    setError('')
    setMessage('')

    if (!passwordForm.current_password) {
      const msg = 'Current password is required.'
      setPasswordErrors({ current_password: msg })
      setError(msg)
      return
    }
    if (passwordForm.new_password.length < 12) {
      const msg = 'New password must be at least 12 characters.'
      setPasswordErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!/[A-Z]/.test(passwordForm.new_password)) {
      const msg = 'New password must contain at least one uppercase letter.'
      setPasswordErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!/[a-z]/.test(passwordForm.new_password)) {
      const msg = 'New password must contain at least one lowercase letter.'
      setPasswordErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!/[0-9]/.test(passwordForm.new_password)) {
      const msg = 'New password must contain at least one number.'
      setPasswordErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!/[^a-zA-Z0-9]/.test(passwordForm.new_password)) {
      const msg = 'New password must contain at least one special character.'
      setPasswordErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (!passwordReqChecks.notEmail) {
      const msg = 'New password must not contain parts of your email address.'
      setPasswordErrors({ new_password: msg })
      setError(msg)
      return
    }
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      const msg = 'New password and confirmation do not match.'
      setPasswordErrors({ confirm_password: msg })
      setError(msg)
      return
    }

    setPasswordSaving(true)
    try {
      await accountApi.changeAccountPassword({
        current_password: passwordForm.current_password,
        new_password: passwordForm.new_password,
      })
      const updatedProfile = profile ? { ...profile, must_change_password: false } : profile
      if (updatedProfile) {
        setProfile(updatedProfile)
        storeUser(updatedProfile)
        notifyStoredUserChanged()
      }
      setPasswordForm(EMPTY_PASSWORD_FORM)
      setMessage('Password updated.')
    } catch (requestError) {
      const extracted = extractApiFieldErrors(requestError)
      const errorMsg = apiErrorMessage(requestError, 'Unable to update your password.')
      if (!extracted.new_password && errorMsg && errorMsg.toLowerCase().includes('password')) {
        extracted.new_password = errorMsg
      }
      setPasswordErrors(extracted)
      setError(errorMsg)
    } finally {
      setPasswordSaving(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="Account"
        description={`Manage your ${branding.app_name} profile and password.`}
      />

      <FeedbackToast type="success" message={message} onDismiss={() => setMessage('')} />
      <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>
        {error}
      </InlineAlert>

      {loading ? (
        <div className="py-16 text-center text-sm text-brand-text-muted">Loading account...</div>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
          <GlassPanel>
            <form onSubmit={handleProfileSubmit} className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-brand-text">Profile</h2>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <FormField id="account-first-name" label="First Name" required>
                  <input
                    id="account-first-name"
                    className="input-field mt-1"
                    value={profileForm.first_name}
                    onChange={(event) => setProfileForm((current) => ({ ...current, first_name: event.target.value }))}
                    required
                  />
                </FormField>
                <FormField id="account-last-name" label="Last Name" required>
                  <input
                    id="account-last-name"
                    className="input-field mt-1"
                    value={profileForm.last_name}
                    onChange={(event) => setProfileForm((current) => ({ ...current, last_name: event.target.value }))}
                    required
                  />
                </FormField>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <FormField id="account-email" label="Email">
                  <input
                    id="account-email"
                    className="input-field mt-1"
                    value={profile?.email || ''}
                    readOnly
                  />
                </FormField>
                <FormField id="account-role" label="Role">
                  <input
                    id="account-role"
                    className="input-field mt-1"
                    value={formatRole(profile?.role) || ''}
                    readOnly
                  />
                </FormField>
              </div>

              <div className="flex justify-end">
                <Button type="submit" icon={Save} loading={profileSaving}>
                  Save Profile
                </Button>
              </div>
            </form>
          </GlassPanel>

          <GlassPanel>
            <form onSubmit={handlePasswordSubmit} className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-brand-text">Password</h2>
              </div>

              <FormField id="account-current-password" label="Current Password" required error={passwordErrors.current_password}>
                <PasswordInput
                  id="account-current-password"
                  wrapperClassName="mt-1"
                  value={passwordForm.current_password}
                  onChange={(event) => {
                    const val = event.target.value
                    setPasswordForm((current) => ({ ...current, current_password: val }))
                    if (passwordErrors.current_password) {
                      setPasswordErrors((prev) => ({ ...prev, current_password: '' }))
                    }
                    if (error) setError('')
                  }}
                  required
                  autoComplete="current-password"
                />
              </FormField>

              <FormField id="account-new-password" label="New Password" required error={passwordErrors.new_password}>
                <PasswordInput
                  id="account-new-password"
                  wrapperClassName="mt-1"
                  value={passwordForm.new_password}
                  onChange={(event) => {
                    const val = event.target.value
                    setPasswordForm((current) => ({ ...current, new_password: val }))
                    if (passwordErrors.new_password) {
                      setPasswordErrors((prev) => ({ ...prev, new_password: '' }))
                    }
                    if (error) setError('')
                  }}
                  required
                  autoComplete="new-password"
                />
              </FormField>

              <div className="text-xs bg-slate-50 border border-slate-200 dark:bg-slate-800/40 dark:border-slate-700/50 p-3.5 rounded-md space-y-2">
                <p className="font-semibold text-slate-700 dark:text-slate-300">Password Requirements:</p>
                <ul className="space-y-1.5 text-slate-600 dark:text-slate-400">
                  <li className={`flex items-center gap-1.5 transition-colors ${passwordReqChecks.length ? 'text-emerald-600 dark:text-emerald-400 font-medium' : 'text-slate-600 dark:text-slate-400'}`}>
                    <Check className={`h-3.5 w-3.5 shrink-0 transition-colors ${passwordReqChecks.length ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-600'}`} />
                    <span>Minimum 12 characters</span>
                  </li>
                  <li className={`flex items-center gap-1.5 transition-colors ${passwordReqChecks.upper && passwordReqChecks.lower ? 'text-emerald-600 dark:text-emerald-400 font-medium' : 'text-slate-600 dark:text-slate-400'}`}>
                    <Check className={`h-3.5 w-3.5 shrink-0 transition-colors ${passwordReqChecks.upper && passwordReqChecks.lower ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-600'}`} />
                    <span>At least one uppercase and one lowercase letter</span>
                  </li>
                  <li className={`flex items-center gap-1.5 transition-colors ${passwordReqChecks.digit && passwordReqChecks.special ? 'text-emerald-600 dark:text-emerald-400 font-medium' : 'text-slate-600 dark:text-slate-400'}`}>
                    <Check className={`h-3.5 w-3.5 shrink-0 transition-colors ${passwordReqChecks.digit && passwordReqChecks.special ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-600'}`} />
                    <span>At least one digit and one special character</span>
                  </li>
                  <li className={`flex items-center gap-1.5 transition-colors ${!passwordReqChecks.notEmail ? 'text-rose-600 dark:text-rose-400 font-medium' : (passwordForm.new_password && passwordReqChecks.notEmail ? 'text-emerald-600 dark:text-emerald-400 font-medium' : 'text-slate-600 dark:text-slate-400')}`}>
                    <Check className={`h-3.5 w-3.5 shrink-0 transition-colors ${!passwordReqChecks.notEmail ? 'text-rose-600 dark:text-rose-400' : (passwordForm.new_password && passwordReqChecks.notEmail ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-600')}`} />
                    <span>Must not contain parts of your email address</span>
                  </li>
                </ul>
              </div>

              <FormField id="account-confirm-password" label="Confirm New Password" required error={passwordErrors.confirm_password}>
                <PasswordInput
                  id="account-confirm-password"
                  wrapperClassName="mt-1"
                  value={passwordForm.confirm_password}
                  onChange={(event) => {
                    const val = event.target.value
                    setPasswordForm((current) => ({ ...current, confirm_password: val }))
                    if (passwordErrors.confirm_password) {
                      setPasswordErrors((prev) => ({ ...prev, confirm_password: '' }))
                    }
                    if (error) setError('')
                  }}
                  required
                  autoComplete="new-password"
                />
              </FormField>

              <div className="flex justify-end">
                <Button type="submit" icon={KeyRound} loading={passwordSaving}>
                  Update Password
                </Button>
              </div>
            </form>
          </GlassPanel>

          <GlassPanel className="xl:col-span-2">
            <form onSubmit={handlePrefsSubmit} className="space-y-6">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-slate-200 dark:border-slate-700/40 pb-4">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-brand-primary/10 text-brand-primary">
                    <Bell className="h-5 w-5" />
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold text-brand-text">Notification Preferences</h2>
                    <p className="text-xs text-brand-text-muted">
                      Control which notifications you receive across In-App and Email delivery channels.
                    </p>
                  </div>
                </div>
                <Button type="submit" icon={Save} loading={prefsSaving}>
                  Save Preferences
                </Button>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                {/* Critical Alerts & Overrides */}
                <div className="flex flex-col justify-between p-4 rounded-lg bg-slate-50 border border-slate-200 dark:bg-slate-800/40 dark:border-slate-700/50">
                  <div className="space-y-1.5 mb-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-brand-text">Critical Alerts &amp; Overrides</span>
                      <span className="inline-flex items-center gap-1 rounded bg-amber-50 text-amber-700 border border-amber-200 px-1.5 py-0.5 text-[10px] font-semibold dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20">
                        <ShieldAlert className="h-3 w-3" /> Mandatory
                      </span>
                    </div>
                    <p className="text-xs text-brand-text-muted">
                      Security events, statutory compliance breaches, and administrative privilege overrides. Cannot be disabled under {branding.app_name} governance policy.
                    </p>
                  </div>
                  <div className="pt-2 border-t border-slate-200/60 dark:border-slate-700/40 flex items-center gap-6">
                    <label className="flex items-center gap-2 text-xs font-medium text-slate-600 dark:text-slate-400 cursor-not-allowed">
                      <input
                        type="checkbox"
                        checked={true}
                        disabled
                        aria-label="Critical Alerts In-App"
                        className="h-4 w-4 rounded border-slate-300 bg-slate-100 text-slate-400 cursor-not-allowed dark:border-slate-600 dark:bg-slate-700"
                      />
                      In-App (Mandatory)
                    </label>
                    <label className="flex items-center gap-2 text-xs font-medium text-slate-600 dark:text-slate-400 cursor-not-allowed">
                      <input
                        type="checkbox"
                        checked={true}
                        disabled
                        aria-label="Critical Alerts Email"
                        className="h-4 w-4 rounded border-slate-300 bg-slate-100 text-slate-400 cursor-not-allowed dark:border-slate-600 dark:bg-slate-700"
                      />
                      Email (Mandatory)
                    </label>
                  </div>
                </div>

                {/* Deadlines & Overdue Notices */}
                <div className="flex flex-col justify-between p-4 rounded-lg bg-slate-50 border border-slate-200 hover:border-slate-300 dark:bg-slate-800/40 dark:border-slate-700/50 dark:hover:border-slate-600/60 transition-colors">
                  <div className="space-y-1.5 mb-3">
                    <span className="text-sm font-semibold text-brand-text">Compliance &amp; SLA Deadlines</span>
                    <p className="text-xs text-brand-text-muted">
                      Approaching document submission deadlines (3 working days and 1 working day advance warnings) and overdue SLA notices.
                    </p>
                    <p className="text-[11px] text-slate-600 dark:text-slate-400 italic">
                      If disabled, you will not receive advance reminders before statutory deadlines expire.
                    </p>
                  </div>
                  <div className="pt-2 border-t border-slate-200/60 dark:border-slate-700/40 flex items-center gap-6">
                    <label className="flex items-center gap-2 text-xs font-medium text-brand-text cursor-pointer">
                      <input
                        type="checkbox"
                        id="pref-in-app-deadline-reminders"
                        checked={Boolean(prefs.in_app_deadline_reminders)}
                        onChange={(e) => setPrefs((current) => ({ ...current, in_app_deadline_reminders: e.target.checked }))}
                        className="h-4 w-4 rounded border-slate-300 bg-white text-blue-600 focus:ring-blue-500/30 dark:border-slate-600 dark:bg-slate-700 dark:text-brand-primary cursor-pointer transition-colors"
                      />
                      In-App
                    </label>
                    <label className="flex items-center gap-2 text-xs font-medium text-brand-text cursor-pointer">
                      <input
                        type="checkbox"
                        id="pref-email-deadline-reminders"
                        checked={Boolean(prefs.email_deadline_reminders)}
                        onChange={(e) => setPrefs((current) => ({ ...current, email_deadline_reminders: e.target.checked }))}
                        className="h-4 w-4 rounded border-slate-300 bg-white text-blue-600 focus:ring-blue-500/30 dark:border-slate-600 dark:bg-slate-700 dark:text-brand-primary cursor-pointer transition-colors"
                      />
                      Email
                    </label>
                  </div>
                </div>

                {/* Review Reminders */}
                <div className="flex flex-col justify-between p-4 rounded-lg bg-slate-50 border border-slate-200 hover:border-slate-300 dark:bg-slate-800/40 dark:border-slate-700/50 dark:hover:border-slate-600/60 transition-colors">
                  <div className="space-y-1.5 mb-3">
                    <span className="text-sm font-semibold text-brand-text">Review &amp; Verification Reminders</span>
                    <p className="text-xs text-brand-text-muted">
                      Alerts for unreviewed submissions, documents returned for revision, and pending provincial approvals.
                    </p>
                    <p className="text-[11px] text-slate-600 dark:text-slate-400 italic">
                      If disabled, you will not receive action reminders when documents are waiting for review or correction.
                    </p>
                  </div>
                  <div className="pt-2 border-t border-slate-200/60 dark:border-slate-700/40 flex items-center gap-6">
                    <label className="flex items-center gap-2 text-xs font-medium text-brand-text cursor-pointer">
                      <input
                        type="checkbox"
                        id="pref-in-app-review-reminders"
                        checked={Boolean(prefs.in_app_review_reminders)}
                        onChange={(e) => setPrefs((current) => ({ ...current, in_app_review_reminders: e.target.checked }))}
                        className="h-4 w-4 rounded border-slate-300 bg-white text-blue-600 focus:ring-blue-500/30 dark:border-slate-600 dark:bg-slate-700 dark:text-brand-primary cursor-pointer transition-colors"
                      />
                      In-App
                    </label>
                    <label className="flex items-center gap-2 text-xs font-medium text-brand-text cursor-pointer">
                      <input
                        type="checkbox"
                        id="pref-email-review-reminders"
                        checked={Boolean(prefs.email_review_reminders)}
                        onChange={(e) => setPrefs((current) => ({ ...current, email_review_reminders: e.target.checked }))}
                        className="h-4 w-4 rounded border-slate-300 bg-white text-blue-600 focus:ring-blue-500/30 dark:border-slate-600 dark:bg-slate-700 dark:text-brand-primary cursor-pointer transition-colors"
                      />
                      Email
                    </label>
                  </div>
                </div>

                {/* Workflow Notifications */}
                <div className="flex flex-col justify-between p-4 rounded-lg bg-slate-50 border border-slate-200 hover:border-slate-300 dark:bg-slate-800/40 dark:border-slate-700/50 dark:hover:border-slate-600/60 transition-colors">
                  <div className="space-y-1.5 mb-3">
                    <span className="text-sm font-semibold text-brand-text">Workflow &amp; Status Transitions</span>
                    <p className="text-xs text-brand-text-muted">
                      Routine operational updates when requirements are submitted, verified by staff, or given final approval.
                    </p>
                    <p className="text-[11px] text-slate-600 dark:text-slate-400 italic">
                      If disabled, you will not receive status updates on routine document workflow progressions.
                    </p>
                  </div>
                  <div className="pt-2 border-t border-slate-200/60 dark:border-slate-700/40 flex items-center gap-6">
                    <label className="flex items-center gap-2 text-xs font-medium text-brand-text cursor-pointer">
                      <input
                        type="checkbox"
                        id="pref-in-app-workflow-notifications"
                        checked={Boolean(prefs.in_app_workflow_notifications)}
                        onChange={(e) => setPrefs((current) => ({ ...current, in_app_workflow_notifications: e.target.checked }))}
                        className="h-4 w-4 rounded border-slate-300 bg-white text-blue-600 focus:ring-blue-500/30 dark:border-slate-600 dark:bg-slate-700 dark:text-brand-primary cursor-pointer transition-colors"
                      />
                      In-App
                    </label>
                    <label className="flex items-center gap-2 text-xs font-medium text-brand-text cursor-pointer">
                      <input
                        type="checkbox"
                        id="pref-email-workflow-notifications"
                        checked={Boolean(prefs.email_workflow_notifications)}
                        onChange={(e) => setPrefs((current) => ({ ...current, email_workflow_notifications: e.target.checked }))}
                        className="h-4 w-4 rounded border-slate-300 bg-white text-blue-600 focus:ring-blue-500/30 dark:border-slate-600 dark:bg-slate-700 dark:text-brand-primary cursor-pointer transition-colors"
                      />
                      Email
                    </label>
                  </div>
                </div>

                {/* Daily Digest */}
                <div className="flex flex-col justify-between p-4 rounded-lg bg-slate-50 border border-slate-200 hover:border-slate-300 dark:bg-slate-800/40 dark:border-slate-700/50 dark:hover:border-slate-600/60 md:col-span-2 transition-colors">
                  <div className="space-y-1.5 mb-3">
                    <span className="text-sm font-semibold text-brand-text">Daily Summary Digest</span>
                    <p className="text-xs text-brand-text-muted">
                      Receive a consolidated summary email each morning outlining pending actions across your scope.
                    </p>
                  </div>
                  <div className="pt-2 border-t border-slate-200/60 dark:border-slate-700/40 flex items-center gap-6">
                    <label className="flex items-center gap-2 text-xs font-medium text-brand-text cursor-pointer">
                      <input
                        type="checkbox"
                        id="pref-daily-digest"
                        checked={Boolean(prefs.email_daily_digest)}
                        onChange={(e) => setPrefs((current) => ({ ...current, email_daily_digest: e.target.checked }))}
                        className="h-4 w-4 rounded border-slate-300 bg-white text-blue-600 focus:ring-blue-500/30 dark:border-slate-600 dark:bg-slate-700 dark:text-brand-primary cursor-pointer transition-colors"
                      />
                      Email Digest
                    </label>
                  </div>
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <Button type="submit" icon={Save} loading={prefsSaving}>
                  Save Preferences
                </Button>
              </div>
            </form>
          </GlassPanel>
        </div>
      )}
    </div>
  )
}
