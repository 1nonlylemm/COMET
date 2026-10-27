import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { formatTableCell } from '../lib/formatters'
import { EmptyState } from './EmptyState'

export function DataTable({
  columns,
  data,
  keyField = 'id',
  getRowId,
  onRowClick,
  emptyMessage = 'No data found',
  isLoading = false,
  caption,
  hidePagination = false,
  density = 'normal',
  getRowClassName,
  preserveEmptyTable = false,
  selectedRowId,
}) {
  const [page, setPage] = useState(1)
  const perPage = 20
  const totalPages = Math.max(1, Math.ceil(data.length / perPage))
  const shouldPaginate = !hidePagination && totalPages > 1
  const pageData = shouldPaginate ? data.slice((page - 1) * perPage, page * perPage) : data
  const cellPadding = density === 'compact' ? 'px-2 py-2' : 'px-3 py-2.5'

  if (isLoading) {
    return (
      <div className="data-table-panel">
        <div className="p-8 text-center text-sm text-brand-text-muted">
          <div className="animate-spin h-8 w-8 border-2 border-brand-primary border-t-transparent rounded-full mx-auto mb-3" />
          Loading records...
        </div>
      </div>
    )
  }

  if (data.length === 0 && !preserveEmptyTable) {
    return (
      <div className="data-table-panel">
        <EmptyState title={emptyMessage} />
      </div>
    )
  }

  return (
    <div className="data-table-panel">
      <div className="overflow-x-auto">
        <table className="w-full">
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead>
            <tr className="data-table-header transition-colors">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={`micro-text ${cellPadding} text-left font-semibold border-b border-brand-border`}
                  scope="col"
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.length === 0 ? (
              <tr className="data-table-row">
                <td className={`data-table-cell ${cellPadding} text-center text-brand-text-muted`} colSpan={columns.length}>
                  {emptyMessage}
                </td>
              </tr>
            ) : pageData.map((row, index) => {
              const rowId = getRowId ? getRowId(row, index) : row[keyField] ?? index
              const isSelected = selectedRowId !== undefined && rowId === selectedRowId
              return (
              <tr
                key={rowId}
                className={`data-table-row ${onRowClick ? 'cursor-pointer' : ''} ${isSelected ? 'bg-brand-primary/10 dark:bg-brand-primary/20' : ''} ${getRowClassName?.(row, index) || ''}`}
                onClick={(event) => onRowClick?.(row, event)}
                tabIndex={onRowClick ? 0 : undefined}
                onKeyDown={(event) => {
                  if (!onRowClick) return
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onRowClick(row, event)
                  }
                }}
              >
                {columns.map((col) => (
                  <td key={col.key} className={`data-table-cell ${cellPadding}`}>
                    {col.render ? col.render(row) : formatTableCell(row[col.key], col.key)}
                  </td>
                ))}
              </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {shouldPaginate && (
        <div className="flex items-center justify-between border-t border-brand-border bg-brand-surface px-4 py-3">
          <span className="text-sm text-brand-text-muted">
            Showing {(page - 1) * perPage + 1}-{Math.min(page * perPage, data.length)} of {data.length}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="btn-outline text-sm px-3 py-1 disabled:opacity-30"
              aria-label="Previous page"
              title="Previous page"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="py-1 text-sm font-medium text-brand-text-muted">{page} / {totalPages}</span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="btn-outline text-sm px-3 py-1 disabled:opacity-30"
              aria-label="Next page"
              title="Next page"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
