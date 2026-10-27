import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { EmptyState } from '../../../components/EmptyState'
import { formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'

const PHASE_ORDER = ['Pre-Implementation', 'Implementation', 'Completion']

function RequirementDeadline({ requirement }) {
  const deadline = requirement.active_deadline
  if (deadline?.deadline_date) {
    const date = new Date(deadline.deadline_date)
    const label = Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleDateString('en-PH', { month: 'short', day: 'numeric', year: 'numeric' })
    return (
      <div className="space-y-1 text-xs leading-5">
        <p className={deadline.is_overdue ? 'font-medium text-red-700 dark:text-red-300' : 'font-medium text-brand-text'}>{deadline.is_overdue ? 'Overdue since' : 'Due'} {label}</p>
        <p className="text-brand-text-muted">{formatStatus(deadline.deadline_type)}</p>
      </div>
    )
  }
  return (
    <div className="space-y-1 text-xs leading-5 text-brand-text-muted">
      <p>{requirement.has_sla ? 'No active deadline' : 'No deadline set'}</p>
      {requirement.has_sla && requirement.sla_days != null && <p>Rule: {requirement.sla_days} working days</p>}
    </div>
  )
}

function RequirementEvidence({ requirement }) {
  const hasEvidence = Boolean(requirement.has_documentary_evidence || requirement.submission_count > 0)
  if (!hasEvidence) return <span className="text-xs text-brand-text-muted">No evidence recorded</span>
  const version = requirement.current_version_number || requirement.submission_count || 1
  const workflow = requirement.is_returned ? 'returned_for_revision' : requirement.workflow_status
  const labels = {
    returned_for_revision: 'Needs Correction', resubmitted: 'Resubmitted', approved: 'Approved',
    staff_approved: 'Staff Approved', under_verification: 'Under Verification',
    pending_provincial_approval: 'Awaiting Provincial Approval', submitted: 'Submitted',
  }
  return (
    <div className="space-y-1">
      <span className={badgeClassForStatus(workflow || 'pending', 'neutral')}>V{version} · {labels[workflow] || (workflow ? formatStatus(workflow) : 'Attached')}</span>
      {requirement.submission_count > 1 && <p className="text-xs text-brand-text-muted">{requirement.submission_count} submissions</p>}
    </div>
  )
}

function inactiveRequirementSubtext(requirement) {
  if (requirement.has_documentary_evidence) {
    return 'Previous checklist · documents preserved'
  }
  if (requirement.submission_count > 0) {
    return 'Previous checklist · submissions recorded'
  }
  return 'Previous checklist · inactive requirement'
}

export function ProjectRequirementsTable({ requirements, renderActions, emptyMessage, preserveEmptyTable = false }) {
  const [page, setPage] = useState(1)
  const [collapsedPhases, setCollapsedPhases] = useState(() => new Set())
  const togglePhase = phase => setCollapsedPhases(current => {
    const next = new Set(current)
    if (next.has(phase)) next.delete(phase)
    else next.add(phase)
    return next
  })
  const perPage = 20
  const totalPages = Math.max(1, Math.ceil(requirements.length / perPage))
  const visiblePage = Math.min(page, totalPages)
  const phases = [...new Set([...PHASE_ORDER, ...requirements.map(row => row.phase_name || 'Other requirements')])]
  // Keep matrix order within a phase; show all phases in their lifecycle order.
  const ordered = phases.flatMap(phase => requirements.filter(row => (row.phase_name || 'Other requirements') === phase))
  const visible = ordered.slice((visiblePage - 1) * perPage, visiblePage * perPage)

  if (!requirements.length && !preserveEmptyTable) {
    return <div className="data-table-panel"><EmptyState title={emptyMessage} /></div>
  }

  return (
    <div className="data-table-panel">
      <div role="region" aria-label="Project requirements table, scroll horizontally on smaller screens" tabIndex={0} className="overflow-x-auto focus-visible:outline-2 focus-visible:outline-brand-primary focus-visible:-outline-offset-2">
        <table className="w-full min-w-[920px] table-fixed text-left">
          <caption className="sr-only">Project requirements</caption>
          <colgroup><col className="w-[31%]" /><col className="w-[12%]" /><col className="w-[18%]" /><col className="w-[14%]" /><col className="w-[25%]" /></colgroup>
          <thead className="data-table-header">
            <tr>{['Requirement', 'Compliance', 'Evidence / review', 'Due', 'Actions'].map(label => <th key={label} scope="col" className="border-b border-brand-border px-4 py-3 text-xs font-semibold text-brand-text-muted">{label}</th>)}</tr>
          </thead>
          {requirements.length === 0 ? (
            <tbody><tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-brand-text-muted">{emptyMessage}</td></tr></tbody>
          ) : phases.map(phase => {
            const rows = visible.filter(row => (row.phase_name || 'Other requirements') === phase)
            if (!rows.length) return null
            const total = requirements.filter(row => (row.phase_name || 'Other requirements') === phase).length
            const collapsed = collapsedPhases.has(phase)
            return (
              <tbody key={phase} aria-label={phase}>
                <tr className="border-b border-brand-border bg-slate-50 dark:bg-slate-800/60">
                  <th scope="rowgroup" colSpan={5} className="text-left">
                    <button type="button" aria-expanded={!collapsed} aria-controls={rows.map(row => `requirement-row-${row.id}`).join(' ')} onClick={() => togglePhase(phase)} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-slate-100 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand-primary dark:hover:bg-slate-700/60">
                      <ChevronDown aria-hidden="true" size={16} className={`shrink-0 text-brand-text-muted ${collapsed ? '-rotate-90' : ''}`} />
                      <span className="text-sm font-semibold text-brand-text">{phase}</span>{' '}
                      <span className="text-xs font-normal text-brand-text-muted">{rows.length < total ? `${rows.length} of ${total} on this page` : `${total} ${total === 1 ? 'requirement' : 'requirements'}`}</span>
                      {' '}<span className="ml-auto text-xs font-normal text-brand-text-muted">{collapsed ? 'Expand' : 'Collapse'}</span>
                    </button>
                  </th>
                </tr>
                {rows.map(requirement => (
                    <tr key={requirement.id} id={`requirement-row-${requirement.id}`} hidden={collapsed} className="data-table-row">
                      <td className="data-table-cell px-4 py-3.5">
                        <p className="break-words font-medium leading-5 text-brand-text">{requirement.requirement_name}</p>
                        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-brand-text-muted">
                          <span>{requirement.is_mandatory ? 'Required' : 'Optional'}</span>
                          {requirement.annex_reference && <span className="border-l border-brand-border pl-2">{requirement.annex_reference}</span>}
                          {requirement.is_active === false && (
                            <span className="border-l border-brand-border pl-2 font-medium text-slate-500 dark:text-slate-400">
                              Inactive
                            </span>
                          )}
                          {requirement.applicability === 'not_applicable' && (
                            <span className="border-l border-brand-border pl-2 font-medium text-amber-700 dark:text-amber-400">
                              Not Applicable
                            </span>
                          )}
                        </div>
                        {requirement.is_active === false && (
                          <p className="mt-1 text-xs text-brand-text-muted">
                            {inactiveRequirementSubtext(requirement)}
                          </p>
                        )}
                        {requirement.applicability === 'not_applicable' && (
                          <div className="mt-1 space-y-0.5 text-xs">
                            <p className="font-medium text-amber-800 dark:text-amber-300">
                              Justification: {requirement.applicability_reason || 'Marked Not Applicable'}
                            </p>
                            {(requirement.applicability_set_by_name || requirement.applicability_set_at) && (
                              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                                Set by {requirement.applicability_set_by_name || 'Authorized user'}
                                {requirement.applicability_set_at && (
                                  ` on ${new Date(requirement.applicability_set_at).toLocaleDateString('en-PH', { month: 'short', day: 'numeric', year: 'numeric' })}`
                                )}
                              </p>
                            )}
                          </div>
                        )}
                        {requirement.waived_reason && requirement.applicability !== 'not_applicable' && (
                          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 italic">
                            Reason: {requirement.waived_reason}
                          </p>
                        )}
                      </td>
                      <td className="data-table-cell px-4 py-3.5">
                        <div className="space-y-1">
                          <span className={badgeClassForStatus(requirement.status)}>{formatStatus(requirement.status)}</span>
                          {requirement.applicability === 'not_applicable' && (
                            <div>
                              <span className="inline-block rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                                Not Applicable
                              </span>
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="data-table-cell px-4 py-3.5"><RequirementEvidence requirement={requirement} /></td>
                      <td className="data-table-cell px-4 py-3.5"><RequirementDeadline requirement={requirement} /></td>
                      <td className="data-table-cell px-4 py-3.5">{renderActions(requirement)}</td>
                    </tr>
                ))}
              </tbody>
            )
          })}
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-brand-border px-4 py-3 text-sm text-brand-text-muted">
          <span>Page includes {(visiblePage - 1) * perPage + 1}–{Math.min(visiblePage * perPage, requirements.length)} of {requirements.length} requirements</span>
          <div className="flex items-center gap-3">
            <button type="button" className="btn-outline px-3 py-1.5 disabled:opacity-40" disabled={visiblePage <= 1} onClick={() => setPage(visiblePage - 1)}>Previous</button>
            <span>Page {visiblePage} of {totalPages}</span>
            <button type="button" className="btn-outline px-3 py-1.5 disabled:opacity-40" disabled={visiblePage >= totalPages} onClick={() => setPage(visiblePage + 1)}>Next</button>
          </div>
        </div>
      )}
    </div>
  )
}
