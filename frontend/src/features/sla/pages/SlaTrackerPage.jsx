import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Clock, AlertTriangle, CheckCircle2, Timer, Plus, Search, Info, X } from 'lucide-react'
import { Button, CategoryBadge, InlineAlert, KpiCard, useToast, PageHeader, FormField, Modal } from '../../../components'
import { isAdmin, isStaff } from '../../../lib/auth'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import { apiErrorMessage } from '../../../lib/formErrors'
import { useBranding } from '../../../hooks/useBranding'
import * as projectApi from '../../projects/api/projectApi'
import { ComplianceDeadlinesTable } from '../components/ComplianceDeadlinesTable'
import { deadlinePosition } from '../utils/deadlinePresentation'
import * as slaApi from '../api/slaApi'

const TYPE_FILTERS = [
  { value: '', label: 'All Types' },
  { value: 'notice_of_eligibility_5day', label: 'Notice of Eligibility (5 Working Days)' },
  { value: 'standard_15day', label: '15-Working-Day Notice Window' },
  { value: 'rectification_period', label: 'Rectification Period' },
  { value: 'custom_sla', label: 'Internal Tracking Timer' },
]

const STATUS_FILTERS = [
  { value: '', label: 'All Statuses' },
  { value: 'active', label: 'Active' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'resolved', label: 'Closed' },
]

const SCOPE_FILTERS = [
  { value: '', label: 'All Scopes' },
  { value: 'requirement', label: 'Requirements' },
  { value: 'project', label: 'Project-Level' },
]

const REQUIREMENT_STATUS_FILTERS = [
  { value: '', label: 'Any Requirement Status' },
  { value: 'pending', label: 'Pending' },
  { value: 'under_review', label: 'Under Review' },
  { value: 'compliant', label: 'Compliant' },
  { value: 'non_compliant', label: 'Non-Compliant' },
  { value: 'waived', label: 'Waived' },
]

const DUE_FILTERS = [
  { value: '', label: 'Any Due Window' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'due_today', label: 'Due Today' },
  { value: 'due_3', label: 'Due in 3 Working Days' },
  { value: 'due_7', label: 'Due in 7 Working Days' },
  { value: 'future', label: 'Future' },
  { value: 'report_due_3', label: 'Report: Due in 1–3 Working Days' },
  { value: 'report_due_7', label: 'Report: Due in 4–7 Working Days' },
  { value: 'report_future', label: 'Report: More Than 7 Working Days' },
]

function parsePositiveInteger(value) {
  if (!value) return ''
  const trimmed = String(value).trim()
  return /^\d+$/.test(trimmed) ? trimmed : ''
}

function initialCreateForm() {
  return {
    timer_intent: 'compliance_deadline',
    timer_scope: 'requirement',
    project_id: '',
    project_requirement_id: '',
    deadline_type: 'standard_15day',
    trigger_date: '',
    deadline_date: '',
    sla_working_days: '',
    notes: '',
  }
}

function deadlineTypeFromDays(days) {
  if (!days) return 'standard_15day'
  if (days <= 5) return 'notice_of_eligibility_5day'
  if (days >= 15) return 'standard_15day'
  return 'rectification_period'
}

function statusBadge(row) {
  const { isOverdue } = getDeadlineMetrics(row)
  if (row.is_resolved) {
    return <span className={badgeClassForStatus('resolved')}>Closed</span>
  }
  if (isOverdue) {
    return <span className={badgeClassForStatus('overdue')}>Overdue</span>
  }
  return <span className={badgeClassForStatus('active')}>Active</span>
}

function formatDate(dt) {
  if (!dt) return '-'
  try { return new Date(dt).toLocaleDateString('en-PH', { year: 'numeric', month: 'short', day: 'numeric' }) }
  catch { return dt }
}

function parseDateInput(value) {
  const text = String(value || '').trim()
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return null
  const parsed = new Date(`${text}T00:00:00.000Z`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function formatStatusText(value) {
  if (!value) return '-'
  return String(value).replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function countWorkingDaysBetween(fromDate, toDate) {
  const start = new Date(fromDate)
  const end = new Date(toDate)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null
  if (end <= start) return 0

  const cursor = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate()))
  const endDate = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), end.getUTCDate()))
  let workingDays = 0

  while (cursor < endDate) {
    cursor.setUTCDate(cursor.getUTCDate() + 1)
    const day = cursor.getUTCDay()
    if (day !== 0 && day !== 6) workingDays += 1
  }

  return workingDays
}

function workingDaysDelta(fromDate, toDate) {
  const start = new Date(fromDate)
  const end = new Date(toDate)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null
  if (end >= start) return countWorkingDaysBetween(start, end)
  const inverse = countWorkingDaysBetween(end, start)
  return inverse === null ? null : -inverse
}

function getDeadlineMetrics(row) {
  if (row.is_resolved) return { daysRemaining: null, isOverdue: false }
  const now = new Date()
  const deadline = new Date(row.deadline_date)
  if (Number.isNaN(deadline.getTime())) return { daysRemaining: null, isOverdue: false }

  const todayUtc = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))
  const deadlineUtc = new Date(Date.UTC(deadline.getUTCFullYear(), deadline.getUTCMonth(), deadline.getUTCDate()))

  const daysRemaining = workingDaysDelta(todayUtc, deadlineUtc)
  const isOverdue = deadline < now

  return { daysRemaining, isOverdue }
}


export default function SlaTrackerPage() {
  const { branding } = useBranding()
  const [searchParams, setSearchParams] = useSearchParams()
  const reportProjectStatus = searchParams.get('project_status') || ''
  const rawLguId = searchParams.get('lgu_id')
  const initialLguId = parsePositiveInteger(rawLguId)
  const initialProjectId = parsePositiveInteger(searchParams.get('project_id'))
  const initialDueBucket = searchParams.get('due_bucket') || ''
  const initialStatus = searchParams.get('status') || ''

  const isInitialOverdue = initialDueBucket === 'overdue' || initialStatus === 'overdue'
  const effectiveInitialDueBucket = initialDueBucket || (initialStatus === 'overdue' ? 'overdue' : '')

  const toast = useToast()
  const [dashboard, setDashboard] = useState(null)
  const [dashboardError, setDashboardError] = useState(false)
  const [deadlines, setDeadlines] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [meta, setMeta] = useState({ total: 0, pages: 1, page: 1, per_page: 20 })

  const [filterLguId, setFilterLguId] = useState(initialLguId)
  const [filterProjectId, setFilterProjectId] = useState(initialProjectId)
  const [filterType, setFilterType] = useState('')
  const [filterStatus, setFilterStatus] = useState(initialStatus)
  const [filterScope, setFilterScope] = useState('')
  const [filterRequirementStatus, setFilterRequirementStatus] = useState('')
  const [filterDueBucket, setFilterDueBucket] = useState(effectiveInitialDueBucket)
  const [overdueOnly, setOverdueOnly] = useState(isInitialOverdue)
  const [searchDraft, setSearchDraft] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [page, setPage] = useState(1)

  const activeLguName = useMemo(() => {
    if (!filterLguId) return ''
    const match = deadlines.find((d) => String(d.lgu_id) === String(filterLguId))
    return match?.lgu_name || ''
  }, [filterLguId, deadlines])

  useEffect(() => {
    const urlLguId = parsePositiveInteger(searchParams.get('lgu_id'))
    setFilterLguId(urlLguId)
    const urlProjectId = parsePositiveInteger(searchParams.get('project_id'))
    setFilterProjectId(urlProjectId)

    const urlDue = searchParams.get('due_bucket') || ''
    const urlStatus = searchParams.get('status') || ''
    if (urlDue) {
      setFilterDueBucket(urlDue)
      setOverdueOnly(urlDue === 'overdue')
    } else if (urlStatus === 'overdue') {
      setFilterDueBucket('overdue')
      setOverdueOnly(true)
    } else {
      setFilterDueBucket('')
      setOverdueOnly(false)
    }

    if (urlStatus) {
      setFilterStatus(urlStatus)
    }
  }, [searchParams])

  const handleClearLguFilter = () => {
    setFilterLguId('')
    setPage(1)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('lgu_id')
      return next
    }, { replace: true })
  }

  const handleDueBucketChange = (value) => {
    setFilterDueBucket(value)
    const isOverdue = value === 'overdue'
    setOverdueOnly(isOverdue)
    if (filterStatus === 'overdue' && !isOverdue) {
      setFilterStatus('')
    }
    setPage(1)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value) {
        next.set('due_bucket', value)
      } else {
        next.delete('due_bucket')
      }
      if (!isOverdue && next.get('status') === 'overdue') {
        next.delete('status')
      }
      return next
    }, { replace: true })
  }

  const handleToggleOverdueOnly = () => {
    const nextOverdue = !overdueOnly
    setOverdueOnly(nextOverdue)
    const nextDueBucket = nextOverdue ? 'overdue' : (filterDueBucket === 'overdue' ? '' : filterDueBucket)
    setFilterDueBucket(nextDueBucket)
    if (!nextOverdue && filterStatus === 'overdue') {
      setFilterStatus('')
    }
    setPage(1)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (nextOverdue) {
        next.set('due_bucket', 'overdue')
      } else {
        if (next.get('due_bucket') === 'overdue') {
          next.delete('due_bucket')
        }
        if (next.get('status') === 'overdue') {
          next.delete('status')
        }
      }
      return next
    }, { replace: true })
  }

  const handleStatusChange = (value) => {
    setFilterStatus(value)
    if (value === 'overdue') {
      setFilterDueBucket('overdue')
      setOverdueOnly(true)
    } else if (filterDueBucket === 'overdue') {
      setFilterDueBucket('')
      setOverdueOnly(false)
    }
    setPage(1)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value) {
        next.set('status', value)
      } else {
        next.delete('status')
      }
      if (value === 'overdue') {
        next.set('due_bucket', 'overdue')
      } else if (next.get('due_bucket') === 'overdue') {
        next.delete('due_bucket')
      }
      return next
    }, { replace: true })
  }

  const [resolving, setResolving] = useState(null)
  const [resolveNotes, setResolveNotes] = useState('')
  const [resolveLoading, setResolveLoading] = useState(false)
  const [resolveError, setResolveError] = useState('')
  const resolveSubmittingRef = useRef(false)
  const [selectedDetail, setSelectedDetail] = useState(null)
  const [showSemantics, setShowSemantics] = useState(false)
  const semanticsRef = useRef(null)

  useEffect(() => {
    if (!showSemantics) return undefined

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setShowSemantics(false)
      }
    }

    const handleClickOutside = (event) => {
      if (semanticsRef.current && !semanticsRef.current.contains(event.target)) {
        setShowSemantics(false)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showSemantics])

  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState(initialCreateForm())
  const [createError, setCreateError] = useState('')
  const [createLoading, setCreateLoading] = useState(false)
  const createSubmittingRef = useRef(false)
  const [projectSearch, setProjectSearch] = useState('')
  const [projectSearchAttempted, setProjectSearchAttempted] = useState(false)
  const [projectOptions, setProjectOptions] = useState([])
  const [projectLoading, setProjectLoading] = useState(false)
  const [selectedProject, setSelectedProject] = useState(null)
  const [projectRequirements, setProjectRequirements] = useState([])
  const [requirementsLoading, setRequirementsLoading] = useState(false)
  const projectSearchRequestRef = useRef(0)

  const selectedRequirement = projectRequirements.find((item) => String(item.id) === String(createForm.project_requirement_id))
  const usesConfiguredRequirementSla = createForm.timer_scope === 'requirement' && Boolean(selectedRequirement?.has_sla && selectedRequirement?.sla_days)

  const fetchDashboard = useCallback(async () => {
    try {
      const res = await slaApi.getSlaDashboard()
      setDashboard(res.data)
      setDashboardError(false)
    } catch {
      setDashboardError(true)
    }
  }, [])

  const fetchDeadlines = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = { page, per_page: 20 }
      if (reportProjectStatus) params.project_status = reportProjectStatus
      if (appliedSearch) params.search = appliedSearch
      if (filterType) params.deadline_type = filterType
      if (filterScope === 'requirement') params.has_requirement = 'true'
      if (filterScope === 'project') params.has_requirement = 'false'
      if (filterRequirementStatus) params.requirement_status = filterRequirementStatus
      if (filterLguId) params.lgu_id = Number(filterLguId)
      if (filterProjectId) params.project_id = Number(filterProjectId)
      if (filterDueBucket) params.due_bucket = filterDueBucket
      if (overdueOnly || filterStatus === 'overdue' || filterDueBucket === 'overdue') params.overdue_only = 'true'
      if (filterStatus === 'resolved') params.is_resolved = 'true'
      else if (filterStatus === 'active') params.is_resolved = 'false'
      const res = await slaApi.listSlaDeadlines(params)
      setDeadlines(res.data || [])
      if (res.meta) setMeta(res.meta)
    } catch (err) {
      setError(apiErrorMessage(err, 'Unable to load compliance deadlines. Please try again.'))
    } finally {
      setLoading(false)
    }
  }, [page, appliedSearch, filterType, filterScope, filterRequirementStatus, filterLguId, filterProjectId, filterDueBucket, filterStatus, overdueOnly, reportProjectStatus])

  useEffect(() => { fetchDashboard() }, [fetchDashboard])
  useEffect(() => { fetchDeadlines() }, [fetchDeadlines])

  const resetCreateState = () => {
    projectSearchRequestRef.current += 1
    setCreateForm(initialCreateForm())
    setCreateError('')
    setProjectSearch('')
    setProjectSearchAttempted(false)
    setProjectOptions([])
    setSelectedProject(null)
    setProjectRequirements([])
  }

  const closeCreateModal = () => {
    setShowCreate(false)
    resetCreateState()
  }

  const searchProjectOptions = useCallback(async (searchValue) => {
    const requestId = projectSearchRequestRef.current + 1
    projectSearchRequestRef.current = requestId
    setProjectLoading(true)
    setCreateError('')
    setProjectSearchAttempted(true)
    try {
      const params = { per_page: 10 }
      const term = String(searchValue || '').trim()
      if (term) params.search = term
      const res = await projectApi.searchProjectsAcrossFiscalYears(params)
      if (requestId !== projectSearchRequestRef.current) return
      setProjectOptions(res.data || [])
    } catch {
      if (requestId !== projectSearchRequestRef.current) return
      setProjectOptions([])
      setCreateError('Unable to search projects.')
    } finally {
      if (requestId === projectSearchRequestRef.current) {
        setProjectLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    if (!showCreate) return undefined

    const term = projectSearch.trim()
    if (term.length < 2) {
      projectSearchRequestRef.current += 1
      setProjectLoading(false)
      setProjectOptions([])
      setProjectSearchAttempted(false)
      return undefined
    }

    const timeoutId = window.setTimeout(() => {
      searchProjectOptions(term)
    }, 250)

    return () => window.clearTimeout(timeoutId)
  }, [projectSearch, searchProjectOptions, showCreate])

  const handleProjectSearch = () => {
    searchProjectOptions(projectSearch)
  }

  const handleProjectSearchChange = (value) => {
    projectSearchRequestRef.current += 1
    setProjectSearch(value)
    setCreateError('')
    setProjectOptions([])
    setProjectSearchAttempted(false)
    setSelectedProject(null)
    setProjectRequirements([])
    setCreateForm((current) => ({
      ...current,
      project_id: '',
      project_requirement_id: '',
      deadline_date: '',
      sla_working_days: '',
    }))
  }

  const handleProjectSelect = async (projectId) => {
    const project = projectOptions.find((item) => String(item.id) === String(projectId)) || null
    setSelectedProject(project)
    setProjectRequirements([])
    setCreateForm((current) => ({
      ...current,
      project_id: projectId,
      project_requirement_id: '',
      deadline_date: '',
      sla_working_days: '',
    }))
    if (!projectId) return

    setRequirementsLoading(true)
    setCreateError('')
    try {
      const res = await projectApi.listProjectRequirements(projectId)
      setProjectRequirements(res.data || [])
    } catch {
      setProjectRequirements([])
      setCreateError('Unable to load project requirements.')
    } finally {
      setRequirementsLoading(false)
    }
  }

  const handleRequirementSelect = (requirementId) => {
    const requirement = projectRequirements.find((item) => String(item.id) === String(requirementId))
    setCreateForm((current) => ({
      ...current,
      project_requirement_id: requirementId,
      deadline_type: current.timer_intent === 'internal_timer' ? 'custom_sla' : deadlineTypeFromDays(requirement?.sla_days),
      sla_working_days: requirement?.sla_days || '',
      deadline_date: requirement?.has_sla ? '' : current.deadline_date,
    }))
  }

  const handleResolve = async () => {
    if (!resolving || resolveSubmittingRef.current) return
    resolveSubmittingRef.current = true
    setResolveLoading(true)
    setResolveError('')
    try {
      await slaApi.resolveSlaDeadline(resolving.id, { notes: resolveNotes })
      setResolving(null)
      setResolveNotes('')
      fetchDeadlines()
      fetchDashboard()
      toast.success('Compliance deadline marked as closed.')
    } catch (err) {
      setResolveError(err.response?.data?.message || 'Unable to mark the deadline as closed.')
    } finally {
      resolveSubmittingRef.current = false
      setResolveLoading(false)
    }
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    if (createSubmittingRef.current) return
    const isRequirementTimer = createForm.timer_scope === 'requirement'
    if (!createForm.project_id) {
      setCreateError('Select a project before recording a compliance deadline.')
      return
    }
    if (!createForm.trigger_date) {
      setCreateError('Trigger date is required.')
      return
    }
    const triggerDate = parseDateInput(createForm.trigger_date)
    if (!triggerDate) {
      setCreateError('Trigger date must be a valid calendar date.')
      return
    }
    if (isRequirementTimer && !createForm.project_requirement_id) {
      setCreateError('Select the requirement this deadline tracks.')
      return
    }
    if (!usesConfiguredRequirementSla && (!createForm.deadline_type || !createForm.deadline_date)) {
      setCreateError('Deadline type and deadline date are required for manual deadlines.')
      return
    }
    const deadlineDate = usesConfiguredRequirementSla ? null : parseDateInput(createForm.deadline_date)
    if (!usesConfiguredRequirementSla && !deadlineDate) {
      setCreateError('Deadline date must be a valid calendar date.')
      return
    }
    if (deadlineDate && deadlineDate <= triggerDate) {
      setCreateError('Deadline date must be after the trigger date.')
      return
    }

    createSubmittingRef.current = true
    setCreateLoading(true)
    setCreateError('')
    try {
      if (usesConfiguredRequirementSla) {
        await slaApi.autoCreateSla(parseInt(createForm.project_requirement_id), {
          trigger_date: triggerDate.toISOString(),
        })
      } else {
        const payload = {
          project_id: parseInt(createForm.project_id),
          deadline_type: createForm.deadline_type,
          trigger_date: triggerDate.toISOString(),
          deadline_date: deadlineDate.toISOString(),
          sla_working_days: createForm.sla_working_days ? parseInt(createForm.sla_working_days) : null,
          notes: createForm.notes || undefined,
        }
        if (isRequirementTimer) {
          payload.project_requirement_id = parseInt(createForm.project_requirement_id)
        }
        await slaApi.createSlaDeadline(payload)
      }
      closeCreateModal()
      fetchDeadlines()
      fetchDashboard()
      toast.success('Compliance deadline recorded successfully.')
    } catch (err) {
      const data = err.response?.data
      setCreateError(data?.message || (data?.errors ? Object.values(data.errors).join(', ') : 'Unable to record the compliance deadline.'))
    } finally {
      createSubmittingRef.current = false
      setCreateLoading(false)
    }
  }

  const handleSearchSubmit = (event) => {
    event.preventDefault()
    const nextSearch = searchDraft.trim()
    setPage(1)
    setAppliedSearch(nextSearch)
    if (page === 1 && nextSearch === appliedSearch) {
      fetchDeadlines()
    }
  }

  const handleClearSearch = () => {
    setSearchDraft('')
    setPage(1)
    if (appliedSearch) {
      setAppliedSearch('')
    }
  }

  const hasDashboardError = Boolean(dashboardError && !dashboard)
  const total = hasDashboardError ? '—' : (dashboard?.total || 0)
  const active = hasDashboardError ? '—' : (dashboard?.active ?? dashboard?.unresolved ?? 0)
  const overdue = hasDashboardError ? '—' : (dashboard?.overdue || 0)
  const resolved = hasDashboardError ? '—' : (dashboard?.resolved || 0)

  const semanticsButton = (
    <div ref={semanticsRef} className="relative inline-flex items-center">
      <button
        type="button"
        onClick={() => setShowSemantics((open) => !open)}
        className="inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/35 transition-colors"
        aria-label="Compliance deadline & timer semantics info"
        aria-expanded={showSemantics}
        aria-haspopup="dialog"
      >
        <Info className="h-4 w-4" />
      </button>

      {showSemantics && (
        <div
          role="dialog"
          aria-labelledby="semantics-popover-title"
          className="absolute left-0 top-full z-40 mt-2 w-80 sm:w-96 rounded-lg border border-brand-border bg-brand-surface-solid p-4 shadow-xl ring-1 ring-slate-950/10"
        >
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-blue-600 dark:text-blue-400 shrink-0" />
              <h2 id="semantics-popover-title" className="text-sm font-semibold text-brand-text">
                Compliance Deadline &amp; Timer Semantics
              </h2>
            </div>
            <button
              type="button"
              onClick={() => setShowSemantics(false)}
              className="rounded p-1 text-brand-text-muted hover:bg-brand-surface hover:text-brand-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/35"
              aria-label="Close guidance"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="space-y-2 text-xs text-brand-text-muted leading-relaxed">
            <p>
              {branding.app_name} monitors procedural deadlines established through the applicable workflow. It does not create legal obligations.
            </p>
            <p>
              An overdue deadline does not automatically issue a notice or determine non-compliance. Internal tracking timers are operational reminders only.
            </p>
          </div>
        </div>
      )}
    </div>
  )

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Compliance Deadline Tracker"
        titleExtra={semanticsButton}
        description="Monitor requirement, project, and follow-up deadlines by working-day windows."
        actions={(isAdmin() || isStaff()) && (
          <Button icon={Plus} onClick={() => { resetCreateState(); setShowCreate(true) }}>Record Compliance Deadline</Button>
        )}
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4 mb-6">
        <KpiCard title="Deadlines" value={total} subtitle="tracked" icon={Clock} color="blue" />
        <KpiCard title="Active Deadlines" value={active} subtitle="in progress" icon={Timer} color="amber" />
        <KpiCard title="Overdue Deadlines" value={overdue} subtitle="past due" icon={AlertTriangle} color="red" />
        <KpiCard title="Closed Deadlines" value={resolved} subtitle="closed" icon={CheckCircle2} color="emerald" />
      </div>

      <div className="mb-4 grid grid-cols-1 items-end gap-3 rounded-lg border border-brand-border bg-brand-surface-solid p-4 sm:grid-cols-2 xl:grid-cols-4">
        <form
          onSubmit={handleSearchSubmit}
          className="flex min-w-0 flex-col gap-1.5 sm:col-span-2"
          role="search"
          aria-label="Search compliance deadlines"
        >
          <label htmlFor="deadline-search" className="text-xs font-medium text-brand-text">Search</label>
          <div className="flex gap-2">
          <div className="relative min-w-0 flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600 dark:text-slate-400" />
            <input
              id="deadline-search"
              type="text"
              className="input-field pl-10"
              placeholder="Search project, LGU, requirement, or notes..."
              value={searchDraft}
              onChange={(e) => setSearchDraft(e.target.value)}
              aria-label="Search compliance deadlines"
            />
          </div>
          <div className="flex gap-2">
            <Button type="submit" variant="outline" className="self-center">Search</Button>
            {(searchDraft || appliedSearch) && (
              <Button type="button" variant="ghost" onClick={handleClearSearch}>
                Clear
              </Button>
            )}
          </div>
          </div>
        </form>
        <label className="grid min-w-0 gap-1.5 text-xs font-medium text-brand-text"><span>Deadline type</span>
        <select
          id="sla-type"
          value={filterType}
          onChange={(e) => { setFilterType(e.target.value); setPage(1) }}
          className="input-field"
          aria-label="Filter by deadline type"
        >
          {TYPE_FILTERS.map((filter) => <option key={filter.value} value={filter.value}>{filter.label}</option>)}
        </select>
        </label>
        <label className="grid min-w-0 gap-1.5 text-xs font-medium text-brand-text"><span>Deadline status</span>
        <select
          id="sla-status"
          value={filterStatus}
          onChange={(e) => handleStatusChange(e.target.value)}
          className="input-field"
          aria-label="Filter by timer status"
        >
          {STATUS_FILTERS.map((filter) => <option key={filter.value} value={filter.value}>{filter.label}</option>)}
        </select>
        </label>
        <label className="grid min-w-0 gap-1.5 text-xs font-medium text-brand-text"><span>Scope</span>
        <select
          id="sla-scope"
          value={filterScope}
          onChange={(e) => { setFilterScope(e.target.value); setPage(1) }}
          className="input-field"
          aria-label="Filter by scope"
        >
          {SCOPE_FILTERS.map((filter) => <option key={filter.value} value={filter.value}>{filter.label}</option>)}
        </select>
        </label>
        <label className="grid min-w-0 gap-1.5 text-xs font-medium text-brand-text"><span>Requirement status</span>
        <select
          id="sla-requirement-status"
          value={filterRequirementStatus}
          onChange={(e) => { setFilterRequirementStatus(e.target.value); setPage(1) }}
          className="input-field"
          aria-label="Filter by requirement status"
        >
          {REQUIREMENT_STATUS_FILTERS.map((filter) => <option key={filter.value} value={filter.value}>{filter.label}</option>)}
        </select>
        </label>
        <label className="grid min-w-0 gap-1.5 text-xs font-medium text-brand-text"><span>Due window</span>
        <select
          id="sla-due-window"
          value={filterDueBucket}
          onChange={(e) => handleDueBucketChange(e.target.value)}
          className="input-field"
          aria-label="Filter by due window"
        >
          {DUE_FILTERS.map((filter) => <option key={filter.value} value={filter.value}>{filter.label}</option>)}
        </select>
        </label>
        <Button
          variant="outline"
          className={`${overdueOnly ? 'ring-2 ring-red-500/50' : ''}`}
          onClick={handleToggleOverdueOnly}
        >
          <AlertTriangle className="h-4 w-4 mr-1" />
          {overdueOnly ? 'Showing Overdue Only' : 'Show Overdue Only'}
        </Button>
      </div>

      {filterLguId && (
        <div className="mb-4 flex items-center gap-2" data-testid="active-lgu-filter">
          <span className="text-xs text-brand-text-muted">Active Filter:</span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-800 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-300">
            <span>{activeLguName ? `LGU: ${activeLguName}` : `LGU ID: ${filterLguId}`}</span>
            <button
              type="button"
              onClick={handleClearLguFilter}
              className="inline-flex h-4 w-4 items-center justify-center rounded-full hover:bg-blue-200 dark:hover:bg-blue-800/80 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500"
              aria-label="Clear LGU filter"
              title="Remove LGU filter"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        </div>
      )}

      {reportProjectStatus && <InlineAlert type="info" className="mb-4">Table scope from Reports: {reportProjectStatus.replaceAll('_', ' ')} projects. Dashboard totals retain the fiscal-year portfolio. <button type="button" className="underline" onClick={() => { setSearchParams(previous => { const next = new URLSearchParams(previous); next.delete('project_status'); return next }); setPage(1) }}>Clear report scope</button></InlineAlert>}
      {error && (
        <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>
          <div className="flex items-center justify-between gap-3">
            <span>{error}</span>
            <Button size="sm" variant="outline" onClick={() => { fetchDeadlines(); fetchDashboard() }}>
              Retry
            </Button>
          </div>
        </InlineAlert>
      )}

      <ComplianceDeadlinesTable
        deadlines={deadlines}
        loading={loading}
        emptyMessage={error ? 'Unable to load compliance deadlines. Please retry.' : 'No compliance deadlines found. Create one from a project requirement or project-level window.'}
        getMetrics={getDeadlineMetrics}
        formatDate={formatDate}
        canClose={isAdmin() || isStaff()}
        onDetails={setSelectedDetail}
        onCloseDeadline={(row) => { setResolving(row); setResolveNotes(''); setResolveError('') }}
      />

      {meta.pages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-4">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>Previous</Button>
          <span className="text-sm text-brand-text-muted">Page {meta.page || page} of {meta.pages}</span>
          <Button variant="outline" size="sm" disabled={page >= meta.pages} onClick={() => setPage((current) => current + 1)}>Next</Button>
        </div>
      )}

      <Modal
        open={!!resolving}
        title="Close Deadline"
        description={`Administratively close deadline #${resolving?.id}. Closing a deadline marks it closed in ${branding.app_name} monitoring and does not resolve or waive any underlying documentary deficiency.`}
        size="md"
        onClose={() => { setResolving(null); setResolveNotes(''); setResolveError('') }}
      >
        <InlineAlert type="error" className="mb-3" onDismiss={() => setResolveError('')}>
          {resolveError}
        </InlineAlert>
        <div className="space-y-4">
          <FormField id="resolve-notes" label="Closure Reason / Notes (optional)">
            <textarea
              id="resolve-notes"
              value={resolveNotes}
              onChange={(e) => setResolveNotes(e.target.value)}
              className="input-field"
              rows={3}
              placeholder="Describe the administrative reason for closing this deadline (e.g., submission received, superseded, or administratively closed)."
            />
          </FormField>
          <div className="flex gap-3 justify-end pt-2">
            <Button variant="outline" onClick={() => { setResolving(null); setResolveNotes(''); setResolveError('') }}>Cancel</Button>
            <Button onClick={handleResolve} loading={resolveLoading}>Close Deadline</Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showCreate}
        title="Record Compliance Deadline"
        description={`Record a procedural deadline that has already been established by the applicable process or official action. ${branding.app_name} calculates and monitors the deadline; it does not create the underlying legal or procedural obligation.`}
        size="lg"
        onClose={closeCreateModal}
      >
        <InlineAlert type="error" className="mb-3" onDismiss={() => setCreateError('')}>
          {createError}
        </InlineAlert>
        <form onSubmit={handleCreate} className="space-y-4">
          {/* Intent Selection */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-brand-text-muted mb-2">
              Deadline / Timer Intent
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setCreateForm((curr) => ({
                  ...curr,
                  timer_intent: 'compliance_deadline',
                  deadline_type: curr.deadline_type === 'custom_sla' ? 'standard_15day' : curr.deadline_type,
                }))}
                className={`rounded-lg border p-3 text-left transition-all ${
                  createForm.timer_intent === 'compliance_deadline'
                    ? 'border-brand-primary bg-brand-primary/10 ring-1 ring-brand-primary'
                    : 'border-brand-border bg-brand-surface hover:bg-slate-100 dark:hover:bg-slate-800'
                }`}
              >
                <div className="font-medium text-sm text-brand-text">Compliance Deadline</div>
                <div className="text-xs text-brand-text-muted mt-1">Formal procedural window based on applicable guidelines.</div>
              </button>
              <button
                type="button"
                onClick={() => setCreateForm((curr) => ({
                  ...curr,
                  timer_intent: 'internal_timer',
                  deadline_type: 'custom_sla',
                }))}
                className={`rounded-lg border p-3 text-left transition-all ${
                  createForm.timer_intent === 'internal_timer'
                    ? 'border-amber-500 bg-amber-500/10 ring-1 ring-amber-500'
                    : 'border-brand-border bg-brand-surface hover:bg-slate-100 dark:hover:bg-slate-800'
                }`}
              >
                <div className="font-medium text-sm text-brand-text">Internal Tracking Timer</div>
                <div className="text-xs text-brand-text-muted mt-1">Operational desk reminder for internal follow-up.</div>
              </button>
            </div>
          </div>

          {createForm.timer_intent === 'internal_timer' && (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-100">
              <strong>Internal Operational Reminder:</strong> For internal operational reminders only. This timer does not determine formal compliance, non-compliance, or escalation eligibility.
            </div>
          )}

          <FormField id="create-scope" label="Deadline Scope" required>
            <select
              id="create-scope"
              value={createForm.timer_scope}
              onChange={(e) => setCreateForm({ ...createForm, timer_scope: e.target.value, project_requirement_id: '' })}
              className="input-field"
            >
              <option value="requirement">Specific Requirement</option>
              <option value="project">Project-Level Deadline</option>
            </select>
          </FormField>

          <FormField id="project-search" label="Project" required hint="Search by project name, source code, LGU, or other indexed project text.">
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                id="project-search"
                type="text"
                value={projectSearch}
                onChange={(e) => handleProjectSearchChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleProjectSearch()
                  }
                }}
                className="input-field flex-1"
                placeholder="Search project..."
              />
              <Button type="button" variant="outline" icon={Search} loading={projectLoading} onClick={handleProjectSearch}>
                Search
              </Button>
            </div>
          </FormField>

          {projectOptions.length > 0 && (
            <div className="rounded-md border border-brand-border bg-brand-surface-solid">
              <div className="border-b border-brand-border px-3 py-2 text-xs font-semibold uppercase tracking-wide text-brand-text-muted">
                Project Results
              </div>
              <div className="max-h-56 overflow-y-auto p-1">
                {projectOptions.map((project) => {
                  const selected = String(createForm.project_id) === String(project.id)
                  return (
                    <button
                      key={project.id}
                      type="button"
                      onClick={() => handleProjectSelect(String(project.id))}
                      className={`w-full rounded-md px-3 py-2 text-left transition-colors ${
                        selected
                          ? 'bg-brand-primary/10 text-brand-primary'
                          : 'text-brand-text hover:bg-slate-100 dark:hover:bg-slate-800'
                      }`}
                    >
                      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                        <span className="font-medium">{project.project_name}</span>
                        <span className="text-xs text-brand-text-muted">FY {project.fiscal_year}</span>
                      </div>
                      <div className="mt-1 text-xs text-brand-text-muted">
                        Project #{project.id}
                        {project.source_project_code ? ` · ${project.source_project_code}` : ''}
                        {project.search_score ? ` · match ${project.search_score}` : ''}
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {projectSearchAttempted && !projectLoading && projectOptions.length === 0 && (
            <div className="rounded-md border border-brand-border bg-brand-surface px-3 py-2 text-sm text-brand-text-muted">
              No visible projects matched this search across fiscal years.
            </div>
          )}

          {selectedProject && (
            <div className="rounded-md border border-brand-border bg-brand-surface px-3 py-2 text-sm text-brand-text">
              <span className="font-medium">{selectedProject.project_name}</span>
              <span className="ml-2 text-brand-text-muted">FY {selectedProject.fiscal_year}</span>
            </div>
          )}

          {createForm.timer_scope === 'requirement' && createForm.project_id && (
            <FormField
              id="create-requirement"
              label="Requirement"
              required
              hint={requirementsLoading ? 'Loading requirements...' : 'Select the exact documentary requirement this deadline tracks.'}
            >
              <select
                id="create-requirement"
                value={createForm.project_requirement_id}
                onChange={(e) => handleRequirementSelect(e.target.value)}
                className="input-field"
                disabled={requirementsLoading}
              >
                <option value="">Select requirement...</option>
                {projectRequirements.map((requirement) => (
                  <option key={requirement.id} value={requirement.id}>
                    {requirement.requirement_name} - {formatStatusText(requirement.status)}
                    {requirement.has_sla && requirement.sla_days ? ` - ${requirement.sla_days} working days` : ''}
                  </option>
                ))}
              </select>
            </FormField>
          )}

          {usesConfiguredRequirementSla && (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-100">
              This requirement has a configured {selectedRequirement.sla_days}-working-day rule. {branding.app_name} will compute the deadline from the trigger date.
            </div>
          )}

          {!usesConfiguredRequirementSla && (
            createForm.timer_intent === 'internal_timer' ? (
              <FormField id="create-type" label="Deadline / Timer Type" required>
                <input
                  id="create-type"
                  type="text"
                  value="Internal Tracking Timer"
                  disabled
                  className="input-field bg-slate-50 text-slate-600 dark:text-slate-400 dark:bg-slate-800/50"
                />
              </FormField>
            ) : (
              <FormField id="create-type" label="Deadline Type" required>
                <select
                  id="create-type"
                  value={createForm.deadline_type}
                  onChange={(e) => setCreateForm({ ...createForm, deadline_type: e.target.value })}
                  className="input-field"
                >
                  <option value="standard_15day">15-Working-Day Notice Window</option>
                  <option value="rectification_period">Rectification Period</option>
                  <option value="notice_of_eligibility_5day">Notice of Eligibility (5 Working Days)</option>
                </select>
              </FormField>
            )
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField
              id="create-trigger"
              label="Trigger Date"
              required
              hint={usesConfiguredRequirementSla ? 'Usually the document intake, return-for-revision, or notice acknowledgment date.' : undefined}
            >
              <input
                id="create-trigger"
                type="date"
                value={createForm.trigger_date}
                onChange={(e) => setCreateForm({ ...createForm, trigger_date: e.target.value })}
                className="input-field"
                required
              />
            </FormField>
            {!usesConfiguredRequirementSla && (
              <FormField id="create-deadline" label="Deadline Date" required>
                <input
                  id="create-deadline"
                  type="date"
                  value={createForm.deadline_date}
                  onChange={(e) => setCreateForm({ ...createForm, deadline_date: e.target.value })}
                  className="input-field"
                  required
                />
              </FormField>
            )}
          </div>

          {!usesConfiguredRequirementSla && (
            <>
              <FormField id="create-working-days" label="Working Days">
                <input
                  id="create-working-days"
                  type="number"
                  value={createForm.sla_working_days}
                  onChange={(e) => setCreateForm({ ...createForm, sla_working_days: e.target.value })}
                  className="input-field"
                  min={1}
                  placeholder="e.g. 15"
                />
              </FormField>
              <FormField id="create-notes" label="Notes">
                <textarea
                  id="create-notes"
                  value={createForm.notes}
                  onChange={(e) => setCreateForm({ ...createForm, notes: e.target.value })}
                  className="input-field"
                  rows={3}
                  placeholder="Optional notes or administrative reference..."
                />
              </FormField>
            </>
          )}

          <div className="flex gap-3 justify-end pt-2">
            <Button variant="outline" type="button" onClick={closeCreateModal}>Cancel</Button>
            <Button type="submit" loading={createLoading}>Record Deadline</Button>
          </div>
        </form>
      </Modal>

      {/* Deadline Detail Modal */}
      <Modal
        open={!!selectedDetail}
        title="Deadline & Tracking Details"
        description={`Record details for deadline #${selectedDetail?.id}`}
        size="lg"
        onClose={() => setSelectedDetail(null)}
      >
        {selectedDetail && (
          <div className="space-y-4">
            <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-3 text-xs text-blue-900 dark:border-blue-500/30 dark:bg-blue-950/20 dark:text-blue-200">
              <strong>Administrative Record:</strong> {branding.app_name} monitors this deadline for internal administrative tracking. An overdue deadline does not constitute a formal finding of non-compliance without authorized review and issuance.
            </div>

            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              <div className="rounded-md border border-brand-border bg-brand-surface p-3">
                <dt className="text-xs font-semibold uppercase text-brand-text-muted">Deadline Type</dt>
                <dd className="mt-1 flex items-center gap-2">
                  <CategoryBadge category="deadline_type" value={selectedDetail.deadline_type} />
                </dd>
              </div>

              <div className="rounded-md border border-brand-border bg-brand-surface p-3">
                <dt className="text-xs font-semibold uppercase text-brand-text-muted">Current Status</dt>
                <dd className="mt-1">{statusBadge(selectedDetail)}</dd>
              </div>

              <div className="rounded-md border border-brand-border bg-brand-surface p-3">
                <dt className="text-xs font-semibold uppercase text-brand-text-muted">Project</dt>
                <dd className="mt-1 font-medium text-brand-text">
                  {selectedDetail.project_name || `Project #${selectedDetail.project_id}`}
                  <p className="text-xs text-brand-text-muted mt-0.5">{selectedDetail.lgu_name || 'LGU not set'}</p>
                </dd>
              </div>

              <div className="rounded-md border border-brand-border bg-brand-surface p-3">
                <dt className="text-xs font-semibold uppercase text-brand-text-muted">Tracked Item</dt>
                <dd className="mt-1 font-medium text-brand-text">
                  {selectedDetail.requirement_name || 'Project-Level Deadline'}
                  <p className="text-xs text-brand-text-muted mt-0.5">
                    {selectedDetail.requirement_phase_name ? `${selectedDetail.requirement_phase_name} · ` : ''}
                    {formatStatusText(selectedDetail.requirement_status)}
                  </p>
                </dd>
              </div>

              <div className="rounded-md border border-brand-border bg-brand-surface p-3">
                <dt className="text-xs font-semibold uppercase text-brand-text-muted">Trigger Date</dt>
                <dd className="mt-1 font-medium text-brand-text">{formatDate(selectedDetail.trigger_date)}</dd>
              </div>

              <div className="rounded-md border border-brand-border bg-brand-surface p-3">
                <dt className="text-xs font-semibold uppercase text-brand-text-muted">Deadline Date</dt>
                <dd className="mt-1 font-medium text-brand-text">
                  {formatDate(selectedDetail.deadline_date)}
                  <span className="ml-2 text-xs text-brand-text-muted">({selectedDetail.sla_working_days || '-'} working days)</span>
                </dd>
              </div>

              <div className="rounded-md border border-brand-border bg-brand-surface p-3">
                <dt className="text-xs font-semibold uppercase text-brand-text-muted">Working-Day Position</dt>
                <dd className="mt-1 font-medium text-brand-text">
                  {deadlinePosition(selectedDetail, getDeadlineMetrics(selectedDetail))}
                </dd>
              </div>

              <div className="rounded-md border border-brand-border bg-brand-surface p-3">
                <dt className="text-xs font-semibold uppercase text-brand-text-muted">Program & FY</dt>
                <dd className="mt-1 text-brand-text">
                  {selectedDetail.program_name || selectedDetail.program_code || '-'} (FY {selectedDetail.project_fiscal_year || '-'})
                </dd>
              </div>
            </dl>

            {selectedDetail.notes && (
              <div className="rounded-md border border-brand-border bg-brand-surface p-3">
                <p className="text-xs font-semibold uppercase text-brand-text-muted">Notes / Administrative Context</p>
                <p className="mt-1 text-sm text-brand-text whitespace-pre-wrap">{selectedDetail.notes}</p>
              </div>
            )}

            <div className="flex justify-end pt-2">
              <Button variant="outline" onClick={() => setSelectedDetail(null)}>Close</Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
