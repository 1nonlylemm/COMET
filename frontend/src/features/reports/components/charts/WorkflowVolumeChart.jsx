import { useMemo } from 'react'
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Clock,
  X,
} from 'lucide-react'
import { ACTION_CONFIG } from '../../constants/workflowConstants'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

export default function WorkflowVolumeChart({
  activityData = {},
  selectedMonth = null,
  selectedAction = null,
  onMonthClick,
  onActionClick,
  emptyMessage = 'No workflow telemetry recorded for the selected cohort.',
}) {
  const months = useMemo(() => {
    return activityData?.monthly_volume || activityData?.months || []
  }, [activityData?.monthly_volume, activityData?.months])
  const action_totals = activityData?.action_totals || {}
  const total_actions = activityData?.total_actions ?? Object.values(action_totals).reduce((a, b) => a + b, 0)

  const maxMonthTotal = useMemo(() => {
    if (!months.length) return 1
    return Math.max(...months.map((m) => m.total || 0), 1)
  }, [months])

  if (!total_actions && (!months || months.length === 0)) {
    return (
      <div className="py-8 text-center text-sm text-brand-text-muted">
        {emptyMessage}
      </div>
    )
  }

  const actionsList = Object.keys(ACTION_CONFIG)

  return (
    <div className="space-y-5">
      {/* Action Totals Summary Bar */}
      <div className="flex flex-wrap items-center gap-2">
        {actionsList.map((actionKey) => {
          const cfg = ACTION_CONFIG[actionKey]
          const count = action_totals[actionKey] || 0
          const isSelected = selectedAction === actionKey
          const Icon = cfg.icon

          return (
            <button
              key={actionKey}
              type="button"
              onClick={() => onActionClick && onActionClick(isSelected ? null : actionKey)}
              className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs transition-all ${
                isSelected
                  ? `${cfg.lightBg} ${cfg.border} ring-2 ring-brand-primary ring-offset-1 font-semibold`
                  : 'border-brand-border bg-brand-surface hover:bg-brand-surface-solid text-brand-text'
              }`}
              title={`Click to filter by action: ${cfg.label}`}
            >
              <span className={`h-2.5 w-2.5 rounded-full ${cfg.color}`} />
              <Icon className="h-3.5 w-3.5 opacity-70" />
              <span>{cfg.label}</span>
              <span className="ml-1 rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.2 font-bold tabular-nums text-[11px] text-brand-text">
                {formatNumber(count)}
              </span>
            </button>
          )
        })}
      </div>

      {/* Monthly Time-Series Columns */}
      <div className="rounded-xl border border-brand-border bg-brand-surface p-4 shadow-sm">
        <div className="mb-4 flex items-center justify-between text-xs text-brand-text-muted">
          <span>Monthly Transition Volume (Chronological)</span>
          <span>Max Monthly Volume: {formatNumber(maxMonthTotal)}</span>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8">
          {months.map((mObj) => {
            const isSelected = selectedMonth === mObj.month
            const heightPct = (mObj.total / maxMonthTotal) * 100

            return (
              <div
                key={mObj.month}
                onClick={() => onMonthClick && onMonthClick(isSelected ? null : mObj.month)}
                className={`group flex flex-col items-center justify-end rounded-xl border p-2.5 transition-all cursor-pointer ${
                  isSelected
                    ? 'border-brand-primary bg-brand-primary/5 ring-2 ring-brand-primary ring-offset-1 shadow-sm'
                    : 'border-brand-border bg-brand-surface hover:border-brand-border-strong hover:bg-brand-surface-solid'
                }`}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onMonthClick && onMonthClick(isSelected ? null : mObj.month)
                  }
                }}
              >
                {/* Total Count Badge */}
                <span className="mb-2 text-xs font-bold tabular-nums text-brand-text">
                  {formatNumber(mObj.total)}
                </span>

                {/* Stacked Vertical Bar */}
                <div className="flex h-[120px] items-end"><div className="flex w-10 flex-col-reverse overflow-hidden rounded-md bg-slate-100 dark:bg-slate-800" style={{ height: `${heightPct * 1.2}px` }}>
                  {actionsList.map((actionKey) => {
                    const actCount = mObj.actions?.[actionKey] || 0
                    if (!actCount) return null
                    const actPct = (actCount / mObj.total) * 100
                    const cfg = ACTION_CONFIG[actionKey]

                    return (
                      <div
                        key={actionKey}
                        className={`${cfg.color} w-full transition-all`}
                        style={{ height: `${actPct}%` }}
                        title={`${mObj.label || mObj.month_label || mObj.month} · ${cfg.label}: ${formatNumber(actCount)} (${Math.round(actPct)}%)`}
                      />
                    )
                  })}
                </div>

                </div>
                {/* Month Label */}
                <span className="mt-2 text-[11px] font-medium text-brand-text truncate">
                  {mObj.label || mObj.month_label || mObj.month}
                </span>
                {isSelected && (
                  <span className="mt-0.5 text-[9px] font-semibold text-brand-primary">
                    Filtered
                  </span>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
