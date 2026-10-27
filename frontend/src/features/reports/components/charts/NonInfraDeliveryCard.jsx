import {
  CheckCircle2,
  FileCheck2,
  FileSpreadsheet,
  FileText,
  Filter,
  Info,
  Package,
  Truck,
  Users,
  XCircle,
} from 'lucide-react'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatPercent(value) {
  return `${Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })}%`
}

const SPEC_STYLE_CONFIG = {
  met: {
    color: 'bg-emerald-500',
    card: 'border-emerald-200 bg-emerald-50/50 dark:border-emerald-900/50 dark:bg-emerald-950/20',
    text: 'text-emerald-700 dark:text-emerald-300',
    icon: CheckCircle2,
  },
  not_met: {
    color: 'bg-rose-500',
    card: 'border-rose-200 bg-rose-50/50 dark:border-rose-900/50 dark:bg-rose-950/20',
    text: 'text-rose-700 dark:text-rose-300',
    icon: XCircle,
  },
  pending: {
    color: 'bg-amber-500',
    card: 'border-amber-200 bg-amber-50/50 dark:border-amber-900/50 dark:bg-amber-950/20',
    text: 'text-amber-700 dark:text-amber-300',
    icon: Info,
  },
}

export function NonInfraDeliveryCard({
  nonInfraData = {},
  selectedFilter = null,
  onFilterSelect,
  emptyMessage = 'No non-infrastructure monitoring records found in visible portfolio.',
}) {
  const {
    total_non_infra_projects = 0,
    total_monitoring_records = 0,
    total_evidence_records = 0,
    total_beneficiaries_assisted = 0,
    specifications_summary = {},
    specifications_distribution = [],
    evidence_types = [],
  } = nonInfraData

  if (!total_non_infra_projects && total_monitoring_records === 0 && total_evidence_records === 0) {
    return (
      <div className="py-8 text-center text-sm text-brand-text-muted">
        {emptyMessage}
      </div>
    )
  }

  const handleFilterClick = (filterKey) => {
    if (onFilterSelect) {
      onFilterSelect(selectedFilter === filterKey ? null : filterKey)
    }
  }

  return (
    <div className="space-y-4">
      {/* Metric Cards Row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl border border-brand-border bg-brand-surface p-3 shadow-xs">
          <div className="flex items-center gap-2 text-brand-text-muted">
            <Package className="h-4 w-4 text-brand-primary" />
            <span className="text-xs font-semibold">Non-Infra Projects</span>
          </div>
          <div className="mt-2 text-xl font-bold tabular-nums text-brand-text">
            {formatNumber(total_non_infra_projects)}
          </div>
          <div className="mt-1 text-[11px] text-brand-text-muted">
            Goods, Vehicles, Assistance
          </div>
        </div>

        <div className="rounded-xl border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50/40 dark:bg-emerald-950/20 p-3 shadow-xs">
          <div className="flex items-center gap-2 text-emerald-800 dark:text-emerald-300">
            <Users className="h-4 w-4 text-emerald-700 dark:text-emerald-400" />
            <span className="text-xs font-semibold">Recorded beneficiary counts</span>
          </div>
          <div className="mt-2 text-xl font-bold tabular-nums text-emerald-700 dark:text-emerald-300">
            {formatNumber(total_beneficiaries_assisted)}
          </div>
          <div className="mt-1 text-[11px] text-emerald-700 dark:text-emerald-400/80">
            Sum across evidence records; not unique people
          </div>
        </div>

        <div className="rounded-xl border border-brand-border bg-brand-surface p-3 shadow-xs">
          <div className="flex items-center gap-2 text-brand-text-muted">
            <FileSpreadsheet className="h-4 w-4 text-brand-primary" />
            <span className="text-xs font-semibold">Monitoring Records</span>
          </div>
          <div className="mt-2 text-xl font-bold tabular-nums text-brand-text">
            {formatNumber(total_monitoring_records)}
          </div>
          <div className="mt-1 text-[11px] text-brand-text-muted">
            APM & Appendix templates
          </div>
        </div>

        <div className="rounded-xl border border-brand-border bg-brand-surface p-3 shadow-xs">
          <div className="flex items-center gap-2 text-brand-text-muted">
            <FileCheck2 className="h-4 w-4 text-brand-primary" />
            <span className="text-xs font-semibold">Evidence Documents</span>
          </div>
          <div className="mt-2 text-xl font-bold tabular-nums text-brand-text">
            {formatNumber(total_evidence_records)}
          </div>
          <div className="mt-1 text-[11px] text-brand-text-muted">
            Signed lists, receipts, photos
          </div>
        </div>
      </div>

      <p className="text-xs text-brand-text-muted">Specification buckets count records. A project can appear in multiple buckets; its overall recorded status can differ.</p>
      {/* Specifications Met Distribution */}
      <div className="rounded-xl border border-brand-border bg-brand-surface p-4 shadow-xs space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-brand-text">
            <CheckCircle2 className="h-4 w-4 text-emerald-700" />
            <span>Specifications Verification Status</span>
          </div>
          <div className="text-xs text-brand-text-muted">
            Specifications met (records):{' '}
            <strong className="text-emerald-700 dark:text-emerald-400 font-bold tabular-nums">
              {formatPercent(specifications_summary.compliance_rate)}
            </strong>
            {total_monitoring_records > 0 && (
              <span className="ml-1 text-[11px] text-brand-text-muted">
                ({formatNumber(total_monitoring_records)} records recorded)
              </span>
            )}
          </div>
        </div>

        {/* Segmented Bar */}
        <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800 flex shadow-inner">
          {specifications_distribution.map((item) => {
            if (!item.count || !total_monitoring_records) return null
            const pct = ((item.count / total_monitoring_records) * 100)
            const styleCfg = SPEC_STYLE_CONFIG[item.key] || SPEC_STYLE_CONFIG.pending

            return (
              <div
                key={item.key}
                className={`${styleCfg.color} h-full transition-all duration-300`}
                style={{ width: `${pct}%` }}
                title={`${item.label}: ${formatNumber(item.count)} (${formatPercent(item.percentage)})`}
              />
            )
          })}
        </div>

        {/* Specs Status Cards */}
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
          {specifications_distribution.map((item) => {
            const styleCfg = SPEC_STYLE_CONFIG[item.key] || SPEC_STYLE_CONFIG.pending
            const SpecIcon = styleCfg.icon
            const isSelected = selectedFilter === item.key

            return (
              <div
                key={item.key}
                onClick={() => handleFilterClick(item.key)}
                className={`flex items-center justify-between rounded-lg border p-2.5 transition-all ${
                  styleCfg.card
                } ${onFilterSelect ? 'cursor-pointer hover:shadow-xs' : ''} ${
                  isSelected ? 'ring-2 ring-brand-primary font-semibold' : ''
                }`}
                role={onFilterSelect ? 'button' : undefined}
                tabIndex={onFilterSelect ? 0 : undefined}
                onKeyDown={(e) => {
                  if (onFilterSelect && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault()
                    handleFilterClick(item.key)
                  }
                }}
              >
                <div className="flex items-center gap-2">
                  <SpecIcon className={`h-4 w-4 shrink-0 ${styleCfg.text}`} />
                  <div>
                    <div className="text-xs font-semibold text-brand-text">{item.label}</div>
                    <div className="text-[10px] text-brand-text-muted">
                      {formatPercent(item.percentage)}{item.project_count !== undefined ? ` • ${item.project_count} projects` : ''}
                    </div>
                  </div>
                </div>
                <div className={`text-base font-bold tabular-nums ${styleCfg.text}`}>
                  {formatNumber(item.count)}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Evidence Type Breakdown */}
      {evidence_types && evidence_types.length > 0 && (
        <div className="rounded-xl border border-brand-border bg-brand-surface p-4 shadow-xs">
          <h4 className="text-xs font-semibold text-brand-text mb-3">
            Delivery Evidence Types Breakdown
          </h4>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {evidence_types.map((et) => (
              <div
                key={et.key}
                className="flex items-center justify-between rounded-lg border border-brand-border/60 bg-slate-50/40 dark:bg-slate-900/30 p-2.5 text-xs"
              >
                <div className="min-w-0 pr-2">
                  <span className="font-medium text-brand-text truncate block">
                    {et.label}
                  </span>
                  <span className="text-[10px] text-brand-text-muted">
                    {formatNumber(et.beneficiary_count)} beneficiaries
                  </span>
                </div>
                <span className="rounded-full bg-brand-surface border border-brand-border px-2 py-0.5 font-bold tabular-nums text-brand-text text-[11px] shrink-0">
                  {formatNumber(et.record_count)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default NonInfraDeliveryCard
