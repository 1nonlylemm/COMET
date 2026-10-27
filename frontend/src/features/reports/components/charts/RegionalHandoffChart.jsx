import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileCheck2,
  HardDrive,
  Info,
  ListFilter,
  RefreshCw,
  Send,
  UploadCloud,
  XCircle,
} from 'lucide-react'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatPercent(value) {
  return `${Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })}%`
}

const STATUS_CONFIG = {
  completed: {
    label: 'Completed',
    color: 'bg-emerald-500',
    card: 'border-emerald-200 bg-emerald-50/50 hover:bg-emerald-50 dark:border-emerald-900/50 dark:bg-emerald-950/20',
    text: 'text-emerald-700 dark:text-emerald-300',
    ring: 'ring-emerald-500',
    icon: CheckCircle2,
    badge: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
  },
  in_progress: {
    label: 'In Progress',
    color: 'bg-amber-500',
    card: 'border-amber-200 bg-amber-50/50 hover:bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20',
    text: 'text-amber-700 dark:text-amber-300',
    ring: 'ring-amber-500',
    icon: RefreshCw,
    badge: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200',
  },
  pending: {
    label: 'Pending',
    color: 'bg-yellow-500',
    card: 'border-yellow-200 bg-yellow-50/50 hover:bg-yellow-50 dark:border-yellow-900/50 dark:bg-yellow-950/20',
    text: 'text-yellow-800 dark:text-yellow-300',
    ring: 'ring-yellow-500',
    icon: Clock,
    badge: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-200',
  },
  failed: {
    label: 'Failed',
    color: 'bg-rose-500',
    card: 'border-rose-200 bg-rose-50/50 hover:bg-rose-50 dark:border-rose-900/50 dark:bg-rose-950/20',
    text: 'text-rose-700 dark:text-rose-300',
    ring: 'ring-rose-500',
    icon: XCircle,
    badge: 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200',
  },
}

export default function RegionalHandoffChart({
  handoffData = {},
  selectedStatus = null,
  onStatusSelect,
  onViewTransmissionsClick,
  emptyMessage = 'No regional handoff transmission telemetry available for current scope.',
}) {
  const {
    total_events = 0,
    distinct_projects_transmitted = 0,
    total_files_pushed = 0,
    projects_all_completed = 0,
    projects_with_failures = 0,
    statuses = [],
  } = handoffData

  if (!total_events && (!statuses || statuses.length === 0)) {
    return (
      <div className="py-8 text-center text-sm text-brand-text-muted">
        {emptyMessage}
      </div>
    )
  }

  const handleStatusClick = (statusKey) => {
    if (onStatusSelect) {
      onStatusSelect(selectedStatus === statusKey ? null : statusKey)
    }
  }

  return (
    <div className="space-y-4">
      {/* Header Info & Metrics */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-1.5 text-brand-text-muted">
          <UploadCloud className="h-3.5 w-3.5 shrink-0 text-brand-primary" />
          <span>Automated & manual push events to Google Drive DMS repository (Transmission Status, distinct from Regional Approval)</span>
        </div>
        <div className="flex flex-wrap items-center gap-3 font-semibold text-brand-text">
          <span>
            Total Push Events: <strong className="tabular-nums text-brand-text">{formatNumber(total_events)}</strong>
          </span>
          <span className="text-slate-300 dark:text-slate-700">•</span>
          <span>
            Transmitted Projects: <strong className="tabular-nums text-brand-primary">{formatNumber(distinct_projects_transmitted)}</strong>
          </span>
          <span className="text-slate-300 dark:text-slate-700">•</span>
          <span>
            Files Pushed: <strong className="tabular-nums text-emerald-700 dark:text-emerald-400">{formatNumber(total_files_pushed)}</strong>
          </span>
        </div>
      </div>

      {/* Status Cards Grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {statuses.map((st) => {
          const cfg = STATUS_CONFIG[st.status] || {
            label: st.label,
            icon: CheckCircle2,
            card: 'border-brand-border bg-brand-surface',
            text: 'text-brand-text',
            ring: 'ring-brand-primary',
          }
          const IconComponent = cfg.icon
          const isSelected = selectedStatus === st.status
          const count = st.count || 0

          return (
            <button
              key={st.status}
              type="button"
              onClick={() => handleStatusClick(st.status)}
              className={`flex flex-col justify-between rounded-xl border p-4 text-left transition-all ${cfg.card} ${
                isSelected ? `ring-2 ${cfg.ring} shadow-md scale-[1.02]` : 'hover:shadow-sm'
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className={`rounded-lg p-1.5 bg-white/80 dark:bg-black/20 ${cfg.text}`}>
                    <IconComponent className="h-4 w-4" />
                  </span>
                  <span className="text-xs font-semibold tabular-nums text-brand-text-muted">
                    {formatPercent(st.percentage)}
                  </span>
                </div>
                <div className="text-xs font-medium text-brand-text-muted">{cfg.label}</div>
                <div className="mt-1 text-2xl font-bold tabular-nums text-brand-text">
                  {formatNumber(count)}
                </div>
              </div>
              <div className="mt-3 flex items-center justify-between text-[11px] font-medium text-brand-text-muted">
                <span>{st.project_count} {st.project_count === 1 ? 'project' : 'projects'}</span>
                <span className="text-brand-primary text-[10px] uppercase tracking-wider font-semibold">
                  {isSelected ? 'Active' : 'Filter'}
                </span>
              </div>
            </button>
          )
        })}
      </div>

      {/* Transmission Health & Actions Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-brand-border bg-brand-surface p-4 shadow-xs">
        <div className="flex flex-wrap items-center gap-4 text-xs font-medium">
          <span className="flex items-center gap-1.5 text-emerald-700 dark:text-emerald-400">
            <CheckCircle2 className="h-4 w-4" />
            <span>{projects_all_completed} Projects Fully Completed</span>
          </span>
          <span className="text-slate-300 dark:text-slate-700">•</span>
          <span className={`flex items-center gap-1.5 ${projects_with_failures > 0 ? 'text-rose-700 dark:text-rose-400 font-semibold' : 'text-brand-text-muted'}`}>
            <AlertTriangle className="h-4 w-4" />
            <span>{projects_with_failures} Projects with Push Failures</span>
          </span>
          <span className="text-slate-300 dark:text-slate-700">•</span>
          <span className="flex items-center gap-1.5 text-brand-text-muted">
            <HardDrive className="h-4 w-4" />
            <span>{total_files_pushed} Files Archived to Cloud</span>
          </span>
        </div>

        <div className="flex items-center gap-2">
          {selectedStatus && (
            <button
              type="button"
              onClick={() => handleStatusClick(selectedStatus)}
              className="rounded-lg border border-brand-border bg-brand-surface px-3 py-1.5 text-xs font-semibold text-brand-text hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors shadow-xs"
            >
              Clear status filter ({STATUS_CONFIG[selectedStatus]?.label || selectedStatus})
            </button>
          )}
          <button
            type="button"
            onClick={onViewTransmissionsClick}
            className="inline-flex items-center gap-1.5 rounded-lg bg-brand-primary px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-brand-primary/90 transition-colors shadow-xs dark:text-slate-950"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            <span>View Transmission Logs ({formatNumber(total_events)})</span>
          </button>
        </div>
      </div>
    </div>
  )
}
