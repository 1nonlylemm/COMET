import { useMemo } from 'react'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatPercent(value) {
  if (value === null) return 'Not reported'
  return `${Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })}%`
}

const PHASE_CONFIG = {
  pre_implementation: {
    color: 'bg-slate-500',
    card: 'border-slate-300 bg-slate-50/70 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900/40',
    text: 'text-slate-700 dark:text-slate-200 dark:text-slate-300',
  },
  implementation: {
    color: 'bg-blue-600',
    card: 'border-blue-200 bg-blue-50/60 hover:bg-blue-50 dark:border-blue-900/50 dark:bg-blue-950/20',
    text: 'text-blue-700 dark:text-blue-300',
  },
  completion: {
    color: 'bg-emerald-600',
    card: 'border-emerald-200 bg-emerald-50/60 hover:bg-emerald-50 dark:border-emerald-900/50 dark:bg-emerald-950/20',
    text: 'text-emerald-700 dark:text-emerald-300',
  },
}

const PROGRESS_BAND_TONE = {
  zero: { bg: 'bg-red-50 dark:bg-red-950/30', border: 'border-red-200 dark:border-red-800', bar: 'bg-red-500', text: 'text-red-700 dark:text-red-300' },
  early: { bg: 'bg-amber-50 dark:bg-amber-950/30', border: 'border-amber-200 dark:border-amber-800', bar: 'bg-amber-500', text: 'text-amber-700 dark:text-amber-300' },
  mid: { bg: 'bg-blue-50 dark:bg-blue-950/30', border: 'border-blue-200 dark:border-blue-800', bar: 'bg-blue-500', text: 'text-blue-700 dark:text-blue-300' },
  near_complete: { bg: 'bg-cyan-50 dark:bg-cyan-950/30', border: 'border-cyan-200 dark:border-cyan-800', bar: 'bg-cyan-500', text: 'text-cyan-700 dark:text-cyan-300' },
  complete: { bg: 'bg-emerald-50 dark:bg-emerald-950/30', border: 'border-emerald-200 dark:border-emerald-800', bar: 'bg-emerald-500', text: 'text-emerald-700 dark:text-emerald-300' },
}

export default function PortfolioProgressCard({
  phaseData = {},
  progressBands = [],
  selectedPhase = null,
  selectedBand = null,
  onPhaseSelect,
  onBandSelect,
  emptyMessage = 'No portfolio progress or phase distribution records available.',
}) {
  const { total_projects = 0, phases = [] } = phaseData

  const { nonZeroBands, zeroBands } = useMemo(() => {
    const nonZero = []
    const zero = []
    progressBands.forEach((b) => {
      if ((b.count || 0) > 0) {
        nonZero.push(b)
      } else {
        zero.push(b)
      }
    })
    return { nonZeroBands: nonZero, zeroBands: zero }
  }, [progressBands])

  const isEmpty = !total_projects && (!phases || phases.length === 0) && (!progressBands || progressBands.length === 0)

  if (isEmpty) {
    return (
      <div className="py-8 text-center text-sm text-brand-text-muted">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* ── ROW 1: LIFECYCLE PHASE DISTRIBUTION ── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between text-xs">
          <span className="font-semibold text-brand-text uppercase tracking-wider text-[11px]">
            Lifecycle Phase Distribution
          </span>
          <span className="text-brand-text-muted">
            {formatNumber(total_projects)} Total Projects
          </span>
        </div>

        {/* Segmented Phase Bar */}
        <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800 flex shadow-inner">
          {phases.map((p, idx) => {
            if (!p.count || !total_projects) return null
            const phaseKey = p.phase || p.key || `phase-${idx}`
            const pct = ((p.count / total_projects) * 100)
            const cfg = PHASE_CONFIG[phaseKey] || { color: 'bg-slate-400' }
            const isSelected = selectedPhase === phaseKey
            const isClickable = Boolean(onPhaseSelect)

            return (
              <div
                key={phaseKey}
                onClick={() => isClickable && onPhaseSelect(isSelected ? null : phaseKey)}
                className={`${cfg.color} h-full transition-all duration-300 ${
                  isClickable ? 'cursor-pointer hover:brightness-110' : ''
                } ${isSelected ? 'ring-2 ring-brand-primary' : ''}`}
                style={{ width: `${pct}%` }}
                title={`${p.label}: ${formatNumber(p.count)} (${formatPercent(p.percentage)})`}
              />
            )
          })}
        </div>

        {/* Phase Cards Grid */}
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
          {phases.map((p, idx) => {
            const phaseKey = p.phase || p.key || `phase-${idx}`
            const cfg = PHASE_CONFIG[phaseKey] || {
              color: 'bg-slate-400',
              card: 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800',
              text: 'text-slate-700 dark:text-slate-200',
            }
            const isClickable = Boolean(onPhaseSelect)
            const isSelected = selectedPhase === phaseKey

            return (
              <button
                key={phaseKey}
                type="button"
                data-testid={`phase-${phaseKey}`}
                onClick={() => isClickable && onPhaseSelect(isSelected ? null : phaseKey)}
                className={`flex items-center justify-between rounded-xl border p-3 text-left transition-all ${cfg.card} ${
                  isClickable ? 'cursor-pointer hover:shadow-xs' : ''
                } ${isSelected ? 'ring-2 ring-brand-primary ring-offset-1 font-semibold shadow-xs' : ''}`}
                title={`Filter projects by ${p.label}`}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className={`h-2.5 w-2.5 rounded-full ${cfg.color}`} />
                    <span className="text-xs font-semibold text-brand-text truncate">
                      {p.label}
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] text-brand-text-muted">
                    {formatPercent(p.percentage)} of portfolio
                  </div>
                </div>

                <div className="text-right shrink-0">
                  <div className={`text-base font-bold tabular-nums ${cfg.text}`}>
                    {formatNumber(p.count)}
                  </div>
                  {isSelected && (
                    <span className="text-[10px] font-bold text-brand-primary uppercase">
                      Filtered
                    </span>
                  )}
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* ── ROW 2: PHYSICAL ACCOMPLISHMENT BANDS ── */}
      <div className="space-y-3 pt-3 border-t border-brand-border/60">
        <div className="flex items-center justify-between text-xs">
          <span className="font-semibold text-brand-text uppercase tracking-wider text-[11px]">
            Physical Accomplishment Bands
          </span>
          <span className="text-brand-text-muted">
            Click band to filter project records
          </span>
        </div>

        {/* Non-Zero Bands Cards */}
        {nonZeroBands.length > 0 && (
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 xl:grid-cols-5">
            {nonZeroBands.map((band) => {
              const tone = PROGRESS_BAND_TONE[band.key] || PROGRESS_BAND_TONE.mid
              const isSelected = selectedBand === band.key
              const isClickable = Boolean(onBandSelect)

              return (
                <button
                  key={band.key}
                  type="button"
                  data-testid={`progress-band-${band.key}`}
                  onClick={() => isClickable && onBandSelect(isSelected ? null : band.key)}
                  className={`rounded-lg border p-3 text-left transition-all ${tone.bg} ${tone.border} ${
                    isClickable ? 'cursor-pointer hover:shadow-xs' : ''
                  } ${isSelected ? 'ring-2 ring-brand-primary ring-offset-1 font-semibold shadow-xs' : ''}`}
                  title={`Filter projects by ${band.label}`}
                >
                  <div className="mb-1 flex items-baseline justify-between gap-1.5">
                    <span className={`text-[11px] font-semibold uppercase tracking-wide truncate ${tone.text}`}>
                      {band.label}
                    </span>
                    <span className={`tabular-nums text-xs font-medium ${tone.text} opacity-70 shrink-0`}>
                      {formatPercent(band.percentage)}
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between">
                    <p className="text-xl font-bold text-brand-text tabular-nums">{formatNumber(band.count)}</p>
                    {isSelected && (
                      <span className="text-[10px] font-bold text-brand-primary uppercase">
                        Filtered
                      </span>
                    )}
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-black/10 dark:bg-white/10">
                    <div
                      className={`h-full ${tone.bar}`}
                      style={{ width: `${Math.max(0, Number(band.percentage || 0))}%` }}
                    />
                  </div>
                </button>
              )
            })}
          </div>
        )}

        {/* Zero Bands Rendered as Compact Muted Chips */}
        {zeroBands.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-[11px] text-brand-text-muted">Zero projects:</span>
            {zeroBands.map((band) => (
              <span
                key={band.key}
                className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/30 px-2 py-0.5 text-xs text-brand-text-muted opacity-60"
                title={`${band.label}: 0 projects`}
              >
                <span>{band.label}</span>
                <span className="font-semibold tabular-nums">0</span>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
