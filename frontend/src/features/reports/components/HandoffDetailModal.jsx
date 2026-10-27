import { useState, useMemo } from 'react'
import { Modal, Button } from '../../../components'
import {
  AlertCircle,
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Clock,
  ExternalLink,
  Filter,
  FolderArchive,
  HardDrive,
  Info,
  MapPin,
  RefreshCw,
  Search,
  UploadCloud,
  User,
  XCircle,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { ROUTES } from '../../../config/routes'

function formatDate(dateStr) {
  if (!dateStr) return '—'
  try {
    return new Date(dateStr).toLocaleDateString('en-PH', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateStr
  }
}

const STATUS_CONFIG = {
  completed: {
    label: 'Completed',
    badge: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300 ring-1 ring-emerald-200 dark:ring-emerald-800',
    icon: CheckCircle2,
  },
  in_progress: {
    label: 'In Progress',
    badge: 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300 ring-1 ring-amber-200 dark:ring-amber-800',
    icon: RefreshCw,
  },
  pending: {
    label: 'Pending',
    badge: 'bg-yellow-50 text-yellow-800 dark:bg-yellow-950/50 dark:text-yellow-300 ring-1 ring-yellow-200 dark:ring-yellow-800',
    icon: Clock,
  },
  failed: {
    label: 'Failed',
    badge: 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300 ring-1 ring-rose-200 dark:ring-rose-800',
    icon: XCircle,
  },
}

export default function HandoffDetailModal({
  transmissions = [],
  initialStatus = null,
  open,
  onClose,
}) {
  const [statusFilter, setStatusFilter] = useState(initialStatus || 'all')
  const [prevStatus, setPrevStatus] = useState(initialStatus)
  const [searchQuery, setSearchQuery] = useState('')

  if (initialStatus !== prevStatus) {
    setPrevStatus(initialStatus)
    setStatusFilter(initialStatus || 'all')
  }

  const counts = useMemo(() => {
    const res = { all: transmissions.length, completed: 0, in_progress: 0, pending: 0, failed: 0 }
    for (const t of transmissions) {
      if (t.push_status in res) {
        res[t.push_status]++
      }
    }
    return res
  }, [transmissions])

  const filteredTransmissions = useMemo(() => {
    return transmissions.filter((t) => {
      if (statusFilter !== 'all' && t.push_status !== statusFilter) {
        return false
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const matchProject = (t.project_name || '').toLowerCase().includes(q)
        const matchCode = (t.project_code || '').toLowerCase().includes(q)
        const matchLgu = (t.lgu_name || '').toLowerCase().includes(q)
        const matchDest = (t.destination_path || '').toLowerCase().includes(q)
        if (!matchProject && !matchCode && !matchLgu && !matchDest) {
          return false
        }
      }
      return true
    })
  }, [transmissions, statusFilter, searchQuery])

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Regional Handoff Transmission Records"
      size="xl"
      footer={
        <div className="flex w-full items-center justify-between">
          <span className="text-xs text-brand-text-muted">
            Showing {filteredTransmissions.length} of {transmissions.length} transmission events
          </span>
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {/* Info Banner */}
        <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-3 text-xs text-blue-800 dark:border-blue-900/50 dark:bg-blue-950/20 dark:text-blue-300 flex items-start gap-2">
          <UploadCloud className="h-4 w-4 shrink-0 mt-0.5" />
          <div>
            <strong>Regional Handoff Transmission Status:</strong> These logs document automated and manual push events syncing project closeout dossiers to the Regional DILG Google Drive document repository. Push transmission does not equate to formal regional approval.
          </div>
        </div>

        {/* Filter Pills and Search */}
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => setStatusFilter('all')}
              className={`inline-flex items-center gap-1 rounded-lg px-3 py-1 text-xs font-semibold transition-colors ${
                statusFilter === 'all'
                  ? 'bg-brand-primary text-white shadow-xs dark:text-slate-950'
                  : 'bg-brand-surface text-brand-text border border-brand-border hover:bg-slate-50 dark:hover:bg-slate-800'
              }`}
            >
              All Events ({counts.all})
            </button>

            <button
              type="button"
              onClick={() => setStatusFilter('completed')}
              className={`inline-flex items-center gap-1 rounded-lg px-3 py-1 text-xs font-semibold transition-colors ${
                statusFilter === 'completed'
                  ? 'bg-emerald-600 text-white shadow-xs'
                  : 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300 hover:bg-emerald-100'
              }`}
            >
              <CheckCircle2 className="h-3 w-3" />
              Completed ({counts.completed})
            </button>

            <button
              type="button"
              onClick={() => setStatusFilter('in_progress')}
              className={`inline-flex items-center gap-1 rounded-lg px-3 py-1 text-xs font-semibold transition-colors ${
                statusFilter === 'in_progress'
                  ? 'bg-amber-600 text-white shadow-xs'
                  : 'bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300 hover:bg-amber-100'
              }`}
            >
              <RefreshCw className="h-3 w-3" />
              In Progress ({counts.in_progress})
            </button>

            <button
              type="button"
              onClick={() => setStatusFilter('pending')}
              className={`inline-flex items-center gap-1 rounded-lg px-3 py-1 text-xs font-semibold transition-colors ${
                statusFilter === 'pending'
                  ? 'bg-yellow-600 text-white shadow-xs'
                  : 'bg-yellow-50 text-yellow-800 dark:bg-yellow-950/40 dark:text-yellow-300 hover:bg-yellow-100'
              }`}
            >
              <Clock className="h-3 w-3" />
              Pending ({counts.pending})
            </button>

            <button
              type="button"
              onClick={() => setStatusFilter('failed')}
              className={`inline-flex items-center gap-1 rounded-lg px-3 py-1 text-xs font-semibold transition-colors ${
                statusFilter === 'failed'
                  ? 'bg-rose-600 text-white shadow-xs'
                  : 'bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300 hover:bg-rose-100'
              }`}
            >
              <XCircle className="h-3 w-3" />
              Failed ({counts.failed})
            </button>
          </div>

          <div className="relative min-w-[14rem]">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-brand-text-muted" />
            <input
              type="text"
              placeholder="Search by project, LGU, path..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-brand-border bg-brand-surface py-1.5 pl-8 pr-3 text-xs text-brand-text placeholder-brand-text-muted focus:border-brand-primary focus:outline-hidden"
            />
          </div>
        </div>

        {/* Transmissions List */}
        {filteredTransmissions.length === 0 ? (
          <div className="py-8 text-center text-sm text-brand-text-muted">
            No regional handoff transmission records match the selected filters.
          </div>
        ) : (
          <div className="max-h-[60vh] space-y-3 overflow-y-auto pr-1">
            {filteredTransmissions.map((item) => {
              const cfg = STATUS_CONFIG[item.push_status] || STATUS_CONFIG.pending
              const IconComp = cfg.icon

              return (
                <div
                  key={item.id}
                  className="rounded-xl border border-brand-border bg-brand-surface p-4 shadow-xs space-y-2.5"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Link
                          to={ROUTES.projectDetail(item.project_id)}
                          className="font-semibold text-brand-primary hover:underline flex items-center gap-1 text-sm"
                        >
                          {item.project_name}
                          <ExternalLink className="h-3 w-3 inline" />
                        </Link>
                        <span className="text-xs text-brand-text-muted">·</span>
                        <span className="text-xs font-medium text-brand-text-muted flex items-center gap-1">
                          <MapPin className="h-3 w-3 inline opacity-70" />
                          {item.lgu_name}
                        </span>
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-brand-text-muted">
                        <span>Pushed: <strong>{formatDate(item.pushed_at || item.created_at)}</strong></span>
                        <span>•</span>
                        <span className="flex items-center gap-1">
                          <User className="h-3 w-3 inline" />
                          <span>By: <strong>{item.pushed_by_name}</strong></span>
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold ${cfg.badge}`}>
                        <IconComp className="h-3 w-3" />
                        {cfg.label}
                      </span>
                      <span className="rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs font-medium text-brand-text">
                        {item.files_count} {item.files_count === 1 ? 'file' : 'files'}
                      </span>
                    </div>
                  </div>

                  {/* Path & Drive Info */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs bg-slate-50/60 dark:bg-slate-900/40 rounded-lg p-2.5">
                    <div>
                      <span className="font-semibold text-brand-text block mb-0.5">Destination Path:</span>
                      <span className="font-mono text-brand-text-muted break-all text-[11px]">
                        {item.destination_path || 'PDMU Laguna / Closeout Archive'}
                      </span>
                    </div>
                    <div>
                      <span className="font-semibold text-brand-text block mb-0.5">Google Drive Folder:</span>
                      {item.drive_folder_url ? (
                        <a
                          href={item.drive_folder_url}
                          target="_blank"
                          rel="noreferrer"
                          className="font-mono text-brand-primary hover:underline break-all text-[11px] inline-flex items-center gap-1"
                        >
                          {item.drive_folder_id || 'Open in Google Drive'}
                          <ExternalLink className="h-3 w-3 shrink-0" />
                        </a>
                      ) : (
                        <span className="font-mono text-brand-text-muted text-[11px]">
                          {item.drive_folder_id || 'Local Push Stage'}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Error Message if Failed */}
                  {item.error_message && (
                    <div className="rounded-lg border border-rose-200 bg-rose-50/60 dark:border-rose-900/50 dark:bg-rose-950/20 p-2.5 text-xs text-rose-800 dark:text-rose-300">
                      <span className="font-semibold block mb-0.5">Transmission Error:</span>
                      <p>{item.error_message}</p>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </Modal>
  )
}
