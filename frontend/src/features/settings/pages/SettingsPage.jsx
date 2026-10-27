import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, CheckCircle2, Cloud, Link2, OctagonAlert, Pencil, Plus, Settings, ShieldCheck, Unplug } from 'lucide-react'
import { BrandLogo, Button, DataTable, FeedbackToast, FormField, GlassPanel, InlineAlert, KpiCard, Modal, PageHeader } from '../../../components'
import { getUserRole, isAdmin } from '../../../lib/auth'
import { formatMachineLabel, formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import { useBranding } from '../../../hooks/useBranding'
import * as settingsApi from '../api/settingsApi'

const EMPTY_FORM = {
  key: '',
  value: '',
  value_type: 'string',
  description: '',
  is_encrypted: false,
}

const EMPTY_BRANDING = {
  app_name: '',
  app_tagline: '',
  logo_alt_text: '',
}

function statusBadge(status) {
  return (
    <span className={badgeClassForStatus(status, 'warning')}>
      {formatStatus(status)}
    </span>
  )
}

function normalizeBranding(branding) {
  return {
    app_name: branding?.app_name || '',
    app_tagline: branding?.app_tagline || '',
    logo_alt_text: branding?.logo_alt_text || '',
  }
}

export default function SettingsPage() {
  const { refreshBranding } = useBranding()
  const [readiness, setReadiness] = useState({ summary: { ready: 0, warning: 0, disabled: 0 }, checks: [] })
  const [configs, setConfigs] = useState([])
  const [defaultsCatalog, setDefaultsCatalog] = useState([])
  const [driveConnection, setDriveConnection] = useState(null)
  const [driveRootFolderId, setDriveRootFolderId] = useState('')
  const [brandingForm, setBrandingForm] = useState(EMPTY_BRANDING)
  const [brandingSummary, setBrandingSummary] = useState(EMPTY_BRANDING)
  const [logoFile, setLogoFile] = useState(null)
  const [faviconFile, setFaviconFile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [brandingSubmitting, setBrandingSubmitting] = useState(false)
  const [driveSubmitting, setDriveSubmitting] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [brandingModalOpen, setBrandingModalOpen] = useState(false)
  const [configModalOpen, setConfigModalOpen] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [form, setForm] = useState(EMPTY_FORM)

  const canManage = getUserRole() === 'admin'

  const loadPage = useCallback(async () => {
    if (!canManage) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    try {
      const [brandingRes, readinessRes, configRes, defaultsRes, driveConnectionRes] = await Promise.all([
        settingsApi.getBranding(),
        settingsApi.getReadiness(),
        settingsApi.listSystemConfigs(),
        settingsApi.listOperationalDefaults(),
        settingsApi.getDriveConnection(),
      ])
      const loadedBranding = normalizeBranding(brandingRes.data || {})
      setBrandingForm(loadedBranding)
      setBrandingSummary(loadedBranding)
      setReadiness(readinessRes.data || { summary: { ready: 0, warning: 0, disabled: 0 }, checks: [] })
      setConfigs(configRes.data || [])
      setDefaultsCatalog(defaultsRes.data || [])
      setDriveConnection(driveConnectionRes.data || null)
      setDriveRootFolderId(driveConnectionRes.data?.root_folder_id || '')
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to load settings and system checks.')
    } finally {
      setLoading(false)
    }
  }, [canManage])

  useEffect(() => {
    loadPage()
  }, [loadPage])

  useEffect(() => {
    if (!canManage) return
    const params = new URLSearchParams(window.location.search)
    const driveOauth = params.get('drive_oauth')
    if (driveOauth === 'connected') {
      setMessage('Google Drive account connected successfully.')
      window.history.replaceState({}, '', window.location.pathname)
    } else if (driveOauth === 'error') {
      setError(params.get('reason') || 'Google Drive account connection failed.')
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [canManage])

  const handleDriveRootSubmit = async (event) => {
    event.preventDefault()
    if (!canManage) return
    setDriveSubmitting('root')
    setError('')
    setMessage('')
    try {
      const response = await settingsApi.updateDriveConnection({
        root_folder_id: driveRootFolderId.trim(),
      })
      setDriveConnection(response.data || null)
      setDriveRootFolderId(response.data?.root_folder_id || '')
      await loadPage()
      setMessage('Google Drive root folder saved.')
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to save Google Drive root folder.')
    } finally {
      setDriveSubmitting('')
    }
  }

  const handleConnectDrive = async () => {
    if (!canManage) return
    setDriveSubmitting('connect')
    setError('')
    setMessage('')
    try {
      const response = await settingsApi.startDriveOAuth()
      window.location.href = response.data.authorization_url
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to start Google Drive connection.')
      setDriveSubmitting('')
    }
  }

  const handleDisconnectDrive = async () => {
    if (!canManage) return
    setDriveSubmitting('disconnect')
    setError('')
    setMessage('')
    try {
      const response = await settingsApi.disconnectDriveOAuth()
      setDriveConnection(response.data || null)
      await loadPage()
      setMessage('Google Drive account disconnected.')
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to disconnect Google Drive.')
    } finally {
      setDriveSubmitting('')
    }
  }

  if (!isAdmin()) {
    return (
      <GlassPanel>
        <h1 className="page-title mb-2">Settings & System Checks</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Administrator settings are only available to admin and chief accounts.
        </p>
      </GlassPanel>
    )
  }

  const openBrandingModal = () => {
    setBrandingForm(brandingSummary)
    setLogoFile(null)
    setFaviconFile(null)
    setError('')
    setMessage('')
    setBrandingModalOpen(true)
  }

  const closeBrandingModal = () => {
    setBrandingForm(brandingSummary)
    setLogoFile(null)
    setFaviconFile(null)
    setBrandingModalOpen(false)
  }

  const openNewConfigModal = () => {
    setEditingId(null)
    setForm({ ...EMPTY_FORM })
    setError('')
    setMessage('')
    setConfigModalOpen(true)
  }

  const closeConfigModal = () => {
    setEditingId(null)
    setForm({ ...EMPTY_FORM })
    setConfigModalOpen(false)
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!canManage) return

    setSubmitting(true)
    setError('')
    setMessage('')
    try {
      const response = editingId
        ? await settingsApi.updateSystemConfig(editingId, form)
        : await settingsApi.createSystemConfig(form)
      setMessage(response.message || 'Operational default saved successfully.')
      setEditingId(null)
      setForm({ ...EMPTY_FORM })
      await loadPage()
      setConfigModalOpen(false)
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to save the operational default.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleBrandingSubmit = async (event) => {
    event.preventDefault()
    if (!canManage) return

    setBrandingSubmitting(true)
    setError('')
    setMessage('')
    try {
      await settingsApi.updateBranding(brandingForm)
      if (logoFile) {
        await settingsApi.uploadBrandAsset('logo', logoFile)
      }
      if (faviconFile) {
        await settingsApi.uploadBrandAsset('favicon', faviconFile)
      }
      setLogoFile(null)
      setFaviconFile(null)
      await refreshBranding()
      await loadPage()
      setBrandingModalOpen(false)
      setMessage('Application branding saved successfully.')
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to save application branding.')
    } finally {
      setBrandingSubmitting(false)
    }
  }

  const handleEdit = (config) => {
    setEditingId(config.id)
    setError('')
    setMessage('')
    setForm({
      key: config.key || '',
      value: config.value || '',
      value_type: config.value_type || 'string',
      description: config.description || '',
      is_encrypted: config.is_encrypted,
    })
    setConfigModalOpen(true)
  }

  const handleUseDefault = (defaultItem) => {
    if (!canManage) return
    setEditingId(defaultItem.config_id || null)
    setError('')
    setMessage('')
    setForm({
      key: defaultItem.key,
      value: defaultItem.current_value ?? defaultItem.default_value ?? '',
      value_type: defaultItem.value_type || 'string',
      description: defaultItem.description || '',
      is_encrypted: false,
    })
    setConfigModalOpen(true)
  }

  const configColumns = [
    { key: 'key', label: 'Key' },
    { key: 'value_type', label: 'Type', render: (row) => formatMachineLabel(row.value_type) },
    { key: 'value', label: 'Value', render: (row) => row.has_value ? (row.value ?? 'Stored securely') : 'None' },
    { key: 'description', label: 'Description' },
    ...(canManage ? [{
      key: 'actions',
      label: '',
      render: (row) => (
        <Button size="sm" variant="outline" icon={Pencil} onClick={() => handleEdit(row)}>
          Edit
        </Button>
      ),
    }] : []),
  ]

  return (
    <div>
      <PageHeader
        title="Settings & System Checks"
        description="Review operational defaults, upload access, handoff settings, and scheduled jobs before staff encounter system issues."
      />

      <FeedbackToast type="success" message={message} onDismiss={() => setMessage('')} />
      <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>
        {error}
      </InlineAlert>

      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-4">
        <KpiCard title="Ready" value={readiness.summary.ready} subtitle="operational" icon={CheckCircle2} color="emerald" />
        <KpiCard title="Warnings" value={readiness.summary.warning} subtitle="needs attention" icon={OctagonAlert} color="amber" />
        <KpiCard title="Disabled" value={readiness.summary.disabled} subtitle="off" icon={ShieldCheck} color="blue" />
        <KpiCard title="Defaults" value={configs.length} subtitle="configured" icon={Settings} color="cyan" />
      </div>

      <GlassPanel className="mb-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="section-title">Application branding</h2>
            <p className="mt-1 text-sm text-brand-text-muted">
              App identity used across public and internal screens.
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-3">
            <BrandLogo size="xl" nameClassName="max-w-[240px] text-lg" />
            {canManage && (
              <Button variant="outline" icon={Pencil} onClick={openBrandingModal}>
                Edit branding
              </Button>
            )}
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div className="rounded-lg border border-brand-border bg-brand-surface p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-text-muted">App name</p>
            <p className="mt-1 text-sm font-medium text-brand-text">{brandingSummary.app_name || 'Not set'}</p>
          </div>
          <div className="rounded-lg border border-brand-border bg-brand-surface p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-text-muted">Tagline</p>
            <p className="mt-1 text-sm font-medium text-brand-text">{brandingSummary.app_tagline || 'Not set'}</p>
          </div>
          <div className="rounded-lg border border-brand-border bg-brand-surface p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-text-muted">Logo alt text</p>
            <p className="mt-1 text-sm font-medium text-brand-text">{brandingSummary.logo_alt_text || 'Not set'}</p>
          </div>
        </div>
        {!canManage && (
          <p className="mt-3 text-sm text-brand-text-muted">
            Only administrators can change the app name or logo.
          </p>
        )}
      </GlassPanel>

      <GlassPanel className="mb-6">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="section-title">Google Drive handoff</h2>
            <p className="mt-1 text-sm text-brand-text-muted">
              Connect a Google account and choose the root folder used for Regional Handoff uploads.
            </p>
          </div>
          <span className={badgeClassForStatus(driveConnection?.oauth_connected && driveConnection?.has_root_folder ? 'ready' : 'warning')}>
            {driveConnection?.oauth_connected && driveConnection?.has_root_folder ? 'Ready' : 'Setup Required'}
          </span>
        </div>

        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <div className="rounded-lg border border-brand-border bg-brand-surface p-4">
            <div className="mb-2 flex items-center gap-2">
              <Cloud className="h-4 w-4 text-brand-text-muted" />
              <p className="text-sm font-semibold text-brand-text">Connected account</p>
            </div>
            <p className="break-all text-sm text-brand-text-muted">
              {driveConnection?.connected_email || 'No Google account connected'}
            </p>
            <p className="mt-2 text-xs text-brand-text-muted">
              Mode: {formatMachineLabel(driveConnection?.auth_mode || 'unconfigured')}
            </p>
          </div>

          <form onSubmit={handleDriveRootSubmit} className="rounded-lg border border-brand-border bg-brand-surface p-4 lg:col-span-2">
            <FormField
              id="google-drive-root-folder"
              label="Regional handoff root folder ID"
              hint="Use a folder owned by or shared with the connected Google account with Editor access."
            >
              <input
                id="google-drive-root-folder"
                className="input-field"
                value={driveRootFolderId}
                onChange={(event) => setDriveRootFolderId(event.target.value)}
                placeholder="Example: 1gj8tAxmfyZ2VzLb5EyobPkA6couzXwuo"
                disabled={!canManage}
              />
            </FormField>
            {canManage && (
              <div className="mt-3 flex flex-wrap gap-2">
                <Button type="submit" variant="outline" icon={Link2} loading={driveSubmitting === 'root'}>
                  Save root folder
                </Button>
                <Button
                  type="button"
                  icon={Cloud}
                  loading={driveSubmitting === 'connect'}
                  disabled={!driveConnection?.oauth_configured}
                  onClick={handleConnectDrive}
                  title={driveConnection?.oauth_configured ? 'Connect Google Drive' : 'Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET first'}
                >
                  {driveConnection?.oauth_connected ? 'Reconnect Google Drive' : 'Connect Google Drive'}
                </Button>
                {driveConnection?.oauth_connected && (
                  <Button
                    type="button"
                    variant="outline"
                    icon={Unplug}
                    loading={driveSubmitting === 'disconnect'}
                    onClick={handleDisconnectDrive}
                  >
                    Disconnect
                  </Button>
                )}
              </div>
            )}
          </form>
        </div>

        {!driveConnection?.oauth_configured && (
          <InlineAlert type="warning" className="mt-4">
            Google OAuth client credentials are not configured. Set GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, and GOOGLE_DRIVE_OAUTH_REDIRECT_URI before connecting a normal Gmail Drive account.
          </InlineAlert>
        )}
      </GlassPanel>

      <GlassPanel className="mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="section-title">Document templates</h2>
            <p className="mt-1 text-sm text-brand-text-muted">
              Templates have moved to the Reference Library. Manage DOCX layouts for reports, notices, and letters alongside guidelines and annexes in one place.
            </p>
          </div>
          <Link
            to="/dashboard/library?reference_type=template"
            className="inline-flex items-center gap-1.5 rounded-md border border-brand-primary/30 bg-brand-primary/10 px-3 py-2 text-sm font-medium text-brand-primary transition hover:border-brand-primary/50 hover:bg-brand-primary/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/35"
          >
            Manage templates in the Reference Library
            <ArrowUpRight className="h-4 w-4" strokeWidth={1.75} />
          </Link>
        </div>
      </GlassPanel>

      <GlassPanel className="mb-6">
        <h2 className="section-title mb-3">System checks</h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {readiness.checks.map((check) => (
            <div key={check.key} className="rounded-lg border border-brand-border bg-brand-surface p-4">
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="text-sm font-semibold uppercase tracking-wide text-brand-text">
                  {formatMachineLabel(check.key)}
                </p>
                {statusBadge(check.status)}
              </div>
              <p className="text-sm text-brand-text-muted">{check.message}</p>
            </div>
          ))}
        </div>
      </GlassPanel>

      <GlassPanel className="mb-6">
        <h2 className="section-title mb-3">Recommended operational defaults</h2>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {defaultsCatalog.map((defaultItem) => (
            <div key={defaultItem.key} className="rounded-lg border border-brand-border bg-brand-surface p-4">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-brand-text">{defaultItem.label}</p>
                  <p className="text-xs text-brand-text-muted">{defaultItem.key}</p>
                </div>
                <span className={badgeClassForStatus(defaultItem.configured ? 'ready' : 'warning')}>
                  {defaultItem.configured ? 'Configured' : 'Suggested'}
                </span>
              </div>
              <p className="mb-3 text-sm text-brand-text-muted">{defaultItem.description}</p>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="text-sm text-brand-text-muted">
                  Value: {defaultItem.current_value ?? defaultItem.default_value ?? 'None'}
                </span>
                {canManage && (
                  <Button size="sm" variant="outline" icon={Pencil} onClick={() => handleUseDefault(defaultItem)}>
                    {defaultItem.configured ? 'Edit' : 'Use default'}
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </GlassPanel>

      <GlassPanel>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="section-title">Operational defaults</h2>
            {!canManage && (
              <p className="mt-1 text-sm text-brand-text-muted">
                Only administrators can edit operational defaults.
              </p>
            )}
          </div>
          {canManage && (
            <Button variant="outline" icon={Plus} onClick={openNewConfigModal}>
              Add default
            </Button>
          )}
        </div>
        <DataTable
          columns={configColumns}
          data={configs}
          keyField="id"
          isLoading={loading}
          emptyMessage="No operational defaults have been saved yet."
        />
      </GlassPanel>

      <Modal
        open={brandingModalOpen}
        title="Edit application branding"
        description="Update the identity shown across application screens."
        onClose={closeBrandingModal}
        size="lg"
        footer={(
          <div className="flex flex-wrap justify-end gap-3">
            <Button variant="outline" onClick={closeBrandingModal}>
              Cancel
            </Button>
            <Button type="submit" form="branding-settings-form" loading={brandingSubmitting}>
              Save branding
            </Button>
          </div>
        )}
      >
        <form id="branding-settings-form" onSubmit={handleBrandingSubmit} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <FormField id="branding-app-name" label="App name" required>
              <input
                id="branding-app-name"
                className="input-field"
                value={brandingForm.app_name}
                maxLength={80}
                onChange={(event) => setBrandingForm((current) => ({ ...current, app_name: event.target.value }))}
                required
              />
            </FormField>
            <FormField id="branding-logo-alt" label="Logo alt text">
              <input
                id="branding-logo-alt"
                className="input-field"
                value={brandingForm.logo_alt_text}
                maxLength={160}
                onChange={(event) => setBrandingForm((current) => ({ ...current, logo_alt_text: event.target.value }))}
              />
            </FormField>
            <FormField id="branding-tagline" label="App tagline" className="md:col-span-2">
              <input
                id="branding-tagline"
                className="input-field"
                value={brandingForm.app_tagline}
                maxLength={180}
                onChange={(event) => setBrandingForm((current) => ({ ...current, app_tagline: event.target.value }))}
              />
            </FormField>
            <FormField id="branding-logo-file" label="Logo image">
              <input
                id="branding-logo-file"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="input-field"
                onChange={(event) => setLogoFile(event.target.files?.[0] || null)}
              />
            </FormField>
            <FormField id="branding-favicon-file" label="Browser icon">
              <input
                id="branding-favicon-file"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="input-field"
                onChange={(event) => setFaviconFile(event.target.files?.[0] || null)}
              />
            </FormField>
          </div>
        </form>
      </Modal>

      <Modal
        open={configModalOpen}
        title={editingId ? 'Update operational default' : 'Add operational default'}
        description="Manage the keys used by intake, handoff, uploads, and automation."
        onClose={closeConfigModal}
        size="lg"
        footer={(
          <div className="flex flex-wrap justify-end gap-3">
            <Button variant="outline" onClick={closeConfigModal}>
              Cancel
            </Button>
            <Button type="submit" form="settings-config-form" loading={submitting}>
              {editingId ? 'Update default' : 'Save default'}
            </Button>
          </div>
        )}
      >
        <form id="settings-config-form" onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <FormField id="config-key" label="Config key" required>
              <input
                id="config-key"
                className="input-field"
                value={form.key}
                onChange={(event) => setForm((current) => ({ ...current, key: event.target.value }))}
                required
              />
            </FormField>
            <FormField id="config-value-type" label="Value type">
              <select
                id="config-value-type"
                className="input-field"
                value={form.value_type}
                onChange={(event) => setForm((current) => ({ ...current, value_type: event.target.value }))}
              >
                <option value="string">String</option>
                <option value="integer">Integer</option>
                <option value="boolean">Boolean</option>
                <option value="json">JSON</option>
                <option value="secret">Secret</option>
              </select>
            </FormField>
            <FormField id="config-value" label="Value" className="md:col-span-2">
              <input
                id="config-value"
                className="input-field"
                value={form.value}
                onChange={(event) => setForm((current) => ({ ...current, value: event.target.value }))}
              />
            </FormField>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
            <input
              type="checkbox"
              checked={form.is_encrypted}
              onChange={(event) => setForm((current) => ({ ...current, is_encrypted: event.target.checked }))}
            />
            Treat as encrypted / secret storage
          </label>
          <FormField id="config-description" label="Description">
            <textarea
              id="config-description"
              className="input-field min-h-[96px]"
              value={form.description}
              onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
            />
          </FormField>
        </form>
      </Modal>
    </div>
  )
}
