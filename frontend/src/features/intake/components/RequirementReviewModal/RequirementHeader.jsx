import { formatStatus } from '../../../../lib/formatters'
import { badgeClassForStatus } from '../../../../lib/statusStyles'
import { StatusBadge } from '../../lib/intakeComponents.jsx'
import { phaseBadgeClass, reviewTask } from '../../lib/intakeFormatters.js'

/**
 * RequirementHeader — compact header for the review modal.
 *
 * Shows requirement title, project + LGU subtitle, phase chip, status chip,
 * and the inline review-task summary (Awaiting Document, Evaluate Attachment,
 * Approved for Handoff, etc.).
 */
export function RequirementHeader({ requirement, userRole = 'staff', compact = false }) {
  if (!requirement) return null
  const task = reviewTask(requirement, userRole === 'field_officer')
  if (compact) {
    return (
      <header data-testid="requirement-header" className="flex flex-wrap items-start justify-between gap-3 border-b border-brand-border pb-4">
        <div className="min-w-0 flex-1">
          <h3 className="break-words text-lg font-semibold text-brand-text">{requirement.requirement_name || 'Unnamed requirement'}</h3>
          <p className="mt-1 text-xs text-brand-text-muted">{[requirement.phase_name, requirement.annex_reference, requirement.workflow_status && `Workflow: ${formatStatus(requirement.workflow_status)}`].filter(Boolean).join(' · ')}</p>
          {requirement.program_is_active === false && <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">Movement paused: this program is inactive. Existing records remain available for viewing.</p>}
        </div>
        <StatusBadge row={requirement} />
      </header>
    )
  }
  return (
    <header
      data-testid="requirement-header"
      className="flex flex-col gap-3 rounded-xl border border-brand-border bg-brand-surface px-4 py-3 sm:flex-row sm:items-start sm:justify-between"
    >
      <div className="min-w-0">
        <div className="text-sm font-semibold text-brand-text">{requirement.requirement_name || 'Unnamed requirement'}</div>
        {requirement.program_is_active === false && (
          <p className="mt-1 text-xs font-medium text-amber-700 dark:text-amber-300">Movement paused: this program is inactive. Existing records remain available for viewing.</p>
        )}
        <div className="mt-1 truncate text-xs text-brand-text-muted">
          {requirement.project_name || 'Unassigned project'} · {requirement.lgu_name || 'No LGU'}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
          {requirement.phase_name && (
            <span className={`inline-flex items-center rounded-full border px-2 py-0.5 font-medium ${phaseBadgeClass(requirement.phase_name)}`}>
              {requirement.phase_name}
            </span>
          )}
          {requirement.annex_reference && (
            <span className="inline-flex items-center rounded-full border border-brand-border bg-brand-surface-solid px-2 py-0.5 font-medium text-brand-text-muted">
              {requirement.annex_reference}
            </span>
          )}
          <span className={badgeClassForStatus(task.tone)}>{task.label}</span>
        </div>
      </div>
      <div className="shrink-0 flex flex-col items-end gap-1">
        <StatusBadge row={requirement} />
        {requirement.workflow_status && (
          <span className="inline-flex items-center rounded-full border border-brand-border bg-brand-surface-solid px-2 py-0.5 text-[11px] font-medium text-brand-text-muted">
            Workflow: {formatStatus(requirement.workflow_status)}
          </span>
        )}
      </div>
    </header>
  )
}

export default RequirementHeader
