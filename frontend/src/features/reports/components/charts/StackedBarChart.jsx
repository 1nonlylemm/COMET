import { useMemo } from 'react'
import { ShieldCheck } from 'lucide-react'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatPercent(value) {
  if (value === 'Not rated') return 'Not rated'
  if (value === null || value === undefined) return 'Not reported'
  return `${Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })}%`
}

const COMPLIANCE_STATUS_CONFIG = [
  { key: 'compliant', label: 'Compliant', color: 'bg-emerald-500', textClass: 'text-emerald-700 dark:text-emerald-400' },
  { key: 'under_review', label: 'Under Review', color: 'bg-blue-500', textClass: 'text-blue-700 dark:text-blue-400' },
  { key: 'non_compliant', label: 'Non-Compliant', color: 'bg-rose-500', textClass: 'text-rose-700 dark:text-rose-400' },
  { key: 'pending', label: 'Pending', color: 'bg-amber-500', textClass: 'text-amber-700 dark:text-amber-400' },
  { key: 'waived', label: 'Waived', color: 'bg-slate-400', textClass: 'text-slate-600 dark:text-slate-400' },
  { key: 'not_applicable', label: 'Not Applicable', color: 'bg-slate-500', textClass: 'text-slate-500 dark:text-slate-400' },
]

export default function StackedBarChart({
  programs = [],
  onProgramClick,
  onSegmentClick,
  selectedProgramId = null,
  selectedComplianceStatus = null,
  emptyMessage = 'No program compliance data available.',
}) {
  // Aggregate provincial totals across all programs
  const provincialTotals = useMemo(() => {
    const acc = { compliant: 0, under_review: 0, non_compliant: 0, pending: 0, waived: 0, not_applicable: 0, total: 0 }
    programs.forEach((p) => {
      acc.compliant += p.compliant || 0
      acc.under_review += p.under_review || 0
      acc.non_compliant += p.non_compliant || 0
      acc.pending += p.pending || 0
      acc.waived += p.waived || 0
      acc.not_applicable += p.not_applicable || 0
      acc.total += p.total || 0
    })
    return acc
  }, [programs])

  const handleSegmentClick = (e, program, statusKey) => {
    e.stopPropagation()
    if (onSegmentClick) {
      onSegmentClick(program, statusKey)
    } else if (onProgramClick) {
      onProgramClick(program, statusKey)
    }
  }

  if (!programs || programs.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-brand-text-muted">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Legend & Provincial Summary */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-brand-border pb-3">
        <div className="flex flex-wrap items-center gap-3.5 text-xs">
          {COMPLIANCE_STATUS_CONFIG.map((cfg) => {
            const count = provincialTotals[cfg.key] || 0
            return (
              <div key={cfg.key} className="flex items-center gap-1.5">
                <span className={`h-2.5 w-2.5 rounded-sm ${cfg.color}`} />
                <span className="text-brand-text-muted">{cfg.label}:</span>
                <span className="font-semibold text-brand-text tabular-nums">{formatNumber(count)}</span>
              </div>
            )
          })}
        </div>
        <div className="text-xs text-brand-text-muted">
          Total: <span className="font-bold text-brand-text tabular-nums">{formatNumber(provincialTotals.total)}</span> reqs
        </div>
      </div>

      {/* Program Bars */}
      <div className="space-y-4">
        {programs.map((program) => {
          const total = program.total || 0
          const notApplicable = program.not_applicable || 0
          const applicableDocs = program.applicable_document_count ?? program.applicable ?? (total - notApplicable)
          const isNotRated = applicableDocs === 0
          const rate = isNotRated ? 'Not rated' : (program.compliance_rate || 0)
          const isProgramSelected = selectedProgramId === program.program_id
          const isClickable = Boolean(onProgramClick || onSegmentClick)

          return (
            <div
              key={program.program_id}
              onClick={() => onProgramClick && onProgramClick(program)}
              className={`rounded-lg border bg-brand-surface p-3.5 transition-all ${
                isProgramSelected && !selectedComplianceStatus
                  ? 'border-brand-primary ring-2 ring-brand-primary/20 shadow-sm'
                  : 'border-brand-border/60'
              } ${
                isClickable
                  ? 'cursor-pointer hover:border-brand-primary/50 hover:shadow-sm'
                  : ''
              }`}
              role={onProgramClick ? 'button' : undefined}
              tabIndex={onProgramClick ? 0 : undefined}
              onKeyDown={(e) => {
                if (onProgramClick && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault()
                  onProgramClick(program)
                }
              }}
            >
              {/* Header */}
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-brand-text truncate">
                      {program.program_name}
                    </span>
                    {program.program_code && (
                      <span className="rounded bg-brand-surface-solid px-1.5 py-0.5 text-[10px] font-mono font-medium text-brand-text-muted border border-brand-border">
                        {program.program_code}
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-brand-text-muted">
                    {formatNumber(program.project_count)} {program.project_count === 1 ? 'project' : 'projects'} · {formatNumber(total)} requirements
                  </span>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {isNotRated ? (
                    <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium text-brand-text-muted bg-slate-100 dark:bg-slate-800">
                      Not rated
                    </span>
                  ) : (
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold tabular-nums ${
                        rate >= 80
                          ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300'
                          : rate >= 50
                          ? 'bg-blue-50 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300'
                          : rate > 0
                          ? 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300'
                          : 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300'
                      }`}
                    >
                      <ShieldCheck className="h-3 w-3" />
                      {formatPercent(rate)} Compliant
                    </span>
                  )}
                </div>
              </div>

              {/* Stacked Bar */}
              <div className="h-4 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800 flex">
                {total > 0 ? (
                  COMPLIANCE_STATUS_CONFIG.map((cfg) => {
                    const count = program[cfg.key] || 0
                    if (!count) return null
                    const pct = (count / total) * 100
                    const isSegmentActive = isProgramSelected && selectedComplianceStatus === cfg.key
                    return (
                      <div
                        key={cfg.key}
                        className={`${cfg.color} h-full transition-all duration-300 hover:brightness-110 cursor-pointer ${
                          isSegmentActive ? 'ring-2 ring-black dark:ring-white z-10' : ''
                        }`}
                        style={{ width: `${pct}%` }}
                        title={`${program.program_name} - ${cfg.label}: ${formatNumber(count)} (${formatPercent(pct)}) — Click to filter`}
                        role="button"
                        tabIndex={0}
                        onClick={(e) => handleSegmentClick(e, program, cfg.key)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            handleSegmentClick(e, program, cfg.key)
                          }
                        }}
                        aria-label={`${program.program_name} ${cfg.label} ${count}`}
                      />
                    )
                  })
                ) : (
                  <div className="h-full w-full bg-slate-200 dark:bg-slate-700" />
                )}
              </div>

              {/* Status Breakdown Chips */}
              <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-brand-text-muted">
                {COMPLIANCE_STATUS_CONFIG.map((cfg) => {
                  const count = program[cfg.key] || 0
                  const isSegmentActive = isProgramSelected && selectedComplianceStatus === cfg.key
                  return (
                    <button
                      key={cfg.key}
                      type="button"
                      onClick={(e) => handleSegmentClick(e, program, cfg.key)}
                      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 transition-colors ${
                        isSegmentActive
                          ? 'bg-brand-primary/15 ring-1 ring-brand-primary text-brand-text font-semibold'
                          : 'hover:bg-slate-100 dark:hover:bg-slate-800'
                      }`}
                      title={`Filter by ${program.program_name} + ${cfg.label}`}
                    >
                      <span className={`h-2 w-2 rounded-full ${cfg.color}`} />
                      <span className={cfg.textClass}>{cfg.label}:</span>{' '}
                      <span className="font-semibold text-brand-text tabular-nums">{formatNumber(count)}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
