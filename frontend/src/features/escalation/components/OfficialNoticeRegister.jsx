import { EmptyState } from '../../../components/EmptyState'
import { formatDate, formatMachineLabel } from '../../../lib/formatters'

export function OfficialNoticeRegister({ notices, loading, pagination, noticeLabels, renderStatus, canRelease, onOpen, onRelease, onReceipt, onDocument, onPageChange }) {
  if (loading) return <div role="status" className="p-10 text-center text-sm text-brand-text-muted">Loading notice documents…</div>
  if (!notices.length) return <EmptyState title="No notice documents match the active filters." />
  const { page, pages, total, per_page: perPage } = pagination
  return (
    <div className="data-table-panel">
      <div role="region" aria-label="Official notice register, scroll horizontally on smaller screens" tabIndex={0} className="overflow-x-auto focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand-primary">
        <table className="w-full min-w-[1120px] table-fixed text-left">
          <caption className="sr-only">Official notice register</caption>
          <colgroup><col className="w-[26%]" /><col className="w-[27%]" /><col className="w-[12%]" /><col className="w-[14%]" /><col className="w-[21%]" /></colgroup>
          <thead className="data-table-header"><tr>{['Notice / requirement', 'Project / LGU', 'Prepared', 'Workflow status', 'Actions'].map(label => <th key={label} scope="col" className="border-b border-brand-border px-4 py-3 text-xs font-semibold text-brand-text-muted">{label}</th>)}</tr></thead>
          <tbody>{notices.map(notice => (
            <tr key={notice.id} className="data-table-row">
              <td className="data-table-cell px-4 py-3.5">
                <p className="break-words font-medium leading-5 text-brand-text">{noticeLabels[notice.notice_type] || formatMachineLabel(notice.notice_type)}</p>
                <p className="mt-1.5 break-words text-xs text-brand-text-muted">{notice.notice_number != null ? `Notice #${notice.notice_number}` : 'Notice number not recorded'}</p>
                <p className="mt-1.5 break-words text-xs leading-5 text-brand-text-muted">{notice.requirement_name || 'General compliance'}</p>
              </td>
              <td className="data-table-cell px-4 py-3.5">
                <p className="break-words leading-5 text-brand-text">{notice.project_name || 'Project not recorded'}</p>
                <p className="mt-1.5 text-xs leading-5 text-brand-text-muted">{notice.lgu_name || 'LGU not recorded'}</p>
                {notice.program_code && <p className="mt-1.5 break-words text-xs text-brand-text-muted">{notice.program_code}</p>}
              </td>
              <td className="data-table-cell px-4 py-3.5 text-sm tabular-nums text-brand-text">{formatDate(notice.generated_at, 'Date not recorded')}</td>
              <td className="data-table-cell px-4 py-3.5">
                {renderStatus(notice)}
                {notice.sent_at && <p className="mt-1.5 text-xs leading-5 text-brand-text-muted">Released {formatDate(notice.sent_at)}</p>}
                {notice.acknowledged_at && <p className="mt-1.5 text-xs leading-5 text-brand-text-muted">Acknowledged {formatDate(notice.acknowledged_at)}</p>}
              </td>
              <td className="data-table-cell px-4 py-3.5">
                <div className="flex flex-wrap items-start gap-2">
                  <button type="button" className="btn-primary whitespace-nowrap px-3 py-2 text-xs" aria-label={`Open notice ${notice.id}`} onClick={() => onOpen(notice.id)}>Open notice</button>
                  {canRelease && (notice.status === 'draft' || notice.status === 'reviewed') && <button type="button" className="btn-outline whitespace-nowrap px-3 py-2 text-xs" aria-label={`Release notice ${notice.id}`} onClick={() => onRelease(notice)}>Release</button>}
                  {notice.status === 'sent' && !notice.acknowledged_at && <button type="button" className="btn-outline px-3 py-2 text-xs" aria-label={`Record acknowledgment for notice ${notice.id}`} onClick={() => onReceipt(notice)}>Acknowledgment</button>}
                </div>
                <details className="mt-2 text-xs text-brand-text-muted">
                  <summary className="cursor-pointer focus-visible:outline-2 focus-visible:outline-brand-primary" aria-label={`Documents for notice ${notice.id}`}>Documents</summary>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button type="button" className="btn-outline px-2 py-2 text-xs" aria-label={`Open PDF for notice ${notice.id}`} onClick={() => onDocument(notice.id, 'pdf')}>Open PDF</button>
                    <button type="button" className="btn-outline px-2 py-2 text-xs" aria-label={`Download DOCX for notice ${notice.id}`} onClick={() => onDocument(notice.id, 'docx')}>Download DOCX</button>
                  </div>
                </details>
              </td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-brand-border px-4 py-3 text-sm text-brand-text-muted">
        <span>Showing {(page - 1) * perPage + 1}–{Math.min((page - 1) * perPage + notices.length, total)} of {total} notices</span>
        {pages > 1 && <div className="flex items-center gap-3">
          <button type="button" className="btn-outline px-3 py-1.5 disabled:opacity-40" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Previous</button><span>Page {page} of {pages}</span><button type="button" className="btn-outline px-3 py-1.5 disabled:opacity-40" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>Next</button>
        </div>}
      </div>
    </div>
  )
}
