import { useMemo } from 'react'
import { ChevronRight } from 'lucide-react'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatPercent(value) {
  return `${Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })}%`
}

export default function HorizontalBarChart({
  data = [],
  emptyMessage = 'No data available.',
  onItemClick,
  maxItems = 10,
  valueSuffix = '',
  legend = [],
}) {
  const items = useMemo(() => {
    if (!maxItems) return data
    return data.slice(0, maxItems)
  }, [data, maxItems])

  const maxTotal = useMemo(() => {
    if (!data.length) return 1
    return Math.max(...data.map((d) => d.total || d.backlog_count || 0), 1)
  }, [data])

  if (!data || data.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-brand-text-muted">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Legend if provided */}
      {legend.length > 0 && (
        <div className="flex flex-wrap items-center gap-4 text-xs text-brand-text-muted">
          {legend.map((item) => (
            <div key={item.key} className="flex items-center gap-1.5">
              <span className={`h-2.5 w-2.5 rounded-sm ${item.color}`} />
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      )}

      {/* Bar List */}
      <div className="space-y-3">
        {items.map((item, idx) => {
          const totalVal = item.total ?? item.backlog_count ?? 0
          const barPct = Math.min(100, ((totalVal / maxTotal) * 100))
          const isClickable = Boolean(onItemClick)

          return (
            <div
              key={item.id || item.lgu_id || item.category || idx}
              onClick={() => isClickable && onItemClick(item)}
              className={`group rounded-lg border border-transparent p-2.5 transition-all ${
                isClickable
                  ? 'cursor-pointer hover:border-brand-border hover:bg-brand-surface-solid dark:hover:bg-brand-surface'
                  : ''
              }`}
              role={isClickable ? 'button' : undefined}
              tabIndex={isClickable ? 0 : undefined}
              onKeyDown={(e) => {
                if (isClickable && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault()
                  onItemClick(item)
                }
              }}
            >
              {/* Row Header */}
              <div className="mb-1.5 flex items-baseline justify-between gap-3 text-xs">
                <div className="flex items-baseline gap-2 min-w-0">
                  <span className="font-semibold text-brand-text truncate">
                    {item.label || item.lgu_name || item.category_label || item.category}
                  </span>
                  {item.secondaryLabel && (
                    <span className="text-brand-text-muted truncate">
                      · {item.secondaryLabel}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="tabular-nums font-bold text-brand-text">
                    {formatNumber(totalVal)} {valueSuffix}
                  </span>
                  {item.badgeText && (
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                        item.badgeTone === 'success'
                          ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300'
                          : item.badgeTone === 'warning'
                          ? 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300'
                          : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
                      }`}
                    >
                      {item.badgeText}
                    </span>
                  )}
                  {isClickable && (
                    <ChevronRight className="h-3.5 w-3.5 text-brand-text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                  )}
                </div>
              </div>

              {/* Stacked Bar container */}
              <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                <div
                  className="flex h-full rounded-full transition-all duration-300"
                  style={{ width: `${barPct}%` }}
                >
                  {item.segments && item.segments.length > 0 ? (
                    item.segments.map((seg) => {
                      const segVal = Number(seg.value || 0)
                      if (!segVal || !totalVal) return null
                      const segPct = (segVal / totalVal) * 100
                      return (
                        <div
                          key={seg.key}
                          className={`${seg.color} h-full transition-all`}
                          style={{ width: `${segPct}%` }}
                          title={`${seg.label}: ${formatNumber(segVal)} (${formatPercent(segPct)})`}
                        />
                      )
                    })
                  ) : (
                    <div
                      className="h-full bg-brand-primary"
                      style={{ width: '100%' }}
                    />
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
