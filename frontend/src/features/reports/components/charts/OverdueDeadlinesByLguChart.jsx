import { useMemo } from 'react'
import { AlertOctagon, ChevronRight, Clock, ExternalLink, MapPin } from 'lucide-react'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

export default function OverdueDeadlinesByLguChart({
  overdueData = {},
  onLguClick,
  maxItems = 10,
  emptyMessage = 'No active overdue compliance deadlines found for visible LGUs.',
}) {
  const { lgus = [], total_overdue = 0, affected_lgus_count = 0 } = overdueData

  const items = useMemo(() => {
    if (!maxItems) return lgus
    return lgus.slice(0, maxItems)
  }, [lgus, maxItems])

  const maxOverdue = useMemo(() => {
    if (!lgus.length) return 1
    return Math.max(...lgus.map((l) => l.overdue_count || 0), 1)
  }, [lgus])

  if (!total_overdue && (!lgus || lgus.length === 0)) {
    return (
      <div className="py-8 text-center text-sm text-brand-text-muted">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Metrics Banner */}
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span className="flex items-center gap-1.5 rounded-md border border-rose-200 bg-rose-50/50 dark:border-rose-900/50 dark:bg-rose-950/20 px-2.5 py-1 text-rose-700 dark:text-rose-300 font-semibold">
          <AlertOctagon className="h-3.5 w-3.5" />
          {formatNumber(total_overdue)} Overdue Compliance Deadlines
        </span>
        <span className="flex items-center gap-1.5 rounded-md border border-brand-border bg-brand-surface px-2.5 py-1 text-brand-text">
          <MapPin className="h-3.5 w-3.5 opacity-70" />
          {formatNumber(affected_lgus_count)} LGUs with Overdue Deadlines
        </span>
      </div>

      {/* Ranked Bar List */}
      <div className="space-y-3">
        {items.map((item, idx) => {
          const barPct = Math.min(100, ((item.overdue_count / maxOverdue) * 100))
          const isClickable = Boolean(onLguClick)

          return (
            <div
              key={item.lgu_id || idx}
              onClick={() => isClickable && onLguClick(item)}
              className={`group rounded-lg border border-brand-border/60 bg-brand-surface p-3 transition-all ${
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
              {/* Header row */}
              <div className="mb-2 flex items-start justify-between gap-3 text-xs">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-brand-text truncate">
                      {item.lgu_name}
                    </span>
                    {item.cluster_name && (
                      <span className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.2 text-[10px] text-brand-text-muted">
                        {item.cluster_name}
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 text-[11px] text-brand-text-muted">
                    {formatNumber(item.affected_project_count)} {item.affected_project_count === 1 ? 'project' : 'projects'} affected
                  </div>
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

              {/* Bar */}
              <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-rose-500 to-red-600 transition-all duration-300"
                  style={{ width: `${barPct}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
