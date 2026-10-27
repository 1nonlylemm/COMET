import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  CheckCircle2,
  Clock,
  Download,
  Eye,
  Inbox,
  Search,
  ShieldCheck,
  Upload,
  XCircle,
} from 'lucide-react'
import { Button, FeedbackToast, GlassPanel, InlineAlert, KpiCard, Modal } from '../../../components'
import { isFieldOfficer, isAdmin } from '../../../lib/auth'
import { fileTransferErrorMessage } from '../../../lib/fileTransfer'
import { formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import { AiRewriteControl } from '../../ai/components/AiRewriteControl'
import { AnnotatedDocumentPreview } from '../components/AnnotatedDocumentPreview'
import { ComplianceScorecard } from '../components/ComplianceScorecard'
import { MatcherReviewNotice } from '../components/MatcherReviewNotice.jsx'
import RequirementReviewModal from '../components/RequirementReviewModal/index.jsx'
import {
  ComplianceSummary,
  StatusBadge,
} from '../lib/intakeComponents.jsx'
import {
  fileMeta,
  formatConfidence,
  formatDate,
  matchTier,
  matchTierBadgeClass,
  phaseBadgeClass,
  reviewTask,
  scanStatusClass,
} from '../lib/intakeFormatters.js'
import * as lguApi from '../../lgus/api/lguApi'
import * as projectApi from '../../projects/api/projectApi'
import * as monitoringApi from '../../monitoring/api/monitoringApi'
import { isWorkflowNotApplicableError } from '../lib/workflowErrors'

const STATUS_FILTERS = [
  { value: '', label: 'All Statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'under_review', label: 'Under Review' },
  { value: 'compliant', label: 'Compliant' },
  { value: 'non_compliant', label: 'Non-Compliant' },
  { value: 'waived', label: 'Waived' },
]

const PHASE_FILTERS = [
  { value: '', label: 'All Phases' },
  { value: 'Pre-Implementation', label: 'Pre-Implementation' },
  { value: 'Implementation', label: 'Implementation' },
  { value: 'Completion', label: 'Completion' },
]

const DOCUMENT_UPLOAD_ACCEPT = '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.csv'

function EvidenceWarning({ candidate }) {
  if (!candidate) return null
  const alreadyReviewed = ['compliant', 'non_compliant', 'waived'].includes(candidate.status)
  if (!candidate.has_documentary_evidence && !alreadyReviewed) return null

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-300/40 dark:bg-amber-300/10 dark:text-amber-100">
      This requirement already has {candidate.has_documentary_evidence ? 'documentary evidence' : 'a reviewed status'}
      {candidate.status ? ` and is marked ${formatStatus(candidate.status)}` : ''}.
      Recording another file adds a new intake record and scan result; it does not change the requirement status by itself.
    </div>
  )
}

function summarizeLatestSubmission(submissions = []) {
  const latestSubmission = submissions[0]
  if (!latestSubmission) return null
  const files = latestSubmission.document_files || []
  const primaryFile = files[files.length - 1] || null
  return {
    id: latestSubmission.id,
    source: latestSubmission.source,
    description: latestSubmission.description,
    created_at: latestSubmission.created_at,
    document_count: files.length,
    primary_file_id: primaryFile?.id || null,
    primary_file_name: primaryFile?.file_name || null,
    primary_file_mime_type: primaryFile?.mime_type || null,
    primary_file_size_bytes: primaryFile?.file_size_bytes || null,
    latest_nlp_scan: latestSubmission.nlp_scan_results?.[0] || null,
    latest_compliance_result: latestSubmission.latest_compliance_result || latestSubmission.compliance_results?.[0] || null,
  }
}

function mergeRequirementReviewSnapshot(current = {}, fresh = {}, submissions = []) {
  const currentSnapshot = current || {}
  const freshSnapshot = fresh || {}
  const hasFreshSubmissionCount = Object.prototype.hasOwnProperty.call(freshSnapshot, 'submission_count')
  const hasFreshLatestRevision = Object.prototype.hasOwnProperty.call(freshSnapshot, 'latest_revision')
  const hasFreshLatestSubmission = Object.prototype.hasOwnProperty.call(freshSnapshot, 'latest_submission')
  const hasFreshCustomFields = Object.prototype.hasOwnProperty.call(freshSnapshot, 'custom_fields')
  const customFields = freshSnapshot.custom_fields || currentSnapshot.custom_fields || {}
  const baseSubmissionCount = Number(
    hasFreshSubmissionCount
      ? freshSnapshot.submission_count
      : currentSnapshot.submission_count ?? 0,
  )
  const submissionCount = Math.max(
    Number.isFinite(baseSubmissionCount) ? baseSubmissionCount : 0,
    submissions.length,
  )
  const hasEvidence = typeof freshSnapshot.has_documentary_evidence === 'boolean'
    ? freshSnapshot.has_documentary_evidence
    : Boolean(currentSnapshot.has_documentary_evidence)
  const summarizedLatestSubmission = summarizeLatestSubmission(submissions)

  return {
    ...currentSnapshot,
    ...freshSnapshot,
    project_name: freshSnapshot.project_name ?? currentSnapshot.project_name ?? null,
    source_project_code: freshSnapshot.source_project_code ?? currentSnapshot.source_project_code ?? null,
    fiscal_year: freshSnapshot.fiscal_year ?? currentSnapshot.fiscal_year ?? null,
    lgu_id: freshSnapshot.lgu_id ?? currentSnapshot.lgu_id ?? null,
    lgu_name: freshSnapshot.lgu_name ?? currentSnapshot.lgu_name ?? null,
    program_name: freshSnapshot.program_name ?? currentSnapshot.program_name ?? null,
    latest_revision: hasFreshLatestRevision
      ? freshSnapshot.latest_revision
      : customFields.latest_revision ?? (hasFreshCustomFields ? null : currentSnapshot.latest_revision ?? null),
    latest_submission: hasFreshLatestSubmission
      ? freshSnapshot.latest_submission
      : summarizedLatestSubmission ?? (hasFreshSubmissionCount ? null : currentSnapshot.latest_submission ?? null),
    submission_count: submissionCount,
    has_documentary_evidence: hasEvidence || submissionCount > 0,
  }
}

function suggestionScore(item) {
  if (item.status === 'pending' && !item.has_documentary_evidence) return 0
  if (item.status === 'under_review' && item.latest_revision) return 1
  if (item.status === 'under_review') return 2
  if (item.status === 'pending') return 3
  return 4
}

function sortTargetSuggestions(items = []) {
  return [...items].sort((a, b) => {
    const priority = suggestionScore(a) - suggestionScore(b)
    if (priority !== 0) return priority
    return String(a.project_name || '').localeCompare(String(b.project_name || ''))
  })
}

function groupIntakeItems(items = []) {
  const groups = []
  const lookup = new Map()

  items.forEach((item) => {
    const key = [
      item.project_id || item.project_name || 'project',
      item.lgu_id || item.lgu_name || 'lgu',
      item.phase_name || 'phase',
    ].join('|')

    if (!lookup.has(key)) {
      const group = {
        key,
        projectName: item.project_name || 'Unassigned project',
        lguName: item.lgu_name || 'No LGU assigned',
        phaseName: item.phase_name || 'No phase',
        rows: [],
      }
      lookup.set(key, group)
      groups.push(group)
    }

    lookup.get(key).rows.push(item)
  })

  return groups
}

function IntakeQueueList({
  groups,
  isLoading,
  filePreviewLoadingId,
  onOpenRequirement,
  onUploadRequirement,
  onPreviewFile,
}) {
  if (isLoading) {
    return (
      <div className="overflow-hidden">
        <div className="data-table-header hidden grid-cols-[minmax(220px,1.5fr)_130px_minmax(170px,1fr)_minmax(170px,1fr)_220px] gap-4 border-b border-brand-border px-4 py-3 text-[11px] font-semibold uppercase text-brand-text-muted lg:grid">
          <span>Requirement</span>
          <span>Status</span>
          <span>Review Task</span>
          <span>Evidence</span>
          <span className="text-right">Actions</span>
        </div>
        <div className="divide-y divide-brand-border">
          {[0, 1, 2, 3].map((index) => (
            <div key={index} className="grid gap-4 px-4 py-4 lg:grid-cols-[minmax(220px,1.5fr)_130px_minmax(170px,1fr)_minmax(170px,1fr)_220px] lg:items-center">
              <div>
                <div className="h-4 w-3/4 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
                <div className="mt-2 h-3 w-20 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
              </div>
              <div className="h-6 w-24 animate-pulse rounded-full bg-slate-200 dark:bg-slate-700" />
              <div className="space-y-2">
                <div className="h-4 w-28 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
                <div className="h-3 w-36 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
              </div>
              <div className="h-8 w-32 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
              <div className="h-10 w-36 animate-pulse rounded bg-slate-200 dark:bg-slate-700 lg:ml-auto" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (!groups.length) {
    return (
      <div className="px-4 py-10 text-center">
        <div className="text-sm font-medium text-brand-text">No documentary requirements found.</div>
        <div className="mt-1 text-sm text-brand-text-muted">Try a different search, status, phase, or LGU filter.</div>
      </div>
    )
  }

  return (
    <div className="overflow-hidden">
      <div className="data-table-header hidden grid-cols-[minmax(220px,1.5fr)_130px_minmax(170px,1fr)_minmax(170px,1fr)_220px] gap-4 border-b border-brand-border px-4 py-3 text-[11px] font-semibold uppercase text-brand-text-muted lg:grid">
        <span>Requirement</span>
        <span>Status</span>
        <span>Review Task</span>
        <span>Evidence</span>
        <span className="text-right">Actions</span>
      </div>

      {groups.map((group) => (
        <section key={group.key} className="border-b border-brand-border last:border-b-0">
          <div className="flex flex-wrap items-center gap-2 border-b border-brand-border bg-brand-surface-solid px-4 py-3">
            <span className="min-w-0 max-w-full truncate text-sm font-semibold text-brand-text">
              {group.projectName}
            </span>
            <span className="hidden text-xs text-brand-text-muted sm:inline">·</span>
            <span className="text-xs font-medium text-brand-text-muted">{group.lguName}</span>
            <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${phaseBadgeClass(group.phaseName)}`}>
              {group.phaseName}
            </span>
            <span className="inline-flex items-center rounded-full border border-brand-border bg-brand-surface px-2 py-0.5 text-xs font-medium text-brand-text-muted">
              {group.rows.length} {group.rows.length === 1 ? 'requirement' : 'requirements'}
            </span>
          </div>

          <div className="divide-y divide-brand-border">
            {group.rows.map((row) => {
              const task = reviewTask(row, isFieldOfficer())
              const isPending = (row.status || 'pending') === 'pending'
              const fileId = row.latest_submission?.primary_file_id
              const fileName = row.latest_submission?.primary_file_name
              const fileDate = row.latest_submission?.created_at
              const canPreview = Boolean(fileId && fileName)
              const fileDetails = fileName ? fileMeta(fileName) : null

              return (
                <div
                  key={row.id}
                  className="grid gap-4 px-4 py-4 transition-colors hover:bg-brand-surface-solid/70 lg:grid-cols-[minmax(220px,1.5fr)_130px_minmax(170px,1fr)_minmax(170px,1fr)_220px] lg:items-center"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-semibold leading-snug text-brand-text">
                      {row.requirement_name || 'Unnamed requirement'}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {row.annex_reference && (
                        <span className="inline-flex items-center rounded-full border border-brand-border bg-brand-surface px-2 py-0.5 text-xs font-medium text-brand-text-muted">
                          {row.annex_reference}
                        </span>
                      )}
                      {row.source_project_code && (
                        <span className="inline-flex items-center rounded-full border border-brand-border bg-brand-surface px-2 py-0.5 text-xs font-medium text-brand-text-muted">
                          {row.source_project_code}
                        </span>
                      )}
                    </div>
                  </div>

                  <div><StatusBadge row={row} /></div>

                  <div className="min-w-0">
                    <span className={badgeClassForStatus(task.tone)}>{task.label}</span>
                    <div className="mt-1 text-xs leading-snug text-brand-text-muted">{task.detail}</div>
                  </div>

                  <div className="min-w-0">
                    {canPreview ? (
                      <div className="flex min-w-0 items-center gap-2">
                        <button
                          type="button"
                          className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border transition-colors hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/35 ${fileDetails.className}`}
                          title={`Preview ${fileName}`}
                          aria-label={`Preview latest intake file: ${fileName}`}
                          onClick={() => onPreviewFile({
                            id: fileId,
                            file_name: fileName,
                            mime_type: row.latest_submission.primary_file_mime_type,
                            file_size_bytes: row.latest_submission.primary_file_size_bytes,
                            latest_compliance_result: row.latest_submission.latest_compliance_result,
                          })}
                        >
                          {filePreviewLoadingId === fileId ? (
                            <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                          ) : (
                            <fileDetails.Icon className="h-4 w-4" strokeWidth={1.7} />
                          )}
                        </button>
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-brand-text" title={fileName}>
                            {fileName}
                          </div>
                          {fileDate && (
                            <div className="text-xs text-brand-text-muted">{formatDate(fileDate)}</div>
                          )}
                          {!isFieldOfficer() && (
                            <ComplianceSummary result={row.latest_submission?.latest_compliance_result} compact />
                          )}
                        </div>
                      </div>
                    ) : row.has_documentary_evidence ? (
                      <span className={badgeClassForStatus('compliant')}>Evidence on file</span>
                    ) : (
                      <span className="text-sm text-brand-text-muted">None</span>
                    )}
                  </div>

                  <div className="flex flex-nowrap gap-2 lg:justify-end">
                    <Button
                      size="sm"
                      variant="outline"
                      icon={Eye}
                      className="min-w-[96px]"
                      onClick={() => onOpenRequirement(row)}
                    >
                      Review
                    </Button>
                    {isPending && (
                      <Button
                        size="sm"
                        icon={Upload}
                        className="min-w-[96px]"
                        onClick={() => onUploadRequirement(row)}
                      >
                        Upload
                      </Button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      ))}
    </div>
  )
}

export default function IntakeTriagePage() {
  const [items, setItems] = useState([])
  const [meta, setMeta] = useState({ total: 0, page: 1, pages: 1 })
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [phaseName, setPhaseName] = useState('')
  const [lguId, setLguId] = useState('')
  const [lguOptions, setLguOptions] = useState([])
  const [lguOptionsLoading, setLguOptionsLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [smartIntakeOpen, setSmartIntakeOpen] = useState(false)
  const [actionError, setActionError] = useState('')
  const [actionMessage, setActionMessage] = useState('')
    const [smartForm, setSmartForm] = useState({
    source: isFieldOfficer() ? 'field_upload' : 'dms_ingestion',
    description: '',
    file: null,
  })
  const [smartFileInputKey, setSmartFileInputKey] = useState(0)
  const [smartPreview, setSmartPreview] = useState(null)
  const [smartPreviewLoading, setSmartPreviewLoading] = useState(false)
  const [smartScanProgress, setSmartScanProgress] = useState(null)
  const [smartPreviewError, setSmartPreviewError] = useState('')
      const [smartSelectedRequirementId, setSmartSelectedRequirementId] = useState('')
  const [manualTargetSearch, setManualTargetSearch] = useState('')
  const [manualSuggestions, setManualSuggestions] = useState([])
  const [manualSuggestionsLoading, setManualSuggestionsLoading] = useState(false)
  const [manualSuggestionError, setManualSuggestionError] = useState('')
  const [smartUploading, setSmartUploading] = useState(false)
  const [selectedRequirement, setSelectedRequirement] = useState(null)
  const [submissions, setSubmissions] = useState([])
  const [submissionsLoading, setSubmissionsLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [reviewUploadOpen, setReviewUploadOpen] = useState(false)
  const [uploadForm, setUploadForm] = useState({
    source: isFieldOfficer() ? 'field_upload' : 'dms_ingestion',
    description: '',
    file: null,
  })
  const [scanPreview, setScanPreview] = useState(null)
  const [scanPreviewLoading, setScanPreviewLoading] = useState(false)
  const [scanPreviewError, setScanPreviewError] = useState('')
  const [reviewingScanId, setReviewingScanId] = useState(null)
  const [checkingSubmissionId, setCheckingSubmissionId] = useState('')
  const [reviewingComplianceResultId, setReviewingComplianceResultId] = useState('')
  const [requirementReviewing, setRequirementReviewing] = useState('')
  const isSubmittingReturnRef = useRef(false)
  const isSubmittingApproveRef = useRef(false)
  const [revisionNotes, setRevisionNotes] = useState('')
  const [filePreview, setFilePreview] = useState(null)
  const [filePreviewLoadingId, setFilePreviewLoadingId] = useState('')
  const canReviewScan = !isFieldOfficer()
  const canSelectSource = !isFieldOfficer()

  const loadQueue = useCallback(async () => {
    setLoading(true)
    setActionError('')
    try {
      const response = await projectApi.listIntakeQueue({
        page,
        per_page: 20,
        search: search || undefined,
        status: status || undefined,
        phase_name: phaseName || undefined,
        lgu_id: lguId || undefined,
      })
      const nextItems = response.data || []
      setItems(nextItems)
      setMeta(response.meta || { total: 0, page: 1, pages: 1 })
      setSelectedRequirement((current) => {
        if (!current?.id) return current
        const freshQueueItem = nextItems.find((item) => Number(item.id) === Number(current.id))
        return freshQueueItem ? mergeRequirementReviewSnapshot(current, freshQueueItem) : current
      })
      return response
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to load documentary intake and review items.')
      setItems([])
      return null
    } finally {
      setLoading(false)
    }
  }, [lguId, page, phaseName, search, status])

  useEffect(() => {
    loadQueue()
  }, [loadQueue])

  useEffect(() => {
    let ignore = false

    async function loadLguOptions() {
      setLguOptionsLoading(true)
      try {
        const response = await lguApi.listLgus({ page: 1, per_page: 200, is_active: true })
        if (!ignore) {
          setLguOptions(response.data || [])
        }
      } catch {
        if (!ignore) {
          setLguOptions([])
        }
      } finally {
        if (!ignore) {
          setLguOptionsLoading(false)
        }
      }
    }

    loadLguOptions()
    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => () => {
    if (filePreview?.url) {
      window.URL.revokeObjectURL(filePreview.url)
    }
  }, [filePreview?.url])

  useEffect(() => {
    if (!smartForm.file) {
      setSmartPreview(null)
      setSmartPreviewError('')
      setSmartPreviewLoading(false)
      setSmartSelectedRequirementId('')
      return undefined
    }

    let ignore = false
    const controller = new AbortController()
    async function previewSmartScan() {
      setSmartPreviewLoading(true)
      setSmartScanProgress(null)
      setSmartPreviewError('')
      setSmartSelectedRequirementId('')
      try {
        const payload = new FormData()
        payload.append('file', smartForm.file)
        const response = await projectApi.previewSubmissionScan(payload, {
          signal: controller.signal,
          onProgress: progress => { if (!ignore) setSmartScanProgress(progress) },
        })
        if (!ignore) {
          const preview = response.data || null
          setSmartPreview(preview)
          setSmartSelectedRequirementId(
            preview?.suggested_project_requirement_id
              ? String(preview.suggested_project_requirement_id)
              : '',
          )
        }
      } catch (error) {
        console.error('Preview error:', error)
        if (!ignore) {
          setSmartPreview(null)
          setSmartPreviewError(error.response?.data?.message || error.message || 'Unable to preview document mapping.')
        }
      } finally {
        if (!ignore) {
          setSmartPreviewLoading(false)
        }
      }
    }
    previewSmartScan()
    return () => {
      ignore = true
      controller.abort()
    }
  }, [smartForm.file])

  useEffect(() => {
    if (!smartIntakeOpen) {
      setManualSuggestions([])
      setManualSuggestionsLoading(false)
      setManualSuggestionError('')
      return undefined
    }

    let ignore = false
    async function loadManualSuggestions() {
      setManualSuggestionsLoading(true)
      setManualSuggestionError('')
      try {
        const query = manualTargetSearch.trim()
        const response = await projectApi.listIntakeQueue({
          page: 1,
          per_page: 10,
          search: query || undefined,
          status: query ? undefined : 'pending',
        })
        if (!ignore) {
          setManualSuggestions(sortTargetSuggestions(
            (response.data || []).map((item) => ({
              ...item,
              project_requirement_id: item.project_requirement_id || item.id,
              confidence: item.confidence || null,
            })),
          ))
        }
      } catch (error) {
        if (!ignore) {
          setManualSuggestions([])
          setManualSuggestionError(error.response?.data?.message || 'Unable to search documentary requirements.')
        }
      } finally {
        if (!ignore) {
          setManualSuggestionsLoading(false)
        }
      }
    }

    const timer = window.setTimeout(loadManualSuggestions, manualTargetSearch.trim() ? 250 : 0)
    return () => {
      ignore = true
      window.clearTimeout(timer)
    }
  }, [manualTargetSearch, smartIntakeOpen])

  const refreshRequirementReview = useCallback(async (requirement) => {
    if (!requirement?.id) return null
    try {
      const [detailResponse, submissionsResponse] = await Promise.all([
        projectApi.getProjectRequirement(requirement.id),
        projectApi.listRequirementSubmissions(requirement.id),
      ])
      const freshSubmissions = submissionsResponse.data || []
      const freshRequirement = mergeRequirementReviewSnapshot(
        requirement,
        detailResponse.data || {},
        freshSubmissions,
      )
      setSubmissions(freshSubmissions)
      setSelectedRequirement(freshRequirement)
      return freshRequirement
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to load the submission history for this requirement.')
      return null
    }
  }, [])

  const openRequirement = useCallback(async (requirement) => {
    const initialRequirement = mergeRequirementReviewSnapshot(requirement)
    setSelectedRequirement(initialRequirement)
    setSubmissions([])
    setSubmissionsLoading(true)
    setActionError('')
    setUploadForm({
      source: isFieldOfficer() ? 'field_upload' : 'dms_ingestion',
      description: '',
      file: null,
    })
    setReviewUploadOpen(false)
    setRevisionNotes('')
    setRequirementReviewing('')
    setCheckingSubmissionId('')
    setScanPreview(null)
    setScanPreviewError('')
    try {
      await refreshRequirementReview(initialRequirement)
    } finally {
      setSubmissionsLoading(false)
    }
  }, [refreshRequirementReview])

  function closeRequirementReview() {
    setSelectedRequirement(null)
    setSubmissions([])
    setReviewUploadOpen(false)
    setRevisionNotes('')
    setActionError('')
    setActionMessage('')
    setCheckingSubmissionId('')
    setScanPreview(null)
    setScanPreviewError('')
    setUploadForm({
      source: isFieldOfficer() ? 'field_upload' : 'dms_ingestion',
      description: '',
      file: null,
    })
  }

  useEffect(() => {
    if (!selectedRequirement?.project_id || !uploadForm.file) {
      setScanPreview(null)
      setScanPreviewError('')
      setScanPreviewLoading(false)
      return undefined
    }

    let ignore = false
    async function previewScan() {
      setScanPreviewLoading(true)
      setScanPreview(null)
      setScanPreviewError('')
      try {
        const payload = new FormData()
        payload.append('project_id', selectedRequirement.project_id)
        payload.append('project_requirement_id', selectedRequirement.id)
        payload.append('file', uploadForm.file)
        const response = await projectApi.previewSubmissionScan(payload)
        if (!ignore) {
          setScanPreview(response.data || null)
        }
      } catch (error) {
        if (!ignore) {
          setScanPreview(null)
          setScanPreviewError(error.response?.data?.message || 'Unable to preview document mapping.')
        }
      } finally {
        if (!ignore) {
          setScanPreviewLoading(false)
        }
      }
    }
    previewScan()
    return () => {
      ignore = true
    }
  }, [selectedRequirement?.project_id, selectedRequirement?.id, uploadForm.file])

  async function handleSmartUpload(event) {
    event.preventDefault()
    if (!smartForm.file) {
      setActionError('Choose the received documentary file before recording intake.')
      return
    }
    const targetRequirementId = Number(smartSelectedRequirementId || smartPreview?.suggested_project_requirement_id)
    if (!targetRequirementId) {
      setActionError('Choose the target project requirement before recording this document.')
      return
    }

    setSmartUploading(true)
    setActionError('')
    setActionMessage('')
    try {
      const payload = new FormData()
      payload.append('source', isFieldOfficer() ? 'field_upload' : smartForm.source)
      if (smartForm.description) {
        payload.append('description', smartForm.description)
      }
      payload.append('file', smartForm.file)
      await projectApi.createRequirementSubmission(targetRequirementId, payload)
      setActionMessage('Document recorded. OCR/NLP scan result is saved for staff review.')
      setSmartForm({
        source: isFieldOfficer() ? 'field_upload' : 'dms_ingestion',
        description: '',
        file: null,
      })
      setSmartFileInputKey((current) => current + 1)
      setSmartPreview(null)
      setSmartPreviewError('')
      setSmartPreviewLoading(false)
      setSmartSelectedRequirementId('')
      setManualTargetSearch('')
      setManualSuggestions([])
      setSmartIntakeOpen(false)
      await loadQueue()
      if (selectedRequirement?.id && Number(selectedRequirement.id) === Number(targetRequirementId)) {
        await openRequirement(selectedRequirement)
      }
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to record this documentary intake.')
    } finally {
      setSmartUploading(false)
    }
  }

  async function handleUploadSubmission(event) {
    event.preventDefault()
    if (!selectedRequirement) return
    if (!uploadForm.file) {
      setActionError('Choose the received documentary file before recording intake.')
      return
    }

    setUploading(true)
    setActionError('')
    try {
      const payload = new FormData()
      payload.append('source', isFieldOfficer() ? 'field_upload' : uploadForm.source)
      if (uploadForm.description) {
        payload.append('description', uploadForm.description)
      }
      payload.append('file', uploadForm.file)
      await projectApi.createRequirementSubmission(selectedRequirement.id, payload)
      setActionMessage('New documentary version recorded for this requirement.')
      setUploadForm({
        source: isFieldOfficer() ? 'field_upload' : 'dms_ingestion',
        description: '',
        file: null,
      })
      setReviewUploadOpen(false)
      setScanPreview(null)
      await Promise.all([loadQueue(), openRequirement(selectedRequirement)])
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to record this documentary intake.')
    } finally {
      setUploading(false)
    }
  }

  async function handleReviewScan(scan, decision) {
    if (!scan?.id || !selectedRequirement) return
    setReviewingScanId(scan.id)
    setActionError('')
    setActionMessage('')
    try {
      await projectApi.reviewSubmissionScan(scan.id, { decision })
      setActionMessage(
        decision === 'accepted'
          ? 'Mapping accepted. Review the attachment itself before approving compliance.'
          : 'Mapping rejected. If the attachment needs correction, return the requirement for revision with notes.',
      )
      await Promise.all([loadQueue(), openRequirement(selectedRequirement)])
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to record this document intelligence review.')
    } finally {
      setReviewingScanId(null)
    }
  }

  async function handleApproveRequirement() {
    if (!selectedRequirement) return
    if (isSubmittingApproveRef.current) return
    if (!submissions.length) {
      setActionError('Upload documentary evidence before approving this requirement.')
      return
    }

    isSubmittingApproveRef.current = true
    setRequirementReviewing('approve')
    setActionError('')
    setActionMessage('')
    try {
      let response
      if (selectedRequirement.document_category) {
        const wfStatus = selectedRequirement.workflow_status
        const admin = isAdmin()
        if (wfStatus === 'approved') {
          setActionMessage('Requirement is already approved.')
          return
        }
        if (admin && (!wfStatus || wfStatus === 'draft' || wfStatus === 'submitted' || wfStatus === 'resubmitted' || wfStatus === 'under_verification')) {
          setActionError('This requirement must be verified and recommended by Technical Staff before Provincial Director approval.')
          return
        }
        if (wfStatus === 'draft' || !wfStatus) {
          await monitoringApi.submitRequirementWorkflow(selectedRequirement.id)
          await monitoringApi.verifyRequirementWorkflow(selectedRequirement.id)
          await monitoringApi.staffApproveRequirementWorkflow(selectedRequirement.id)
          response = await monitoringApi.getRequirementWorkflow(selectedRequirement.id)
          setActionMessage('Requirement verified and staff-approved. Forwarded for Provincial Director approval.')
        } else if (wfStatus === 'submitted' || wfStatus === 'resubmitted') {
          await monitoringApi.verifyRequirementWorkflow(selectedRequirement.id)
          await monitoringApi.staffApproveRequirementWorkflow(selectedRequirement.id)
          response = await monitoringApi.getRequirementWorkflow(selectedRequirement.id)
          setActionMessage('Requirement verified and staff-approved. Forwarded for Provincial Director approval.')
        } else if (wfStatus === 'under_verification') {
          await monitoringApi.staffApproveRequirementWorkflow(selectedRequirement.id)
          response = await monitoringApi.getRequirementWorkflow(selectedRequirement.id)
          setActionMessage('Requirement staff-approved. Forwarded for Provincial Director approval.')
        } else if (wfStatus === 'staff_approved' || wfStatus === 'pending_provincial_approval') {
          if (admin) {
            response = await monitoringApi.provincialApproveRequirementWorkflow(selectedRequirement.id)
            setActionMessage('Attachment approved. Requirement marked Compliant and approved.')
          } else {
            setActionMessage('Requirement is already staff-approved and awaiting Provincial Director approval.')
            return
          }
        } else {
          response = await monitoringApi.provincialApproveRequirementWorkflow(selectedRequirement.id)
          setActionMessage('Attachment approved.')
        }
      } else {
        response = await projectApi.updateProjectRequirement(selectedRequirement.id, { status: 'compliant' })
        setActionMessage('Attachment approved. Requirement marked Compliant and ready for regional handoff.')
      }

      const responseData = response?.data || response || {}
      const updatedRequirement = {
        ...selectedRequirement,
        ...responseData,
        project_name: selectedRequirement.project_name,
        lgu_name: selectedRequirement.lgu_name,
        program_name: selectedRequirement.program_name,
      }
      setRevisionNotes('')
      await Promise.all([loadQueue(), openRequirement(updatedRequirement)])
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to approve this requirement attachment.')
    } finally {
      isSubmittingApproveRef.current = false
      setRequirementReviewing('')
    }
  }

  async function handleReturnRequirementForRevision(returnData) {
    if (!selectedRequirement) return
    if (isSubmittingReturnRef.current) return
    if (!submissions.length) {
      setActionError('Upload documentary evidence before returning this requirement for revision.')
      return
    }
    const isObject = typeof returnData === 'object' && returnData !== null
    const notes = isObject
      ? (returnData.reason || '')
      : (typeof returnData === 'string' ? returnData : revisionNotes)
    const deficiencies = isObject ? returnData.deficiencies : undefined

    if (!notes.trim() && (!deficiencies || deficiencies.length === 0)) {
      setActionError('Revision notes or at least one deficiency item is required so the correction needed is clear.')
      return
    }

    isSubmittingReturnRef.current = true
    setRequirementReviewing('revision')
    setActionError('')
    setActionMessage('')
    try {
      if (!selectedRequirement.workflow_status || selectedRequirement.workflow_status === 'draft') {
        if (selectedRequirement.document_category) {
          await monitoringApi.submitRequirementWorkflow(selectedRequirement.id)
        }
      }

      const payload = {
        reason: notes.trim() || undefined,
        ...(deficiencies && deficiencies.length > 0 ? { deficiencies } : {}),
      }

      let response
      try {
        response = await monitoringApi.returnRequirementWorkflow(selectedRequirement.id, payload)
      } catch (workflowErr) {
        if (!selectedRequirement.document_category && isWorkflowNotApplicableError(workflowErr)) {
          response = await projectApi.returnProjectRequirementForRevision(selectedRequirement.id, {
            review_notes: notes.trim(),
          })
        } else {
          throw workflowErr
        }
      }

      const responseData = response?.data || response || {}
      const updatedRequirement = {
        ...selectedRequirement,
        ...responseData,
        project_name: selectedRequirement.project_name,
        lgu_name: selectedRequirement.lgu_name,
        program_name: selectedRequirement.program_name,
      }
      setRevisionNotes('')
      setActionMessage('Requirement returned for revision. It remains Under Review until corrected or escalated after an overdue deadline.')
      await Promise.all([loadQueue(), openRequirement(updatedRequirement)])
    } catch (error) {
      if (
        error.response?.status === 409 &&
        (String(error.response?.data?.message || '').includes('returned_for_revision') ||
         String(error.response?.data?.error || '').includes('returned_for_revision'))
      ) {
        setActionMessage('This requirement was already returned for revision. The review state has been refreshed.')
        setActionError('')
        await Promise.all([
          loadQueue(),
          openRequirement({ ...selectedRequirement, workflow_status: 'returned_for_revision' }),
        ])
        return
      }
      setActionError(error.response?.data?.message || 'Unable to return this requirement for revision.')
    } finally {
      isSubmittingReturnRef.current = false
      setRequirementReviewing('')
    }
  }

  function applyCheckerReturnNotes(result) {
    if (!result?.suggested_return_notes) return
    setRevisionNotes(result.suggested_return_notes)
  }

  async function handleRescanSubmission(submissionId) {
    if (!submissionId || !selectedRequirement) return
    setReviewingScanId(`rescan-${submissionId}`)
    setActionError('')
    try {
      await projectApi.scanSubmissionDocument(submissionId)
      await Promise.all([loadQueue(), openRequirement(selectedRequirement)])
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to run document intelligence scan.')
    } finally {
      setReviewingScanId(null)
    }
  }

  async function handleRefreshDestination(submissionId) {
    if (!submissionId || !selectedRequirement) return
    setReviewingScanId(`refresh-destination-${submissionId}`)
    setActionError('')
    try {
      await projectApi.refreshSubmissionDestination(submissionId)
      await Promise.all([loadQueue(), openRequirement(selectedRequirement)])
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to refresh document destination check.')
    } finally {
      setReviewingScanId(null)
    }
  }

  async function handleRunComplianceCheck(submissionId, options = {}) {
    if (!submissionId || !selectedRequirement) return
    setCheckingSubmissionId(`${submissionId}:${options.use_prior_year_reference ? 'prior' : 'current'}`)
    setActionError('')
    setActionMessage('')
    try {
      const response = await projectApi.runSubmissionComplianceCheck(submissionId, options)
      const result = response.data
      setActionMessage(
        result?.status === 'ready_for_approval'
          ? 'Compliance checker found no deterministic issues. Staff approval is still recorded separately.'
          : 'Compliance checker completed. Review the findings before approving or returning the attachment.',
      )
      await Promise.all([loadQueue(), openRequirement(selectedRequirement)])
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to run documentary compliance check.')
    } finally {
      setCheckingSubmissionId('')
    }
  }

  async function handleStatusChange(requirementId, data) {
    if (!requirementId) return
    setActionError('')
    setActionMessage('')
    try {
      const response = await projectApi.createChangeStatusRequest(requirementId, data)
      if (data.auto_approve) {
        setActionMessage('Requirement status updated successfully.')
        await Promise.all([
          loadQueue(),
          selectedRequirement ? refreshRequirementReview(selectedRequirement) : Promise.resolve(),
        ])
      } else {
        setActionMessage('Status change request submitted for administrator review.')
      }
      return response
    } catch (error) {
      setActionError(error.response?.data?.message || error.response?.data?.error || 'Unable to update status.')
      throw error
    }
  }

  async function handleRecordComplianceReview(resultId, payload) {
    if (!resultId || !selectedRequirement) return
    setReviewingComplianceResultId(resultId)
    setActionError('')
    setActionMessage('')
    try {
      const response = await projectApi.reviewComplianceResult(resultId, payload)
      if (payload.finding_reviews && response.data?.id) {
        const updated = response.data
        setSubmissions(previous => previous.map(submission => submission.id !== updated.submission_id ? submission : {
          ...submission,
          latest_compliance_result: updated,
          compliance_results: submission.compliance_results?.map(result => result.id === updated.id ? updated : result),
        }))
        setActionMessage('Finding decision recorded.')
        return true
      }
      setActionMessage('Reviewer decision recorded for the compliance result.')
      await Promise.all([loadQueue(), openRequirement(selectedRequirement)])
      return true
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to record the compliance review decision.')
      return false
    } finally {
      setReviewingComplianceResultId('')
    }
  }

  async function handleDownload(file) {
    try {
      const response = await projectApi.downloadSubmissionFile(file.id)
      const mimeType = response.headers?.['content-type'] || file.mime_type || 'application/octet-stream'
      const blob = new Blob([response.data], { type: mimeType })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = file.file_name || `submission-${file.id}`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      setTimeout(() => window.URL.revokeObjectURL(url), 1500)
    } catch (error) {
      setActionError(await fileTransferErrorMessage(error, 'Unable to download the selected file.'))
    }
  }

  async function handlePreview(file) {
    if (!file?.id) {
      setActionError('No previewable file is attached to this intake record.')
      return
    }

    setFilePreviewLoadingId(file.id)
    setActionError('')
    try {
      const response = await projectApi.downloadSubmissionFile(file.id)
      const mimeType = response.headers?.['content-type'] || file.mime_type || 'application/octet-stream'
      const blob = new Blob([response.data], { type: mimeType })
      const url = window.URL.createObjectURL(blob)
      setFilePreview((current) => {
        if (current?.url) {
          window.URL.revokeObjectURL(current.url)
        }
        return {
          url,
          fileName: file.file_name || `submission-${file.id}`,
          mimeType,
          sizeBytes: file.file_size_bytes,
          complianceResult: complianceResultForFile(file),
        }
      })
    } catch (error) {
      setActionError(await fileTransferErrorMessage(error, 'Unable to preview the selected file.'))
    } finally {
      setFilePreviewLoadingId('')
    }
  }

  function closeFilePreview() {
    setFilePreview(null)
  }

  function complianceResultForFile(file) {
    if (file?.latest_compliance_result) return file.latest_compliance_result
    if (file?.compliance_result) return file.compliance_result
    const fileId = Number(file?.id)
    if (!Number.isFinite(fileId)) return null

    for (const submission of submissions) {
      const results = [
        submission.latest_compliance_result,
        ...(submission.compliance_results || []),
      ].filter(Boolean)
      const exact = results.find((result) => Number(result.document_file_id) === fileId)
      if (exact) return exact

      const belongsToSubmission = (submission.document_files || []).some(
        (documentFile) => Number(documentFile.id) === fileId,
      )
      if (belongsToSubmission && results.length === 1 && !results[0].document_file_id) {
        return results[0]
      }
    }

    return null
  }

  async function openRequirementUpload(requirement) {
    await openRequirement(requirement)
    setReviewUploadOpen(true)
  }

  const queueSummary = meta.summary || {}
  const totalItems = queueSummary.total ?? meta.total ?? items.length
  const withEvidence = queueSummary.with_evidence ?? items.filter((item) => item.has_documentary_evidence).length
  const pendingCount = queueSummary.pending ?? items.filter((item) => item.status === 'pending').length
  const reviewCount = queueSummary.under_review ?? items.filter((item) => item.status === 'under_review').length
  const groupedItems = useMemo(() => groupIntakeItems(items), [items])
  const previewMatchesSelected = scanPreview?.suggested_project_requirement_id
    ? Number(scanPreview.suggested_project_requirement_id) === Number(selectedRequirement?.id)
    : false
  const smartCandidates = smartPreview?.candidate_rankings || []
  const smartCandidatesUnverified = !manualTargetSearch && (smartPreview?.review_reasons || []).some(
    (reason) => ['ai_abstained', 'ai_refinement_unavailable'].includes(reason),
  )
  const selectedSmartCandidate = [...smartCandidates, ...manualSuggestions].find(
    (candidate) => Number(candidate.project_requirement_id) === Number(smartSelectedRequirementId),
  )
  const selectedHasEvidence = Boolean(selectedRequirement?.has_documentary_evidence || submissions.length)
  const selectedReviewLocked = ['compliant', 'non_compliant', 'waived'].includes(selectedRequirement?.status)

  return (
    <div className="animate-fade-in">
      <div className="mb-6">
        <h1 className="page-title">Documentary Intake & Review</h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Record documentary submissions, evaluate documentary compliance, and verify supporting files for PDMU review. AI suggestions assist evaluation and do not determine compliance or workflow status.
        </p>
      </div>

      <FeedbackToast type="success" message={actionMessage} onDismiss={() => setActionMessage('')} />
      {!selectedRequirement && actionError && (
        <InlineAlert type="error" className="mb-4" onDismiss={() => setActionError('')}>
          {actionError}
        </InlineAlert>
      )}

      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-4">
        <KpiCard title="Items" value={totalItems} subtitle="in queue" icon={Inbox} color="blue" />
        <KpiCard title="With evidence" value={withEvidence} subtitle="documented" icon={CheckCircle2} color="emerald" />
        <KpiCard title="Pending" value={pendingCount} subtitle="awaiting review" icon={Clock} color="amber" />
        <KpiCard title="Under review" value={reviewCount} subtitle="in progress" icon={Upload} color="cyan" />
      </div>

      <div className="mb-4 flex flex-wrap gap-3">
        <form
          onSubmit={(event) => {
            event.preventDefault()
            setPage(1)
            loadQueue()
          }}
          className="flex min-w-[260px] flex-1 gap-2"
        >
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600 dark:text-slate-400" />
            <input
              className="input-field pl-10"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search project, LGU, or requirement"
            />
          </div>
          <Button type="submit" variant="outline" className="self-center">Search</Button>
        </form>
        <select className="input-field w-auto" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1) }}>
          {STATUS_FILTERS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <select className="input-field w-auto" value={phaseName} onChange={(event) => { setPhaseName(event.target.value); setPage(1) }}>
          {PHASE_FILTERS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <select
          className="input-field w-auto min-w-[180px]"
          value={lguId}
          disabled={lguOptionsLoading && !lguOptions.length}
          aria-label="Filter by LGU"
          onChange={(event) => { setLguId(event.target.value); setPage(1) }}
        >
          <option value="">{lguOptionsLoading ? 'Loading LGUs...' : 'All LGUs'}</option>
          {lguOptions.map((lgu) => (
            <option key={lgu.id} value={lgu.id}>{lgu.name}</option>
          ))}
        </select>
        <Button icon={Upload} className="sm:ml-auto" onClick={() => setSmartIntakeOpen(true)}>
          Record Received Document
        </Button>
      </div>

      <Modal
        open={smartIntakeOpen}
        title="Smart Document Intake"
        description="Upload a received DMS or field file, confirm the OCR/NLP mapping, then record it to the selected requirement."
        size="xl"
        onClose={() => setSmartIntakeOpen(false)}
      >
        <form onSubmit={handleSmartUpload} className="space-y-4">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-brand-text">Upload and Match Document</h2>
              <p className="mt-1 text-sm text-brand-text-muted">
                Upload a received file first, then confirm the OCR/NLP-suggested project requirement.
              </p>
            </div>
            {selectedSmartCandidate && (
              <span
                className={scanStatusClass({
                  is_accepted: null,
                  needs_review: smartPreview?.needs_review,
                  mapping_mismatch: false,
                })}
                title="Heuristic lexical match indicator based on document and project metadata, not statistical probability."
              >
                {selectedSmartCandidate.confidence
                  ? `${selectedSmartCandidate.match_tier || matchTier(selectedSmartCandidate.confidence)} (${formatConfidence(selectedSmartCandidate.confidence)})`
                  : 'Manual Target'}
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[180px_1fr]">
            <div>
              <label className="label-text">Source</label>
              <select
                className="input-field mt-1"
                value={smartForm.source}
                disabled={!canSelectSource}
                onChange={(event) => setSmartForm((current) => ({ ...current, source: event.target.value }))}
              >
                <option value="dms_ingestion">DMS Ingestion</option>
                <option value="direct_upload">Direct Upload</option>
                <option value="field_upload">Field Upload</option>
                <option value="api_push">API Push</option>
              </select>
            </div>
            <div>
              <label className="label-text">Document File</label>
              <input
                key={smartFileInputKey}
                type="file"
                accept={DOCUMENT_UPLOAD_ACCEPT}
                className="input-field mt-1"
                onChange={(event) => {
                  setActionMessage('')
                  setSmartForm((current) => ({ ...current, file: event.target.files?.[0] || null }))
                }}
              />
            </div>
          </div>

          <AiRewriteControl
            label="Intake Notes"
            value={smartForm.description}
            onTextChange={(text) => setSmartForm((current) => ({ ...current, description: text }))}
            contextLabel="Document intake notes"
            disabled={smartUploading}
            placeholder="Add DMS reference, routing context, or reviewer notes."
            rows={2}
          />
          
          {smartPreviewLoading && (
            <div className="rounded-lg border border-brand-border bg-brand-surface-solid p-6 text-center mt-4 mb-4">
              <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-brand-primary border-t-transparent" />
              <div role="status" aria-live="polite" className="mt-4 font-medium text-brand-text">
                {smartScanProgress?.stage === 'queued' ? 'Document queued for processing…'
                  : smartScanProgress?.stage === 'matching' ? 'Finding matching project requirements…'
                  : smartScanProgress?.total_pages
                    ? `Reading pages: ${smartScanProgress.completed_pages} of ${smartScanProgress.total_pages}`
                    : 'Preparing document for scanning…'}
              </div>
              <div className="mt-1 text-sm text-brand-text-muted">You can close this window while scanning continues. Reopen it here to check the result.</div>
            </div>
          )}
          {smartPreviewError && (
            <InlineAlert type="error" className="mt-4 mb-4">{smartPreviewError}</InlineAlert>
          )}

          {/* Project/LGU Context Line */}
          {smartPreview?.suggested_project_name && (
            <div className="rounded-lg border border-brand-border bg-brand-surface-solid p-3 mb-2 mt-4">
              <div className="text-sm font-medium text-brand-text flex items-center justify-between">
                <div>
                  Suggested Context: <span className="font-bold">{smartPreview.suggested_project_name}</span> ({smartPreview.suggested_lgu_name})
                </div>
                {smartPreview.document_structure && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-brand-primary/10 text-brand-primary border border-brand-primary/20 capitalize">
                    {smartPreview.document_structure.replace(/_/g, ' ')}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Project Status Alerts */}
          <MatcherReviewNotice scan={smartPreview} />
          {smartPreview?.project_status === 'ambiguous' && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-300/40 dark:bg-amber-300/10 dark:text-amber-100 mb-2">
              <strong>Ambiguous Project Match:</strong> The document content matches multiple projects. Please verify and select the correct project requirement below.
            </div>
          )}
          {smartPreview?.project_status === 'unresolved' && (
            <div className="rounded-lg border border-sky-300 bg-sky-50 px-3 py-2 text-sm text-sky-900 dark:border-sky-300/40 dark:bg-sky-300/10 dark:text-sky-100 mb-2">
              <strong>Project Unresolved:</strong> No matching project could be uniquely identified from the document text. Please search and select the target project requirement below.
            </div>
          )}

          {/* Warning Banners */}
          {smartPreview?.close_call && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-300/40 dark:bg-amber-300/10 dark:text-amber-100 mb-2">
              <strong>Close Call:</strong> The scan result is very close between multiple candidates. Please verify the correct project requirement.
            </div>
          )}
          {smartPreview?.semantic_conflict && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-300/40 dark:bg-amber-300/10 dark:text-amber-100 mb-2">
              <strong>Semantic Conflict:</strong> The system detected overlapping content (e.g., SORD vs Proof of Return). Please verify the selected requirement matches the document intent.
            </div>
          )}

          {/* Unified Search and Candidate List */}
          <div className="rounded-lg border border-brand-border bg-brand-surface-solid p-4 mb-4 mt-2">
            <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
              <div>
                <div className="text-sm font-semibold text-brand-text">Requirement Search & {smartCandidatesUnverified ? 'Review Candidates' : 'Document Matches'}</div>
                <p className="mt-1 text-xs text-brand-text-muted">
                  Match indicators are heuristic similarity scores based on text and project metadata overlap, not statistical certainty. Pending requirements without evidence are prioritized.
                </p>
              </div>
              {manualSuggestionsLoading && (
                <span className="text-xs text-brand-text-muted">Searching...</span>
              )}
            </div>
            <div className="relative mt-3">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600 dark:text-slate-400" />
              <input
                className="input-field pl-10"
                value={manualTargetSearch}
                onChange={(event) => setManualTargetSearch(event.target.value)}
                placeholder="Search catalog... (or clear to see AI suggestions)"
              />
            </div>
            {manualSuggestionError && (
                <InlineAlert type="warning" className="mt-3" onDismiss={() => setManualSuggestionError('')}>
                  {manualSuggestionError}
                </InlineAlert>
            )}

            <div className="mt-3 grid grid-cols-1 gap-2 xl:grid-cols-2">
              {(!manualTargetSearch ? (smartPreview?.candidate_rankings || []) : manualSuggestions).map((candidate) => {
                const selected = Number(candidate.project_requirement_id) === Number(smartSelectedRequirementId)
                const task = reviewTask(candidate)
                return (
                  <button
                    key={candidate.project_requirement_id}
                    type="button"
                    className={`rounded-lg border px-3 py-2 text-left transition-colors ${
                      selected
                        ? 'border-brand-primary bg-brand-primary/5 ring-1 ring-brand-primary'
                        : 'border-brand-border hover:border-brand-primary/30 hover:bg-brand-surface'
                    }`}
                    onClick={() => setSmartSelectedRequirementId(String(candidate.project_requirement_id))}
                  >
                    <div className="flex items-center justify-between">
                      <div className="font-medium text-brand-text">{candidate.requirement_name}</div>
                      {candidate.confidence != null && (
                        <div className="flex items-center gap-1.5" title="Heuristic lexical match score, not statistical probability">
                          <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium border ${matchTierBadgeClass(candidate.match_tier || matchTier(candidate.confidence))}`}>
                            {smartCandidatesUnverified ? 'Review candidate' : (candidate.match_tier || matchTier(candidate.confidence))}
                          </span>
                          <span className="text-xs font-semibold text-brand-text-muted">
                            {formatConfidence(candidate.confidence)}
                          </span>
                        </div>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-brand-text-muted">
                      {candidate.project_name} • {candidate.lgu_name}
                    </div>
                    <div className="mt-1 text-xs text-brand-text-muted">
                      {task ? `Requires: ${task.label}` : 'Ready for evidence'}
                    </div>
                  </button>
                )
              })}
              {(!manualTargetSearch && !(smartPreview?.candidate_rankings?.length > 0)) && (
                  <div className="col-span-full py-4 text-center text-sm text-brand-text-muted">
                      {smartPreview?.review_reasons?.includes('missing_fund_return_requirement')
                        ? 'No matching fund-return requirement is available in this project checklist. Request a checklist review before recording this document.'
                        : smartPreview?.review_reasons?.includes('missing_compatible_requirement')
                          ? 'No compatible documentary requirement is available in this project checklist. Review the project or request a checklist correction.'
                        : 'No AI suggestions available. Please search the catalog.'}
                  </div>
              )}
            </div>
          </div>
          <EvidenceWarning candidate={selectedSmartCandidate} />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-brand-text-muted">
              Recording saves the evidence and scan result; compliance still needs staff review.
            </span>
            <Button
              type="submit"
              icon={Upload}
              loading={smartUploading}
              disabled={!smartForm.file || !smartSelectedRequirementId}
            >
              Record to Selected Requirement
            </Button>
          </div>
        </form>
      </Modal>

      <GlassPanel noPadding className="overflow-hidden">
          <IntakeQueueList
            groups={groupedItems}
            isLoading={loading}
            filePreviewLoadingId={filePreviewLoadingId}
            onOpenRequirement={openRequirement}
            onUploadRequirement={openRequirementUpload}
            onPreviewFile={handlePreview}
          />

          {meta.pages > 1 && (
            <div className="flex items-center justify-center gap-3 border-t border-brand-border px-4 py-4">
              <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>
                Previous
              </Button>
              <span className="text-sm text-brand-text-muted">Page {page} of {meta.pages}</span>
              <Button size="sm" variant="outline" disabled={page >= meta.pages} onClick={() => setPage((current) => current + 1)}>
                Next
              </Button>
            </div>
          )}
      </GlassPanel>

      <RequirementReviewModal
        open={Boolean(selectedRequirement)}
        selectedRequirement={selectedRequirement}
        submissions={submissions}
        submissionsLoading={submissionsLoading}
        canReviewScan={canReviewScan}
        selectedHasEvidence={selectedHasEvidence}
        selectedReviewLocked={selectedReviewLocked}
        reviewUploadOpen={reviewUploadOpen}
        setReviewUploadOpen={setReviewUploadOpen}
        uploadForm={uploadForm}
        setUploadForm={setUploadForm}
        uploading={uploading}
        scanPreview={scanPreview}
        scanPreviewLoading={scanPreviewLoading}
        scanPreviewError={scanPreviewError}
        setScanPreviewError={setScanPreviewError}
        previewMatchesSelected={previewMatchesSelected}
        revisionNotes={revisionNotes}
        setRevisionNotes={setRevisionNotes}
        requirementReviewing={requirementReviewing}
        reviewingScanId={reviewingScanId}
        checkingSubmissionId={checkingSubmissionId}
        reviewingComplianceResultId={reviewingComplianceResultId}
        filePreviewLoadingId={filePreviewLoadingId}
        userRole={isFieldOfficer() ? 'field_officer' : (isAdmin() ? 'admin' : 'staff')}
        error={actionError}
        onDismissError={() => setActionError('')}
        onClose={closeRequirementReview}
        onUploadSubmission={handleUploadSubmission}
        onApproveRequirement={handleApproveRequirement}
        onReturnRequirementForRevision={handleReturnRequirementForRevision}
        onApplyCheckerReturnNotes={applyCheckerReturnNotes}
        onRecordComplianceReview={handleRecordComplianceReview}
        onRunComplianceCheck={handleRunComplianceCheck}
        onRescanSubmission={handleRescanSubmission}
        onRefreshDestination={handleRefreshDestination}
        onReviewScan={handleReviewScan}
        onPreview={handlePreview}
        onDownload={handleDownload}
        onStatusChange={handleStatusChange}
        onRefreshRequirement={refreshRequirementReview}
      />

      <Modal
        open={Boolean(filePreview)}
        title="Document Preview"
        description={filePreview?.fileName}
        onClose={closeFilePreview}
        size="xl"
        footer={filePreview && (
          <div className="flex justify-end">
            <a
              href={filePreview.url}
              download={filePreview.fileName}
              className="btn-outline inline-flex min-h-10 items-center justify-center gap-2 px-4 py-2 text-sm"
            >
              <Download className="h-4 w-4" strokeWidth={1.5} />
              Download
            </a>
          </div>
        )}
      >
        {filePreview && <AnnotatedDocumentPreview filePreview={filePreview} />}
      </Modal>
    </div>
  )
}
