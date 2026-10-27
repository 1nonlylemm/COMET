import { EmptyState } from '../../../components/EmptyState'
import { formatDateTime, formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'

export function DocumentArchiveTable({ records, programs, loading, pagination, onPageChange, onOpen, selectedId }) {
  if (loading) return <div role="status" className="p-10 text-center text-sm text-brand-text-muted">Loading archive records…</div>
  if (!records.length) return <EmptyState title="No archived documentary records match the current filters." />

  const { page, pages, total, per_page: perPage } = pagination
  return (
    <div>
      <div role="region" aria-label="Document archive, scroll for more records and columns" tabIndex={0} className="max-h-[34rem] overflow-auto focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand-primary">
        <table className="w-full min-w-[1040px] table-fixed text-left">
          <caption className="sr-only">Document archive</caption>
          <colgroup><col className="w-[24%]" /><col className="w-[25%]" /><col className="w-[13%]" /><col className="w-[16%]" /><col className="w-[10%]" /><col className="w-[12%]" /></colgroup>
          <thead className="sticky top-0 z-10 bg-slate-100 dark:bg-slate-800">
            <tr>{['Document / requirement', 'Project / LGU', 'Program / FY', 'Latest record', 'Handoff', 'Actions'].map(label => <th key={label} scope="col" className="border-b border-brand-border px-4 py-3 text-xs font-semibold text-brand-text-muted">{label}</th>)}</tr>
          </thead>
          <tbody>
            {records.map(record => {
              const program = programs.find(item => item.id === record.program_id)
              const programName = record.program_name || program?.name
              const programCode = record.program_code || program?.code
              return (
                <tr key={record.project_requirement_id} className={`data-table-row ${selectedId === record.project_requirement_id ? 'bg-brand-primary/10 dark:bg-brand-primary/20' : ''}`}>
                  <td className="data-table-cell px-4 py-4">
                    <p className="break-words font-medium leading-5 text-brand-text">{record.requirement_name || 'Unnamed requirement'}</p>
                    <p className="mt-1.5 text-xs text-brand-text-muted">{record.phase_name || 'Phase not recorded'}</p>
                  </td>
                  <td className="data-table-cell px-4 py-4">
                    <p className="break-words leading-5 text-brand-text">{record.project_name || 'Project not recorded'}</p>
                    <p className="mt-1.5 text-xs text-brand-text-muted">{record.lgu_name || 'LGU not recorded'}</p>
                  </td>
                  <td className="data-table-cell px-4 py-4">
                    {programCode && programName ? (
                      <details>
                        <summary className="cursor-pointer break-words font-medium text-brand-text focus-visible:outline-2 focus-visible:outline-brand-primary"><span className="sr-only">Program details: </span>{programCode}</summary>
                        <p className="mt-2 break-words text-xs leading-5 text-brand-text-muted">{programName}</p>
                      </details>
                    ) : <p className="break-words text-brand-text">{programName || programCode || 'Program not recorded'}</p>}
                    <p className="mt-1.5 text-xs text-brand-text-muted">{record.fiscal_year ? `FY ${record.fiscal_year}` : 'FY not recorded'}</p>
                  </td>
                  <td className="data-table-cell px-4 py-4">
                    <p className="font-medium text-brand-text">{record.submission_count ?? 0} {record.submission_count === 1 ? 'submission' : 'submissions'}</p>
                    <p className="mt-1.5 text-xs leading-5 text-brand-text-muted">{record.latest_submission_at ? formatDateTime(record.latest_submission_at, 'Submission date unavailable') : 'No submission date recorded'}</p>
                  </td>
                  <td className="data-table-cell px-4 py-4">{record.latest_push_status ? <span className={badgeClassForStatus(record.latest_push_status)}>{formatStatus(record.latest_push_status)}</span> : <span className="text-xs text-brand-text-muted">No handoff recorded</span>}</td>
                  <td className="data-table-cell px-4 py-4"><button type="button" className="btn-outline whitespace-nowrap px-2 py-2 text-xs" aria-label={`View versions: ${record.requirement_name || 'Unnamed requirement'}, ${record.project_name || 'Project not recorded'}, ${record.lgu_name || 'LGU not recorded'}`} onClick={() => onOpen(record)}>View versions</button></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-brand-border px-4 py-3 text-sm text-brand-text-muted">
        <span>Showing {(page - 1) * perPage + 1}–{Math.min((page - 1) * perPage + records.length, total)} of {total} records</span>
        {pages > 1 && <div className="flex items-center gap-3">
          <button type="button" className="btn-outline px-3 py-1.5 disabled:opacity-40" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Previous</button>
          <span>Page {page} of {pages}</span>
          <button type="button" className="btn-outline px-3 py-1.5 disabled:opacity-40" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>Next</button>
        </div>}
      </div>
    </div>
  )
}
