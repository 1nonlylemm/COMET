import { useEffect, useRef, useState } from 'react'
import { FileDown, Loader2 } from 'lucide-react'
import { Modal } from '../../../components/Modal'
import { exportMonitoringUpdatesPdf } from '../api/reportsApi'
import { fileTransferErrorMessage } from '../../../lib/fileTransfer'

export default function ExportPdfModal({
  isOpen,
  onClose,
  activeFilters = {},
  activeFilterSummary = 'Current selection',
  selectedProjectIds = null,
}) {
  const [scope, setScope] = useState('all')
  const [includeAppendix, setIncludeAppendix] = useState(false)
  const [orientation, setOrientation] = useState('landscape')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const exportingRef = useRef(false)

  useEffect(() => {
    if (!isOpen) return
    setError('')
    setScope('all')
    setIncludeAppendix(false)
    setOrientation('landscape')
  }, [isOpen])

  const close = () => {
    if (!exportingRef.current) onClose()
  }

  const handleExport = async (event) => {
    event.preventDefault()
    if (exportingRef.current) return
    exportingRef.current = true
    setLoading(true)
    setError('')

    const filters = scope === 'all'
      ? { fiscal_year: activeFilters.fiscal_year }
      : { ...activeFilters, ...(selectedProjectIds !== null ? { project_ids: selectedProjectIds } : {}) }

    const recordDetail = includeAppendix ? 'full' : 'summary'
    const riskDetail = includeAppendix ? 'comprehensive' : 'executive'
    const tabs = ['monitoring', 'documents']

    try {
      const response = await exportMonitoringUpdatesPdf({
        tabs,
        scope,
        risk_detail: riskDetail,
        record_detail: recordDetail,
        include_appendix: includeAppendix,
        orientation,
        filters,
      })
      const disposition = response.headers?.['content-disposition'] || ''
      const filename = disposition.match(/filename="?([^";]+)"?/)?.[1] || 'Reports_Analytics.pdf'
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      onClose()
    } catch (requestError) {
      setError(await fileTransferErrorMessage(requestError, 'The report could not be generated. Please try again.'))
    } finally {
      exportingRef.current = false
      setLoading(false)
    }
  }

  return (
    <Modal
      open={isOpen}
      onClose={close}
      title="Export Reports & Analytics"
      description="Choose the records and appendix options for your PDF report."
      size="lg"
      workspace
      fitContent
    >
      <form onSubmit={handleExport} className="space-y-5">
        {error && (
          <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        )}

        {/* 1. Records Scope */}
        <fieldset disabled={loading} className="space-y-2">
          <legend className="mb-2 text-sm font-semibold text-brand-text">Records to include</legend>
          <label className="flex gap-3 rounded-lg border border-brand-border p-3 text-sm text-brand-text cursor-pointer hover:bg-brand-surface-secondary/40">
            <input
              type="radio"
              name="scope"
              value="all"
              checked={scope === 'all'}
              onChange={() => setScope('all')}
              className="mt-0.5"
            />
            <span>
              Full portfolio for FY {activeFilters.fiscal_year || 'selected year'}
              <small className="mt-1 block text-brand-text-muted">
                All projects you are authorized to view. Search and chart selections are cleared.
              </small>
            </span>
          </label>
          <label className="flex gap-3 rounded-lg border border-brand-border p-3 text-sm text-brand-text cursor-pointer hover:bg-brand-surface-secondary/40">
            <input
              type="radio"
              name="scope"
              value="filtered"
              checked={scope === 'filtered'}
              onChange={() => setScope('filtered')}
              className="mt-0.5"
            />
            <span>
              Current selection{selectedProjectIds !== null ? ` (${selectedProjectIds.length} project${selectedProjectIds.length === 1 ? '' : 's'})` : ''}
              <small className="mt-1 block break-words text-brand-text-muted">{activeFilterSummary}</small>
            </span>
          </label>
          <p className="text-xs text-brand-text-muted">
            Totals and charts are recalculated for the exported projects, including their full recorded history. Record-level selections identify projects. Fiscal year and access permissions always apply.
          </p>
        </fieldset>

        {/* 2. Standard Overview Report & Optional Appendix */}
        <fieldset disabled={loading} className="space-y-3">
          <legend className="mb-2 text-sm font-semibold text-brand-text">Report content</legend>

          <div className="rounded-lg border border-brand-border bg-slate-50/60 dark:bg-slate-800/40 p-3 text-sm text-brand-text">
            <span className="font-semibold text-brand-primary">Standard Overview Report</span>
            <small className="block text-brand-text-muted mt-0.5">
              Authoritative single-page overview: Project Implementation Status Distribution, Program & Cluster Summary, Completion Documents & Closeout, and Documentary Compliance by LGU.
            </small>
          </div>

          <label className="flex items-start gap-2.5 rounded-lg border border-brand-border p-3 text-sm text-brand-text cursor-pointer hover:bg-brand-surface-secondary/40">
            <input
              type="checkbox"
              id="include-appendix-checkbox"
              checked={includeAppendix}
              onChange={(e) => setIncludeAppendix(e.target.checked)}
              className="mt-0.5 rounded border-brand-border"
            />
            <div>
              <span className="font-medium">Include Supporting Records Appendix</span>
              <small className="block text-brand-text-muted mt-0.5">
                Adds individual project monitoring detail, documentary compliance register, active workflow requirements, and return event logs. Large portfolios may produce many pages.
              </small>
            </div>
          </label>
        </fieldset>

        {/* 3. Page Layout */}
        <details className="text-sm text-brand-text">
          <summary className="cursor-pointer font-medium">Page layout</summary>
          <label className="mt-3 block">
            Orientation
            <select
              aria-label="Page orientation"
              value={orientation}
              disabled={loading}
              onChange={(event) => setOrientation(event.target.value)}
              className="input-field mt-1 w-full"
            >
              <option value="landscape">Landscape</option>
              <option value="portrait">Portrait</option>
            </select>
          </label>
        </details>

        <div className="flex flex-wrap items-center justify-end gap-3 border-t border-brand-border pt-4">
          <button type="button" onClick={close} disabled={loading} className="btn-outline px-4 py-2">
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading}
            className="btn-primary flex items-center gap-2 px-4 py-2"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />}
            {loading ? 'Generating PDF…' : 'Download PDF'}
          </button>
        </div>

        {loading && <p role="status" className="text-sm text-brand-text-muted">Generating the report. Keep this window open.</p>}
      </form>
    </Modal>
  )
}
