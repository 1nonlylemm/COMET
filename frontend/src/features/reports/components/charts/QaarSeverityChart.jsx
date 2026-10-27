import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  FileCheck,
  Info,
  ListFilter,
  ShieldAlert,
} from 'lucide-react'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatPercent(value) {
  return `${Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })}%`
}

const SEVERITY_STYLE_CONFIG = {
  severe: {
    color: 'bg-rose-500',
    card: 'border-rose-200 bg-rose-50/50 hover:bg-rose-50 dark:border-rose-900/50 dark:bg-rose-950/20',
    text: 'text-rose-700 dark:text-rose-300',
    icon: AlertOctagon,
    actionText: 'Critical structural / safety defect',
  },
  major: {
    color: 'bg-amber-500',
    card: 'border-amber-200 bg-amber-50/50 hover:bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20',
    text: 'text-amber-700 dark:text-amber-300',
    icon: AlertTriangle,
    actionText: 'Material workmanship / spec non-conformance',
  },
  minor: {
    color: 'bg-yellow-500',
    card: 'border-yellow-200 bg-yellow-50/50 hover:bg-yellow-50 dark:border-yellow-900/50 dark:bg-yellow-950/20',
    text: 'text-yellow-800 dark:text-yellow-300',
    icon: Info,
    actionText: 'Cosmetic / minor dimensional defect',
  },
  unclassified: {
    color: 'bg-slate-400',
    card: 'border-slate-200 bg-slate-50/50 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900/40',
    text: 'text-slate-700 dark:text-slate-300',
    icon: Info,
    actionText: 'Unclassified defect degree',
  },
}

export function QaarSeverityChart({
  qaarData = {},
  onSeverityClick,
  onViewAllClick,
  emptyMessage = 'No QAAR field inspection defects recorded in visible portfolio.',
}) {
  const {
    total_findings = 0,
    total_inspections = 0,
    affected_projects_count = 0,
    severities = [],
  } = qaarData

  if (!total_findings || total_findings === 0) {
    return (
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/20 p-6 text-center">
        <div className="flex justify-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-400">
            <CheckCircle2 className="h-5 w-5" />
          </div>
        </div>
        <h4 className="mt-2 text-sm font-semibold text-brand-text">
          {total_inspections > 0 ? 'Zero QAAR Inspection Defects' : 'No QAAR Inspections Recorded'}
        </h4>
        <p className="mt-1 text-xs text-brand-text-muted max-w-md mx-auto">
          {total_inspections > 0
            ? `${total_inspections} QAAR field inspections conducted across visible infrastructure projects with zero open defect findings recorded.`
            : emptyMessage}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header Info & Counts */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-1.5 text-brand-text-muted">
          <ShieldAlert className="h-3.5 w-3.5 shrink-0 text-brand-primary" />
          <span>Quality Assurance Assessment Report (QAAR) civil works inspection defect breakdown</span>
        </div>
        <div className="flex flex-wrap items-center gap-3 font-semibold text-brand-text">
          <span>
            Total Findings: <strong className="tabular-nums text-brand-primary">{formatNumber(total_findings)}</strong>
          </span>
          <span className="text-slate-300 dark:text-slate-700">•</span>
          <span>
            Inspections: <strong className="tabular-nums text-brand-text">{formatNumber(total_inspections)}</strong>
          </span>
          <span className="text-slate-300 dark:text-slate-700">•</span>
          <span>
            Projects Affected: <strong className="tabular-nums text-amber-600 dark:text-amber-400">{formatNumber(affected_projects_count)}</strong>
          </span>
          {onViewAllClick && (
            <button
              type="button"
              onClick={onViewAllClick}
              className="inline-flex items-center gap-1 rounded-lg border border-brand-border bg-brand-surface px-2.5 py-1 text-xs font-semibold text-brand-text hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors shadow-xs"
            >
              <ListFilter className="h-3 w-3 text-brand-primary" />
              <span>View Findings List</span>
            </button>
          )}
        </div>
      </div>

      {/* Segmented Distribution Bar */}
      <div className="h-3.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800 flex shadow-inner">
        {severities.map((s) => {
          if (!s.count || !total_findings) return null
          const pct = ((s.count / total_findings) * 100)
          const styleCfg = SEVERITY_STYLE_CONFIG[s.severity] || SEVERITY_STYLE_CONFIG.unclassified

          return (
            <div
              key={s.severity}
              className={`${styleCfg.color} h-full transition-all duration-300 hover:brightness-110 cursor-pointer`}
              style={{ width: `${pct}%` }}
              onClick={() => onSeverityClick && onSeverityClick(s.severity)}
              title={`${s.label}: ${formatNumber(s.count)} (${formatPercent(s.percentage)})`}
            />
          )
        })}
      </div>

      {/* Severity Cards Grid */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {severities
          .filter((s) => s.severity !== 'unclassified' || s.count > 0)
          .map((s) => {
            const styleCfg = SEVERITY_STYLE_CONFIG[s.severity] || SEVERITY_STYLE_CONFIG.unclassified
            const SevIcon = styleCfg.icon
            const isClickable = Boolean(onSeverityClick)

            return (
              <div
                key={s.severity}
                onClick={() => isClickable && onSeverityClick(s.severity)}
                className={`flex flex-col justify-between rounded-xl border p-3.5 transition-all ${
                  styleCfg.card
                } ${isClickable ? 'cursor-pointer hover:shadow-sm' : ''}`}
                role={isClickable ? 'button' : undefined}
                tabIndex={isClickable ? 0 : undefined}
                onKeyDown={(e) => {
                  if (isClickable && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault()
                    onSeverityClick(s.severity)
                  }
                }}
                title={isClickable ? `Click to view ${s.label} findings` : s.label}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className={`h-3 w-3 rounded-full shrink-0 ${styleCfg.color}`} />
                    <span className="text-xs font-semibold text-brand-text">
                      {s.label}
                    </span>
                  </div>
                  <SevIcon className={`h-4 w-4 shrink-0 ${styleCfg.text}`} />
                </div>

                <div className="my-2 text-[11px] text-brand-text-muted">
                  {styleCfg.actionText}
                </div>

                <div className="flex items-baseline justify-between border-t border-brand-border/40 pt-2">
                  <span className={`text-xl font-bold tabular-nums ${styleCfg.text}`}>
                    {formatNumber(s.count)}
                  </span>
                  <span className="text-xs text-brand-text-muted tabular-nums">
                    {formatPercent(s.percentage)}
                  </span>
                </div>
              </div>
            )
          })}
      </div>
    </div>
  )
}

export default QaarSeverityChart
