import { useMemo } from 'react'
import {
  AlertOctagon,
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Clock,
  ExternalLink,
  Flame,
  HeartPulse,
  Info,
  ShieldAlert,
} from 'lucide-react'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatPercent(value) {
  return `${Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })}%`
}

const SLA_TONE_CONFIG = {
  danger: {
    bg: 'bg-rose-500',
    card: 'border-rose-200 bg-rose-50/50 hover:bg-rose-50 dark:border-rose-900/50 dark:bg-rose-950/20',
    text: 'text-rose-700 dark:text-rose-300',
    icon: Flame,
  },
  amber: {
    bg: 'bg-amber-500',
    card: 'border-amber-200 bg-amber-50/50 hover:bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20',
    text: 'text-amber-700 dark:text-amber-300',
    icon: AlertOctagon,
  },
  warning: {
    bg: 'bg-yellow-500',
    card: 'border-yellow-200 bg-yellow-50/50 hover:bg-yellow-50 dark:border-yellow-900/50 dark:bg-yellow-950/20',
    text: 'text-yellow-800 dark:text-yellow-300',
    icon: Clock,
  },
  info: {
    bg: 'bg-blue-500',
    card: 'border-blue-200 bg-blue-50/50 hover:bg-blue-50 dark:border-blue-900/50 dark:bg-blue-950/20',
    text: 'text-blue-700 dark:text-blue-300',
    icon: Calendar,
  },
  neutral: {
    bg: 'bg-slate-400',
    card: 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/50 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900/40',
    text: 'text-slate-700 dark:text-slate-200 dark:text-slate-300',
    icon: CheckCircle2,
  },
}

export function SlaUrgencyDistribution({
  slaData = {},
  onBucketClick,
  emptyMessage = 'No active SLA deadlines found.',
}) {
  const { total_active = 0, buckets = [] } = slaData

  if (!total_active && (!buckets || buckets.length === 0)) {
    return (
      <div className="py-8 text-center text-sm text-brand-text-muted">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header Info */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-1.5 text-brand-text-muted">
          <Info className="h-3.5 w-3.5" />
          <span>Active, non-suppressed deadlines partitioned by working-day proximity</span>
        </div>
        <div className="font-semibold text-brand-text">
          Total Active: <span className="tabular-nums font-bold text-brand-primary">{formatNumber(total_active)}</span>
        </div>
      </div>

      {/* Segmented Distribution Strip */}
      <div className="h-3.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800 flex">
        {total_active > 0 ? (
          buckets.map((b) => {
            const count = b.count || 0
            if (!count) return null
            const pct = (count / total_active) * 100
            const toneCfg = SLA_TONE_CONFIG[b.tone] || SLA_TONE_CONFIG.neutral
            return (
              <div
                key={b.key}
                className={`${toneCfg.bg} h-full transition-all duration-300`}
                style={{ width: `${pct}%` }}
                title={`${b.label}: ${formatNumber(count)} (${formatPercent(pct)})`}
              />
            )
          })
        ) : (
          <div className="h-full w-full bg-slate-200 dark:bg-slate-700" />
        )}
      </div>

      {/* Interactive Bucket Cards */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {buckets.map((b) => {
          const toneCfg = SLA_TONE_CONFIG[b.tone] || SLA_TONE_CONFIG.neutral
          const Icon = toneCfg.icon
          const isClickable = Boolean(onBucketClick)

          return (
            <div
              key={b.key}
              onClick={() => isClickable && onBucketClick(b)}
              className={`rounded-lg border p-3 transition-all ${toneCfg.card} ${
                isClickable ? 'cursor-pointer hover:shadow-sm' : ''
              }`}
              role={isClickable ? 'button' : undefined}
              tabIndex={isClickable ? 0 : undefined}
            >
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="font-semibold text-brand-text truncate">{b.label}</span>
                <Icon className={`h-3.5 w-3.5 shrink-0 ${toneCfg.text}`} />
              </div>
              <div className="mt-1 flex items-baseline justify-between gap-1">
                <span className={`text-xl font-bold tabular-nums ${toneCfg.text}`}>
                  {formatNumber(b.count)}
                </span>
                <span className="text-xs font-medium text-brand-text-muted tabular-nums">
                  {formatPercent(b.percentage)}
                </span>
              </div>
              {isClickable && (
                <div className="mt-2 flex items-center gap-1 text-[11px] text-brand-primary opacity-80 hover:opacity-100">
                  <span>View in SLA Tracker</span>
                  <ExternalLink className="h-3 w-3" />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

const HEALTH_CONFIG = {
  healthy: {
    color: 'bg-emerald-500',
    card: 'border-emerald-200 bg-emerald-50/50 hover:bg-emerald-50 dark:border-emerald-900/50 dark:bg-emerald-950/20',
    text: 'text-emerald-700 dark:text-emerald-300',
  },
  at_risk: {
    color: 'bg-amber-500',
    card: 'border-amber-200 bg-amber-50/50 hover:bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20',
    text: 'text-amber-700 dark:text-amber-300',
  },
  critical: {
    color: 'bg-rose-500',
    card: 'border-rose-200 bg-rose-50/50 hover:bg-rose-50 dark:border-rose-900/50 dark:bg-rose-950/20',
    text: 'text-rose-700 dark:text-rose-300',
  },
}

export function ProjectHealthDistribution({
  healthData = {},
  onCategorySelect,
  selectedCategory = null,
  emptyMessage = 'No project health data available.',
}) {
  const {
    total_projects = 0,
    average_score = 0,
    categories = {},
    risk_factors = [],
  } = healthData

  const catList = useMemo(() => {
    return [
      { key: 'healthy', ...(categories.healthy || { count: 0, percentage: 0, label: 'Healthy (80-100)' }) },
      { key: 'at_risk', ...(categories.at_risk || { count: 0, percentage: 0, label: 'At Risk (40 to <80)' }) },
      { key: 'critical', ...(categories.critical || { count: 0, percentage: 0, label: 'Critical (0 to <40)' }) },
    ]
  }, [categories])

  if (!total_projects) {
    return (
      <div className="py-8 text-center text-sm text-brand-text-muted">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header Info: Average Health Score & Total */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2">
          <HeartPulse className="h-4 w-4 text-brand-primary" />
          <span className="font-medium text-brand-text">Average Health Score:</span>
          <span className="rounded-md bg-brand-surface-solid px-2 py-0.5 font-bold tabular-nums text-brand-text border border-brand-border">
            {average_score == null ? 'Not assessed' : `${average_score} / 100`}
          </span>
        </div>
        <div className="text-brand-text-muted">
          Projects Monitored: <span className="font-bold text-brand-text tabular-nums">{formatNumber(total_projects)}</span>
        </div>
      </div>

      {/* Distribution Strip */}
      <div className="h-3.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800 flex">
        {total_projects > 0 ? (
          catList.map((cat) => {
            const count = cat.count || 0
            if (!count) return null
            const pct = (count / total_projects) * 100
            const cfg = HEALTH_CONFIG[cat.key] || HEALTH_CONFIG.healthy
            return (
              <div
                key={cat.key}
                className={`${cfg.color} h-full transition-all duration-300`}
                style={{ width: `${pct}%` }}
                title={`${cat.label}: ${formatNumber(count)} (${formatPercent(pct)})`}
              />
            )
          })
        ) : (
          <div className="h-full w-full bg-slate-200 dark:bg-slate-700" />
        )}
      </div>

      {/* 3 Health Tier Cards */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {catList.map((cat) => {
          const cfg = HEALTH_CONFIG[cat.key] || HEALTH_CONFIG.healthy
          const isClickable = Boolean(onCategorySelect)
          const isSelected = selectedCategory === cat.key

          return (
            <div
              key={cat.key}
              onClick={() => isClickable && onCategorySelect(cat.key)}
              className={`rounded-lg border p-3.5 transition-all ${cfg.card} ${
                isSelected
                  ? 'ring-2 ring-brand-primary shadow-sm border-brand-primary'
                  : ''
              } ${
                isClickable ? 'cursor-pointer hover:shadow-sm' : ''
              }`}
              role={isClickable ? 'button' : undefined}
              tabIndex={isClickable ? 0 : undefined}
              onKeyDown={(e) => {
                if (isClickable && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault()
                  onCategorySelect(cat.key)
                }
              }}
              title={`Filter projects by ${cat.label} (${formatNumber(cat.count)} projects)`}
              aria-label={`Health tier ${cat.label}: ${formatNumber(cat.count)} projects`}
            >
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="font-semibold text-brand-text">{cat.label}</span>
                <span className={`h-2.5 w-2.5 rounded-full ${cfg.color}`} />
              </div>
              <div className="mt-2 flex items-baseline justify-between gap-1">
                <span className={`text-2xl font-bold tabular-nums ${cfg.text}`}>
                  {formatNumber(cat.count)}
                </span>
                <span className="text-xs font-semibold text-brand-text-muted tabular-nums">
                  {formatPercent(cat.percentage)}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Risk Factors Breakdown */}
      {risk_factors && risk_factors.length > 0 && (
        <div className="mt-3 border-t border-brand-border/60 pt-3">
          <div className="mb-2 text-xs font-semibold text-brand-text">
            Active Risk & Remediation Factors
          </div>
          <div className="flex flex-wrap gap-2">
            {risk_factors.map((rf) => (
              <div
                key={rf.key}
                className="flex items-center gap-1.5 rounded-md border border-brand-border bg-brand-surface px-2.5 py-1 text-xs text-brand-text"
              >
                <span
                  className={`h-2 w-2 rounded-full ${
                    rf.tone === 'danger'
                      ? 'bg-rose-500'
                      : rf.tone === 'warning'
                      ? 'bg-amber-500'
                      : 'bg-blue-500'
                  }`}
                />
                <span>{rf.label}</span>
                <span className="ml-1 rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.2 font-bold tabular-nums text-[10px]">
                  {formatNumber(rf.count)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const PHASE_CONFIG = {
  pre_implementation: {
    color: 'bg-sky-500',
    card: 'border-sky-200 bg-sky-50/50 hover:bg-sky-50 dark:border-sky-900/50 dark:bg-sky-950/20',
    text: 'text-sky-700 dark:text-sky-300',
  },
  implementation: {
    color: 'bg-amber-500',
    card: 'border-amber-200 bg-amber-50/50 hover:bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20',
    text: 'text-amber-700 dark:text-amber-300',
  },
  completion: {
    color: 'bg-emerald-500',
    card: 'border-emerald-200 bg-emerald-50/50 hover:bg-emerald-50 dark:border-emerald-900/50 dark:bg-emerald-950/20',
    text: 'text-emerald-700 dark:text-emerald-300',
  },
}

export function ProjectPhaseDistribution({
  phaseData = {},
  selectedPhase = null,
  onPhaseClick,
  onPhaseSelect,
  emptyMessage = 'No project phase data available.',
}) {
  const { total_projects = 0, phases = [] } = phaseData
  const handleSelect = onPhaseSelect || onPhaseClick

  if (!total_projects && (!phases || phases.length === 0)) {
    return (
      <div className="py-8 text-center text-sm text-brand-text-muted">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Segmented Bar */}
      <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800 flex shadow-inner">
        {phases.map((p, idx) => {
          if (!p.count || !total_projects) return null
          const phaseKey = p.phase || p.key || `phase-${idx}`
          const pct = ((p.count / total_projects) * 100)
          const cfg = PHASE_CONFIG[phaseKey] || { color: 'bg-slate-400' }
          const isSelected = selectedPhase === phaseKey

          return (
            <div
              key={phaseKey}
              className={`${cfg.color} h-full transition-all duration-300 ${isSelected ? 'brightness-110 ring-2 ring-brand-primary' : ''}`}
              style={{ width: `${pct}%` }}
              title={`${p.label}: ${formatNumber(p.count)} (${formatPercent(p.percentage)})`}
            />
          )
        })}
      </div>

      {/* Tier Cards Grid */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {phases.map((p, idx) => {
          const phaseKey = p.phase || p.key || `phase-${idx}`
          const cfg = PHASE_CONFIG[phaseKey] || {
            color: 'bg-slate-400',
            card: 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800',
            text: 'text-slate-700 dark:text-slate-200',
          }
          const isClickable = Boolean(handleSelect)
          const isSelected = selectedPhase === phaseKey

          return (
            <div
              key={phaseKey}
              onClick={() => isClickable && handleSelect(isSelected ? null : phaseKey)}
              className={`flex items-center justify-between rounded-xl border p-3 transition-all ${cfg.card} ${
                isClickable ? 'cursor-pointer hover:shadow-sm' : ''
              } ${isSelected ? 'ring-2 ring-brand-primary ring-offset-2 font-semibold shadow-sm' : ''}`}
              role={isClickable ? 'button' : undefined}
              tabIndex={isClickable ? 0 : undefined}
              onKeyDown={(e) => {
                if (isClickable && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault()
                  handleSelect(isSelected ? null : phaseKey)
                }
              }}
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
                  <span className="text-[10px] font-bold text-brand-primary">
                    Filtered
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

