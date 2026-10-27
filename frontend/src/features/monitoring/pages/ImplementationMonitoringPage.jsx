import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  AlertTriangle,
  Calculator,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  ClipboardList,
  FileDown,
  FileText,
  Flag,
  HardHat,
  Hash,
  History,
  ListChecks,
  MapPinned,
  Package,
  Plus,
  RefreshCw,
  Save,
  Search,
  ScrollText,
  Send,
  Sparkles,
  Trash2,
  Workflow,
} from 'lucide-react'
import { AmountInput, Button, DataTable, FeedbackToast, FormField, GlassPanel, InlineAlert, KpiCard, Modal, PageHeader } from '../../../components'
import { isInternalUser } from '../../../lib/auth'
import { formatMachineLabel, formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import * as monitoringApi from '../api/monitoringApi'
import * as projectApi from '../../projects/api/projectApi'
import { BeneficiaryEvidencePanel } from '../components/BeneficiaryEvidencePanel'
import { Form3Panel } from '../components/Form3Panel'
import { ManagementActionPanel } from '../components/ManagementActionPanel'
import { MonthlyProgressPanel } from '../components/MonthlyProgressPanel'
import { NonInfraMonitoringPanel } from '../components/NonInfraMonitoringPanel'
import { ProjectExceptionPanel } from '../components/ProjectExceptionPanel'
import { WorkflowQueuePanel } from '../components/WorkflowQueuePanel'

const EMPTY_FORM = {
  project_id: '',
  inspection_date: new Date().toISOString().slice(0, 10),
  monitoring_type: 'qaar',
  physical_accomplishment_pct: '',
  observation_summary: '',
  findings: '',
  recommendations: '',
  agreement_summary: '',
  issues_identified: '',
  is_site_visit: true,
  aide_memoire_text: '',
  annex_d_reference: '',
  transmittal_status: 'not_required',
  transmittal_reference: '',
  transmitted_at: '',
  monthly_cycle_tag: '',
  monthly_cycle_note: '',
  project_kind: '',
  monitoring_applicability: '',
  qaar_category: '',
  subaybayan_project_code: '',
  subaybayan_url: '',
  nadai_received_at: '',
  subaybayan_enrolled_at: '',
  subaybayan_enrollment_status: '',
  qaar_report_summary: {},
  qaar_project_management_checks: [],
  qaar_work_items: [],
  qaar_work_findings: [],
  qaar_health_safety_checks: [],
  subaybayan_verification: {
    cycle_month: '',
    lgu_encoded_status: 'not_checked',
    ro_action_status: 'pending',
    status: 'open',
    discrepancy_notes: '',
    observations: '',
  },
  management_action: {
    risk_level: '',
    trigger_summary: '',
    action_required: '',
    responsible_office: '',
    due_date: '',
    status: 'draft',
  },
  status: 'draft',
}

const TRANSMITTAL_STATUSES = [
  { value: 'not_required', label: 'Not required' },
  { value: 'pending', label: 'Pending transmittal' },
  { value: 'transmitted', label: 'Transmitted' },
  { value: 'acknowledged', label: 'Acknowledged' },
]

const QAAR_PROJECT_STATUSES = [
  { value: '', label: 'Blank' },
  { value: 'ON-GOING', label: 'ON-GOING' },
  { value: 'SUSPENDED', label: 'SUSPENDED' },
  { value: 'COMPLETED', label: 'COMPLETED' },
  { value: 'CANCELLED', label: 'CANCELLED' },
]

const QAAR_DEFAULT_REGION = 'CALABARZON'
const QAAR_DEFAULT_PROVINCE = 'LAGUNA'

const QAAR_OUTPUT_LABELS = {
  full_package: 'QAAR Package',
  report_summary: 'Report Summary',
  project_management: 'Project Management',
  quality_of_works: 'Quality of Works',
  health_and_safety: 'Health and Safety',
  findings_recommendations: 'Findings',
  aide_memoire: 'Aide Memoire',
  notice_of_defects: 'Notice',
}

function emptyWorkItem() {
  return {
    item_code: '',
    description: '',
    quantity: '',
    inspected_quantity: '',
    unit: '',
    unit_cost: '',
    location: '',
    source_catalog_row: '',
  }
}

function emptyFinding() {
  return {
    work_item_index: '',
    defect_code: '',
    defect_description: '',
    quality_issue: '',
    recommendation: '',
    location: '',
    degree_of_defect: '',
    rating_weight: '',
    timeline: '',
    remarks: '',
    risk_level: '',
    source_catalog_row: '',
  }
}

function buildDefaultChecks(catalog, key) {
  return (catalog?.[key] || []).map((item) => ({
    ...item,
    check_key: item.check_key,
    section: item.section,
    label: item.label,
    response: '',
    remarks: '',
    form_data: {},
    sort_order: item.sort_order,
  }))
}

function buildQaarState(catalog, packageData = {}) {
  const workItems = packageData.work_items?.length ? packageData.work_items : [emptyWorkItem()]
  const workItemIndexById = new Map(
    workItems
      .filter((item) => item.id)
      .map((item, index) => [Number(item.id), String(index + 1)]),
  )
  const workFindings = packageData.work_findings?.length
    ? packageData.work_findings.map((item) => ({
        ...item,
        work_item_index: item.work_item_index
          || (item.work_item_id ? workItemIndexById.get(Number(item.work_item_id)) || '' : ''),
      }))
    : [emptyFinding()]

  return {
    qaar_report_summary: packageData.report_summary || {},
    qaar_project_management_checks: packageData.project_management_checks?.length
      ? packageData.project_management_checks
      : buildDefaultChecks(catalog, 'project_management_checks'),
    qaar_work_items: workItems,
    qaar_work_findings: workFindings,
    qaar_health_safety_checks: packageData.health_safety_checks?.length
      ? packageData.health_safety_checks
      : buildDefaultChecks(catalog, 'health_safety_checks'),
  }
}

function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('en-PH', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function formatDateTimeInput(value) {
  if (!value) return ''
  return value.slice(0, 16)
}

function parseOptionalPercentInput(value) {
  const text = String(value ?? '').trim()
  if (!text) return { value: null }
  const parsed = Number(text)
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100) {
    return { error: 'Physical accomplishment must be between 0 and 100.' }
  }
  return { value: parsed }
}

function supportsQaarMonitoring(project) {
  const applicability = project?.monitoring_profile?.effective_monitoring_applicability || project?.monitoring_applicability
  if (applicability) return ['qaar', 'mixed'].includes(applicability)
  const effectiveType = (project?.project_kind || project?.program_type || '').toLowerCase().trim()
  if (['goods', 'vehicle', 'financial_assistance', 'non_infrastructure'].includes(effectiveType)) return false
  if (['infrastructure', 'infra', 'hybrid', 'mixed'].includes(effectiveType)) return true
  return true
}

function labelFor(options, value) {
  return options.find((item) => item.value === value)?.label || formatMachineLabel(value)
}

function numericValue(value) {
  if (value === null || value === undefined || value === '') return null
  const clean = typeof value === 'string' ? value.replace(/,/g, '').trim() : value
  const parsed = Number(clean)
  return Number.isFinite(parsed) ? parsed : null
}

function dateValue(value) {
  if (!value) return null
  const parsed = new Date(`${value}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function inclusiveDays(startValue, endValue) {
  const startDate = dateValue(startValue)
  const endDate = dateValue(endValue)
  if (!startDate || !endDate || endDate < startDate) return null
  return Math.floor((endDate.getTime() - startDate.getTime()) / 86400000) + 1
}

function formatComputedNumber(value, fractionDigits = 2) {
  if (value === null || value === undefined || !Number.isFinite(value)) return ''
  return value.toLocaleString('en-PH', {
    maximumFractionDigits: fractionDigits,
  })
}

const QAAR_AMOUNT_KEYS = new Set(['national_subsidy', 'contract_amount', 'lgu_counterpart', 'liquidation'])

function hasCheckAnswer(item) {
  if (item?.response) return true
  const formData = item?.form_data || {}
  return Object.values(formData).some((value) => value !== null && value !== undefined && value !== '')
}

function responseRecommendation(item, response = item?.response) {
  if (!response) return ''
  const option = (item?.response_options || []).find((candidate) => candidate.value === response)
  return option?.recommendation || option?.finding || ''
}

function computeRatioCheck(item) {
  if (item?.input_type !== 'ratio') return {}
  const fields = item.input_fields || []
  const formData = item.form_data || {}
  const denominator = numericValue(formData[fields[0]?.key])
  const numerator = numericValue(formData[fields[1]?.key])
  const maxPoints = numericValue(item.max_points) || 0
  if (denominator === null) {
    return { response: '', score: '', scoreBucket: '', recommendation: '' }
  }
  let completionRate = null
  let score = maxPoints
  if (denominator !== 0) {
    completionRate = Math.min(Math.max((numerator || 0) / denominator, 0), 1)
    score = Number((completionRate * maxPoints).toFixed(2))
  }
  const response = denominator === 0 ? 'N/A' : `${formatComputedNumber((completionRate || 0) * 100)}%`
  const scoreBucket = Number.isFinite(score) ? Math.floor(score) : ''
  const recommendation = Number.isFinite(score) && score < maxPoints ? item.recommendation || '' : ''
  return { response, score, scoreBucket, recommendation }
}

function checkPayloadEntered(item) {
  return hasCheckAnswer(item) || Boolean(item?.remarks)
}

function fieldHasValue(value) {
  return value !== null && value !== undefined && String(value).trim() !== ''
}

function workItemPayloadEntered(item) {
  return [
    item?.item_code,
    item?.description,
    item?.quantity,
    item?.inspected_quantity,
    item?.unit,
    item?.unit_cost,
    item?.location,
    item?.source_catalog_row,
  ].some(fieldHasValue)
}

function workFindingPayloadEntered(item) {
  return [
    item?.work_item_index,
    item?.defect_code,
    item?.defect_description,
    item?.quality_issue,
    item?.recommendation,
    item?.location,
    item?.degree_of_defect,
    item?.rating_weight,
    item?.timeline,
    item?.remarks,
    item?.risk_level,
    item?.source_catalog_row,
  ].some(fieldHasValue)
}

function normalizeQaarProjectStatus(value) {
  if (!value) return ''
  const normalized = String(value).trim().replace(/[_-]/g, ' ').replace(/\s+/g, ' ').toUpperCase()
  const aliases = {
    ONGOING: 'ON-GOING',
    'ON GOING': 'ON-GOING',
    'ON-GOING': 'ON-GOING',
    SUSPENDED: 'SUSPENDED',
    COMPLETED: 'COMPLETED',
    CANCELED: 'CANCELLED',
    CANCELLED: 'CANCELLED',
  }
  return aliases[normalized] || String(value).trim()
}

function normalizeQaarRegion(value) {
  const normalized = String(value || '').trim().toUpperCase()
  if (!normalized) return QAAR_DEFAULT_REGION
  if (normalized.includes('CALABARZON') || normalized === 'REGION IV-A' || normalized === 'REGION IVA') {
    return QAAR_DEFAULT_REGION
  }
  return normalized
}

function normalizeQaarProvince(value) {
  const normalized = String(value || '').trim().toUpperCase()
  return normalized || QAAR_DEFAULT_PROVINCE
}

function normalizeQaarMunicipality(project) {
  const raw = project?.lgu_municipality || project?.lgu_name || ''
  const displayName = project?.lgu_name || ''
  const withoutPrefix = String(raw)
    .replace(/^Municipality of\s+/i, '')
    .replace(/^City of\s+/i, '')
    .trim()
  if (!withoutPrefix) return ''
  if (withoutPrefix.toLowerCase() === 'santa cruz') return 'SANTA CRUZ (Capital)'
  if (/^City of\s+/i.test(displayName) && !/^CITY OF\s+/i.test(withoutPrefix)) {
    return `CITY OF ${withoutPrefix.replace(/\s+City$/i, '').toUpperCase()}`
  }
  return withoutPrefix.toUpperCase()
}

function implementingUnitForProject(project) {
  const customFields = project?.custom_fields || {}
  const configured = String(customFields.implementing_unit || '').trim().toUpperCase()
  if (['PROVINCIAL LGU', 'MUNICIPAL LGU', 'CITY LGU', 'BARANGAY LGU'].includes(configured)) {
    return configured
  }
  if (String(customFields.district || '').trim().toUpperCase() === 'PROVINCIAL') {
    return 'PROVINCIAL LGU'
  }
  if (/^City of\s+/i.test(project?.lgu_name || '')) {
    return 'CITY LGU'
  }
  return 'MUNICIPAL LGU'
}

function reportSummarySelectOptions(field, currentValue = '') {
  if (field.key === 'actual_project_status') return QAAR_PROJECT_STATUSES
  if (field.options?.length) {
    const options = [{ value: '', label: 'Blank' }, ...field.options]
    const hasCurrentValue = options.some((option) => option.value === currentValue)
    if (currentValue && !hasCurrentValue) {
      return [...options, { value: currentValue, label: currentValue }]
    }
    return options
  }
  return null
}

function computeQaarReportSummary(summary = {}) {
  const planned = numericValue(summary.planned_accomplishment_pct)
  const actual = numericValue(summary.actual_accomplishment_pct)
  const nationalSubsidy = numericValue(summary.national_subsidy)
  const lguCounterpart = numericValue(summary.lgu_counterpart)
  const liquidation = numericValue(summary.liquidation)
  const contractAmount = numericValue(summary.contract_amount)
  const actualProjectStatus = normalizeQaarProjectStatus(summary.actual_project_status)
  const duration = inclusiveDays(summary.date_started, summary.target_completion_date)
  const elapsedDays = actualProjectStatus === 'COMPLETED'
    ? inclusiveDays(summary.date_started, summary.actual_completion_date)
    : inclusiveDays(summary.date_started, summary.date_of_inspection_assessment)
  const timeElapsed = duration && elapsedDays ? Math.min(elapsedDays / duration, 1) : null
  const statusAllowsSlippage = ['ON-GOING', 'SUSPENDED', 'CANCELLED'].includes(actualProjectStatus)
  const slippageBasis = planned !== null ? planned : timeElapsed !== null ? timeElapsed * 100 : null

  return {
    percent_slippage: statusAllowsSlippage && slippageBasis !== null && actual !== null
      ? formatComputedNumber(actual - slippageBasis)
      : '',
    project_duration: duration ? String(duration) : '',
    time_elapsed: timeElapsed !== null ? `${formatComputedNumber(timeElapsed * 100)}%` : '',
    total_project_cost: nationalSubsidy !== null
      ? formatComputedNumber(nationalSubsidy + (lguCounterpart || 0))
      : '',
    balance_of_contract: contractAmount !== null && liquidation !== null
      ? formatComputedNumber(contractAmount - liquidation)
      : '',
  }
}

function computeWorkItemMetrics(items = []) {
  const rows = items.map((item) => {
    const inspectedQuantity = numericValue(item.inspected_quantity)
    const quantity = numericValue(item.quantity)
    const unitCost = numericValue(item.unit_cost)
    const basisQuantity = inspectedQuantity ?? quantity
    const computedCost = basisQuantity !== null && unitCost !== null ? basisQuantity * unitCost : null
    return { computedCost, computedWeight: null }
  })
  const totalCost = rows.reduce((sum, item) => sum + (item.computedCost ?? 0), 0)
  return rows.map((item) => ({
    ...item,
    computedWeight: totalCost && item.computedCost !== null ? item.computedCost / totalCost : null,
  }))
}

function checkRowPoints(item) {
  if (item?.input_type === 'ratio') {
    const metrics = computeRatioCheck(item)
    return numericValue(metrics.score)
  }
  if (!item?.response) return null
  const option = (item.response_options || []).find((candidate) => candidate.value === item.response)
  return numericValue(option?.points)
}

function scoreChecklistRows(rows = []) {
  const answeredRows = rows.filter(hasCheckAnswer)
  const points = answeredRows.reduce((sum, item) => sum + (checkRowPoints(item) || 0), 0)
  const officialMaxPoints = rows.reduce((sum, item) => sum + (numericValue(item.max_points) || 0), 0)
  return {
    answeredRows: answeredRows.length,
    officialRows: rows.length,
    points,
    officialMaxPoints,
  }
}

function riskForFraction(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return ''
  const percent = value * 100
  if (percent === 100) return 'NO RISK'
  if (percent >= 85) return 'LOW'
  if (percent >= 70) return 'MODERATE'
  return 'HIGH'
}

function riskForComponent(value, componentWeight) {
  if (value === null || value === undefined || !Number.isFinite(value) || !componentWeight) return ''
  return riskForFraction(value / componentWeight)
}

function riskForTimeliness(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return ''
  if (value === 100) return 'NO RISK'
  if (value === 80) return 'LOW'
  if (value === 70) return 'MODERATE'
  return 'HIGH'
}

function qualityIssueWeight(value, ratings = {}) {
  if (!value) return null
  const normalized = String(value).trim().toLowerCase().replace(/\s+/g, ' ')
  const match = (ratings.quality_issue_weights || []).find((option) => {
    const optionValues = [option.value, option.label].map((item) => String(item || '').trim().toLowerCase().replace(/\s+/g, ' '))
    return optionValues.includes(normalized)
  })
  if (match) return numericValue(match.weight)
  if (normalized.startsWith('high')) return 5
  if (normalized.startsWith('moderate')) return 3
  if (normalized.startsWith('low')) return 1
  return null
}

function computeQualityFindingMetrics(findings = [], workItems = [], workItemMetrics = [], ratings = {}) {
  const qualityWeightTotals = new Map()
  findings.forEach((finding) => {
    const itemIndex = Number(finding.work_item_index)
    if (!Number.isInteger(itemIndex) || itemIndex <= 0) return
    const weight = qualityIssueWeight(finding.quality_issue, ratings)
    if (weight === null) return
    qualityWeightTotals.set(itemIndex, (qualityWeightTotals.get(itemIndex) || 0) + weight)
  })
  return findings.map((finding) => {
    const itemIndex = Number(finding.work_item_index)
    const workItem = Number.isInteger(itemIndex) && itemIndex > 0 ? workItems[itemIndex - 1] : null
    const workItemMetric = Number.isInteger(itemIndex) && itemIndex > 0 ? workItemMetrics[itemIndex - 1] : null
    const itemWeight = workItemMetric?.computedWeight ?? null
    const ratingPerDegree = numericValue(finding.rating_weight)
    const issueWeight = qualityIssueWeight(finding.quality_issue, ratings)
    const issueWeightTotal = qualityWeightTotals.get(itemIndex)
    const derivedRating = itemWeight !== null && issueWeightTotal ? itemWeight / issueWeightTotal : null
    const weightedIssue = issueWeight !== null && derivedRating !== null ? issueWeight * derivedRating : null
    const totalRating = ratingPerDegree !== null && weightedIssue !== null ? ratingPerDegree * weightedIssue : null
    return {
      description: workItem?.description || '',
      unit: workItem?.unit || '',
      weight: itemWeight,
      qualityIssueWeight: issueWeight,
      derivedRating,
      totalRating,
    }
  })
}

function timelinessRatingPct(summary = {}, computedSummary = {}) {
  const status = normalizeQaarProjectStatus(summary.actual_project_status)
  const planned = numericValue(summary.planned_accomplishment_pct)
  const actual = status === 'COMPLETED' ? 100 : numericValue(summary.actual_accomplishment_pct)
  const timeElapsed = numericValue(computedSummary.time_elapsed)
  const plannedTarget = planned !== null ? planned : timeElapsed
  const variance = actual !== null && plannedTarget !== null ? actual - plannedTarget : null
  if (timeElapsed === null && plannedTarget === null) return { plannedTarget, actual, variance, rating: null, note: '' }
  if ([plannedTarget, actual, variance].every((value) => value === 0)) return { plannedTarget, actual, variance, rating: null, note: '' }
  let rating = null
  if (timeElapsed !== null && timeElapsed > 100) rating = 0
  else if (variance === null) rating = null
  else if (variance >= 100) rating = 0
  else if (variance >= 0) rating = 100
  else if (variance >= -5.99) rating = 80
  else if (variance >= -10.99) rating = 70
  else if (variance >= -15.99) rating = 50
  else if (variance >= -20.99) rating = 30
  else rating = 0
  const note = timeElapsed !== null && timeElapsed > 100
    ? 'Time elapsed exceeded the construction duration'
    : variance !== null && variance < -15
      ? "Subject for Termination of the Contractor's Contract"
      : variance !== null && variance < 0
        ? 'Per RA 9184: LGU must issue a warning letter to Contractor'
        : ''
  return { plannedTarget, actual, variance, rating, note }
}

function computeQaarAssessmentRatings({
  summary,
  computedSummary,
  projectManagementChecks,
  healthSafetyChecks,
  findingMetrics,
}) {
  const projectManagement = scoreChecklistRows(projectManagementChecks)
  const healthSafety = scoreChecklistRows(healthSafetyChecks)
  const pmWeighted = projectManagement.answeredRows && projectManagement.officialMaxPoints
    ? (projectManagement.points / projectManagement.officialMaxPoints) * 0.3
    : null
  const totalDemerit = findingMetrics.reduce((sum, item) => sum + (item.totalRating ?? 0), 0)
  const qowWeighted = findingMetrics.length ? Math.max(1 - totalDemerit, 0) * 0.7 : null
  const combinedQuality = [pmWeighted, qowWeighted].some((value) => value !== null)
    ? (pmWeighted || 0) + (qowWeighted || 0)
    : null
  const timeliness = timelinessRatingPct(summary, computedSummary)
  const timelinessFraction = timeliness.rating !== null ? timeliness.rating / 100 : null
  const toDate = combinedQuality !== null && timelinessFraction !== null
    ? combinedQuality * 0.6 + timelinessFraction * 0.4
    : null
  const healthRating = healthSafety.answeredRows && healthSafety.officialMaxPoints
    ? healthSafety.points / healthSafety.officialMaxPoints
    : null
  return {
    qualityRows: [
      { label: 'Project Management (30%)', value: pmWeighted, risk: riskForComponent(pmWeighted, 0.3) },
      { label: 'Workmanship/Quality of Works (70%)', value: qowWeighted, risk: riskForComponent(qowWeighted, 0.7) },
      { label: 'Rating on Quality (Output I + Output II)', value: combinedQuality, risk: riskForFraction(combinedQuality) },
    ],
    timeliness: {
      ...timeliness,
      value: timelinessFraction,
      risk: riskForTimeliness(timeliness.rating),
    },
    toDate: { value: toDate, risk: riskForFraction(toDate) },
    healthSafety: {
      value: healthRating,
      risk: healthRating === null ? '' : healthRating >= 1 ? 'Compliant' : 'Non-Compliant',
    },
  }
}

function formatComputedPercent(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return ''
  return `${formatComputedNumber(value * 100, 2)}%`
}

function formatPercentValue(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return ''
  return `${formatComputedNumber(value, 2)}%`
}

function filenameFromDisposition(disposition, fallback) {
  const match = /filename="?([^"]+)"?/i.exec(disposition || '')
  return match?.[1] || fallback
}

function statusBadge(status) {
  return (
    <span className={badgeClassForStatus(status || 'draft', 'info')}>
      {formatStatus(status)}
    </span>
  )
}

function transmittalBadge(status) {
  return (
    <span className={badgeClassForStatus(status || 'not_required')}>
      {labelFor(TRANSMITTAL_STATUSES, status)}
    </span>
  )
}

const QAAR_OUTPUT_ORDER = [
  'full_package',
  'aide_memoire',
  'notice_of_defects',
]

const QAAR_OUTPUT_DESCRIPTIONS = {
  full_package: 'Complete monitoring report package for this record.',
  report_summary: 'Project details, schedule, accomplishment, and contract amounts.',
  project_management: 'Project controls, site records, and required project documents.',
  quality_of_works: 'Inspected work items, defects, recommendations, timelines, and ratings.',
  health_and_safety: 'Safety practices, worker protection, and site control checks.',
  aide_memoire: 'Findings, recommendations, timelines, and agreements prepared for the Aide Memoire.',
  notice_of_defects: 'Defects and required corrective actions prepared for notice issuance.',
}

function SectionCard({ id, eyebrow, title, description, action, children, contentClassName = 'space-y-4' }) {
  return (
    <section
      id={id}
      className="scroll-mt-4 rounded-lg border border-brand-border bg-brand-surface-solid shadow-sm"
    >
      <header className="flex flex-col gap-1 border-b border-brand-border px-5 py-4 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div className="min-w-0">
          {eyebrow && (
            <p className="text-[11px] font-semibold uppercase tracking-wider text-brand-text-muted">
              {eyebrow}
            </p>
          )}
          <h3 className="text-sm font-semibold text-brand-text">{title}</h3>
          {description && (
            <p className="mt-1 text-xs text-brand-text-muted">{description}</p>
          )}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </header>
      <div className={`px-5 py-4 ${contentClassName}`}>{children}</div>
    </section>
  )
}

function ComputedStrip({ items }) {
  const visible = items.filter((item) => item)
  if (!visible.length) return null
  return (
    <div className="rounded-md border border-dashed border-brand-border bg-brand-surface px-4 py-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-brand-text-muted">
        <Calculator className="h-3.5 w-3.5" strokeWidth={1.8} />
        Calculated for you
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        {visible.map((item) => (
          <div key={item.label} className="min-w-0">
            <dt className="truncate text-[11px] font-medium uppercase tracking-wide text-brand-text-muted">
              {item.label}
            </dt>
            <dd className="truncate text-sm font-semibold text-brand-text">
              {item.value || <span className="text-brand-text-muted">—</span>}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function SectionTabs({ items, activeId, onSelect }) {
  if (!items.length) return null
  const activeIndex = Math.max(items.findIndex((item) => item.id === activeId), 0)
  return (
    <nav
      role="tablist"
      aria-label="Monitoring record sections"
      className="sticky top-0 z-10 -mx-1 flex flex-wrap gap-1 rounded-md border border-brand-border bg-brand-surface-solid/95 p-1 shadow-sm backdrop-blur"
    >
      {items.map((item, index) => {
        const Icon = item.icon
        const active = item.id === activeId
        const visited = index < activeIndex
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onSelect(item.id)}
            className={`inline-flex items-center gap-2 rounded px-3 py-1.5 text-xs font-medium transition-colors ${
              active
                ? 'bg-brand-primary/10 text-brand-primary ring-1 ring-brand-primary/30'
                : visited
                  ? 'text-brand-text hover:bg-brand-surface'
                  : 'text-brand-text-muted hover:bg-brand-surface hover:text-brand-text'
            }`}
          >
            <span
              className={`inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-semibold ${
                active
                  ? 'bg-brand-primary text-white dark:text-slate-950'
                  : visited
                    ? 'bg-brand-primary/15 text-brand-primary'
                    : 'bg-brand-surface text-brand-text-muted'
              }`}
              aria-hidden="true"
            >
              {index + 1}
            </span>
            {Icon && <Icon className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden="true" />}
            <span>{item.label}</span>
            {item.badge && (
              <span className="ml-1 rounded-full bg-brand-surface px-1.5 py-px text-[10px] font-semibold text-brand-text-muted">
                {item.badge}
              </span>
            )}
          </button>
        )
      })}
    </nav>
  )
}

function GeneratedOutputsPanel({ outputs, onDownload }) {
  const lookup = latestOutputByType(outputs)
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {QAAR_OUTPUT_ORDER.map((type) => {
        const output = lookup.get(type)
        const ready = Boolean(output?.file_object_id)
        return (
          <div
            key={type}
            className="flex items-center justify-between gap-3 rounded-md border border-brand-border bg-brand-surface px-3 py-2"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-brand-text-muted" strokeWidth={1.7} aria-hidden="true" />
                <p className="truncate text-sm font-semibold text-brand-text">
                  {QAAR_OUTPUT_LABELS[type] || formatStatus(type)}
                </p>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                    ready
                      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300'
                      : 'bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300'
                  }`}
                >
                  {ready ? 'Ready' : 'Not generated'}
                </span>
              </div>
              <p className="mt-1 truncate text-xs text-brand-text-muted">
                {QAAR_OUTPUT_DESCRIPTIONS[type] || 'Prepared from this monitoring record.'}
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              variant={ready ? 'outline' : 'ghost'}
              icon={FileDown}
              disabled={!ready}
              onClick={() => ready && onDownload(output)}
            >
              Download
            </Button>
          </div>
        )
      })}
    </div>
  )
}

function ReportsModal({ inspection, onClose, onGenerate, onDownload, generatingId, generatingType }) {
  const [showHistory, setShowHistory] = useState(false)

  if (!inspection) return null

  const allOutputs = displayableGeneratedOutputs(inspection.generated_outputs || [])
  const groups = groupOutputsByType(allOutputs)
  const latest = latestOutputByType(allOutputs)
  const isBusy = generatingId === inspection.id
  const isAllRunning = isBusy && generatingType === 'all'
  const totalReady = QAAR_OUTPUT_ORDER.reduce((count, type) => count + (latest.get(type)?.file_object_id ? 1 : 0), 0)
  const hasAnyHistory = QAAR_OUTPUT_ORDER.some((type) => (groups.get(type) || []).length > 1)

  return (
    <Modal
      open
      title="QAAR monitoring reports"
      description={`Generate, regenerate, and download monitoring PDFs for ${inspection.project_name || 'this record'}.`}
      onClose={onClose}
      size="xl"
      footer={(
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-brand-text-muted">
            {totalReady}/{QAAR_OUTPUT_ORDER.length} reports ready · Latest version is highlighted for each report.
          </p>
          <Button variant="outline" size="sm" onClick={onClose} disabled={isBusy}>Close</Button>
        </div>
      )}
    >
      <div className="space-y-5">
        <div className="flex flex-col gap-3 rounded-md border border-brand-border bg-brand-surface px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-brand-text">
              {totalReady === 0 ? 'No reports generated yet.' : 'All monitoring reports'}
            </p>
            <p className="text-xs text-brand-text-muted">
              {totalReady === 0
                ? 'Click below to create the QAAR Package, Aide Memoire, and Notice of Defects PDFs.'
                : 'Regenerate everything when the underlying record has changed materially.'}
            </p>
          </div>
          <Button
            size="sm"
            variant="primary"
            icon={isAllRunning ? undefined : (totalReady === 0 ? FileDown : RefreshCw)}
            loading={isAllRunning}
            disabled={isBusy && !isAllRunning}
            onClick={() => onGenerate(inspection)}
          >
            {isAllRunning
              ? 'Generating…'
              : (totalReady === 0 ? 'Generate all reports' : 'Regenerate all')}
          </Button>
        </div>

        <div className="space-y-3">
          {QAAR_OUTPUT_ORDER.map((type) => {
            const current = latest.get(type)
            const ready = Boolean(current?.file_object_id)
            const isThisRunning = isBusy && generatingType === type
            return (
              <div key={type} className="rounded-md border border-brand-border bg-brand-surface-solid p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <FileText className="h-4 w-4 text-brand-text-muted" strokeWidth={1.7} aria-hidden="true" />
                      <p className="text-sm font-semibold text-brand-text">
                        {QAAR_OUTPUT_LABELS[type] || formatStatus(type)}
                      </p>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                          ready
                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300'
                            : 'bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300'
                        }`}
                      >
                        {ready ? 'Ready' : 'Not generated'}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-brand-text-muted">
                      {QAAR_OUTPUT_DESCRIPTIONS[type] || 'Prepared from this monitoring record.'}
                    </p>
                    {ready && (
                      <p className="mt-1 text-xs text-brand-text-muted">
                        Latest generated {formatGeneratedAt(current.generated_at)}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-shrink-0 flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      icon={FileDown}
                      disabled={!ready || isBusy}
                      onClick={() => ready && onDownload(current)}
                    >
                      Download
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      icon={isThisRunning ? undefined : (ready ? RefreshCw : FileDown)}
                      loading={isThisRunning}
                      disabled={isBusy && !isThisRunning}
                      onClick={() => onGenerate(inspection, { outputTypes: [type] })}
                    >
                      {isThisRunning ? 'Generating…' : (ready ? 'Regenerate' : 'Generate')}
                    </Button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {hasAnyHistory && (
          <div className="rounded-md border border-brand-border bg-brand-surface">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
              onClick={() => setShowHistory((value) => !value)}
            >
              <span className="flex items-center gap-2 text-sm font-semibold text-brand-text">
                <History className="h-4 w-4 text-brand-text-muted" strokeWidth={1.7} aria-hidden="true" />
                Previous versions
              </span>
              <span className="text-xs text-brand-text-muted">
                {showHistory ? 'Hide' : 'Show'}
              </span>
            </button>
            {showHistory && (
              <div className="space-y-3 border-t border-brand-border px-4 py-3">
                {QAAR_OUTPUT_ORDER.map((type) => {
                  const versions = groups.get(type) || []
                  if (versions.length <= 1) return null
                  const older = versions.slice(1)
                  return (
                    <div key={`history-${type}`} className="space-y-1">
                      <p className="text-xs font-semibold uppercase tracking-wide text-brand-text-muted">
                        {QAAR_OUTPUT_LABELS[type] || formatStatus(type)}
                      </p>
                      <ul className="divide-y divide-brand-border rounded-md border border-brand-border bg-brand-surface-solid">
                        {older.map((output) => {
                          const ready = Boolean(output.file_object_id)
                          return (
                            <li key={output.id} className="flex items-center justify-between gap-3 px-3 py-2 text-xs">
                              <span className="text-brand-text">{formatGeneratedAt(output.generated_at)}</span>
                              <Button
                                size="sm"
                                variant="ghost"
                                icon={FileDown}
                                disabled={!ready || isBusy}
                                onClick={() => ready && onDownload(output)}
                              >
                                Download
                              </Button>
                            </li>
                          )
                        })}
                      </ul>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  )
}

function displayableGeneratedOutputs(outputs = []) {
  const userFacing = outputs.filter((output) => QAAR_OUTPUT_ORDER.includes(output.output_type))
  return userFacing.length ? userFacing : outputs
}

function groupOutputsByType(outputs = []) {
  const groups = new Map()
  for (const output of outputs) {
    const list = groups.get(output.output_type) || []
    list.push(output)
    groups.set(output.output_type, list)
  }
  for (const list of groups.values()) {
    list.sort((a, b) => {
      const left = a.generated_at ? Date.parse(a.generated_at) : 0
      const right = b.generated_at ? Date.parse(b.generated_at) : 0
      return right - left
    })
  }
  return groups
}

function latestOutputByType(outputs = []) {
  const latest = new Map()
  for (const [type, list] of groupOutputsByType(outputs)) {
    if (list.length) latest.set(type, list[0])
  }
  return latest
}

function formatGeneratedAt(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('en-PH', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return value
  }
}

function groupChecksBySection(checks) {
  const groups = []
  const lookup = new Map()
  ;(checks || []).forEach((check, index) => {
    const sectionKey = check.section || 'general'
    if (!lookup.has(sectionKey)) {
      const group = { key: sectionKey, label: check.section || '', items: [] }
      lookup.set(sectionKey, group)
      groups.push(group)
    }
    lookup.get(sectionKey).items.push({ ...check, originalIndex: index })
  })
  return groups
}

function checklistCompletion(checks) {
  const total = (checks || []).length
  const answered = (checks || []).filter(hasCheckAnswer).length
  return { total, answered }
}

function ChecklistRow({ item, onPatch }) {
  const headerLabel = `${item.official_item_no ? `${item.official_item_no}. ` : ''}${item.label || item.check_key}`
  const points = item.max_points ? `${item.max_points} pt${item.max_points === 1 ? '' : 's'}` : null
  const responseId = `check-response-${item.check_key}`
  const remarksId = `check-remarks-${item.check_key}`
  const options = item.response_options?.length ? [{ value: '', label: 'Blank' }, ...item.response_options] : []

  if (item.input_type === 'ratio') {
    const metrics = computeRatioCheck(item)
    return (
      <div className="grid grid-cols-1 gap-3 rounded-md border border-brand-border bg-brand-surface px-3 py-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1.1fr)_minmax(0,1.3fr)]">
        <div className="min-w-0">
          <p className="block text-sm font-medium text-brand-text">{headerLabel}</p>
          {points && (
            <p className="mt-0.5 text-[11px] uppercase tracking-wide text-brand-text-muted">
              Max {points}
            </p>
          )}
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {(item.input_fields || []).map((field) => (
            <div key={field.key}>
              <label htmlFor={`${item.check_key}-${field.key}`} className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-brand-text-muted">
                {field.label}
              </label>
              <input
                id={`${item.check_key}-${field.key}`}
                className="input-field"
                type="number"
                min="0"
                step="1"
                value={item.form_data?.[field.key] ?? ''}
                onChange={(event) => onPatch({
                  form_data: {
                    ...(item.form_data || {}),
                    [field.key]: event.target.value,
                  },
                })}
              />
            </div>
          ))}
        </div>
        <div className="space-y-2">
          <ComputedStrip
            items={[
              { label: 'Result', value: metrics.response },
              { label: 'Score', value: metrics.score === '' ? '' : String(metrics.score) },
              { label: 'Score bucket', value: metrics.scoreBucket === '' ? '' : String(metrics.scoreBucket) },
            ]}
          />
          <textarea
            id={remarksId}
            className="input-field min-h-[74px]"
            readOnly
            value={metrics.recommendation}
            placeholder="Recommendation appears when action is needed"
          />
        </div>
      </div>
    )
  }

  const recommendation = item.remarks || responseRecommendation(item)

  return (
    <div className="grid grid-cols-1 gap-3 rounded-md border border-brand-border bg-brand-surface px-3 py-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(8rem,11rem)_minmax(0,1.2fr)]">
      <div className="min-w-0">
        <label htmlFor={responseId} className="block text-sm font-medium text-brand-text">
          {headerLabel}
        </label>
        {points && (
          <p className="mt-0.5 text-[11px] uppercase tracking-wide text-brand-text-muted">
            Max {points}
          </p>
        )}
      </div>
      <div>
        {options.length ? (
          <select
            id={responseId}
            className="input-field"
            value={item.response || ''}
            onChange={(event) => {
              const response = event.target.value
              onPatch({
                response,
                remarks: responseRecommendation(item, response),
              })
            }}
          >
            {options.map((option, optionIndex) => (
              <option key={`${option.value}-${optionIndex}`} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : (
          <p className="rounded-md border border-dashed border-brand-border px-3 py-2 text-xs text-brand-text-muted">
            No response input required.
          </p>
        )}
      </div>
      <div>
        <textarea
          id={remarksId}
          className="input-field min-h-[64px]"
          readOnly
          placeholder="Recommendation appears after choosing a response"
          value={recommendation}
        />
      </div>
    </div>
  )
}

function QaarChecklist({ field, checks, updateArrayItem }) {
  const groups = groupChecksBySection(checks)
  const [showOnlyUnanswered, setShowOnlyUnanswered] = useState(false)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-brand-text-muted">
          Enter the required values or choose the observed response. Recommendations fill in when action is needed.
        </p>
        <label className="inline-flex items-center gap-2 text-xs text-brand-text-muted">
          <input
            type="checkbox"
            checked={showOnlyUnanswered}
            onChange={(event) => setShowOnlyUnanswered(event.target.checked)}
          />
          Show only unanswered
        </label>
      </div>
      {groups.map((group) => {
        const visible = showOnlyUnanswered
          ? group.items.filter((item) => !hasCheckAnswer(item))
          : group.items
        if (!visible.length && showOnlyUnanswered) return null
        const total = group.items.length
        const answered = group.items.filter(hasCheckAnswer).length
        return (
          <div key={group.key} className="rounded-md border border-brand-border">
            <header className="flex items-center justify-between gap-2 border-b border-brand-border bg-brand-surface px-3 py-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-brand-text">
                {group.label || 'General'}
              </h4>
              <span className="text-[11px] font-medium text-brand-text-muted">
                {answered} of {total} answered
              </span>
            </header>
            <div className="space-y-2 p-3">
              {visible.map((item) => {
                return (
                  <ChecklistRow
                    key={`${item.check_key}-${item.originalIndex}`}
                    item={item}
                    onPatch={(patch) => updateArrayItem(field, item.originalIndex, patch)}
                  />
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

const VALID_MODULES = ['qaar', 'monthly_progress', 'form3', 'exception', 'non_infra', 'beneficiary', 'vv_queue', 'mar']

export default function ImplementationMonitoringPage() {
  const [searchParams] = useSearchParams()
  const urlTab = searchParams.get('tab') || searchParams.get('module')
  const initialPageView = VALID_MODULES.includes(urlTab) ? urlTab : 'qaar'
  const initialSearch = searchParams.get('search') || ''
  const initialStatus = searchParams.get('status') || ''
  const [projects, setProjects] = useState([])
  const [inspections, setInspections] = useState([])
  const [qaarCatalog, setQaarCatalog] = useState({ project_management_checks: [], health_safety_checks: [] })
  const [meta, setMeta] = useState({ total: 0 })
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [savingDraft, setSavingDraft] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [formOpen, setFormOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [filters, setFilters] = useState({ search: initialSearch, status: initialStatus, transmittal_status: '', monthly_cycle_tag: '' })
  const [form, setForm] = useState(EMPTY_FORM)
  const [activeSection, setActiveSection] = useState('record-details')
  const [generatingId, setGeneratingId] = useState(null)
  const [generatingType, setGeneratingType] = useState(null)
  const [reportsInspection, setReportsInspection] = useState(null)
  const [pageView, setPageView] = useState(initialPageView)

  const loadPage = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = { per_page: 100 }
      if (filters.search) params.search = filters.search
      if (filters.status) params.status = filters.status
      if (filters.transmittal_status) params.transmittal_status = filters.transmittal_status
      if (filters.monthly_cycle_tag) params.monthly_cycle_tag = filters.monthly_cycle_tag

      const [projectsRes, inspectionsRes, catalogRes] = await Promise.all([
        projectApi.listProjects({ per_page: 100 }),
        monitoringApi.listInspections(params),
        monitoringApi.getQaarCatalog(),
      ])
      setProjects(projectsRes.data || [])
      setInspections(inspectionsRes.data || [])
      setQaarCatalog(catalogRes.data || { project_management_checks: [], health_safety_checks: [] })
      setMeta(inspectionsRes.meta || { total: 0 })
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to load implementation monitoring records.')
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    loadPage()
  }, [loadPage])

  useEffect(() => {
    const tab = searchParams.get('tab') || searchParams.get('module')
    if (tab && VALID_MODULES.includes(tab)) {
      setPageView((prev) => (prev !== tab ? tab : prev))
    }
    const s = searchParams.get('search') || ''
    const st = searchParams.get('status') || ''
    setFilters((prev) => ({
      ...prev,
      search: s,
      status: st,
    }))
  }, [searchParams])

  useEffect(() => {
    if (!reportsInspection) return
    const fresh = inspections.find((item) => item.id === reportsInspection.id)
    if (fresh && fresh !== reportsInspection) {
      setReportsInspection(fresh)
    }
  }, [inspections, reportsInspection])

  useEffect(() => {
    if (!formOpen) return
    setForm((current) => {
      const patch = {}
      if (!current.qaar_project_management_checks.length && qaarCatalog.project_management_checks?.length) {
        patch.qaar_project_management_checks = buildDefaultChecks(qaarCatalog, 'project_management_checks')
      }
      if (!current.qaar_health_safety_checks.length && qaarCatalog.health_safety_checks?.length) {
        patch.qaar_health_safety_checks = buildDefaultChecks(qaarCatalog, 'health_safety_checks')
      }
      if (!Object.keys(patch).length) return current
      return { ...current, ...patch }
    })
  }, [formOpen, qaarCatalog])

  const monitorableProjects = useMemo(
    () => projects.filter((project) => project.current_phase !== 'pre_implementation' && supportsQaarMonitoring(project)),
    [projects],
  )

  const selectedProject = useMemo(
    () => monitorableProjects.find((project) => Number(project.id) === Number(form.project_id)),
    [form.project_id, monitorableProjects],
  )

  const itemCatalogOptions = useMemo(() => {
    const category = form.qaar_category || selectedProject?.monitoring_profile?.qaar_category || selectedProject?.qaar_category || ''
    return (qaarCatalog.item_catalog_entries || []).filter((item) => !category || item.category === category)
  }, [form.qaar_category, qaarCatalog.item_catalog_entries, selectedProject])

  const findingCatalogOptions = useMemo(
    () => qaarCatalog.finding_catalog_entries || [],
    [qaarCatalog.finding_catalog_entries],
  )

  const itemCatalogByCode = useMemo(() => {
    const lookup = new Map()
    ;(qaarCatalog.item_catalog_entries || []).forEach((item) => {
      lookup.set(item.item_code, item)
    })
    return lookup
  }, [qaarCatalog.item_catalog_entries])

  const findingCatalogByCode = useMemo(() => {
    const lookup = new Map()
    ;(qaarCatalog.finding_catalog_entries || []).forEach((item) => {
      lookup.set(item.code_no, item)
    })
    return lookup
  }, [qaarCatalog.finding_catalog_entries])

  const degreeOptions = useMemo(
    () => qaarCatalog.ratings?.degree_of_defect_options || [],
    [qaarCatalog.ratings],
  )

  const unitOptions = useMemo(() => {
    const unitField = (qaarCatalog.report_summary_work_item_fields || []).find((field) => field.key === 'unit')
    return unitField?.options || []
  }, [qaarCatalog.report_summary_work_item_fields])

  const computedReportSummary = useMemo(
    () => computeQaarReportSummary(form.qaar_report_summary),
    [form.qaar_report_summary],
  )

  const computedWorkItemMetrics = useMemo(
    () => computeWorkItemMetrics(form.qaar_work_items),
    [form.qaar_work_items],
  )

  const computedFindingMetrics = useMemo(
    () => computeQualityFindingMetrics(
      form.qaar_work_findings,
      form.qaar_work_items,
      computedWorkItemMetrics,
      qaarCatalog.ratings || {},
    ),
    [computedWorkItemMetrics, form.qaar_work_findings, form.qaar_work_items, qaarCatalog.ratings],
  )

  const computedAssessmentRatings = useMemo(
    () => computeQaarAssessmentRatings({
      summary: form.qaar_report_summary,
      computedSummary: computedReportSummary,
      projectManagementChecks: form.qaar_project_management_checks,
      healthSafetyChecks: form.qaar_health_safety_checks,
      findingMetrics: computedFindingMetrics,
    }),
    [
      computedFindingMetrics,
      computedReportSummary,
      form.qaar_health_safety_checks,
      form.qaar_project_management_checks,
      form.qaar_report_summary,
    ],
  )

  const editingInspection = useMemo(
    () => (editingId ? inspections.find((row) => row.id === editingId) || null : null),
    [editingId, inspections],
  )

  const projectManagementCompletion = useMemo(
    () => checklistCompletion(form.qaar_project_management_checks),
    [form.qaar_project_management_checks],
  )
  const healthSafetyCompletion = useMemo(
    () => checklistCompletion(form.qaar_health_safety_checks),
    [form.qaar_health_safety_checks],
  )

  const sectionTabs = useMemo(() => {
    const items = [
      {
        id: 'record-details',
        label: 'Record details',
        icon: ClipboardList,
      },
    ]
    items.push({
      id: 'qaar-report-summary',
      label: 'Report summary',
      icon: ScrollText,
    })
    items.push({
      id: 'qaar-project-management',
      label: 'Project management',
      icon: ListChecks,
      badge: projectManagementCompletion.total
        ? `${projectManagementCompletion.answered}/${projectManagementCompletion.total}`
        : null,
    })
    items.push({
      id: 'qaar-quality-of-works',
      label: 'Quality of works',
      icon: Package,
    })
    items.push({
      id: 'qaar-health-safety',
      label: 'Health & safety',
      icon: HardHat,
      badge: healthSafetyCompletion.total
        ? `${healthSafetyCompletion.answered}/${healthSafetyCompletion.total}`
        : null,
    })
    if (editingId) {
      items.push({ id: 'generated-outputs', label: 'Generated PDFs', icon: FileText })
    }
    return items
  }, [
    projectManagementCompletion.answered,
    projectManagementCompletion.total,
    healthSafetyCompletion.answered,
    healthSafetyCompletion.total,
    editingId,
  ])

  useEffect(() => {
    if (!sectionTabs.length) return
    if (!sectionTabs.some((item) => item.id === activeSection)) {
      setActiveSection(sectionTabs[0].id)
    }
  }, [sectionTabs, activeSection])

  useEffect(() => {
    if (!formOpen) return
    setActiveSection('record-details')
  }, [formOpen])

  const handleSelectSection = (id) => {
    setActiveSection(id)
    if (typeof document !== 'undefined') {
      const target = document.getElementById(id)
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    }
  }

  const currentStepIndex = useMemo(() => {
    const idx = sectionTabs.findIndex((item) => item.id === activeSection)
    return idx >= 0 ? idx : 0
  }, [sectionTabs, activeSection])

  const isLastStep = currentStepIndex >= sectionTabs.length - 1

  const validateRecordDetails = useCallback(() => {
    const projectId = Number(form.project_id)
    if (!Number.isInteger(projectId) || projectId <= 0) {
      setError('Select an implementation-stage project before continuing.')
      return false
    }
    if (!String(form.inspection_date || '').trim()) {
      setError('Inspection date is required before continuing.')
      return false
    }
    return true
  }, [form.project_id, form.inspection_date])

  const handleNextStep = () => {
    if (sectionTabs[currentStepIndex]?.id === 'record-details' && !validateRecordDetails()) {
      return
    }
    setError('')
    const next = sectionTabs[currentStepIndex + 1]
    if (next) {
      handleSelectSection(next.id)
    }
  }

  const handlePreviousStep = () => {
    setError('')
    const previous = sectionTabs[currentStepIndex - 1]
    if (previous) {
      handleSelectSection(previous.id)
    }
  }


  if (!isInternalUser()) {
    return (
      <GlassPanel>
        <h1 className="page-title mb-2">Implementation Monitoring</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          This workspace is only available to internal DILG users involved in project monitoring.
        </p>
      </GlassPanel>
    )
  }

  const handleProjectChange = (projectId) => {
    const project = monitorableProjects.find((item) => Number(item.id) === Number(projectId))
    const profile = project?.monitoring_profile || {}
    const customFields = project?.custom_fields || {}
    setForm((current) => ({
      ...current,
      project_id: projectId,
      project_kind: profile.project_kind || project?.project_kind || '',
      monitoring_applicability: profile.monitoring_applicability || project?.monitoring_applicability || '',
      qaar_category: profile.qaar_category || project?.qaar_category || '',
      subaybayan_project_code: profile.subaybayan_project_code || project?.subaybayan_project_code || project?.source_project_code || '',
      subaybayan_url: profile.subaybayan_url || project?.subaybayan_url || '',
      nadai_received_at: profile.nadai_received_at || project?.nadai_received_at || '',
      subaybayan_enrolled_at: profile.subaybayan_enrolled_at || project?.subaybayan_enrolled_at || '',
      subaybayan_enrollment_status: profile.subaybayan_enrollment_status || project?.subaybayan_enrollment_status || '',
      qaar_report_summary: {
        ...current.qaar_report_summary,
        office_address: customFields.office_address || current.qaar_report_summary.office_address || '',
        region: normalizeQaarRegion(customFields.region || project?.region || current.qaar_report_summary.region),
        province: normalizeQaarProvince(customFields.province || project?.lgu_province || current.qaar_report_summary.province),
        project_id_text: profile.subaybayan_project_code || project?.subaybayan_project_code || project?.source_project_code || '',
        project_title: project?.project_name || current.qaar_report_summary.project_title || '',
        program_name: project?.program_name || current.qaar_report_summary.program_name || '',
        funded_year: project?.fiscal_year || current.qaar_report_summary.funded_year || '',
        city_municipality: normalizeQaarMunicipality(project) || current.qaar_report_summary.city_municipality || '',
        implementing_unit: implementingUnitForProject(project) || current.qaar_report_summary.implementing_unit || '',
        barangay: customFields.barangay || current.qaar_report_summary.barangay || '',
        monitoring_office: customFields.monitoring_office || current.qaar_report_summary.monitoring_office || 'PROVINCIAL OFFICE',
        national_subsidy: project?.budget_amount ?? current.qaar_report_summary.national_subsidy ?? '',
        project_location: customFields.location || project?.lgu_municipality || current.qaar_report_summary.project_location || '',
        project_description: customFields.project_description || customFields.description || current.qaar_report_summary.project_description || '',
        date_of_inspection_assessment: current.inspection_date || current.qaar_report_summary.date_of_inspection_assessment || '',
        actual_accomplishment_pct: project?.physical_completion_pct ?? current.qaar_report_summary.actual_accomplishment_pct ?? '',
        actual_project_status: normalizeQaarProjectStatus(project?.overall_status) || current.qaar_report_summary.actual_project_status || '',
        date_started: project?.actual_start_date || current.qaar_report_summary.date_started || '',
        target_completion_date: project?.target_end_date || current.qaar_report_summary.target_completion_date || '',
        contract_amount: project?.budget_amount ?? current.qaar_report_summary.contract_amount ?? '',
      },
    }))
  }

  const updateArrayItem = (field, index, patch) => {
    setForm((current) => ({
      ...current,
      [field]: current[field].map((item, itemIndex) => (
        itemIndex === index ? { ...item, ...patch } : item
      )),
    }))
  }

  const removeArrayItem = (field, index) => {
    setForm((current) => ({
      ...current,
      [field]: current[field].filter((_, itemIndex) => itemIndex !== index),
    }))
  }

  const updateNested = (field, patch) => {
    setForm((current) => ({
      ...current,
      [field]: {
        ...current[field],
        ...patch,
      },
    }))
  }

  const updateWorkItemCode = (index, value) => {
    const catalogItem = itemCatalogByCode.get(value)
    updateArrayItem('qaar_work_items', index, {
      item_code: value,
      description: catalogItem?.description || form.qaar_work_items[index]?.description || '',
      source_catalog_row: catalogItem?.source_row || '',
    })
  }

  const updateFindingCode = (index, value) => {
    const catalogItem = findingCatalogByCode.get(value)
    updateArrayItem('qaar_work_findings', index, {
      defect_code: value,
      defect_description: catalogItem?.finding || form.qaar_work_findings[index]?.defect_description || '',
      recommendation: catalogItem?.recommendation || form.qaar_work_findings[index]?.recommendation || '',
      quality_issue: catalogItem?.quality_issue || form.qaar_work_findings[index]?.quality_issue || '',
      source_catalog_row: catalogItem?.source_row || '',
    })
  }

  const submitForm = async ({ keepOpen = false, asDraft = false } = {}) => {
    setError('')
    setMessage('')
    const projectId = Number(form.project_id)
    const inspectionDate = String(form.inspection_date || '').trim()
    const physicalPct = parseOptionalPercentInput(form.physical_accomplishment_pct)
    if (!Number.isInteger(projectId) || projectId <= 0) {
      setError('Select a QAAR-applicable implementation-stage project.')
      return { ok: false }
    }
    if (!inspectionDate) {
      setError('Inspection date is required.')
      return { ok: false }
    }
    if (physicalPct.error) {
      setError(physicalPct.error)
      return { ok: false }
    }

    if (asDraft) {
      setSavingDraft(true)
    } else {
      setSubmitting(true)
    }

    try {
      const effectiveStatus = asDraft ? 'draft' : form.status
      const payload = {
        ...form,
        monitoring_type: 'qaar',
        status: effectiveStatus,
        project_id: projectId,
        inspection_date: inspectionDate,
        physical_accomplishment_pct: physicalPct.value,
        observation_summary: null,
        findings: null,
        recommendations: null,
        agreement_summary: null,
        issues_identified: null,
        aide_memoire_text: null,
        transmitted_at: form.transmitted_at || null,
        monthly_cycle_tag: form.monthly_cycle_tag || null,
        monthly_cycle_note: null,
        qaar_package: {
          report_summary: form.qaar_report_summary,
          project_management_checks: form.qaar_project_management_checks.filter(checkPayloadEntered),
          work_items: form.qaar_work_items.filter(workItemPayloadEntered),
          work_findings: form.qaar_work_findings.filter(workFindingPayloadEntered),
          health_safety_checks: form.qaar_health_safety_checks.filter(checkPayloadEntered),
        },
        subaybayan_verification: null,
        management_action: null,
      }

      const response = editingId
        ? await monitoringApi.updateInspection(editingId, payload)
        : await monitoringApi.createInspection(payload)

      const savedId = response?.data?.id || editingId

      if (asDraft) {
        setMessage('Draft saved. You can keep editing or come back later.')
      } else {
        setMessage(response.message || 'Monitoring record saved successfully.')
      }

      if (keepOpen) {
        if (asDraft) {
          setForm((current) => ({ ...current, status: 'draft' }))
        }
        if (savedId && savedId !== editingId) {
          setEditingId(savedId)
        }
        await loadPage()
      } else {
        setEditingId(null)
        setForm({
          ...EMPTY_FORM,
          project_id: form.project_id,
          ...buildQaarState(qaarCatalog),
        })
        setFormOpen(false)
        await loadPage()
      }
      return { ok: true, id: savedId }
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to save the monitoring record.')
      return { ok: false }
    } finally {
      if (asDraft) {
        setSavingDraft(false)
      } else {
        setSubmitting(false)
      }
    }
  }

  const handleSubmit = (event) => {
    event.preventDefault()
  }

  const handleFinalSubmit = () => {
    submitForm({ keepOpen: false, asDraft: false })
  }

  const handleSaveDraft = () => {
    submitForm({ keepOpen: true, asDraft: true })
  }

  const handleEdit = (inspection) => {
    const profile = inspection.monitoring_profile || {}
    const subay = inspection.subaybayan_verification || {}
    const action = inspection.management_actions?.[0] || {}
    setEditingId(inspection.id)
    setFormOpen(true)
    setMessage('')
    setError('')
    setForm({
      project_id: inspection.project_id,
      inspection_date: inspection.inspection_date || EMPTY_FORM.inspection_date,
      monitoring_type: 'qaar',
      physical_accomplishment_pct: inspection.physical_accomplishment_pct ?? '',
      observation_summary: inspection.observation_summary || '',
      findings: inspection.findings || '',
      recommendations: inspection.recommendations || '',
      agreement_summary: inspection.agreement_summary || '',
      issues_identified: inspection.issues_identified || '',
      is_site_visit: inspection.is_site_visit,
      aide_memoire_text: inspection.aide_memoire_text || '',
      annex_d_reference: inspection.annex_d_reference || '',
      transmittal_status: inspection.transmittal_status || 'not_required',
      transmittal_reference: inspection.transmittal_reference || '',
      transmitted_at: formatDateTimeInput(inspection.transmitted_at),
      monthly_cycle_tag: inspection.monthly_cycle_tag || '',
      monthly_cycle_note: inspection.monthly_cycle_note || '',
      project_kind: profile.project_kind || '',
      monitoring_applicability: profile.monitoring_applicability || '',
      qaar_category: profile.qaar_category || '',
      subaybayan_project_code: profile.subaybayan_project_code || '',
      subaybayan_url: profile.subaybayan_url || '',
      nadai_received_at: profile.nadai_received_at || '',
      subaybayan_enrolled_at: profile.subaybayan_enrolled_at || '',
      subaybayan_enrollment_status: profile.subaybayan_enrollment_status || '',
      ...buildQaarState(qaarCatalog, inspection.qaar_package || {}),
      subaybayan_verification: {
        cycle_month: subay.cycle_month || inspection.monthly_cycle_tag || '',
        lgu_encoded_status: subay.lgu_encoded_status || 'not_checked',
        ro_action_status: subay.ro_action_status || 'pending',
        status: subay.status || 'open',
        discrepancy_notes: subay.discrepancy_notes || '',
        observations: subay.observations || '',
      },
      management_action: {
        risk_level: action.risk_level || '',
        trigger_summary: action.trigger_summary || '',
        action_required: action.action_required || '',
        responsible_office: action.responsible_office || '',
        due_date: action.due_date || '',
        status: action.status || 'draft',
      },
      status: inspection.status || 'draft',
    })
  }

  const openCreateForm = () => {
    setEditingId(null)
    setMessage('')
    setError('')
    setForm({
      ...EMPTY_FORM,
      ...buildQaarState(qaarCatalog),
    })
    setFormOpen(true)
  }

  const closeForm = () => {
    setFormOpen(false)
    setEditingId(null)
    setError('')
    setForm({
      ...EMPTY_FORM,
      ...buildQaarState(qaarCatalog),
    })
  }

  const handleGenerateOutputs = async (inspection, options = {}) => {
    if (generatingId) return
    const outputTypes = Array.isArray(options.outputTypes) && options.outputTypes.length
      ? options.outputTypes
      : QAAR_OUTPUT_ORDER
    const isSingle = outputTypes.length === 1
    setError('')
    setMessage('')
    setGeneratingId(inspection.id)
    setGeneratingType(isSingle ? outputTypes[0] : 'all')
    try {
      const response = await monitoringApi.generateInspectionOutputs(inspection.id, {
        output_types: outputTypes,
      })
      const generatedCount = response.data?.filter((item) => item.file_object_id).length || 0
      const successText = isSingle
        ? `${QAAR_OUTPUT_LABELS[outputTypes[0]] || formatStatus(outputTypes[0])} regenerated successfully.`
        : (response.message || 'QAAR outputs generated successfully.')
      setMessage(`${successText} ${generatedCount} PDF file${generatedCount === 1 ? '' : 's'} ready.`)
      await loadPage()
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to generate QAAR outputs.')
    } finally {
      setGeneratingId(null)
      setGeneratingType(null)
    }
  }

  const handleDownloadOutput = async (output) => {
    if (!output?.id) return
    setError('')
    try {
      const response = await monitoringApi.downloadGeneratedOutput(output.id)
      const blob = new Blob([response.data], { type: response.headers['content-type'] || 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filenameFromDisposition(
        response.headers['content-disposition'],
        output.file?.filename || `${QAAR_OUTPUT_LABELS[output.output_type] || 'QAAR Output'}.pdf`,
      )
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to download the generated QAAR PDF.')
    }
  }

  const siteVisitCount = inspections.filter((inspection) => inspection.is_site_visit).length
  const flaggedCount = inspections.filter((inspection) => inspection.status === 'flagged').length
  const pendingTransmittalCount = inspections.filter((inspection) => inspection.transmittal_status === 'pending').length

  const columns = [
    { key: 'project_name', label: 'Project' },
    { key: 'lgu_name', label: 'LGU' },
    { key: 'status', label: 'Status', render: (row) => statusBadge(row.status) },
    { key: 'transmittal_status', label: 'Transmittal', render: (row) => transmittalBadge(row.transmittal_status) },
    { key: 'monthly_cycle_tag', label: 'Cycle', render: (row) => row.monthly_cycle_tag || '—' },
    { key: 'inspection_date', label: 'Date', render: (row) => formatDate(row.inspection_date) },
    {
      key: 'physical_accomplishment_pct',
      label: 'Physical %',
      render: (row) => row.physical_accomplishment_pct == null ? '—' : `${row.physical_accomplishment_pct}%`,
    },
    {
      key: 'actions',
      label: '',
      render: (row) => {
        const isGenerating = generatingId === row.id
        const readyCount = QAAR_OUTPUT_ORDER.reduce((count, type) => {
          const latest = latestOutputByType(row.generated_outputs || []).get(type)
          return latest?.file_object_id ? count + 1 : count
        }, 0)
        return (
          <div className="flex flex-wrap justify-end gap-2">
            <Button size="sm" variant="outline" onClick={() => handleEdit(row)} disabled={isGenerating}>
              Edit
            </Button>
            {row.monitoring_type === 'qaar' && (
              <Button
                size="sm"
                variant="outline"
                icon={FileText}
                loading={isGenerating}
                disabled={Boolean(generatingId) && !isGenerating}
                onClick={() => setReportsInspection(row)}
              >
                {isGenerating ? 'Generating…' : `Reports${readyCount ? ` (${readyCount})` : ''}`}
              </Button>
            )}
          </div>
        )
      },
    },
  ]

  const PAGE_MODULES = [
    { value: 'qaar', label: 'QAAR Monitoring', icon: ClipboardCheck },
    { value: 'monthly_progress', label: 'Monthly Progress Report', icon: ScrollText },
    { value: 'form3', label: 'Form 3', icon: FileText },
    { value: 'exception', label: 'Project Exception Report', icon: AlertTriangle },
    { value: 'non_infra', label: 'Non-Infra Monitoring', icon: Package },
    { value: 'beneficiary', label: 'Beneficiary Records', icon: HardHat },
    { value: 'vv_queue', label: 'V&V Queue', icon: ListChecks },
    { value: 'mar', label: 'Management Action Report', icon: Flag },
  ]

  const moduleTabs = (
    <div className="mb-6 flex flex-wrap gap-2 border-b border-brand-border pb-4" role="tablist" aria-label="Monitoring modules">
      {PAGE_MODULES.map((moduleTab) => {
        const Icon = moduleTab.icon
        const active = pageView === moduleTab.value
        return (
          <button
            key={moduleTab.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => setPageView(moduleTab.value)}
            className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              active
                ? 'bg-brand-primary/10 text-brand-primary ring-1 ring-brand-primary/30'
                : 'text-brand-text-muted hover:bg-brand-surface hover:text-brand-text'
            }`}
          >
            <Icon className="h-4 w-4" strokeWidth={1.8} aria-hidden="true" />
            {moduleTab.label}
          </button>
        )
      })}
    </div>
  )

  if (pageView === 'monthly_progress') {
    return (
      <div>
        {moduleTabs}
        <MonthlyProgressPanel projects={projects} />
      </div>
    )
  }

  if (pageView === 'form3') {
    return (
      <div>
        {moduleTabs}
        <Form3Panel projects={projects} />
      </div>
    )
  }

  if (pageView === 'exception') {
    return (
      <div>
        {moduleTabs}
        <ProjectExceptionPanel projects={projects} />
      </div>
    )
  }

  if (pageView === 'non_infra') {
    return (
      <div>
        {moduleTabs}
        <NonInfraMonitoringPanel projects={projects} />
      </div>
    )
  }

  if (pageView === 'beneficiary') {
    return (
      <div>
        {moduleTabs}
        <BeneficiaryEvidencePanel projects={projects} />
      </div>
    )
  }

  if (pageView === 'vv_queue') {
    return (
      <div>
        {moduleTabs}
        <WorkflowQueuePanel />
      </div>
    )
  }

  if (pageView === 'mar') {
    return (
      <div>
        {moduleTabs}
        <ManagementActionPanel projects={projects} />
      </div>
    )
  }

  return (
    <div>
      {moduleTabs}
      <PageHeader
        title="Implementation Monitoring"
        description="Record QAAR monitoring for projects already under implementation and generate the official QAAR, Aide Memoire, and Notice PDF outputs from the saved record."
        actions={(
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={loadPage}>Refresh</Button>
            <Button size="sm" icon={Plus} onClick={openCreateForm}>Record QAAR</Button>
          </div>
        )}
      />

      <FeedbackToast type="success" message={message} onDismiss={() => setMessage('')} />
      <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>
        {error}
      </InlineAlert>

      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-5">
        <KpiCard title="Records" value={meta.total || inspections.length} subtitle="monitored" icon={ClipboardCheck} color="blue" />
        <KpiCard title="Projects" value={monitorableProjects.length} subtitle="QAAR-applicable" icon={Workflow} color="blue" />
        <KpiCard title="Site visits" value={siteVisitCount} subtitle="logged" icon={MapPinned} color="emerald" />
        <KpiCard title="Pending" value={pendingTransmittalCount} subtitle="transmittal" icon={Send} color="amber" />
        <KpiCard title="Flagged" value={flaggedCount} subtitle="needs review" icon={Flag} color="red" />
      </div>

      <div className="mb-4 flex flex-wrap gap-3">
        <div className="relative min-w-[260px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-brand-text-muted" strokeWidth={1.5} />
          <input
            id="monitoring-search"
            className="input-field pl-10"
            placeholder="Project, LGU, or QAAR reference"
            value={filters.search}
            onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))}
            aria-label="Search monitoring records"
          />
        </div>
        <select
          id="monitoring-status-filter"
          className="input-field w-auto min-w-[150px]"
          value={filters.status}
          onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="submitted">Submitted</option>
          <option value="reviewed">Reviewed</option>
          <option value="approved">Approved</option>
          <option value="flagged">Flagged</option>
        </select>
        <select
          id="monitoring-transmittal-filter"
          className="input-field w-auto min-w-[180px]"
          value={filters.transmittal_status}
          onChange={(event) => setFilters((current) => ({ ...current, transmittal_status: event.target.value }))}
          aria-label="Filter by transmittal"
        >
          <option value="">All transmittals</option>
          {TRANSMITTAL_STATUSES.map((status) => (
            <option key={status.value} value={status.value}>{status.label}</option>
          ))}
        </select>
        <label className="min-w-[190px] text-xs text-brand-text-muted" htmlFor="monitoring-cycle-filter">
          Cycle month
        <input
          id="monitoring-cycle-filter"
          className="input-field mt-1 min-w-[190px]"
          type="month"
          value={filters.monthly_cycle_tag}
          onChange={(event) => setFilters((current) => ({ ...current, monthly_cycle_tag: event.target.value }))}
          aria-label="Filter by cycle"
        />
        </label>
        <Button variant="outline" onClick={loadPage} className="self-center">Apply Filters</Button>
      </div>

      <Modal
        open={formOpen}
        title={editingId ? 'Edit QAAR monitoring record' : 'Record QAAR monitoring'}
        description="Complete the QAAR details you have now, then save a draft or submit the record when it is ready."
        size="xl"
        onClose={closeForm}
      >
        <form onSubmit={handleSubmit} className="space-y-5">
          <InlineAlert type="error" onDismiss={() => setError('')}>
            {error}
          </InlineAlert>

          <SectionTabs items={sectionTabs} activeId={activeSection} onSelect={handleSelectSection} />

          {activeSection === 'record-details' && (
          <SectionCard
            id="record-details"
            eyebrow="Step 1"
            title="Record details"
            description="Select the project, inspection date, and current status for this QAAR record."
          >
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <FormField id="monitoring-project" label="Project" className="md:col-span-2" required>
                <select
                  id="monitoring-project"
                  className="input-field"
                  value={form.project_id}
                  onChange={(event) => handleProjectChange(event.target.value)}
                  required
                >
                  <option value="">Select QAAR-applicable project</option>
                  {monitorableProjects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.project_name} ({formatMachineLabel(project.current_phase)})
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField id="monitoring-inspection-date" label="Inspection date" required>
                <input
                  id="monitoring-inspection-date"
                  className="input-field"
                  type="date"
                  value={form.inspection_date}
                  onChange={(event) => setForm((current) => ({ ...current, inspection_date: event.target.value }))}
                  required
                />
              </FormField>
              <FormField id="monitoring-type" label="Monitoring report">
                <div
                  id="monitoring-type"
                  className="input-field flex min-h-10 items-center text-sm font-medium text-brand-text"
                  role="status"
                >
                  QAAR Monitoring
                </div>
              </FormField>
              <FormField id="monitoring-physical-pct" label="Physical accomplishment %">
                <input
                  id="monitoring-physical-pct"
                  className="input-field"
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  value={form.physical_accomplishment_pct}
                  onChange={(event) => setForm((current) => ({ ...current, physical_accomplishment_pct: event.target.value }))}
                />
              </FormField>
              <FormField id="monitoring-status" label="Record status">
                <select
                  id="monitoring-status"
                  className="input-field"
                  value={form.status}
                  onChange={(event) => setForm((current) => ({ ...current, status: event.target.value }))}
                >
                  <option value="draft">Draft</option>
                  <option value="submitted">Submitted</option>
                  <option value="reviewed">Reviewed</option>
                  <option value="approved">Approved</option>
                  <option value="flagged">Flagged</option>
                </select>
              </FormField>
              <FormField id="monitoring-monthly-cycle" label="Monthly cycle">
                <input
                  id="monitoring-monthly-cycle"
                  className="input-field"
                  type="month"
                  value={form.monthly_cycle_tag}
                  onChange={(event) => setForm((current) => ({ ...current, monthly_cycle_tag: event.target.value }))}
                />
              </FormField>
            </div>

            <details className="rounded-md border border-brand-border bg-brand-surface px-3 py-2">
              <summary className="cursor-pointer select-none text-xs font-semibold uppercase tracking-wide text-brand-text-muted">
                QAAR & transmittal details
              </summary>
              <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-3">
                <FormField id="monitoring-annex-reference" label="QAAR reference">
                  <input
                    id="monitoring-annex-reference"
                    className="input-field"
                    value={form.annex_d_reference}
                    onChange={(event) => setForm((current) => ({ ...current, annex_d_reference: event.target.value }))}
                  />
                </FormField>
                <FormField id="monitoring-transmittal-status" label="Transmittal status">
                  <select
                    id="monitoring-transmittal-status"
                    className="input-field"
                    value={form.transmittal_status}
                    onChange={(event) => setForm((current) => ({ ...current, transmittal_status: event.target.value }))}
                  >
                    {TRANSMITTAL_STATUSES.map((status) => (
                      <option key={status.value} value={status.value}>{status.label}</option>
                    ))}
                  </select>
                </FormField>
                <FormField id="monitoring-transmittal-reference" label="Transmittal reference">
                  <input
                    id="monitoring-transmittal-reference"
                    className="input-field"
                    value={form.transmittal_reference}
                    onChange={(event) => setForm((current) => ({ ...current, transmittal_reference: event.target.value }))}
                  />
                </FormField>
                <FormField id="monitoring-transmitted-at" label="Transmitted at">
                  <input
                    id="monitoring-transmitted-at"
                    className="input-field"
                    type="datetime-local"
                    value={form.transmitted_at}
                    onChange={(event) => setForm((current) => ({ ...current, transmitted_at: event.target.value }))}
                  />
                </FormField>
              </div>
            </details>

            <label className="inline-flex items-center gap-2 text-sm text-brand-text">
              <input
                type="checkbox"
                checked={form.is_site_visit}
                onChange={(event) => setForm((current) => ({ ...current, is_site_visit: event.target.checked }))}
              />
              Site visit conducted
            </label>
          </SectionCard>
          )}

          <>
              {activeSection === 'qaar-report-summary' && (
              <SectionCard
                id="qaar-report-summary"
                eyebrow="QAAR Monitoring"
                title="Project profile, schedule, and contract"
                description="Review the project details, schedule, accomplishment, and contract amounts that will appear in the monitoring report."
                action={(
                  <span className="inline-flex items-center gap-1 rounded-full bg-brand-surface px-2 py-0.5 text-[11px] font-semibold text-brand-text-muted">
                    <Sparkles className="h-3 w-3" strokeWidth={1.8} aria-hidden="true" />
                    Filled from project
                  </span>
                )}
              >
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  {(qaarCatalog.report_summary_fields || [])
                    .filter((field) => field.input_type !== 'computed')
                    .map((field) => {
                      const fieldValue = form.qaar_report_summary[field.key] || ''
                      const selectOptions = reportSummarySelectOptions(field, fieldValue)
                      return (
                        <FormField
                          key={field.key}
                          id={`qaar-summary-${field.key}`}
                          label={field.label}
                          hint={field.hint}
                          className={field.input_type === 'textarea' ? 'md:col-span-3' : ''}
                        >
                          {selectOptions ? (
                            <select
                              id={`qaar-summary-${field.key}`}
                              className="input-field"
                              value={fieldValue}
                              onChange={(event) => updateNested('qaar_report_summary', { [field.key]: event.target.value })}
                            >
                              {selectOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                            </select>
                          ) : field.input_type === 'textarea' ? (
                            <textarea
                              id={`qaar-summary-${field.key}`}
                              className="input-field min-h-[72px]"
                              value={fieldValue}
                              onChange={(event) => updateNested('qaar_report_summary', { [field.key]: event.target.value })}
                            />
                          ) : QAAR_AMOUNT_KEYS.has(field.key) ? (
                            <AmountInput
                              id={`qaar-summary-${field.key}`}
                              className="input-field"
                              value={fieldValue}
                              onChange={(event) => updateNested('qaar_report_summary', { [field.key]: event.target.value })}
                            />
                          ) : (
                            <input
                              id={`qaar-summary-${field.key}`}
                              className="input-field"
                              type={field.input_type === 'number' || field.input_type === 'date' ? field.input_type : 'text'}
                              step={field.input_type === 'number' ? '0.01' : undefined}
                              value={fieldValue}
                              onChange={(event) => updateNested('qaar_report_summary', { [field.key]: event.target.value })}
                            />
                          )}
                        </FormField>
                      )
                    })}
                </div>

                {/* Hidden fields keep computed IDs in the DOM for external tests and anchor links. */}
                <div className="sr-only" aria-hidden="true">
                  {(qaarCatalog.report_summary_fields || [])
                    .filter((field) => field.input_type === 'computed')
                    .map((field) => (
                      <input
                        key={field.key}
                        id={`qaar-summary-${field.key}`}
                        readOnly
                        tabIndex={-1}
                        value={computedReportSummary[field.key] || form.qaar_report_summary[field.key] || ''}
                      />
                    ))}
                </div>

                <ComputedStrip
                  items={(qaarCatalog.report_summary_fields || [])
                    .filter((field) => field.input_type === 'computed')
                    .map((field) => ({
                      label: field.label,
                      value: computedReportSummary[field.key] || form.qaar_report_summary[field.key] || '',
                    }))}
                />

                <div className="overflow-hidden rounded-md border border-brand-border">
                  <div className="border-b border-brand-border bg-brand-surface px-3 py-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-brand-text">
                      Assessment rating
                    </h4>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-brand-border text-sm">
                      <thead className="bg-brand-surface">
                        <tr>
                          <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-brand-text-muted">Component</th>
                          <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-brand-text-muted">Rating</th>
                          <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-brand-text-muted">Risk level</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-brand-border">
                        {computedAssessmentRatings.qualityRows.map((row) => (
                          <tr key={row.label}>
                            <td className="px-3 py-2 text-brand-text">{row.label}</td>
                            <td className="px-3 py-2 font-medium text-brand-text">{formatComputedPercent(row.value)}</td>
                            <td className="px-3 py-2 text-brand-text">{row.risk}</td>
                          </tr>
                        ))}
                        <tr>
                          <td className="px-3 py-2 text-brand-text">
                            <div>Timeliness 40%</div>
                            <div className="mt-1 text-xs text-brand-text-muted">
                              Planned/target {formatPercentValue(computedAssessmentRatings.timeliness.plannedTarget)};
                              {' '}
                              Actual {formatPercentValue(computedAssessmentRatings.timeliness.actual)};
                              {' '}
                              Variance {formatPercentValue(computedAssessmentRatings.timeliness.variance)}
                            </div>
                            {computedAssessmentRatings.timeliness.note && (
                              <div className="mt-1 text-xs text-brand-text-muted">
                                {computedAssessmentRatings.timeliness.note}
                              </div>
                            )}
                          </td>
                          <td className="px-3 py-2 font-medium text-brand-text">{formatComputedPercent(computedAssessmentRatings.timeliness.value)}</td>
                          <td className="px-3 py-2 text-brand-text">{computedAssessmentRatings.timeliness.risk}</td>
                        </tr>
                        <tr>
                          <td className="px-3 py-2 text-brand-text">To Date Assessment Rating</td>
                          <td className="px-3 py-2 font-medium text-brand-text">{formatComputedPercent(computedAssessmentRatings.toDate.value)}</td>
                          <td className="px-3 py-2 text-brand-text">{computedAssessmentRatings.toDate.risk}</td>
                        </tr>
                        <tr>
                          <td className="px-3 py-2 text-brand-text">Assessment Rating for Safety and Health</td>
                          <td className="px-3 py-2 font-medium text-brand-text">{formatComputedPercent(computedAssessmentRatings.healthSafety.value)}</td>
                          <td className="px-3 py-2 text-brand-text">{computedAssessmentRatings.healthSafety.risk}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </SectionCard>
              )}

              {activeSection === 'qaar-project-management' && (
              <SectionCard
                id="qaar-project-management"
                eyebrow="QAAR Monitoring"
                title={`Project Management checklist (${projectManagementCompletion.answered}/${projectManagementCompletion.total} answered)`}
                description="Check the documents, permits, site records, and project controls observed during monitoring."
              >
                <QaarChecklist
                  field="qaar_project_management_checks"
                  checks={form.qaar_project_management_checks}
                  updateArrayItem={updateArrayItem}
                />
              </SectionCard>
              )}

              {activeSection === 'qaar-quality-of-works' && (
              <SectionCard
                id="qaar-quality-of-works"
                eyebrow="QAAR Monitoring"
                title="Inspected items, findings & recommendations"
                description="List the inspected work items, then record defects, recommendations, timelines, and remarks for each finding."
              >
                <datalist id="qaar-item-codes">
                  {itemCatalogOptions.map((catalogItem) => (
                    <option key={`${catalogItem.item_code}-${catalogItem.source_row}`} value={catalogItem.item_code}>
                      {catalogItem.description}
                    </option>
                  ))}
                </datalist>
                <datalist id="qaar-finding-codes">
                  {findingCatalogOptions.map((catalogItem) => (
                    <option key={`${catalogItem.code_no}-${catalogItem.source_row}`} value={catalogItem.code_no}>
                      {catalogItem.finding}
                    </option>
                  ))}
                </datalist>

                <div>
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <div>
                      <h4 className="text-sm font-semibold text-brand-text">Item description</h4>
                      <p className="text-xs text-brand-text-muted">
                        Choose an item code when available, or enter the item details manually.
                      </p>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      icon={Plus}
                      onClick={() => setForm((current) => ({ ...current, qaar_work_items: [...current.qaar_work_items, emptyWorkItem()] }))}
                    >
                      Add item
                    </Button>
                  </div>
                  {form.qaar_work_items.length === 0 ? (
                    <p className="rounded-md border border-dashed border-brand-border px-3 py-6 text-center text-sm text-brand-text-muted">
                      No inspected items yet. Add your first item to start scoring.
                    </p>
                  ) : (
                    <div className="space-y-3">
                      {form.qaar_work_items.map((item, index) => (
                        <div
                          key={`work-item-${index}`}
                          className="rounded-md border border-brand-border bg-brand-surface"
                        >
                          <div className="flex items-center justify-between gap-2 border-b border-brand-border bg-brand-surface-solid px-3 py-2">
                            <div className="flex min-w-0 items-center gap-2">
                              <Hash className="h-3.5 w-3.5 text-brand-text-muted" strokeWidth={1.8} aria-hidden="true" />
                              <span className="truncate text-sm font-semibold text-brand-text">
                                Item #{index + 1}{item.item_code ? ` · ${item.item_code}` : ''}
                              </span>
                            </div>
                            {form.qaar_work_items.length > 1 && (
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                icon={Trash2}
                                onClick={() => removeArrayItem('qaar_work_items', index)}
                              >
                                Remove
                              </Button>
                            )}
                          </div>
                          <div className="grid grid-cols-1 gap-3 p-3 md:grid-cols-6">
                            <FormField id={`item-code-${index}`} label="Item code">
                              <input
                                id={`item-code-${index}`}
                                className="input-field"
                                list="qaar-item-codes"
                                value={item.item_code || ''}
                                onChange={(event) => updateWorkItemCode(index, event.target.value)}
                              />
                            </FormField>
                            <FormField id={`item-desc-${index}`} label="Description" className="md:col-span-3">
                              <input
                                id={`item-desc-${index}`}
                                className="input-field"
                                value={item.description || ''}
                                onChange={(event) => updateArrayItem('qaar_work_items', index, { description: event.target.value })}
                              />
                            </FormField>
                            <FormField id={`item-unit-${index}`} label="Unit">
                              <select
                                id={`item-unit-${index}`}
                                className="input-field"
                                value={item.unit || ''}
                                onChange={(event) => updateArrayItem('qaar_work_items', index, { unit: event.target.value })}
                              >
                                <option value="">Blank</option>
                                {unitOptions.map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                                {item.unit && !unitOptions.some((option) => option.value === item.unit) && (
                                  <option value={item.unit}>{item.unit}</option>
                                )}
                              </select>
                            </FormField>
                            <FormField id={`item-location-${index}`} label="Location">
                              <input
                                id={`item-location-${index}`}
                                className="input-field"
                                value={item.location || ''}
                                onChange={(event) => updateArrayItem('qaar_work_items', index, { location: event.target.value })}
                              />
                            </FormField>
                            <FormField id={`item-qty-${index}`} label="Quantity">
                              <input
                                id={`item-qty-${index}`}
                                className="input-field"
                                type="number"
                                value={item.quantity || ''}
                                onChange={(event) => updateArrayItem('qaar_work_items', index, { quantity: event.target.value })}
                              />
                            </FormField>
                            <FormField id={`item-inspected-${index}`} label="Inspected quantity">
                              <input
                                id={`item-inspected-${index}`}
                                className="input-field"
                                type="number"
                                value={item.inspected_quantity || ''}
                                onChange={(event) => updateArrayItem('qaar_work_items', index, { inspected_quantity: event.target.value })}
                              />
                            </FormField>
                            <FormField id={`item-unit-cost-${index}`} label="Unit cost">
                              <AmountInput
                                id={`item-unit-cost-${index}`}
                                className="input-field"
                                placeholder="0.00"
                                value={item.unit_cost || ''}
                                onChange={(event) => updateArrayItem('qaar_work_items', index, { unit_cost: event.target.value })}
                              />
                            </FormField>
                            <div className="md:col-span-3">
                              <ComputedStrip
                                items={[
                                  {
                                    label: 'Cost',
                                    value: formatComputedNumber(computedWorkItemMetrics[index]?.computedCost, 2),
                                  },
                                  {
                                    label: 'Weight',
                                    value: formatComputedPercent(computedWorkItemMetrics[index]?.computedWeight),
                                  },
                                ]}
                              />
                              {/* Hidden inputs preserve original computed-field IDs */}
                              <div className="sr-only" aria-hidden="true">
                                <input
                                  id={`item-cost-${index}`}
                                  readOnly
                                  tabIndex={-1}
                                  value={formatComputedNumber(computedWorkItemMetrics[index]?.computedCost, 2)}
                                />
                                <input
                                  id={`item-weight-${index}`}
                                  readOnly
                                  tabIndex={-1}
                                  value={formatComputedPercent(computedWorkItemMetrics[index]?.computedWeight)}
                                />
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <div>
                      <h4 className="text-sm font-semibold text-brand-text">Findings & recommendations</h4>
                      <p className="text-xs text-brand-text-muted">
                        Link each finding to an inspected item, then add the defect, recommendation, timeline, and remarks.
                      </p>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      icon={Plus}
                      onClick={() => setForm((current) => ({ ...current, qaar_work_findings: [...current.qaar_work_findings, emptyFinding()] }))}
                    >
                      Add finding
                    </Button>
                  </div>
                  {form.qaar_work_findings.length === 0 ? (
                    <p className="rounded-md border border-dashed border-brand-border px-3 py-6 text-center text-sm text-brand-text-muted">
                      No findings recorded. Add a finding once you have an inspected item.
                    </p>
                  ) : (
                    <div className="space-y-3">
                      {form.qaar_work_findings.map((item, index) => {
                        const metrics = computedFindingMetrics[index] || {}
                        return (
                          <div
                            key={`finding-${index}`}
                            className="rounded-md border border-brand-border bg-brand-surface"
                          >
                            <div className="flex items-center justify-between gap-2 border-b border-brand-border bg-brand-surface-solid px-3 py-2">
                              <div className="flex min-w-0 items-center gap-2">
                                <AlertTriangle className="h-3.5 w-3.5 text-amber-500" strokeWidth={1.8} aria-hidden="true" />
                                <span className="truncate text-sm font-semibold text-brand-text">
                                  Finding #{index + 1}
                                  {item.work_item_index ? ` · references item #${item.work_item_index}` : ''}
                                  {item.defect_code ? ` · ${item.defect_code}` : ''}
                                </span>
                              </div>
                              {form.qaar_work_findings.length > 1 && (
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="ghost"
                                  icon={Trash2}
                                  onClick={() => removeArrayItem('qaar_work_findings', index)}
                                >
                                  Remove
                                </Button>
                              )}
                            </div>
                            <div className="space-y-3 p-3">
                              <div className="grid grid-cols-1 gap-3 md:grid-cols-6">
                                <FormField id={`finding-item-${index}`} label="Inspected item no.">
                                  <input
                                    id={`finding-item-${index}`}
                                    className="input-field"
                                    type="number"
                                    min="1"
                                    value={item.work_item_index || ''}
                                    onChange={(event) => updateArrayItem('qaar_work_findings', index, { work_item_index: event.target.value })}
                                  />
                                </FormField>
                                <FormField id={`finding-code-${index}`} label="Code no.">
                                  <input
                                    id={`finding-code-${index}`}
                                    className="input-field"
                                    list="qaar-finding-codes"
                                    value={item.defect_code || ''}
                                    onChange={(event) => updateFindingCode(index, event.target.value)}
                                  />
                                </FormField>
                                <FormField id={`finding-location-${index}`} label="Location / landmark" className="md:col-span-2">
                                  <input
                                    id={`finding-location-${index}`}
                                    className="input-field"
                                    value={item.location || ''}
                                    onChange={(event) => updateArrayItem('qaar_work_findings', index, { location: event.target.value })}
                                  />
                                </FormField>
                                <FormField id={`finding-defect-${index}`} label="Type of defect / damage" className="md:col-span-2">
                                  <input
                                    id={`finding-defect-${index}`}
                                    className="input-field"
                                    value={item.defect_description || ''}
                                    onChange={(event) => updateArrayItem('qaar_work_findings', index, { defect_description: event.target.value })}
                                  />
                                </FormField>
                                <FormField id={`finding-quality-${index}`} label="Quality issue" className="md:col-span-3">
                                  <input
                                    id={`finding-quality-${index}`}
                                    className="input-field"
                                    value={item.quality_issue || ''}
                                    onChange={(event) => updateArrayItem('qaar_work_findings', index, { quality_issue: event.target.value })}
                                  />
                                </FormField>
                                <FormField id={`finding-degree-${index}`} label="Degree of defect">
                                  <select
                                    id={`finding-degree-${index}`}
                                    className="input-field"
                                    value={item.degree_of_defect || ''}
                                    onChange={(event) => {
                                      const rating = degreeOptions.find((option) => option.value === event.target.value)
                                      updateArrayItem('qaar_work_findings', index, {
                                        degree_of_defect: event.target.value,
                                        rating_weight: rating?.rating_per_degree ?? '',
                                      })
                                    }}
                                  >
                                    <option value="">Blank</option>
                                    {degreeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                                  </select>
                                </FormField>
                                <FormField id={`finding-recommendation-${index}`} label="Recommendation" className="md:col-span-2">
                                  <input
                                    id={`finding-recommendation-${index}`}
                                    className="input-field"
                                    value={item.recommendation || ''}
                                    onChange={(event) => updateArrayItem('qaar_work_findings', index, { recommendation: event.target.value })}
                                  />
                                </FormField>
                                <FormField id={`finding-timeline-${index}`} label="Timeline">
                                  <input
                                    id={`finding-timeline-${index}`}
                                    className="input-field"
                                    value={item.timeline || ''}
                                    onChange={(event) => updateArrayItem('qaar_work_findings', index, { timeline: event.target.value })}
                                  />
                                </FormField>
                                <FormField id={`finding-remarks-${index}`} label="Remarks" className="md:col-span-3">
                                  <input
                                    id={`finding-remarks-${index}`}
                                    className="input-field"
                                    value={item.remarks || ''}
                                    onChange={(event) => updateArrayItem('qaar_work_findings', index, { remarks: event.target.value })}
                                  />
                                </FormField>
                              </div>

                              <ComputedStrip
                                items={[
                                  { label: 'Item description', value: metrics.description || '' },
                                  { label: 'Unit', value: metrics.unit || '' },
                                  { label: 'Item weight', value: formatComputedPercent(metrics.weight) },
                                  { label: 'Rating per degree', value: item.rating_weight ? String(item.rating_weight) : '' },
                                  { label: 'Total rating', value: formatComputedNumber(metrics.totalRating, 6) },
                                ]}
                              />

                              {/* Hidden inputs preserve original computed-field IDs */}
                              <div className="sr-only" aria-hidden="true">
                                <input
                                  id={`finding-unit-${index}`}
                                  readOnly
                                  tabIndex={-1}
                                  value={metrics.unit || ''}
                                />
                                <input
                                  id={`finding-desc-${index}`}
                                  readOnly
                                  tabIndex={-1}
                                  value={metrics.description || ''}
                                />
                                <input
                                  id={`finding-weight-${index}`}
                                  readOnly
                                  tabIndex={-1}
                                  value={formatComputedPercent(metrics.weight)}
                                />
                                <input
                                  id={`finding-rating-${index}`}
                                  readOnly
                                  tabIndex={-1}
                                  value={item.rating_weight || ''}
                                />
                                <input
                                  id={`finding-total-rating-${index}`}
                                  readOnly
                                  tabIndex={-1}
                                  value={formatComputedNumber(metrics.totalRating, 6)}
                                />
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              </SectionCard>
              )}

              {activeSection === 'qaar-health-safety' && (
              <SectionCard
                id="qaar-health-safety"
                eyebrow="QAAR Monitoring"
                title={`Health and Safety checklist (${healthSafetyCompletion.answered}/${healthSafetyCompletion.total} answered)`}
                description="Review safety practices, site controls, protective equipment, and worker health measures observed during monitoring."
              >
                <QaarChecklist
                  field="qaar_health_safety_checks"
                  checks={form.qaar_health_safety_checks}
                  updateArrayItem={updateArrayItem}
                />
              </SectionCard>
              )}
          </>

          {editingId && activeSection === 'generated-outputs' && (
            <SectionCard
              id="generated-outputs"
              eyebrow="Generated"
              title="QAAR PDFs"
              description="Create the monitoring report files for this record. Saved files can be downloaded again later."
              action={(
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  icon={FileDown}
                  onClick={() => handleGenerateOutputs(editingInspection)}
                >
                  Generate PDFs
                </Button>
              )}
            >
              <GeneratedOutputsPanel
                outputs={editingInspection?.generated_outputs}
                onDownload={handleDownloadOutput}
              />
            </SectionCard>
          )}

          <div className="sticky bottom-0 -mx-1 flex flex-wrap items-center justify-between gap-3 border-t border-brand-border bg-brand-surface-solid/95 px-1 pt-3 backdrop-blur">
            <div className="flex min-w-0 flex-col gap-0.5 text-xs text-brand-text-muted">
              <span className="font-semibold uppercase tracking-wide">
                Step {Math.max(currentStepIndex + 1, 1)} of {Math.max(sectionTabs.length, 1)}
              </span>
              <span className="truncate text-sm font-medium text-brand-text">
                {sectionTabs[currentStepIndex]?.label || 'Record details'}
              </span>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={closeForm}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={handlePreviousStep}
                disabled={currentStepIndex <= 0 || submitting || savingDraft}
                icon={ChevronLeft}
              >
                Previous
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={handleSaveDraft}
                loading={savingDraft}
                disabled={submitting}
                icon={Save}
              >
                Save draft
              </Button>
              {isLastStep ? (
                <Button
                  type="button"
                  onClick={handleFinalSubmit}
                  loading={submitting}
                  disabled={savingDraft}
                  icon={CheckCircle2}
                >
                  {editingId ? 'Update monitoring record' : 'Save monitoring record'}
                </Button>
              ) : (
                <Button
                  type="button"
                  onClick={handleNextStep}
                  disabled={submitting || savingDraft}
                >
                  Next
                  <ChevronRight strokeWidth={1.7} className="h-4 w-4" aria-hidden="true" />
                </Button>
              )}
            </div>
          </div>
        </form>
      </Modal>

      <GlassPanel noPadding>
        <DataTable
          columns={columns}
          data={inspections}
          keyField="id"
          isLoading={loading}
          emptyMessage="No implementation monitoring records have been captured yet."
          caption="Implementation monitoring records"
          density="compact"
        />
      </GlassPanel>

      <ReportsModal
        key={reportsInspection?.id || 'reports-modal-closed'}
        inspection={reportsInspection}
        onClose={() => {
          if (generatingId) return
          setReportsInspection(null)
        }}
        onGenerate={handleGenerateOutputs}
        onDownload={handleDownloadOutput}
        generatingId={generatingId}
        generatingType={generatingType}
      />
    </div>
  )
}
