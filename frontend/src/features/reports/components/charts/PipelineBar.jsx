import { useMemo } from 'react'
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Clock,
  FileCheck,
  FileSearch,
  FileText,
  RotateCcw,
  Send,
  ShieldCheck,
} from 'lucide-react'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatPercent(value) {
  return `${Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })}%`
}

const STAGE_ICONS = {
  draft: FileText,
  submitted: Send,
  under_verification: FileSearch,
  staff_approved: FileCheck,
  pending_provincial_approval: Clock,
  approved: CheckCircle2,
  returned_for_revision: AlertCircle,
  resubmitted: RotateCcw,
}

const STAGE_THEMES = {
  draft: {
    badge: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    bar: 'bg-slate-400',
    border: 'border-slate-200 dark:border-slate-700',
  },
  submitted: {
    badge: 'bg-blue-50 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300',
    bar: 'bg-blue-400',
    border: 'border-blue-200 dark:border-blue-800',
  },
  under_verification: {
    badge: 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300',
    bar: 'bg-indigo-500',
    border: 'border-indigo-200 dark:border-indigo-800',
  },
  staff_approved: {
    badge: 'bg-cyan-50 text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300',
    bar: 'bg-cyan-500',
    border: 'border-cyan-200 dark:border-cyan-800',
  },
  pending_provincial_approval: {
    badge: 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300',
    bar: 'bg-amber-500',
    border: 'border-amber-200 dark:border-amber-800',
  },
  approved: {
    badge: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
    bar: 'bg-emerald-500',
    border: 'border-emerald-200 dark:border-emerald-800',
  },
  returned_for_revision: {
    badge: 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300',
    bar: 'bg-rose-500',
    border: 'border-rose-200 dark:border-rose-800',
  },
  resubmitted: {
    badge: 'bg-purple-50 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300',
    bar: 'bg-purple-500',
    border: 'border-purple-200 dark:border-purple-800',
  },
}

export default function PipelineBar({
  pipelineData = {},
  onStageClick,
  selectedStage = null,
  emptyMessage = 'No workflow routing data available.',
}) {
  const {
    total = 0,
    stages = [],
    approved_count = 0,
    returned_count = 0,
    in_progress_count = 0,
  } = pipelineData

  // Forward progression stages
  const forwardStages = useMemo(() => {
    const forwardKeys = ['draft', 'submitted', 'under_verification', 'staff_approved', 'pending_provincial_approval', 'approved']
    return forwardKeys.map((key) => {
      const found = stages.find((s) => s.stage === key)
      return found || { stage: key, label: key.replace(/_/g, ' '), count: 0, percentage: 0 }
    })
  }, [stages])

  // Revision branch
  const returnedStage = stages.find((s) => s.stage === 'returned_for_revision') || { count: 0, percentage: 0 }
  const resubmittedStage = stages.find((s) => s.stage === 'resubmitted') || { count: 0, percentage: 0 }

  const isClickable = Boolean(onStageClick)

  if (!total && (!stages || stages.length === 0)) {
    return (
      <div className="py-8 text-center text-sm text-brand-text-muted">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Top summary KPIs */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-brand-border bg-brand-surface p-3">
          <span className="text-xs text-brand-text-muted">Total Tracked</span>
          <p className="mt-1 text-xl font-bold text-brand-text tabular-nums">{formatNumber(total)}</p>
        </div>
        <div className="rounded-lg border border-brand-border bg-brand-surface p-3">
          <span className="text-xs text-brand-text-muted">Approved (Complete)</span>
          <p className="mt-1 text-xl font-bold text-emerald-700 dark:text-emerald-400 tabular-nums">
            {formatNumber(approved_count)}
            <span className="ml-1.5 text-xs font-normal text-brand-text-muted">({formatPercent(total ? (approved_count / total) * 100 : 0)})</span>
          </p>
        </div>
        <div className="rounded-lg border border-brand-border bg-brand-surface p-3">
          <span className="text-xs text-brand-text-muted">Not approved (includes returned)</span>
          <p className="mt-1 text-xl font-bold text-blue-600 dark:text-blue-400 tabular-nums">
            {formatNumber(in_progress_count)}
          </p>
        </div>
        <div
          onClick={() => isClickable && onStageClick('returned_for_revision')}
          className={`rounded-lg border border-rose-200 bg-rose-50/50 p-3 transition-all dark:border-rose-900/50 dark:bg-rose-950/20 ${
            isClickable ? 'cursor-pointer hover:border-rose-400 hover:shadow-sm' : ''
          } ${selectedStage === 'returned_for_revision' ? 'ring-2 ring-rose-500 shadow-sm' : ''}`}
          role={isClickable ? 'button' : undefined}
          tabIndex={isClickable ? 0 : undefined}
          onKeyDown={(e) => {
            if (isClickable && (e.key === 'Enter' || e.key === ' ')) {
              e.preventDefault()
              onStageClick('returned_for_revision')
            }
          }}
          title="Click to filter by Returned for Revision"
        >
          <span className="text-xs font-medium text-rose-700 dark:text-rose-300 flex items-center gap-1">
            <AlertCircle className="h-3 w-3" /> Returned for Revision
          </span>
          <p className="mt-1 text-xl font-bold text-rose-700 dark:text-rose-400 tabular-nums">
            {formatNumber(returned_count)}
          </p>
        </div>
      </div>

      {/* Primary Forward Workflow Pipeline (6 Stages) */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-semibold text-brand-text">
          <span>Primary Forward Routing Flow</span>
          <span className="text-brand-text-muted font-normal">Click any stage to filter requirements</span>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {forwardStages.map((stage, idx) => {
            const theme = STAGE_THEMES[stage.stage] || STAGE_THEMES.draft
            const Icon = STAGE_ICONS[stage.stage] || FileText
            const pct = stage.percentage || (total ? (stage.count / total) * 100 : 0)
            const isSelected = selectedStage === stage.stage

            return (
              <div
                key={stage.stage}
                onClick={() => isClickable && onStageClick(stage.stage)}
                className={`relative flex flex-col justify-between rounded-lg border bg-brand-surface p-3 transition-all ${
                  isSelected
                    ? 'border-brand-primary ring-2 ring-brand-primary/30 shadow-sm'
                    : theme.border
                } ${
                  isClickable
                    ? 'cursor-pointer hover:border-brand-primary/50 hover:shadow-sm'
                    : ''
                }`}
                role={isClickable ? 'button' : undefined}
                tabIndex={isClickable ? 0 : undefined}
                onKeyDown={(e) => {
                  if (isClickable && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault()
                    onStageClick(stage.stage)
                  }
                }}
                aria-label={`Workflow stage ${stage.label}: ${formatNumber(stage.count)} requirements`}
                title={`Filter by ${stage.label} (${formatNumber(stage.count)} requirements)`}
              >
                <div className="flex items-center justify-between gap-1 text-xs text-brand-text-muted mb-2">
                  <span className="font-mono text-[10px] uppercase font-bold text-brand-text-muted">
                    Step {idx + 1}
                  </span>
                  <Icon className="h-3.5 w-3.5" />
                </div>

                <div>
                  <h4 className="text-xs font-semibold text-brand-text line-clamp-2 leading-tight">
                    {stage.label}
                  </h4>
                  <div className="mt-2 flex items-baseline justify-between gap-1">
                    <span className="text-lg font-bold text-brand-text tabular-nums">
                      {formatNumber(stage.count)}
                    </span>
                    <span className="text-[11px] font-medium text-brand-text-muted tabular-nums">
                      {formatPercent(pct)}
                    </span>
                  </div>
                </div>

                {/* Progress Mini Bar */}
                <div className="mt-2.5 h-1 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                  <div
                    className={`h-full ${theme.bar}`}
                    style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Revision Loop Callout (Returned for Revision -> Resubmitted) */}
      <div className="rounded-lg border border-dashed border-rose-300 bg-rose-50/40 p-3.5 dark:border-rose-900/60 dark:bg-rose-950/10">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-rose-100 text-rose-700 dark:bg-rose-900 dark:text-rose-200">
              <RotateCcw className="h-3.5 w-3.5" />
            </span>
            <div>
              <h4 className="text-xs font-semibold text-brand-text">Revision & Rectification Branch</h4>
              <p className="text-[11px] text-brand-text-muted">
                Documents returned to LGUs requiring corrective resubmission before re-entering verification
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 text-xs">
            <button
              type="button"
              onClick={() => isClickable && onStageClick('returned_for_revision')}
              className={`flex items-center gap-1.5 rounded-md px-2 py-1 transition-all ${
                selectedStage === 'returned_for_revision'
                  ? 'bg-rose-100 ring-2 ring-rose-500 font-bold text-rose-800 dark:bg-rose-900/60 dark:text-rose-200 shadow-sm'
                  : 'hover:bg-rose-100/60 dark:hover:bg-rose-900/30'
              }`}
              title={`Filter by Returned for Revision (${formatNumber(returnedStage.count)} items)`}
            >
              <span className="h-2 w-2 rounded-full bg-rose-500" />
              <span className="text-brand-text-muted">Returned for Revision:</span>
              <span className="font-bold text-rose-700 dark:text-rose-400 tabular-nums">
                {formatNumber(returnedStage.count)}
              </span>
            </button>

            <ArrowRight className="h-3.5 w-3.5 text-brand-text-muted hidden sm:inline" />

            <button
              type="button"
              onClick={() => isClickable && onStageClick('resubmitted')}
              className={`flex items-center gap-1.5 rounded-md px-2 py-1 transition-all ${
                selectedStage === 'resubmitted'
                  ? 'bg-purple-100 ring-2 ring-purple-500 font-bold text-purple-800 dark:bg-purple-900/60 dark:text-purple-200 shadow-sm'
                  : 'hover:bg-purple-100/60 dark:hover:bg-purple-900/30'
              }`}
              title={`Filter by Resubmitted (${formatNumber(resubmittedStage.count)} items)`}
            >
              <span className="h-2 w-2 rounded-full bg-purple-500" />
              <span className="text-brand-text-muted">Resubmitted:</span>
              <span className="font-bold text-purple-600 dark:text-purple-400 tabular-nums">
                {formatNumber(resubmittedStage.count)}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
