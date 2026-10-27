import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Eye,
  FilePenLine,
  FileText,
  FolderKanban,
  History,
  Search,
  Send,
  ShieldAlert,
  Sparkles,
} from 'lucide-react'
import { Button, DocumentPreview, GlassPanel, InlineAlert, KpiCard, Modal, PageHeader, useToast } from '../../../components'
import { isAdmin } from '../../../lib/auth'
import { formatDate, formatDateTime, parseDate, formatMachineLabel, formatRole, formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import { OfficialNoticeRegister } from '../components/OfficialNoticeRegister'
import * as escalationApi from '../api/escalationApi'
import * as lguApi from '../../lgus/api/lguApi'
import * as programApi from '../../programs/api/programApi'

const NOTICE_LABELS = {
  annex_e: 'Notice of Deficiencies (Annex E)',
  annex_m: 'Notice of Non-Compliance No. 1 (Annex M)',
  annex_n: 'Notice of Non-Compliance No. 2 (Annex N)',
  annex_o: 'Notice of Non-Compliance No. 3 (Annex O)',
}

const NOTICE_STATUS_LABELS = {
  draft: 'Draft',
  reviewed: 'Ready for Release',
  sent: 'Released',
  acknowledged: 'Acknowledged',
  expired: 'Expired',
}

const BREACH_STATE_FILTERS = [
  { value: '', label: 'All Readiness States' },
  { value: 'ready', label: 'Ready for Notice' },
  { value: 'blocked', label: 'Needs Prerequisite' },
  { value: 'waiting', label: 'Waiting 15-Day Window' },
  { value: 'complete', label: 'Notice Flow Complete' },
]

const NEXT_NOTICE_TYPE_FILTERS = [
  { value: '', label: 'All Next Notice Types' },
  { value: 'annex_m', label: 'Notice of Non-Compliance No. 1 (Annex M)' },
  { value: 'annex_n', label: 'Notice of Non-Compliance No. 2 (Annex N)' },
  { value: 'annex_o', label: 'Notice of Non-Compliance No. 3 (Annex O)' },
]

const NOTICE_TYPE_FILTERS = [
  { value: '', label: 'All Notice Types' },
  { value: 'annex_e', label: 'Notice of Deficiencies (Annex E)' },
  { value: 'annex_m', label: 'Notice of Non-Compliance No. 1 (Annex M)' },
  { value: 'annex_n', label: 'Notice of Non-Compliance No. 2 (Annex N)' },
  { value: 'annex_o', label: 'Notice of Non-Compliance No. 3 (Annex O)' },
]

const NOTICE_STATUS_FILTER_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'draft', label: 'Draft' },
  { value: 'reviewed', label: 'Ready for Release' },
  { value: 'sent', label: 'Released / Dispatched' },
  { value: 'acknowledged', label: 'Acknowledged' },
  { value: 'expired', label: 'Expired' },
]

function stateBadge(row) {
  const stateLabels = {
    blocked: 'Needs Prerequisite',
    ready: 'Ready for Notice',
    waiting: 'Waiting',
  }
  const state = row.state || 'blocked'
  return (
    <span className={badgeClassForStatus(state, 'danger')}>
      {stateLabels[state] || formatStatus(state)}
    </span>
  )
}

function noticeStatusBadge(row) {
  const status = row.status || 'draft'
  return (
    <span className={badgeClassForStatus(status, 'info')}>
      {NOTICE_STATUS_LABELS[status] || formatStatus(status)}
    </span>
  )
}

function blankFinding() {
  return {
    informal_notes: '',
    formal_findings: '',
    recommendations: '',
    agreements_timelines: '',
    ai_model_used: '',
    ai_prompt_used: '',
  }
}

function buildNoticeDraft(notice) {
  return {
    id: notice.id,
    notice_type: notice.notice_type,
    title: notice.title || '',
    status: notice.status || 'draft',
    sent_at: notice.sent_at || '',
    acknowledged_at: notice.acknowledged_at || '',
    body_text: notice.body_text || '',
    final_text: notice.final_text || '',
    legal_findings: notice.notice_type === 'annex_e'
      ? (notice.legal_findings?.length ? notice.legal_findings : [blankFinding()])
      : (notice.legal_findings || []),
    recipients: notice.recipients || [],
    magic_links_enabled: notice.magic_links_enabled !== false,
    magic_links: notice.magic_links || [],
    communications: notice.communications || [],
  }
}

function toDateTimeLocalValue(value) {
  if (!value) return ''
  const date = parseDate(value)
  if (!date) return ''
  const pad = (number) => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function nowDateTimeLocalValue() {
  return toDateTimeLocalValue(new Date().toISOString())
}

function localDateTimeToIso(value) {
  if (!value) return undefined
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toISOString()
}

function buildReleaseState(notice = {}) {
  const latestCommunication = notice.communications?.[0]
  const primaryRecipient = notice.recipients?.[0]
  return {
    channel: latestCommunication?.channel || 'dms',
    released_at: toDateTimeLocalValue(notice.sent_at) || nowDateTimeLocalValue(),
    recipient_name: latestCommunication?.recipient_name || primaryRecipient?.recipient_name || '',
    recipient_destination: latestCommunication?.recipient_destination || '',
    recipient_office: latestCommunication?.recipient_office || '',
    reference_no: latestCommunication?.reference_no || '',
    remarks: latestCommunication?.remarks || '',
  }
}

function buildReceiptState(notice = {}) {
  return {
    acknowledged_at: toDateTimeLocalValue(notice.acknowledged_at) || nowDateTimeLocalValue(),
    remarks: '',
  }
}

function mergeNoticeDetailPreservingEdits(currentDraft, serverNotice) {
  const refreshedDraft = buildNoticeDraft(serverNotice)
  if (!currentDraft) {
    return refreshedDraft
  }
  return {
    ...refreshedDraft,
    title: currentDraft.title,
    body_text: currentDraft.body_text,
    final_text: currentDraft.final_text,
    legal_findings: currentDraft.notice_type === 'annex_e'
      ? (currentDraft.legal_findings || refreshedDraft.legal_findings)
      : refreshedDraft.legal_findings,
  }
}

function editableDocumentVariables(template) {
  const definitions = template?.placeholder_definitions || []
  const editableSystemKeys = new Set([
    'date',
    'notice_date_display',
    'notice_label',
    'notice_title',
    'subject_line',
    'lce_name_upper',
    'lce_position',
    'lgu_display',
    'lce_surname',
    'content',
    'program_title',
    'program_name',
    'fiscal_year',
    'funding_year',
    'project_name',
    'project_names_text',
    'project_rows_text',
    'findings_text',
    'recommendations_text',
    'timelines_text',
    'compliance_period_text',
    'signatory_name',
    'signatory_title',
    'province',
    'province_name',
    'provincial_director_name',
    'provincial_director_title',
    'regional_director_name',
    'regional_director_title',
    'region_name',
    'regional_office_address',
    'regional_office_website',
    'budget_allocation_text',
    'annex_e_date_display',
    'annex_m_date_display',
    'annex_n_date_display',
    'prior_nnc_dates_display',
    'annex_m_and_n_date_display',
    'aide_memoire_date_display',
  ])
  return definitions.filter((item) => item?.key && editableSystemKeys.has(item.key))
}

function editableDocumentVariableKeys(template) {
  return editableDocumentVariables(template).map((item) => item.key)
}

function nonBlankDocumentPlaceholderValues(values) {
  return Object.fromEntries(
    Object.entries(values || {})
      .map(([key, value]) => [String(key || '').trim(), String(value ?? '').trim()])
      .filter(([key, value]) => key && value)
  )
}

function documentValuesFromPreview(preview, currentValues = {}, editableKeys = null) {
  const defaults = preview?.variables?.defaults || {}
  const activeKeys = Array.isArray(editableKeys) && editableKeys.length > 0
    ? editableKeys
    : Object.keys(defaults)
  const nextValues = { ...(currentValues || {}) }
  activeKeys.forEach((key) => {
    const currentValue = String(nextValues[key] ?? '').trim()
    const defaultValue = String(defaults[key] ?? '').trim()
    if (!currentValue && defaultValue) {
      nextValues[key] = defaultValue
    }
  })
  return nextValues
}

export default function EscalationPage() {
  const [searchParams] = useSearchParams()
  const urlView = searchParams.get('view') || searchParams.get('tab')
  const initialView = urlView === 'register' ? 'register' : 'worklist'
  const initialNoticeType = searchParams.get('notice_type') || ''
  const initialNoticeStatus = searchParams.get('notice_status') || ''
  const initialLgu = searchParams.get('lgu_id') || ''
  const initialProgram = searchParams.get('program_id') || ''
  const toast = useToast()
  const canReleaseNotices = isAdmin()
  const [activeView, setActiveView] = useState(initialView)
  const [expandedBreachIds, setExpandedBreachIds] = useState(new Set())
  const [dashboard, setDashboard] = useState(null)
  const [breaches, setBreaches] = useState([])
  const [notices, setNotices] = useState([])
  const [noticePage, setNoticePage] = useState(1)
  const [noticeMeta, setNoticeMeta] = useState({ page: 1, pages: 1, total: 0, per_page: 20 })
  const listRequestRef = useRef(0)
  const [loading, setLoading] = useState(true)
  const [searchDraft, setSearchDraft] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [filterLgu, setFilterLgu] = useState(initialLgu)
  const [filterProgram, setFilterProgram] = useState(initialProgram)
  const [filterBreachState, setFilterBreachState] = useState('')
  const [filterNextNoticeType, setFilterNextNoticeType] = useState('')
  const [filterNoticeType, setFilterNoticeType] = useState(initialNoticeType)
  const [filterNoticeStatus, setFilterNoticeStatus] = useState(initialNoticeStatus)
  const [lgus, setLgus] = useState([])
  const [programs, setPrograms] = useState([])
  const [actionError, setActionError] = useState('')
  const [actionLoadingKey, setActionLoadingKey] = useState('')
  const createAnnexESubmittingRef = useRef(false)
  const generateNextSubmittingRef = useRef(false)
  const saveNoticeSubmittingRef = useRef(false)
  const releaseNoticeSubmittingRef = useRef(false)
  const recordReceiptSubmittingRef = useRef(false)

  const [editorOpen, setEditorOpen] = useState(false)
  const [editorLoading, setEditorLoading] = useState(false)
  const [editorSaving, setEditorSaving] = useState(false)
  const [editorError, setEditorError] = useState('')
  const [findingAiKey, setFindingAiKey] = useState('')
  const [noticeDraft, setNoticeDraft] = useState(null)
  const [workflowLoadingKey, setWorkflowLoadingKey] = useState('')
  const [releaseModalOpen, setReleaseModalOpen] = useState(false)
  const [receiptModalOpen, setReceiptModalOpen] = useState(false)
  const [releaseForm, setReleaseForm] = useState(buildReleaseState())
  const [receiptForm, setReceiptForm] = useState(buildReceiptState())
  const [editorTab, setEditorTab] = useState('details')
  const [documentTemplates, setDocumentTemplates] = useState([])
  const [selectedDocumentTemplateId, setSelectedDocumentTemplateId] = useState('')
  const [documentPlaceholderValues, setDocumentPlaceholderValues] = useState({})
  const [documentPreview, setDocumentPreview] = useState(null)
  const [documentPreviewLoading, setDocumentPreviewLoading] = useState(false)
  const [documentDownloading, setDocumentDownloading] = useState(false)

  const toggleRowExpand = (slaId) => {
    setExpandedBreachIds((prev) => {
      const next = new Set(prev)
      if (next.has(slaId)) {
        next.delete(slaId)
      } else {
        next.add(slaId)
      }
      return next
    })
  }

  useEffect(() => {
    Promise.all([
      lguApi.listLgus({ per_page: 200 }).catch(() => ({ data: [] })),
      programApi.listPrograms({ per_page: 200 }).catch(() => ({ data: [] })),
    ]).then(([lguRes, progRes]) => {
      setLgus(lguRes.data || [])
      setPrograms(progRes.data || [])
    })
  }, [])

  const loadEscalation = useCallback(async () => {
    const requestId = ++listRequestRef.current
    setLoading(true)
    setActionError('')
    try {
      const breachParams = {
        per_page: 100,
        search: appliedSearch || undefined,
        lgu_id: filterLgu || undefined,
        program_id: filterProgram || undefined,
        state: filterBreachState || undefined,
        next_notice_type: filterNextNoticeType || undefined,
      }
      const noticeParams = {
        page: noticePage,
        per_page: 20,
        search: appliedSearch || undefined,
        lgu_id: filterLgu || undefined,
        program_id: filterProgram || undefined,
        notice_type: filterNoticeType || undefined,
        status: filterNoticeStatus || undefined,
      }
      const [dashboardRes, breachRes, noticeRes] = await Promise.all([
        escalationApi.getEscalationDashboard(),
        escalationApi.listEscalationBreaches(breachParams),
        escalationApi.listEscalationNotices(noticeParams),
      ])
      if (requestId !== listRequestRef.current) return
      if (noticeRes.meta?.pages > 0 && noticePage > noticeRes.meta.pages) { setNoticePage(noticeRes.meta.pages); return }
      setDashboard(dashboardRes.data || null)
      setBreaches(breachRes.data || [])
      setNotices(noticeRes.data || [])
      setNoticeMeta({ page: noticePage, pages: 1, total: (noticeRes.data || []).length, per_page: 20, ...noticeRes.meta })
    } catch (error) {
      if (requestId !== listRequestRef.current) return
      setActionError(error.response?.data?.message || 'Unable to load notices and follow-up records.')
    } finally {
      if (requestId === listRequestRef.current) setLoading(false)
    }
  }, [noticePage, appliedSearch, filterLgu, filterProgram, filterBreachState, filterNextNoticeType, filterNoticeType, filterNoticeStatus])

  useEffect(() => {
    loadEscalation()
  }, [loadEscalation])

  const handleSearchSubmit = (event) => {
    event.preventDefault()
    const nextSearch = searchDraft.trim()
    setNoticePage(1)
    setAppliedSearch(nextSearch)
    if (nextSearch === appliedSearch) {
      loadEscalation()
    }
  }

  const hasActiveFilters = Boolean(
    appliedSearch || searchDraft || filterLgu || filterProgram || filterBreachState || filterNextNoticeType || filterNoticeType || filterNoticeStatus
  )

  const handleClearAllFilters = () => {
    setNoticePage(1)
    setSearchDraft('')
    setAppliedSearch('')
    setFilterLgu('')
    setFilterProgram('')
    setFilterBreachState('')
    setFilterNextNoticeType('')
    setFilterNoticeType('')
    setFilterNoticeStatus('')
  }

  function closeEditor() {
    setEditorOpen(false)
    setEditorTab('details')
    setNoticeDraft(null)
    setEditorError('')
    setFindingAiKey('')
    setWorkflowLoadingKey('')
    setReleaseModalOpen(false)
    setReceiptModalOpen(false)
    setReleaseForm(buildReleaseState())
    setReceiptForm(buildReceiptState())
    setDocumentTemplates([])
    setSelectedDocumentTemplateId('')
    setDocumentPlaceholderValues({})
    setDocumentPreview(null)
  }

  async function openEditor(noticeId) {
    setEditorOpen(true)
    setEditorTab('details')
    setEditorLoading(true)
    setEditorError('')
    setDocumentPreview(null)
    try {
      const [detail, templatesRes] = await Promise.all([
        escalationApi.getEscalationNotice(noticeId),
        escalationApi.listNoticeDocumentTemplates(),
      ])
      const notice = detail.data
      setNoticeDraft(buildNoticeDraft(notice))
      setReleaseForm(buildReleaseState(notice))
      setReceiptForm(buildReceiptState(notice))

      const group = (templatesRes.data || []).find((item) => item.template_type === notice.notice_type)
      const availableTemplates = (group?.templates || []).filter((item) => item.available)
      setDocumentTemplates(availableTemplates)
      const defaultTemplateId = group?.default_template_id || availableTemplates[0]?.id || ''
      setSelectedDocumentTemplateId(defaultTemplateId)

      const selected = availableTemplates.find((item) => item.id === defaultTemplateId)
      const defaults = nonBlankDocumentPlaceholderValues(selected?.placeholder_defaults)
      setDocumentPlaceholderValues(defaults)
      await handlePreviewDocumentTemplate(defaultTemplateId, defaults, buildNoticeDraft(notice))
    } catch (error) {
      setEditorError(error.response?.data?.message || 'Unable to open the notice editor.')
    } finally {
      setEditorLoading(false)
    }
  }

  async function handleCreateAnnexE(row) {
    if (createAnnexESubmittingRef.current) return
    createAnnexESubmittingRef.current = true
    const key = `create-${row.sla_id}`
    setActionLoadingKey(key)
    setActionError('')
    try {
      const response = await escalationApi.createEscalationNotice({
        project_id: row.project_id,
        notice_type: 'annex_e',
        trigger_sla_id: row.sla_id,
        trigger_project_requirement_id: row.project_requirement_id,
      })
      await loadEscalation()
      await openEditor(response.data.id)
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to create the Notice of Deficiency / Annex E draft.')
    } finally {
      createAnnexESubmittingRef.current = false
      setActionLoadingKey('')
    }
  }

  async function handleGenerateNext(row) {
    if (generateNextSubmittingRef.current) return
    generateNextSubmittingRef.current = true
    const key = `generate-${row.sla_id}`
    setActionLoadingKey(key)
    setActionError('')
    try {
      const response = await escalationApi.generateNextEscalationNotice({ sla_id: row.sla_id })
      await loadEscalation()
      if (response.data?.notice?.id) {
        await openEditor(response.data.notice.id)
      }
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to prepare the next notice.')
    } finally {
      generateNextSubmittingRef.current = false
      setActionLoadingKey('')
    }
  }

  async function handleSaveNotice() {
    if (!noticeDraft || saveNoticeSubmittingRef.current) return
    saveNoticeSubmittingRef.current = true
    setEditorSaving(true)
    setEditorError('')
    try {
      const payload = {
        title: noticeDraft.title,
        body_text: noticeDraft.body_text,
        final_text: noticeDraft.final_text,
        legal_findings: noticeDraft.notice_type === 'annex_e' ? noticeDraft.legal_findings : [],
      }
      if (['draft', 'reviewed', 'expired'].includes(noticeDraft.status)) {
        payload.status = noticeDraft.status
      }
      await escalationApi.updateEscalationNotice(noticeDraft.id, payload)
      await loadEscalation()
      closeEditor()
      toast.success('Notice changes saved.')
    } catch (error) {
      setEditorError(error.response?.data?.message || 'Unable to save notice changes.')
    } finally {
      saveNoticeSubmittingRef.current = false
      setEditorSaving(false)
    }
  }

  async function handleAiDraft(index) {
    if (!noticeDraft) return
    const finding = noticeDraft.legal_findings?.[index]
    if (!finding?.informal_notes?.trim()) {
      setEditorError('Add evaluator notes first so the assistant has review remarks to formalize.')
      return
    }

    const key = `${noticeDraft.id}-${index}`
    setFindingAiKey(key)
    setEditorError('')
    try {
      const response = await escalationApi.draftEscalationFinding(noticeDraft.id, {
        finding_id: finding.id || undefined,
        informal_notes: finding.informal_notes,
      })
      const draft = response.data
      setNoticeDraft((current) => {
        const nextFindings = [...(current.legal_findings || [])]
        nextFindings[index] = {
          ...nextFindings[index],
          informal_notes: draft.informal_notes,
          formal_findings: draft.formal_findings,
          recommendations: draft.recommendations,
          agreements_timelines: draft.agreements_timelines,
          ai_model_used: draft.ai_model_used,
          ai_prompt_used: draft.ai_prompt_used,
        }
        return { ...current, legal_findings: nextFindings }
      })
    } catch (error) {
      setEditorError(error.response?.data?.message || 'Unable to draft formal findings from these notes.')
    } finally {
      setFindingAiKey('')
    }
  }

  function openReleaseModal(notice = null) {
    const isNoticeObject = notice && typeof notice === 'object' && ('id' in notice || 'notice_type' in notice) && !('nativeEvent' in notice) && !('target' in notice)
    const target = isNoticeObject ? notice : noticeDraft
    if (!target) return
    if (isNoticeObject) setNoticeDraft(buildNoticeDraft(notice))
    setReleaseForm(buildReleaseState(target))
    setReleaseModalOpen(true)
  }

  function openReceiptModal(notice = null) {
    const isNoticeObject = notice && typeof notice === 'object' && ('id' in notice || 'notice_type' in notice) && !('nativeEvent' in notice) && !('target' in notice)
    const target = isNoticeObject ? notice : noticeDraft
    if (!target) return
    if (isNoticeObject) setNoticeDraft(buildNoticeDraft(notice))
    setReceiptForm(buildReceiptState(target))
    setReceiptModalOpen(true)
  }

  async function handleReleaseNotice() {
    if (!noticeDraft || releaseNoticeSubmittingRef.current) return
    releaseNoticeSubmittingRef.current = true
    setWorkflowLoadingKey('release')
    setEditorError('')
    try {
      const response = await escalationApi.releaseEscalationNotice(noticeDraft.id, {
        channel: releaseForm.channel,
        released_at: localDateTimeToIso(releaseForm.released_at),
        recipient_name: releaseForm.recipient_name,
        recipient_destination: releaseForm.recipient_destination,
        recipient_office: releaseForm.recipient_office,
        reference_no: releaseForm.reference_no,
        remarks: releaseForm.remarks,
      })
      const refreshedNotice = response.data?.notice
      if (refreshedNotice) {
        setNoticeDraft((current) => mergeNoticeDetailPreservingEdits(current, refreshedNotice))
        setReleaseForm(buildReleaseState(refreshedNotice))
        setReceiptForm(buildReceiptState(refreshedNotice))
      }
      setReleaseModalOpen(false)
      await loadEscalation()
      toast.success('Notice marked released.')
    } catch (error) {
      setEditorError(error.response?.data?.message || 'Unable to mark the notice released.')
    } finally {
      releaseNoticeSubmittingRef.current = false
      setWorkflowLoadingKey('')
    }
  }

  async function handleRecordReceipt() {
    if (!noticeDraft || recordReceiptSubmittingRef.current) return
    recordReceiptSubmittingRef.current = true
    setWorkflowLoadingKey('receipt')
    setEditorError('')
    try {
      const response = await escalationApi.recordEscalationNoticeReceipt(noticeDraft.id, {
        acknowledged_at: localDateTimeToIso(receiptForm.acknowledged_at),
        remarks: receiptForm.remarks,
      })
      const refreshedNotice = response.data
      if (refreshedNotice) {
        setNoticeDraft((current) => mergeNoticeDetailPreservingEdits(current, refreshedNotice))
        setReleaseForm(buildReleaseState(refreshedNotice))
        setReceiptForm(buildReceiptState(refreshedNotice))
      }
      setReceiptModalOpen(false)
      await loadEscalation()
      toast.success('Notice acknowledgment recorded.')
    } catch (error) {
      setEditorError(error.response?.data?.message || 'Unable to record the acknowledgment date.')
    } finally {
      recordReceiptSubmittingRef.current = false
      setWorkflowLoadingKey('')
    }
  }

  function documentPlaceholderOverrides() {
    return nonBlankDocumentPlaceholderValues(documentPlaceholderValues)
  }

  async function handlePreviewDocumentTemplate(templateId = selectedDocumentTemplateId, overrides = documentPlaceholderValues, draft = noticeDraft) {
    if (!draft) return
    setDocumentPreviewLoading(true)
    setEditorError('')
    try {
      const response = await escalationApi.previewNoticeDocument(draft.id, {
        template_id: templateId || undefined,
        placeholder_overrides: nonBlankDocumentPlaceholderValues(overrides),
        draft: {
          title: draft.title,
          body_text: draft.body_text,
          final_text: draft.final_text,
          legal_findings: draft.legal_findings,
        },
      })
      const previewData = response.data || null
      setDocumentPreview(previewData)
      const tpl = documentTemplates.find((item) => item.id === templateId) || selectedDocumentTemplate
      setDocumentPlaceholderValues((current) => documentValuesFromPreview(
        previewData,
        current,
        editableDocumentVariableKeys(tpl),
      ))
    } catch (error) {
      setEditorError(error.response?.data?.message || 'Unable to preview the generated document.')
    } finally {
      setDocumentPreviewLoading(false)
    }
  }

  function handleSelectDocumentTemplate(templateId) {
    setSelectedDocumentTemplateId(templateId)
    const selected = documentTemplates.find((item) => item.id === templateId)
    const nextValues = nonBlankDocumentPlaceholderValues(selected?.placeholder_defaults)
    setDocumentPlaceholderValues(nextValues)
    handlePreviewDocumentTemplate(templateId, nextValues, noticeDraft)
  }

  function handleSwitchToPreviewTab() {
    setEditorTab('preview')
    if (!documentPreview) {
      handlePreviewDocumentTemplate(selectedDocumentTemplateId, documentPlaceholderValues, noticeDraft)
    }
  }

  async function handleDownloadDocumentTemplate() {
    if (!noticeDraft) return
    setDocumentDownloading(true)
    setEditorError('')
    try {
      await handleOpenDocument(noticeDraft.id, 'docx', {
        template_id: selectedDocumentTemplateId || undefined,
        placeholder_overrides: documentPlaceholderOverrides(),
      })
      toast.success('Notice document downloaded.')
    } catch (error) {
      setEditorError(error.response?.data?.message || 'Unable to download the generated document.')
    } finally {
      setDocumentDownloading(false)
    }
  }

  function updateFinding(index, field, value) {
    setNoticeDraft((current) => {
      const nextFindings = [...(current.legal_findings || [])]
      nextFindings[index] = { ...nextFindings[index], [field]: value }
      return { ...current, legal_findings: nextFindings }
    })
  }

  async function handleOpenDocument(noticeId, format, options = {}) {
    try {
      const response = await escalationApi.fetchNoticeDocument(noticeId, format, options)
      if (format === 'html') {
        const previewWindow = window.open('', '_blank')
        if (previewWindow) {
          previewWindow.document.open()
          previewWindow.document.write(response.data)
          previewWindow.document.close()
        }
        return
      }

      const mimeType = response.headers?.['content-type'] || (format === 'pdf'
        ? 'application/pdf'
        : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
      const blob = new Blob([response.data], { type: mimeType })
      const url = window.URL.createObjectURL(blob)

      if (format === 'pdf') {
        window.open(url, '_blank', 'noopener,noreferrer')
        setTimeout(() => window.URL.revokeObjectURL(url), 1500)
        return
      }

      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `notice-${noticeId}.${format}`
      document.body.appendChild(anchor)
      anchor.click()
      document.body.removeChild(anchor)
      setTimeout(() => window.URL.revokeObjectURL(url), 1500)
    } catch (error) {
      setActionError(error.response?.data?.message || `Unable to open the ${format.toUpperCase()} document.`)
      throw error
    }
  }

  const selectedDocumentTemplate = documentTemplates.find((item) => item.id === selectedDocumentTemplateId) || null
  const documentVariableFields = editableDocumentVariables(selectedDocumentTemplate)


  return (
    <div>
      <PageHeader
        title="Notices & Follow-Up Center"
        description="Prepare reminder and notice packets, attach read-only checklist links only when enabled, and log official DMS or intranet dispatches. Formal notices require authorized human review and release. An overdue deadline does not automatically issue a notice or declare non-compliance."
      />

      <InlineAlert type="error" className="mb-4" onDismiss={() => setActionError('')}>
        {actionError}
      </InlineAlert>

      {/* KPI Cards: 4 distinct operational metrics */}
      <div className="grid grid-cols-1 gap-4 mb-6 sm:grid-cols-2 md:grid-cols-4">
        <KpiCard
          title="Total Overdue"
          value={dashboard?.breached_deadlines || 0}
          subtitle="overdue requirements"
          icon={AlertTriangle}
          color="red"
        />
        <KpiCard
          title="Needs Prerequisite"
          value={dashboard?.blocked || 0}
          subtitle="missing Annex E / acknowledgment"
          icon={ShieldAlert}
          color="amber"
        />
        <KpiCard
          title="Ready for Notice"
          value={dashboard?.ready_to_generate || 0}
          subtitle="ready to prepare"
          icon={FilePenLine}
          color="emerald"
        />
        <KpiCard
          title="Waiting Window"
          value={dashboard?.waiting || 0}
          subtitle="15-day window active"
          icon={Clock}
          color="blue"
        />
      </div>

      {/* Tab Navigation: Escalation Worklist vs Official Document Register */}
      <div className="flex border-b border-brand-border mb-6">
        <button
          type="button"
          className={`flex items-center gap-2 px-5 py-3 text-sm font-semibold border-b-2 transition-colors ${
            activeView === 'worklist'
              ? 'border-brand-primary text-brand-primary'
              : 'border-transparent text-brand-text-muted hover:text-brand-text hover:border-brand-border'
          }`}
          onClick={() => setActiveView('worklist')}
        >
          <FolderKanban className="h-4 w-4" />
          <span>Escalation Worklist</span>
          <span className="ml-1.5 rounded-full bg-brand-primary/10 text-brand-primary px-2 py-0.5 text-xs font-bold">
            {breaches.length}
          </span>
        </button>

        <button
          type="button"
          className={`flex items-center gap-2 px-5 py-3 text-sm font-semibold border-b-2 transition-colors ${
            activeView === 'register'
              ? 'border-brand-primary text-brand-primary'
              : 'border-transparent text-brand-text-muted hover:text-brand-text hover:border-brand-border'
          }`}
          onClick={() => setActiveView('register')}
        >
          <FileText className="h-4 w-4" />
          <span>Official Notice Register</span>
          <span className="ml-1.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-2 py-0.5 text-xs font-bold">
            {noticeMeta.total}
          </span>
        </button>
      </div>

      {activeView === 'worklist' && (
        <div className="space-y-6">
          {/* Worklist Filter Bar */}
          <div className="filter-bar flex flex-wrap items-center gap-3">
            <form
              onSubmit={handleSearchSubmit}
              className="flex min-w-[260px] flex-1 gap-2"
              role="search"
              aria-label="Search notices and follow-up records"
            >
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600 dark:text-slate-400" />
                <input
                  type="text"
                  className="input-field pl-9"
                  placeholder="Search project or requirement..."
                  value={searchDraft}
                  onChange={(e) => setSearchDraft(e.target.value)}
                />
              </div>
              <Button type="submit" variant="outline">Search</Button>
            </form>

            <select
              id="escalation-filter-lgu"
              className="input-field w-full sm:w-auto sm:min-w-[150px]"
              value={filterLgu}
              onChange={(e) => { setNoticePage(1); setFilterLgu(e.target.value) }}
              aria-label="Filter by LGU"
            >
              <option value="">All LGUs</option>
              {lgus.map((lgu) => (
                <option key={lgu.id} value={lgu.id}>{lgu.name || lgu.municipality}</option>
              ))}
            </select>

            <select
              id="escalation-filter-program"
              className="input-field w-full sm:w-auto sm:min-w-[140px]"
              value={filterProgram}
              onChange={(e) => { setNoticePage(1); setFilterProgram(e.target.value) }}
              aria-label="Filter by Program"
            >
              <option value="">All Programs</option>
              {programs.map((prog) => (
                <option key={prog.id} value={prog.id} title={prog.name}>
                  {prog.code || prog.name}
                </option>
              ))}
            </select>

            <select
              id="breach-filter-state"
              className="input-field w-full sm:w-auto sm:min-w-[150px]"
              value={filterBreachState}
              onChange={(e) => setFilterBreachState(e.target.value)}
              aria-label="Filter by readiness state"
            >
              {BREACH_STATE_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </select>

            <select
              id="breach-filter-next-type"
              className="input-field w-full sm:w-auto sm:min-w-[150px]"
              value={filterNextNoticeType}
              onChange={(e) => setFilterNextNoticeType(e.target.value)}
              aria-label="Filter by next notice type"
            >
              {NEXT_NOTICE_TYPE_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </select>

            {hasActiveFilters && (
              <Button type="button" variant="ghost" onClick={handleClearAllFilters}>
                Clear Filters
              </Button>
            )}
          </div>

          {/* Unified Requirement-Centric List */}
          <GlassPanel>
            <div className="mb-4">
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Escalation Requirements</h2>
              <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                Each row tracks an overdue requirement. Expand any row to view its full notice history, timeline, and document downloads.
              </p>
            </div>

            {loading ? (
              <div className="p-8 text-center text-sm text-brand-text-muted">
                <div className="animate-spin h-8 w-8 border-2 border-brand-primary border-t-transparent rounded-full mx-auto mb-3" />
                Loading requirements...
              </div>
            ) : breaches.length === 0 ? (
              <div className="p-8 text-center text-sm text-brand-text-muted">
                No overdue requirements match the active filters.
              </div>
            ) : (
              <div className="divide-y divide-brand-border">
                {breaches.map((row) => {
                  const isExpanded = expandedBreachIds.has(row.sla_id)
                  return (
                    <div key={row.sla_id} className="transition-colors hover:bg-slate-50/50 dark:hover:bg-slate-800/20">
                      {/* Summary Row */}
                      <div className="p-4 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-slate-900 dark:text-white text-base">
                              {row.project_name}
                            </span>
                            {row.program_code && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-mono">
                                {row.program_code}
                              </span>
                            )}
                          </div>
                          <div className="mt-1 flex items-center gap-3 text-xs text-brand-text-muted flex-wrap">
                            <span className="font-medium text-slate-700 dark:text-slate-300">
                              {row.requirement_name || 'General compliance requirement'}
                            </span>
                            <span>•</span>
                            <span>LGU: <strong className="text-slate-800 dark:text-slate-200 font-medium">{row.lgu_name || '—'}</strong></span>
                            <span>•</span>
                            <span>Due: {formatDate(row.deadline_date)} ({row.days_overdue} working days overdue)</span>
                          </div>
                        </div>

                        {/* Stage Badge & Context */}
                        <div className="flex flex-col items-start lg:items-end min-w-[180px]">
                          {stateBadge(row)}
                          <span className="mt-1 text-xs text-brand-text-muted">
                            {row.state === 'ready' && row.next_notice_type
                              ? `Ready for ${NOTICE_LABELS[row.next_notice_type] || row.next_notice_type}`
                              : row.blocking_message || (row.state === 'complete' ? 'All notices completed' : 'Awaiting prerequisites')}
                          </span>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex items-center gap-2 flex-wrap justify-end">
                          {row.blocking_reason === 'missing_annex_e' && (
                            <Button
                              size="sm"
                              icon={FilePenLine}
                              loading={actionLoadingKey === `create-${row.sla_id}`}
                              onClick={() => handleCreateAnnexE(row)}
                            >
                              Create Annex E
                            </Button>
                          )}
                          {row.state === 'ready' && row.next_notice_type && (
                            <Button
                              size="sm"
                              icon={FilePenLine}
                              loading={actionLoadingKey === `generate-${row.sla_id}`}
                              onClick={() => handleGenerateNext(row)}
                            >
                              Prepare {NOTICE_LABELS[row.next_notice_type] || formatMachineLabel(row.next_notice_type)}
                            </Button>
                          )}
                          {row.latest_notice_id && (
                            <Button
                              size="sm"
                              variant="outline"
                              icon={Eye}
                              onClick={() => openEditor(row.latest_notice_id)}
                            >
                              Open Notice
                            </Button>
                          )}
                          <button
                            type="button"
                            className="p-2 rounded-lg border border-brand-border text-brand-text-muted hover:text-brand-text hover:bg-brand-border/30 transition-colors inline-flex items-center justify-center"
                            onClick={() => toggleRowExpand(row.sla_id)}
                            aria-label={isExpanded ? 'Collapse timeline' : 'Expand notice timeline'}
                            title={isExpanded ? 'Collapse timeline' : 'Expand notice timeline'}
                          >
                            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                          </button>
                        </div>
                      </div>

                      {/* Expandable Accordion Drawer */}
                      {isExpanded && (
                        <div className="bg-slate-50/70 dark:bg-slate-900/40 p-4 border-t border-brand-border rounded-b-lg">
                          <div className="text-xs font-semibold text-brand-text-muted uppercase tracking-wider mb-3 flex items-center gap-1.5">
                            <History className="h-3.5 w-3.5 text-brand-primary" />
                            Notice Sequence & Document History
                          </div>

                          {/* Visual Step Indicator */}
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
                            {['annex_e', 'annex_m', 'annex_n', 'annex_o'].map((typeKey, idx) => {
                              const matchingNotice = (row.notices || []).find((n) => n.notice_type === typeKey)
                              const isReadyNext = row.state === 'ready' && row.next_notice_type === typeKey
                              return (
                                <div
                                  key={typeKey}
                                  className={`p-2.5 rounded-lg border text-xs transition-colors ${
                                    matchingNotice
                                      ? matchingNotice.status === 'acknowledged'
                                        ? 'border-emerald-500/30 bg-emerald-500/5 text-emerald-900 dark:text-emerald-300'
                                        : matchingNotice.status === 'sent'
                                        ? 'border-blue-500/30 bg-blue-500/5 text-blue-900 dark:text-blue-300'
                                        : 'border-brand-primary/30 bg-brand-primary/5 text-brand-text'
                                      : isReadyNext
                                      ? 'border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-300 font-semibold'
                                      : 'border-brand-border/60 bg-brand-surface/40 text-brand-text-muted opacity-60'
                                  }`}
                                >
                                  <div className="flex items-center justify-between mb-1">
                                    <span className="font-semibold">{idx + 1}. {NOTICE_LABELS[typeKey]}</span>
                                    {matchingNotice ? (
                                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                                    ) : isReadyNext ? (
                                      <Sparkles className="h-3.5 w-3.5 text-amber-500 animate-pulse" />
                                    ) : (
                                      <span className="h-2 w-2 rounded-full bg-brand-border" />
                                    )}
                                  </div>
                                  <p className="text-[11px] truncate">
                                    {matchingNotice
                                      ? matchingNotice.status === 'acknowledged'
                                        ? `Received ${formatDate(matchingNotice.acknowledged_at)}`
                                        : matchingNotice.status === 'sent'
                                        ? `Dispatched ${formatDate(matchingNotice.sent_at)}`
                                        : 'Draft In Progress'
                                      : isReadyNext
                                      ? 'Ready to Prepare'
                                      : 'Pending Prior Notice'}
                                  </p>
                                </div>
                              )
                            })}
                          </div>

                          {/* List of Issued Notices */}
                          {(row.notices || []).length > 0 ? (
                            <div className="space-y-2">
                              {(row.notices || []).map((noticeItem) => (
                                <div
                                  key={noticeItem.id}
                                  className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg border border-brand-border bg-brand-surface text-sm"
                                >
                                  <div className="flex items-center gap-3">
                                    <FileText className="h-4 w-4 text-brand-primary shrink-0" />
                                    <div>
                                      <span className="font-semibold text-brand-text">
                                        {NOTICE_LABELS[noticeItem.notice_type] || noticeItem.notice_type} #{noticeItem.notice_number}
                                      </span>
                                      <span className="ml-2 text-xs text-brand-text-muted">
                                        Prepared {formatDate(noticeItem.generated_at)}
                                        {noticeItem.sent_at && ` · Sent ${formatDate(noticeItem.sent_at)}`}
                                        {noticeItem.acknowledged_at && ` · Received ${formatDate(noticeItem.acknowledged_at)}`}
                                      </span>
                                    </div>
                                  </div>

                                  <div className="flex items-center gap-2">
                                    {noticeStatusBadge(noticeItem)}
                                    <Button size="sm" variant="outline" icon={FilePenLine} onClick={() => openEditor(noticeItem.id)}>
                                      Edit
                                    </Button>
                                    <Button size="sm" variant="outline" icon={Eye} onClick={() => handleOpenDocument(noticeItem.id, 'pdf')}>
                                      PDF
                                    </Button>
                                    <Button size="sm" variant="outline" icon={FileText} onClick={() => handleOpenDocument(noticeItem.id, 'docx')}>
                                      DOCX
                                    </Button>
                                    {canReleaseNotices && (noticeItem.status === 'draft' || noticeItem.status === 'reviewed') && (
                                      <Button size="sm" variant="outline" icon={Send} onClick={() => openReleaseModal(noticeItem)}>
                                        Release
                                      </Button>
                                    )}
                                    {noticeItem.status === 'sent' && !noticeItem.acknowledged_at && (
                                      <Button size="sm" variant="outline" icon={CheckCircle2} onClick={() => openReceiptModal(noticeItem)}>
                                        Acknowledgment
                                      </Button>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="p-3 bg-brand-surface rounded-lg border border-brand-border text-xs text-brand-text-muted">
                              No notices have been prepared for this requirement yet.
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </GlassPanel>
        </div>
      )}

      {activeView === 'register' && (
        <div className="space-y-6">
          {/* Register Filter Bar */}
          <div className="filter-bar flex flex-wrap items-center gap-3">
            <form
              onSubmit={handleSearchSubmit}
              className="flex min-w-[260px] flex-1 gap-2"
              role="search"
              aria-label="Search notices and follow-up records"
            >
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600 dark:text-slate-400" />
                <input
                  type="text"
                  className="input-field pl-9"
                  placeholder="Search notice, project, or requirement..."
                  value={searchDraft}
                  onChange={(e) => setSearchDraft(e.target.value)}
                />
              </div>
              <Button type="submit" variant="outline">Search</Button>
            </form>

            <select
              id="escalation-filter-lgu-reg"
              className="input-field w-full sm:w-auto sm:min-w-[150px]"
              value={filterLgu}
              onChange={(e) => { setNoticePage(1); setFilterLgu(e.target.value) }}
              aria-label="Filter by LGU"
            >
              <option value="">All LGUs</option>
              {lgus.map((lgu) => (
                <option key={lgu.id} value={lgu.id}>{lgu.name || lgu.municipality}</option>
              ))}
            </select>

            <select
              id="escalation-filter-program-reg"
              className="input-field w-full sm:w-auto sm:min-w-[140px]"
              value={filterProgram}
              onChange={(e) => { setNoticePage(1); setFilterProgram(e.target.value) }}
              aria-label="Filter by Program"
            >
              <option value="">All Programs</option>
              {programs.map((prog) => (
                <option key={prog.id} value={prog.id} title={prog.name}>
                  {prog.code || prog.name}
                </option>
              ))}
            </select>

            <select
              id="notice-filter-type"
              className="input-field w-full sm:w-auto sm:min-w-[150px]"
              value={filterNoticeType}
              onChange={(e) => { setNoticePage(1); setFilterNoticeType(e.target.value) }}
              aria-label="Filter by notice type"
            >
              {NOTICE_TYPE_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </select>

            <select
              id="notice-filter-status"
              className="input-field w-full sm:w-auto sm:min-w-[150px]"
              value={filterNoticeStatus}
              onChange={(e) => { setNoticePage(1); setFilterNoticeStatus(e.target.value) }}
              aria-label="Filter by notice status"
            >
              {NOTICE_STATUS_FILTER_OPTIONS.map((f) => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </select>

            {hasActiveFilters && (
              <Button type="button" variant="ghost" onClick={handleClearAllFilters}>
                Clear Filters
              </Button>
            )}
          </div>

          {/* Document Table */}
          <GlassPanel>
            <div className="mb-4">
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Official Document Register</h2>
              <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                Complete registry of prepared notice documents. Download DOCX/PDF output, edit contents, and record official dispatch/acknowledgments.
              </p>
            </div>
            <OfficialNoticeRegister
              notices={notices}
              loading={loading}
              pagination={noticeMeta}
              noticeLabels={NOTICE_LABELS}
              renderStatus={noticeStatusBadge}
              canRelease={canReleaseNotices}
              onOpen={openEditor}
              onRelease={openReleaseModal}
              onReceipt={openReceiptModal}
              onDocument={(id, format) => handleOpenDocument(id, format).catch(() => {})}
              onPageChange={setNoticePage}
            />
          </GlassPanel>
        </div>
      )}

      <Modal
        open={editorOpen}
        title={noticeDraft ? `${NOTICE_LABELS[noticeDraft.notice_type] || formatMachineLabel(noticeDraft.notice_type)} Notice Document` : ''}
        description={noticeDraft ? 'Review the notice content, preview the generated document, then track release and acknowledgment as separate workflow actions.' : ''}
        size="2xl"
        onClose={closeEditor}
        footer={noticeDraft ? (
          <div className="flex items-center justify-between gap-3 w-full">
            <div className="text-xs text-brand-text-muted">
              {editorTab === 'preview' ? 'Previewing rendered OpenXML document.' : 'Unsaved edits are dynamically synchronized to document preview.'}
            </div>
            <div className="flex gap-3">
              <Button variant="outline" onClick={closeEditor}>Close</Button>
              <Button loading={editorSaving} onClick={handleSaveNotice}>Save Notice</Button>
            </div>
          </div>
        ) : null}
      >
        {editorLoading ? (
          <div className="py-10 text-center text-slate-400">Loading notice...</div>
        ) : noticeDraft ? (
          <>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-brand-border">
              <div className="flex gap-2">
                <button
                  type="button"
                  className={`border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
                    editorTab === 'details'
                      ? 'border-brand-primary text-brand-primary'
                      : 'border-transparent text-brand-text-muted hover:text-brand-text'
                  }`}
                  onClick={() => setEditorTab('details')}
                >
                  Notice Content & Findings
                </button>
                <button
                  type="button"
                  className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
                    editorTab === 'preview'
                      ? 'border-brand-primary text-brand-primary'
                      : 'border-transparent text-brand-text-muted hover:text-brand-text'
                  }`}
                  onClick={handleSwitchToPreviewTab}
                >
                  <Eye className="h-4 w-4" />
                  Document Preview & Download
                </button>
              </div>
              <div className="flex items-center gap-2 pb-2">
                <Button size="sm" variant="outline" onClick={() => handleOpenDocument(noticeDraft.id, 'pdf')}>
                  Open PDF
                </Button>
                {editorTab === 'details' ? (
                  <Button size="sm" variant="outline" icon={Eye} onClick={handleSwitchToPreviewTab}>
                    Preview / Download DOCX
                  </Button>
                ) : (
                  <Button size="sm" icon={FileText} onClick={handleDownloadDocumentTemplate} loading={documentDownloading}>
                    Download DOCX
                  </Button>
                )}
              </div>
            </div>

            <InlineAlert type="error" className="mb-4" onDismiss={() => setEditorError('')}>
              {editorError}
            </InlineAlert>

            {editorTab === 'details' ? (
              <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.1fr_0.9fr]">
                  <div className="space-y-4">
                    <div>
                      <label className="label-text">Notice Title</label>
                      <input
                        className="input-field mt-1"
                        value={noticeDraft.title}
                        onChange={(event) => setNoticeDraft((current) => ({ ...current, title: event.target.value }))}
                      />
                    </div>

                    <div className="grid gap-4 lg:grid-cols-3">
                      <div>
                        <label className="label-text">Document State</label>
                        {['sent', 'acknowledged'].includes(noticeDraft.status) ? (
                          <div className="input-field mt-1 flex min-h-[44px] items-center text-sm text-brand-text">
                            {NOTICE_STATUS_LABELS[noticeDraft.status] || formatStatus(noticeDraft.status)}
                          </div>
                        ) : (
                          <select
                            className="input-field mt-1"
                            value={noticeDraft.status}
                            onChange={(event) => setNoticeDraft((current) => ({ ...current, status: event.target.value }))}
                          >
                            <option value="draft">Draft</option>
                            <option value="reviewed">Ready for Release</option>
                            <option value="expired">Expired</option>
                          </select>
                        )}
                      </div>
                      <div>
                        <label className="label-text">Released On</label>
                        <div className="input-field mt-1 flex min-h-[44px] items-center text-sm text-brand-text">
                          {formatDateTime(noticeDraft.sent_at)}
                        </div>
                      </div>
                      <div>
                        <label className="label-text">Received On</label>
                        <div className="input-field mt-1 flex min-h-[44px] items-center text-sm text-brand-text">
                          {formatDateTime(noticeDraft.acknowledged_at)}
                        </div>
                      </div>
                    </div>

                    <div>
                      <label className="label-text">Notice Body Text</label>
                      <textarea
                        className="input-field mt-1 min-h-[220px]"
                        value={noticeDraft.body_text || ''}
                        onChange={(event) => setNoticeDraft((current) => ({ ...current, body_text: event.target.value }))}
                      />
                    </div>

                    <div>
                      <label className="label-text">Supplemental Routing Text</label>
                      <textarea
                        className="input-field mt-1 min-h-[220px]"
                        value={noticeDraft.final_text || ''}
                        onChange={(event) => setNoticeDraft((current) => ({ ...current, final_text: event.target.value }))}
                        placeholder="Add reviewed notice language or routing notes that should appear in the final annex."
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <h3 className="text-base font-semibold text-slate-900 dark:text-white">Findings / Observations</h3>
                      {noticeDraft.notice_type === 'annex_e' && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setNoticeDraft((current) => ({
                            ...current,
                            legal_findings: [...(current.legal_findings || []), blankFinding()],
                          }))}
                        >
                          Add Finding
                        </Button>
                      )}
                    </div>

                    {(noticeDraft.legal_findings || []).map((finding, index) => (
                      <div key={`${noticeDraft.id}-finding-${index}`} className="space-y-3 rounded-lg border border-brand-border bg-brand-surface p-4">
                        <div>
                          <div className="flex items-center justify-between gap-3">
                            <label className="label-text">Remarks / Notes</label>
                            {noticeDraft.notice_type === 'annex_e' && (
                              <Button
                                size="sm"
                                variant="outline"
                                icon={FilePenLine}
                                loading={findingAiKey === `${noticeDraft.id}-${index}`}
                                onClick={() => handleAiDraft(index)}
                              >
                                Draft with Assistant
                              </Button>
                            )}
                          </div>
                          <textarea
                            className="input-field mt-1 min-h-[72px]"
                            value={finding.informal_notes || ''}
                            onChange={(event) => updateFinding(index, 'informal_notes', event.target.value)}
                          />
                        </div>
                        <div>
                          <label className="label-text">Finding / Observation</label>
                          <textarea
                            className="input-field mt-1 min-h-[96px]"
                            value={finding.formal_findings || ''}
                            onChange={(event) => updateFinding(index, 'formal_findings', event.target.value)}
                          />
                        </div>
                        <div>
                          <label className="label-text">Recommendation</label>
                          <textarea
                            className="input-field mt-1 min-h-[96px]"
                            value={finding.recommendations || ''}
                            onChange={(event) => updateFinding(index, 'recommendations', event.target.value)}
                          />
                        </div>
                        <div>
                          <label className="label-text">Timeline / Agreement</label>
                          <textarea
                            className="input-field mt-1 min-h-[80px]"
                            value={finding.agreements_timelines || ''}
                            onChange={(event) => updateFinding(index, 'agreements_timelines', event.target.value)}
                          />
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="space-y-4">
                    {!!noticeDraft.recipients?.length && (
                      <div className="rounded-lg border border-brand-border bg-brand-surface px-4 py-3 text-sm text-brand-text">
                        <div className="mb-2 font-medium text-brand-text">Auto-populated Recipients</div>
                        <div className="space-y-1">
                          {noticeDraft.recipients.map((recipient) => (
                            <div key={recipient.id || recipient.recipient_email}>
                              {recipient.recipient_name} ({recipient.recipient_role ? formatRole(recipient.recipient_role) : 'Recipient'}){recipient.recipient_email ? ` - ${recipient.recipient_email}` : ''}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="space-y-4 rounded-lg border border-brand-border bg-brand-surface p-4">
                      <div>
                        <h3 className="text-base font-semibold text-slate-900 dark:text-white">Release and Acknowledgment</h3>
                        <p className="mt-1 text-xs text-slate-400">
                          Document output stays separate from official release and acknowledgment tracking.
                        </p>
                      </div>

                      <div className="grid gap-3 sm:grid-cols-3">
                        <div className="rounded-lg border border-brand-border bg-brand-surface-solid px-3 py-3">
                          <div className="text-xs font-medium uppercase tracking-wide text-brand-text-muted">State</div>
                          <div className="mt-1 text-sm font-semibold text-brand-text">
                            {NOTICE_STATUS_LABELS[noticeDraft.status] || formatStatus(noticeDraft.status)}
                          </div>
                        </div>
                        <div className="rounded-lg border border-brand-border bg-brand-surface-solid px-3 py-3">
                          <div className="text-xs font-medium uppercase tracking-wide text-brand-text-muted">Released</div>
                          <div className="mt-1 text-sm font-semibold text-brand-text">{formatDateTime(noticeDraft.sent_at)}</div>
                        </div>
                        <div className="rounded-lg border border-brand-border bg-brand-surface-solid px-3 py-3">
                          <div className="text-xs font-medium uppercase tracking-wide text-brand-text-muted">Acknowledged</div>
                          <div className="mt-1 text-sm font-semibold text-brand-text">{formatDateTime(noticeDraft.acknowledged_at)}</div>
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        {canReleaseNotices && (
                          <Button
                            size="sm"
                            icon={Send}
                            loading={workflowLoadingKey === 'release'}
                            disabled={noticeDraft.status !== 'reviewed' || !!noticeDraft.sent_at || workflowLoadingKey === 'receipt'}
                            onClick={() => openReleaseModal()}
                          >
                            Mark Released
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="outline"
                          icon={CheckCircle2}
                          loading={workflowLoadingKey === 'receipt'}
                          disabled={!noticeDraft.sent_at || !!noticeDraft.acknowledged_at || workflowLoadingKey === 'release'}
                          onClick={() => openReceiptModal()}
                        >
                          Record Acknowledgment
                        </Button>
                      </div>

                      {!!noticeDraft.communications?.length && (
                        <div className="rounded-lg border border-brand-border bg-brand-surface p-4">
                          <div className="mb-3 text-sm font-medium text-brand-text">Release History</div>
                          <div className="space-y-3">
                            {noticeDraft.communications.map((communication) => (
                              <div key={communication.id} className="rounded-lg border border-brand-border bg-brand-surface-solid px-3 py-3 text-xs text-brand-text-muted">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <span className="font-medium text-brand-text">
                                    {formatMachineLabel(communication.channel)} · {communication.reference_no || 'No ref. no.'}
                                  </span>
                                  <span>{formatDateTime(communication.sent_at || communication.created_at)}</span>
                                </div>
                                <div className="mt-2 text-slate-400">
                                  {communication.recipient_name || 'Recipient not specified'}{communication.recipient_destination ? ` · ${communication.recipient_destination}` : ''}
                                </div>
                                {communication.remarks && (
                                  <div className="mt-2 text-slate-400">{communication.remarks}</div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap items-end justify-between gap-4">
                  <div className="min-w-[240px] flex-1">
                    {documentTemplates.length > 0 ? (
                      <div>
                        <label className="label-text" htmlFor="notice-document-template">Template</label>
                        <select
                          id="notice-document-template"
                          className="input-field mt-1"
                          value={selectedDocumentTemplateId}
                          onChange={(event) => handleSelectDocumentTemplate(event.target.value)}
                        >
                          {documentTemplates.map((template) => (
                            <option key={template.id} value={template.id}>
                              {template.label || template.file_name}
                            </option>
                          ))}
                        </select>
                      </div>
                    ) : (
                      <InlineAlert type="info">
                        No custom DOCX template is configured for this notice type. The built-in layout will be used.
                      </InlineAlert>
                    )}

                    {selectedDocumentTemplate && (
                      <p className="mt-1 text-xs text-brand-text-muted">
                        Template file: {selectedDocumentTemplate.file_name}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => handlePreviewDocumentTemplate(selectedDocumentTemplateId, documentPlaceholderValues, noticeDraft)}
                      loading={documentPreviewLoading}
                    >
                      Refresh Preview
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => handleOpenDocument(noticeDraft.id, 'pdf')}
                    >
                      Open PDF
                    </Button>
                    <Button
                      type="button"
                      icon={FileText}
                      onClick={handleDownloadDocumentTemplate}
                      loading={documentDownloading}
                    >
                      Download DOCX
                    </Button>
                  </div>
                </div>

                {documentVariableFields.length > 0 ? (
                  <div className="rounded-lg border border-brand-border bg-brand-surface p-4">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-brand-text-muted">
                      Template Scanned Variables
                    </div>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      {documentVariableFields.map(({ key, label }) => (
                        <div key={key}>
                          <label className="label-text" htmlFor={`notice-document-${key}`}>{label || formatMachineLabel(key)}</label>
                          <input
                            id={`notice-document-${key}`}
                            className="input-field mt-1"
                            value={documentPlaceholderValues[key] || ''}
                            onChange={(event) => setDocumentPlaceholderValues((current) => ({
                              ...current,
                              [key]: event.target.value,
                            }))}
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-brand-text-muted">
                    This template does not expose editable scanned variables, or all variables are filled directly from the notice record.
                  </p>
                )}

                <DocumentPreview
                  document={documentPreview}
                  fallbackText={documentPreview?.preview_text}
                  title="Generated document preview"
                  loading={documentPreviewLoading}
                />
              </div>
            )}
          </>
        ) : null}
      </Modal>

      <Modal
        open={releaseModalOpen}
        title="Mark Notice Released"
        description="Record the official release channel and reference details."
        size="lg"
        onClose={() => {
          if (!workflowLoadingKey) setReleaseModalOpen(false)
        }}
      >
        <div className="space-y-4">
          <InlineAlert type="error" onDismiss={() => setEditorError('')}>
            {editorError}
          </InlineAlert>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label-text" htmlFor="notice-release-channel">Release Channel</label>
              <select
                id="notice-release-channel"
                className="input-field mt-1"
                value={releaseForm.channel}
                onChange={(event) => setReleaseForm((current) => ({ ...current, channel: event.target.value }))}
              >
                <option value="dms">DMS</option>
                <option value="intranet">Intranet</option>
                <option value="manual_print">Manual Print</option>
                <option value="email">Email</option>
              </select>
            </div>
            <div>
              <label className="label-text" htmlFor="notice-release-at">Released At</label>
              <input
                id="notice-release-at"
                type="datetime-local"
                className="input-field mt-1"
                value={releaseForm.released_at}
                onChange={(event) => setReleaseForm((current) => ({ ...current, released_at: event.target.value }))}
              />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label-text" htmlFor="notice-release-recipient">Recipient Name</label>
              <input
                id="notice-release-recipient"
                className="input-field mt-1"
                value={releaseForm.recipient_name}
                onChange={(event) => setReleaseForm((current) => ({ ...current, recipient_name: event.target.value }))}
              />
            </div>
            <div>
              <label className="label-text" htmlFor="notice-release-reference">Reference No.</label>
              <input
                id="notice-release-reference"
                className="input-field mt-1"
                value={releaseForm.reference_no}
                onChange={(event) => setReleaseForm((current) => ({ ...current, reference_no: event.target.value }))}
              />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label-text" htmlFor="notice-release-destination">Recipient Destination</label>
              <input
                id="notice-release-destination"
                className="input-field mt-1"
                value={releaseForm.recipient_destination}
                onChange={(event) => setReleaseForm((current) => ({ ...current, recipient_destination: event.target.value }))}
              />
            </div>
            <div>
              <label className="label-text" htmlFor="notice-release-office">Recipient Office</label>
              <input
                id="notice-release-office"
                className="input-field mt-1"
                value={releaseForm.recipient_office}
                onChange={(event) => setReleaseForm((current) => ({ ...current, recipient_office: event.target.value }))}
              />
            </div>
          </div>
          <div>
            <label className="label-text" htmlFor="notice-release-remarks">Remarks</label>
            <textarea
              id="notice-release-remarks"
              className="input-field mt-1 min-h-[90px]"
              value={releaseForm.remarks}
              onChange={(event) => setReleaseForm((current) => ({ ...current, remarks: event.target.value }))}
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <Button type="button" variant="outline" onClick={() => setReleaseModalOpen(false)} disabled={!!workflowLoadingKey}>
              Cancel
            </Button>
            <Button type="button" icon={Send} onClick={handleReleaseNotice} loading={workflowLoadingKey === 'release'}>
              Mark Released
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={receiptModalOpen}
        title="Record Notice Acknowledgment"
        description="Record the date the released notice was delivered or acknowledged."
        size="md"
        onClose={() => {
          if (!workflowLoadingKey) setReceiptModalOpen(false)
        }}
      >
        <div className="space-y-4">
          <InlineAlert type="error" onDismiss={() => setEditorError('')}>
            {editorError}
          </InlineAlert>
          <div>
            <label className="label-text" htmlFor="notice-receipt-at">Acknowledged / Delivery Date</label>
            <input
              id="notice-receipt-at"
              type="datetime-local"
              className="input-field mt-1"
              value={receiptForm.acknowledged_at}
              onChange={(event) => setReceiptForm((current) => ({ ...current, acknowledged_at: event.target.value }))}
            />
          </div>
          <div>
            <label className="label-text" htmlFor="notice-receipt-remarks">Remarks</label>
            <textarea
              id="notice-receipt-remarks"
              className="input-field mt-1 min-h-[90px]"
              value={receiptForm.remarks}
              onChange={(event) => setReceiptForm((current) => ({ ...current, remarks: event.target.value }))}
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <Button type="button" variant="outline" onClick={() => setReceiptModalOpen(false)} disabled={!!workflowLoadingKey}>
              Cancel
            </Button>
            <Button type="button" icon={CheckCircle2} onClick={handleRecordReceipt} loading={workflowLoadingKey === 'receipt'}>
              Record Acknowledgment
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
