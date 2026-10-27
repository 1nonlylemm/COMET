import { useCallback, useEffect, useState } from 'react'
import {
  Activity,
  AlertCircle,
  Clock,
  Eye,
  Filter,
  Info,
  RefreshCw,
  Search,
  Server,
  X,
} from 'lucide-react'
import {
  Button,
  DataTable,
  FormField,
  GlassPanel,
  InlineAlert,
  Modal,
  PageHeader,
} from '../../../components'
import { formatDateTime } from '../../../lib/formatters'
import * as systemAdminApi from '../api/systemAdminApi'

const SEVERITY_OPTIONS = [
  { value: '', label: 'All Severities' },
  { value: 'CRITICAL', label: 'CRITICAL' },
  { value: 'ERROR', label: 'ERROR' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'INFO', label: 'INFO' },
  { value: 'DEBUG', label: 'DEBUG' },
]

const SEVERITY_TONES = {
  CRITICAL: 'status-badge-danger',
  ERROR: 'status-badge-danger',
  WARNING: 'status-badge-warning',
  INFO: 'status-badge-info',
  DEBUG: 'status-badge-neutral',
}

function SeverityBadge({ severity }) {
  const tone = SEVERITY_TONES[severity] || 'status-badge-neutral'
  return <span className={`status-badge ${tone}`}>{severity || 'UNKNOWN'}</span>
}

export default function SystemAdminDiagnosticsPage() {
  const [events, setEvents] = useState([])
  const [meta, setMeta] = useState({ page: 1, per_page: 20, total_pages: 1, total_items: 0, has_next: false, has_prev: false })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filters state
  const [filters, setFilters] = useState({
    severity: '',
    component: '',
    search: '',
    request_id: '',
    operation_id: '',
    start_time: '',
    end_time: '',
  })
  const [page, setPage] = useState(1)

  // Detail modal state
  const [selectedEventId, setSelectedEventId] = useState(null)
  const [eventDetail, setEventDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState(null)

  const fetchEvents = useCallback(async (targetPage = page) => {
    setLoading(true)
    setError(null)
    try {
      const params = {
        page: targetPage,
        per_page: 20,
      }
      if (filters.severity) params.severity = filters.severity
      if (filters.component.trim()) params.component = filters.component.trim()
      if (filters.search.trim()) params.search = filters.search.trim()
      if (filters.request_id.trim()) params.request_id = filters.request_id.trim()
      if (filters.operation_id.trim()) params.operation_id = filters.operation_id.trim()
      if (filters.start_time) params.start_time = `${filters.start_time}T00:00:00Z`
      if (filters.end_time) params.end_time = `${filters.end_time}T23:59:59Z`

      const res = await systemAdminApi.listOperationalEvents(params)
      setEvents(res.data || [])
      if (res.meta) setMeta(res.meta)
    } catch (err) {
      setError(err?.response?.data?.message || err?.message || 'Failed to load operational events.')
    } finally {
      setLoading(false)
    }
  }, [filters, page])

  useEffect(() => {
    fetchEvents(page)
  }, [fetchEvents, page])

  const handleFilterChange = (field, value) => {
    setFilters((prev) => ({ ...prev, [field]: value }))
  }

  const handleApplyFilters = (e) => {
    if (e) e.preventDefault()
    setPage(1)
    fetchEvents(1)
  }

  const handleResetFilters = () => {
    setFilters({
      severity: '',
      component: '',
      search: '',
      request_id: '',
      operation_id: '',
      start_time: '',
      end_time: '',
    })
    setPage(1)
  }

  const handleInspect = async (event) => {
    setSelectedEventId(event.id)
    setEventDetail(event) // Show summary while loading details
    setDetailLoading(true)
    setDetailError(null)

    try {
      const res = await systemAdminApi.getOperationalEvent(event.id)
      setEventDetail(res.data)
    } catch (err) {
      setDetailError(err?.response?.data?.message || err?.message || 'Failed to fetch event details.')
    } finally {
      setDetailLoading(false)
    }
  }

  const handleCloseModal = () => {
    setSelectedEventId(null)
    setEventDetail(null)
    setDetailError(null)
  }

  const tableColumns = [
    {
      key: 'timestamp',
      label: 'Timestamp',
      className: 'whitespace-nowrap text-xs text-brand-text-muted',
      render: (row) => formatDateTime(row.timestamp),
    },
    {
      key: 'severity',
      label: 'Severity',
      className: 'whitespace-nowrap',
      render: (row) => <SeverityBadge severity={row.severity} />,
    },
    {
      key: 'component',
      label: 'Component',
      className: 'whitespace-nowrap font-mono text-xs text-brand-text-muted',
      render: (row) => row.component || '—',
    },
    {
      key: 'event_name',
      label: 'Event & Message',
      render: (row) => (
        <div className="max-w-md">
          <div className="font-semibold text-xs text-brand-text">{row.event_name}</div>
          <div className="text-xs text-brand-text-muted truncate mt-0.5" title={row.message}>
            {row.message}
          </div>
        </div>
      ),
    },
    {
      key: 'identifiers',
      label: 'Identifiers',
      className: 'whitespace-nowrap text-xs font-mono text-brand-text-muted',
      render: (row) => (
        <div className="space-y-0.5 text-xs">
          {row.request_id && (
            <div title={`Request ID: ${row.request_id}`}>
              <span className="text-slate-400">req:</span> {row.request_id.slice(0, 14)}…
            </div>
          )}
          {row.operation_id && (
            <div title={`Operation ID: ${row.operation_id}`}>
              <span className="text-slate-400">op:</span> {row.operation_id.slice(0, 14)}…
            </div>
          )}
          {!row.request_id && !row.operation_id && <span>—</span>}
        </div>
      ),
    },
    {
      key: 'actions',
      label: 'Action',
      className: 'text-right whitespace-nowrap',
      render: (row) => (
        <Button
          size="sm"
          variant="outline"
          onClick={() => handleInspect(row)}
          className="inline-flex items-center gap-1 text-xs"
        >
          <Eye className="w-3.5 h-3.5" />
          Inspect
        </Button>
      ),
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title="System Diagnostics"
        subtitle="Inspect application runtime operational events, backend errors, and system diagnostic logs."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchEvents(page)}
            disabled={loading}
            className="inline-flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        }
      />

      {/* Outage Fallback Notice Banner */}
      <InlineAlert
        variant="info"
        title="Diagnostic Availability Notice"
      >
        Technical operational events are recorded to the database when available. During a database outage or connection failure, events may not be listed here; Docker container log streams (stdout/stderr) serve as the primary external diagnostic path for outage investigation.
      </InlineAlert>

      {/* Filters Panel */}
      <GlassPanel className="p-4 space-y-4">
        <form onSubmit={handleApplyFilters} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            <FormField label="Search Message or Event">
              <input
                type="text"
                placeholder="Search error message..."
                value={filters.search}
                onChange={(e) => handleFilterChange('search', e.target.value)}
                className="input-field text-sm w-full"
              />
            </FormField>

            <FormField label="Severity">
              <select
                value={filters.severity}
                onChange={(e) => handleFilterChange('severity', e.target.value)}
                className="input-field text-sm w-full"
              >
                {SEVERITY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label="Component">
              <input
                type="text"
                placeholder="e.g. api, celery_worker"
                value={filters.component}
                onChange={(e) => handleFilterChange('component', e.target.value)}
                className="input-field text-sm w-full"
              />
            </FormField>

            <FormField label="Request or Operation ID">
              <input
                type="text"
                placeholder="Exact ID match..."
                value={filters.request_id || filters.operation_id}
                onChange={(e) => {
                  handleFilterChange('request_id', e.target.value)
                  handleFilterChange('operation_id', e.target.value)
                }}
                className="input-field text-sm w-full"
              />
            </FormField>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
            <FormField label="From Date">
              <input
                type="date"
                value={filters.start_time}
                onChange={(e) => handleFilterChange('start_time', e.target.value)}
                className="input-field text-sm w-full"
              />
            </FormField>

            <FormField label="To Date">
              <input
                type="date"
                value={filters.end_time}
                onChange={(e) => handleFilterChange('end_time', e.target.value)}
                className="input-field text-sm w-full"
              />
            </FormField>

            <div className="flex gap-2 justify-end">
              <Button type="button" variant="outline" size="sm" onClick={handleResetFilters}>
                Clear Filters
              </Button>
              <Button type="submit" variant="primary" size="sm" disabled={loading}>
                Apply Filters
              </Button>
            </div>
          </div>
        </form>
      </GlassPanel>

      {/* Events Table & Pagination */}
      <GlassPanel className="p-4 space-y-4">
        {error && (
          <InlineAlert variant="danger" title="Failed to Load Events">
            <div className="flex items-center justify-between gap-4">
              <span>{error}</span>
              <Button size="sm" variant="outline" onClick={() => fetchEvents(page)}>
                Retry
              </Button>
            </div>
          </InlineAlert>
        )}

        {loading ? (
          <div className="flex justify-center items-center py-12 text-sm text-brand-text-muted">
            <RefreshCw className="w-5 h-5 animate-spin mr-2" />
            Loading operational diagnostic events...
          </div>
        ) : events.length === 0 ? (
          <div className="text-center py-12 space-y-2">
            <Activity className="w-10 h-10 text-brand-text-muted mx-auto opacity-50" />
            <div className="text-base font-semibold text-brand-text">No Operational Events Found</div>
            <p className="text-xs text-brand-text-muted max-w-sm mx-auto">
              No diagnostic events match the current filter criteria, or the event retention threshold has pruned older records.
            </p>
            <Button size="sm" variant="outline" onClick={handleResetFilters} className="mt-2">
              Clear Filters
            </Button>
          </div>
        ) : (
          <>
            <DataTable columns={tableColumns} data={events} />

            {/* Pagination Controls */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-2 pt-4 border-t border-brand-border text-xs text-brand-text-muted">
              <div>
                Showing page <span className="font-semibold text-brand-text">{meta.page}</span> of{' '}
                <span className="font-semibold text-brand-text">{meta.total_pages || 1}</span> (
                {meta.total_items} total recorded events)
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!meta.has_prev || loading}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Previous
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!meta.has_next || loading}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </GlassPanel>

      {/* Event Detail Modal */}
      {selectedEventId && eventDetail && (
        <Modal
          open={true}
          onClose={handleCloseModal}
          title={`Diagnostic Event #${eventDetail.id}`}
        >
          <div className="space-y-4 max-h-[75vh] overflow-y-auto pr-1">
            {detailError && (
              <InlineAlert variant="danger" title="Detail Error">
                {detailError}
              </InlineAlert>
            )}

            {detailLoading && (
              <div className="text-xs text-brand-text-muted flex items-center gap-1.5">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Fetching detailed diagnostic payload...
              </div>
            )}

            {/* Metadata Badges & Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 p-3 rounded-lg bg-slate-50 dark:bg-slate-900 border border-brand-border text-xs">
              <div>
                <span className="text-brand-text-muted block text-[10px] uppercase font-semibold">Severity</span>
                <SeverityBadge severity={eventDetail.severity} />
              </div>
              <div>
                <span className="text-brand-text-muted block text-[10px] uppercase font-semibold">Component</span>
                <span className="font-mono text-brand-text font-medium">{eventDetail.component}</span>
              </div>
              <div>
                <span className="text-brand-text-muted block text-[10px] uppercase font-semibold">Event Name</span>
                <span className="font-semibold text-brand-text">{eventDetail.event_name}</span>
              </div>
              <div>
                <span className="text-brand-text-muted block text-[10px] uppercase font-semibold">Timestamp</span>
                <span className="text-brand-text">{formatDateTime(eventDetail.timestamp)}</span>
              </div>
              <div>
                <span className="text-brand-text-muted block text-[10px] uppercase font-semibold">Request ID</span>
                <span className="font-mono text-brand-text text-[11px] truncate block" title={eventDetail.request_id}>
                  {eventDetail.request_id || '—'}
                </span>
              </div>
              <div>
                <span className="text-brand-text-muted block text-[10px] uppercase font-semibold">Operation ID</span>
                <span className="font-mono text-brand-text text-[11px] truncate block" title={eventDetail.operation_id}>
                  {eventDetail.operation_id || '—'}
                </span>
              </div>
            </div>

            {/* Error Message */}
            <div>
              <div className="text-xs font-semibold text-brand-text mb-1">Sanitized Error Message</div>
              <div className="p-3 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/40 rounded text-xs text-red-900 dark:text-red-200 font-mono whitespace-pre-wrap break-words">
                {eventDetail.message}
              </div>
            </div>

            {/* Traceback Section - Rendered strictly as plain text */}
            {eventDetail.traceback && (
              <div>
                <div className="text-xs font-semibold text-brand-text mb-1">Exception Traceback (Plain Text)</div>
                <pre
                  data-testid="traceback-container"
                  className="p-3 bg-slate-950 text-emerald-400 dark:bg-slate-900 rounded text-xs font-mono whitespace-pre-wrap break-all overflow-x-auto max-h-64 select-text"
                >
                  {eventDetail.traceback}
                </pre>
              </div>
            )}

            {/* Context Data Section */}
            {eventDetail.context_data && Object.keys(eventDetail.context_data).length > 0 && (
              <div>
                <div className="text-xs font-semibold text-brand-text mb-1">Context Payload</div>
                <pre
                  data-testid="context-container"
                  className="p-3 bg-slate-950 text-slate-200 dark:bg-slate-900 rounded text-xs font-mono whitespace-pre-wrap break-all overflow-x-auto max-h-48 select-text"
                >
                  {JSON.stringify(eventDetail.context_data, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  )
}
