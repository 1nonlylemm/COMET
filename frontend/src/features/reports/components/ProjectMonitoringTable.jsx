import { useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ROUTES } from '../../../config/routes'
import { formatCurrency } from '../../../lib/formatters'

export default function ProjectMonitoringTable({ rows, loading, renderStatus, renderProgress, renderPerformance, formatCount }) {
  const [page, setPage] = useState(1)
  const perPage = 20
  const pages = Math.max(1, Math.ceil(rows.length / perPage))
  const visiblePage = Math.min(page, pages)
  const visibleRows = rows.slice((visiblePage - 1) * perPage, visiblePage * perPage)
  if (loading) return <div role="status" className="p-10 text-center text-sm text-brand-text-muted">Loading project monitoring rows…</div>
  if (!rows.length) return <EmptyState title="No project rows match the current filters." />
  return (
    <div className="data-table-panel">
      <div role="region" aria-label="Project monitoring, scroll horizontally on smaller screens" tabIndex={0} className="overflow-x-auto focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand-primary">
        <table className="w-full min-w-[1240px] table-fixed text-left">
          <caption className="sr-only">Project monitoring details</caption>
          <colgroup><col className="w-[33%]" /><col className="w-[18%]" /><col className="w-[14%]" /><col className="w-[12%]" /><col className="w-[14%]" /><col className="w-[9%]" /></colgroup>
          <thead className="data-table-header"><tr>{['Project / program', 'LGU / cluster', 'Implementation status', 'Project progress', 'Performance', 'Open documents'].map(label => <th key={label} scope="col" className="border-b border-brand-border px-4 py-3 text-xs font-semibold text-brand-text-muted">{label}</th>)}</tr></thead>
          <tbody>{visibleRows.map(row => (
            <tr key={row.project_id} className="data-table-row">
              <td className="data-table-cell px-4 py-3.5">
                {row.project_id != null ? <Link to={ROUTES.PROJECT_DETAIL.replace(':id', row.project_id)} className="break-words font-medium leading-5 text-brand-primary hover:underline focus-visible:outline-2 focus-visible:outline-brand-primary">{row.project_name || `Project #${row.project_id}`}</Link> : <p className="break-words font-medium leading-5 text-brand-text">{row.project_name || 'Project not recorded'}</p>}
                {row.program_code && row.program_name && row.program_code !== row.program_name ? <details className="mt-2 text-xs text-brand-text-muted"><summary className="cursor-pointer break-words focus-visible:outline-2 focus-visible:outline-brand-primary"><span className="sr-only">Program details: </span>{row.program_code}</summary><p className="mt-1 break-words leading-5">{row.program_name}</p></details> : <p className="mt-2 break-words text-xs text-brand-text-muted">{row.program_code || row.program_name || 'Program not recorded'}</p>}
                {row.budget_amount != null && row.budget_amount > 0 ? (
                  <p className="mt-1 text-xs font-semibold tabular-nums text-brand-text">
                    {formatCurrency(row.budget_amount)}
                  </p>
                ) : row.budget_amount === null ? (
                  <p className="mt-1 text-xs text-brand-text-muted italic" title="Allocation amount not recorded in project record">
                    Allocation: Not recorded
                  </p>
                ) : row.budget_amount === 0 ? (
                  <p className="mt-1 text-xs font-semibold tabular-nums text-brand-text">
                    ₱0.00
                  </p>
                ) : null}
              </td>
              <td className="data-table-cell px-4 py-3.5"><p className="break-words leading-5 text-brand-text">{row.lgu_name || 'LGU not recorded'}</p><p className="mt-1.5 break-words text-xs leading-5 text-brand-text-muted">{row.cluster_name || 'Cluster not recorded'}</p></td>
              <td className="data-table-cell px-4 py-3.5">{renderStatus(row)}</td>
              <td className="data-table-cell px-4 py-3.5">{renderProgress(row)}</td>
              <td className="data-table-cell px-4 py-3.5"><p className="mb-1.5 text-xs text-brand-text-muted">{row.effective_project_kind && row.effective_project_kind !== 'infrastructure' ? 'Specification status' : 'Slippage'}</p>{renderPerformance(row)}</td>
              <td className="data-table-cell px-4 py-3.5 text-right tabular-nums text-brand-text">{formatCount(row.document_open_count ?? row.documentary_summary?.open ?? 0)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {pages > 1 && <div className="flex flex-wrap items-center justify-between gap-3 border-t border-brand-border px-4 py-3 text-sm text-brand-text-muted">
        <span>Showing {(visiblePage - 1) * perPage + 1}–{Math.min(visiblePage * perPage, rows.length)} of {rows.length} projects</span>
        <div className="flex items-center gap-3"><button type="button" aria-label="Previous project monitoring page" className="btn-outline px-3 py-1.5 disabled:opacity-40" disabled={visiblePage <= 1} onClick={() => setPage(visiblePage - 1)}>Previous</button><span>Page {visiblePage} of {pages}</span><button type="button" aria-label="Next project monitoring page" className="btn-outline px-3 py-1.5 disabled:opacity-40" disabled={visiblePage >= pages} onClick={() => setPage(visiblePage + 1)}>Next</button></div>
      </div>}
    </div>
  )
}
