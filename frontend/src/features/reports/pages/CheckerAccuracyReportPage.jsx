import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Download,
  FileSearch,
  GitBranch,
  MapPinned,
  RefreshCw,
  ScanText,
  ShieldAlert,
  Target,
  Users,
} from 'lucide-react'
import { Button, DataTable, GlassPanel, InlineAlert, KpiCard, PageHeader } from '../../../components'
import { formatMachineLabel } from '../../../lib/formatters'
import { badgeClassForStatus, badgeClassForTone } from '../../../lib/statusStyles'
import * as reportsApi from '../api/reportsApi'

function formatPercent(value, fallback = 'Not measured') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return fallback
  return `${(Number(value) * 100).toFixed(1)}%`
}

function formatCount(value, fallback = '0') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return fallback
  return new Intl.NumberFormat('en-US').format(Number(value))
}

function formatDateTime(value) {
  if (!value) return 'Not recorded'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Not recorded'
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatGateStatus(status) {
  if (status === 'not_enough_cases') return 'Not enough cases'
  if (status === 'not_applicable') return 'Not applicable'
  return formatMachineLabel(status)
}

function gateTone(status) {
  if (status === 'passed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'warning' || status === 'not_enough_cases') return 'warning'
  return 'neutral'
}

function metricValue(snapshot, key) {
  return snapshot?.metrics?.[key]
}

function nestedMetric(metrics, path, fallbackKey) {
  const value = path.reduce((current, key) => current?.[key], metrics)
  if (value !== null && value !== undefined) return value
  return fallbackKey ? metrics?.[fallbackKey] : value
}

function passRate(snapshot) {
  const metrics = snapshot?.metrics || {}
  if (metrics.pass_rate !== null && metrics.pass_rate !== undefined) return metrics.pass_rate
  const total = Number(metrics.total_cases || 0)
  if (!total) return null
  return Number(metrics.passed_cases || 0) / total
}

function gateHealth(snapshot) {
  const gates = snapshot?.gates || []
  const passed = gates.filter((gate) => String(gate.status || '').toLowerCase() === 'passed').length
  return gates.length ? `${formatCount(passed)}/${formatCount(gates.length)}` : 'No gates'
}

function downloadTextFile({ content, contentType, filename }) {
  const blob = new Blob([content || ''], { type: contentType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function AccuracyGateList({ gates = [] }) {
  if (!gates.length) {
    return (
      <div className="rounded-lg border border-brand-border bg-brand-surface p-4 text-sm text-brand-text-muted">
        No accuracy gates have been calculated yet.
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {gates.map((gate, index) => (
        <div key={gate.id || gate.key || `${gate.label}-${index}`} className="rounded-lg border border-brand-border bg-brand-surface p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-brand-text">{gate.label}</p>
              <p className="mt-1 text-xs text-brand-text-muted">{gate.message}</p>
            </div>
            <span className={badgeClassForTone(gateTone(gate.status))}>
              {formatGateStatus(gate.status)}
            </span>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-2 text-xs text-brand-text-muted sm:grid-cols-3">
            <span>Actual: {gate.actual === null || gate.actual === undefined ? 'Not measured' : formatPercent(gate.actual)}</span>
            <span>Target: {gate.target || 'Not set'}</span>
            <span>Support: {formatCount(gate.support)} case(s)</span>
          </div>
        </div>
      ))}
    </div>
  )
}

function ReviewerFeedback({ feedback }) {
  const total = feedback?.total_reviewer_decisions || 0
  if (!total) {
    return (
      <div className="rounded-lg border border-brand-border bg-brand-surface p-4 text-sm text-brand-text-muted">
        Reviewer feedback will appear after staff record checker decisions in Documentary Intake.
      </div>
    )
  }

  const cards = [
    ['Decisions', formatCount(total), 'reviewer feedback record(s)'],
    ['Accepted', formatPercent(feedback.acceptance_rate), `${formatCount(feedback.accepted_checker_result)} accepted checker result(s)`],
    ['Overrides', formatPercent(feedback.override_rate), `${formatCount((feedback.override_approve || 0) + (feedback.override_return || 0))} approval/return override(s)`],
    ['False Positives', formatCount(feedback.checker_false_positive), `${formatCount(feedback.checker_missed_evidence)} missed-evidence report(s)`],
  ]

  return (
    <div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        {cards.map(([label, value, detail]) => (
          <div key={label} className="rounded-lg border border-brand-border bg-brand-surface p-4">
            <p className="text-sm font-semibold text-brand-text">{label}</p>
            <p className="mt-2 font-display text-2xl font-semibold leading-none text-brand-text">{value}</p>
            <p className="mt-2 text-xs text-brand-text-muted">{detail}</p>
          </div>
        ))}
      </div>

      <div className="mt-3 rounded-lg border border-brand-border bg-brand-surface p-4">
        <p className="text-sm font-semibold text-brand-text">Top reviewer reason codes</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {(feedback.top_reason_codes || []).length ? (
            feedback.top_reason_codes.map((item) => (
              <span key={item.reason_code} className="status-badge status-badge-info">
                {formatMachineLabel(item.reason_code)}: {formatCount(item.count)}
              </span>
            ))
          ) : (
            <span className="text-sm text-brand-text-muted">No reason codes recorded yet.</span>
          )}
        </div>
      </div>
    </div>
  )
}

export default function CheckerAccuracyReportPage() {
  const [releasedReports, setReleasedReports] = useState([])
  const [feedback, setFeedback] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [exportingRunId, setExportingRunId] = useState(null)
  const [error, setError] = useState('')

  const loadReport = useCallback(async ({ refresh = false } = {}) => {
    if (refresh) setRefreshing(true)
    else setLoading(true)
    setError('')
    try {
      const [releasedReportsRes, feedbackRes] = await Promise.all([
        reportsApi.listCheckerReleasedReports({ limit: 8 }),
        reportsApi.getCheckerReviewerFeedback(),
      ])
      setReleasedReports(releasedReportsRes.data || [])
      setFeedback(feedbackRes.data || null)
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to load DMS checker accuracy report.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    loadReport()
  }, [loadReport])

  const exportRunReport = async (run) => {
    if (!run?.id) return
    setExportingRunId(run.id)
    setError('')
    try {
      const response = await reportsApi.getCheckerRunReport(run.id)
      const report = response.data || {}
      downloadTextFile({
        content: report.markdown || '',
        contentType: report.content_type || 'text/markdown',
        filename: report.filename || `dms-checker-evaluation-run-${run.id}.md`,
      })
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to export benchmark report.')
    } finally {
      setExportingRunId(null)
    }
  }

  const latestRelease = releasedReports[0] || null
  const latestSnapshot = latestRelease?.snapshot || null
  const metrics = latestSnapshot?.metrics || {}
  const gates = latestSnapshot?.gates || []
  const trends = useMemo(
    () => releasedReports.map((release) => {
      const snapshot = release.snapshot || {}
      const run = release.run || {}
      const metricsPayload = snapshot.metrics || run.summary_metrics || {}
      return {
        id: `release-${release.id}`,
        run_id: release.run_id,
        created_at: release.released_at || snapshot.created_at,
        metrics: metricsPayload,
        gates: snapshot.gates || metricsPayload.gates || [],
      }
    }),
    [releasedReports],
  )
  const completedRuns = useMemo(
    () => releasedReports
      .map((release) => ({
        ...(release.run || {}),
        release_id: release.id,
        released_at: release.released_at,
        report_version: release.report_version,
        release_notes: release.release_notes,
      }))
      .filter((run) => run.id)
      .slice(0, 8),
    [releasedReports],
  )
  const passedGateCount = gates.filter((gate) => gate.status === 'passed').length
  const totalGateCount = gates.length
  const caseCount = metrics.total_cases ?? latestRelease?.dataset?.case_count

  const scorecards = [
    {
      title: 'Benchmark Cases',
      value: formatCount(caseCount),
      subtitle: `${formatCount(metrics.passed_cases)} passed, ${formatCount(metrics.failed_cases)} failed`,
      icon: FileSearch,
      color: 'blue',
    },
    {
      title: 'False Approval Rate',
      value: formatPercent(metrics.false_approval_rate),
      subtitle: `${formatCount(metrics.false_approval_count)} false approval(s)`,
      icon: ShieldAlert,
      color: metrics.false_approval_count ? 'red' : 'emerald',
    },
    {
      title: 'False Return Rate',
      value: formatPercent(metrics.false_return_rate),
      subtitle: `${formatCount(metrics.false_return_count)} false return(s)`,
      icon: AlertTriangle,
      color: metrics.false_return_count ? 'amber' : 'emerald',
    },
    {
      title: 'OCR CER / WER',
      value: `${formatPercent(nestedMetric(metrics, ['ocr', 'cer'], 'ocr_cer'))} / ${formatPercent(nestedMetric(metrics, ['ocr', 'wer'], 'ocr_wer'))}`,
      subtitle: `${formatCount(nestedMetric(metrics, ['ocr', 'text_support'], 'ocr_cer_support'))} OCR text case(s)`,
      icon: ScanText,
      color: 'cyan',
    },
    {
      title: 'Mapping F1',
      value: formatPercent(nestedMetric(metrics, ['mapping', 'aggregate', 'f1'], 'mapping_f1')),
      subtitle: `Top-k ${formatPercent(nestedMetric(metrics, ['mapping', 'top_k_accuracy'], 'mapping_top_k_accuracy'))}`,
      icon: GitBranch,
      color: 'cyan',
    },
    {
      title: 'Field Extraction F1',
      value: formatPercent(nestedMetric(metrics, ['fields', 'aggregate', 'f1'])),
      subtitle: `${formatCount(nestedMetric(metrics, ['fields', 'aggregate', 'support']))} field label(s)`,
      icon: Target,
      color: 'blue',
    },
    {
      title: 'Layout Element F1',
      value: formatPercent(metrics.layout_element_f1),
      subtitle: `${formatCount(metrics.layout_element_support)} layout label(s)`,
      icon: MapPinned,
      color: 'cyan',
    },
    {
      title: 'Gate Health',
      value: totalGateCount ? `${formatCount(passedGateCount)}/${formatCount(totalGateCount)}` : 'No gates',
      subtitle: `${formatCount(releasedReports.length)} released benchmark report(s)`,
      icon: CheckCircle2,
      color: passedGateCount === totalGateCount && totalGateCount ? 'emerald' : 'amber',
    },
    {
      title: 'Reviewer Overrides',
      value: formatPercent(feedback?.override_rate),
      subtitle: `${formatCount(feedback?.total_reviewer_decisions)} reviewer decision(s)`,
      icon: Users,
      color: feedback?.override_rate ? 'amber' : 'slate',
    },
  ]

  const trendColumns = [
    {
      key: 'created_at',
      label: 'Snapshot',
      render: (row) => (
        <div>
          <p className="font-medium text-brand-text">{formatDateTime(row.created_at)}</p>
          <p className="mt-1 text-xs text-brand-text-muted">Run #{row.run_id || 'not linked'}</p>
        </div>
      ),
    },
    { key: 'total_cases', label: 'Cases', render: (row) => formatCount(metricValue(row, 'total_cases')) },
    { key: 'pass_rate', label: 'Pass Rate', render: (row) => formatPercent(passRate(row)) },
    { key: 'false_approval_rate', label: 'False Approval', render: (row) => formatPercent(metricValue(row, 'false_approval_rate')) },
    { key: 'false_return_rate', label: 'False Return', render: (row) => formatPercent(metricValue(row, 'false_return_rate')) },
    { key: 'ocr_cer', label: 'OCR CER', render: (row) => formatPercent(metricValue(row, 'ocr_cer')) },
    { key: 'mapping_f1', label: 'Mapping F1', render: (row) => formatPercent(metricValue(row, 'mapping_f1')) },
    { key: 'layout_element_f1', label: 'Layout F1', render: (row) => formatPercent(metricValue(row, 'layout_element_f1')) },
    { key: 'gate_health', label: 'Gate Health', render: (row) => gateHealth(row) },
  ]

  const runColumns = [
    { key: 'run_name', label: 'Run' },
    {
      key: 'status',
      label: 'Status',
      render: (row) => <span className={badgeClassForStatus(row.status)}>{formatMachineLabel(row.status)}</span>,
    },
    { key: 'checker_version', label: 'Checker Version', render: (row) => row.checker_version || 'Not recorded' },
    { key: 'total_cases', label: 'Cases', render: (row) => formatCount(row.summary_metrics?.total_cases) },
    { key: 'false_approval_count', label: 'False Approvals', render: (row) => formatCount(row.summary_metrics?.false_approval_count) },
    { key: 'false_return_count', label: 'False Returns', render: (row) => formatCount(row.summary_metrics?.false_return_count) },
    { key: 'released_at', label: 'Released', render: (row) => formatDateTime(row.released_at) },
    {
      key: 'actions',
      label: '',
      render: (row) => (
        <Button
          size="sm"
          variant="outline"
          icon={Download}
          loading={exportingRunId === row.id}
          aria-label={`Export ${row.run_name}`}
          onClick={() => exportRunReport(row)}
        >
          Export
        </Button>
      ),
    },
  ]

  return (
    <div className="page-container">
      <PageHeader
        eyebrow="Reports & Analytics"
        title="DMS Checker Accuracy Report"
        description="Read-only benchmark scorecard for OCR, document mapping, field extraction, compliance quality, layout checks, and reviewer feedback."
        actions={(
          <Button variant="outline" icon={RefreshCw} onClick={() => loadReport({ refresh: true })} loading={refreshing}>
            Refresh
          </Button>
        )}
        meta={(
          <>
            <span className="status-badge status-badge-info">Operational report</span>
            <span className="status-badge status-badge-success">Released benchmark</span>
            <span className="status-badge status-badge-neutral">Read-only</span>
          </>
        )}
      />

      {error && <InlineAlert type="error" title="Unable to load accuracy report" className="mb-4">{error}</InlineAlert>}

      {loading ? (
        <GlassPanel>
          <div className="p-8 text-center text-sm text-brand-text-muted">
            <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-brand-primary border-t-transparent" />
            Loading checker accuracy report...
          </div>
        </GlassPanel>
      ) : (
        <div className="space-y-5">
          {!latestRelease && (
            <InlineAlert type="info">
              No released checker accuracy report is available yet.
            </InlineAlert>
          )}

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {scorecards.map((card) => <KpiCard key={card.title} {...card} />)}
          </div>

          <GlassPanel>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wide text-brand-text">Accuracy Gates</h2>
                <p className="mt-1 text-xs text-brand-text-muted">
                  Dataset cases: {formatCount(caseCount)}
                </p>
              </div>
              <BarChart3 className="h-4 w-4 text-brand-text-muted" strokeWidth={1.8} aria-hidden="true" />
            </div>
            <AccuracyGateList gates={gates} />
          </GlassPanel>

          <GlassPanel>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wide text-brand-text">Benchmark Trends</h2>
                <p className="mt-1 text-xs text-brand-text-muted">Latest {formatCount(trends.length)} snapshot(s)</p>
              </div>
            </div>
            <DataTable
              columns={trendColumns}
              data={trends}
              keyField="id"
              density="compact"
              hidePagination
              emptyMessage="No released benchmark trend snapshots are available yet."
            />
          </GlassPanel>

          <GlassPanel>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wide text-brand-text">Released Benchmark Reports</h2>
                <p className="mt-1 text-xs text-brand-text-muted">System Administrator-released runs available for export</p>
              </div>
            </div>
            <DataTable
              columns={runColumns}
              data={completedRuns}
              keyField="id"
              density="compact"
              hidePagination
              emptyMessage="No released benchmark reports are available yet."
            />
          </GlassPanel>

          <GlassPanel>
            <div className="mb-4">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-brand-text">Reviewer Feedback</h2>
            </div>
            <ReviewerFeedback feedback={feedback} />
          </GlassPanel>
        </div>
      )}
    </div>
  )
}
