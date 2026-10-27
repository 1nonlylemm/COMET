import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertOctagon,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  ExternalLink,
  Flame,
  Info,
  MapPin,
} from 'lucide-react'
import { ROUTES } from '../../../../config/routes'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatPercent(value) {
  return `${Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })}%`
}

const BUCKET_CONFIG = {
  overdue: {
    bg: 'bg-rose-500',
    card: 'border-rose-200 bg-rose-50/60 dark:border-rose-900/50 dark:bg-rose-950/20',
    text: 'text-rose-700 dark:text-rose-300',
    icon: Flame,
    shortLabel: 'Overdue',
    zeroLabel: 'overdue',
  },
  due_today: {
    bg: 'bg-amber-500',
    card: 'border-amber-200 bg-amber-50/60 dark:border-amber-900/50 dark:bg-amber-950/20',
    text: 'text-amber-700 dark:text-amber-300',
    icon: AlertOctagon,
    shortLabel: 'Due Today',
    zeroLabel: 'due today',
  },
  due_in_3: {
    bg: 'bg-yellow-500',
    card: 'border-yellow-200 bg-yellow-50/60 dark:border-yellow-900/50 dark:bg-yellow-950/20',
    text: 'text-yellow-800 dark:text-yellow-300',
    icon: Clock,
    shortLabel: 'In 1-3 Days',
    zeroLabel: 'in 1-3',
  },
  due_in_7: {
    bg: 'bg-blue-500',
    card: 'border-blue-200 bg-blue-50/60 dark:border-blue-900/50 dark:bg-blue-950/20',
    text: 'text-blue-700 dark:text-blue-300',
    icon: Calendar,
    shortLabel: 'In 4-7 Days',
    zeroLabel: 'in 4-7',
  },
  future: {
    bg: 'bg-slate-400',
    card: 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60 dark:border-slate-800 dark:bg-slate-900/40',
    text: 'text-slate-700 dark:text-slate-200 dark:text-slate-300',
    icon: CheckCircle2,
    shortLabel: '>7 Days',
    zeroLabel: '7+ working days',
  },
}

export default function SlaSnapshotCard({
  slaData = {},
  overdueData = {},
  onBucketClick,
  onLguClick,
  emptyMessage = 'No active or overdue SLA compliance deadlines found.',
  showUrgencyTiers = true,
}) {
  const { total_active = 0, buckets = [] } = slaData
  const { lgus = [], total_overdue = 0, affected_lgus_count = 0 } = overdueData
  const [showAllLgus, setShowAllLgus] = useState(false)

  const { nonZeroBuckets, zeroBuckets } = useMemo(() => {
    if (!showUrgencyTiers) return { nonZeroBuckets: [], zeroBuckets: [] }
    const nonZero = []
    const zero = []
    buckets.forEach((b) => {
      if ((b.count || 0) > 0) {
        nonZero.push(b)
      } else {
        zero.push(b)
      }
    })
    return { nonZeroBuckets: nonZero, zeroBuckets: zero }
  }, [buckets, showUrgencyTiers])

  const zeroSummaryText = useMemo(() => {
    if (!showUrgencyTiers || !buckets.length) return null
    if (nonZeroBuckets.length === 0) {
      return 'None overdue, due today, in 1-3, 4-7, or 7+ working days'
    }
    if (zeroBuckets.length === 0) {
      return null
    }
    const labels = zeroBuckets.map((b) => {
      const cfg = BUCKET_CONFIG[b.key]
      return cfg?.zeroLabel || b.label.toLowerCase()
    })
    if (labels.length === 1) {
      return `None ${labels[0]}`
    }
    if (labels.length === 2) {
      return `None ${labels[0]} or ${labels[1]}`
    }
    const last = labels.pop()
    return `None ${labels.join(', ')}, or ${last}`
  }, [buckets, nonZeroBuckets, zeroBuckets, showUrgencyTiers])

  const visibleLgus = useMemo(() => {
    if (showAllLgus) return lgus
    return lgus.slice(0, 5)
  }, [lgus, showAllLgus])

  const maxOverdue = useMemo(() => {
    if (!lgus.length) return 1
    return Math.max(...lgus.map((l) => l.overdue_count || 0), 1)
  }, [lgus])

  const isEmpty = showUrgencyTiers
    ? total_active === 0 && (!lgus || lgus.length === 0)
    : total_overdue === 0 && (!lgus || lgus.length === 0)

  if (isEmpty) {
    return (
      <div className="py-8 text-center text-sm text-brand-text-muted">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Top Telemetry & SLA Tracker Link */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          {showUrgencyTiers ? (
            <span className="font-semibold text-brand-text">
              Active Timers: <span className="tabular-nums font-bold text-brand-primary">{formatNumber(total_active)}</span>
            </span>
          ) : (
            <span className="font-semibold text-brand-text">
              Overdue Submissions: <span className="tabular-nums font-bold text-rose-600 dark:text-rose-400">{formatNumber(total_overdue)}</span>
            </span>
          )}
          {showUrgencyTiers && total_overdue > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 dark:bg-rose-950/40 px-2 py-0.5 font-bold text-rose-700 dark:text-rose-300 ring-1 ring-rose-200 dark:ring-rose-800">
              <Flame className="h-3 w-3" />
              {formatNumber(total_overdue)} Overdue
            </span>
          )}
          {affected_lgus_count > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-brand-text-muted">
              <MapPin className="h-3 w-3 opacity-70" />
              {formatNumber(affected_lgus_count)} LGUs affected
            </span>
          )}
        </div>

        <Link
          to={ROUTES.SLA}
          className="inline-flex items-center gap-1 text-xs font-semibold text-brand-primary hover:underline"
        >
          <span>SLA Tracker</span>
          <ExternalLink className="h-3 w-3" />
        </Link>
      </div>

      {/* Stacked Urgency Bar (Only when showUrgencyTiers is true) */}
      {showUrgencyTiers && (
        <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800 flex shadow-inner">
        {nonZeroBuckets.length > 0 ? (
          nonZeroBuckets.map((b) => {
            const count = b.count || 0
            const pct = total_active > 0 ? (count / total_active) * 100 : 0
            const cfg = BUCKET_CONFIG[b.key] || { bg: 'bg-slate-400' }
            const isClickable = Boolean(onBucketClick)

            return (
              <div
                key={b.key}
                onClick={() => isClickable && onBucketClick(b)}
                className={`${cfg.bg} h-full transition-all duration-300 ${
                  isClickable ? 'cursor-pointer hover:brightness-110' : ''
                }`}
                style={{ width: `${pct}%` }}
                title={`${b.label}: ${formatNumber(count)} (${formatPercent(pct)}) — click to view in SLA Tracker`}
              />
            )
          })
        ) : (
          <div className="h-full w-full bg-slate-200 dark:bg-slate-700" />
        )}
        </div>
      )}

      {/* Non-Zero Bucket Pills (Only when showUrgencyTiers is true) */}
      {showUrgencyTiers && nonZeroBuckets.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {nonZeroBuckets.map((b) => {
            const cfg = BUCKET_CONFIG[b.key] || {
              card: 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800',
              text: 'text-slate-700 dark:text-slate-200',
              icon: Clock,
              shortLabel: b.label,
            }
            const Icon = cfg.icon
            const isClickable = Boolean(onBucketClick)

            return (
              <button
                key={b.key}
                type="button"
                onClick={() => isClickable && onBucketClick(b)}
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-all ${
                  cfg.card
                } ${isClickable ? 'cursor-pointer hover:shadow-xs' : ''}`}
                title={`Filter SLA Tracker by ${b.label}`}
              >
                <Icon className={`h-3.5 w-3.5 ${cfg.text}`} />
                <span className="text-brand-text font-semibold">{cfg.shortLabel}:</span>
                <span className={`tabular-nums font-bold ${cfg.text}`}>
                  {formatNumber(b.count)}
                </span>
                <span className="text-[10px] text-brand-text-muted opacity-80">
                  ({formatPercent(total_active > 0 ? (b.count / total_active) * 100 : 0)})
                </span>
              </button>
            )
          })}
        </div>
      )}

      {/* Zero Buckets Collapsed into Single Muted Line */}
      {showUrgencyTiers && zeroSummaryText && (
        <p className="text-xs text-brand-text-muted italic flex items-center gap-1.5 px-0.5">
          <Info className="h-3 w-3 shrink-0 opacity-70" />
          <span>{zeroSummaryText}</span>
        </p>
      )}

      {/* Overdue Deadlines by LGU List */}
      {lgus.length > 0 && (
        <div className="pt-2 border-t border-brand-border/60">
          <div className="mb-2 flex items-center justify-between text-xs">
            <span className="font-semibold text-brand-text">
              Top LGUs by Overdue Deadlines ({showAllLgus ? `All ${lgus.length}` : `Top ${Math.min(5, lgus.length)} of ${lgus.length}`})
            </span>
            <span className="text-[11px] text-brand-text-muted">Click an LGU to inspect records in SLA Tracker</span>
          </div>

          <div className="space-y-1.5">
            {visibleLgus.map((item, idx) => {
              const barPct = Math.min(100, ((item.overdue_count / maxOverdue) * 100))
              const isClickable = Boolean(onLguClick)

              return (
                <div
                  key={item.lgu_id || idx}
                  data-testid={`overdue-lgu-${item.lgu_id || idx}`}
                  onClick={() => isClickable && onLguClick(item)}
                  className={`group rounded-lg border border-brand-border/60 bg-brand-surface p-2.5 transition-all ${
                    isClickable
                      ? 'cursor-pointer hover:border-brand-primary hover:bg-brand-surface-solid'
                      : ''
                  }`}
                  role={isClickable ? 'button' : undefined}
                  tabIndex={isClickable ? 0 : undefined}
                  onKeyDown={(e) => {
                    if (isClickable && (e.key === 'Enter' || e.key === ' ')) {
                      e.preventDefault()
                      onLguClick(item)
                    }
                  }}
                >
                  <div className="flex items-center justify-between gap-3 text-xs">
                    <div className="min-w-0 flex items-center gap-2">
                      <span className="font-medium text-brand-text truncate">
                        {item.lgu_name}
                      </span>
                      {item.cluster_name && (
                        <span className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.2 text-[10px] text-brand-text-muted shrink-0">
                          {item.cluster_name}
                        </span>
                      )}
                      <span className="text-[11px] text-brand-text-muted shrink-0">
                        · {formatNumber(item.affected_project_count)} {item.affected_project_count === 1 ? 'project' : 'projects'}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span className="rounded-full bg-rose-50 dark:bg-rose-950/40 px-2 py-0.5 text-xs font-bold text-rose-700 dark:text-rose-300">
                        {formatNumber(item.overdue_count)} overdue
                      </span>
                      {isClickable && (
                        <span className="flex items-center gap-0.5 text-[11px] font-semibold text-brand-primary opacity-0 transition-opacity group-hover:opacity-100">
                          SLA Tracker
                          <ExternalLink className="h-3 w-3" />
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Relative Volume Progress Bar */}
                  <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                    <div
                      className="h-full bg-rose-500 rounded-full transition-all duration-300"
                      style={{ width: `${barPct}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>

          {lgus.length > 5 && (
            <div className="mt-2.5 flex justify-end">
              <button
                type="button"
                onClick={() => setShowAllLgus((prev) => !prev)}
                className="inline-flex items-center gap-1 text-xs font-semibold text-brand-primary hover:underline"
              >
                {showAllLgus ? (
                  <>
                    <span>Show top 5 LGUs</span>
                    <ChevronUp className="h-3.5 w-3.5" />
                  </>
                ) : (
                  <>
                    <span>View all {lgus.length} LGUs</span>
                    <ChevronDown className="h-3.5 w-3.5" />
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
