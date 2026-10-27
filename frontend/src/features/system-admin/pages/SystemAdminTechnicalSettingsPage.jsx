import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Cloud,
  Database,
  Download,
  Edit3,
  ExternalLink,
  FolderTree,
  HardDrive,
  Info,
  KeyRound,
  Lock,
  Mail,
  RefreshCw,
  RotateCcw,
  ServerCog,
  Shield,
  ShieldCheck,
  SlidersHorizontal,
  Unlink,
  XCircle,
} from 'lucide-react'
import {
  Button,
  ConfirmationModal,
  DataTable,
  FormField,
  GlassPanel,
  InlineAlert,
  KpiCard,
  Modal,
  PageHeader,
} from '../../../components'
import { formatBoolean, formatDateTime, formatMachineLabel, formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import * as systemAdminApi from '../api/systemAdminApi'

function formatCount(value) {
  if (value === null || value === undefined) return '-'
  return new Intl.NumberFormat().format(value)
}

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
}

function valueOrDash(value) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '-'
  if (typeof value === 'boolean') return formatBoolean(value)
  return String(value)
}

function statusBadge(status) {
  return <span className={badgeClassForStatus(status)}>{formatStatus(status)}</span>
}

function booleanStatus(value) {
  return value ? 'ready' : 'disabled'
}

function sourceBadge(source, hasOverride, overrideStatus, overrideError) {
  if (overrideStatus === 'invalid_or_unreadable') {
    return (
      <span
        className="inline-flex items-center rounded-full bg-rose-100 dark:bg-rose-900/40 px-2 py-0.5 text-xs font-medium text-rose-700 dark:text-rose-300"
        title={overrideError || 'Database override could not be decrypted; fallback active'}
      >
        Corrupted Override (Fallback Active)
      </span>
    )
  }
  if (hasOverride || source === 'database') {
    return (
      <span className="inline-flex items-center rounded-full bg-purple-100 dark:bg-purple-900/40 px-2 py-0.5 text-xs font-medium text-purple-700 dark:text-purple-300">
        Database Override
      </span>
    )
  }
  if (source === 'environment') {
    return (
      <span className="inline-flex items-center rounded-full bg-blue-100 dark:bg-blue-900/40 px-2 py-0.5 text-xs font-medium text-blue-700 dark:text-blue-300">
        Environment Fallback
      </span>
    )
  }
  return (
    <span className="inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs font-medium text-slate-600 dark:text-slate-400">
      Default
    </span>
  )
}

function providerRows(settings) {
  const providers = settings?.providers || {}
  const ai = providers.ai || {}
  const documentIntelligence = providers.document_intelligence || {}
  const objectStorage = providers.object_storage || {}
  const aiProviderRows = (ai.providers || []).map((provider) => ({
    key: `ai-${provider.name}`,
    area: 'AI provider',
    setting: formatMachineLabel(provider.name),
    value: provider.model || '-',
    status: booleanStatus(provider.configured),
  }))

  return [
    ...aiProviderRows,
    { key: 'ai-provider-order', area: 'AI runtime', setting: 'Failover order', value: ai.provider_order || [], status: 'ready' },
    { key: 'ai-timeout', area: 'AI runtime', setting: 'Request timeout', value: `${valueOrDash(ai.request_timeout_seconds)} seconds`, status: 'ready' },
    { key: 'ai-temperature', area: 'AI runtime', setting: 'Temperature', value: ai.temperature, status: 'ready' },
    { key: 'ai-output-tokens', area: 'AI runtime', setting: 'Max output tokens', value: ai.max_output_tokens, status: 'ready' },
    { key: 'ai-prompt-chars', area: 'AI runtime', setting: 'Max prompt chars', value: ai.max_prompt_chars, status: 'ready' },
    { key: 'ocr-max-pages', area: 'Document intelligence', setting: 'OCR max pages', value: documentIntelligence.ocr_max_pages, status: 'ready' },
    { key: 'provider-refinement', area: 'Document intelligence', setting: 'Provider refinement', value: documentIntelligence.provider_refinement_enabled, status: booleanStatus(documentIntelligence.provider_refinement_enabled) },
    { key: 'aws-region', area: 'Document intelligence', setting: 'AWS region', value: documentIntelligence.aws_region, status: booleanStatus(documentIntelligence.aws_enabled) },
    { key: 'textract', area: 'Document intelligence', setting: 'AWS Textract', value: documentIntelligence.textract_feature_types || [], status: booleanStatus(documentIntelligence.textract_enabled) },
    { key: 'rekognition', area: 'Document intelligence', setting: 'AWS Rekognition', value: `${valueOrDash(documentIntelligence.rekognition_max_labels)} labels at ${valueOrDash(documentIntelligence.rekognition_min_confidence)} confidence`, status: booleanStatus(documentIntelligence.rekognition_enabled) },
    { key: 'location', area: 'Document intelligence', setting: 'AWS Location', value: documentIntelligence.location_language, status: booleanStatus(documentIntelligence.location_enabled) },
    { key: 'language-tool', area: 'Language quality', setting: 'LanguageTool', value: documentIntelligence.language_tool_language, status: booleanStatus(documentIntelligence.language_tool_enabled) },
    { key: 'language-tool-timeout', area: 'Language quality', setting: 'LanguageTool timeout', value: `${valueOrDash(documentIntelligence.language_tool_timeout_seconds)} seconds`, status: booleanStatus(documentIntelligence.language_tool_enabled) },
    { key: 'language-tool-max-chars', area: 'Language quality', setting: 'LanguageTool max chars', value: documentIntelligence.language_tool_max_chars, status: booleanStatus(documentIntelligence.language_tool_enabled) },
    { key: 'language-tool-confidence', area: 'Language quality', setting: 'LanguageTool confidence', value: documentIntelligence.language_tool_min_confidence, status: booleanStatus(documentIntelligence.language_tool_enabled) },
    { key: 'object-storage-provider', area: 'Object storage', setting: 'Provider', value: objectStorage.provider, status: 'ready' },
    { key: 'object-storage-env', area: 'Object storage', setting: 'Environment', value: objectStorage.environment, status: 'ready' },
    { key: 'object-storage-ttl', area: 'Object storage', setting: 'Signed URL TTL', value: `${valueOrDash(objectStorage.signed_url_ttl_seconds)} seconds`, status: 'ready' },
    { key: 'object-storage-r2', area: 'Object storage', setting: 'R2 configuration', value: objectStorage.r2_configured, status: booleanStatus(objectStorage.r2_configured) },
  ]
}

function runtimeRows(settings) {
  const runtime = settings?.runtime || {}
  return [
    { key: 'environment', label: 'Environment', value: runtime.environment },
    { key: 'app_name', label: 'Application', value: runtime.app_name },
    { key: 'frontend_url', label: 'Frontend URL', value: runtime.frontend_url },
    { key: 'public_magic_links_enabled', label: 'Public magic links', value: runtime.public_magic_links_enabled },
    { key: 'celery_configured', label: 'Celery configured', value: runtime.celery_configured },
    { key: 'google_drive_enabled', label: 'Google Drive enabled', value: runtime.google_drive_enabled },
  ]
}

function storageRows(settings) {
  const s = settings?.storage_settings || {}
  const keys = [
    { key: 'OBJECT_STORAGE_PROVIDER', label: 'Storage Provider', isSecret: false },
    { key: 'R2_BUCKET_NAME', label: 'R2 Bucket Name', isSecret: false },
    { key: 'R2_ENDPOINT_URL', label: 'R2 Endpoint URL', isSecret: false },
    { key: 'R2_ACCESS_KEY_ID', label: 'R2 Access Key ID', isSecret: true },
    { key: 'R2_SECRET_ACCESS_KEY', label: 'R2 Secret Access Key', isSecret: true },
    { key: 'R2_REGION', label: 'R2 Region', isSecret: false },
    { key: 'OBJECT_STORAGE_BUCKET_PREFIX', label: 'Bucket Object Prefix', isSecret: false },
  ]
  return keys.map((item) => {
    const entry = s[item.key] || {}
    return {
      key: item.key,
      label: item.label,
      value: entry.value,
      isSecret: item.isSecret,
      maskedPreview: entry.masked_preview,
      source: entry.source || 'default',
      hasOverride: Boolean(entry.has_override),
      overrideStatus: entry.override_status || 'none',
      overrideError: entry.override_error,
      updatedAt: entry.updated_at,
    }
  })
}

function emailRows(settings) {
  const e = settings?.email_settings || {}
  const keys = [
    { key: 'SMTP_HOST', label: 'SMTP Host / Relay', isSecret: false },
    { key: 'SMTP_PORT', label: 'SMTP Port', isSecret: false },
    { key: 'SMTP_USE_TLS', label: 'STARTTLS Encryption', isSecret: false },
    { key: 'MAIL_FROM', label: 'Outbound From Address', isSecret: false },
    { key: 'SMTP_USERNAME', label: 'SMTP Username', isSecret: true },
    { key: 'SMTP_PASSWORD', label: 'SMTP Password', isSecret: true },
  ]
  return keys.map((item) => {
    const entry = e[item.key] || {}
    return {
      key: item.key,
      label: item.label,
      value: item.key === 'SMTP_USE_TLS' ? formatBoolean(entry.value) : entry.value,
      isSecret: item.isSecret,
      maskedPreview: entry.masked_preview,
      source: entry.source || 'default',
      hasOverride: Boolean(entry.has_override),
      overrideStatus: entry.override_status || 'none',
      overrideError: entry.override_error,
      updatedAt: entry.updated_at,
    }
  })
}

function driveRows(settings) {
  const d = settings?.drive_settings || {}
  return [
    {
      key: 'google_drive_root_folder_id',
      label: 'Workspace Root Folder ID',
      value: d.root_folder_id || '(not set)',
      isSecret: false,
      maskedPreview: null,
      source: d.has_root_folder ? 'database' : 'default',
      hasOverride: Boolean(d.has_root_folder),
      overrideStatus: 'none',
      overrideError: null,
    },
    {
      key: 'GOOGLE_DRIVE_SHARED_DRIVE_ID',
      label: 'Shared Drive ID',
      value: d.shared_drive_id || '(not set)',
      isSecret: false,
      maskedPreview: null,
      source: d.shared_drive_id ? 'environment' : 'default',
      hasOverride: false,
      overrideStatus: 'none',
      overrideError: null,
    },
  ]
}

const INTEGRATION_TABS = [
  { id: 'ai', label: 'AI Providers & Runtime', icon: KeyRound },
  { id: 'storage', label: 'Cloudflare R2 Storage', icon: Cloud },
  { id: 'email', label: 'Transactional Email (SMTP)', icon: Mail },
  { id: 'drive', label: 'Google Drive & Handoffs', icon: FolderTree },
]

export default function SystemAdminTechnicalSettingsPage() {
  const [activeTab, setActiveTab] = useState('ai')
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionSuccess, setActionSuccess] = useState('')
  const [backupSuccess, setBackupSuccess] = useState('')

  // Backups state
  const [backupsData, setBackupsData] = useState({ backups: [], summary: {}, meta: {} })
  const [backupsLoading, setBackupsLoading] = useState(false)
  const [triggeringBackup, setTriggeringBackup] = useState(false)

  // AI Provider Modal State
  const [editingProvider, setEditingProvider] = useState(null)
  const [providerForm, setProviderForm] = useState({ model: '', apiKey: '', confirmPassword: '' })
  const [savingProvider, setSavingProvider] = useState(false)
  const [providerModalError, setProviderModalError] = useState('')

  // Validation State per AI Provider
  const [validatingProvider, setValidatingProvider] = useState({})
  const [validationResults, setValidationResults] = useState({})

  // Reset Override Modal State (Used for AI, Storage, Email, Drive keys)
  const [resetOverrideKey, setResetOverrideKey] = useState(null)
  const [resettingOverride, setResettingOverride] = useState(false)
  const [resetConfirmPassword, setResetConfirmPassword] = useState('')

  // AI Runtime Parameters Edit State
  const [runtimeForm, setRuntimeForm] = useState({
    providerOrder: '',
    timeout: 30,
    temperature: 0.2,
    maxTokens: 1200,
    maxPromptChars: 4000,
    confirmPassword: '',
  })
  const [savingRuntime, setSavingRuntime] = useState(false)
  const [runtimeError, setRuntimeError] = useState('')

  // Storage State
  const [storageModalOpen, setStorageModalOpen] = useState(false)
  const [storageForm, setStorageForm] = useState({
    provider: 'r2',
    bucketName: '',
    endpointUrl: '',
    accessKeyId: '',
    secretAccessKey: '',
    region: 'auto',
    bucketPrefix: 'comet',
    confirmPassword: '',
  })
  const [savingStorage, setSavingStorage] = useState(false)
  const [storageModalError, setStorageModalError] = useState('')
  const [validatingStorage, setValidatingStorage] = useState(false)
  const [storageValidationResult, setStorageValidationResult] = useState(null)

  // Email State
  const [emailModalOpen, setEmailModalOpen] = useState(false)
  const [emailForm, setEmailForm] = useState({
    host: '',
    port: 587,
    useTls: true,
    fromAddress: '',
    username: '',
    password: '',
    confirmPassword: '',
  })
  const [savingEmail, setSavingEmail] = useState(false)
  const [emailModalError, setEmailModalError] = useState('')
  const [validatingEmail, setValidatingEmail] = useState(false)
  const [emailValidationResult, setEmailValidationResult] = useState(null)

  // Drive State
  const [driveModalOpen, setDriveModalOpen] = useState(false)
  const [driveForm, setDriveForm] = useState({
    rootFolderId: '',
    sharedDriveId: '',
    confirmPassword: '',
  })
  const [savingDrive, setSavingDrive] = useState(false)
  const [driveModalError, setDriveModalError] = useState('')
  const [connectingDrive, setConnectingDrive] = useState(false)
  const [driveDisconnectModalOpen, setDriveDisconnectModalOpen] = useState(false)
  const [disconnectingDrive, setDisconnectingDrive] = useState(false)

  const loadSettings = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await systemAdminApi.getSystemAdminTechnicalSettings()
      const data = response.data || null
      setSettings(data)

      if (data?.ai_settings) {
        const aiConf = data.ai_settings
        setRuntimeForm({
          providerOrder: (aiConf.AI_PROVIDER_ORDER?.value || ['gemini', 'groq', 'openrouter']).join(', '),
          timeout: aiConf.AI_REQUEST_TIMEOUT_SECONDS?.value ?? 30,
          temperature: aiConf.AI_TEMPERATURE?.value ?? 0.2,
          maxTokens: aiConf.AI_MAX_OUTPUT_TOKENS?.value ?? 1200,
          maxPromptChars: aiConf.AI_MAX_PROMPT_CHARS?.value ?? 4000,
          confirmPassword: '',
        })
      }
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to load technical settings.')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadBackups = useCallback(async () => {
    setBackupsLoading(true)
    try {
      const res = await systemAdminApi.listBackups({ page: 1, per_page: 20 })
      setBackupsData(res.data || { backups: [], summary: {}, meta: {} })
    } catch {
      // Fail quietly
    } finally {
      setBackupsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadSettings()
    loadBackups()
  }, [loadSettings, loadBackups])

  const handleTriggerBackup = async () => {
    setTriggeringBackup(true)
    setError('')
    setBackupSuccess('')
    try {
      const res = await systemAdminApi.triggerBackup()
      setBackupSuccess(`Database backup "${res.data?.filename}" created successfully.`)
      await loadBackups()
    } catch (err) {
      setError(err.response?.data?.message || 'Failed to trigger database backup.')
    } finally {
      setTriggeringBackup(false)
    }
  }

  const handleDownloadBackup = async (backup) => {
    try {
      const response = await systemAdminApi.downloadBackup(backup.id)
      const blob = new Blob([response.data], { type: 'application/octet-stream' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', backup.filename || `backup_${backup.id}.dump`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to download backup archive.')
    }
  }

  // ── AI Handlers ─────────────────────────────────────────────────────────────
  const handleValidateProvider = async (providerName, customApiKey = null, customPassword = '') => {
    setValidatingProvider((prev) => ({ ...prev, [providerName]: true }))
    setValidationResults((prev) => ({ ...prev, [providerName]: null }))
    try {
      const payload = { provider: providerName }
      if (customApiKey) payload.api_key = customApiKey
      if (customPassword) payload.confirm_password = customPassword
      const res = await systemAdminApi.validateAiCredential(payload)
      const resultData = res?.data || res
      setValidationResults((prev) => ({ ...prev, [providerName]: resultData }))
      return resultData
    } catch (err) {
      const msg = err.response?.data?.message || 'Connection validation failed.'
      const resultData = { valid: false, message: msg }
      setValidationResults((prev) => ({ ...prev, [providerName]: resultData }))
      return resultData
    } finally {
      setValidatingProvider((prev) => ({ ...prev, [providerName]: false }))
    }
  }

  const openProviderModal = (providerKey) => {
    const aiConf = settings?.ai_settings || {}
    const modelKey = `${providerKey.toUpperCase()}_MODEL`
    const currentModel = aiConf[modelKey]?.value || ''
    setEditingProvider(providerKey)
    setProviderForm({
      model: currentModel,
      apiKey: '',
      confirmPassword: '',
    })
    setProviderModalError('')
  }

  const handleSaveProvider = async (e) => {
    e.preventDefault()
    setSavingProvider(true)
    setProviderModalError('')
    setActionSuccess('')
    try {
      const providerKey = editingProvider
      const modelKey = `${providerKey.toUpperCase()}_MODEL`
      const secretKey = `${providerKey.toUpperCase()}_API_KEY`

      const updates = { [modelKey]: providerForm.model.trim() }
      if (providerForm.apiKey && providerForm.apiKey.trim()) {
        updates[secretKey] = providerForm.apiKey.trim()
      }
      if (providerForm.confirmPassword) {
        updates.confirm_password = providerForm.confirmPassword
      }

      await systemAdminApi.updateSystemAdminTechnicalSettings(updates)
      setActionSuccess(`${formatMachineLabel(providerKey)} configuration updated successfully.`)
      setEditingProvider(null)
      await loadSettings()
    } catch (err) {
      setProviderModalError(err.response?.data?.message || 'Failed to update provider configuration.')
    } finally {
      setSavingProvider(false)
    }
  }

  const handleSaveRuntimeParameters = async (e) => {
    if (e && e.preventDefault) e.preventDefault()
    setSavingRuntime(true)
    setRuntimeError('')
    setActionSuccess('')
    try {
      const order = runtimeForm.providerOrder
        ? runtimeForm.providerOrder.split(',').map((s) => s.trim().toLowerCase()).filter(Boolean)
        : ['gemini', 'groq', 'openrouter']
      const updates = {
        AI_PROVIDER_ORDER: order,
        AI_REQUEST_TIMEOUT_SECONDS: Number(runtimeForm.timeout),
        AI_TEMPERATURE: Number(runtimeForm.temperature),
        AI_MAX_OUTPUT_TOKENS: Number(runtimeForm.maxTokens),
        AI_MAX_PROMPT_CHARS: Number(runtimeForm.maxPromptChars),
      }
      if (runtimeForm.confirmPassword) {
        updates.confirm_password = runtimeForm.confirmPassword
      }

      await systemAdminApi.updateSystemAdminTechnicalSettings(updates)
      setActionSuccess('AI runtime parameters updated successfully.')
      setRuntimeForm((prev) => ({ ...prev, confirmPassword: '' }))
      await loadSettings()
    } catch (err) {
      setRuntimeError(err.response?.data?.message || 'Failed to update runtime parameters.')
    } finally {
      setSavingRuntime(false)
    }
  }

  // ── Storage Handlers ────────────────────────────────────────────────────────
  const openStorageModal = () => {
    const s = settings?.storage_settings || {}
    setStorageForm({
      provider: s.OBJECT_STORAGE_PROVIDER?.value || 'r2',
      bucketName: s.R2_BUCKET_NAME?.value || '',
      endpointUrl: s.R2_ENDPOINT_URL?.value || '',
      accessKeyId: '',
      secretAccessKey: '',
      region: s.R2_REGION?.value || 'auto',
      bucketPrefix: s.OBJECT_STORAGE_BUCKET_PREFIX?.value || 'comet',
      confirmPassword: '',
    })
    setStorageModalError('')
    setStorageModalOpen(true)
  }

  const handleSaveStorage = async (e) => {
    if (e && e.preventDefault) e.preventDefault()
    setSavingStorage(true)
    setStorageModalError('')
    setActionSuccess('')
    try {
      const updates = {
        OBJECT_STORAGE_PROVIDER: storageForm.provider,
        R2_BUCKET_NAME: storageForm.bucketName,
        R2_ENDPOINT_URL: storageForm.endpointUrl,
        R2_REGION: storageForm.region,
        OBJECT_STORAGE_BUCKET_PREFIX: storageForm.bucketPrefix,
      }
      if (storageForm.accessKeyId && storageForm.accessKeyId.trim()) {
        updates.R2_ACCESS_KEY_ID = storageForm.accessKeyId.trim()
      }
      if (storageForm.secretAccessKey && storageForm.secretAccessKey.trim()) {
        updates.R2_SECRET_ACCESS_KEY = storageForm.secretAccessKey.trim()
      }
      if (storageForm.confirmPassword) {
        updates.confirm_password = storageForm.confirmPassword
      }

      await systemAdminApi.updateSystemAdminTechnicalSettings(updates)
      setActionSuccess('Object storage configuration updated successfully.')
      setStorageModalOpen(false)
      await loadSettings()
    } catch (err) {
      setStorageModalError(err.response?.data?.message || err.message || 'Failed to update object storage settings.')
    } finally {
      setSavingStorage(false)
    }
  }

  const handleValidateStorage = async () => {
    setValidatingStorage(true)
    setStorageValidationResult(null)
    try {
      const res = await systemAdminApi.validateStorageCredentials({})
      const resultData = res?.data || res
      setStorageValidationResult(resultData)
      return resultData
    } catch (err) {
      const msg = err.response?.data?.message || err.message || 'Storage validation failed.'
      const resultData = { valid: false, message: msg }
      setStorageValidationResult(resultData)
      return resultData
    } finally {
      setValidatingStorage(false)
    }
  }

  // ── Email Handlers ──────────────────────────────────────────────────────────
  const openEmailModal = () => {
    const e = settings?.email_settings || {}
    setEmailForm({
      host: e.SMTP_HOST?.value || '',
      port: e.SMTP_PORT?.value ?? 587,
      useTls: e.SMTP_USE_TLS?.value ?? true,
      fromAddress: e.MAIL_FROM?.value || '',
      username: '',
      password: '',
      confirmPassword: '',
    })
    setEmailModalError('')
    setEmailModalOpen(true)
  }

  const handleSaveEmail = async (e) => {
    if (e && e.preventDefault) e.preventDefault()
    setSavingEmail(true)
    setEmailModalError('')
    setActionSuccess('')
    try {
      const updates = {
        SMTP_HOST: emailForm.host,
        SMTP_PORT: Number(emailForm.port),
        SMTP_USE_TLS: Boolean(emailForm.useTls),
        MAIL_FROM: emailForm.fromAddress,
      }
      if (emailForm.username && emailForm.username.trim()) {
        updates.SMTP_USERNAME = emailForm.username.trim()
      }
      if (emailForm.password && emailForm.password.trim()) {
        updates.SMTP_PASSWORD = emailForm.password.trim()
      }
      if (emailForm.confirmPassword) {
        updates.confirm_password = emailForm.confirmPassword
      }

      await systemAdminApi.updateSystemAdminTechnicalSettings(updates)
      setActionSuccess('Transactional email configuration updated successfully.')
      setEmailModalOpen(false)
      await loadSettings()
    } catch (err) {
      setEmailModalError(err.response?.data?.message || err.message || 'Failed to update transactional email settings.')
    } finally {
      setSavingEmail(false)
    }
  }

  const handleValidateEmail = async () => {
    setValidatingEmail(true)
    setEmailValidationResult(null)
    try {
      const res = await systemAdminApi.validateEmailCredentials({})
      const resultData = res?.data || res
      setEmailValidationResult(resultData)
      return resultData
    } catch (err) {
      const msg = err.response?.data?.message || err.message || 'SMTP validation probe failed.'
      const resultData = { valid: false, message: msg }
      setEmailValidationResult(resultData)
      return resultData
    } finally {
      setValidatingEmail(false)
    }
  }

  // ── Drive Handlers ──────────────────────────────────────────────────────────
  const openDriveModal = () => {
    const d = settings?.drive_settings || {}
    setDriveForm({
      rootFolderId: d.root_folder_id || '',
      sharedDriveId: d.shared_drive_id || '',
      confirmPassword: '',
    })
    setDriveModalError('')
    setDriveModalOpen(true)
  }

  const handleSaveDrive = async (e) => {
    if (e && e.preventDefault) e.preventDefault()
    setSavingDrive(true)
    setDriveModalError('')
    setActionSuccess('')
    try {
      const updates = {
        google_drive_root_folder_id: driveForm.rootFolderId,
        GOOGLE_DRIVE_SHARED_DRIVE_ID: driveForm.sharedDriveId,
      }
      if (driveForm.confirmPassword) {
        updates.confirm_password = driveForm.confirmPassword
      }

      await systemAdminApi.updateSystemAdminTechnicalSettings(updates)
      setActionSuccess('Google Drive handoff settings updated successfully.')
      setDriveModalOpen(false)
      await loadSettings()
    } catch (err) {
      setDriveModalError(err.response?.data?.message || err.message || 'Failed to update Google Drive settings.')
    } finally {
      setSavingDrive(false)
    }
  }

  const handleStartDriveOAuth = async () => {
    setConnectingDrive(true)
    setError('')
    try {
      const res = await systemAdminApi.startDriveOAuth()
      const data = res?.data || res
      if (data?.authorization_url) {
        window.location.href = data.authorization_url
      } else {
        setError('OAuth authorization URL was not returned by the server.')
      }
    } catch (err) {
      setError(err.response?.data?.message || err.message || 'Failed to start Google Drive OAuth authorization flow.')
    } finally {
      setConnectingDrive(false)
    }
  }

  const handleConfirmDisconnectDrive = async () => {
    setDisconnectingDrive(true)
    setError('')
    setActionSuccess('')
    try {
      await systemAdminApi.disconnectDriveOAuth()
      setActionSuccess('Google Drive account disconnected successfully.')
      setDriveDisconnectModalOpen(false)
      await loadSettings()
    } catch (err) {
      setError(err.response?.data?.message || err.message || 'Failed to disconnect Google Drive.')
    } finally {
      setDisconnectingDrive(false)
    }
  }

  // ── Universal Reset Override Handler ────────────────────────────────────────
  const handleConfirmResetOverride = async () => {
    if (!resetOverrideKey) return
    setResettingOverride(true)
    setError('')
    setActionSuccess('')
    try {
      const headers = {}
      if (resetConfirmPassword) {
        headers['X-Step-Up-Password'] = resetConfirmPassword
      }
      await systemAdminApi.deleteSystemAdminTechnicalSettingOverride(resetOverrideKey, headers)
      setActionSuccess(`Database override for '${resetOverrideKey}' removed; reverted to deployment fallback.`)
      setResetOverrideKey(null)
      setResetConfirmPassword('')
      await loadSettings()
    } catch (err) {
      setError(err.response?.data?.message || 'Failed to reset configuration override.')
    } finally {
      setResettingOverride(false)
    }
  }

  // Derived Values
  const providers = settings?.providers || {}
  const ai = providers.ai || {}
  const aiSettings = settings?.ai_settings || {}
  const driveSettings = settings?.drive_settings || {}

  const readyChecks = settings?.readiness?.summary?.ready || 0
  const totalChecks = settings?.readiness?.summary?.total || 0

  const providerTableRows = useMemo(() => providerRows(settings), [settings])
  const runtimeTableRows = useMemo(() => runtimeRows(settings), [settings])
  const storageTableRows = useMemo(() => storageRows(settings), [settings])
  const emailTableRows = useMemo(() => emailRows(settings), [settings])
  const driveTableRows = useMemo(() => driveRows(settings), [settings])

  const providerColumns = [
    { key: 'area', label: 'Area', render: (row) => <span className="text-sm text-brand-text-muted">{row.area}</span> },
    { key: 'setting', label: 'Setting', render: (row) => <span className="font-medium text-brand-text">{row.setting}</span> },
    { key: 'value', label: 'Value', render: (row) => <span className="break-words text-sm text-brand-text-muted">{valueOrDash(row.value)}</span> },
    { key: 'status', label: 'Status', render: (row) => statusBadge(row.status) },
  ]

  const runtimeColumns = [
    { key: 'label', label: 'Runtime', render: (row) => <span className="font-medium text-brand-text">{row.label}</span> },
    { key: 'value', label: 'Value', render: (row) => <span className="break-words text-sm text-brand-text-muted">{valueOrDash(row.value)}</span> },
  ]

  const integrationConfigColumns = (onResetOverride) => [
    {
      key: 'label',
      label: 'Setting',
      render: (row) => (
        <div>
          <span className="font-medium text-brand-text">{row.label}</span>
          <span className="block font-mono text-xs text-brand-text-muted">{row.key}</span>
        </div>
      ),
    },
    {
      key: 'value',
      label: 'Effective Value',
      render: (row) => (
        <span className="font-mono text-xs text-brand-text break-all">
          {row.isSecret
            ? (row.maskedPreview ? '••••••••' : '(not configured)')
            : valueOrDash(row.value)}
        </span>
      ),
    },
    {
      key: 'source',
      label: 'Source',
      render: (row) => sourceBadge(row.source, row.hasOverride, row.overrideStatus, row.overrideError),
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (row) =>
        row.hasOverride ? (
          <Button
            size="sm"
            variant="ghost"
            icon={RotateCcw}
            onClick={() => onResetOverride(row.key)}
            className="text-xs text-amber-700 dark:text-amber-400"
            title="Reset database override to deployment fallback"
          >
            Reset
          </Button>
        ) : (
          <span className="text-xs text-brand-text-muted">-</span>
        ),
    },
  ]

  const backupColumns = [
    {
      key: 'created_at',
      label: 'Timestamp',
      render: (row) => <span className="font-medium text-brand-text">{formatDateTime(row.created_at)}</span>,
    },
    {
      key: 'filename',
      label: 'Archive Filename',
      render: (row) => <span className="font-mono text-xs text-brand-text-muted">{row.filename}</span>,
    },
    {
      key: 'byte_size',
      label: 'Size',
      render: (row) => <span className="text-sm text-brand-text">{formatBytes(row.byte_size)}</span>,
    },
    {
      key: 'trigger_type',
      label: 'Trigger',
      render: (row) => (
        <span className="inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs font-medium text-slate-700 dark:text-slate-300 capitalize">
          {row.trigger_type}
        </span>
      ),
    },
    {
      key: 'storage_provider',
      label: 'Storage',
      render: (row) => (
        <span className="inline-flex items-center rounded-full bg-sky-50 dark:bg-sky-950 px-2 py-0.5 text-xs font-medium text-sky-700 dark:text-sky-300 uppercase">
          {row.storage_provider}
        </span>
      ),
    },
    {
      key: 'sha256_checksum',
      label: 'SHA-256',
      render: (row) => (
        <span className="font-mono text-[11px] text-brand-text-muted" title={row.sha256_checksum}>
          {row.sha256_checksum ? `${row.sha256_checksum.substring(0, 12)}...` : '-'}
        </span>
      ),
    },
    {
      key: 'status',
      label: 'Status',
      render: (row) => statusBadge(row.status),
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (row) =>
        row.status === 'completed' ? (
          <Button
            size="sm"
            variant="ghost"
            icon={Download}
            onClick={() => handleDownloadBackup(row)}
            title="Download backup dump archive"
          >
            Download
          </Button>
        ) : '-',
    },
  ]

  const backupsSummary = backupsData.summary || {}

  const aiProviderCards = [
    { id: 'gemini', name: 'Google Gemini', secretKey: 'GEMINI_API_KEY', modelKey: 'GEMINI_MODEL' },
    { id: 'groq', name: 'Groq Cloud', secretKey: 'GROQ_API_KEY', modelKey: 'GROQ_MODEL' },
    { id: 'openrouter', name: 'OpenRouter', secretKey: 'OPENROUTER_API_KEY', modelKey: 'OPENROUTER_MODEL' },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title="Technical Settings"
        description="Unified configuration and connectivity management for AI providers, Cloudflare R2 object storage, transactional email relay, and Google Drive handoffs."
        actions={(
          <Button variant="outline" icon={RefreshCw} onClick={() => { loadSettings(); loadBackups(); }} loading={loading || backupsLoading}>
            Refresh
          </Button>
        )}
      />

      <InlineAlert type="error" onDismiss={() => setError('')}>
        {error}
      </InlineAlert>

      {actionSuccess && (
        <InlineAlert type="success" onDismiss={() => setActionSuccess('')}>
          {actionSuccess}
        </InlineAlert>
      )}

      {backupSuccess && (
        <InlineAlert type="success" onDismiss={() => setBackupSuccess('')}>
          {backupSuccess}
        </InlineAlert>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          title="AI Providers"
          value={`${formatCount(ai.configured_count || 0)}/${formatCount((ai.providers || []).length || 3)}`}
          subtitle="configured and ready"
          icon={KeyRound}
          color={ai.configured_count ? 'emerald' : 'amber'}
        />
        <KpiCard
          title="Readiness"
          value={`${formatCount(readyChecks)}/${formatCount(totalChecks)}`}
          subtitle="system checks ready"
          icon={SlidersHorizontal}
          color={readyChecks === totalChecks ? 'emerald' : 'amber'}
        />
        <KpiCard
          title="DB Backups"
          value={formatCount(backupsSummary.completed_count || 0)}
          subtitle={`${formatBytes(backupsSummary.total_bytes || 0)} retained (${backupsSummary.storage_provider || 'local'})`}
          icon={Database}
          color="blue"
        />
        <KpiCard
          title="Runtime"
          value={settings?.runtime?.environment || 'Unknown'}
          subtitle={settings?.runtime?.app_name || 'Application runtime'}
          icon={ServerCog}
          color="purple"
        />
      </div>

      {/* ── Integration Tabs Navigation ────────────────────────────────────── */}
      <div className="border-b border-slate-200 dark:border-slate-800" role="tablist">
        <div className="flex flex-wrap gap-2">
          {INTEGRATION_TABS.map((tab) => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors -mb-px ${
                  isActive
                    ? 'border-brand-primary text-brand-primary font-semibold'
                    : 'border-transparent text-slate-600 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                <Icon className={`h-4 w-4 ${isActive ? 'text-brand-primary' : 'text-slate-400'}`} />
                <span>{tab.label}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* ── TAB 1: AI Providers & Runtime ──────────────────────────────────── */}
      {activeTab === 'ai' && (
        <div className="space-y-6">
          {/* AI Provider Cards */}
          <GlassPanel className="p-5">
            <div className="mb-4">
              <h2 className="section-title flex items-center gap-2">
                <KeyRound className="h-5 w-5 text-brand-primary" />
                AI Providers Configuration
              </h2>
              <p className="mt-1 text-sm text-brand-text-muted">
                Manage provider credentials, selected models, and test connectivity. Credentials are encrypted at rest using Fernet and never returned in plaintext.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {aiProviderCards.map((p) => {
                const secretInfo = aiSettings[p.secretKey] || {}
                const modelInfo = aiSettings[p.modelKey] || {}
                const isConfigured = secretInfo.has_value
                const valResult = validationResults[p.id]
                const isValidating = validatingProvider[p.id]
                const hasSecretOverride = secretInfo.has_override
                const hasModelOverride = modelInfo.has_override

                return (
                  <div
                    key={p.id}
                    className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-slate-900/50 p-4 flex flex-col justify-between space-y-4"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="font-semibold text-brand-text text-base">{p.name}</h3>
                        <span className={badgeClassForStatus(isConfigured ? 'ready' : 'disabled')}>
                          {isConfigured ? 'Configured' : 'Not Configured'}
                        </span>
                      </div>

                      <div className="space-y-2 text-xs">
                        <div>
                          <span className="text-brand-text-muted">Active Model:</span>{' '}
                          <span className="font-mono font-medium text-brand-text">{modelInfo.value || '-'}</span>
                          <div className="mt-0.5">{sourceBadge(modelInfo.source, modelInfo.has_override, modelInfo.override_status, modelInfo.override_error)}</div>
                        </div>

                        <div>
                          <span className="text-brand-text-muted">Access Key:</span>{' '}
                          <span className="font-mono text-brand-text">
                            {secretInfo.masked_preview ? '••••••••' : '(none)'}
                          </span>
                          <div className="mt-0.5">{sourceBadge(secretInfo.source, secretInfo.has_override, secretInfo.override_status, secretInfo.override_error)}</div>
                        </div>

                        {secretInfo.override_status === 'invalid_or_unreadable' && (
                          <div className="mt-2 p-2 rounded bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900/50 text-amber-800 dark:text-amber-300 text-xs flex items-start gap-1.5">
                            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
                            <span>{secretInfo.override_error || 'Database override could not be decrypted; environment fallback is active.'}</span>
                          </div>
                        )}

                        {valResult && (
                          <div
                            className={`mt-2 p-2 rounded text-xs flex items-start gap-1.5 ${
                              valResult.valid
                                ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-300'
                                : 'bg-rose-50 dark:bg-rose-950/40 text-rose-800 dark:text-rose-300'
                            }`}
                          >
                            {valResult.valid ? (
                              <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-emerald-600 dark:text-emerald-400" />
                            ) : (
                              <XCircle className="h-4 w-4 shrink-0 mt-0.5 text-rose-600 dark:text-rose-400" />
                            )}
                            <span>{valResult.message}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="pt-2 border-t border-slate-100 dark:border-slate-800 space-y-2">
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="primary"
                          icon={Edit3}
                          onClick={() => openProviderModal(p.id)}
                          className="flex-1"
                        >
                          Configure
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleValidateProvider(p.id)}
                          loading={isValidating}
                          title="Run a low-cost connection probe without generating tokens"
                        >
                          Test
                        </Button>
                      </div>

                      {(hasSecretOverride || hasModelOverride) && (
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={RotateCcw}
                          onClick={() => setResetOverrideKey(hasSecretOverride ? p.secretKey : p.modelKey)}
                          className="w-full text-xs text-amber-700 dark:text-amber-400"
                        >
                          Reset to Environment
                        </Button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </GlassPanel>

          {/* AI Runtime Parameters */}
          <GlassPanel className="p-5">
            <div className="mb-4">
              <h2 className="section-title flex items-center gap-2">
                <SlidersHorizontal className="h-5 w-5 text-brand-primary" />
                AI Runtime Parameters
              </h2>
              <p className="mt-1 text-sm text-brand-text-muted">
                Configure provider failover priority and runtime constraints across backend services and Celery workers.
              </p>
            </div>

            {runtimeError && (
              <InlineAlert type="error" onDismiss={() => setRuntimeError('')} className="mb-4">
                {runtimeError}
              </InlineAlert>
            )}

            <form onSubmit={handleSaveRuntimeParameters} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <FormField
                  label="Provider Failover Priority Order"
                  description="Comma-separated list in priority order (e.g. gemini, groq, openrouter)"
                >
                  <input
                    type="text"
                    className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                    value={runtimeForm.providerOrder}
                    onChange={(e) => setRuntimeForm({ ...runtimeForm, providerOrder: e.target.value })}
                    placeholder="gemini, groq, openrouter"
                    required
                  />
                </FormField>

                <FormField
                  label="Request Timeout (Seconds)"
                  description="Maximum duration before AI requests fail over to next provider (5 to 120s)"
                >
                  <input
                    type="number"
                    min="5"
                    max="120"
                    className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text"
                    value={runtimeForm.timeout}
                    onChange={(e) => setRuntimeForm({ ...runtimeForm, timeout: e.target.value })}
                    required
                  />
                </FormField>

                <FormField
                  label="Temperature"
                  description="Controls sampling randomness (0.0 for deterministic analysis, up to 2.0)"
                >
                  <input
                    type="number"
                    step="0.05"
                    min="0.0"
                    max="2.0"
                    className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text"
                    value={runtimeForm.temperature}
                    onChange={(e) => setRuntimeForm({ ...runtimeForm, temperature: e.target.value })}
                    required
                  />
                </FormField>

                <FormField
                  label="Maximum Output Tokens"
                  description="Token ceiling per AI completion request (100 to 16,000 tokens)"
                >
                  <input
                    type="number"
                    min="100"
                    max="16000"
                    step="100"
                    className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text"
                    value={runtimeForm.maxTokens}
                    onChange={(e) => setRuntimeForm({ ...runtimeForm, maxTokens: e.target.value })}
                    required
                  />
                </FormField>

                <FormField
                  label="Maximum Prompt Characters"
                  description="Input length limit before refusal/truncation guardrails apply (500 to 100,000 chars)"
                >
                  <input
                    type="number"
                    min="500"
                    max="100000"
                    step="500"
                    className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text"
                    value={runtimeForm.maxPromptChars}
                    onChange={(e) => setRuntimeForm({ ...runtimeForm, maxPromptChars: e.target.value })}
                    required
                  />
                </FormField>

                <FormField
                  label="Step-Up Confirmation Password"
                  description="Required for privileged technical configuration changes if session has expired"
                >
                  <input
                    type="password"
                    className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text"
                    value={runtimeForm.confirmPassword}
                    onChange={(e) => setRuntimeForm({ ...runtimeForm, confirmPassword: e.target.value })}
                    placeholder="Enter password to confirm"
                  />
                </FormField>
              </div>

              <div className="flex justify-end pt-2">
                <Button
                  type="button"
                  variant="primary"
                  icon={SlidersHorizontal}
                  onClick={handleSaveRuntimeParameters}
                  loading={savingRuntime}
                >
                  Save Runtime Parameters
                </Button>
              </div>
            </form>
          </GlassPanel>

          {/* Provider Runtime Settings Table */}
          <GlassPanel className="p-5">
            <div className="mb-4">
              <h2 className="section-title">Provider Runtime Settings</h2>
              <p className="mt-1 text-sm text-brand-text-muted">
                Configured state is visible; secret values are never returned by the API.
              </p>
            </div>
            <DataTable
              columns={providerColumns}
              data={providerTableRows}
              keyField="key"
              isLoading={loading}
              emptyMessage="No provider settings available."
              caption="Technical provider runtime settings"
              density="compact"
            />
          </GlassPanel>
        </div>
      )}

      {/* ── TAB 2: Cloudflare R2 Storage ───────────────────────────────────── */}
      {activeTab === 'storage' && (
        <div className="space-y-6">
          {/* Existing-Objects Safety Alert */}
          <div className="rounded-xl border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 p-4 text-amber-900 dark:text-amber-200">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
              <div>
                <h4 className="font-semibold text-sm">Storage Safety & Migration Guardrails</h4>
                <p className="mt-1 text-xs leading-relaxed text-amber-800 dark:text-amber-300">
                  Modifying the object storage provider, bucket name (<code className="font-mono">R2_BUCKET_NAME</code>), or endpoint URL (<code className="font-mono">R2_ENDPOINT_URL</code>) does not automatically migrate existing stored documents, templates, or database backup archives. If stored files currently reside in Cloudflare R2, configuration changes to the bucket or endpoint will be rejected by the server to prevent stranding active files. Coordinated data migration is required before switching targets.
                </p>
              </div>
            </div>
          </div>

          {/* Storage Actions and Diagnostics */}
          <GlassPanel className="p-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
              <div>
                <h2 className="section-title flex items-center gap-2">
                  <Cloud className="h-5 w-5 text-brand-primary" />
                  Cloudflare R2 Object Storage
                </h2>
                <p className="mt-1 text-sm text-brand-text-muted">
                  S3-compatible durable object storage for uploaded files, document compliance runs, and automated database backups.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  icon={CheckCircle2}
                  onClick={handleValidateStorage}
                  loading={validatingStorage}
                  title="Run non-destructive read-only probe against effective storage configuration"
                >
                  Validate Connection
                </Button>
                <Button
                  variant="primary"
                  icon={Edit3}
                  onClick={openStorageModal}
                >
                  Configure Storage
                </Button>
              </div>
            </div>

            {/* Validation Feedback */}
            {storageValidationResult && (
              <div
                className={`mb-4 p-3 rounded-lg text-sm flex items-start gap-2 ${
                  storageValidationResult.valid
                    ? 'bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900/50 text-emerald-800 dark:text-emerald-300'
                    : 'bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/50 text-rose-800 dark:text-rose-300'
                }`}
              >
                {storageValidationResult.valid ? (
                  <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600 dark:text-emerald-400 mt-0.5" />
                ) : (
                  <XCircle className="h-5 w-5 shrink-0 text-rose-600 dark:text-rose-400 mt-0.5" />
                )}
                <div>
                  <span className="font-medium">
                    {storageValidationResult.valid ? 'Storage Connection Valid' : 'Storage Validation Failed'}
                  </span>
                  <p className="mt-0.5 text-xs">{storageValidationResult.message}</p>
                </div>
              </div>
            )}

            {/* Storage Settings Table */}
            <DataTable
              columns={integrationConfigColumns((key) => setResetOverrideKey(key))}
              data={storageTableRows}
              keyField="key"
              isLoading={loading}
              emptyMessage="No storage settings found."
              caption="Effective object storage configuration"
              density="compact"
            />
          </GlassPanel>
        </div>
      )}

      {/* ── TAB 3: Transactional Email (SMTP) ──────────────────────────────── */}
      {activeTab === 'email' && (
        <div className="space-y-6">
          {/* Non-Sending Notice */}
          <div className="rounded-xl border border-blue-200 dark:border-blue-900/50 bg-blue-50 dark:bg-blue-950/40 p-4 text-blue-900 dark:text-blue-200">
            <div className="flex items-start gap-3">
              <Info className="h-5 w-5 shrink-0 text-blue-600 dark:text-blue-400 mt-0.5" />
              <div>
                <h4 className="font-semibold text-sm">Non-Sending Diagnostic Validation</h4>
                <p className="mt-1 text-xs leading-relaxed text-blue-800 dark:text-blue-300">
                  The SMTP validation probe establishes a direct TCP socket, performs the TLS handshake (when enabled), verifies credentials with the SMTP relay, and issues a harmless NOOP command. In accordance with operational reliability guidelines, <strong>no test email is transmitted</strong> to avoid consuming transactional quotas or triggering spam filter penalties.
                </p>
              </div>
            </div>
          </div>

          {/* Email Actions and Diagnostics */}
          <GlassPanel className="p-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
              <div>
                <h2 className="section-title flex items-center gap-2">
                  <Mail className="h-5 w-5 text-brand-primary" />
                  Transactional Email (SMTP Relay)
                </h2>
                <p className="mt-1 text-sm text-brand-text-muted">
                  Outbound SMTP relay configuration for user invitations, password resets, and automated notification alerts.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  icon={CheckCircle2}
                  onClick={handleValidateEmail}
                  loading={validatingEmail}
                  title="Run socket/TLS/AUTH probe without transmitting emails"
                >
                  Validate SMTP Connection
                </Button>
                <Button
                  variant="primary"
                  icon={Edit3}
                  onClick={openEmailModal}
                >
                  Configure SMTP Relay
                </Button>
              </div>
            </div>

            {/* Validation Feedback */}
            {emailValidationResult && (
              <div
                className={`mb-4 p-3 rounded-lg text-sm flex items-start gap-2 ${
                  emailValidationResult.valid
                    ? 'bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900/50 text-emerald-800 dark:text-emerald-300'
                    : 'bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/50 text-rose-800 dark:text-rose-300'
                }`}
              >
                {emailValidationResult.valid ? (
                  <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600 dark:text-emerald-400 mt-0.5" />
                ) : (
                  <XCircle className="h-5 w-5 shrink-0 text-rose-600 dark:text-rose-400 mt-0.5" />
                )}
                <div>
                  <span className="font-medium">
                    {emailValidationResult.valid ? 'SMTP Connection Valid' : 'SMTP Validation Failed'}
                  </span>
                  <p className="mt-0.5 text-xs">{emailValidationResult.message}</p>
                </div>
              </div>
            )}

            {/* Email Settings Table */}
            <DataTable
              columns={integrationConfigColumns((key) => setResetOverrideKey(key))}
              data={emailTableRows}
              keyField="key"
              isLoading={loading}
              emptyMessage="No transactional email settings found."
              caption="Effective transactional email configuration"
              density="compact"
            />
          </GlassPanel>
        </div>
      )}

      {/* ── TAB 4: Google Drive & Handoffs ──────────────────────────────────── */}
      {activeTab === 'drive' && (
        <div className="space-y-6">
          {/* Prerequisite Alert if OAuth is not configured */}
          {!driveSettings?.oauth_configured && (
            <div className="rounded-xl border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 p-4 text-amber-900 dark:text-amber-200">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
                <div>
                  <h4 className="font-semibold text-sm">OAuth Deployment Prerequisites Required</h4>
                  <p className="mt-1 text-xs leading-relaxed text-amber-800 dark:text-amber-300">
                    Google Drive OAuth integration requires deployment-level credentials. Please ensure <code className="font-mono">GOOGLE_OAUTH_CLIENT_ID</code> and <code className="font-mono">GOOGLE_OAUTH_CLIENT_SECRET</code> are configured in the server environment before initiating the authorization flow.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Unreadable Credential Warning */}
          {driveSettings?.credential_error && (
            <div className="rounded-xl border border-rose-300 dark:border-rose-800 bg-rose-50 dark:bg-rose-950/40 p-4 text-rose-900 dark:text-rose-200">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 shrink-0 text-rose-600 dark:text-rose-400 mt-0.5" />
                <div>
                  <h4 className="font-semibold text-sm">Stored OAuth Credentials Error</h4>
                  <p className="mt-1 text-xs leading-relaxed text-rose-800 dark:text-rose-300">
                    {driveSettings.credential_error}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Drive Main Panel */}
          <GlassPanel className="p-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
              <div>
                <h2 className="section-title flex items-center gap-2">
                  <FolderTree className="h-5 w-5 text-brand-primary" />
                  Google Drive & Regional Handoffs
                </h2>
                <p className="mt-1 text-sm text-brand-text-muted">
                  Manage cloud folder routing, shared drive workspace bindings, and OAuth connection for document handoffs.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  icon={Edit3}
                  onClick={openDriveModal}
                >
                  Configure Folders
                </Button>
                {driveSettings?.oauth_connected ? (
                  <>
                    <Button
                      variant="primary"
                      icon={RefreshCw}
                      onClick={handleStartDriveOAuth}
                      loading={connectingDrive}
                      title="Reconnect Google Drive account"
                    >
                      Reconnect
                    </Button>
                    <Button
                      variant="danger"
                      icon={Unlink}
                      onClick={() => setDriveDisconnectModalOpen(true)}
                    >
                      Disconnect
                    </Button>
                  </>
                ) : (
                  <Button
                    variant="primary"
                    icon={ExternalLink}
                    onClick={handleStartDriveOAuth}
                    loading={connectingDrive}
                    disabled={!driveSettings?.oauth_configured}
                    title={!driveSettings?.oauth_configured ? 'Requires GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in environment' : 'Initiate Google Drive authorization'}
                  >
                    Connect Google Drive
                  </Button>
                )}
              </div>
            </div>

            {/* Connection Status Card */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-3 bg-white/40 dark:bg-slate-900/40">
                <span className="text-xs text-brand-text-muted block">Connection Status</span>
                <div className="mt-1 flex items-center gap-2">
                  {driveSettings?.oauth_connected ? (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 dark:bg-emerald-950 px-2.5 py-0.5 text-xs font-semibold text-emerald-800 dark:text-emerald-300">
                      <CheckCircle2 className="h-3.5 w-3.5" /> Connected
                    </span>
                  ) : driveSettings?.credential_error ? (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-100 dark:bg-rose-950 px-2.5 py-0.5 text-xs font-semibold text-rose-800 dark:text-rose-300">
                      <XCircle className="h-3.5 w-3.5" /> Connection Error
                    </span>
                  ) : driveSettings?.oauth_configured ? (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-100 dark:bg-blue-950 px-2.5 py-0.5 text-xs font-semibold text-blue-800 dark:text-blue-300">
                      Configured
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 dark:bg-slate-800 px-2.5 py-0.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                      Not Configured
                    </span>
                  )}
                </div>
              </div>

              <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-3 bg-white/40 dark:bg-slate-900/40">
                <span className="text-xs text-brand-text-muted block">Connected Account</span>
                <span className="mt-1 font-medium text-brand-text text-sm block truncate" title={driveSettings?.connected_email || '(none)'}>
                  {driveSettings?.connected_email || '(none)'}
                </span>
              </div>

              <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-3 bg-white/40 dark:bg-slate-900/40">
                <span className="text-xs text-brand-text-muted block">Auth Mode</span>
                <span className="mt-1 font-mono text-xs text-brand-text block uppercase">
                  {driveSettings?.auth_mode || 'unconfigured'}
                </span>
              </div>

              <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-3 bg-white/40 dark:bg-slate-900/40">
                <span className="text-xs text-brand-text-muted block">Service Account Fallback</span>
                <span className="mt-1 text-xs text-brand-text block">
                  {driveSettings?.service_account_configured ? 'Configured' : 'Not Configured'}
                </span>
              </div>
            </div>

            {/* Folder Configuration Table */}
            <DataTable
              columns={integrationConfigColumns((key) => setResetOverrideKey(key))}
              data={driveTableRows}
              keyField="key"
              isLoading={loading}
              emptyMessage="No Google Drive folder settings found."
              caption="Google Drive folder routing"
              density="compact"
            />

            {/* Security Note */}
            <div className="mt-4 flex items-start gap-2 text-xs text-brand-text-muted">
              <Lock className="h-4 w-4 shrink-0 text-slate-400 mt-0.5" />
              <span>
                OAuth refresh and access tokens are encrypted at rest using Fernet and never transmitted to or held in browser storage.
              </span>
            </div>
          </GlassPanel>
        </div>
      )}

      {/* ── COMMON SECTION 1: Environment & Deployment Infrastructure ──────── */}
      <GlassPanel className="p-5 border-l-4 border-l-brand-primary">
        <div className="flex items-start gap-3">
          <Shield className="h-6 w-6 text-brand-primary shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-brand-text text-base">Environment & Deployment Infrastructure</h3>
            <p className="mt-1 text-sm text-brand-text-muted leading-relaxed">
              Cryptographic keys (<code className="text-xs bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded">SECRET_KEY</code>,{' '}
              <code className="text-xs bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded">JWT_SECRET_KEY</code>,{' '}
              <code className="text-xs bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded">SYSTEM_CONFIG_SECRET_KEY</code>),{' '}
              PostgreSQL connection strings (<code className="text-xs bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded">DATABASE_URL</code>),{' '}
              and Celery broker configuration remain strictly deployment-managed via environment variables.
              They cannot be modified at runtime through administrative interfaces to preserve infrastructure isolation and security.
            </p>
          </div>
        </div>
      </GlassPanel>

      {/* ── COMMON SECTION 2: Database Backups ──────────────────────────────── */}
      <GlassPanel className="p-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div>
            <h2 className="section-title flex items-center gap-2">
              <HardDrive className="h-5 w-5 text-brand-primary" />
              Database Backups & Snapshot Archives
            </h2>
            <p className="mt-1 text-sm text-brand-text-muted">
              Scheduled daily snapshots (30-day retention) and on-demand compressed dumps stored to Cloudflare R2 / durable storage.
            </p>
          </div>
          <Button
            variant="primary"
            icon={Database}
            onClick={handleTriggerBackup}
            loading={triggeringBackup}
          >
            Create Backup Now
          </Button>
        </div>

        <DataTable
          columns={backupColumns}
          data={backupsData.backups || []}
          keyField="id"
          isLoading={backupsLoading}
          emptyMessage="No database backups created yet. Click 'Create Backup Now' to generate an immediate snapshot."
          caption="Database backup history"
          density="compact"
        />
      </GlassPanel>

      {/* ── COMMON SECTION 3: Technical Runtime Configuration ───────────────── */}
      <GlassPanel className="p-5">
        <div className="mb-4">
          <h2 className="section-title">Runtime Configuration</h2>
          <p className="mt-1 text-sm text-brand-text-muted">
            Deployment-level runtime state shown without database URLs, tokens, or secrets.
          </p>
        </div>
        <DataTable
          columns={runtimeColumns}
          data={runtimeTableRows}
          keyField="key"
          isLoading={loading}
          emptyMessage="No runtime metadata available."
          caption="Technical runtime configuration"
          density="compact"
        />
      </GlassPanel>

      {/* ── MODALS ──────────────────────────────────────────────────────────── */}

      {/* 1. Edit AI Provider Modal */}
      {editingProvider && (
        <Modal
          open={Boolean(editingProvider)}
          title={`Configure ${aiProviderCards.find((c) => c.id === editingProvider)?.name || formatMachineLabel(editingProvider)}`}
          description="Update model selection or rotate API credentials. Changes take effect on subsequent AI requests."
          size="md"
          onClose={() => setEditingProvider(null)}
          footer={(
            <div className="flex justify-end gap-3">
              <Button variant="outline" onClick={() => setEditingProvider(null)} disabled={savingProvider}>
                Cancel
              </Button>
              <Button variant="primary" onClick={handleSaveProvider} loading={savingProvider}>
                Save Changes
              </Button>
            </div>
          )}
        >
          <div className="space-y-4">
            {providerModalError && (
              <InlineAlert type="error" onDismiss={() => setProviderModalError('')}>
                {providerModalError}
              </InlineAlert>
            )}

            <FormField
              label="Selected Model"
              description="Model identifier passed to provider API"
            >
              <input
                type="text"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                value={providerForm.model}
                onChange={(e) => setProviderForm({ ...providerForm, model: e.target.value })}
                required
              />
            </FormField>

            <FormField
              label="Provider API Key"
              description="Leave blank to preserve existing key. If provided, key is encrypted at rest using Fernet."
            >
              <input
                type="password"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                value={providerForm.apiKey}
                onChange={(e) => setProviderForm({ ...providerForm, apiKey: e.target.value })}
                placeholder="Leave blank to keep unchanged"
              />
            </FormField>

            <FormField
              label="Step-Up Confirmation Password"
              description="Required for privileged technical configuration changes if session has expired"
            >
              <input
                type="password"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text"
                value={providerForm.confirmPassword}
                onChange={(e) => setProviderForm({ ...providerForm, confirmPassword: e.target.value })}
                placeholder="Admin password to confirm"
              />
            </FormField>
          </div>
        </Modal>
      )}

      {/* 2. Configure Storage Modal */}
      {storageModalOpen && (
        <Modal
          open={storageModalOpen}
          title="Configure Cloudflare R2 Object Storage"
          description="Update storage provider, bucket name, endpoint, or rotate access keys. Changes take effect on subsequent storage operations."
          size="md"
          onClose={() => setStorageModalOpen(false)}
          footer={(
            <div className="flex justify-end gap-3">
              <Button variant="outline" onClick={() => setStorageModalOpen(false)} disabled={savingStorage}>
                Cancel
              </Button>
              <Button variant="primary" onClick={handleSaveStorage} loading={savingStorage}>
                Save Changes
              </Button>
            </div>
          )}
        >
          <div className="space-y-4">
            {storageModalError && (
              <InlineAlert type="error" onDismiss={() => setStorageModalError('')}>
                {storageModalError}
              </InlineAlert>
            )}

            <FormField label="Storage Provider" description="Active object storage backend">
              <select
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text"
                value={storageForm.provider}
                onChange={(e) => setStorageForm({ ...storageForm, provider: e.target.value })}
              >
                <option value="r2">Cloudflare R2 (S3-Compatible)</option>
                <option value="local">Local Storage (Development only)</option>
              </select>
            </FormField>

            <FormField label="R2 Bucket Name" description="Target bucket for document and backup objects">
              <input
                type="text"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                value={storageForm.bucketName}
                onChange={(e) => setStorageForm({ ...storageForm, bucketName: e.target.value })}
                placeholder="e.g. comet-production-storage"
              />
            </FormField>

            <FormField label="R2 Endpoint URL" description="S3-compatible endpoint URL for Cloudflare R2">
              <input
                type="text"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                value={storageForm.endpointUrl}
                onChange={(e) => setStorageForm({ ...storageForm, endpointUrl: e.target.value })}
                placeholder="https://<account_id>.r2.cloudflarestorage.com"
              />
            </FormField>

            <FormField label="R2 Access Key ID" description="S3 API token Access Key ID">
              <input
                type="text"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                value={storageForm.accessKeyId}
                onChange={(e) => setStorageForm({ ...storageForm, accessKeyId: e.target.value })}
                placeholder="Leave blank to keep unchanged"
              />
            </FormField>

            <FormField label="R2 Secret Access Key" description="S3 API token Secret Access Key (encrypted at rest)">
              <input
                type="password"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                value={storageForm.secretAccessKey}
                onChange={(e) => setStorageForm({ ...storageForm, secretAccessKey: e.target.value })}
                placeholder="Leave blank to keep unchanged"
              />
            </FormField>

            <FormField label="R2 Region" description="Region identifier (defaults to 'auto')">
              <input
                type="text"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                value={storageForm.region}
                onChange={(e) => setStorageForm({ ...storageForm, region: e.target.value })}
                placeholder="auto"
              />
            </FormField>

            <FormField label="Bucket Object Prefix" description="Root path prefix for partitioned objects (e.g. 'comet')">
              <input
                type="text"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                value={storageForm.bucketPrefix}
                onChange={(e) => setStorageForm({ ...storageForm, bucketPrefix: e.target.value })}
                placeholder="comet"
              />
            </FormField>

            <FormField label="Step-Up Confirmation Password" description="Required for privileged technical configuration changes if session has expired">
              <input
                type="password"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text"
                value={storageForm.confirmPassword}
                onChange={(e) => setStorageForm({ ...storageForm, confirmPassword: e.target.value })}
                placeholder="Admin password to confirm"
              />
            </FormField>
          </div>
        </Modal>
      )}

      {/* 3. Configure Email Modal */}
      {emailModalOpen && (
        <Modal
          open={emailModalOpen}
          title="Configure Transactional Email (SMTP Relay)"
          description="Update outbound SMTP relay host, port, TLS security, and credentials. Changes take effect on subsequent outbound emails."
          size="md"
          onClose={() => setEmailModalOpen(false)}
          footer={(
            <div className="flex justify-end gap-3">
              <Button variant="outline" onClick={() => setEmailModalOpen(false)} disabled={savingEmail}>
                Cancel
              </Button>
              <Button variant="primary" onClick={handleSaveEmail} loading={savingEmail}>
                Save Changes
              </Button>
            </div>
          )}
        >
          <div className="space-y-4">
            {emailModalError && (
              <InlineAlert type="error" onDismiss={() => setEmailModalError('')}>
                {emailModalError}
              </InlineAlert>
            )}

            <FormField label="SMTP Host / Server" description="Outbound mail relay hostname (e.g. smtp-relay.brevo.com)">
              <input
                type="text"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                value={emailForm.host}
                onChange={(e) => setEmailForm({ ...emailForm, host: e.target.value })}
                placeholder="smtp-relay.brevo.com"
                required
              />
            </FormField>

            <FormField label="SMTP Port" description="Standard submission port (typically 587 for STARTTLS, 465 for SSL)">
              <input
                type="number"
                min="1"
                max="65535"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text"
                value={emailForm.port}
                onChange={(e) => setEmailForm({ ...emailForm, port: e.target.value })}
                required
              />
            </FormField>

            <FormField label="TLS Encryption" description="Enable STARTTLS encryption handshake for socket transport">
              <label className="flex items-center gap-2 cursor-pointer mt-1">
                <input
                  type="checkbox"
                  className="rounded border-slate-300 dark:border-slate-700 text-brand-primary focus:ring-brand-primary h-4 w-4"
                  checked={emailForm.useTls}
                  onChange={(e) => setEmailForm({ ...emailForm, useTls: e.target.checked })}
                />
                <span className="text-sm text-brand-text">Enable STARTTLS (Recommended)</span>
              </label>
            </FormField>

            <FormField label="Outbound From Address" description="Sender email address displayed in notification headers">
              <input
                type="email"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                value={emailForm.fromAddress}
                onChange={(e) => setEmailForm({ ...emailForm, fromAddress: e.target.value })}
                placeholder="notifications@example.com"
                required
              />
            </FormField>

            <FormField label="SMTP Username" description="Relay account or API key identifier">
              <input
                type="text"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                value={emailForm.username}
                onChange={(e) => setEmailForm({ ...emailForm, username: e.target.value })}
                placeholder="Leave blank to keep unchanged"
              />
            </FormField>

            <FormField label="SMTP Password / Secret" description="Relay password or API secret key (encrypted at rest)">
              <input
                type="password"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                value={emailForm.password}
                onChange={(e) => setEmailForm({ ...emailForm, password: e.target.value })}
                placeholder="Leave blank to keep unchanged"
              />
            </FormField>

            <FormField label="Step-Up Confirmation Password" description="Required for privileged technical configuration changes if session has expired">
              <input
                type="password"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text"
                value={emailForm.confirmPassword}
                onChange={(e) => setEmailForm({ ...emailForm, confirmPassword: e.target.value })}
                placeholder="Admin password to confirm"
              />
            </FormField>
          </div>
        </Modal>
      )}

      {/* 4. Configure Drive Modal */}
      {driveModalOpen && (
        <Modal
          open={driveModalOpen}
          title="Configure Google Drive Workspace Folders"
          description="Configure the root workspace folder ID and optional shared drive ID for external handoffs."
          size="md"
          onClose={() => setDriveModalOpen(false)}
          footer={(
            <div className="flex justify-end gap-3">
              <Button variant="outline" onClick={() => setDriveModalOpen(false)} disabled={savingDrive}>
                Cancel
              </Button>
              <Button variant="primary" onClick={handleSaveDrive} loading={savingDrive}>
                Save Changes
              </Button>
            </div>
          )}
        >
          <div className="space-y-4">
            {driveModalError && (
              <InlineAlert type="error" onDismiss={() => setDriveModalError('')}>
                {driveModalError}
              </InlineAlert>
            )}

            <FormField label="Workspace Root Folder ID" description="Google Drive folder ID where exported records and handoffs reside">
              <input
                type="text"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                value={driveForm.rootFolderId}
                onChange={(e) => setDriveForm({ ...driveForm, rootFolderId: e.target.value })}
                placeholder="e.g. 1a2b3c4d5e6f7g8h9i0j..."
              />
            </FormField>

            <FormField label="Shared Drive ID (Optional)" description="ID of Google Workspace Shared Drive if workspace is not in My Drive">
              <input
                type="text"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text font-mono"
                value={driveForm.sharedDriveId}
                onChange={(e) => setDriveForm({ ...driveForm, sharedDriveId: e.target.value })}
                placeholder="e.g. 0A1B2C3D4E5F6G7H8I9..."
              />
            </FormField>

            <FormField label="Step-Up Confirmation Password" description="Required for privileged technical configuration changes if session has expired">
              <input
                type="password"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text"
                value={driveForm.confirmPassword}
                onChange={(e) => setDriveForm({ ...driveForm, confirmPassword: e.target.value })}
                placeholder="Admin password to confirm"
              />
            </FormField>
          </div>
        </Modal>
      )}

      {/* 5. Google Drive Disconnect Confirmation Modal */}
      {driveDisconnectModalOpen && (
        <ConfirmationModal
          open={driveDisconnectModalOpen}
          title="Disconnect Google Drive Account"
          description="Are you sure you want to disconnect Google Drive? This will revoke and remove stored OAuth authorization tokens. Handoff operations requiring Google Drive will be suspended until re-authorized."
          confirmLabel="Disconnect"
          cancelLabel="Cancel"
          isDestructive={true}
          loading={disconnectingDrive}
          onConfirm={handleConfirmDisconnectDrive}
          onClose={() => setDriveDisconnectModalOpen(false)}
        />
      )}

      {/* 6. Universal Reset Override Confirmation Modal */}
      {resetOverrideKey && (
        <Modal
          open={Boolean(resetOverrideKey)}
          title="Reset Setting Override"
          description={`Remove database override for '${resetOverrideKey}' and revert to deployment configuration fallback.`}
          size="sm"
          onClose={() => { setResetOverrideKey(null); setResetConfirmPassword(''); }}
          footer={(
            <div className="flex justify-end gap-3">
              <Button variant="outline" onClick={() => { setResetOverrideKey(null); setResetConfirmPassword(''); }} disabled={resettingOverride}>
                Cancel
              </Button>
              <Button variant="danger" onClick={handleConfirmResetOverride} loading={resettingOverride}>
                Reset Override
              </Button>
            </div>
          )}
        >
          <div className="space-y-4">
            <div className="flex items-start gap-3 rounded-md bg-amber-50 dark:bg-amber-950/40 p-3 text-amber-800 dark:text-amber-300 text-sm">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
              <p>This will delete the database-managed override and immediately revert to the deployment environment fallback.</p>
            </div>

            <FormField
              label="Confirmation Password"
              description="Enter your administrator password to authenticate this action"
            >
              <input
                type="password"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-brand-text"
                value={resetConfirmPassword}
                onChange={(e) => setResetConfirmPassword(e.target.value)}
                placeholder="Admin password"
              />
            </FormField>
          </div>
        </Modal>
      )}
    </div>
  )
}
