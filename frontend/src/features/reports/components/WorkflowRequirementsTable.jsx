import { useId, useState } from 'react'
import { EmptyState } from '../../../components/EmptyState'

function ReturnNotes({ text }) {
  const [expanded, setExpanded] = useState(false)
  const id = useId()
  if (!text || text === '—') return <span className="text-brand-text-muted">No return notes</span>
  const lengthy = text.length > 140
  return (
    <div>
      <p id={id} className="whitespace-pre-wrap break-words leading-5 text-brand-text">{lengthy && !expanded ? `${text.slice(0, 140).trimEnd()}…` : text}</p>
      {lengthy && <button type="button" aria-expanded={expanded} aria-controls={id} onClick={() => setExpanded(value => !value)} className="mt-2 text-xs font-medium text-brand-primary hover:underline focus-visible:outline-2 focus-visible:outline-brand-primary">{expanded ? 'Show less' : 'Show full notes'}</button>}
    </div>
  )
}

export default function WorkflowRequirementsTable({ rows, loading, stageLabel, renderCompliance, renderWorkflow }) {
  const [page, setPage] = useState(1)
  const perPage = 20
  const pages = Math.max(1, Math.ceil(rows.length / perPage))
  const visiblePage = Math.min(page, pages)
  const visibleRows = rows.slice((visiblePage - 1) * perPage, visiblePage * perPage)

  if (loading) return <div role="status" className="p-10 text-center text-sm text-brand-text-muted">Loading workflow requirements…</div>
  if (!rows.length) return <EmptyState title={`No requirements currently in '${stageLabel}' state match the active filters.`} />

  return (
    <div className="data-table-panel">
      <div role="region" aria-label="Workflow requirements, scroll horizontally on smaller screens" tabIndex={0} className="overflow-x-auto focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand-primary">
        <table className="w-full min-w-[1100px] table-fixed text-left">
          <caption className="sr-only">Workflow requirements details</caption>
          <colgroup><col className="w-[26%]" /><col className="w-[28%]" /><col className="w-[13%]" /><col className="w-[14%]" /><col className="w-[19%]" /></colgroup>
          <thead className="data-table-header"><tr>{['Requirement / program', 'Project / LGU', 'Compliance determination', 'Workflow routing state', 'Return reason / notes'].map(label => <th key={label} scope="col" className="border-b border-brand-border px-4 py-3 text-xs font-semibold text-brand-text-muted">{label}</th>)}</tr></thead>
          <tbody>{visibleRows.map(row => (
            <tr key={row.id} className="data-table-row">
              <td className="data-table-cell px-4 py-3.5">
                <p className="break-words font-medium leading-5 text-brand-text">{row.requirement_name || 'Requirement not recorded'}</p>
                {row.program_code && row.program_name && row.program_code !== row.program_name ? <details className="mt-2 text-xs text-brand-text-muted"><summary className="cursor-pointer break-words focus-visible:outline-2 focus-visible:outline-brand-primary"><span className="sr-only">Program details: </span>{row.program_code}</summary><p className="mt-1 break-words leading-5">{row.program_name}</p></details> : <p className="mt-2 break-words text-xs text-brand-text-muted">{row.program_code || row.program_name || 'Program not recorded'}</p>}
              </td>
              <td className="data-table-cell px-4 py-3.5"><p className="break-words leading-5 text-brand-text">{row.project_name || 'Project not recorded'}</p><p className="mt-1.5 break-words text-xs leading-5 text-brand-text-muted">{row.lgu_name || 'LGU not recorded'}</p></td>
              <td className="data-table-cell px-4 py-3.5">{renderCompliance(row)}</td>
              <td className="data-table-cell px-4 py-3.5">{renderWorkflow(row)}</td>
              <td className="data-table-cell px-4 py-3.5 text-xs"><ReturnNotes key={`${row.id}:${row.workflow_return_reason}`} text={row.workflow_return_reason} /></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {pages > 1 && <div className="flex flex-wrap items-center justify-between gap-3 border-t border-brand-border px-4 py-3 text-sm text-brand-text-muted">
        <span>Showing {(visiblePage - 1) * perPage + 1}–{Math.min(visiblePage * perPage, rows.length)} of {rows.length} requirements</span>
        <div className="flex items-center gap-3"><button type="button" aria-label="Previous workflow requirements page" className="btn-outline px-3 py-1.5 disabled:opacity-40" disabled={visiblePage <= 1} onClick={() => setPage(visiblePage - 1)}>Previous</button><span>Page {visiblePage} of {pages}</span><button type="button" aria-label="Next workflow requirements page" className="btn-outline px-3 py-1.5 disabled:opacity-40" disabled={visiblePage >= pages} onClick={() => setPage(visiblePage + 1)}>Next</button></div>
      </div>}
    </div>
  )
}
