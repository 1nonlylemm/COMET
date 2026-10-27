import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileQuestion,
  Gauge,
  Info,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatPercent(value) {
  return `${Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })}%`
}

const TIER_STYLE_CONFIG = {
  critical: {
    color: 'bg-rose-500',
    card: 'border-rose-200 bg-rose-50/50 hover:bg-rose-50 dark:border-rose-900/50 dark:bg-rose-950/20',
    text: 'text-rose-700 dark:text-rose-300',
    icon: AlertOctagon,
  },
  delayed: {
    color: 'bg-amber-500',
    card: 'border-amber-200 bg-amber-50/50 hover:bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20',
    text: 'text-amber-700 dark:text-amber-300',
    icon: AlertTriangle,
  },
  slightly_delayed: {
    color: 'bg-yellow-500',
    card: 'border-yellow-200 bg-yellow-50/50 hover:bg-yellow-50 dark:border-yellow-900/50 dark:bg-yellow-950/20',
    text: 'text-yellow-800 dark:text-yellow-300',
    icon: Clock,
  },
  on_track: {
    color: 'bg-emerald-500',
    card: 'border-emerald-200 bg-emerald-50/50 hover:bg-emerald-50 dark:border-emerald-900/50 dark:bg-emerald-950/20',
    text: 'text-emerald-700 dark:text-emerald-300',
    icon: CheckCircle2,
  },
  unreported: {
    color: 'bg-slate-400',
    card: 'border-slate-200 bg-slate-50/50 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900/40',
    text: 'text-slate-700 dark:text-slate-300',
    icon: FileQuestion,
  },
}

export function SlippageDistributionChart({
  slippageData = {},
  selectedTier = null,
  onTierSelect,
  emptyMessage = 'No infrastructure project slippage data available.',
}) {
  const {
    total_infrastructure_projects = 0,
    total_reported_projects = 0,
    average_variance_pct = 0.0,
    tiers = [],
  } = slippageData

  if (!total_infrastructure_projects && (!tiers || tiers.length === 0)) {
    return (
      <div className="py-8 text-center text-sm text-brand-text-muted">
        {emptyMessage}
      </div>
    )
  }

  const handleTierClick = (tierKey) => {
    if (onTierSelect) {
      onTierSelect(selectedTier === tierKey ? null : tierKey)
    }
  }

  const isPositiveVariance = Number(average_variance_pct) >= 0

  return (
    <div className="space-y-4">
      {/* Header Info & Metrics */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-1.5 text-brand-text-muted">
          <Info className="h-3.5 w-3.5 shrink-0" />
          <span>Physical slippage based on latest Monthly Progress Report (MPR) per infrastructure project</span>
        </div>
        <div className="flex flex-wrap items-center gap-3 font-semibold text-brand-text">
          <span>
            Infra Projects: <strong className="tabular-nums text-brand-primary">{formatNumber(total_infrastructure_projects)}</strong>
          </span>
          <span className="text-slate-300 dark:text-slate-700">•</span>
          <span>
            Reported: <strong className="tabular-nums text-brand-text">{formatNumber(total_reported_projects)}</strong>
          </span>
          <span className="text-slate-300 dark:text-slate-700">•</span>
          <span className="flex items-center gap-1">
            Avg variance (actual − target):{' '}
            <strong
              className={`inline-flex items-center gap-0.5 tabular-nums ${
                !total_reported_projects ? 'text-brand-text-muted' : isPositiveVariance ? 'text-emerald-700 dark:text-emerald-400' : 'text-rose-700 dark:text-rose-400'
              }`}
            >
              {total_reported_projects > 0 && (isPositiveVariance ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />)}
              {!total_reported_projects ? 'Not reported' : average_variance_pct > 0 ? `+${average_variance_pct} pp` : `${average_variance_pct} pp`}
            </strong>
          </span>
        </div>
      </div>

      {/* Segmented Distribution Bar */}
      <div className="h-3.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800 flex shadow-inner">
        {tiers.map((t) => {
          if (!t.count || !total_infrastructure_projects) return null
          const pct = ((t.count / total_infrastructure_projects) * 100)
          const styleCfg = TIER_STYLE_CONFIG[t.tier] || TIER_STYLE_CONFIG.unreported
          const isSelected = selectedTier === t.tier

          return (
            <div
              key={t.tier}
              className={`${styleCfg.color} h-full transition-all duration-300 ${
                isSelected ? 'brightness-110 ring-2 ring-brand-primary' : ''
              }`}
              style={{ width: `${pct}%` }}
              title={`${t.label}: ${formatNumber(t.count)} (${formatPercent(t.percentage)})`}
            />
          )
        })}
      </div>

      {/* Interactive Tier Cards */}
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-5">
        {tiers.map((t) => {
          const styleCfg = TIER_STYLE_CONFIG[t.tier] || TIER_STYLE_CONFIG.unreported
          const isSelected = selectedTier === t.tier
          const isClickable = Boolean(onTierSelect)
          const TierIcon = styleCfg.icon

          return (
            <div
              key={t.tier}
              onClick={() => isClickable && handleTierClick(t.tier)}
              className={`relative flex flex-col justify-between rounded-xl border p-3 transition-all ${
                styleCfg.card
              } ${isClickable ? 'cursor-pointer hover:shadow-sm' : ''} ${
                isSelected ? 'ring-2 ring-brand-primary ring-offset-2 font-semibold shadow-sm' : ''
              }`}
              role={isClickable ? 'button' : undefined}
              tabIndex={isClickable ? 0 : undefined}
              onKeyDown={(e) => {
                if (isClickable && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault()
                  handleTierClick(t.tier)
                }
              }}
              title={isClickable ? `Click to filter projects in ${t.label}` : t.label}
            >
              <div className="flex items-start justify-between gap-1.5">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className={`h-2.5 w-2.5 rounded-full shrink-0 ${styleCfg.color}`} />
                  <span className="text-xs font-semibold text-brand-text truncate">
                    {t.short_label || t.label}
                  </span>
                </div>
                <TierIcon className={`h-3.5 w-3.5 shrink-0 ${styleCfg.text}`} />
              </div>

              <div className="mt-2 text-[11px] text-brand-text-muted">
                Variance: <span className="font-medium text-brand-text">{t.range}</span>
              </div>

              <div className="mt-2 flex items-baseline justify-between border-t border-brand-border/40 pt-2">
                <span className={`text-base font-bold tabular-nums ${styleCfg.text}`}>
                  {formatNumber(t.count)}
                </span>
                <span className="text-[11px] text-brand-text-muted tabular-nums">
                  {formatPercent(t.percentage)}
                </span>
              </div>

              {isSelected && (
                <div className="mt-1 text-right text-[10px] font-bold text-brand-primary">
                  Filter Active ✓
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default SlippageDistributionChart
