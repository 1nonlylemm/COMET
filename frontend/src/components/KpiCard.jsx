import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { formatStatus } from '../lib/formatters'

const statusColors = {
  compliant: { badge: 'status-badge-success', dot: 'bg-emerald-600 dark:bg-emerald-300' },
  approved: { badge: 'status-badge-success', dot: 'bg-emerald-600 dark:bg-emerald-300' },
  resolved: { badge: 'status-badge-success', dot: 'bg-emerald-600 dark:bg-emerald-300' },
  pending: { badge: 'status-badge-warning', dot: 'bg-amber-600 dark:bg-amber-300' },
  under_review: { badge: 'status-badge-info', dot: 'bg-blue-600 dark:bg-blue-300' },
  in_progress: { badge: 'status-badge-info', dot: 'bg-blue-600 dark:bg-blue-300' },
  non_compliant: { badge: 'status-badge-danger', dot: 'bg-red-600 dark:bg-red-300' },
  returned: { badge: 'status-badge-danger', dot: 'bg-red-600 dark:bg-red-300' },
  deficient: { badge: 'status-badge-danger', dot: 'bg-red-600 dark:bg-red-300' },
  breached: { badge: 'status-badge-danger', dot: 'bg-red-600 dark:bg-red-300' },
  overdue: { badge: 'status-badge-danger', dot: 'bg-red-600 dark:bg-red-300' },
  handed_off: { badge: 'status-badge-handoff', dot: 'bg-cyan-600 dark:bg-cyan-300' },
  archived: { badge: 'status-badge-neutral', dot: 'bg-slate-500 dark:bg-slate-300' },
  waived: { badge: 'status-badge-neutral', dot: 'bg-slate-500 dark:bg-slate-300' },
}

export function ComplianceBadge({ status, label }) {
  const colors = statusColors[status] || statusColors.pending
  const displayLabel = label || formatStatus(status)

  return (
    <span className={`status-badge ${colors.badge}`}>
      <span className={`status-dot ${colors.dot}`} />
      {displayLabel}
    </span>
  )
}

const toneMap = {
  blue: {
    icon: 'text-blue-600 dark:text-blue-300',
    trendBg: 'bg-blue-50 text-blue-800 dark:bg-blue-400/10 dark:text-blue-200',
  },
  emerald: {
    icon: 'text-emerald-600 dark:text-emerald-300',
    trendBg: 'bg-emerald-50 text-emerald-800 dark:bg-emerald-400/10 dark:text-emerald-200',
  },
  amber: {
    icon: 'text-amber-600 dark:text-amber-300',
    trendBg: 'bg-amber-50 text-amber-800 dark:bg-amber-300/10 dark:text-amber-100',
  },
  red: {
    icon: 'text-red-600 dark:text-red-300',
    trendBg: 'bg-red-50 text-red-800 dark:bg-red-400/10 dark:text-red-200',
  },
  cyan: {
    icon: 'text-cyan-600 dark:text-cyan-300',
    trendBg: 'bg-cyan-50 text-cyan-800 dark:bg-cyan-300/10 dark:text-cyan-100',
  },
  slate: {
    icon: 'text-slate-600 dark:text-slate-300',
    trendBg: 'bg-slate-100 text-slate-700 dark:bg-slate-700/40 dark:text-slate-200',
  },
}

function isPositiveTrend(trend) {
  const value = Number(trend)
  return Number.isFinite(value) ? value >= 0 : true
}

function formatTrend(trend) {
  if (trend === undefined || trend === null || trend === '') return null
  if (typeof trend === 'string') return trend
  return `${trend >= 0 ? '+' : ''}${trend}%`
}

export function KpiCard({ title, value, subtitle, icon: Icon, trend, trendLabel, color = 'blue' }) {
  const tone = toneMap[color] || toneMap.blue
  const trendText = formatTrend(trend)
  const positiveTrend = isPositiveTrend(trend)
  const TrendIcon = positiveTrend ? ArrowUpRight : ArrowDownRight

  return (
    <article className="rounded-lg border border-brand-border bg-brand-surface-solid p-4 shadow-sm dark:bg-brand-surface">
      <div className="flex items-start justify-between gap-3">
        <p className="truncate text-sm font-semibold text-brand-text">{title}</p>
        {Icon && (
          <Icon strokeWidth={1.8} className={`h-4 w-4 shrink-0 ${tone.icon}`} aria-hidden="true" />
        )}
      </div>
      <div className="mt-3 flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="break-words font-display text-2xl font-semibold leading-none text-brand-text">
          {(() => {
            if (value === null || value === undefined) return '—'
            if (typeof value === 'number') {
              if (Number.isInteger(value) && value >= 1900 && value <= 2100 && /(year|fy)/i.test(title || '')) {
                return String(value)
              }
              return value.toLocaleString('en-PH')
            }
            if (typeof value === 'string' && /^-?\d+(\.\d+)?$/.test(value.trim())) {
              const num = Number(value.trim())
              if (Number.isInteger(num) && num >= 1900 && num <= 2100 && /(year|fy)/i.test(title || '')) {
                return value.trim()
              }
              return num.toLocaleString('en-PH')
            }
            return value
          })()}
        </span>
        {subtitle && (
          <span className="text-sm leading-5 text-brand-text-muted">
            {subtitle}
          </span>
        )}
      </div>

      {(trendText || trendLabel) && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {trendText && (
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${positiveTrend ? toneMap.emerald.trendBg : toneMap.red.trendBg}`}>
              <TrendIcon className="h-3 w-3" aria-hidden="true" />
              {trendText}
            </span>
          )}
          {trendLabel && <span className="text-xs text-brand-text-muted">{trendLabel}</span>}
        </div>
      )}
    </article>
  )
}
