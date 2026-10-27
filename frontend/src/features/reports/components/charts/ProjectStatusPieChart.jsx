import { useMemo, useState } from 'react'
import { PROJECT_STATUS_CONFIG, CANONICAL_STATUS_ORDER } from '../../../../lib/projectStatus'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatPercent(value) {
  return `${Number(value || 0).toLocaleString('en-PH', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`
}

export default function ProjectStatusPieChart({
  statusData,
  selectedStatus = '',
  onStatusClick,
  className = '',
}) {
  const [hoveredStatus, setHoveredStatus] = useState(null)

  // Normalize data and guarantee exact total reconciliation
  const { total, items } = useMemo(() => {
    let tot = 0
    let rawItems = []

    if (statusData && Array.isArray(statusData.items)) {
      rawItems = statusData.items
      tot = Number(statusData.total || 0)
    } else if (Array.isArray(statusData)) {
      rawItems = statusData
      tot = rawItems.reduce((acc, curr) => acc + (Number(curr.count) || 0), 0)
    } else if (statusData && typeof statusData === 'object') {
      const keys = CANONICAL_STATUS_ORDER
      const countsSource = statusData.counts || statusData
      rawItems = keys.map((k) => ({
        key: k,
        label: PROJECT_STATUS_CONFIG[k]?.label || k,
        count: Number(countsSource[k] || 0),
      }))
      tot = rawItems.reduce((acc, curr) => acc + curr.count, 0)
    }

    // Ensure all 4 canonical statuses are represented in authoritative order
    const normalized = CANONICAL_STATUS_ORDER.map((key) => {
      const existing = rawItems.find((it) => it.key === key || it.status === key)
      const count = existing ? Number(existing.count || 0) : 0
      return {
        key,
        label: PROJECT_STATUS_CONFIG[key]?.label || key,
        count,
        percentage: 0,
        config: PROJECT_STATUS_CONFIG[key],
      }
    })

    // Strict reconciliation: sum of canonical slice counts
    const computedTotal = normalized.reduce((acc, curr) => acc + curr.count, 0)
    const finalTotal = tot > 0 ? tot : computedTotal

    normalized.forEach((item) => {
      item.percentage = finalTotal > 0 ? (item.count / finalTotal) * 100 : 0
    })

    return { total: finalTotal, items: normalized }
  }, [statusData])

  // Calculate solid SVG Pie wedges (no inner donut hole)
  const slices = useMemo(() => {
    if (total <= 0) return []

    const cx = 100
    const cy = 100
    const rOut = 85
    let currentAngle = -Math.PI / 2 // Start at 12 o'clock

    return items
      .filter((item) => item.count > 0)
      .map((item) => {
        const fraction = item.count / total
        const sweep = fraction * 2 * Math.PI
        const startAngle = currentAngle
        const endAngle = currentAngle + sweep

        let path = ''
        if (fraction >= 0.9999) {
          // Full 360 circle solid pie
          path = `M ${cx} ${cy - rOut} A ${rOut} ${rOut} 0 1 1 ${cx} ${cy + rOut} A ${rOut} ${rOut} 0 1 1 ${cx} ${cy - rOut} Z`
        } else {
          const x1 = cx + rOut * Math.cos(startAngle)
          const y1 = cy + rOut * Math.sin(startAngle)
          const x2 = cx + rOut * Math.cos(endAngle)
          const y2 = cy + rOut * Math.sin(endAngle)

          const largeArc = sweep > Math.PI ? 1 : 0
          // Solid pie wedge: from center (cx, cy) to perimeter arc and back to center
          path = `M ${cx} ${cy} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${rOut} ${rOut} 0 ${largeArc} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`
        }

        currentAngle = endAngle

        return {
          ...item,
          path,
          fraction,
        }
      })
  }, [items, total])

  const handleStatusSelect = (key) => {
    if (!onStatusClick) return
    if (selectedStatus === key) {
      onStatusClick('') // Toggle off filter
    } else {
      onStatusClick(key)
    }
  }

  return (
    <div
      className={`grid grid-cols-1 items-center gap-6 sm:grid-cols-[200px_1fr] md:grid-cols-[220px_1fr] ${className}`}
      data-testid="project-status-pie-chart"
    >
      {/* Solid SVG Pie Chart (No Donut Hole) */}
      <div className="relative mx-auto flex h-[190px] w-[190px] items-center justify-center sm:h-[210px] sm:w-[210px]">
        {total > 0 && slices.length > 0 ? (
          <svg
            viewBox="0 0 200 200"
            className="h-full w-full drop-shadow-xs"
            role="img"
            aria-label={`Project implementation status pie chart: ${items.map((it) => `${it.label} ${it.count} (${formatPercent(it.percentage)})`).join(', ')}`}
          >
            {slices.map((slice) => {
              const isSelected = selectedStatus === slice.key
              const isHovered = hoveredStatus === slice.key
              const opacity =
                selectedStatus && !isSelected && !isHovered
                  ? 0.35
                  : isHovered || isSelected
                    ? 1
                    : 0.92

              return (
                <path
                  key={slice.key}
                  d={slice.path}
                  fill={isHovered ? slice.config.hoverColor : slice.config.color}
                  opacity={opacity}
                  className="cursor-pointer transition-all duration-150"
                  stroke="#ffffff"
                  strokeWidth={isSelected ? 2.5 : 1.5}
                  onClick={() => handleStatusSelect(slice.key)}
                  onMouseEnter={() => setHoveredStatus(slice.key)}
                  onMouseLeave={() => setHoveredStatus(null)}
                  data-testid={`pie-slice-${slice.key}`}
                >
                  <title>{`${slice.label}: ${formatNumber(slice.count)} (${formatPercent(slice.percentage)})`}</title>
                </path>
              )
            })}
          </svg>
        ) : (
          <div className="flex h-full w-full items-center justify-center rounded-full border-4 border-dashed border-slate-200 dark:border-slate-800">
            <span className="text-xs text-brand-text-muted">No projects</span>
          </div>
        )}
      </div>

      {/* Right: Total Portfolio Header + Flat Status Rows */}
      <div className="flex flex-col gap-2">
        <div className="mb-1 flex items-baseline justify-between border-b border-brand-border/40 pb-2">
          <span className="text-xs font-semibold text-brand-text-muted uppercase tracking-wider">Total Portfolio</span>
          <p className="text-lg font-bold tabular-nums text-brand-text" data-testid="pie-total-count">
            {formatNumber(total)} {total === 1 ? 'Project' : 'Projects'}
          </p>
        </div>

        <div className="flex flex-col gap-1">
          {items.map((item) => {
            const isSelected = selectedStatus === item.key
            const isHovered = hoveredStatus === item.key
            const isZero = item.count === 0

            return (
              <button
                key={item.key}
                type="button"
                onClick={() => handleStatusSelect(item.key)}
                onMouseEnter={() => setHoveredStatus(item.key)}
                onMouseLeave={() => setHoveredStatus(null)}
                className={`group flex items-center justify-between rounded-lg border px-3 py-2 text-left transition-all ${
                  isZero ? 'opacity-60 ' : ''
                }${
                  isSelected
                    ? 'border-brand-primary/50 bg-brand-primary/10 shadow-xs ring-1 ring-brand-primary'
                    : isHovered
                      ? 'border-transparent bg-slate-100/70 dark:bg-slate-800/60 shadow-xs'
                      : 'border-transparent bg-transparent hover:bg-slate-100/50 dark:hover:bg-slate-800/40'
                }`}
                aria-pressed={isSelected}
                data-testid={`pie-legend-${item.key}`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <span
                    className={`h-2.5 w-2.5 shrink-0 rounded-full transition-transform ${item.config.bgClass} ${
                      isHovered || isSelected ? 'scale-125' : ''
                    }`}
                    aria-hidden="true"
                  />
                  <span className="truncate text-xs font-semibold text-brand-text">
                    {item.label}
                  </span>
                  <span className="text-xs font-medium text-brand-text-muted">
                    {formatPercent(item.percentage)}
                  </span>
                </div>

                <div className="text-right pl-2 shrink-0">
                  <span className="text-sm font-bold tabular-nums text-brand-text">
                    {formatNumber(item.count)}
                  </span>
                  <span className="ml-1 text-[11px] text-brand-text-muted">
                    {item.count === 1 ? 'project' : 'projects'}
                  </span>
                </div>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
