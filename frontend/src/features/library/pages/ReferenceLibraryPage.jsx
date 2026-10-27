import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  BookOpen,
  ChevronDown,
  ChevronUp,
  Download,
  ExternalLink,
  FileSpreadsheet,
  FileText,
  FilterX,
  Layers,
  MoreHorizontal,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  ShieldCheck,
  Star,
  Trash2,
  Upload,
} from 'lucide-react'
import {
  Button,
  ConfirmationModal,
  DataTable,
  FeedbackToast,
  FormField,
  GlassPanel,
  InlineAlert,
  Modal,
  PageHeader,
  StyledSelect,
} from '../../../components'
import { getUserRole, isInternalUser } from '../../../lib/auth'
import { fileTransferErrorMessage } from '../../../lib/fileTransfer'
import { formatMachineLabel } from '../../../lib/formatters'
import { apiErrorMessage } from '../../../lib/formErrors'
import * as libraryApi from '../api/libraryApi'
import * as programApi from '../../programs/api/programApi'
import ReferenceCreateModal from '../components/ReferenceCreateModal'
import FormatProfileHelperPanel from '../components/FormatProfileHelperPanel'
import PolicyReferencesTable from '../components/PolicyReferencesTable'
import TemplateEditModal from '../components/TemplateEditModal'
import TemplateUploadModal from '../components/TemplateUploadModal'
import { REFERENCE_TYPE_META } from '../components/referenceTypeMeta'

// Six view-only Reference_Types (every value except 'template').
const VIEW_ONLY_TYPE_OPTIONS = Object.entries(REFERENCE_TYPE_META)
  .filter(([value]) => value !== 'template')
  .map(([value, meta]) => ({ value, label: meta.label }))

const DEFAULT_PER_PAGE = 20

const CHECKER_TYPE_OPTIONS = [
  { value: 'official_template', label: 'Official Template' },
  { value: 'accepted_sample', label: 'Accepted Sample' },
  { value: 'returned_sample', label: 'Returned Sample' },
  { value: 'guideline_basis', label: 'Guideline Basis' },
  { value: 'logo_letterhead_reference', label: 'Logo/Letterhead' },
  { value: 'validation_checklist', label: 'Validation Checklist' },
]

const CHECKER_USE_HELPERS = {
  official_template: 'Enforces exact headings, tables, and signature placement. Highest strictness.',
  accepted_sample: 'Matches against a prior approved submission. More flexible layout matching.',
  returned_sample: 'Flags known defect patterns from a rejected submission. No layout checks.',
  guideline_basis: 'Checks policy terms and context only — skips layout/geometry checks.',
  logo_letterhead_reference: 'Validates official seals, letterheads, and crests.',
  validation_checklist: 'Standard structured checklist matching.',
}

const CHECKER_STATUS_OPTIONS = [
  { value: 'draft', label: 'Draft' },
  { value: 'active', label: 'Active' },
  { value: 'superseded', label: 'Superseded' },
  { value: 'archived', label: 'Archived' },
]

const REQUIREMENT_TYPE_OPTIONS = [
  { value: '', label: 'Any type' },
  { value: 'document', label: 'Document' },
  { value: 'certificate', label: 'Certificate' },
  { value: 'resolution', label: 'Resolution' },
  { value: 'financial', label: 'Financial' },
  { value: 'engineering', label: 'Engineering' },
  { value: 'inspection', label: 'Inspection' },
  { value: 'other', label: 'Other' },
]

function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('en-PH', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function parseListString(value) {
  if (Array.isArray(value)) return value.filter(Boolean).map(String)
  if (typeof value === 'string' && value.trim()) {
    return value.split(',').map((s) => s.trim()).filter(Boolean)
  }
  return []
}

/**
 * RowActionMenu provides a unified overflow dropdown (⋯) for non-primary actions.
 */
function RowActionMenu({ actions = [], inline = false, label = 'More actions' }) {
  const [open, setOpen] = useState(false)
  const menuRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined

    const handlePointerDown = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setOpen(false)
      }
    }

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setOpen(false)
      }
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  if (actions.length === 0) return null

  return (
    <div className="relative inline-block text-left" ref={menuRef}>
      <button
        type="button"
        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-brand-border bg-brand-surface-solid text-brand-text-muted transition-colors hover:bg-brand-surface hover:text-brand-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/30"
        aria-label={label}
        aria-haspopup="true"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation()
          setOpen((prev) => !prev)
        }}
      >
        <MoreHorizontal className="h-4 w-4" strokeWidth={1.7} />
      </button>

      {open && (
        <div
          role="menu"
          className={`${inline ? 'mt-2 w-52 max-w-full' : 'absolute right-0 z-30 mt-1.5 w-52 origin-top-right'} rounded-lg border border-brand-border bg-brand-surface-solid py-1 shadow-lg ring-1 ring-black/5 dark:ring-white/10`}
        >
          {actions.map((action, index) => {
            const Icon = action.icon
            return (
              <button
                key={index}
                type="button"
                role="menuitem"
                className={`flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/30 ${
                  action.isDestructive
                    ? 'text-red-700 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-950/40'
                    : 'text-brand-text hover:bg-brand-surface'
                }`}
                onClick={(event) => {
                  event.stopPropagation()
                  setOpen(false)
                  action.onClick()
                }}
              >
                {Icon && (
                  <Icon
                    className={`h-4 w-4 shrink-0 ${
                      action.isDestructive
                        ? 'text-red-600 dark:text-red-400'
                        : 'text-brand-text-muted'
                    }`}
                    strokeWidth={1.5}
                  />
                )}
                <span>{action.label}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

/**
 * CheckerProfileModal: Enhanced modal with plain-language helper descriptions,
 * sentence-case labels, and dual-mode (simple + advanced collapsible JSON) editing.
 */
function CheckerProfileModal({ open, reference, onClose, onSuccess }) {
  const [form, setForm] = useState({
    checker_reference_type: 'guideline_basis',
    status: 'draft',
    fiscal_year: '',
    requirement_name: '',
    requirement_type: '',
    phase_name: '',
    project_kind: '',
    profile_metadata: '',
  })
  const [showAdvancedJson, setShowAdvancedJson] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open || !reference) return
    const profile = reference.checker_profile || {}
    setForm({
      checker_reference_type: profile.checker_reference_type || 'guideline_basis',
      status: profile.status || 'draft',
      fiscal_year: profile.fiscal_year ? String(profile.fiscal_year) : '',
      requirement_name: profile.requirement_name || '',
      requirement_type: profile.requirement_type || '',
      phase_name: profile.phase_name || '',
      project_kind: profile.project_kind || '',
      profile_metadata: JSON.stringify(profile.profile_metadata || {}, null, 2),
    })
    setShowAdvancedJson(false)
    setError('')
  }, [open, reference])

  const updateField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }))
  }

  // Parse current metadata JSON safely for simple fields
  const parsedMetadata = useMemo(() => {
    try {
      const parsed = JSON.parse(form.profile_metadata || '{}')
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
    } catch {
      return {}
    }
  }, [form.profile_metadata])

  if (!reference) return null

  const updateMetadataProperty = (key, value) => {
    try {
      const current = JSON.parse(form.profile_metadata || '{}')
      if (value === undefined || value === '' || (Array.isArray(value) && value.length === 0)) {
        delete current[key]
      } else {
        current[key] = value
      }
      updateField('profile_metadata', JSON.stringify(current, null, 2))
    } catch {
      // If raw JSON was invalid, don't overwrite
    }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      let metadata = {}
      if (form.profile_metadata.trim()) {
        metadata = JSON.parse(form.profile_metadata)
        if (!metadata || Array.isArray(metadata) || typeof metadata !== 'object') {
          throw new Error('Metadata must be a JSON object.')
        }
      }
      const payload = {
        checker_reference_type: form.checker_reference_type,
        status: form.status,
        fiscal_year: form.fiscal_year ? Number(form.fiscal_year) : null,
        requirement_name: form.requirement_name || null,
        requirement_type: form.requirement_type || null,
        phase_name: form.phase_name || null,
        project_kind: form.project_kind || null,
        profile_metadata: metadata,
      }
      if (reference.program_id) {
        payload.program_id = reference.program_id
      }
      const response = await libraryApi.updateReferenceCheckerProfile(reference.reference_uri, payload)
      onSuccess(response)
    } catch (requestError) {
      setError(
        requestError instanceof SyntaxError || requestError.message === 'Metadata must be a JSON object.'
          ? requestError.message || 'Metadata must be valid JSON.'
          : apiErrorMessage(requestError, 'Unable to save checker reference profile.'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  const helperText = CHECKER_USE_HELPERS[form.checker_reference_type] || ''

  return (
    <Modal
      open={open}
      title="Checker reference profile"
      description={reference.title}
      onClose={onClose}
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <InlineAlert type="error" onDismiss={() => setError('')}>
          {error}
        </InlineAlert>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <FormField id="checker-reference-type" label="Checker use">
              <StyledSelect
                id="checker-reference-type"
                value={form.checker_reference_type}
                onChange={(event) => updateField('checker_reference_type', event.target.value)}
                options={CHECKER_TYPE_OPTIONS}
              />
            </FormField>
            {helperText && (
              <p className="mt-1 text-xs text-brand-text-muted italic">{helperText}</p>
            )}
          </div>

          <FormField id="checker-status" label="Status">
            <StyledSelect
              id="checker-status"
              value={form.status}
              onChange={(event) => updateField('status', event.target.value)}
              options={CHECKER_STATUS_OPTIONS}
            />
          </FormField>

          <FormField id="checker-fiscal-year" label="Funding year">
            <input
              id="checker-fiscal-year"
              type="number"
              min="2000"
              max="2100"
              className="input-field"
              value={form.fiscal_year}
              onChange={(event) => updateField('fiscal_year', event.target.value)}
              placeholder="2026"
            />
          </FormField>

          <FormField id="checker-requirement-type" label="Requirement type">
            <StyledSelect
              id="checker-requirement-type"
              value={form.requirement_type}
              onChange={(event) => updateField('requirement_type', event.target.value)}
              options={REQUIREMENT_TYPE_OPTIONS}
            />
          </FormField>

          <FormField id="checker-requirement-name" label="Requirement name">
            <input
              id="checker-requirement-name"
              className="input-field"
              value={form.requirement_name}
              onChange={(event) => updateField('requirement_name', event.target.value)}
              placeholder="Detailed Engineering Design"
            />
          </FormField>

          <FormField id="checker-phase-name" label="Phase">
            <input
              id="checker-phase-name"
              className="input-field"
              value={form.phase_name}
              onChange={(event) => updateField('phase_name', event.target.value)}
              placeholder="Pre-Implementation"
            />
          </FormField>
        </div>

        <FormField id="checker-project-kind" label="Project kind">
          <input
            id="checker-project-kind"
            className="input-field"
            value={form.project_kind}
            onChange={(event) => updateField('project_kind', event.target.value)}
            placeholder="Leave blank for all project kinds"
          />
        </FormField>

        {/* Simple Metadata Fields */}
        <div className="rounded-lg border border-brand-border bg-brand-surface p-4 space-y-3">
          <p className="text-xs font-semibold text-brand-text">
            Validation Rules & Keywords
          </p>

          <FormField
            id="checker-required-terms"
            label="Required terms / keywords (comma-separated)"
            hint="Keywords the checker requires to find in the document."
          >
            <input
              id="checker-required-terms"
              className="input-field"
              placeholder="e.g. Approved Budget for the Contract, Certified True Copy"
              value={(parsedMetadata.required_terms || []).join(', ')}
              onChange={(event) =>
                updateMetadataProperty('required_terms', parseListString(event.target.value))
              }
            />
          </FormField>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormField
              id="checker-min-chars"
              label="Minimum readable characters"
              hint="Minimum OCR characters required for validation."
            >
              <input
                id="checker-min-chars"
                type="number"
                min="0"
                className="input-field"
                placeholder="20"
                value={parsedMetadata.minimum_text_chars ?? ''}
                onChange={(event) =>
                  updateMetadataProperty(
                    'minimum_text_chars',
                    event.target.value ? Number(event.target.value) : undefined,
                  )
                }
              />
            </FormField>

            <FormField
              id="checker-allowed-ext"
              label="Allowed file extensions"
              hint="e.g. pdf, docx, jpg"
            >
              <input
                id="checker-allowed-ext"
                className="input-field"
                placeholder="pdf, docx"
                value={(parsedMetadata.allowed_extensions || []).join(', ')}
                onChange={(event) =>
                  updateMetadataProperty('allowed_extensions', parseListString(event.target.value))
                }
              />
            </FormField>
          </div>
        </div>

        {/* Collapsible Advanced JSON & Format Profile */}
        <div className="rounded-lg border border-brand-border bg-brand-surface-solid overflow-hidden">
          <button
            type="button"
            className="flex w-full items-center justify-between px-4 py-3 text-left text-xs font-semibold text-brand-text hover:bg-brand-surface transition-colors focus-visible:outline-none"
            onClick={() => setShowAdvancedJson((prev) => !prev)}
          >
            <span>Advanced format profile & raw JSON metadata</span>
            {showAdvancedJson ? (
              <ChevronUp className="h-4 w-4 text-brand-text-muted" />
            ) : (
              <ChevronDown className="h-4 w-4 text-brand-text-muted" />
            )}
          </button>

          {showAdvancedJson && (
            <div className="border-t border-brand-border p-4 space-y-3">
              <FormField
                id="checker-profile-metadata"
                label="Raw JSON metadata"
                hint="Hand-author bounding boxes, signature zones, and strictness rules if needed."
              >
                <textarea
                  id="checker-profile-metadata"
                  className="input-field min-h-[120px] font-mono text-xs"
                  value={form.profile_metadata}
                  onChange={(event) => updateField('profile_metadata', event.target.value)}
                />
              </FormField>

              <FormatProfileHelperPanel
                metadataText={form.profile_metadata}
                onMetadataTextChange={(value) => updateField('profile_metadata', value)}
              />
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" icon={ShieldCheck} loading={submitting}>
            Save Checker Profile
          </Button>
        </div>
      </form>
    </Modal>
  )
}

export default function ReferenceLibraryPage() {
  const role = getUserRole()
  const isAdminUser = role === 'admin'
  const isStaffUser = role === 'staff'
  const isFieldOfficerUser = role === 'field_officer'
  const canManageViewOnly = isAdminUser || isStaffUser
  const canManageTemplates = isAdminUser

  const [searchParams, setSearchParams] = useSearchParams()

  // Tab State: 'references' (Policy References) vs 'templates' (Document Templates)
  const initialTab = useMemo(() => {
    if (isFieldOfficerUser) return 'references'
    const paramTab = searchParams.get('tab')
    const refType = searchParams.get('reference_type')
    if (paramTab === 'templates' || refType === 'template') return 'templates'
    return 'references'
  }, [searchParams, isFieldOfficerUser])

  const [activeTab, setActiveTab] = useState(initialTab)
  const [references, setReferences] = useState([])
  const [meta, setMeta] = useState({ page: 1, per_page: DEFAULT_PER_PAGE, total: 0, pages: 1 })
  const [page, setPage] = useState(1)
  const [programs, setPrograms] = useState([])
  const [templateSubtypes, setTemplateSubtypes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  // Filters
  const [refFilters, setRefFilters] = useState({
    search: searchParams.get('search') || '',
    program_id: searchParams.get('program_id') || '',
    reference_type:
      REFERENCE_TYPE_META[searchParams.get('reference_type')] &&
      searchParams.get('reference_type') !== 'template'
        ? searchParams.get('reference_type')
        : '',
    is_current:
      searchParams.get('is_current') === 'true' || searchParams.get('is_current') === 'false'
        ? searchParams.get('is_current')
        : '',
  })

  const [tplFilters, setTplFilters] = useState({
    search: searchParams.get('search') || '',
    template_subtype: searchParams.get('template_subtype') || '',
    is_default:
      searchParams.get('is_default') === 'true' || searchParams.get('is_default') === 'false'
        ? searchParams.get('is_default')
        : '',
  })

  // Modal States
  const [createOpen, setCreateOpen] = useState(false)
  const [editingReference, setEditingReference] = useState(null)
  const [templateUploadOpen, setTemplateUploadOpen] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState(null)
  const [checkerReference, setCheckerReference] = useState(null)
  const [pendingDelete, setPendingDelete] = useState(null)
  const [deleteSubmitting, setDeleteSubmitting] = useState(false)
  const [actionInFlight, setActionInFlight] = useState('')

  // Keep activeTab synced with URL query or role change
  useEffect(() => {
    if (isFieldOfficerUser && activeTab !== 'references') {
      setActiveTab('references')
    }
  }, [isFieldOfficerUser, activeTab])

  // Load programs & template subtypes once on mount
  useEffect(() => {
    let cancelled = false
    programApi
      .listPrograms({ per_page: 100 })
      .then((response) => {
        if (cancelled) return
        setPrograms(response.data || [])
      })
      .catch(() => {
        if (cancelled) return
        setPrograms([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (isFieldOfficerUser) return undefined
    let cancelled = false
    libraryApi
      .listTemplateSubtypes()
      .then((response) => {
        if (cancelled) return
        setTemplateSubtypes(response.data || [])
      })
      .catch(() => {
        if (cancelled) return
        setTemplateSubtypes([])
      })
    return () => {
      cancelled = true
    }
  }, [isFieldOfficerUser])

  // Tab switcher
  const handleTabChange = (nextTab) => {
    if (nextTab === activeTab) return
    setActiveTab(nextTab)
    setPage(1)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('tab', nextTab)
      if (nextTab === 'templates') {
        next.set('reference_type', 'template')
        next.delete('program_id')
        next.delete('is_current')
      } else {
        next.delete('reference_type')
        next.delete('template_subtype')
        next.delete('is_default')
      }
      return next
    })
  }

  // Build API query payload based on active tab
  const filtersForRequest = useMemo(() => {
    const params = { page, per_page: DEFAULT_PER_PAGE }
    if (activeTab === 'references') {
      params.origin = 'guideline'
      if (refFilters.search) params.search = refFilters.search
      if (refFilters.program_id) params.program_id = Number(refFilters.program_id)
      if (refFilters.reference_type) params.reference_type = refFilters.reference_type
      if (refFilters.is_current) params.is_current = refFilters.is_current === 'true'
    } else {
      params.origin = 'template'
      params.reference_type = 'template'
      if (tplFilters.search) params.search = tplFilters.search
      if (tplFilters.template_subtype) params.template_subtype = tplFilters.template_subtype
      if (tplFilters.is_default) params.is_default = tplFilters.is_default === 'true'
    }
    return params
  }, [activeTab, page, refFilters, tplFilters])

  const loadReferences = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await libraryApi.listReferences(filtersForRequest)
      setReferences(response.data || [])
      const responseMeta = response.meta || {}
      setMeta({
        page: responseMeta.page ?? page,
        per_page: responseMeta.per_page ?? DEFAULT_PER_PAGE,
        total: responseMeta.total ?? 0,
        pages: responseMeta.pages ?? 1,
      })
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load the Reference Library.'))
    } finally {
      setLoading(false)
    }
  }, [filtersForRequest, page])

  useEffect(() => {
    loadReferences()
  }, [loadReferences])

  // Defensive client filter guaranteeing strict tab segregation
  const displayedReferences = useMemo(() => {
    if (activeTab === 'references') {
      return references.filter((r) => r.origin !== 'template' && r.reference_type !== 'template')
    }
    return references.filter((r) => r.origin === 'template' || r.reference_type === 'template')
  }, [activeTab, references])

  // Filter option sets for StyledSelect
  const refTypeOptions = useMemo(
    () => [{ value: '', label: 'All Types' }, ...VIEW_ONLY_TYPE_OPTIONS],
    [],
  )

  const programOptions = useMemo(
    () => [
      { value: '', label: 'All Programs' },
      ...programs.map((p) => ({ value: String(p.id), label: p.name })),
    ],
    [programs],
  )

  const refStatusOptions = useMemo(
    () => [
      { value: '', label: 'All Statuses' },
      { value: 'true', label: 'Current Only' },
      { value: 'false', label: 'Historical Only' },
    ],
    [],
  )

  const tplSubtypeOptions = useMemo(
    () => [
      { value: '', label: 'All Subtypes' },
      ...templateSubtypes.map((s) => ({ value: s.template_subtype, label: s.label })),
    ],
    [templateSubtypes],
  )

  const tplStatusOptions = useMemo(
    () => [
      { value: '', label: 'All Statuses' },
      { value: 'true', label: 'Default Only' },
      { value: 'false', label: 'Available Only' },
    ],
    [],
  )

  const updateRefFilter = (field, value) => {
    setRefFilters((current) => ({ ...current, [field]: value }))
    setPage(1)
  }

  const updateTplFilter = (field, value) => {
    setTplFilters((current) => ({ ...current, [field]: value }))
    setPage(1)
  }

  const resetRefFilters = () => {
    setRefFilters({ search: '', program_id: '', reference_type: '', is_current: '' })
    setPage(1)
  }

  const resetTplFilters = () => {
    setTplFilters({ search: '', template_subtype: '', is_default: '' })
    setPage(1)
  }

  const hasActiveRefFilters = Boolean(
    refFilters.search || refFilters.program_id || refFilters.reference_type || refFilters.is_current,
  )
  const hasActiveTplFilters = Boolean(
    tplFilters.search || tplFilters.template_subtype || tplFilters.is_default,
  )

  const refresh = () => {
    loadReferences()
  }

  const openCreateView = () => {
    setEditingReference(null)
    setCreateOpen(true)
  }

  const openEditView = (reference) => {
    setEditingReference(reference)
    setCreateOpen(true)
  }

  const closeCreate = () => {
    setCreateOpen(false)
    setEditingReference(null)
  }

  const handleCreateSuccess = (response) => {
    setMessage(response?.message || 'Reference saved successfully.')
    closeCreate()
    loadReferences()
  }

  const openTemplateUpload = () => {
    setTemplateUploadOpen(true)
  }

  const handleTemplateUploadSuccess = (response) => {
    setMessage(response?.message || 'Template uploaded successfully.')
    setTemplateUploadOpen(false)
    loadReferences()
  }

  const openTemplateEdit = (reference) => {
    setEditingTemplate(reference)
  }

  const handleTemplateEditSuccess = (response) => {
    setMessage(response?.message || 'Template updated successfully.')
    setEditingTemplate(null)
    loadReferences()
  }

  const openCheckerProfile = (reference) => {
    setCheckerReference(reference)
  }

  const handleCheckerProfileSuccess = (response) => {
    setMessage(response?.message || 'Checker reference profile saved.')
    setCheckerReference(null)
    loadReferences()
  }

  const requestDelete = (reference) => {
    setPendingDelete(reference)
  }

  const cancelDelete = () => {
    setPendingDelete(null)
  }

  const handleConfirmDelete = async () => {
    if (!pendingDelete) return
    setDeleteSubmitting(true)
    setError('')
    try {
      const response = await libraryApi.deleteReference(pendingDelete.reference_uri)
      setMessage(response?.message || 'Reference deleted successfully.')
      setPendingDelete(null)
      if (references.length === 1 && page > 1) {
        setPage((current) => current - 1)
      } else {
        loadReferences()
      }
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to delete this reference.'))
    } finally {
      setDeleteSubmitting(false)
    }
  }

  const handleDownload = async (reference) => {
    setActionInFlight(reference.reference_uri)
    setError('')
    try {
      const response = await libraryApi.downloadReferenceFile(reference.reference_uri)
      const blob = new Blob([response.data], {
        type: response.headers['content-type'] || 'application/octet-stream',
      })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = reference.file_name || reference.title || 'reference'
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (requestError) {
      setError(await fileTransferErrorMessage(requestError, 'Unable to download the reference file.'))
    } finally {
      setActionInFlight('')
    }
  }

  const handleSetTemplateDefault = async (reference) => {
    if (!canManageTemplates) return
    setActionInFlight(reference.reference_uri)
    setError('')
    try {
      const payload = new FormData()
      payload.append('reference_type', 'template')
      payload.append('is_default', 'true')
      const response = await libraryApi.updateReference(reference.reference_uri, payload)
      setMessage(response?.message || 'Default template updated.')
      loadReferences()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to set this template as the default.'))
    } finally {
      setActionInFlight('')
    }
  }

  if (!isInternalUser()) {
    return (
      <GlassPanel>
        <h1 className="page-title mb-2">Reference Library</h1>
        <p className="text-sm text-brand-text-muted">
          The Reference Library is only available to internal users.
        </p>
      </GlassPanel>
    )
  }

  // Cell Renderers
  const renderTplStatusCell = (row) => {
    if (row.is_default) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-800 dark:border-amber-700/50 dark:bg-amber-950/40 dark:text-amber-300">
          <Star className="h-3 w-3 fill-amber-500 text-amber-500" strokeWidth={1.5} />
          Default
        </span>
      )
    }
    return <span className="status-badge status-badge-neutral">Available</span>
  }

  const renderFileCell = (row) => {
    if (row.file_kind === 'upload') {
      return (
        <button
          type="button"
          className="action-link text-xs"
          onClick={() => handleDownload(row)}
          disabled={actionInFlight === row.reference_uri}
        >
          <Download className="h-3.5 w-3.5" strokeWidth={1.5} />
          <span>{row.file_name || 'Download'}</span>
        </button>
      )
    }
    if (row.file_kind === 'external_url') {
      return (
        <a
          className="action-link text-xs"
          href={row.file_path}
          target="_blank"
          rel="noopener noreferrer"
        >
          <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.5} />
          <span>Open link</span>
        </a>
      )
    }
    return <span className="text-brand-text-muted">—</span>
  }

  // Row Actions: References Tab
  const renderRefActionsCell = (row) => {
    if (isFieldOfficerUser) return null

    const canEdit = canManageViewOnly
    const canDelete = canManageViewOnly
    const canConfigureChecker = isAdminUser || isStaffUser

    const overflowActions = []
    if (canEdit) overflowActions.push({ label: 'Edit reference', icon: Pencil, onClick: () => openEditView(row) })
    if (canConfigureChecker) {
      overflowActions.push({
        label: 'Configure checker profile',
        icon: ShieldCheck,
        onClick: () => openCheckerProfile(row),
      })
    }
    if (canDelete) {
      overflowActions.push({
        label: 'Delete reference',
        icon: Trash2,
        isDestructive: true,
        onClick: () => requestDelete(row),
      })
    }

    return <RowActionMenu actions={overflowActions} inline label={`More actions: ${row.title}`} />
  }

  // Row Actions: Templates Tab
  const renderTplActionsCell = (row) => {
    if (isFieldOfficerUser) return null

    const canEdit = canManageTemplates
    const canDelete = canManageTemplates
    const canSetDefault = canManageTemplates && !row.is_default
    const canConfigureChecker = isAdminUser || isStaffUser

    const overflowActions = []
    if (canSetDefault) {
      overflowActions.push({
        label: 'Set as default template',
        icon: Star,
        onClick: () => handleSetTemplateDefault(row),
      })
    }
    if (canConfigureChecker) {
      overflowActions.push({
        label: 'Configure checker profile',
        icon: ShieldCheck,
        onClick: () => openCheckerProfile(row),
      })
    }
    if (canDelete) {
      overflowActions.push({
        label: 'Delete template',
        icon: Trash2,
        isDestructive: true,
        onClick: () => requestDelete(row),
      })
    }

    return (
      <div className="flex items-center justify-end gap-1.5">
        {canEdit && (
          <Button
            size="sm"
            variant="ghost"
            icon={Pencil}
            onClick={() => openTemplateEdit(row)}
            aria-label="Edit template"
          >
            Edit
          </Button>
        )}
        <RowActionMenu actions={overflowActions} />
      </div>
    )
  }

  // Table Columns Definition
  const templateColumns = [
    {
      key: 'title',
      label: 'Template name',
      render: (row) => (
        <div>
          <div className="font-medium text-brand-text">{row.title}</div>
          {row.file_name && (
            <div className="mt-0.5 font-mono text-xs text-brand-text-muted">{row.file_name}</div>
          )}
        </div>
      ),
    },
    {
      key: 'template_subtype',
      label: 'Subtype',
      render: (row) => (
        <span className="text-xs font-medium text-brand-text">
          {row.template_subtype_label || formatMachineLabel(row.template_subtype)}
        </span>
      ),
    },
    {
      key: 'format',
      label: 'Format',
      render: () => <span className="status-badge status-badge-info">DOCX</span>,
    },
    { key: 'status', label: 'Default status', render: renderTplStatusCell },
    {
      key: 'placeholders',
      label: 'Placeholders',
      render: (row) => {
        const count = row.placeholder_fields?.length || 0
        return (
          <span className="text-xs text-brand-text-muted">
            {count > 0 ? `${count} mapped` : 'None'}
          </span>
        )
      },
    },
    {
      key: 'updated_at',
      label: 'Last updated',
      render: (row) => formatDate(row.updated_at || row.created_at),
    },
    { key: 'file', label: 'File', render: renderFileCell },
  ]

  if (!isFieldOfficerUser) {
    templateColumns.push({ key: 'actions', label: 'Actions', render: renderTplActionsCell })
  }

  // Header Contextual Action Button
  const headerActions = (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="outline" size="sm" onClick={refresh}>
        Refresh
      </Button>

      {activeTab === 'references' && canManageViewOnly && (
        <Button size="sm" icon={Plus} onClick={openCreateView}>
          Add Reference
        </Button>
      )}

      {activeTab === 'templates' && canManageTemplates && (
        <Button size="sm" icon={Upload} onClick={openTemplateUpload}>
          Upload Template
        </Button>
      )}
    </div>
  )


  return (
    <div className="space-y-4">
      <PageHeader
        title="Reference Library"
        description="Access statutory guidelines, memorandums, circulars, and standard reusable document templates."
        actions={headerActions}
      />

      <FeedbackToast type="success" message={message} onDismiss={() => setMessage('')} />
      <InlineAlert type="error" onDismiss={() => setError('')}>
        {error}
      </InlineAlert>

      {/* Tab Navigation Controls (Hidden for Field Officers) */}
      {!isFieldOfficerUser && (
        <div className="border-b border-brand-border">
          <nav className="flex space-x-4" aria-label="Reference Library views">
            <button
              type="button"
              onClick={() => handleTabChange('references')}
              className={`inline-flex items-center gap-2 border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
                activeTab === 'references'
                  ? 'border-brand-primary text-brand-primary dark:border-blue-400 dark:text-blue-300'
                  : 'border-transparent text-brand-text-muted hover:border-brand-border hover:text-brand-text'
              }`}
              aria-current={activeTab === 'references' ? 'page' : undefined}
            >
              <BookOpen className="h-4 w-4" strokeWidth={1.7} />
              <span>Policy References</span>
            </button>
            <button
              type="button"
              onClick={() => handleTabChange('templates')}
              className={`inline-flex items-center gap-2 border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
                activeTab === 'templates'
                  ? 'border-brand-primary text-brand-primary dark:border-blue-400 dark:text-blue-300'
                  : 'border-transparent text-brand-text-muted hover:border-brand-border hover:text-brand-text'
              }`}
              aria-current={activeTab === 'templates' ? 'page' : undefined}
            >
              <FileSpreadsheet className="h-4 w-4" strokeWidth={1.7} />
              <span>Document Templates</span>
            </button>
          </nav>
        </div>
      )}

      {/* Lightweight Summary Bar (Fixes page-slice stat cards bug) */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-brand-text-muted">
        <div>
          {activeTab === 'references' ? (
            <span>
              Showing <strong className="font-semibold text-brand-text">{meta.total}</strong> policy{' '}
              {meta.total === 1 ? 'reference' : 'references'}
              {refFilters.search && ` matching "${refFilters.search}"`}
              {refFilters.program_id &&
                ` for ${programs.find((p) => p.id === Number(refFilters.program_id))?.name || 'Program'}`}
              {refFilters.reference_type &&
                ` · Type: ${REFERENCE_TYPE_META[refFilters.reference_type]?.label || refFilters.reference_type}`}
              {refFilters.is_current === 'true' && ' · Current only'}
              {refFilters.is_current === 'false' && ' · Historical only'}
            </span>
          ) : (
            <span>
              Showing <strong className="font-semibold text-brand-text">{meta.total}</strong> document{' '}
              {meta.total === 1 ? 'template' : 'templates'}
              {tplFilters.search && ` matching "${tplFilters.search}"`}
              {tplFilters.template_subtype &&
                ` for ${templateSubtypes.find((s) => s.template_subtype === tplFilters.template_subtype)?.label || tplFilters.template_subtype}`}
              {tplFilters.is_default === 'true' && ' · Default only'}
              {tplFilters.is_default === 'false' && ' · Available only'}
            </span>
          )}
        </div>
      </div>

      {/* Filter Bars with Custom StyledSelect Controls */}
      {activeTab === 'references' ? (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-brand-border bg-brand-surface-solid p-3 shadow-sm">
          <div className="relative min-w-[240px] flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              id="library-search"
              className="input-field pl-9 text-xs"
              placeholder="Search by title, reference no., or issuing body..."
              value={refFilters.search}
              onChange={(event) => updateRefFilter('search', event.target.value)}
              aria-label="Search references"
            />
          </div>

          <div className="w-auto min-w-[150px]">
            <StyledSelect
              id="library-type-filter"
              size="sm"
              value={refFilters.reference_type}
              onChange={(event) => updateRefFilter('reference_type', event.target.value)}
              options={refTypeOptions}
              placeholder="All Types"
              aria-label="Filter by type"
            />
          </div>

          <div className="w-auto min-w-[160px]">
            <StyledSelect
              id="library-program-filter"
              size="sm"
              searchable
              value={refFilters.program_id}
              onChange={(event) => updateRefFilter('program_id', event.target.value)}
              options={programOptions}
              placeholder="All Programs"
              aria-label="Filter by program"
            />
          </div>

          <div className="w-auto min-w-[140px]">
            <StyledSelect
              id="library-status-filter"
              size="sm"
              value={refFilters.is_current}
              onChange={(event) => updateRefFilter('is_current', event.target.value)}
              options={refStatusOptions}
              placeholder="All Statuses"
              aria-label="Filter by status"
            />
          </div>

          {hasActiveRefFilters && (
            <Button
              variant="ghost"
              size="sm"
              icon={FilterX}
              onClick={resetRefFilters}
              aria-label="Clear filters"
            >
              Clear
            </Button>
          )}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-brand-border bg-brand-surface-solid p-3 shadow-sm">
          <div className="relative min-w-[240px] flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              id="template-search"
              className="input-field pl-9 text-xs"
              placeholder="Search templates by label or file name..."
              value={tplFilters.search}
              onChange={(event) => updateTplFilter('search', event.target.value)}
              aria-label="Search templates"
            />
          </div>

          <div className="w-auto min-w-[180px]">
            <StyledSelect
              id="library-template-subtype-filter"
              size="sm"
              searchable
              value={tplFilters.template_subtype}
              onChange={(event) => updateTplFilter('template_subtype', event.target.value)}
              options={tplSubtypeOptions}
              placeholder="All Subtypes"
              aria-label="Filter by template subtype"
            />
          </div>

          <div className="w-auto min-w-[140px]">
            <StyledSelect
              id="template-status-filter"
              size="sm"
              value={tplFilters.is_default}
              onChange={(event) => updateTplFilter('is_default', event.target.value)}
              options={tplStatusOptions}
              placeholder="All Statuses"
              aria-label="Filter by default status"
            />
          </div>

          {hasActiveTplFilters && (
            <Button
              variant="ghost"
              size="sm"
              icon={FilterX}
              onClick={resetTplFilters}
              aria-label="Clear filters"
            >
              Clear
            </Button>
          )}
        </div>
      )}

      {/* Main Data Table */}
      <GlassPanel noPadding>
        {activeTab === 'references' ? <PolicyReferencesTable
          references={displayedReferences}
          programs={programs}
          loading={loading}
          actionInFlight={actionInFlight}
          onDownload={handleDownload}
          renderManagement={renderRefActionsCell}
        /> : <DataTable
          columns={templateColumns}
          data={displayedReferences}
          keyField="reference_uri"
          isLoading={loading}
          emptyMessage={
            activeTab === 'references'
              ? 'No policy references match the current filters.'
              : 'No document templates match the current filters.'
          }
          caption={activeTab === 'references' ? 'Policy References' : 'Document Templates'}
          hidePagination
          density="compact"
        />}

        {meta.pages > 1 && (
          <div className="flex items-center justify-between gap-3 border-t border-brand-border bg-brand-surface px-4 py-3">
            <span className="text-xs text-brand-text-muted">
              Showing page {meta.page} of {meta.pages} ({meta.total} total)
            </span>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={page <= 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
              >
                Previous
              </Button>
              <span className="text-xs text-brand-text-muted">
                Page {meta.page} of {meta.pages}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={page >= meta.pages}
                onClick={() => setPage((current) => Math.min(meta.pages, current + 1))}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </GlassPanel>

      {/* Modals */}
      <ReferenceCreateModal
        open={createOpen}
        editingReference={editingReference}
        onClose={closeCreate}
        onSuccess={handleCreateSuccess}
        defaultReferenceType={
          refFilters.reference_type && refFilters.reference_type !== 'template'
            ? refFilters.reference_type
            : undefined
        }
      />

      <TemplateUploadModal
        open={templateUploadOpen}
        onClose={() => setTemplateUploadOpen(false)}
        onSuccess={handleTemplateUploadSuccess}
      />

      <TemplateEditModal
        open={Boolean(editingTemplate)}
        reference={editingTemplate}
        onClose={() => setEditingTemplate(null)}
        onSuccess={handleTemplateEditSuccess}
      />

      <CheckerProfileModal
        open={Boolean(checkerReference)}
        reference={checkerReference}
        onClose={() => setCheckerReference(null)}
        onSuccess={handleCheckerProfileSuccess}
      />

      <ConfirmationModal
        open={Boolean(pendingDelete)}
        title={pendingDelete?.reference_type === 'template' ? 'Delete template' : 'Delete reference'}
        description={
          pendingDelete
            ? `This will permanently remove "${pendingDelete.title}" from the Reference Library.${
                pendingDelete.reference_type === 'template' && pendingDelete.is_default
                  ? ' It is currently the default template for its subtype; the next available template will be promoted.'
                  : ''
              }`
            : ''
        }
        confirmLabel={pendingDelete?.reference_type === 'template' ? 'Delete template' : 'Delete reference'}
        onConfirm={handleConfirmDelete}
        onClose={cancelDelete}
        loading={deleteSubmitting}
        isDestructive
      />
    </div>
  )
}
