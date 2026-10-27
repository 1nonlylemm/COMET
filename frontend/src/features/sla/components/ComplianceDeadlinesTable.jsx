import { deadlinePosition } from '../utils/deadlinePresentation'
import { EmptyState } from '../../../components/EmptyState'
import { formatMachineLabel, formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'

export function ComplianceDeadlinesTable({ deadlines, loading, emptyMessage, getMetrics, formatDate, canClose, onDetails, onCloseDeadline }) {
  if (loading) return <div className="data-table-panel p-10 text-center text-sm text-brand-text-muted" role="status">Loading compliance deadlines…</div>
  if (!deadlines.length) return <div className="data-table-panel"><EmptyState title={emptyMessage} /></div>
  return (
    <div className="data-table-panel">
      <div role="region" aria-label="Compliance deadlines, scroll horizontally on smaller screens" tabIndex={0} className="overflow-x-auto focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand-primary">
        <table className="w-full min-w-[1100px] table-fixed text-left">
          <caption className="sr-only">Compliance deadlines</caption>
          <colgroup><col className="w-[28%]" /><col className="w-[28%]" /><col className="w-[15%]" /><col className="w-[16%]" /><col className="w-[13%]" /></colgroup>
          <thead className="data-table-header"><tr>{['Tracked item', 'Project / LGU', 'Deadline', 'Time / status', 'Actions'].map(label => <th key={label} scope="col" className="border-b border-brand-border px-4 py-3 text-xs font-semibold text-brand-text-muted">{label}</th>)}</tr></thead>
          <tbody>{deadlines.map(row => {
            const metrics = getMetrics(row)
            const projectName = row.project_name || `Project #${row.project_id}`
            const status = row.is_resolved ? 'resolved' : metrics.isOverdue ? 'overdue' : 'active'
            return (
              <tr key={row.id} className="data-table-row">
                <td className="data-table-cell px-4 py-3.5">
                  <p className="break-words font-medium leading-5 text-brand-text">{row.requirement_name || projectName}</p>
                  <p className="mt-1.5 text-xs text-brand-text-muted">{row.requirement_name ? [row.requirement_phase_name, row.requirement_status && formatStatus(row.requirement_status)].filter(Boolean).join(' · ') : 'Project-level deadline'}</p>
                  <p className="mt-1.5 text-xs leading-5 text-brand-text-muted">#{row.id} · {formatMachineLabel(row.deadline_type)}</p>
                </td>
                <td className="data-table-cell px-4 py-3.5">
                  {row.requirement_name && <p className="break-words leading-5 text-brand-text">{projectName}</p>}
                  <p className={`${row.requirement_name ? 'mt-1.5 text-xs' : 'text-sm'} text-brand-text-muted`}>{row.lgu_name || 'LGU not recorded'}</p>
                  <p className="mt-1.5 break-words text-xs leading-5 text-brand-text-muted">{row.program_code || row.program_name || 'Program not recorded'} · FY {row.project_fiscal_year || 'not recorded'}</p>
                </td>
                <td className="data-table-cell px-4 py-3.5">
                  <p className="font-medium tabular-nums text-brand-text">{row.deadline_date ? formatDate(row.deadline_date) : 'Date not recorded'}</p>
                  <p className="mt-1.5 text-xs leading-5 text-brand-text-muted">{row.sla_working_days != null ? `${row.sla_working_days} working-day window` : 'Window not recorded'}</p>
                </td>
                <td className="data-table-cell px-4 py-3.5">
                  <span className={badgeClassForStatus(status)}>{row.is_resolved ? 'Closed' : metrics.isOverdue ? 'Overdue' : 'Active'}</span>
                  {!row.is_resolved && <p className={`mt-1.5 text-xs font-medium leading-5 tabular-nums ${metrics.isOverdue ? 'text-red-700 dark:text-red-300' : 'text-brand-text'}`}>{deadlinePosition(row, metrics)}</p>}
                </td>
                <td className="data-table-cell px-4 py-3.5"><div className="flex flex-col items-start gap-2">
                  <button type="button" className="btn-outline px-3 py-2 text-xs" aria-label={`Details for deadline #${row.id}`} onClick={() => onDetails(row)}>Details</button>
                  {!row.is_resolved && canClose && <button type="button" className="action-link whitespace-nowrap text-xs" aria-label={`Close Deadline #${row.id}`} onClick={() => onCloseDeadline(row)}>Close Deadline</button>}
                </div></td>
              </tr>
            )
          })}</tbody>
        </table>
      </div>
    </div>
  )
}
