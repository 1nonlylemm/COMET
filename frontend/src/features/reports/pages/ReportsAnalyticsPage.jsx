import { createElement, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ClipboardList,
  CornerUpLeft,
  FileDown,
  FileText,
  Layers,
  RefreshCw,
  Search,
  ShieldCheck,
  X,
} from 'lucide-react'
import { Button, DataTable, EmptyState, GlassPanel, InlineAlert, KpiCard, PageHeader } from '../../../components'
import { formatCurrency, formatStatus } from '../../../lib/formatters'
import { PROJECT_STATUS_CONFIG } from '../../../lib/projectStatus'
import { badgeClassForTone } from '../../../lib/statusStyles'
import ExportPdfModal from '../components/ExportPdfModal'
import ProjectStatusPieChart from '../components/charts/ProjectStatusPieChart'
import ReturnPatternsChart from '../components/charts/ReturnPatternsChart'
import ReturnEventDetailModal from '../components/ReturnEventDetailModal'
import CloseoutReadinessChart from '../components/charts/CloseoutReadinessChart'
import CompareAnalyticsCard from '../components/charts/CompareAnalyticsCard'
import ReportsDrilldownDrawer from '../components/ReportsDrilldownDrawer'
import DocumentaryStatusBreakdown from '../components/charts/DocumentaryStatusBreakdown'
import * as reportsApi from '../api/reportsApi'

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'not_yet_started', label: 'Not Yet Started' },
  { value: 'ongoing', label: 'Ongoing' },
  { value: 'completed', label: 'Completed' },
  { value: 'cancelled', label: 'Cancelled' },
]

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })
}

function formatPercent(value) {
  if (value === 'Not rated') return 'Not rated'
  if (value === null || value === undefined) return 'Not reported'
  return `${Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })}%`
}

function toneBadge(tone, label) {
  return <span className={badgeClassForTone(tone)}>{label}</span>
}

function formatLabel(value) {
  return String(value || 'N/A')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function documentCount(row, key) {
  if (key === 'not_applicable') {
    return Number(row?.document_not_applicable_count ?? row?.documentary_summary?.[key] ?? 0)
  }
  if (key === 'open') {
    return Number(row?.document_open_count ?? row?.documentary_summary?.open ?? 0)
  }
  if (key === 'applicable') {
    return Number(row?.document_applicable_count ?? row?.documentary_summary?.applicable ?? 0)
  }
  return Number(row?.documentary_summary?.[key] || 0)
}

function matchesProjectMetadata(project, needle) {
  if (!needle) return true
  return [
    project.project_name,
    project.project_code,
    project.lgu_name,
    project.cluster_name,
    project.program_name,
    project.remarks,
    project.risk_reason_labels?.join(' '),
  ].some((val) => String(val || '').toLowerCase().includes(needle))
}

function ProgressBar({ items, total }) {
  const normalizedItems = useMemo(() => {
    if (!items) return []
    if (Array.isArray(items)) {
      return items
        .map((it) => ({
          key: it.key,
          label: it.label || formatLabel(it.key),
          count: Number(it.count || 0),
        }))
        .filter((it) => it.count > 0)
    }
    return Object.entries(items)
      .map(([key, count]) => ({
        key,
        label: formatLabel(key),
        count: Number(count || 0),
      }))
      .filter((it) => it.count > 0)
  }, [items])

  if (!total || normalizedItems.length === 0) {
    return <div className="h-2 rounded-full bg-slate-200 dark:bg-slate-700" />
  }

  return (
    <div className="flex h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700" role="img" aria-label="Status mix">
      {normalizedItems.map((item) => {
        const pct = (item.count / total) * 100
        return (
          <div
            key={item.key}
            className={PROJECT_STATUS_CONFIG[item.key]?.bgClass || 'bg-slate-500'}
            style={{ width: `${pct}%` }}
            title={`${item.label}: ${item.count}`}
          />
        )
      })}
    </div>
  )
}

function SectionHeader({ icon, title, count, description }) {
  return (
    <div className="mb-5 flex items-start justify-between gap-4">
      <div className="flex min-w-0 items-center gap-3">
        {icon && (
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-brand-primary/10">
            {createElement(icon, { className: 'h-4 w-4 text-brand-primary', strokeWidth: 1.8 })}
          </div>
        )}
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-brand-text">{title}</h2>
          {description && <p className="mt-0.5 text-xs text-brand-text-muted">{description}</p>}
        </div>
      </div>
      {count !== undefined && (
        <span className="shrink-0 rounded-full bg-brand-surface px-2.5 py-0.5 text-xs font-medium text-brand-text-muted ring-1 ring-brand-border">
          {formatNumber(count)}
        </span>
      )}
    </div>
  )
}

export function TruncatedText({ text, maxWidth = 'max-w-[16rem]', className = '' }) {
  if (!text) return <span className="text-brand-text-muted">—</span>
  return (
    <span className={`block truncate ${maxWidth} ${className}`} title={text}>
      {text}
    </span>
  )
}

export function ProgressCell({ value, suffix }) {
  if (value === null || value === undefined) return <span className="text-xs text-brand-text-muted">Not reported</span>
  const num = Number(value || 0)
  return (
    <div className="flex items-center gap-2 min-w-[5.5rem]">
      <div className="w-12 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden shrink-0">
        <div
          className="h-full bg-blue-500 rounded-full"
          style={{ width: `${Math.min(100, Math.max(0, num))}%` }}
        />
      </div>
      <span className="tabular-nums text-xs font-medium text-brand-text">
        {formatPercent(num)}{suffix ? ` ${suffix}` : ''}
      </span>
    </div>
  )
}

export function ComplianceBarCell({ value, applicableCount }) {
  const isNotRated = applicableCount === 0 || value === 'Not rated'
  if (isNotRated) {
    return (
      <div className="flex items-center gap-2 min-w-[5.5rem]">
        <span className="text-xs text-brand-text-muted">Not rated</span>
      </div>
    )
  }
  const rate = Number(value || 0)
  const barColor = rate >= 80 ? 'bg-emerald-500' : rate >= 50 ? 'bg-blue-500' : rate > 0 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2 min-w-[5.5rem]">
      <div className="w-12 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden shrink-0">
        <div
          className={`h-full rounded-full ${barColor}`}
          style={{ width: `${Math.min(100, Math.max(0, rate))}%` }}
        />
      </div>
      <span className="tabular-nums text-xs font-semibold text-brand-text">{formatPercent(rate)}</span>
    </div>
  )
}

export function ExpandableRemarks({ text }) {
  const [expanded, setExpanded] = useState(false)
  if (!text || text === '—') return <span className="text-brand-text-muted">—</span>

  const isLong = text.length > 45
  if (!isLong) {
    return <span className="text-xs text-brand-text-muted block truncate max-w-xs" title={text}>{text}</span>
  }

  return (
    <div className="max-w-xs text-xs text-brand-text-muted">
      {expanded ? (
        <div className="space-y-1 py-0.5">
          <p className="whitespace-normal leading-relaxed text-brand-text">{text}</p>
          <button
            type="button"
            onClick={() => setExpanded(false)}
            className="text-[11px] font-semibold text-brand-primary hover:underline"
          >
            Show less
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-1.5">
          <span className="truncate max-w-[13rem] block" title={text}>{text}</span>
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="shrink-0 text-[11px] font-semibold text-brand-primary hover:underline whitespace-nowrap"
          >
            Show more
          </button>
        </div>
      )}
    </div>
  )
}

export function FlagsCell({ reasons }) {
  const [expanded, setExpanded] = useState(false)
  if (!reasons?.length) return toneBadge('neutral', 'No flags')

  const dotColors = {
    danger: 'bg-red-500',
    warning: 'bg-amber-500',
    info: 'bg-blue-500',
    neutral: 'bg-slate-400',
  }

  if (expanded) {
    return (
      <div className="space-y-1.5 py-1">
        <div className="flex max-w-xs flex-wrap gap-1">
          {reasons.map((reason) => (
            <span key={reason.key} className={badgeClassForTone(reason.tone || 'neutral')}>
              {reason.label}
            </span>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="text-[11px] font-semibold text-brand-primary hover:underline"
        >
          Collapse flags
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-1.5">
      <div className="flex items-center gap-1">
        {reasons.map((reason, idx) => (
          <span
            key={reason.key || idx}
            className={`inline-block h-2 w-2 rounded-full shrink-0 ${dotColors[reason.tone] || dotColors.neutral}`}
            title={reason.label}
          />
        ))}
      </div>
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors whitespace-nowrap"
        title="Click to expand flags"
      >
        {reasons.length} {reasons.length === 1 ? 'flag' : 'flags'}
      </button>
    </div>
  )
}

export function OpenDocumentsCell({ row }) {
  const [showDetails, setShowDetails] = useState(false)
  const openCount = row.document_open_count ?? row.documentary_summary?.open ?? 0
  const pending = documentCount(row, 'pending')
  const review = documentCount(row, 'under_review')
  const nonCompliant = documentCount(row, 'non_compliant')

  const tooltipText = `Pending: ${pending}\nUnder Review: ${review}\nNon-Compliant: ${nonCompliant}`

  return (
    <div className="relative inline-block text-left">
      <div className="flex items-center gap-1.5">
        <span className="tabular-nums font-semibold text-brand-text" title={tooltipText}>
          {formatNumber(openCount)}
        </span>
        {openCount > 0 && (
          <button
            type="button"
            onClick={() => setShowDetails(!showDetails)}
            className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-slate-100 dark:bg-slate-800 text-brand-text-muted hover:text-brand-text hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
            title="Toggle status breakdown"
          >
            {showDetails ? 'Hide' : 'Breakdown'}
          </button>
        )}
      </div>
      {showDetails && (
        <div className="mt-1 flex flex-wrap gap-1 text-[10px] whitespace-nowrap">
          <span className="rounded bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 px-1 py-0.5 font-medium" title="Pending">
            {pending} pending
          </span>
          <span className="rounded bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 px-1 py-0.5 font-medium" title="Under Review">
            {review} review
          </span>
          <span className="rounded bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300 px-1 py-0.5 font-medium" title="Non-Compliant">
            {nonCompliant} non-compliant
          </span>
        </div>
      )}
    </div>
  )
}

export function RiskProjectCard({ project }) {
  if (!project) return null

  const healthScore = formatNumber(project.health_score)
  const healthLabel = project.health_label || 'N/A'
  const healthTone = project.health_tone || 'neutral'
  const lguName = project.lgu_name || 'Unassigned LGU'
  const clusterName = project.cluster_name || 'PGL / Unclustered'

  return (
    <div
      data-testid="risk-project-card"
      className="rounded-lg border border-brand-border bg-brand-surface p-4 transition-colors hover:border-brand-primary/30"
    >
      <div className="flex items-start gap-2.5">
        <span className={`shrink-0 ${badgeClassForTone(healthTone)}`}>
          {healthScore} · {healthLabel}
        </span>
        <h3 className="text-sm font-semibold text-brand-text leading-snug">
          {project.project_name}
        </h3>
      </div>

      <p className="mt-1 text-xs text-brand-text-muted">
        {lguName} · {clusterName}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
        <ProgressCell value={project.physical_completion_pct} suffix="progress" />
        <span className="text-brand-text-muted">
          <span className="font-semibold text-brand-text">{formatNumber(project.document_open_count || 0)}</span> open docs
        </span>
        <FlagsCell reasons={project.risk_reasons} />
      </div>

      <div className="mt-2.5">
        <ExpandableRemarks text={project.remarks} />
      </div>
    </div>
  )
}


export default function ReportsAnalyticsPage() {
  const [searchParams] = useSearchParams()
  const initialStatus = searchParams.get('status') || ''
  const [status, setStatus] = useState(initialStatus)
  const [searchDraft, setSearchDraft] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [report, setReport] = useState(null)
  const [deepDive, setDeepDive] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [isExportModalOpen, setIsExportModalOpen] = useState(false)
  const documentarySectionRef = useRef(null)

  // Unified Drawer State
  const [drawerState, setDrawerState] = useState({
    isOpen: false,
    title: '',
    subtitle: '',
    projects: [],
    returnFocusRef: null,
  })

  // Drill-Down States
  const [selectedProgram, setSelectedProgram] = useState(null)
  const [selectedComplianceStatus, setSelectedComplianceStatus] = useState(null)
  const [selectedWorkflowStage, setSelectedWorkflowStage] = useState(null)
  const [selectedReturnRequirement, setSelectedReturnRequirement] = useState(null)
  const [isReturnModalOpen, setIsReturnModalOpen] = useState(false)
  const [selectedCluster, setSelectedCluster] = useState(null)
  const [selectedLgu, setSelectedLgu] = useState(null)

  const latestRequest = useRef(0)
  const loadReport = useCallback(async () => {
    const requestId = ++latestRequest.current
    setLoading(true)
    setError('')
    try {
      const [monitoringRes, deepDiveRes] = await Promise.all([
        reportsApi.getMonitoringUpdatesReport({
          status: status || undefined,
        }),
        reportsApi.getDeepDiveAnalytics({
          status: status || undefined,
        }),
      ])
      if (requestId !== latestRequest.current) return
      setReport(monitoringRes.data || null)
      setDeepDive(deepDiveRes.data || null)
    } catch (err) {
      setReport(null)
      setDeepDive(null)
      setError(err.response?.data?.message || 'Reports and analytics could not be loaded.')
    } finally {
      setLoading(false)
    }
  }, [status])

  const handleReturnRequirementClick = (reqItem) => {
    setSelectedReturnRequirement(reqItem)
    setIsReturnModalOpen(true)
  }

  const handleCloseoutStageSelect = (stageKey, event) => {
    if (!stageKey) return
    const stageObj = cohortCloseoutReadiness?.stages?.find((s) => s.key === stageKey)
    const stageLabel = stageObj?.label || formatLabel(stageKey)
    const matching = filteredProjectRows.filter((p) => {
      const pid = p.project_id ?? p.id
      if (stageObj?.project_ids) {
        return stageObj.project_ids.includes(pid)
      }
      return p.closeout_stage === stageKey
    })
    const triggerEl = event?.currentTarget ? { current: event.currentTarget } : (typeof document !== 'undefined' ? document.activeElement : null)
    setDrawerState({
      isOpen: true,
      title: `Completion & Closeout: ${stageLabel}`,
      subtitle: `${matching.length} contributing ${matching.length === 1 ? 'project' : 'projects'}`,
      projects: matching,
      returnFocusRef: triggerEl,
    })
  }

  const handleClearAllDrillDowns = () => {
    setStatus('')
    setSelectedProgram(null)
    setSelectedComplianceStatus(null)
    setSelectedWorkflowStage(null)
    setSelectedReturnRequirement(null)
    setSelectedCluster(null)
    setSelectedLgu(null)
  }

  useEffect(() => {
    loadReport()
    return () => { latestRequest.current += 1 }
  }, [loadReport])

  useEffect(() => {
    const t = searchParams.get('tab')
    if (t === 'documents' && typeof documentarySectionRef.current?.scrollIntoView === 'function') {
      documentarySectionRef.current.scrollIntoView({ behavior: 'smooth' })
    }
    const s = searchParams.get('status') || ''
    setStatus(s)
  }, [searchParams])

  const analytics = report?.analytics_summary || {}
  const activeFilters = useMemo(() => ({
    fiscal_year: report?.scope?.fiscal_year || undefined,
    status: status || undefined,
    search: appliedSearch || undefined,
  }), [report?.scope?.fiscal_year, status, appliedSearch])

  const activeFilterSummary = useMemo(() => {
    const parts = []
    if (report?.scope?.fiscal_year) parts.push(`FY ${report.scope.fiscal_year}`)
    if (status) parts.push(`Status: ${formatStatus(status)}`)
    if (appliedSearch) parts.push(`Search: "${appliedSearch}"`)
    if (selectedProgram) parts.push(`Program: ${selectedProgram.name}`)
    if (selectedComplianceStatus) parts.push(`Compliance: ${formatLabel(selectedComplianceStatus)}`)
    if (selectedWorkflowStage) parts.push(`Workflow: ${formatLabel(selectedWorkflowStage)}`)
    if (selectedCluster) parts.push(`Cluster: ${selectedCluster.name}`)
    if (selectedLgu) parts.push(`LGU: ${selectedLgu.name}`)
    return parts.length > 0 ? parts.join(' · ') : 'All Project Records'
  }, [report?.scope?.fiscal_year, status, appliedSearch, selectedProgram, selectedComplianceStatus, selectedWorkflowStage, selectedCluster, selectedLgu])

  const projectRows = useMemo(() => report?.project_rows || [], [report])

  const selectProjectRows = useCallback((search = '') => {
    const needle = (search || '').trim().toLowerCase()
    let rows = projectRows
    if (needle) {
      const matchingReqProjectIds = new Set()
      const pipelineItems = deepDive?.workflow_pipeline?.items || []
      for (const item of pipelineItems) {
        if (item.requirement_name && item.requirement_name.toLowerCase().includes(needle)) {
          if (item.project_id) matchingReqProjectIds.add(item.project_id)
        }
      }
      const returnReqs = deepDive?.return_patterns?.requirements || []
      for (const req of returnReqs) {
        if (req.requirement_name && req.requirement_name.toLowerCase().includes(needle)) {
          for (const ev of (req.events || [])) {
            if (ev.project_id) matchingReqProjectIds.add(ev.project_id)
          }
        }
      }

      rows = rows.filter((r) => {
        const matchesProject = matchesProjectMetadata(r, needle)
        const matchesRequirement = Array.isArray(r.requirements) && r.requirements.some(
          req => String(req.requirement_name || req.name || '').toLowerCase().includes(needle)
        )
        return matchesProject || matchesRequirement || matchingReqProjectIds.has(r.project_id || r.id)
      })
    }
    if (status) {
      rows = rows.filter((r) => r.overall_status === status)
    }
    if (selectedProgram?.id) {
      rows = rows.filter((r) => r.program_id === selectedProgram.id)
    } else if (selectedProgram?.name) {
      rows = rows.filter((r) => r.program_name === selectedProgram.name)
    }
    if (selectedCluster) {
      rows = rows.filter((r) => (selectedCluster.id ? r.cluster_id === selectedCluster.id : r.cluster_name === selectedCluster.name))
    }
    if (selectedLgu) {
      rows = rows.filter((r) => (selectedLgu.id ? r.lgu_id === selectedLgu.id : r.lgu_name === selectedLgu.name))
    }
    return rows
  }, [projectRows, status, selectedProgram, selectedCluster, selectedLgu, deepDive?.workflow_pipeline?.items, deepDive?.return_patterns?.requirements])

  const hasCohortFilter = Boolean(
    appliedSearch || status || selectedProgram || selectedCluster || selectedLgu
  )

  const filteredProjectRows = useMemo(() => selectProjectRows(appliedSearch), [selectProjectRows, appliedSearch])
  const cohortProjectIds = useMemo(() => new Set(filteredProjectRows.map(row => row.project_id || row.id)), [filteredProjectRows])

  const projectMetadataMatchedIds = useMemo(() => {
    const needle = (appliedSearch || '').trim().toLowerCase()
    if (!needle) return new Set(filteredProjectRows.map(row => row.project_id || row.id))
    const ids = new Set()
    for (const r of filteredProjectRows) {
      if (matchesProjectMetadata(r, needle)) {
        ids.add(r.project_id || r.id)
      }
    }
    return ids
  }, [filteredProjectRows, appliedSearch])

  const isRequirementMatched = useCallback((item) => {
    if (!cohortProjectIds.has(item.project_id)) return false
    const needle = (appliedSearch || '').trim().toLowerCase()
    if (!needle) return true
    if (projectMetadataMatchedIds.has(item.project_id)) return true
    return Boolean(item.requirement_name && item.requirement_name.toLowerCase().includes(needle))
  }, [cohortProjectIds, projectMetadataMatchedIds, appliedSearch])

  const cohortStatusSummary = useMemo(() => {
    if (!hasCohortFilter && report?.status_summary) {
      return report.status_summary
    }

    const counts = {
      completed: 0,
      ongoing: 0,
      not_yet_started: 0,
      cancelled: 0,
    }
    for (const r of filteredProjectRows) {
      const s = r.overall_status
      if (s in counts) counts[s] += 1
    }
    const total = filteredProjectRows.length
    const percentages = {}
    for (const [s, count] of Object.entries(counts)) {
      percentages[s] = total > 0 ? Number(((count / total) * 100).toFixed(1)) : 0.0
    }
    const items = [
      { key: 'completed', label: 'Completed', count: counts.completed, percentage: percentages.completed, tone: 'success' },
      { key: 'ongoing', label: 'Ongoing', count: counts.ongoing, percentage: percentages.ongoing, tone: 'brand' },
      { key: 'not_yet_started', label: 'Not Yet Started', count: counts.not_yet_started, percentage: percentages.not_yet_started, tone: 'warning' },
      { key: 'cancelled', label: 'Cancelled', count: counts.cancelled, percentage: percentages.cancelled, tone: 'neutral' },
    ]
    return {
      total,
      counts,
      percentages,
      items,
    }
  }, [hasCohortFilter, report?.status_summary, filteredProjectRows])

  const cohortDocumentarySummary = useMemo(() => {
    if (!hasCohortFilter && report?.documentary_summary) {
      return report.documentary_summary
    }

    const summary = {
      total: 0,
      pending: 0,
      under_review: 0,
      non_compliant: 0,
      compliant: 0,
      waived: 0,
      not_applicable: 0,
      applicable: 0,
      open: 0,
    }
    for (const r of filteredProjectRows) {
      const ds = r.documentary_summary || {}
      summary.total += (ds.total ?? 0)
      summary.pending += (ds.pending ?? 0)
      summary.under_review += (ds.under_review ?? 0)
      summary.non_compliant += (ds.non_compliant ?? 0)
      summary.compliant += (ds.compliant ?? 0)
      summary.waived += (ds.waived ?? 0)
      summary.not_applicable += (ds.not_applicable ?? 0)
      summary.applicable += (ds.applicable ?? (ds.total != null && ds.not_applicable != null ? ds.total - ds.not_applicable : 0))
    }
    summary.open = summary.pending + summary.under_review + summary.non_compliant
    summary.compliance_rate = summary.applicable > 0 ? Number(((summary.compliant / summary.applicable) * 100).toFixed(1)) : 0.0
    return summary
  }, [hasCohortFilter, report?.documentary_summary, filteredProjectRows])

  const cohortTotalProjects = hasCohortFilter ? filteredProjectRows.length : (analytics.total_projects ?? filteredProjectRows.length)
  const cohortOpenDocuments = hasCohortFilter ? cohortDocumentarySummary.open : (analytics.open_document_count ?? cohortDocumentarySummary.open)
  const cohortComplianceRate = hasCohortFilter ? cohortDocumentarySummary.compliance_rate : analytics.document_compliance_rate
  const isComplianceNotRated = loading
    ? false
    : hasCohortFilter
      ? (cohortTotalProjects === 0 || cohortDocumentarySummary.applicable === 0)
      : (analytics.document_applicable_count === 0 || (report?.documentary_summary?.applicable !== undefined && report.documentary_summary.applicable === 0))

  const cohortComparativeAnalytics = useMemo(() => {
    const hasPrecomputed = Boolean(
      (report?.lgu_analytics && report.lgu_analytics.length > 0) ||
      (report?.cluster_analytics && report.cluster_analytics.length > 0) ||
      (report?.program_analytics && report.program_analytics.length > 0)
    )

    if (!hasCohortFilter && hasPrecomputed) {
      const reportClusters = report?.cluster_analytics || []
      const deepDiveClusters = deepDive?.cluster_performance || []
      const cMap = new Map()
      deepDiveClusters.filter(c => reportClusters.some(row => (row.cluster_id ?? row.cluster_name) === (c.cluster_id ?? c.cluster_name))).forEach((c) => {
        const key = c.cluster_id ?? c.cluster_name
        if (key !== undefined && key !== null) cMap.set(key, { ...c })
      })
      reportClusters.forEach((c) => {
        const key = c.cluster_id ?? c.cluster_name
        if (key !== undefined && key !== null) {
          const existing = cMap.get(key) || {}
          cMap.set(key, { ...existing, ...c })
        }
      })

      const reportLgus = report?.lgu_analytics || []
      const deepDiveLgus = deepDive?.lgu_backlog || []
      const lMap = new Map()
      deepDiveLgus.filter(l => reportLgus.some(row => (row.lgu_id ?? row.lgu_name) === (l.lgu_id ?? l.lgu_name))).forEach((l) => {
        const key = l.lgu_id ?? l.lgu_name
        if (key !== undefined && key !== null) lMap.set(key, { ...l })
      })
      reportLgus.forEach((l) => {
        const key = l.lgu_id ?? l.lgu_name
        if (key !== undefined && key !== null) {
          const existing = lMap.get(key) || {}
          lMap.set(key, { ...existing, ...l })
        }
      })

      return {
        programAnalytics: report?.program_analytics || [],
        clusterAnalytics: Array.from(cMap.values()),
        lguAnalytics: Array.from(lMap.values()),
      }
    }

    const progMap = new Map()
    const clustMap = new Map()
    const lguMap = new Map()

    const createGroup = (base) => ({
      ...base,
      project_count: 0,
      total_document_count: 0,
      applicable_document_count: 0,
      not_applicable_document_count: 0,
      open_document_count: 0,
      pending_document_count: 0,
      under_review_document_count: 0,
      non_compliant_document_count: 0,
      compliant_document_count: 0,
      waived_document_count: 0,
      _progress_total: 0,
      _progress_reported: 0,
    })

    const addRowToGroup = (grp, r) => {
      grp.project_count += 1
      const ds = r.documentary_summary || {}
      const total = ds.total ?? documentCount(r, 'total')
      const na = ds.not_applicable ?? documentCount(r, 'not_applicable')
      const app = ds.applicable ?? (total - na)
      const pending = ds.pending ?? documentCount(r, 'pending')
      const underReview = ds.under_review ?? documentCount(r, 'under_review')
      const nonCompliant = ds.non_compliant ?? documentCount(r, 'non_compliant')
      const compliant = ds.compliant ?? documentCount(r, 'compliant')
      const waived = ds.waived ?? documentCount(r, 'waived')
      const open = ds.open ?? (pending + underReview + nonCompliant)

      grp.total_document_count += total
      grp.applicable_document_count += app
      grp.not_applicable_document_count += na
      grp.open_document_count += open
      grp.pending_document_count += pending
      grp.under_review_document_count += underReview
      grp.non_compliant_document_count += nonCompliant
      grp.compliant_document_count += compliant
      grp.waived_document_count += waived

      if (r.physical_completion_pct != null) {
        grp._progress_total += Number(r.physical_completion_pct)
        grp._progress_reported += 1
      }
    }

    for (const r of filteredProjectRows) {
      // Program
      const pId = r.program_id ?? r.program_name
      if (pId !== undefined && pId !== null) {
        if (!progMap.has(pId)) {
          progMap.set(pId, createGroup({
            program_id: r.program_id,
            program_name: r.program_name,
            program_code: r.program_code,
            fiscal_year: r.fiscal_year,
          }))
        }
        addRowToGroup(progMap.get(pId), r)
      }

      // Cluster
      const cId = r.cluster_id ?? r.cluster_name ?? 'unclustered'
      if (!clustMap.has(cId)) {
        clustMap.set(cId, createGroup({
          cluster_id: r.cluster_id,
          cluster_name: r.cluster_name || 'Unclustered',
        }))
      }
      addRowToGroup(clustMap.get(cId), r)

      // LGU
      const lId = r.lgu_id ?? r.lgu_name ?? 'unassigned'
      if (!lguMap.has(lId)) {
        lguMap.set(lId, createGroup({
          lgu_id: r.lgu_id,
          lgu_name: r.lgu_name || 'Unassigned',
          municipality: r.municipality || r.lgu_name,
          cluster_id: r.cluster_id,
          cluster_name: r.cluster_name,
        }))
      }
      addRowToGroup(lguMap.get(lId), r)
    }

    const finalizeGroups = (m) => Array.from(m.values()).map(grp => {
      const avgProgress = grp._progress_reported > 0 ? Number((grp._progress_total / grp._progress_reported).toFixed(1)) : null
      const compRate = grp.applicable_document_count > 0
        ? Number(((grp.compliant_document_count / grp.applicable_document_count) * 100).toFixed(1))
        : 'Not rated'
      const { _progress_total, _progress_reported, ...rest } = grp
      return {
        ...rest,
        average_progress: avgProgress,
        document_compliance_rate: compRate,
        compliance_rate: compRate,
      }
    })

    return {
      programAnalytics: finalizeGroups(progMap),
      clusterAnalytics: finalizeGroups(clustMap),
      lguAnalytics: finalizeGroups(lguMap),
    }
  }, [hasCohortFilter, filteredProjectRows, report?.program_analytics, report?.cluster_analytics, report?.lgu_analytics, deepDive?.cluster_performance, deepDive?.lgu_backlog])

  const filteredProgramAnalytics = cohortComparativeAnalytics.programAnalytics
  const mergedClusterAnalytics = cohortComparativeAnalytics.clusterAnalytics
  const mergedLguAnalytics = cohortComparativeAnalytics.lguAnalytics

  const cohortCloseoutReadiness = useMemo(() => {
    if (!hasCohortFilter) {
      return deepDive?.closeout_readiness
    }
    const rawCloseout = deepDive?.closeout_readiness
    if (!rawCloseout) return null

    const cohortProjectIds = new Set(filteredProjectRows.map(r => r.project_id || r.id))
    const totalProjects = filteredProjectRows.length
    if (totalProjects === 0) {
      return {
        total_projects: 0,
        physically_complete_count: 0,
        punchlist_cleared_count: 0,
        docs_ready_count: 0,
        docs_pending_count: 0,
        vault_ready_count: 0,
        final_approved_count: 0,
        readiness_rate: 0.0,
        approval_rate: 0.0,
        stages: [],
        projects: [],
      }
    }

    const matchingProjects = (rawCloseout.projects || []).filter(p => cohortProjectIds.has(p.id || p.project_id))

    const stages = (rawCloseout.stages || []).map(st => {
      const filteredIds = (st.project_ids || []).filter(id => cohortProjectIds.has(id))
      return {
        ...st,
        count: filteredIds.length,
        project_ids: filteredIds,
      }
    })

    const physStage = stages.find(s => s.key === 'physically_complete')
    const totalPhys = physStage ? physStage.count : 0
    const docsReadyStage = stages.find(s => s.key === 'docs_ready')
    const docsReadyCount = docsReadyStage ? docsReadyStage.count : 0
    const docsPendingStage = stages.find(s => s.key === 'docs_pending')
    const docsPendingCount = docsPendingStage ? docsPendingStage.count : 0
    const finalApprovedStage = stages.find(s => s.key === 'final_approved')
    const finalApprovedCount = finalApprovedStage ? finalApprovedStage.count : 0
    const punchlistClearedStage = stages.find(s => s.key === 'punchlist_cleared')
    const punchlistClearedCount = punchlistClearedStage ? punchlistClearedStage.count : 0
    const vaultReadyStage = stages.find(s => s.key === 'vault_ready')
    const vaultReadyCount = vaultReadyStage ? vaultReadyStage.count : 0

    const finalizedStages = stages.map(st => {
      let pct = 0.0
      if (st.key === 'physically_complete') {
        pct = totalProjects > 0 ? Number(((st.count / totalProjects) * 100).toFixed(1)) : 0.0
      } else {
        pct = totalPhys > 0 ? Number(((st.count / totalPhys) * 100).toFixed(1)) : 0.0
      }
      return { ...st, percentage: pct }
    })

    const readinessRate = totalPhys > 0 ? Number(((docsReadyCount / totalPhys) * 100).toFixed(1)) : 0.0
    const approvalRate = totalPhys > 0 ? Number(((finalApprovedCount / totalPhys) * 100).toFixed(1)) : 0.0

    return {
      total_projects: totalProjects,
      physically_complete_count: totalPhys,
      docs_ready_count: docsReadyCount,
      docs_pending_count: docsPendingCount,
      final_approved_count: finalApprovedCount,
      punchlist_cleared_count: punchlistClearedCount,
      vault_ready_count: vaultReadyCount,
      readiness_rate: readinessRate,
      approval_rate: approvalRate,
      stages: finalizedStages,
      projects: matchingProjects,
    }
  }, [hasCohortFilter, deepDive?.closeout_readiness, filteredProjectRows])

  const cohortReturnPatterns = useMemo(() => {
    if (!hasCohortFilter) {
      return deepDive?.return_patterns
    }
    const rawPatterns = deepDive?.return_patterns
    if (!rawPatterns) return null

    const cohortProjectIds = new Set(filteredProjectRows.map(r => r.project_id || r.id))
    const totalProjects = filteredProjectRows.length
    if (totalProjects === 0) {
      return {
        total_return_events: 0,
        unique_requirements_returned: 0,
        affected_projects_total: 0,
        requirements: [],
      }
    }

    const reqList = []
    let totalReturnEvents = 0
    const allUniqueReqIds = new Set()
    const allAffectedProjectIds = new Set()

    for (const req of (rawPatterns.requirements || [])) {
      const filteredEvents = (req.events || []).filter(e => cohortProjectIds.has(e.project_id))
      if (filteredEvents.length > 0) {
        totalReturnEvents += filteredEvents.length
        filteredEvents.forEach(e => {
          if (e.project_requirement_id) allUniqueReqIds.add(e.project_requirement_id)
          if (e.project_id) allAffectedProjectIds.add(e.project_id)
        })
        const uniqueReqs = new Set(filteredEvents.map(e => e.project_requirement_id)).size
        const affectedProjs = new Set(filteredEvents.map(e => e.project_id)).size
        const affectedLgus = new Set(filteredEvents.map(e => e.lgu_name)).size
        reqList.push({
          ...req,
          return_count: filteredEvents.length,
          unique_requirements_count: uniqueReqs,
          affected_projects_count: affectedProjs,
          affected_lgus_count: affectedLgus,
          events: filteredEvents,
        })
      }
    }

    reqList.sort((a, b) => b.return_count - a.return_count || a.requirement_name.localeCompare(b.requirement_name))

    return {
      total_return_events: totalReturnEvents,
      unique_requirements_returned: allUniqueReqIds.size,
      affected_projects_total: allAffectedProjectIds.size,
      requirements: reqList,
    }
  }, [hasCohortFilter, deepDive?.return_patterns, filteredProjectRows])

  const workflowRequirementRows = useMemo(() => {
    const rawItems = deepDive?.workflow_pipeline?.items || []
    return rawItems.filter((req) => {
      if (!isRequirementMatched(req)) return false
      if (selectedWorkflowStage && req.workflow_status !== selectedWorkflowStage) {
        return false
      }
      if (selectedProgram?.id && req.program_id !== selectedProgram.id) {
        return false
      }
      if (selectedComplianceStatus) {
        if (selectedComplianceStatus === 'not_applicable') {
          if (req.applicability !== 'not_applicable') return false
        } else if (req.compliance_status !== selectedComplianceStatus) {
          return false
        }
      }
      return true
    })
  }, [deepDive?.workflow_pipeline?.items, selectedWorkflowStage, selectedProgram, selectedComplianceStatus, isRequirementMatched])

  const exportProjectIds = useMemo(() => {
    let ids = selectedWorkflowStage ? [...new Set(workflowRequirementRows.map(row => row.project_id))] : filteredProjectRows.map(row => row.project_id)
    if (selectedComplianceStatus) ids = ids.filter(id => projectRows.some(row => row.project_id === id && documentCount(row, selectedComplianceStatus) > 0))
    if (selectedWorkflowStage) ids = ids.filter(id => workflowRequirementRows.some(row => row.project_id === id))
    return ids
  }, [projectRows, filteredProjectRows, selectedComplianceStatus, selectedWorkflowStage, workflowRequirementRows])

  const programClusterRows = useMemo(() => {
    if (!hasCohortFilter && report?.program_years) {
      const rows = []
      ;(report.program_years || []).forEach((py) => {
        ;(py.clusters || []).forEach((c) => {
          const statusesMap = c.statuses || {}
          rows.push({
            id: `${py.program_id || py.program_name}-${py.fiscal_year}-${c.cluster_id || c.cluster_name}`,
            program_name: py.program_code || py.program_name || 'Program',
            fiscal_year: py.fiscal_year,
            cluster_name: c.cluster_name,
            total: c.total || 0,
            total_allocation: c.total_allocation,
            allocation_recorded_count: c.allocation_recorded_count ?? 0,
            allocation_missing_count: c.allocation_missing_count ?? 0,
            allocation_complete: c.allocation_complete ?? false,
            statuses: [
              { key: 'completed', label: 'Completed', count: statusesMap.completed || 0, tone: 'success' },
              { key: 'ongoing', label: 'Ongoing', count: statusesMap.ongoing || 0, tone: 'brand' },
              { key: 'not_yet_started', label: 'Not Started', count: statusesMap.not_yet_started || 0, tone: 'warning' },
              { key: 'cancelled', label: 'Cancelled', count: statusesMap.cancelled || 0, tone: 'neutral' },
            ],
          })
        })
      })
      return rows
    }

    const groupMap = new Map()
    for (const r of filteredProjectRows) {
      const pKey = r.program_code || r.program_name || 'Program'
      const fy = r.fiscal_year ?? report?.scope?.fiscal_year ?? 'All'
      const cKey = r.cluster_name || 'Unclustered'
      const id = `${pKey}-${fy}-${cKey}`

      if (!groupMap.has(id)) {
        groupMap.set(id, {
          id,
          program_name: pKey,
          fiscal_year: fy,
          cluster_name: cKey,
          total: 0,
          total_allocation: 0.0,
          allocation_recorded_count: 0,
          allocation_missing_count: 0,
          statusesMap: { completed: 0, ongoing: 0, not_yet_started: 0, cancelled: 0 },
        })
      }
      const item = groupMap.get(id)
      item.total += 1
      if (r.overall_status in item.statusesMap) {
        item.statusesMap[r.overall_status] += 1
      }
      const alloc = r.budget_amount ?? r.total_allocation ?? r.allocation_amount
      if (alloc != null) {
        item.total_allocation += Number(alloc)
        item.allocation_recorded_count += 1
      } else {
        item.allocation_missing_count += 1
      }
    }

    return Array.from(groupMap.values()).map(item => ({
      id: item.id,
      program_name: item.program_name,
      fiscal_year: item.fiscal_year,
      cluster_name: item.cluster_name,
      total: item.total,
      total_allocation: item.allocation_recorded_count > 0 ? item.total_allocation : null,
      allocation_recorded_count: item.allocation_recorded_count,
      allocation_missing_count: item.allocation_missing_count,
      allocation_complete: item.allocation_missing_count === 0 && item.total > 0,
      statuses: [
        { key: 'completed', label: 'Completed', count: item.statusesMap.completed || 0, tone: 'success' },
        { key: 'ongoing', label: 'Ongoing', count: item.statusesMap.ongoing || 0, tone: 'brand' },
        { key: 'not_yet_started', label: 'Not Started', count: item.statusesMap.not_yet_started || 0, tone: 'warning' },
        { key: 'cancelled', label: 'Cancelled', count: item.statusesMap.cancelled || 0, tone: 'neutral' },
      ],
    }))
  }, [hasCohortFilter, report?.program_years, filteredProjectRows, report?.scope?.fiscal_year])

  const filteredProgramClusterRows = programClusterRows

  const programClusterColumns = [
    {
      key: 'program_name',
      label: 'Program',
      render: (row) => <TruncatedText text={row.program_name} maxWidth="max-w-[14rem]" className="font-semibold text-brand-text" />,
    },
    {
      key: 'cluster_name',
      label: 'Cluster / Grouping',
      render: (row) => <TruncatedText text={row.cluster_name} maxWidth="max-w-[12rem]" className="text-brand-text" />,
    },
    { key: 'fiscal_year', label: 'FY' },
    { key: 'total', label: 'Projects', render: (row) => formatNumber(row.total) },
    {
      key: 'allocation',
      label: 'Allocation',
      render: (row) => {
        if (row.allocation_recorded_count > 0 && row.total_allocation != null) {
          const formatted = formatCurrency(row.total_allocation)
          if (row.allocation_missing_count > 0) {
            return (
              <span title={`${row.allocation_recorded_count} recorded, ${row.allocation_missing_count} unrecorded`}>
                {formatted} <span className="text-xs text-brand-text-muted">({row.allocation_recorded_count}/{row.total})</span>
              </span>
            )
          }
          return formatted
        }
        return <span className="text-xs text-brand-text-muted italic">Not recorded</span>
      },
    },
    {
      key: 'status_mix',
      label: 'Status Mix',
      render: (row) => (
        <div className="min-w-36 max-w-xs">
          <ProgressBar items={row.statuses} total={row.total} />
        </div>
      ),
    },
  ]

  const handleProgramClusterRowClick = (row, event) => {
    const isUnclustered = !row.cluster_name || row.cluster_name === 'Unclustered' || row.cluster_name === 'None'
    const matching = filteredProjectRows.filter((p) => {
      const matchProg = p.program_name === row.program_name || p.program_code === row.program_name
      const projectFy = p.fiscal_year ?? report?.scope?.fiscal_year
      const matchFy = !row.fiscal_year || row.fiscal_year === 'All' || !projectFy || String(projectFy) === String(row.fiscal_year)
      const matchClust = isUnclustered
        ? (!p.cluster_name || p.cluster_name === 'Unclustered' || p.cluster_name === 'None')
        : (p.cluster_name === row.cluster_name)
      return matchProg && matchFy && matchClust
    })
    setDrawerState({
      isOpen: true,
      title: `Program & Cluster: ${row.program_name}`,
      subtitle: `${row.cluster_name || 'Unclustered'}${row.fiscal_year && row.fiscal_year !== 'All' ? ` • FY ${row.fiscal_year}` : ''} • ${matching.length} ${matching.length === 1 ? 'project' : 'projects'}`,
      projects: matching,
      returnFocusRef: event?.currentTarget ? { current: event.currentTarget } : (typeof document !== 'undefined' ? document.activeElement : null),
    })
  }

  const handleLguDrilldown = (lgu, event) => {
    const lguName = lgu.lgu_name || lgu.name
    const lguProjects = filteredProjectRows.filter(
      (p) => p.lgu_name === lguName || (lgu.lgu_id && p.lgu_id === lgu.lgu_id)
    )
    setDrawerState({
      isOpen: true,
      title: `LGU: ${lguName}`,
      subtitle: `${lguProjects.length} contributing ${lguProjects.length === 1 ? 'project' : 'projects'}`,
      projects: lguProjects,
      returnFocusRef: event?.currentTarget ? { current: event.currentTarget } : (typeof document !== 'undefined' ? document.activeElement : null),
    })
  }

  const handleProgramDrilldown = (program, event) => {
    const pName = program.program_name || program.name
    const pId = program.program_id || program.id
    const progProjects = filteredProjectRows.filter(
      (p) => p.program_name === pName || p.program_id === pId || p.program_code === pName
    )
    setDrawerState({
      isOpen: true,
      title: `Program: ${pName}`,
      subtitle: `${progProjects.length} contributing ${progProjects.length === 1 ? 'project' : 'projects'}`,
      projects: progProjects,
      returnFocusRef: event?.currentTarget ? { current: event.currentTarget } : (typeof document !== 'undefined' ? document.activeElement : null),
    })
  }

  const handleClusterDrilldown = (cluster, event) => {
    const cName = cluster.cluster_name || cluster.name
    const cId = cluster.cluster_id || cluster.id
    const isUnclustered = !cName || cName === 'Unclustered' || cName === 'None'
    const clusterProjects = filteredProjectRows.filter((p) => {
      if (isUnclustered) {
        return !p.cluster_name || p.cluster_name === 'Unclustered' || p.cluster_name === 'None'
      }
      return p.cluster_name === cName || (cId && p.cluster_id === cId)
    })
    setDrawerState({
      isOpen: true,
      title: `Cluster: ${cName || 'Unclustered'}`,
      subtitle: `${clusterProjects.length} contributing ${clusterProjects.length === 1 ? 'project' : 'projects'}`,
      projects: clusterProjects,
      returnFocusRef: event?.currentTarget ? { current: event.currentTarget } : (typeof document !== 'undefined' ? document.activeElement : null),
    })
  }

  const handleCloseDrawer = () => {
    setDrawerState((prev) => ({
      ...prev,
      isOpen: false,
    }))
  }

  const handleSearchSubmit = (event) => {
    event.preventDefault()
    setAppliedSearch(searchDraft.trim())
  }

  const handleClearSearch = () => {
    setSearchDraft('')
    setAppliedSearch('')
  }

  const hasActiveSearch = searchDraft || appliedSearch

  return (
    <div className="page-container">
      <PageHeader
        eyebrow="Reports & Analytics"
        title="Reports & Analytics"
        description="Project monitoring and documentary requirements compliance tracking across DILG Laguna PDMU programs."
        actions={(
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" icon={FileDown} onClick={() => setIsExportModalOpen(true)}>
              Export PDF
            </Button>
            <Button variant="outline" icon={RefreshCw} onClick={loadReport} loading={loading}>
              Refresh
            </Button>
          </div>
        )}
        meta={(
          <>
            <span className="status-badge status-badge-info">FY {report?.scope?.fiscal_year || 'Active'}</span>
            <span className="status-badge status-badge-neutral">{report?.scope?.unrestricted ? 'Province-wide' : 'Scoped view'}</span>
          </>
        )}
      />

      <p className="mb-4 text-xs text-brand-text-muted">All figures on this page follow your current filters. Export PDF lets you choose the full portfolio or just the current selection.</p>
      {error && <InlineAlert type="error" title="Unable to load report" className="mb-4">{error}</InlineAlert>}

      {/* KPI Row */}
      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <KpiCard
          title="Projects in scope"
          value={loading ? '—' : formatNumber(cohortTotalProjects)}
          subtitle="visible records"
          icon={ClipboardList}
          color="blue"
        />
        <KpiCard
          title="Open requirements"
          value={loading ? '—' : formatNumber(cohortOpenDocuments)}
          subtitle="pending, under review or non-compliant"
          icon={FileText}
          color="red"
        />
        <KpiCard
          title="Requirement fulfillment rate"
          value={
            loading
              ? '—'
              : isComplianceNotRated
                ? 'Not rated'
                : formatPercent(cohortComplianceRate)
          }
          subtitle="Compliant / applicable requirements"
          icon={ShieldCheck}
          color="amber"
        />
      </div>

      {/* Filters bar */}
      <div className="mb-5 rounded-xl border border-brand-border bg-brand-surface-solid p-4 shadow-sm dark:bg-brand-surface">
        {/* Search + Status filter */}
        <div className="grid gap-3 sm:grid-cols-[1fr_auto] xl:grid-cols-[1fr_14rem]">
          <form onSubmit={handleSearchSubmit} className="flex gap-2" role="search" aria-label="Search report rows">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-brand-text-muted" strokeWidth={1.5} />
              <input
                id="reports-row-search"
                type="search"
                className="input-field w-full pl-9 pr-9"
                value={searchDraft}
                onChange={(event) => setSearchDraft(event.target.value)}
                placeholder="Search projects, LGUs, clusters…"
                aria-label="Search"
              />
              {hasActiveSearch && (
                <button
                  type="button"
                  onClick={handleClearSearch}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-brand-text-muted hover:text-brand-text"
                  aria-label="Clear search"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            <Button variant="outline" type="submit" className="shrink-0">Search</Button>
          </form>

          <select
            id="reports-status-filter"
            className="input-field"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            aria-label="Filter by implementation status"
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Active Drill-down Filter Chips Banner */}
      {(status || selectedProgram || selectedComplianceStatus || selectedWorkflowStage || selectedCluster || selectedLgu) && (
        <div className="mb-5 flex flex-wrap items-center gap-2 rounded-xl border border-brand-primary/30 bg-brand-primary/5 p-3 text-xs">
          <span className="font-semibold text-brand-primary">Active Drill-Down Filter:</span>
          {status && (
            <span className="inline-flex items-center gap-1 rounded-full bg-brand-surface px-2.5 py-1 font-medium text-brand-text ring-1 ring-brand-border shadow-xs">
              Status: <strong>{PROJECT_STATUS_CONFIG[status]?.label || formatStatus(status)}</strong>
              <button
                type="button"
                onClick={() => setStatus('')}
                className="ml-1 text-brand-text-muted hover:text-brand-text"
                aria-label="Remove status filter"
                title="Remove status filter"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          )}
          {selectedProgram && (
            <span className="inline-flex items-center gap-1 rounded-full bg-brand-surface px-2.5 py-1 font-medium text-brand-text ring-1 ring-brand-border shadow-xs">
              Program: <strong>{selectedProgram.name}</strong>
              <button
                type="button"
                onClick={() => setSelectedProgram(null)}
                className="ml-1 text-brand-text-muted hover:text-brand-text"
                aria-label="Remove program filter"
                title="Remove program filter"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          )}
          {selectedComplianceStatus && (
            <span className="inline-flex items-center gap-1 rounded-full bg-brand-surface px-2.5 py-1 font-medium text-brand-text ring-1 ring-brand-border shadow-xs">
              Compliance Status: <strong>{formatLabel(selectedComplianceStatus)}</strong>
              <button
                type="button"
                onClick={() => setSelectedComplianceStatus(null)}
                className="ml-1 text-brand-text-muted hover:text-brand-text"
                aria-label="Remove compliance status filter"
                title="Remove compliance status filter"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          )}
          {selectedWorkflowStage && (
            <span className="inline-flex items-center gap-1 rounded-full bg-brand-surface px-2.5 py-1 font-medium text-brand-text ring-1 ring-brand-border shadow-xs">
              Workflow Stage: <strong>{formatLabel(selectedWorkflowStage)}</strong>
              <button
                type="button"
                onClick={() => setSelectedWorkflowStage(null)}
                className="ml-1 text-brand-text-muted hover:text-brand-text"
                aria-label="Remove workflow stage filter"
                title="Remove workflow stage filter"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          )}
          {selectedCluster && (
            <span className="inline-flex items-center gap-1 rounded-full bg-brand-surface px-2.5 py-1 font-medium text-brand-text ring-1 ring-brand-border shadow-xs">
              Cluster: <strong>{selectedCluster.name}</strong>
              <button
                type="button"
                onClick={() => setSelectedCluster(null)}
                className="ml-1 text-brand-text-muted hover:text-brand-text"
                aria-label="Remove cluster filter"
                title="Remove cluster filter"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          )}
          {selectedLgu && (
            <span className="inline-flex items-center gap-1 rounded-full bg-brand-surface px-2.5 py-1 font-medium text-brand-text ring-1 ring-brand-border shadow-xs">
              LGU: <strong>{selectedLgu.name}</strong>
              <button
                type="button"
                onClick={() => setSelectedLgu(null)}
                className="ml-1 text-brand-text-muted hover:text-brand-text"
                aria-label="Remove LGU filter"
                title="Remove LGU filter"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          )}
          <span className="ml-auto font-semibold text-brand-primary mr-2" data-testid="matching-projects-count">
            Matching Projects: <strong className="tabular-nums">{exportProjectIds.length}</strong>
          </span>
          <button
            type="button"
            onClick={handleClearAllDrillDowns}
            className="text-xs font-semibold text-brand-primary hover:underline"
          >
            Clear all drill-downs
          </button>
        </div>
      )}

      <div className="flex flex-col gap-6">
      {/* ── SECTION 1: PROJECT IMPLEMENTATION STATUS DISTRIBUTION ── */}
      <GlassPanel>
        <SectionHeader
          icon={Activity}
          title="Project Implementation Status Distribution"
          description="Projects by implementation status. Select a status to filter everything on this page."
        />
        <ProjectStatusPieChart
          statusData={cohortStatusSummary}
          selectedStatus={status}
          onStatusClick={setStatus}
        />
      </GlassPanel>

      {/* ── SECTION 2: PROGRAM & CLUSTER SUMMARY ── */}
      <GlassPanel>
        <SectionHeader
          icon={BarChart3}
          title="Program & Cluster Summary"
          count={filteredProgramClusterRows.length}
          description="Implementation status and allocation breakdown by program, fiscal year, and cluster — click a row to view contributing projects"
        />
        <DataTable
          data={filteredProgramClusterRows}
          columns={programClusterColumns}
          getRowId={(row) => row.id}
          isLoading={loading}
          emptyMessage="No program & cluster summaries found."
          density="compact"
          onRowClick={handleProgramClusterRowClick}
        />
      </GlassPanel>

      {/* ── SECTION 3: COMPLETION DOCUMENTS & CLOSEOUT ── */}
      {cohortCloseoutReadiness && (
        <GlassPanel>
          <SectionHeader
            icon={CheckCircle2}
            title="Completion Documents & Closeout"
            count={cohortCloseoutReadiness?.physically_complete_count}
            description="Internal completion matrix deliverables (Final SWA, Final Inspection Report / IAR, Certificate of Final Acceptance, Final SORD, Proof of Fund Return where applicable) for 100% physically completed projects — click a stage to view projects"
          />
          <CloseoutReadinessChart
            closeoutData={cohortCloseoutReadiness}
            onStageSelect={handleCloseoutStageSelect}
            clientScopeOnly={true}
          />
        </GlassPanel>
      )}

      {/* ── SECTION 4: DOCUMENTARY COMPLIANCE BY LGU ── */}
      <div ref={documentarySectionRef} className="flex flex-col gap-6">
        <GlassPanel>
          <SectionHeader
            icon={FileText}
            title="Documentary Compliance"
            count={cohortDocumentarySummary?.total}
            description="Document status breakdown across all visible projects"
          />
          <DocumentaryStatusBreakdown summary={cohortDocumentarySummary || {}} />
        </GlassPanel>

        <GlassPanel>
          <SectionHeader
            icon={BarChart3}
            title="Documentary Compliance by LGU"
            count={mergedLguAnalytics.length}
            description="Comparative documentary compliance analysis across LGUs, programs, and clusters — click an entity to view contributing projects"
          />
          <CompareAnalyticsCard
            programData={hasCohortFilter ? filteredProgramAnalytics : (filteredProgramAnalytics.length ? filteredProgramAnalytics : (deepDive?.compliance_by_program || []))}
            clusterData={mergedClusterAnalytics}
            lguData={mergedLguAnalytics}
            selectedProgram={selectedProgram}
            selectedCluster={selectedCluster}
            selectedLgu={selectedLgu}
            selectedComplianceStatus={selectedComplianceStatus}
            onProgramClick={handleProgramDrilldown}
            onClusterClick={handleClusterDrilldown}
            onLguClick={handleLguDrilldown}
            onSegmentClick={(row, statusKey, view) => {
              if (view === 'program') {
                handleProgramDrilldown(row)
              } else if (view === 'cluster') {
                handleClusterDrilldown(row)
              } else if (view === 'lgu') {
                handleLguDrilldown(row)
              }
            }}
          />
        </GlassPanel>
      </div>

      {/* ── COLLAPSIBLE SECONDARY: REVIEW AND RETURN HISTORY ── */}
      <GlassPanel>
        <details className="group">
          <summary className="flex cursor-pointer items-center justify-between text-sm font-semibold text-brand-text list-none [&::-webkit-details-marker]:hidden">
            <div className="flex items-center gap-2">
              <CornerUpLeft className="h-4 w-4 text-brand-primary" />
              <span>Review and Return History</span>
              {cohortReturnPatterns?.total_return_events > 0 && (
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                  {cohortReturnPatterns.total_return_events} return events
                </span>
              )}
            </div>
            <span className="text-xs text-brand-text-muted group-open:rotate-180 transition-transform duration-200">
              ▼
            </span>
          </summary>
          <div className="mt-4 pt-4 border-t border-brand-border space-y-3">
            <p className="text-xs text-brand-text-muted">
              Return events represent documents returned for revision during provincial desk review, field inspection, or technical validation. Return volume highlights recurring documentation bottlenecks and does not indicate fraud or project failure.
            </p>
            <ReturnPatternsChart
              returnPatternsData={cohortReturnPatterns}
              onRequirementClick={handleReturnRequirementClick}
            />
          </div>
        </details>
      </GlassPanel>

      </div>

      <ReportsDrilldownDrawer
        isOpen={drawerState.isOpen}
        onClose={handleCloseDrawer}
        title={drawerState.title}
        subtitle={drawerState.subtitle}
        projects={drawerState.projects}
        returnFocusRef={drawerState.returnFocusRef}
      />

      <ExportPdfModal
        isOpen={isExportModalOpen}
        onClose={() => setIsExportModalOpen(false)}
        activeFilters={activeFilters}
        selectedProjectIds={exportProjectIds}
        activeFilterSummary={activeFilterSummary}
      />

      <ReturnEventDetailModal
        requirementData={selectedReturnRequirement}
        open={isReturnModalOpen}
        onClose={() => setIsReturnModalOpen(false)}
      />
    </div>
  )
}
