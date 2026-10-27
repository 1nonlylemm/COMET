import { Download, ExternalLink } from 'lucide-react'
import { EmptyState } from '../../../components/EmptyState'
import ReferenceTypeChip from './ReferenceTypeChip'

function effectiveDate(value) {
  if (!value) return 'Not recorded'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleDateString('en-PH', { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function PolicyReferencesTable({ references, programs, loading, actionInFlight, onDownload, renderManagement }) {
  if (loading) return <div role="status" className="p-10 text-center text-sm text-brand-text-muted">Loading policy references…</div>
  if (!references.length) return <EmptyState title="No policy references match the current filters." />
  return (
    <div role="region" aria-label="Policy references, scroll horizontally on smaller screens" tabIndex={0} className="overflow-x-auto focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand-primary">
      <table className="w-full min-w-[1100px] table-fixed text-left">
        <caption className="sr-only">Policy References</caption>
        <colgroup><col className="w-[36%]" /><col className="w-[18%]" /><col className="w-[14%]" /><col className="w-[10%]" /><col className="w-[22%]" /></colgroup>
        <thead className="data-table-header">
          <tr>{['Reference', 'Applies to', 'Effective date', 'Status', 'Actions'].map(label => <th key={label} scope="col" className="border-b border-brand-border px-4 py-3 text-xs font-semibold text-brand-text-muted">{label}</th>)}</tr>
        </thead>
        <tbody>{references.map(reference => {
          const program = programs.find(item => item.id === reference.program_id)
          const programName = reference.program_name || program?.name
          const programCode = reference.program_code || program?.code
          return (
            <tr key={reference.reference_uri} className="data-table-row">
              <td className="data-table-cell px-4 py-4">
                <p className="break-words font-medium leading-5 text-brand-text">{reference.title}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-brand-text-muted"><span className="break-words">{reference.reference_number || 'Reference number not recorded'}</span><ReferenceTypeChip referenceType={reference.reference_type} /><span>{reference.issuing_body || 'Issuer not recorded'}</span></div>
                {reference.description && <details className="mt-2 text-xs text-brand-text-muted"><summary className="cursor-pointer focus-visible:outline-2 focus-visible:outline-brand-primary">Description<span className="sr-only">: {reference.title}</span></summary><p className="mt-1 break-words leading-5">{reference.description}</p></details>}
              </td>
              <td className="data-table-cell px-4 py-4">
                {programCode && programName ? <details className="text-sm"><summary className="cursor-pointer break-words font-medium text-brand-text focus-visible:outline-2 focus-visible:outline-brand-primary"><span className="sr-only">Program details: </span>{programCode}</summary><p className="mt-2 break-words text-xs leading-5 text-brand-text-muted">{programName}</p></details> : <p className="break-words text-sm text-brand-text-muted">{programName || programCode || 'No program specified'}</p>}
              </td>
              <td className="data-table-cell px-4 py-4 text-sm text-brand-text">{effectiveDate(reference.effective_date)}</td>
              <td className="data-table-cell px-4 py-4">{reference.is_current === true ? <span className="status-badge status-badge-success">Current</span> : reference.is_current === false ? <span className="status-badge status-badge-neutral">Historical</span> : <span className="text-xs text-brand-text-muted">Not recorded</span>}</td>
              <td className="data-table-cell px-4 py-4">
                <div className="flex flex-wrap items-start gap-2">
                  {reference.file_kind === 'upload' ? <button type="button" className="btn-outline inline-flex items-center gap-2 whitespace-nowrap px-3 py-2 text-xs disabled:opacity-40" disabled={actionInFlight === reference.reference_uri} aria-label={`Download reference: ${reference.title}`} onClick={() => onDownload(reference)}><Download size={14} aria-hidden="true" />{actionInFlight === reference.reference_uri ? 'Downloading…' : 'Download reference'}</button> : reference.file_kind === 'external_url' && reference.file_path ? <a className="btn-outline inline-flex items-center gap-2 whitespace-nowrap px-3 py-2 text-xs" href={reference.file_path} target="_blank" rel="noopener noreferrer" aria-label={`Open reference: ${reference.title} (new tab)`}><ExternalLink size={14} aria-hidden="true" />Open reference</a> : <span className="py-2 text-xs text-brand-text-muted">No file or link available</span>}
                  {renderManagement(reference)}
                </div>
                {reference.file_kind === 'upload' && reference.file_name && <p className="mt-2 break-words text-xs leading-5 text-brand-text-muted">{reference.file_name}</p>}
                {reference.file_kind === 'external_url' && <p className="mt-2 text-xs text-brand-text-muted">External link · opens a new tab</p>}
              </td>
            </tr>
          )
        })}</tbody>
      </table>
    </div>
  )
}
