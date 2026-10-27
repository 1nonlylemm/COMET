import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { CheckCircle2, Clock, AlertTriangle, FileText, MapPin, Briefcase, FolderKanban, Edit, ArrowRight, ShieldCheck, Download, Search } from 'lucide-react'
import { AmountInput, Breadcrumb, GlassPanel, Button, DataTable, DocumentPreview, FeedbackToast, FormField, InlineAlert, KpiCard, Modal, ProgramPausedBanner } from '../../../components'
import { isAdmin, isStaff, isFieldOfficer } from '../../../lib/auth'
import RequirementReviewModal from '../../intake/components/RequirementReviewModal/index.jsx'
import { AnnotatedDocumentPreview } from '../../intake/components/AnnotatedDocumentPreview'
import { ROUTES } from '../../../config/routes'
import { formatCurrency, formatMachineLabel, formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import { apiErrorMessage } from '../../../lib/formErrors'
import { AiRewriteControl } from '../../ai/components/AiRewriteControl'
import * as projectApi from '../api/projectApi'
import * as lguApi from '../../lgus/api/lguApi'
import * as programApi from '../../programs/api/programApi'
import * as monitoringApi from '../../monitoring/api/monitoringApi'
import { workflowStatusLabel } from '../../monitoring/components/workflowStatus'
import { isWorkflowNotApplicableError } from '../../intake/lib/workflowErrors'
import { useFiscalYear } from '../../../context/useFiscalYear'
import { hasProjectValidationErrors, validateProjectFields } from '../utils/projectValidation'
import { countActiveFilters, filterRequirements } from '../utils/filterRequirements'
import { PROJECT_STATUS_BADGE, PROJECT_STATUS_OPTIONS } from '../constants/projectStatus'
import { getProgressLabel } from '../utils/progressLabel'
import { ProjectRequirementsTable } from '../components/ProjectRequirementsTable'
import { ChangeApplicabilityModal } from '../components/ChangeApplicabilityModal'
import { checkApplicabilityEligibility } from '../utils/applicability'

const PHASE_BADGE = {
  pre_implementation: { label: 'Pre-Implementation' },
  implementation: { label: 'Implementation' },
  completion: { label: 'Completion' },
}
const PHASE_NAME_BADGE = {
  'Pre-Implementation': PHASE_BADGE.pre_implementation,
  'Implementation': PHASE_BADGE.implementation,
  'Completion': PHASE_BADGE.completion,
}

const REQ_STATUS_BADGE = {
  pending: { label: 'Pending' },
  under_review: { label: 'Under Review' },
  compliant: { label: 'Compliant' },
  non_compliant: { label: 'Non-Compliant' },
  waived: { label: 'Waived' },
  returned_for_revision: { label: 'Returned for Revision' },
}

const REQ_STATUS_OPTIONS = ['pending', 'under_review', 'compliant', 'non_compliant', 'waived', 'returned_for_revision']

const ALL_PROJECT_KIND_OPTIONS = [
  { value: 'infrastructure', label: 'Infrastructure (Civil Works)' },
  { value: 'goods', label: 'Goods / Equipment' },
  { value: 'vehicle', label: 'Motor Vehicles' },
  { value: 'financial_assistance', label: 'Financial / Social Assistance' },
]

const NON_INFRA_PROJECT_KIND_OPTIONS = [
  { value: 'goods', label: 'Goods / Equipment' },
  { value: 'vehicle', label: 'Motor Vehicles' },
  { value: 'financial_assistance', label: 'Financial / Social Assistance' },
]

const INFRA_PROJECT_KIND_OPTIONS = [
  { value: 'infrastructure', label: 'Infrastructure (Civil Works)' },
]

function editableTemplateVariables(template) {
  const definitions = template?.placeholder_definitions || []
  const systemKeys = new Set([
    'report_title',
    'generated_at_display',
    'date',
    'project_id',
    'project_name',
    'source_project_code',
    'lgu_name',
    'program_name',
    'fiscal_year',
    'revision_count',
    'revision_rows',
    'revision_rows_text',
  ])
  return definitions.filter((item) => item?.key && !systemKeys.has(item.key))
}

export default function ProjectDetailPage() {
  const { id } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const { selectedFiscalYear } = useFiscalYear()

  const urlTab = searchParams.get('tab')
  const initialTab = ['overview', 'requirements', 'history', 'activity'].includes(urlTab) ? urlTab : 'overview'
  const initialStatus = searchParams.get('status') || ''
  const initialPhase = searchParams.get('phase') || ''
  const [project, setProject] = useState(null)
  const [requirements, setRequirements] = useState([])
  const [activityLogs, setActivityLogs] = useState([])
  const [activityLoading, setActivityLoading] = useState(false)
  const [reportDownloading, setReportDownloading] = useState(false)
  const [downloadingReqId, setDownloadingReqId] = useState(null)
  const [reportTemplates, setReportTemplates] = useState([])
  const [selectedReportTemplateId, setSelectedReportTemplateId] = useState('')
  const [reportPlaceholderValues, setReportPlaceholderValues] = useState({})
  const [reportPreview, setReportPreview] = useState(null)
  const [reportPreviewLoading, setReportPreviewLoading] = useState(false)
  const [reportModalOpen, setReportModalOpen] = useState(false)
  const [showHistoricalReturns, setShowHistoricalReturns] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [requirementsError, setRequirementsError] = useState('')
  const [activityError, setActivityError] = useState('')
  const [activeTab, setActiveTab] = useState(initialTab)
  const [searchInput, setSearchInput] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [phaseFilter, setPhaseFilter] = useState(initialPhase)
  const [statusFilter, setStatusFilter] = useState(initialStatus)
  const [mandatoryFilter, setMandatoryFilter] = useState('')
  const debounceTimerRef = useRef(null)

  useEffect(() => {
    const t = searchParams.get('tab')
    if (t && ['overview', 'requirements', 'history', 'activity'].includes(t)) {
      setActiveTab((prev) => (prev !== t ? t : prev))
    }
    const st = searchParams.get('status') || ''
    if (st) setStatusFilter((prev) => (prev !== st ? st : prev))
    const ph = searchParams.get('phase') || ''
    if (ph) setPhaseFilter((prev) => (prev !== ph ? ph : prev))
  }, [searchParams])



  const handleTabChange = (tab) => {
    setActiveTab(tab)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (tab === 'overview') {
        next.delete('tab')
      } else {
        next.set('tab', tab)
      }
      return next
    }, { replace: true })
  }

  // Transition form
  const [showTransition, setShowTransition] = useState(false)
  const [transitionTo, setTransitionTo] = useState('')
  const [transitionReason, setTransitionReason] = useState('')
  const [transitionError, setTransitionError] = useState('')
  const [transitioning, setTransitioning] = useState(false)

  // Update requirement modal
  const [editingReq, setEditingReq] = useState(null)
  const [reqForm, setReqForm] = useState({ status: '', waived_reason: '', revision_notes: '' })
  const [reqSubmitting, setReqSubmitting] = useState(false)
  const [reqError, setReqError] = useState('')
  const [reqNotice, setReqNotice] = useState('')
  const [viewingDetailReq, setViewingDetailReq] = useState(null)
  const [applicabilityModalReq, setApplicabilityModalReq] = useState(null)
  const [applicabilityModalMode, setApplicabilityModalMode] = useState('set_not_applicable')

  // Evidence review and upload modal
  const [selectedEvidenceReq, setSelectedEvidenceReq] = useState(null)
  const [evidenceSubmissions, setEvidenceSubmissions] = useState([])
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [reviewUploadOpen, setReviewUploadOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadForm, setUploadForm] = useState({
    source: isFieldOfficer() ? 'field_upload' : 'dms_ingestion',
    description: '',
    file: null,
  })
  const [scanPreview, setScanPreview] = useState(null)
  const [scanPreviewLoading, setScanPreviewLoading] = useState(false)
  const [scanPreviewError, setScanPreviewError] = useState('')
  const [revisionNotes, setRevisionNotes] = useState('')
  const [requirementReviewing, setRequirementReviewing] = useState('')
  const [reviewingScanId, setReviewingScanId] = useState(null)
  const [checkingSubmissionId, setCheckingSubmissionId] = useState('')
  const [reviewingComplianceResultId, setReviewingComplianceResultId] = useState('')
  const [filePreviewLoadingId, setFilePreviewLoadingId] = useState('')
  const [filePreview, setFilePreview] = useState(null)
  const isSubmittingReturnRef = useRef(false)
  const isSubmittingApproveRef = useRef(false)
  const handledReqParamRef = useRef(null)

  // Edit project modal
  const [showEdit, setShowEdit] = useState(false)
  const [editForm, setEditForm] = useState({})
  const [editError, setEditError] = useState('')
  const [editErrors, setEditErrors] = useState({})
  const [editSubmitting, setEditSubmitting] = useState(false)
  const [editLgus, setEditLgus] = useState([])
  const [editPrograms, setEditPrograms] = useState([])
  const [editCycles, setEditCycles] = useState([])
  const [editChoicesLoading, setEditChoicesLoading] = useState(false)
  const [editChoicesError, setEditChoicesError] = useState('')
  const [editCyclesLoading, setEditCyclesLoading] = useState(false)
  const [editCyclesError, setEditCyclesError] = useState('')

  useEffect(() => {
    if (!showEdit) return
    let cancelled = false
    setEditChoicesLoading(true)
    setEditChoicesError('')
    Promise.all([
      lguApi.listLgus({ per_page: 200 }),
      programApi.listPrograms({ per_page: 200 }),
    ]).then(([lgus, programs]) => {
      if (!cancelled) {
        setEditLgus(lgus.data || [])
        setEditPrograms(programs.data || [])
      }
    }).catch(() => {
      if (!cancelled) setEditChoicesError('Unable to load LGU and program choices. Reopen Edit Details to retry.')
    }).finally(() => { if (!cancelled) setEditChoicesLoading(false) })
    return () => { cancelled = true }
  }, [showEdit])

  useEffect(() => {
    if (!showEdit || !editForm.program_id) return
    let cancelled = false
    setEditCyclesLoading(true)
    setEditCyclesError('')
    programApi.listProgramCycles(editForm.program_id, { fiscal_year: Number(editForm.fiscal_year) })
      .then((res) => {
        if (cancelled) return
        const cycles = (res.data || []).filter((cycle) => cycle.is_active !== false || String(cycle.id) === String(project?.program_cycle_id))
        setEditCycles(cycles)
        setEditForm((current) => {
          const valid = cycles.some((cycle) => String(cycle.id) === String(current.program_cycle_id))
          return { ...current, program_cycle_id: valid ? current.program_cycle_id : cycles.length === 1 ? String(cycles[0].id) : '' }
        })
      }).catch(() => {
        if (!cancelled) setEditCyclesError('Unable to load program cycles. Reopen Edit Details to retry.')
      }).finally(() => { if (!cancelled) setEditCyclesLoading(false) })
    return () => { cancelled = true }
  }, [showEdit, editForm.program_id, editForm.fiscal_year, project?.program_cycle_id])

  const selectedEditProgram = editPrograms.find((item) => String(item.id) === String(editForm.program_id))
  const editProgramType = selectedEditProgram?.program_type || (String(editForm.program_id) === String(project?.program_id) ? project?.program_type : undefined)

  const fetchProject = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await projectApi.getProject(id)
      setProject(res.data)
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to load the project record.')
    } finally {
      setLoading(false)
    }
  }, [id])

  const fetchRequirements = useCallback(async () => {
    try {
      const res = await projectApi.listProjectRequirements(id)
      setRequirements(res.data || [])
      setRequirementsError('')
    } catch (err) {
      setRequirementsError(apiErrorMessage(err, 'Unable to load project requirements. Please try again.'))
    }
  }, [id])

  const fetchActivity = useCallback(async () => {
    setActivityLoading(true)
    try {
      const res = await projectApi.getProjectActivity(id, { limit: 100 })
      setActivityLogs(res.data || [])
      setActivityError('')
    } catch (err) {
      setActivityError(apiErrorMessage(err, 'Unable to load activity log. Please try again.'))
    } finally {
      setActivityLoading(false)
    }
  }, [id])

  const fetchReportTemplates = useCallback(async () => {
    if (!isStaff()) return
    try {
      const res = await projectApi.listProjectRevisionReportTemplates()
      const revisionTemplateGroup = (res.data || []).find((item) => item.template_type === 'project_revision_report')
      const availableTemplates = (revisionTemplateGroup?.templates || []).filter((item) => item.available)
      setReportTemplates(availableTemplates)
      const defaultTemplateId = revisionTemplateGroup?.default_template_id || availableTemplates[0]?.id || ''
      setSelectedReportTemplateId((current) => current || defaultTemplateId)
    } catch {
      setReportTemplates([])
    }
  }, [])

  useEffect(() => { fetchProject(); fetchRequirements(); fetchActivity(); fetchReportTemplates() }, [fetchProject, fetchRequirements, fetchActivity, fetchReportTemplates])

  const openEvidenceModal = useCallback(async (req, openUpload = false) => {
    if (!req?.id) return
    const enriched = {
      ...req,
      project_id: project?.id || req.project_id,
      project_name: project?.project_name || req.project_name,
      source_project_code: project?.source_project_code || req.source_project_code,
      fiscal_year: project?.fiscal_year || req.fiscal_year,
      lgu_id: project?.lgu?.id || req.lgu_id,
      lgu_name: project?.lgu?.name || req.lgu_name,
      program_name: project?.program?.name || req.program_name,
      program_is_active: Boolean(project?.program?.is_active !== false && project?.program_is_active !== false),
    }
    setSelectedEvidenceReq(enriched)
    setEvidenceSubmissions([])
    setEvidenceLoading(true)
    setReviewUploadOpen(Boolean(openUpload))
    setUploadForm({
      source: isFieldOfficer() ? 'field_upload' : 'dms_ingestion',
      description: '',
      file: null,
    })
    setRevisionNotes('')
    setRequirementReviewing('')
    setCheckingSubmissionId('')
    setScanPreview(null)
    setScanPreviewError('')
    setReqError('')
    setReqNotice('')
    try {
      const [detailRes, subsRes] = await Promise.all([
        projectApi.getProjectRequirement(req.id).catch(() => ({ data: req })),
        projectApi.listRequirementSubmissions(req.id).catch(() => ({ data: [] })),
      ])
      const freshSubmissions = subsRes?.data || []
      const freshDetail = detailRes?.data || req
      const finalReq = {
        ...enriched,
        ...freshDetail,
        project_id: project?.id || req.project_id,
        project_name: project?.project_name || req.project_name,
        lgu_name: project?.lgu?.name || req.lgu_name,
        program_name: project?.program?.name || req.program_name,
        submission_count: Math.max(freshSubmissions.length, freshDetail.submission_count || 0),
        has_documentary_evidence: Boolean(
          freshDetail.has_documentary_evidence ||
          freshSubmissions.some(sub => (sub.document_files?.length > 0 || sub.files?.length > 0 || sub.document_count > 0))
        ),
      }
      setSelectedEvidenceReq(finalReq)
      setEvidenceSubmissions(freshSubmissions)
    } catch (err) {
      setReqError(err.response?.data?.message || 'Unable to load evidence history.')
    } finally {
      setEvidenceLoading(false)
    }
  }, [project])

  const closeEvidenceModal = useCallback(() => {
    setSelectedEvidenceReq(null)
    setEvidenceSubmissions([])
    setReviewUploadOpen(false)
    setRevisionNotes('')
    setReqError('')
    setReqNotice('')
    setCheckingSubmissionId('')
    setScanPreview(null)
    setScanPreviewError('')
    setUploadForm({
      source: isFieldOfficer() ? 'field_upload' : 'dms_ingestion',
      description: '',
      file: null,
    })
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('req')
      next.delete('requirement_id')
      return next
    }, { replace: true })
  }, [setSearchParams])

  // Deep-link to requirement evidence review
  useEffect(() => {
    const targetReqId = searchParams.get('req') || searchParams.get('requirement_id')
    if (targetReqId && requirements.length > 0) {
      if (handledReqParamRef.current !== targetReqId) {
        const match = requirements.find((r) => String(r.id) === String(targetReqId))
        if (match) {
          handledReqParamRef.current = targetReqId
          setActiveTab('requirements')
          openEvidenceModal(match)
        }
      }
    } else if (!targetReqId) {
      handledReqParamRef.current = null
    }
  }, [searchParams, requirements, openEvidenceModal])

  // Scan preview when file selected
  useEffect(() => {
    if (!selectedEvidenceReq?.project_id || !uploadForm.file || isFieldOfficer()) {
      setScanPreview(null)
      setScanPreviewError('')
      setScanPreviewLoading(false)
      return undefined
    }

    let ignore = false
    async function previewScan() {
      setScanPreviewLoading(true)
      setScanPreviewError('')
      try {
        const payload = new FormData()
        payload.append('project_id', selectedEvidenceReq.project_id)
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
  }, [selectedEvidenceReq?.project_id, uploadForm.file])

  // Revoke preview blob URL cleanup
  useEffect(() => () => {
    if (filePreview?.url) {
      window.URL.revokeObjectURL(filePreview.url)
    }
  }, [filePreview?.url])

  const handleUploadEvidenceSubmission = async (event) => {
    event?.preventDefault?.()
    if (!selectedEvidenceReq) return
    if (!uploadForm.file) {
      setReqError('Choose the received documentary file before recording intake.')
      return
    }

    setUploading(true)
    setReqError('')
    try {
      const payload = new FormData()
      payload.append('source', isFieldOfficer() ? 'field_upload' : uploadForm.source)
      if (uploadForm.description) {
        payload.append('description', uploadForm.description)
      }
      payload.append('file', uploadForm.file)
      await projectApi.createRequirementSubmission(selectedEvidenceReq.id, payload)
      setReqNotice('New documentary version recorded for this requirement.')
      setUploadForm({
        source: isFieldOfficer() ? 'field_upload' : 'dms_ingestion',
        description: '',
        file: null,
      })
      setReviewUploadOpen(false)
      setScanPreview(null)
      await Promise.all([
        fetchRequirements(),
        fetchProject(),
        fetchActivity(),
        openEvidenceModal(selectedEvidenceReq),
      ])
    } catch (error) {
      setReqError(error.response?.data?.message || 'Unable to record this documentary intake.')
    } finally {
      setUploading(false)
    }
  }

  const handleApproveEvidenceRequirement = async () => {
    if (!selectedEvidenceReq) return
    if (isSubmittingApproveRef.current) return
    if (!evidenceSubmissions.length) {
      setReqError('Upload documentary evidence before approving this requirement.')
      return
    }

    isSubmittingApproveRef.current = true
    setRequirementReviewing('approve')
    setReqError('')
    setReqNotice('')
    try {
      if (selectedEvidenceReq.document_category) {
        const wfStatus = selectedEvidenceReq.workflow_status
        const admin = isAdmin()
        if (wfStatus === 'approved') {
          setReqNotice('Requirement is already approved.')
          return
        }
        if (admin && (!wfStatus || wfStatus === 'draft' || wfStatus === 'submitted' || wfStatus === 'resubmitted' || wfStatus === 'under_verification')) {
          setReqError('This requirement must be verified and recommended by Technical Staff before Provincial Director approval.')
          return
        }
        if (wfStatus === 'draft' || !wfStatus) {
          await monitoringApi.submitRequirementWorkflow(selectedEvidenceReq.id)
          await monitoringApi.verifyRequirementWorkflow(selectedEvidenceReq.id)
          await monitoringApi.staffApproveRequirementWorkflow(selectedEvidenceReq.id)
          setReqNotice('Requirement verified and staff-approved. Forwarded for Provincial Director approval.')
        } else if (wfStatus === 'submitted' || wfStatus === 'resubmitted') {
          await monitoringApi.verifyRequirementWorkflow(selectedEvidenceReq.id)
          await monitoringApi.staffApproveRequirementWorkflow(selectedEvidenceReq.id)
          setReqNotice('Requirement verified and staff-approved. Forwarded for Provincial Director approval.')
        } else if (wfStatus === 'under_verification') {
          await monitoringApi.staffApproveRequirementWorkflow(selectedEvidenceReq.id)
          setReqNotice('Requirement staff-approved. Forwarded for Provincial Director approval.')
        } else if (wfStatus === 'staff_approved' || wfStatus === 'pending_provincial_approval') {
          if (admin) {
            await monitoringApi.provincialApproveRequirementWorkflow(selectedEvidenceReq.id)
            setReqNotice('Attachment approved. Requirement marked Compliant and approved.')
          } else {
            setReqNotice('Requirement is already staff-approved and awaiting Provincial Director approval.')
            return
          }
        } else {
          await monitoringApi.provincialApproveRequirementWorkflow(selectedEvidenceReq.id)
          setReqNotice('Attachment approved.')
        }
      } else {
        await projectApi.updateProjectRequirement(selectedEvidenceReq.id, { status: 'compliant' })
        setReqNotice('Attachment approved. Requirement marked Compliant.')
      }

      setRevisionNotes('')
      await Promise.all([
        fetchRequirements(),
        fetchProject(),
        fetchActivity(),
        openEvidenceModal(selectedEvidenceReq),
      ])
    } catch (error) {
      setReqError(error.response?.data?.message || 'Unable to approve this requirement attachment.')
    } finally {
      isSubmittingApproveRef.current = false
      setRequirementReviewing('')
    }
  }

  const handleReturnEvidenceForRevision = async (returnData) => {
    if (!selectedEvidenceReq) return
    if (isSubmittingReturnRef.current) return
    if (!evidenceSubmissions.length) {
      setReqError('Upload documentary evidence before returning this requirement for revision.')
      return
    }
    const isObject = typeof returnData === 'object' && returnData !== null
    const notes = isObject
      ? (returnData.reason || '')
      : (typeof returnData === 'string' ? returnData : revisionNotes)
    const deficiencies = isObject ? returnData.deficiencies : undefined

    if (!notes.trim() && (!deficiencies || deficiencies.length === 0)) {
      setReqError('Revision notes or at least one deficiency item is required so the correction needed is clear.')
      return
    }

    isSubmittingReturnRef.current = true
    setRequirementReviewing('revision')
    setReqError('')
    setReqNotice('')
    try {
      if (!selectedEvidenceReq.workflow_status || selectedEvidenceReq.workflow_status === 'draft') {
        if (selectedEvidenceReq.document_category) {
          await monitoringApi.submitRequirementWorkflow(selectedEvidenceReq.id)
        }
      }

      const payload = {
        reason: notes.trim() || undefined,
        ...(deficiencies && deficiencies.length > 0 ? { deficiencies } : {}),
      }

      try {
        await monitoringApi.returnRequirementWorkflow(selectedEvidenceReq.id, payload)
      } catch (workflowErr) {
        if (!selectedEvidenceReq.document_category && isWorkflowNotApplicableError(workflowErr)) {
          await projectApi.returnProjectRequirementForRevision(selectedEvidenceReq.id, {
            review_notes: notes.trim(),
          })
        } else {
          throw workflowErr
        }
      }

      setReqNotice('Requirement returned for revision.')
      setRevisionNotes('')
      await Promise.all([
        fetchRequirements(),
        fetchProject(),
        fetchActivity(),
        openEvidenceModal(selectedEvidenceReq),
      ])
    } catch (error) {
      setReqError(error.response?.data?.message || 'Unable to return this requirement for revision.')
    } finally {
      isSubmittingReturnRef.current = false
      setRequirementReviewing('')
    }
  }

  const handleEvidenceStatusChange = async (requirementId, data) => {
    if (!requirementId) return
    setReqError('')
    setReqNotice('')
    try {
      const response = await projectApi.createChangeStatusRequest(requirementId, data)
      if (data.auto_approve) {
        setReqNotice('Requirement status updated successfully.')
        await Promise.all([
          fetchRequirements(),
          fetchProject(),
          fetchActivity(),
          selectedEvidenceReq ? openEvidenceModal(selectedEvidenceReq) : Promise.resolve(),
        ])
      } else {
        setReqNotice('Status change request submitted for administrator review.')
      }
      return response
    } catch (error) {
      setReqError(error.response?.data?.message || error.response?.data?.error || 'Unable to update status.')
      throw error
    }
  }

  const handleRunComplianceCheck = async (submissionId, options = {}) => {
    if (!submissionId || !selectedEvidenceReq) return
    setCheckingSubmissionId(`${submissionId}:${options.use_prior_year_reference ? 'prior' : 'current'}`)
    setReqError('')
    try {
      const response = await projectApi.runSubmissionComplianceCheck(submissionId, options)
      const result = response.data
      setReqNotice(
        result?.status === 'ready_for_approval'
          ? 'Compliance checker found no deterministic issues. Staff approval is still recorded separately.'
          : 'Compliance checker completed. Review findings before approving or returning.',
      )
      await openEvidenceModal(selectedEvidenceReq)
    } catch (error) {
      setReqError(error.response?.data?.message || 'Unable to run documentary compliance check.')
    } finally {
      setCheckingSubmissionId('')
    }
  }

  const handleRecordComplianceReview = async (resultId, payload) => {
    if (!resultId || !selectedEvidenceReq) return
    setReviewingComplianceResultId(resultId)
    setReqError('')
    try {
      await projectApi.reviewComplianceResult(resultId, payload)
      setReqNotice('Reviewer decision recorded for the compliance result.')
      await openEvidenceModal(selectedEvidenceReq)
    } catch (error) {
      setReqError(error.response?.data?.message || 'Unable to record compliance review decision.')
    } finally {
      setReviewingComplianceResultId('')
    }
  }

  const handleRescanSubmission = async (submissionId) => {
    if (!submissionId || !selectedEvidenceReq) return
    setReviewingScanId(`rescan-${submissionId}`)
    setReqError('')
    try {
      await projectApi.scanSubmissionDocument(submissionId)
      setReqNotice('Document intelligence scan completed.')
      await openEvidenceModal(selectedEvidenceReq)
    } catch (error) {
      setReqError(error.response?.data?.message || 'Unable to run document intelligence scan.')
    } finally {
      setReviewingScanId(null)
    }
  }

  const handleRefreshDestination = async (submissionId) => {
    if (!submissionId || !selectedEvidenceReq) return
    setReviewingScanId(`refresh-destination-${submissionId}`)
    setReqError('')
    try {
      await projectApi.refreshSubmissionDestination(submissionId)
      setReqNotice('Destination identity refreshed.')
      await openEvidenceModal(selectedEvidenceReq)
    } catch (error) {
      setReqError(error.response?.data?.message || 'Unable to refresh document destination check.')
    } finally {
      setReviewingScanId(null)
    }
  }

  const handleReviewScan = async (scan, decision) => {
    if (!scan?.id || !selectedEvidenceReq) return
    setReviewingScanId(scan.id)
    setReqError('')
    try {
      await projectApi.reviewSubmissionScan(scan.id, { decision })
      setReqNotice(
        decision === 'accepted'
          ? 'Mapping accepted. Review attachment before approving compliance.'
          : 'Mapping rejected.',
      )
      await openEvidenceModal(selectedEvidenceReq)
    } catch (error) {
      setReqError(error.response?.data?.message || 'Unable to record scan review.')
    } finally {
      setReviewingScanId(null)
    }
  }

  const handlePreviewFile = async (file) => {
    if (!file?.id) {
      setReqError('No previewable file is attached to this intake record.')
      return
    }
    setFilePreviewLoadingId(file.id)
    setReqError('')
    try {
      const response = await projectApi.downloadSubmissionFile(file.id)
      const mimeType = response.headers?.['content-type'] || file.mime_type || 'application/octet-stream'
      const blob = new Blob([response.data], { type: mimeType })
      const url = window.URL.createObjectURL(blob)
      setFilePreview({
        url,
        fileName: file.file_name || `submission-${file.id}`,
        mimeType,
        sizeBytes: file.file_size_bytes,
        complianceResult: complianceResultForFile(file),
      })
    } catch (error) {
      setReqError(error.response?.data?.message || 'Unable to preview the selected file.')
    } finally {
      setFilePreviewLoadingId('')
    }
  }

  const handleDownloadFile = async (file) => {
    if (!file?.id) return
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
      setReqError(error.response?.data?.message || 'Unable to download the selected file.')
    }
  }

  const complianceResultForFile = (file) => {
    if (file?.latest_compliance_result) return file.latest_compliance_result
    if (file?.compliance_result) return file.compliance_result
    const fileId = Number(file?.id)
    if (!Number.isFinite(fileId)) return null
    for (const submission of evidenceSubmissions) {
      const results = [
        submission.latest_compliance_result,
        ...(submission.compliance_results || []),
      ].filter(Boolean)
      const exact = results.find((result) => Number(result.document_file_id) === fileId)
      if (exact) return exact
      const belongs = (submission.document_files || []).some(
        (df) => Number(df.id) === fileId,
      )
      if (belongs && results.length === 1 && !results[0].document_file_id) {
        return results[0]
      }
    }
    return null
  }

  useEffect(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current)
    debounceTimerRef.current = setTimeout(() => {
      setAppliedSearch(searchInput)
    }, 300)
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current)
    }
  }, [searchInput])

  useEffect(() => {
    const selected = reportTemplates.find((item) => item.id === selectedReportTemplateId)
    setReportPlaceholderValues({ ...(selected?.placeholder_defaults || {}) })
    setReportPreview(null)
  }, [reportTemplates, selectedReportTemplateId])

  const handleTransition = async () => {
    if (!transitionTo || !transitionReason.trim()) {
      setTransitionError('Next phase and reason are required.')
      return
    }
    setTransitioning(true)
    setTransitionError('')
    try {
      await projectApi.transitionProjectPhase(id, { to_phase: transitionTo, reason: transitionReason })
      setShowTransition(false)
      setTransitionTo('')
      setTransitionReason('')
      fetchProject()
    } catch (err) {
      setTransitionError(err.response?.data?.message || 'Unable to transition this project phase.')
    } finally {
      setTransitioning(false)
    }
  }

  const handleSearchSubmit = (event) => {
    event.preventDefault()
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current)
    setAppliedSearch(searchInput)
  }

  const handleClearFilters = () => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current)
    setSearchInput('')
    setAppliedSearch('')
    setPhaseFilter('')
    setStatusFilter('')
    setMandatoryFilter('')
  }

  const handleUpdateRequirement = async () => {
    if (!editingReq) return
    setReqSubmitting(true)
    setReqError('')
    setReqNotice('')
    try {
      const data = { status: reqForm.status }
      if (reqForm.status === 'waived' && reqForm.waived_reason) {
        data.waived_reason = reqForm.waived_reason
      }
      const reviewedStatuses = ['compliant', 'non_compliant', 'waived']
      const isReversingReviewed = reviewedStatuses.includes(editingReq.status) && editingReq.status !== reqForm.status
      if (isReversingReviewed) {
        if (isAdmin()) {
          await projectApi.createChangeStatusRequest(editingReq.id, {
            requested_status: reqForm.status,
            justification: reqForm.waived_reason || 'Administrator status change from reviewed status.',
            auto_approve: true,
          })
          setReqNotice('Requirement status updated successfully.')
        } else {
          await projectApi.createChangeStatusRequest(editingReq.id, {
            requested_status: reqForm.status,
            justification: reqForm.waived_reason || 'Staff-requested reversal from reviewed status.',
          })
          setReqNotice('Status change request submitted for administrator review.')
        }
      } else {
        await projectApi.updateProjectRequirement(editingReq.id, data)
      }
      setEditingReq(null)
      fetchRequirements()
      fetchProject()
    } catch (err) {
      setReqError(err.response?.data?.message || 'Unable to update the requirement status.')
    } finally {
      setReqSubmitting(false)
    }
  }

  const handleReturnForRevision = async () => {
    if (!editingReq) return
    const notes = reqForm.revision_notes.trim()
    if (!notes) {
      setReqError('Revision notes are required when returning a requirement for correction.')
      return
    }
    setReqSubmitting(true)
    setReqError('')
    setReqNotice('')
    try {
      if (editingReq.document_category) {
        if (!editingReq.workflow_status || editingReq.workflow_status === 'draft') {
          await monitoringApi.submitRequirementWorkflow(editingReq.id)
        }
        try {
          await monitoringApi.returnRequirementWorkflow(editingReq.id, {
            reason: notes,
          })
        } catch (workflowErr) {
          if (!editingReq.document_category && isWorkflowNotApplicableError(workflowErr)) {
            await projectApi.returnProjectRequirementForRevision(editingReq.id, {
              review_notes: notes,
            })
          } else {
            throw workflowErr
          }
        }
      } else {
        await projectApi.returnProjectRequirementForRevision(editingReq.id, {
          review_notes: notes,
        })
      }
      setEditingReq(null)
      setReqNotice('Requirement returned for revision. It remains under review until corrected or escalated after compliance deadline becomes overdue.')
      fetchRequirements()
      fetchProject()
      fetchActivity()
    } catch (err) {
      setReqError(err.response?.data?.message || err.response?.data?.error || err.message || 'Unable to return this requirement for revision.')
    } finally {
      setReqSubmitting(false)
    }
  }

  const handleDownloadRevisionReport = async () => {
    setReportDownloading(true)
    setReqNotice('')
    setReqError('')
    try {
      const placeholderOverrides = Object.fromEntries(
        Object.entries(reportPlaceholderValues)
          .map(([key, value]) => [key, String(value || '').trim()])
          .filter(([, value]) => value)
      )
      const response = await projectApi.downloadProjectRevisionReport(id, {
        template_id: selectedReportTemplateId || undefined,
        placeholder_overrides: placeholderOverrides,
      })
      const blob = new Blob([response.data], {
        type: response.headers?.['content-type'] || 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
      const disposition = response.headers?.['content-disposition'] || ''
      const match = disposition.match(/filename="?([^"]+)"?/i)
      const fileName = match?.[1] || `project-${id}-correction-report.docx`
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = fileName
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      setTimeout(() => window.URL.revokeObjectURL(url), 1500)
      setReqNotice('Correction report generated from the returned-for-revision history.')
      setReportModalOpen(false)
      fetchActivity()
    } catch (err) {
      setReqError(err.response?.data?.message || 'Unable to generate the correction report.')
    } finally {
      setReportDownloading(false)
    }
  }

  const handleDownloadRequirementReport = async (row, options = {}) => {
    setDownloadingReqId(row.id)
    setReqNotice('')
    setReqError('')
    try {
      const response = await projectApi.downloadRequirementCorrectionReport(row.id, options)
      const blob = new Blob([response.data], {
        type: response.headers?.['content-type'] || 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
      const disposition = response.headers?.['content-disposition'] || ''
      const match = disposition.match(/filename="?([^"]+)"?/i)
      const fileName = match?.[1] || `requirement-${row.id}-correction-report.docx`
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = fileName
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      setTimeout(() => window.URL.revokeObjectURL(url), 1500)
      setReqNotice(`Correction report downloaded for ${row.requirement_name}.`)
      fetchActivity()
    } catch (err) {
      setReqError(err.response?.data?.message || 'Unable to download the correction report.')
    } finally {
      setDownloadingReqId(null)
    }
  }

  const handlePreviewRevisionReport = async () => {
    setReportPreviewLoading(true)
    setReqError('')
    try {
      const placeholderOverrides = Object.fromEntries(
        Object.entries(reportPlaceholderValues)
          .map(([key, value]) => [key, String(value || '').trim()])
          .filter(([, value]) => value)
      )
      const response = await projectApi.previewProjectRevisionReport(id, {
        template_id: selectedReportTemplateId || undefined,
        placeholder_overrides: placeholderOverrides,
      })
      setReportPreview(response.data || null)
    } catch (err) {
      setReqError(err.response?.data?.message || 'Unable to preview the correction report.')
    } finally {
      setReportPreviewLoading(false)
    }
  }

  const handleEditProject = async (e) => {
    e.preventDefault()
    const isProjectKindRequired = Boolean(editProgramType)
    const validationErrors = validateProjectFields(editForm, {
      requireCore: true,
      requireProjectKind: isProjectKindRequired,
      requireProjectCode: Boolean(project?.source_project_code),
    })
    if (editCycles.length > 1 && !editForm.program_cycle_id) validationErrors.program_cycle_id = 'Please select a program cycle.'
    if (editChoicesError || editCyclesError || editCyclesLoading || editChoicesLoading) return
    if (hasProjectValidationErrors(validationErrors)) {
      setEditErrors(validationErrors)
      setEditError('Please correct the highlighted fields.')
      return
    }
    setEditErrors({})
    setEditSubmitting(true)
    setEditError('')
    try {
      const payload = { ...editForm }
      payload.lgu_id = Number(payload.lgu_id)
      payload.program_id = Number(payload.program_id)
      payload.fiscal_year = Number(payload.fiscal_year)
      payload.program_cycle_id = payload.program_cycle_id ? Number(payload.program_cycle_id) : null
      if (payload.source_project_code?.trim()) payload.source_project_code = payload.source_project_code.trim()
      else delete payload.source_project_code
      payload.budget_amount = payload.budget_amount === '' ? null : Number(String(payload.budget_amount).replace(/,/g, ''))
      payload.target_start_date = payload.target_start_date || null
      payload.target_end_date = payload.target_end_date || null
      if (payload.overall_status === project.overall_status) delete payload.overall_status
      if (!payload.project_kind) delete payload.project_kind
      await projectApi.updateProject(id, payload)
      setShowEdit(false)
      await Promise.all([fetchProject(), fetchRequirements(), fetchActivity()])
    } catch (err) {
      const data = err.response?.data
      setEditErrors(data?.errors || {})
      setEditError(data?.message || (data?.errors ? Object.values(data.errors).join(', ') : 'Unable to update the project.'))
    } finally {
      setEditSubmitting(false)
    }
  }

  const filteredRequirements = useMemo(() => {
    let list = requirements
    if (statusFilter === 'returned_for_revision') {
      list = list.filter((r) => r.workflow_status === 'returned_for_revision')
      return filterRequirements(list, {
        search: appliedSearch,
        phase: phaseFilter,
        mandatory: mandatoryFilter,
      })
    }
    return filterRequirements(list, {
      search: appliedSearch,
      phase: phaseFilter,
      status: statusFilter,
      mandatory: mandatoryFilter,
    })
  }, [requirements, appliedSearch, phaseFilter, statusFilter, mandatoryFilter])
  const activeFilterCount = countActiveFilters({
    search: searchInput,
    phase: phaseFilter,
    status: statusFilter,
    mandatory: mandatoryFilter,
  })

  if (loading) {
    return (
      <div className="animate-fade-in flex items-center justify-center py-20">
        <div className="text-slate-400">Loading project...</div>
      </div>
    )
  }

  if (error || !project) {
    return (
      <div className="animate-fade-in">
        <Breadcrumb items={[{ label: 'Projects', to: ROUTES.PROJECTS }, { label: 'Not found' }]} />
        <div className="glass-panel p-8 mt-4 text-center">
          <p className="status-text-danger">{error || 'Project not found'}</p>
        </div>
      </div>
    )
  }

  const summary = project.requirement_summary || {}
  const revisionRequirements = project.revision_requirements || []
  const historicalRevisionRequirements = project.historical_revision_requirements || []
  const selectedReportTemplate = reportTemplates.find((item) => item.id === selectedReportTemplateId)
  const reportVariableFields = editableTemplateVariables(selectedReportTemplate)
  const phaseLog = project.phase_history || []
  const currentPhase = project.current_phase
  const importedContext = Object.entries(project.custom_fields?.imported_context || {})
  const workbookFieldLocks = project.workbook_field_locks || {}
  const isWorkbookFieldLocked = (field) => Boolean(workbookFieldLocks[field]?.length)
  const workbookLockLabel = (field) => {
    const lock = workbookFieldLocks[field]?.[0]
    return lock ? `Locked in workbook cell ${lock.cell_ref}` : ''
  }
  const isOutsideActiveFiscalYear = selectedFiscalYear && project.fiscal_year && Number(project.fiscal_year) !== Number(selectedFiscalYear)
  const isProgramInactive = Boolean(project?.program?.is_active === false || project?.program_is_active === false)

  const availableTransitions = {
    pre_implementation: ['implementation'],
    implementation: ['completion'],
    completion: [],
  }[currentPhase] || []

  const renderRequirementActions = (row) => {
      const isInactive = row.is_active === false
      const isWaived = row.status === 'waived'
      const hasEvidence = Boolean(row.has_documentary_evidence || row.submission_count > 0)

      if (isInactive) {
        return (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <button
              type="button"
              onClick={() => setViewingDetailReq(row)}
              className="inline-flex min-h-8 items-center rounded border border-brand-border px-2.5 py-1 text-xs font-medium text-brand-text hover:bg-brand-surface focus-visible:outline-2 focus-visible:outline-brand-primary"
            >
              View details
            </button>
            {row.has_documentary_evidence && (
              <button
                type="button"
                onClick={() => openEvidenceModal(row)}
                className="inline-flex min-h-8 items-center rounded border border-brand-border px-2.5 py-1 text-xs font-medium text-brand-primary hover:bg-brand-surface focus-visible:outline-2 focus-visible:outline-brand-primary"
              >
                View Evidence
              </button>
            )}
          </div>
        )
      }

      if (isProgramInactive) {
        return <span className="text-xs font-medium text-amber-600 dark:text-amber-400">Paused</span>
      }

      const isNotApplicable = row.applicability === 'not_applicable'
      const canOperateEvidence = isFieldOfficer() || isStaff()
      const canUpdateStatus = (isStaff() || isAdmin()) && !isNotApplicable
      const canManageApplicability = isStaff() || isAdmin()
      const ineligibility = checkApplicabilityEligibility(row)

      return (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          {canOperateEvidence && (!isNotApplicable || hasEvidence) && (
            <button
              type="button"
              onClick={() => openEvidenceModal(row, !hasEvidence)}
              className="inline-flex min-h-8 items-center rounded border border-brand-border px-2.5 py-1 text-xs font-medium text-brand-primary hover:bg-brand-surface focus-visible:outline-2 focus-visible:outline-brand-primary"
            >
              {hasEvidence ? 'View Evidence' : 'Upload Evidence'}
            </button>
          )}
          {canUpdateStatus && (
            <button
              type="button"
              onClick={() => {
                setEditingReq(row)
                setReqForm({
                  status: row.status,
                  waived_reason: row.waived_reason || '',
                  revision_notes: '',
                })
                setReqError('')
              }}
              className="min-h-7 rounded text-xs font-medium text-brand-text-muted hover:text-brand-primary hover:underline focus-visible:outline-2 focus-visible:outline-brand-primary"
            >
              Update status
            </button>
          )}
          {canManageApplicability && (
            isNotApplicable ? (
              <button
                type="button"
                onClick={() => {
                  setApplicabilityModalReq(row)
                  setApplicabilityModalMode('restore_applicable')
                }}
                className="min-h-7 rounded text-xs font-medium text-brand-primary hover:underline focus-visible:outline-2 focus-visible:outline-brand-primary"
              >
                Restore applicability
              </button>
            ) : (
              <span className="relative inline-flex items-center">
                <button
                  type="button"
                  onClick={() => {
                    if (!ineligibility.eligible) return
                    setApplicabilityModalReq(row)
                    setApplicabilityModalMode('set_not_applicable')
                  }}
                  disabled={!ineligibility.eligible}
                  aria-disabled={!ineligibility.eligible ? 'true' : undefined}
                  aria-describedby={!ineligibility.eligible ? `applicability-reason-${row.id}` : undefined}
                  title={ineligibility.reason || 'Mark this requirement Not Applicable for this project'}
                  className={`min-h-7 rounded text-xs font-medium ${
                    !ineligibility.eligible
                      ? 'cursor-not-allowed text-brand-text-muted/50'
                      : 'text-brand-text-muted hover:text-brand-primary hover:underline'
                  } focus-visible:outline-2 focus-visible:outline-brand-primary`}
                >
                  Mark Not Applicable
                </button>
                {!ineligibility.eligible && ineligibility.reason && (
                  <span id={`applicability-reason-${row.id}`} className="sr-only">
                    {ineligibility.reason}
                  </span>
                )}
              </span>
            )
          )}
          {(isWaived || isNotApplicable) && (
            <button
              type="button"
              onClick={() => setViewingDetailReq(row)}
              className="min-h-7 rounded text-xs font-medium text-brand-text-muted hover:text-brand-primary hover:underline focus-visible:outline-2 focus-visible:outline-brand-primary"
            >
              View details
            </button>
          )}
        </div>
      )
  }

  const logColumns = [
    { key: 'from_phase', label: 'From', render: (row) => {
      const badge = PHASE_BADGE[row.from_phase]
      return badge ? (
        <span className={badgeClassForStatus(row.from_phase)}>{badge.label}</span>
      ) : <span className="text-slate-600 dark:text-slate-400">—</span>
    }},
    { key: 'to_phase', label: 'To', render: (row) => {
      const badge = PHASE_BADGE[row.to_phase] || { label: formatMachineLabel(row.to_phase) }
      return <span className={badgeClassForStatus(row.to_phase)}>{badge.label}</span>
    }},
    { key: 'notes', label: 'Reason', render: (row) => row.notes || '—' },
    { key: 'transitioned_at', label: 'Date', render: (row) => row.transitioned_at ? new Date(row.transitioned_at).toLocaleDateString() : '—' },
  ]

  const activityColumns = [
    { key: 'created_at', label: 'Date', render: (row) => row.created_at ? new Date(row.created_at).toLocaleString('en-PH') : '—' },
    { key: 'action', label: 'Action', render: (row) => formatMachineLabel(row.action) },
    { key: 'entity_type', label: 'Record', render: (row) => formatMachineLabel(row.entity_type) },
    { key: 'user_name', label: 'Actor', render: (row) => row.user_name || row.user_email || 'System' },
    { key: 'entity_id', label: 'ID', render: (row) => row.entity_id },
  ]

  const revisionColumns = [
    { key: 'requirement_name', label: 'Requirement', render: (row) => (
      <div>
        <div className="font-medium text-slate-900 dark:text-slate-200">{row.requirement_name}</div>
        {row.annex_reference && <div className="text-xs text-slate-600 dark:text-slate-400">{row.annex_reference}</div>}
      </div>
    )},
    { key: 'phase_name', label: 'Phase' },
    { key: 'status', label: 'Current Status', render: (row) => <span className={badgeClassForStatus(row.status)}>{formatStatus(row.status)}</span> },
    { key: 'latest_revision', label: 'Latest Revision Note', render: (row) => row.latest_revision?.notes || '—' },
    { key: 'returned_at', label: 'Returned On', render: (row) => row.latest_revision?.returned_at ? new Date(row.latest_revision.returned_at).toLocaleDateString('en-PH') : '—' },
    { key: 'report_action', label: 'Correction Report', render: (row) => (
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          icon={Download}
          loading={downloadingReqId === row.id}
          disabled={downloadingReqId !== null}
          onClick={() => handleDownloadRequirementReport(row)}
        >
          Download Report
        </Button>
        {row.revision_count > 1 && (
          <span className="text-xs text-slate-600 dark:text-slate-400">
            ({row.revision_count} returns)
          </span>
        )}
      </div>
    )},
  ]

  const historicalRevisionColumns = [
    { key: 'requirement_name', label: 'Requirement', render: (row) => (
      <div>
        <div className="font-medium text-slate-900 dark:text-slate-200">{row.requirement_name}</div>
        {row.annex_reference && <div className="text-xs text-slate-600 dark:text-slate-400">{row.annex_reference}</div>}
      </div>
    )},
    { key: 'phase_name', label: 'Phase' },
    { key: 'status', label: 'Current Status', render: (row) => <span className={badgeClassForStatus(row.status)}>{formatStatus(row.status)}</span> },
    { key: 'latest_revision', label: 'Previous Revision Note', render: (row) => row.latest_revision?.notes || '—' },
    { key: 'returned_at', label: 'Returned On', render: (row) => row.latest_revision?.returned_at ? new Date(row.latest_revision.returned_at).toLocaleDateString('en-PH') : '—' },
    { key: 'report_action', label: 'Historical Report', render: (row) => (
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          icon={Download}
          loading={downloadingReqId === row.id}
          disabled={downloadingReqId !== null || !row.has_report}
          onClick={() => handleDownloadRequirementReport(row, { report_id: row.latest_revision?.report_id })}
        >
          Download Report
        </Button>
      </div>
    )},
  ]

  return (
    <div className="animate-fade-in">
      <Breadcrumb
        items={[
          { label: 'Projects', to: ROUTES.PROJECTS },
          { label: project.project_name },
        ]}
      />
      {isOutsideActiveFiscalYear && (
        <InlineAlert type="warning" className="mb-4">
          This project belongs to FY {project.fiscal_year}. Your active system filter is FY {selectedFiscalYear}.
        </InlineAlert>
      )}

      {/* Context Bar */}
      <GlassPanel className="mb-6" noPadding>
        <div className="p-6 pb-0">
          <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 mb-6">
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-3 mb-2">
                <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 m-0">{project.project_name}</h1>
                {PHASE_BADGE[currentPhase] && (
                  <span className={badgeClassForStatus(currentPhase)}>{PHASE_BADGE[currentPhase].label}</span>
                )}
                {PROJECT_STATUS_BADGE[project.overall_status] && (
                  <span className={badgeClassForStatus(project.overall_status)}>{PROJECT_STATUS_BADGE[project.overall_status].label}</span>
                )}
              </div>
              <div className="text-slate-600 dark:text-slate-400 text-sm flex flex-wrap items-center gap-4 mt-2">
                <span className="flex items-center gap-1.5"><FolderKanban className="w-4 h-4 text-slate-400 dark:text-slate-400" /> FY {project.fiscal_year}</span>
                {project.lgu && <span className="flex items-center gap-1.5"><MapPin className="w-4 h-4 text-slate-400 dark:text-slate-400" /> {project.lgu.name}{project.lgu.municipality ? `, ${project.lgu.municipality}` : ''}</span>}
                {project.program && <span className="flex items-center gap-1.5"><Briefcase className="w-4 h-4 text-slate-400 dark:text-slate-400" /> {project.program.name}</span>}
              </div>
            </div>

            {/* Actions */}
            {isProgramInactive ? (
              <div className="flex flex-wrap gap-2 items-center">
                <ProgramPausedBanner programId={project.program?.id || project.program_id} />
              </div>
            ) : (
              (isAdmin() || isStaff()) && (
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" icon={Edit} onClick={() => {
                    setEditCycles([])
                    setEditCyclesLoading(true)
                    setEditForm({
                      project_name: project.project_name,
                      lgu_id: String(project.lgu_id || project.lgu?.id || ''),
                      program_id: String(project.program_id || project.program?.id || ''),
                      program_cycle_id: String(project.program_cycle_id || project.program_cycle?.id || ''),
                      fiscal_year: project.fiscal_year,
                      source_project_code: project.source_project_code || '',
                      project_kind: project.project_kind || (project.program_type === 'infrastructure' ? 'infrastructure' : ''),
                      overall_status: project.overall_status,
                      budget_amount: project.budget_amount ?? '',
                      target_start_date: project.target_start_date || '',
                      target_end_date: project.target_end_date || '',
                      notes: project.notes || '',
                    })
                    setEditError('')
                    setEditErrors({})
                    setShowEdit(true)
                  }}>Edit Details</Button>
                  {availableTransitions.length > 0 && (
                  <Button icon={ArrowRight} onClick={() => { setTransitionError(''); setShowTransition(true) }}>Move to Next Phase</Button>
                  )}
                </div>
              )
            )}
          </div>

          {/* Compact requirement summary */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
            <KpiCard title="Requirements" value={summary.total || 0} subtitle="tracked" icon={FileText} color="blue" />
            <KpiCard title="Compliant" value={summary.compliant || 0} subtitle="verified" icon={CheckCircle2} color="emerald" />
            <KpiCard title="Pending" value={summary.pending || 0} subtitle="awaiting review" icon={Clock} color="amber" />
            <KpiCard title="Non-compliant" value={summary.non_compliant || 0} subtitle="needs action" icon={AlertTriangle} color="red" />
            <KpiCard title="Waived" value={summary.waived || 0} subtitle="exempted" color="slate" />
          </div>

          {/* Sub Navigation Tabs */}
          <div className="flex gap-6 border-b border-slate-200 dark:border-slate-700/50 px-2">
            {['overview', 'requirements', 'history', 'activity'].map(tab => (
              <button
                key={tab}
                onClick={() => handleTabChange(tab)}
                className={`py-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab
                    ? 'status-text-info border-brand-primary'
                    : 'text-slate-600 dark:text-slate-400 border-transparent hover:text-slate-900 dark:hover:text-slate-300'
                }`}
              >
                {tab === 'history' ? 'Phase Log' : tab === 'activity' ? 'Activity Log' : formatMachineLabel(tab)}
              </button>
            ))}
          </div>
        </div>
      </GlassPanel>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {reqNotice && (
            <FeedbackToast type="success" message={reqNotice} onDismiss={() => setReqNotice('')} />
          )}
          {reqError && !editingReq && (
            <InlineAlert type="error" onDismiss={() => setReqError('')}>
              {reqError}
            </InlineAlert>
          )}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <GlassPanel>
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-200 mb-4">Project Details</h3>
              <dl className="text-sm divide-y divide-slate-200 dark:divide-slate-700/50">
                <div className="flex justify-between py-2">
                  <dt className="text-slate-600 dark:text-slate-400">LGU</dt>
                  <dd className="text-slate-900 dark:text-slate-200 font-medium">{project.lgu?.name || '—'}</dd>
                </div>
                <div className="flex justify-between py-2">
                  <dt className="text-slate-600 dark:text-slate-400">Program</dt>
                  <dd className="text-slate-900 dark:text-slate-200 font-medium">{project.program?.name || '—'}</dd>
                </div>
                <div className="flex justify-between py-2">
                  <dt className="text-slate-600 dark:text-slate-400">Program Cycle</dt>
                  <dd className="text-slate-900 dark:text-slate-200 font-medium">{project.program_cycle?.name || project.program_cycle_name || '—'}</dd>
                </div>
                <div className="flex justify-between py-2">
                  <dt className="text-slate-600 dark:text-slate-400">Fiscal Year</dt>
                  <dd className="text-slate-900 dark:text-slate-200 font-medium">{project.fiscal_year}</dd>
                </div>
                <div className="flex justify-between py-2">
                  <dt className="text-slate-600 dark:text-slate-400">Project Code</dt>
                  <dd className="text-slate-900 dark:text-slate-200 font-medium">{project.source_project_code || '—'}</dd>
                </div>
                <div className="flex justify-between py-2">
                  <dt className="text-slate-600 dark:text-slate-400">Budget</dt>
                  <dd className="text-slate-900 dark:text-slate-200 font-medium">{project.budget_amount ? formatCurrency(project.budget_amount) : '—'}</dd>
                </div>
                <div className="flex justify-between py-2">
                  <dt className="text-slate-600 dark:text-slate-400">Target Start</dt>
                  <dd className="text-slate-900 dark:text-slate-200 font-medium">{project.target_start_date ? new Date(project.target_start_date).toLocaleDateString() : '—'}</dd>
                </div>
                <div className="flex justify-between py-2">
                  <dt className="text-slate-600 dark:text-slate-400">Target End</dt>
                  <dd className="text-slate-900 dark:text-slate-200 font-medium">{project.target_end_date ? new Date(project.target_end_date).toLocaleDateString() : '—'}</dd>
                </div>
                <div className="flex justify-between py-2">
                  <dt className="text-slate-600 dark:text-slate-400">{getProgressLabel(project)}</dt>
                  <dd className="text-slate-900 dark:text-slate-200 font-medium">{project.physical_completion_pct}%</dd>
                </div>
                <div className="flex justify-between pt-2">
                  <dt className="text-slate-600 dark:text-slate-400">Created</dt>
                  <dd className="text-slate-900 dark:text-slate-200 font-medium">{project.created_at ? new Date(project.created_at).toLocaleDateString() : '—'}</dd>
                </div>
              </dl>
              {project.notes && (
                <div className="mt-6 pt-4 border-t border-slate-200 dark:border-slate-700/50">
                  <h4 className="text-xs font-semibold text-slate-600 dark:text-slate-400 mb-2 uppercase tracking-wider">Notes</h4>
                  <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed bg-slate-50 dark:bg-slate-800/30 p-3 rounded">{project.notes}</p>
                </div>
              )}
            </GlassPanel>

            {importedContext.length > 0 && (
              <GlassPanel>
                <h3 className="text-base font-semibold text-slate-900 dark:text-slate-200 mb-4">Workbook Details</h3>
                <dl className="text-sm divide-y divide-slate-200 dark:divide-slate-700/50">
                  {importedContext.map(([key, item]) => (
                    <div key={key} className="grid grid-cols-1 gap-1 py-2 sm:grid-cols-[180px_1fr]">
                      <dt className="text-slate-600 dark:text-slate-400">{item.label || formatMachineLabel(key)}</dt>
                      <dd className="text-slate-900 dark:text-slate-200 font-medium">
                        {item.value === null || item.value === undefined || item.value === '' ? '—' : String(item.value)}
                        {item.source_header && (
                          <div className="mt-0.5 text-[11px] font-normal text-slate-600 dark:text-slate-400">
                            Source: {item.source_header}{item.source_column ? ` (${item.source_column})` : ''}
                          </div>
                        )}
                      </dd>
                    </div>
                  ))}
                </dl>
              </GlassPanel>
            )}

            <GlassPanel>
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-200 mb-4">Documentary Review Breakdown</h3>
              <div className="space-y-4">
                {[
                  { label: 'Compliant', count: summary.compliant || 0, total: summary.total || 1, color: 'bg-emerald-500' },
                  { label: 'Under Review', count: summary.under_review || 0, total: summary.total || 1, color: 'bg-blue-500' },
                  { label: 'Pending', count: summary.pending || 0, total: summary.total || 1, color: 'bg-slate-400 dark:bg-slate-500' },
                  { label: 'Non-Compliant', count: summary.non_compliant || 0, total: summary.total || 1, color: 'bg-red-500' },
                  { label: 'Waived', count: summary.waived || 0, total: summary.total || 1, color: 'bg-amber-500' },
                  { label: 'Not Applicable', count: summary.not_applicable || 0, total: summary.total || 1, color: 'bg-slate-500 dark:bg-slate-400' },
                ].map(item => (
                  <div key={item.label}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-slate-600 dark:text-slate-400">{item.label}</span>
                      <span className="text-slate-900 dark:text-slate-300 font-medium">{item.count} / {item.total}</span>
                    </div>
                    <div className="w-full h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                      <div className={`h-full ${item.color} rounded-full transition-all`} style={{ width: `${item.total > 0 ? (item.count / item.total) * 100 : 0}%` }} />
                    </div>
                  </div>
                ))}
              </div>
              {requirementsError ? (
                <div className="mt-3">
                  <InlineAlert type="error">
                    <div className="flex items-center justify-between gap-4">
                      <span>{requirementsError}</span>
                      <Button size="sm" variant="outline" onClick={fetchRequirements}>Retry</Button>
                    </div>
                  </InlineAlert>
                </div>
              ) : summary.total === 0 ? (
                <p className="text-sm text-slate-600 dark:text-slate-400 mt-3">No requirements initialized yet.</p>
              ) : null}
            </GlassPanel>
          </div>

          <GlassPanel>
            <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div>
                <h3 className="text-base font-semibold text-slate-900 dark:text-slate-200">Returned for Revision</h3>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                  Requirements returned for correction before any overdue non-compliance action.
                </p>
              </div>
              <div className="flex items-center gap-2">
                {historicalRevisionRequirements.length > 0 && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setShowHistoricalReturns((prev) => !prev)}
                  >
                    {showHistoricalReturns ? 'Hide Return History' : `View Return History (${historicalRevisionRequirements.length})`}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  icon={Download}
                  disabled={!revisionRequirements.length || reportDownloading}
                  onClick={() => {
                    if (isStaff()) {
                      setReportModalOpen(true)
                    } else {
                      handleDownloadRevisionReport()
                    }
                  }}
                >
                  {isStaff() ? 'Generate Correction Report' : 'Download All Corrections'}
                </Button>
              </div>
            </div>
            <DataTable
              columns={revisionColumns}
              data={revisionRequirements}
              keyField="id"
              isLoading={false}
              emptyMessage="No requirements are currently returned for revision."
            />

            {showHistoricalReturns && historicalRevisionRequirements.length > 0 && (
              <div className="mt-6 border-t border-slate-200 pt-4 dark:border-slate-700/60">
                <h4 className="mb-2 text-sm font-semibold text-slate-800 dark:text-slate-200">
                  Return History & Previous Corrections
                </h4>
                <DataTable
                  columns={historicalRevisionColumns}
                  data={historicalRevisionRequirements}
                  keyField="id"
                  isLoading={false}
                  emptyMessage="No historical returns recorded."
                />
              </div>
            )}
          </GlassPanel>
        </div>
      )}

      {activeTab === 'requirements' && (
        <>
          {reqNotice && (
            <FeedbackToast type="success" message={reqNotice} onDismiss={() => setReqNotice('')} />
          )}
          {requirementsError && (
            <InlineAlert type="error" className="mb-4">
              <div className="flex items-center justify-between gap-4">
                <span>{requirementsError}</span>
                <Button size="sm" variant="outline" onClick={fetchRequirements}>Retry</Button>
              </div>
            </InlineAlert>
          )}
          <div className="filter-bar mb-6">
            <div className="grid gap-4 lg:grid-cols-[1fr_14rem_12rem_12rem] lg:items-end">
              <form onSubmit={handleSearchSubmit} className="flex flex-col gap-2 sm:flex-row sm:items-end">
                <FormField id="req-search" label="Search" className="flex-1">
                  <div className="relative">
                    <Search
                      aria-hidden="true"
                      className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600 dark:text-slate-400"
                    />
                    <input
                      id="req-search"
                      type="text"
                      value={searchInput}
                      onChange={(event) => setSearchInput(event.target.value)}
                      placeholder="Search requirements..."
                      className="input-field pl-10"
                    />
                  </div>
                </FormField>
                <Button type="submit" variant="outline" className="w-full sm:w-auto">
                  Search
                </Button>
              </form>

              <FormField id="req-phase-filter" label="Phase">
                <select
                  id="req-phase-filter"
                  value={phaseFilter}
                  onChange={(event) => setPhaseFilter(event.target.value)}
                  className="input-field"
                >
                  <option value="">All Phases</option>
                  {Object.keys(PHASE_NAME_BADGE).map((phase) => (
                    <option key={phase} value={phase}>{PHASE_NAME_BADGE[phase].label}</option>
                  ))}
                </select>
              </FormField>

              <FormField id="req-status-filter" label="Status">
                <select
                  id="req-status-filter"
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                  className="input-field"
                >
                  <option value="">All Statuses</option>
                  {REQ_STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status}>{REQ_STATUS_BADGE[status]?.label || formatStatus(status)}</option>
                  ))}
                </select>
              </FormField>

              <FormField id="req-mandatory-filter" label="Mandatory">
                <select
                  id="req-mandatory-filter"
                  value={mandatoryFilter}
                  onChange={(event) => setMandatoryFilter(event.target.value)}
                  className="input-field"
                >
                  <option value="">All</option>
                  <option value="yes">Yes</option>
                  <option value="no">No</option>
                </select>
              </FormField>
            </div>
            {activeFilterCount > 0 && (
              <div className="mt-3 flex justify-end">
                <Button type="button" variant="outline" size="sm" onClick={handleClearFilters}>
                  Clear Filters
                </Button>
              </div>
            )}
          </div>
          <ProjectRequirementsTable
            key={JSON.stringify([appliedSearch, phaseFilter, statusFilter, mandatoryFilter, filteredRequirements.map(row => row.id)])}
            requirements={filteredRequirements}
            renderActions={renderRequirementActions}
            emptyMessage={
              requirementsError
                ? 'Unable to load requirements. Please retry.'
                : requirements.length === 0
                  ? 'No requirements found. Requirements are initialized from the program matrix when a project is created.'
                  : 'No requirements match the current search and filters.'
            }
            preserveEmptyTable={requirements.length > 0}
          />
        </>
      )}

      {activeTab === 'history' && (
        <DataTable
          columns={logColumns}
          data={phaseLog}
          keyField="id"
          isLoading={false}
          emptyMessage="No phase transitions recorded."
        />
      )}

      {activeTab === 'activity' && (
        <GlassPanel>
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-200">Project Activity Log</h3>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                Audit events tied to this project, its requirements, submissions, document intelligence reviews, and handoff records.
              </p>
            </div>
            <Button variant="outline" size="sm" icon={ShieldCheck} onClick={fetchActivity}>Refresh</Button>
          </div>
          {activityError && (
            <InlineAlert type="error" className="mb-4">
              <div className="flex items-center justify-between gap-4">
                <span>{activityError}</span>
                <Button size="sm" variant="outline" onClick={fetchActivity}>Retry</Button>
              </div>
            </InlineAlert>
          )}
          <DataTable
            columns={activityColumns}
            data={activityLogs}
            keyField="id"
            isLoading={activityLoading}
            emptyMessage={activityError ? 'Unable to load project activity. Please retry.' : 'No project activity recorded yet.'}
          />
        </GlassPanel>
      )}

      <Modal
        open={reportModalOpen}
        title="Generate correction report"
        description="Choose a document template, review scanned variables, preview the generated document, then download the DOCX."
        size="xl"
        onClose={() => {
          if (!reportDownloading) setReportModalOpen(false)
        }}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault()
            handleDownloadRevisionReport()
          }}
          className="space-y-4"
        >
          {reqError && !editingReq && (
            <InlineAlert type="error" onDismiss={() => setReqError('')}>
              {reqError}
            </InlineAlert>
          )}

          {reportTemplates.length > 0 && (
            <div>
              <label className="label-text" htmlFor="revision-report-template">Template</label>
              <select
                id="revision-report-template"
                className="input-field mt-1"
                value={selectedReportTemplateId}
                onChange={(event) => setSelectedReportTemplateId(event.target.value)}
              >
                {reportTemplates.map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.label || template.file_name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {reportVariableFields.map(({ key, label }) => (
              <div key={key}>
                <label className="label-text" htmlFor={`revision-report-${key}`}>{label || formatMachineLabel(key)}</label>
                <input
                  id={`revision-report-${key}`}
                  className="input-field mt-1"
                  value={reportPlaceholderValues[key] || ''}
                  onChange={(event) => setReportPlaceholderValues((current) => ({
                    ...current,
                    [key]: event.target.value,
                  }))}
                />
              </div>
            ))}
          </div>

          {selectedReportTemplate && reportVariableFields.length === 0 && (
            <p className="text-xs text-slate-600 dark:text-slate-400">
              This template only uses system-filled variables.
            </p>
          )}

          <DocumentPreview
            document={reportPreview?.preview_document}
            fallbackText={reportPreview?.preview_text}
            title="Generated document preview"
          />

          {selectedReportTemplate && (
            <p className="text-xs text-slate-600 dark:text-slate-400">
              Template file: {selectedReportTemplate.file_name}
            </p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <Button type="button" variant="outline" onClick={() => setReportModalOpen(false)} disabled={reportDownloading}>
              Cancel
            </Button>
            <Button type="button" variant="outline" onClick={handlePreviewRevisionReport} loading={reportPreviewLoading} disabled={!revisionRequirements.length}>
              Preview
            </Button>
            <Button type="submit" icon={Download} loading={reportDownloading} disabled={!revisionRequirements.length}>
              Download DOCX
            </Button>
          </div>
        </form>
      </Modal>

      {/* Phase Transition Modal */}
      <Modal
        open={showTransition}
        title="Move project to next phase"
        description={`Current phase: ${PHASE_BADGE[currentPhase]?.label || formatMachineLabel(currentPhase)}`}
        size="sm"
        onClose={() => setShowTransition(false)}
      >
            {transitionError && (
              <InlineAlert type="error" className="mb-3" onDismiss={() => setTransitionError('')}>{transitionError}</InlineAlert>
            )}
            <div className="space-y-4">
              <div>
                <label className="label-text">Transition To *</label>
                <select value={transitionTo} onChange={(e) => setTransitionTo(e.target.value)} className="input-field mt-1">
                  <option value="">Select phase</option>
                  {availableTransitions.map(phase => (
                    <option key={phase} value={phase}>{PHASE_BADGE[phase]?.label || formatMachineLabel(phase)}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label-text">Reason *</label>
                <textarea value={transitionReason} onChange={(e) => setTransitionReason(e.target.value)} className="input-field mt-1" rows={3} placeholder="Record the review basis for moving this project to the next phase." />
              </div>
              <div className="flex gap-3 justify-end pt-2">
                <Button variant="outline" onClick={() => setShowTransition(false)}>Cancel</Button>
                <Button onClick={handleTransition} loading={transitioning}>Move Phase</Button>
              </div>
            </div>
      </Modal>

      {/* Update Requirement Modal */}
      {editingReq && (
        <Modal
          open={!!editingReq}
          title="Update requirement status"
          size="sm"
          onClose={() => setEditingReq(null)}
        >
            <p className="text-sm text-slate-900 dark:text-slate-300 mb-1">{editingReq.requirement_name}</p>
            {editingReq.annex_reference && <p className="text-xs text-slate-600 dark:text-slate-400 mb-4">{editingReq.annex_reference}</p>}
            {reqError && (
              <InlineAlert type="error" className="mb-3" onDismiss={() => setReqError('')}>{reqError}</InlineAlert>
            )}
            <div className="space-y-4">
              <div>
                <label className="label-text">Status</label>
                <select value={reqForm.status} onChange={(e) => setReqForm({ ...reqForm, status: e.target.value })} className="input-field mt-1">
                  {REQ_STATUS_OPTIONS.map(s => (
                    <option key={s} value={s}>{REQ_STATUS_BADGE[s]?.label || formatStatus(s)}</option>
                  ))}
                </select>
                <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">
                  Use Non-Compliant only after the working-day deadline is overdue. Use Return for Revision when the document needs correction before the deadline.
                </p>
              </div>
              {reqForm.status === 'waived' && (
                <div>
                  <label className="label-text">Waiver Reason</label>
                  <textarea value={reqForm.waived_reason} onChange={(e) => setReqForm({ ...reqForm, waived_reason: e.target.value })} className="input-field mt-1" rows={2} placeholder="Reason for waiving this requirement..." />
                </div>
              )}
              <AiRewriteControl
                label="Revision Notes"
                value={reqForm.revision_notes}
                onTextChange={(text) => setReqForm({ ...reqForm, revision_notes: text })}
                contextLabel="Requirement revision notes"
                disabled={reqSubmitting}
                placeholder="Summarize what the LGU needs to correct or resubmit."
              >
                <Button variant="outline" onClick={handleReturnForRevision} loading={reqSubmitting}>
                  Return for Revision
                </Button>
              </AiRewriteControl>
              <div className="flex gap-3 justify-end pt-2">
                <Button variant="outline" onClick={() => setEditingReq(null)}>Cancel</Button>
                <Button onClick={handleUpdateRequirement} loading={reqSubmitting}>Update</Button>
              </div>
            </div>
        </Modal>
      )}

      {/* Requirement Details Modal (Read-Only Inspection) */}
      {viewingDetailReq && (
        <Modal
          open={Boolean(viewingDetailReq)}
          title="Requirement details"
          description={viewingDetailReq.requirement_name}
          size="md"
          onClose={() => setViewingDetailReq(null)}
          footer={
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                {Boolean(viewingDetailReq.has_documentary_evidence) && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const target = viewingDetailReq
                      setViewingDetailReq(null)
                      openEvidenceModal(target)
                    }}
                  >
                    View Evidence
                  </Button>
                )}
              </div>
              <Button variant="outline" size="sm" onClick={() => setViewingDetailReq(null)}>
                Close
              </Button>
            </div>
          }
        >
          <div className="space-y-4 text-sm">
            {/* Status & Lifecycle Banner */}
            <div className="rounded-lg border border-brand-border bg-brand-surface p-3.5 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-brand-text-muted">Status</span>
                <div className="flex items-center gap-2">
                  <span className={badgeClassForStatus(viewingDetailReq.status)}>
                    {formatStatus(viewingDetailReq.status)}
                  </span>
                  {viewingDetailReq.applicability === 'not_applicable' && (
                    <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                      Not Applicable
                    </span>
                  )}
                  {viewingDetailReq.is_active === false && (
                    <span className="rounded bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-700 dark:bg-slate-700 dark:text-slate-200">
                      Inactive checklist entry
                    </span>
                  )}
                </div>
              </div>

              {viewingDetailReq.workflow_status && (
                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-brand-border pt-2 text-xs">
                  <span className="text-brand-text-muted">Workflow review state</span>
                  <span className="font-medium text-brand-text">{workflowStatusLabel(viewingDetailReq.workflow_status)}</span>
                </div>
              )}
            </div>

            {/* Waiver / Deactivation Reason */}
            {viewingDetailReq.waived_reason && (
              <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3.5 dark:border-amber-900/40 dark:bg-amber-950/20">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-amber-800 dark:text-amber-300">
                  {viewingDetailReq.is_active === false ? 'Deactivation / Exemption Reason' : 'Waiver Justification'}
                </h4>
                <p className="mt-1 text-sm text-amber-900 dark:text-amber-200">{viewingDetailReq.waived_reason}</p>
              </div>
            )}

            {/* Applicability Justification */}
            {viewingDetailReq.applicability === 'not_applicable' && (
              <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3.5 dark:border-amber-900/40 dark:bg-amber-950/20">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-amber-800 dark:text-amber-300">
                  Project Applicability Justification
                </h4>
                <p className="mt-1 text-sm text-amber-900 dark:text-amber-200">
                  {viewingDetailReq.applicability_reason || 'Marked Not Applicable'}
                </p>
                {(viewingDetailReq.applicability_set_by_name || viewingDetailReq.applicability_set_at) && (
                  <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
                    Exemption set by {viewingDetailReq.applicability_set_by_name || 'Authorized user'}
                    {viewingDetailReq.applicability_set_at && (
                      ` on ${new Date(viewingDetailReq.applicability_set_at).toLocaleDateString('en-PH', { month: 'short', day: 'numeric', year: 'numeric' })}`
                    )}
                  </p>
                )}
              </div>
            )}

            {/* Metadata Grid */}
            <dl className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2 text-xs">
              <div>
                <dt className="text-brand-text-muted">Lifecycle phase</dt>
                <dd className="mt-0.5 font-medium text-brand-text">{viewingDetailReq.phase_name || '—'}</dd>
              </div>
              <div>
                <dt className="text-brand-text-muted">Requirement classification</dt>
                <dd className="mt-0.5 font-medium text-brand-text">
                  {viewingDetailReq.is_mandatory ? 'Mandatory (Required)' : 'Optional'}
                </dd>
              </div>
              <div>
                <dt className="text-brand-text-muted">Document category</dt>
                <dd className="mt-0.5 font-medium text-brand-text">
                  {viewingDetailReq.document_category ? formatStatus(viewingDetailReq.document_category) : 'Standard document'}
                </dd>
              </div>
              <div>
                <dt className="text-brand-text-muted">Annex reference</dt>
                <dd className="mt-0.5 font-medium text-brand-text">{viewingDetailReq.annex_reference || '—'}</dd>
              </div>
              <div>
                <dt className="text-brand-text-muted">Submissions / Evidence</dt>
                <dd className="mt-0.5 font-medium text-brand-text">
                  {viewingDetailReq.submission_count > 0
                    ? `${viewingDetailReq.submission_count} submission(s) recorded`
                    : 'No submissions recorded'}
                </dd>
              </div>
              <div>
                <dt className="text-brand-text-muted">Deadline / SLA</dt>
                <dd className="mt-0.5 font-medium text-brand-text">
                  {viewingDetailReq.active_deadline?.deadline_date
                    ? `${new Date(viewingDetailReq.active_deadline.deadline_date).toLocaleDateString('en-PH', { month: 'short', day: 'numeric', year: 'numeric' })} (${formatStatus(viewingDetailReq.active_deadline.deadline_type)})`
                    : viewingDetailReq.has_sla
                      ? `${viewingDetailReq.sla_days} working days rule`
                      : 'No deadline set'}
                </dd>
              </div>
              {viewingDetailReq.last_action_by_name && (
                <div>
                  <dt className="text-brand-text-muted">Last action by</dt>
                  <dd className="mt-0.5 font-medium text-brand-text">{viewingDetailReq.last_action_by_name}</dd>
                </div>
              )}
              {viewingDetailReq.reviewed_at && (
                <div>
                  <dt className="text-brand-text-muted">Reviewed on</dt>
                  <dd className="mt-0.5 font-medium text-brand-text">
                    {new Date(viewingDetailReq.reviewed_at).toLocaleDateString('en-PH', { month: 'short', day: 'numeric', year: 'numeric' })}
                  </dd>
                </div>
              )}
            </dl>

            {/* Return Notes if applicable */}
            {viewingDetailReq.workflow_return_reason && (
              <div className="rounded-lg border border-brand-border bg-brand-surface p-3">
                <dt className="text-xs font-semibold uppercase tracking-wider text-brand-text-muted">Return for revision notes</dt>
                <dd className="mt-1 text-xs text-brand-text">{viewingDetailReq.workflow_return_reason}</dd>
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Edit Project Modal */}
      <Modal
        open={showEdit}
        title="Edit project"
        size="lg"
        onClose={() => setShowEdit(false)}
      >
            {editError && (
              <InlineAlert type="error" className="mb-3" onDismiss={() => setEditError('')}>{editError}</InlineAlert>
            )}
            <form onSubmit={handleEditProject} className="space-y-4">
              <FormField id="edit-project-lgu" label="LGU" required error={editErrors.lgu_id}>
                <select id="edit-project-lgu" value={editForm.lgu_id || ''} onChange={(e) => setEditForm({ ...editForm, lgu_id: e.target.value })} className="input-field" disabled={editChoicesLoading}>
                  <option value="">Select LGU</option>
                  {!editLgus.some((item) => String(item.id) === String(editForm.lgu_id)) && editForm.lgu_id && <option value={editForm.lgu_id}>{project.lgu?.name}</option>}
                  {editLgus.filter((item) => item.is_active !== false || String(item.id) === String(project.lgu_id)).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </FormField>
              <FormField id="edit-project-program" label="Program" required error={editErrors.program_id}>
                <select id="edit-project-program" value={editForm.program_id || ''} disabled={editChoicesLoading} className="input-field" onChange={(e) => {
                  const selected = editPrograms.find((item) => String(item.id) === e.target.value)
                  const options = selected?.program_type === 'infrastructure' ? INFRA_PROJECT_KIND_OPTIONS : selected?.program_type === 'non_infrastructure' ? NON_INFRA_PROJECT_KIND_OPTIONS : ALL_PROJECT_KIND_OPTIONS
                  const kind = options.some((item) => item.value === editForm.project_kind) ? editForm.project_kind : selected?.program_type === 'infrastructure' ? 'infrastructure' : ''
                  setEditCycles([])
                  setEditForm({ ...editForm, program_id: e.target.value, program_cycle_id: '', project_kind: kind })
                }}>
                  <option value="">Select Program</option>
                  {!editPrograms.some((item) => String(item.id) === String(editForm.program_id)) && editForm.program_id && <option value={editForm.program_id}>{project.program?.name}</option>}
                  {editPrograms.filter((item) => item.is_active !== false || String(item.id) === String(project.program_id)).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </FormField>
              <FormField id="edit-project-fy" label="Fiscal Year" required error={editErrors.fiscal_year}>
                <input id="edit-project-fy" type="number" min="2000" max="2100" value={editForm.fiscal_year || ''} onChange={(e) => { setEditCycles([]); setEditForm({ ...editForm, fiscal_year: e.target.value, program_cycle_id: '' }) }} className="input-field" />
              </FormField>
              {editCycles.length > 0 && <FormField id="edit-project-cycle" label="Program Cycle" required={editCycles.length > 1} error={editErrors.program_cycle_id}>
                <select id="edit-project-cycle" value={editForm.program_cycle_id || ''} onChange={(e) => setEditForm({ ...editForm, program_cycle_id: e.target.value })} disabled={editCyclesLoading} className="input-field">
                  <option value="">Select Program Cycle</option>
                  {editCycles.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </FormField>}
              {editCyclesError && <InlineAlert type="error">{editCyclesError}</InlineAlert>}
              {editChoicesError && <InlineAlert type="error">{editChoicesError}</InlineAlert>}
              <p className="text-sm text-slate-600 dark:text-slate-400">Changing the program or classification updates the documentary checklist. Matching requirements keep their submissions; other submitted documents remain available as history.</p>
              <FormField id="edit-project-code" label="Project Code" error={editErrors.source_project_code}>
                <input id="edit-project-code" type="text" value={editForm.source_project_code || ''} onChange={(e) => setEditForm({ ...editForm, source_project_code: e.target.value })} maxLength={120} className="input-field mt-1" disabled={isWorkbookFieldLocked('source_project_code')} title={workbookLockLabel('source_project_code') || undefined} />
                {isWorkbookFieldLocked('source_project_code') && <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{workbookLockLabel('source_project_code')}</p>}
              </FormField>
              <FormField id="edit-project-name" label="Project Name" error={editErrors.project_name}>
                <input
                  id="edit-project-name"
                  type="text"
                  value={editForm.project_name}
                  onChange={(e) => setEditForm({ ...editForm, project_name: e.target.value })}
                  className="input-field mt-1"
                  disabled={isWorkbookFieldLocked('project_name')}
                  title={workbookLockLabel('project_name') || undefined}
                />
                {isWorkbookFieldLocked('project_name') && <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{workbookLockLabel('project_name')}</p>}
              </FormField>
              {(() => {
                const isInfra = editProgramType === 'infrastructure'
                const isNonInfra = editProgramType === 'non_infrastructure'
                const kindOptions = isInfra
                  ? INFRA_PROJECT_KIND_OPTIONS
                  : isNonInfra
                    ? NON_INFRA_PROJECT_KIND_OPTIONS
                    : ALL_PROJECT_KIND_OPTIONS
                const isKindRequired = Boolean(editProgramType)
                return (
                  <FormField
                    id="edit-project-kind"
                    label="Project Classification"
                    required={isKindRequired}
                    error={editErrors.project_kind}
                  >
                    <select
                      id="edit-project-kind"
                      value={editForm.project_kind || ''}
                      onChange={(e) => setEditForm({ ...editForm, project_kind: e.target.value })}
                      className="input-field mt-1"
                    >
                      <option value="">Select Project Classification</option>
                      {kindOptions.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </FormField>
                )
              })()}
              <div className="grid grid-cols-2 gap-4">
                <FormField id="edit-project-status" label="Status" error={editErrors.overall_status}>
                  <select
                    id="edit-project-status"
                    value={editForm.overall_status}
                    onChange={(e) => setEditForm({ ...editForm, overall_status: e.target.value })}
                    className="input-field mt-1"
                    disabled={isWorkbookFieldLocked('overall_status')}
                    title={workbookLockLabel('overall_status') || undefined}
                  >
                    {PROJECT_STATUS_OPTIONS.map((status) => (
                      <option key={status.value} value={status.value}>{status.label}</option>
                    ))}
                  </select>
                  {isWorkbookFieldLocked('overall_status') && <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{workbookLockLabel('overall_status')}</p>}
                </FormField>
                <FormField id="edit-project-budget" label="Budget Amount" error={editErrors.budget_amount}>
                  <AmountInput
                    id="edit-project-budget"
                    value={editForm.budget_amount}
                    onChange={(e) => setEditForm({ ...editForm, budget_amount: e.target.value })}
                    className="input-field mt-1"
                    placeholder="0.00"
                    disabled={isWorkbookFieldLocked('budget_amount')}
                    title={workbookLockLabel('budget_amount') || undefined}
                  />
                  {isWorkbookFieldLocked('budget_amount') && <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{workbookLockLabel('budget_amount')}</p>}
                </FormField>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <FormField id="edit-project-target-start" label="Target Start Date" error={editErrors.target_start_date}>
                  <input id="edit-project-target-start" type="date" value={editForm.target_start_date} onChange={(e) => setEditForm({ ...editForm, target_start_date: e.target.value })} className="input-field mt-1" />
                </FormField>
                <FormField id="edit-project-target-end" label="Target End Date" error={editErrors.target_end_date}>
                  <input id="edit-project-target-end" type="date" value={editForm.target_end_date} onChange={(e) => setEditForm({ ...editForm, target_end_date: e.target.value })} className="input-field mt-1" />
                </FormField>
              </div>
              <FormField id="edit-project-notes" label="Notes">
                <textarea id="edit-project-notes" value={editForm.notes} onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })} className="input-field mt-1" rows={3} />
              </FormField>
              <div className="flex gap-3 justify-end pt-2">
                <Button variant="outline" type="button" onClick={() => setShowEdit(false)}>Cancel</Button>
                <Button type="submit" loading={editSubmitting} disabled={editChoicesLoading || editCyclesLoading || Boolean(editCyclesError || editChoicesError)}>Save Changes</Button>
              </div>
            </form>
      </Modal>

      {/* Documentary Evidence & Intake Review Modal */}
      <RequirementReviewModal
        open={Boolean(selectedEvidenceReq)}
        selectedRequirement={selectedEvidenceReq}
        submissions={evidenceSubmissions}
        submissionsLoading={evidenceLoading}
        canReviewScan={selectedEvidenceReq?.is_active !== false && isStaff()}
        canUpload={selectedEvidenceReq?.is_active !== false && !isProgramInactive && (isFieldOfficer() || isStaff())}
        selectedHasEvidence={Boolean(selectedEvidenceReq?.has_documentary_evidence || evidenceSubmissions?.length > 0)}
        selectedReviewLocked={selectedEvidenceReq?.is_active === false || isProgramInactive || selectedEvidenceReq?.status === 'compliant' || selectedEvidenceReq?.workflow_status === 'approved'}
        reviewUploadOpen={reviewUploadOpen}
        setReviewUploadOpen={setReviewUploadOpen}
        uploadForm={uploadForm}
        setUploadForm={setUploadForm}
        uploading={uploading}
        scanPreview={scanPreview}
        scanPreviewLoading={scanPreviewLoading}
        scanPreviewError={scanPreviewError}
        setScanPreviewError={setScanPreviewError}
        previewMatchesSelected={Boolean(scanPreview && selectedEvidenceReq && Number(scanPreview.suggested_project_requirement_id || scanPreview.requirement_id) === Number(selectedEvidenceReq.id))}
        revisionNotes={revisionNotes}
        setRevisionNotes={setRevisionNotes}
        requirementReviewing={requirementReviewing}
        reviewingScanId={reviewingScanId}
        checkingSubmissionId={checkingSubmissionId}
        reviewingComplianceResultId={reviewingComplianceResultId}
        filePreviewLoadingId={filePreviewLoadingId}
        userRole={isFieldOfficer() ? 'field_officer' : (isAdmin() ? 'admin' : (isStaff() ? 'staff' : 'user'))}
        error={reqError}
        onDismissError={() => setReqError('')}
        onClose={closeEvidenceModal}
        onUploadSubmission={handleUploadEvidenceSubmission}
        onApproveRequirement={handleApproveEvidenceRequirement}
        onReturnRequirementForRevision={handleReturnEvidenceForRevision}
        onApplyCheckerReturnNotes={(notes) => setRevisionNotes(notes || '')}
        onRecordComplianceReview={handleRecordComplianceReview}
        onRunComplianceCheck={handleRunComplianceCheck}
        onRescanSubmission={handleRescanSubmission}
        onRefreshDestination={handleRefreshDestination}
        onReviewScan={handleReviewScan}
        onPreview={handlePreviewFile}
        onDownload={handleDownloadFile}
        onStatusChange={handleEvidenceStatusChange}
        onRefreshRequirement={openEvidenceModal}
      />

      {/* File Preview Modal */}
      <Modal
        open={Boolean(filePreview)}
        title="Document Preview"
        description={filePreview?.fileName}
        onClose={() => {
          if (filePreview?.url) window.URL.revokeObjectURL(filePreview.url)
          setFilePreview(null)
        }}
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

      {/* Change Applicability Modal */}
      <ChangeApplicabilityModal
        open={Boolean(applicabilityModalReq)}
        onClose={() => setApplicabilityModalReq(null)}
        requirement={applicabilityModalReq}
        project={project}
        mode={applicabilityModalMode}
        onSuccess={async (updatedReq) => {
          setApplicabilityModalReq(null)
          setReqNotice(`Requirement applicability updated to '${updatedReq?.applicability || 'applicable'}'.`)
          await Promise.all([
            fetchRequirements(),
            fetchProject(),
            fetchActivity(),
          ])
        }}
      />
    </div>
  )
}
