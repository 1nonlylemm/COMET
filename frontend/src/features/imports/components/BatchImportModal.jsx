import { useMemo, useState } from 'react'
import { FileSpreadsheet, Upload } from 'lucide-react'
import { Button, DataTable, FeedbackToast, InlineAlert, Modal } from '../../../components'
import { formatStatus } from '../../../lib/formatters'
import * as batchImportApi from '../api/batchImportApi'

const TARGET_DETAILS = {
  users: {
    label: 'internal users',
    required: ['email', 'first_name', 'last_name', 'role'],
    optional: ['clusters', 'lgus', 'is_active'],
    note: 'Staff rows require clusters. Field officer rows require LGUs. Admin rows can leave scope blank for province-wide access.',
  },
  programs: {
    label: 'programs',
    required: ['name', 'code', 'program_type'],
    optional: ['description', 'funding_agency', 'is_active'],
    note: 'Program type accepts infrastructure, non_infrastructure, non-infrastructure, non-infra, or hybrid.',
  },
  lgus: {
    label: 'LGUs',
    required: ['name', 'municipality'],
    optional: ['province', 'cluster', 'mayor_name', 'mayor_email', 'contact_person', 'contact_email', 'contact_phone', 'is_active'],
    note: 'Cluster can be an existing cluster name or ID. Blank province defaults to Laguna.',
  },
  clusters: {
    label: 'LGU clusters',
    required: ['name'],
    optional: ['description'],
    note: 'Cluster names are matched case-insensitively to avoid duplicate coverage groups.',
  },
}

function statusClass(status) {
  if (status === 'created' || status === 'ready') return 'status-badge status-badge-success'
  if (status === 'skipped') return 'status-badge status-badge-warning'
  if (status === 'failed') return 'status-badge status-badge-danger'
  return 'status-badge status-badge-info'
}

function summaryText(summary, dryRun) {
  if (!summary) return ''
  if (dryRun) {
    return `${summary.ready || 0} ready, ${summary.skipped || 0} skipped, ${summary.failed || 0} blocked`
  }
  return `${summary.created || 0} created, ${summary.skipped || 0} skipped, ${summary.failed || 0} failed`
}

export function BatchImportModal({
  open,
  target,
  title,
  description,
  onClose,
  onImported,
}) {
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [isCommitting, setIsCommitting] = useState(false)

  const details = TARGET_DETAILS[target] || TARGET_DETAILS.clusters
  const manualCredentials = useMemo(() => (
    (result?.rows || []).filter((row) => row.delivery?.temporary_password)
  ), [result])

  const resetAndClose = () => {
    setFile(null)
    setResult(null)
    setError('')
    setIsPreviewing(false)
    setIsCommitting(false)
    onClose?.()
  }

  const runImport = async (dryRun) => {
    if (!file) {
      setError('Choose a CSV or XLSX file before importing.')
      return
    }

    const formData = new FormData()
    formData.append('file', file)
    formData.append('dry_run', dryRun ? 'true' : 'false')

    setError('')
    if (dryRun) setIsPreviewing(true)
    else setIsCommitting(true)

    try {
      const response = await batchImportApi.importTarget(target, formData)
      setResult(response.data)
      if (!dryRun) {
        onImported?.(response.data)
      }
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to process this import file.')
    } finally {
      if (dryRun) setIsPreviewing(false)
      else setIsCommitting(false)
    }
  }

  const rowColumns = [
    { key: 'row_number', label: 'Row' },
    {
      key: 'status',
      label: 'Status',
      render: (row) => <span className={statusClass(row.status)}>{formatStatus(row.status)}</span>,
    },
    { key: 'identifier', label: 'Record', render: (row) => row.identifier || '—' },
    { key: 'message', label: 'Result' },
  ]

  return (
    <Modal
      open={open}
      title={title || `Batch import ${details.label}`}
      description={description || 'Upload a CSV or XLSX file, preview row outcomes, then commit the valid rows.'}
      size="xl"
      onClose={resetAndClose}
    >
      <div className="space-y-4">
        <div className="rounded-md border border-brand-border bg-brand-surface px-4 py-3">
          <div className="flex items-start gap-3">
            <FileSpreadsheet className="mt-0.5 h-5 w-5 text-brand-primary" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-brand-text">Accepted columns</p>
              <p className="mt-1 text-xs leading-5 text-brand-text-muted">
                Required: {details.required.join(', ')}
              </p>
              <p className="text-xs leading-5 text-brand-text-muted">
                Optional: {details.optional.join(', ')}
              </p>
              <p className="mt-1 text-xs leading-5 text-brand-text-muted">{details.note}</p>
            </div>
          </div>
        </div>

        {error && (
          <InlineAlert type="error" onDismiss={() => setError('')}>
            {error}
          </InlineAlert>
        )}

        <FeedbackToast type="success" message={result?.summary ? summaryText(result.summary, result.dry_run) : ''} />

        {manualCredentials.length > 0 && (
          <InlineAlert type="warning">
            <p className="font-semibold">Manual credential handoff required</p>
            <p className="mt-1 text-sm">
              Email delivery did not complete for these accounts. Share temporary passwords only through an approved secure channel.
            </p>
            <div className="mt-3 max-h-44 overflow-y-auto rounded border border-amber-200 bg-white/70 dark:border-amber-900/60 dark:bg-amber-950/20">
              {manualCredentials.map((row) => (
                <div key={`${row.row_number}-${row.identifier}`} className="grid gap-2 border-b border-amber-200 px-3 py-2 text-sm last:border-b-0 dark:border-amber-900/60 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                  <span className="break-all font-medium">{row.identifier}</span>
                  <span className="break-all font-mono">{row.delivery.temporary_password}</span>
                </div>
              ))}
            </div>
          </InlineAlert>
        )}

        <div>
          <label htmlFor={`batch-import-${target}`} className="label-text">Import file</label>
          <input
            id={`batch-import-${target}`}
            type="file"
            accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="input-field mt-1"
            onChange={(event) => {
              setFile(event.target.files?.[0] || null)
              setResult(null)
              setError('')
            }}
          />
          {file && (
            <p className="mt-1 text-xs text-brand-text-muted">
              Selected: {file.name}
            </p>
          )}
        </div>

        {result?.rows?.length > 0 && (
          <DataTable
            columns={rowColumns}
            data={result.rows}
            keyField="row_number"
            caption="Batch import row results"
            hidePagination
            density="compact"
          />
        )}

        <div className="flex flex-col gap-3 border-t border-brand-border pt-4 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={resetAndClose}>Close</Button>
          <Button variant="outline" icon={FileSpreadsheet} loading={isPreviewing} onClick={() => runImport(true)}>
            Preview Rows
          </Button>
          <Button icon={Upload} loading={isCommitting} onClick={() => runImport(false)}>
            Import Valid Rows
          </Button>
        </div>
      </div>
    </Modal>
  )
}
