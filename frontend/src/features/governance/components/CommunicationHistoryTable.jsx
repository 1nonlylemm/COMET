import { CategoryBadge } from '../../../components/CategoryBadge'
import { EmptyState } from '../../../components/EmptyState'
import { formatDateTime, formatMachineLabel, formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'

export function CommunicationHistoryTable({ records, loading, pagination, onPageChange }) {
  if (loading) return <div role="status" className="p-10 text-center text-sm text-brand-text-muted">Loading communication history…</div>
  if (!records.length) return <EmptyState title="No communication history is available for the current filters." />
  const { page, pages, total, per_page: perPage } = pagination
  return (
    <div>
      <div role="region" aria-label="Communication history, scroll horizontally on smaller screens" tabIndex={0} className="overflow-x-auto focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand-primary">
        <table className="w-full min-w-[960px] table-fixed text-left">
          <caption className="sr-only">Communication history</caption>
          <colgroup><col className="w-[44%]" /><col className="w-[26%]" /><col className="w-[16%]" /><col className="w-[14%]" /></colgroup>
          <thead className="data-table-header"><tr>{['Communication', 'Recipient / LGU', 'Delivery / channel', 'Sent / recorded'].map(label => <th key={label} scope="col" className="border-b border-brand-border px-4 py-3 text-xs font-semibold text-brand-text-muted">{label}</th>)}</tr></thead>
          <tbody>{records.map(record => {
            const subject = record.subject || (record.communication_type ? formatMachineLabel(record.communication_type) : 'Subject not recorded')
            const showProject = record.project_name && !subject.includes(record.project_name)
            return (
              <tr key={record.id} className="data-table-row">
                <td className="data-table-cell px-4 py-3">
                  <p className="break-words font-medium leading-5 text-brand-text">{subject}</p>
                  {showProject && <p className="mt-1.5 break-words text-xs leading-5 text-brand-text-muted">Project: {record.project_name}</p>}
                </td>
                <td className="data-table-cell px-4 py-3">
                  <p className="break-words leading-5 text-brand-text">{record.recipient_name || 'Recipient not recorded'}</p>
                  <p className="mt-1 text-xs leading-5 text-brand-text-muted">{record.lgu_name || 'LGU not recorded'}</p>
                  {record.recipient_email && <p className="mt-1 break-all text-xs text-brand-text-muted">{record.recipient_email}</p>}
                </td>
                <td className="data-table-cell px-4 py-3">
                  {record.delivery_status ? <span className={badgeClassForStatus(record.delivery_status)}>{formatStatus(record.delivery_status)}</span> : <span className="text-xs text-brand-text-muted">Delivery not recorded</span>}
                  <div className="mt-1.5">{record.channel ? <CategoryBadge category="communication_channel" value={record.channel} /> : <span className="text-xs text-brand-text-muted">Channel not recorded</span>}</div>
                  {record.delivery_status === 'failed' && record.remarks && <p className="mt-1.5 break-words text-xs leading-5 text-red-700 dark:text-red-300">{record.remarks}</p>}
                </td>
                <td className="data-table-cell px-4 py-3">
                  <p className="text-xs leading-5 text-brand-text">{formatDateTime(record.sent_at || record.created_at, 'Timestamp not recorded')}</p>
                  {!record.sent_at && record.created_at && <p className="mt-1 text-xs leading-5 text-brand-text-muted">Recorded · sent time unavailable</p>}
                </td>
              </tr>
            )
          })}</tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-brand-border px-4 py-3 text-sm text-brand-text-muted">
        <span>Showing {(page - 1) * perPage + 1}–{Math.min((page - 1) * perPage + records.length, total)} of {total} communications</span>
        {pages > 1 && <div className="flex items-center gap-3">
          <button type="button" aria-label="Previous communications page" className="btn-outline px-3 py-1.5 disabled:opacity-40" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Previous</button>
          <span>Page {page} of {pages}</span>
          <button type="button" aria-label="Next communications page" className="btn-outline px-3 py-1.5 disabled:opacity-40" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>Next</button>
        </div>}
      </div>
    </div>
  )
}
