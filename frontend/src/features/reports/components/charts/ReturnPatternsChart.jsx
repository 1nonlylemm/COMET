import { useMemo } from 'react'
import { AlertCircle, ChevronRight, CornerUpLeft, FileText, Layers } from 'lucide-react'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

export default function ReturnPatternsChart({
  returnPatterns,
  returnPatternsData,
  onRequirementClick,
  maxItems = 10,
  emptyMessage = 'No requirement return events recorded for the selected cohort.',
}) {
  const data = returnPatternsData || returnPatterns || {}
  const {
    requirements = [],
    total_return_events = 0,
    unique_requirements_returned = 0,
    affected_projects_total = 0,
  } = data

  const items = useMemo(() => {
    if (!maxItems) return requirements
    return requirements.slice(0, maxItems)
  }, [requirements, maxItems])

  const maxReturns = useMemo(() => {
    if (!requirements.length) return 1
    return Math.max(...requirements.map((r) => r.return_count || 0), 1)
  }, [requirements])

  if (!total_return_events && (!requirements || requirements.length === 0)) {
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
          <CornerUpLeft className="h-3.5 w-3.5" />
          {formatNumber(total_return_events)} Total Return Events
        </span>
        <span className="flex items-center gap-1.5 rounded-md border border-brand-border bg-brand-surface px-2.5 py-1 text-brand-text">
          <FileText className="h-3.5 w-3.5 opacity-70" />
          {formatNumber(unique_requirements_returned)} Unique Requirements Returned
        </span>
        <span className="flex items-center gap-1.5 rounded-md border border-brand-border bg-brand-surface px-2.5 py-1 text-brand-text">
          <Layers className="h-3.5 w-3.5 opacity-70" />
          {formatNumber(affected_projects_total)} Projects Affected
        </span>
      </div>

      {/* Ranked Bar List */}
      <div className="space-y-3">
        {items.map((item, idx) => {
          const barPct = Math.min(100, ((item.return_count / maxReturns) * 100))
          const isClickable = Boolean(onRequirementClick)

          return (
            <div
              key={item.requirement_name || idx}
              onClick={() => isClickable && onRequirementClick(item)}
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
                  onRequirementClick(item)
                }
              }}
            >
              {/* Header row: title and metrics */}
              <div className="mb-2 flex items-start justify-between gap-3 text-xs">
                <div className="min-w-0">
                  <span className="font-semibold text-brand-text">
                    {item.requirement_name}
                  </span>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-brand-text-muted">
                    <span className="rounded bg-rose-50 dark:bg-rose-950/40 px-1.5 py-0.5 font-bold text-rose-700 dark:text-rose-300">
                      {formatNumber(item.return_count)} returns
                    </span>
                    <span>·</span>
                    <span>{formatNumber(item.unique_requirements_count || item.unique_requirement_count || 0)} unique docs</span>
                    <span>·</span>
                    <span>{formatNumber(item.affected_projects_count)} {item.affected_projects_count === 1 ? 'project' : 'projects'}</span>
                    {item.affected_lgus_count > 0 && (
                      <>
                        <span>·</span>
                        <span>{formatNumber(item.affected_lgus_count)} LGUs</span>
                      </>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {isClickable && (
                    <span className="flex items-center gap-1 text-[11px] font-semibold text-brand-primary opacity-0 transition-opacity group-hover:opacity-100">
                      View details
                      <ChevronRight className="h-3.5 w-3.5" />
                    </span>
                  )}
                </div>
              </div>

              {/* Bar */}
              <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-rose-400 to-rose-600 transition-all duration-300"
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
