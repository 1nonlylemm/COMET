import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  ClipboardList,
  Clock,
  ExternalLink,
  Filter,
  MapPinned,
  MessageSquarePlus,
  RefreshCw,
  Search,
  ShieldCheck,
  SortAsc,
  X,
} from 'lucide-react'
import { Button, FeedbackToast, FormField, GlassPanel, InlineAlert, KpiCard, Modal, PageHeader, ProgramPausedBanner, ErrorBoundary } from '../../../components'
import { ROUTES } from '../../../config/routes'
import { formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import * as fieldApi from '../api/fieldApi'

const COMMENT_TYPES = [
  { value: 'field_follow_up', label: 'Field follow-up' },
  { value: 'submission_update', label: 'Submission update' },
  { value: 'clarification', label: 'Clarification' },
  { value: 'acknowledgement', label: 'Acknowledgement' },
  { value: 'comment', label: 'General comment' },
]

const priorityTone = {
  critical: {
    badge: 'status-badge-danger',
    rail: 'bg-red-700 dark:bg-red-300',
  },
  high: {
    badge: 'status-badge-warning',
    rail: 'bg-amber-600 dark:bg-amber-300',
  },
  medium: {
    badge: 'status-badge-info',
    rail: 'bg-blue-600 dark:bg-blue-300',
  },
  low: {
    badge: 'status-badge-neutral',
    rail: 'bg-slate-500 dark:bg-slate-300',
  },
}

function formatDate(value) {
  if (!value) return 'No due date'
  try {
    return new Date(value).toLocaleDateString('en-PH', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return value
  }
}

function formatNumber(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '0'
  return number.toLocaleString('en-PH')
}

function truncate(value, maxLength = 120) {
  if (!value) return ''
  return value.length > maxLength ? `${value.slice(0, maxLength).trim()}...` : value
}

function actionMeta(item) {
  if (item.type === 'deadline') {
    return {
      label: item.status === 'overdue' ? 'Overdue timer' : 'Working-day timer',
      icon: Clock,
    }
  }
  if (item.type === 'monitoring') {
    return {
      label: 'Monitoring',
      icon: MapPinned,
    }
  }
  return {
    label: 'Requirement',
    icon: ClipboardList,
  }
}

function ActionQueue({ items, loading, onComment }) {
  const [filterPriority, setFilterPriority] = useState('all')
  const [filterType, setFilterType] = useState('all')
  const [sortBy, setSortBy] = useState('priority')

  const filteredAndSortedItems = useMemo(() => {
    let filtered = [...items]

    // Filter by priority
    if (filterPriority !== 'all') {
      filtered = filtered.filter(item => item.priority === filterPriority)
    }

    // Filter by type
    if (filterType !== 'all') {
      filtered = filtered.filter(item => item.type === filterType)
    }

    // Sort items
    filtered.sort((a, b) => {
      if (sortBy === 'priority') {
        const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 }
        return priorityOrder[a.priority] - priorityOrder[b.priority]
      }
      if (sortBy === 'due_date') {
        if (!a.due_at) return 1
        if (!b.due_at) return -1
        return new Date(a.due_at) - new Date(b.due_at)
      }
      if (sortBy === 'type') {
        return (a.type || '').localeCompare(b.type || '')
      }
      return 0
    })

    return filtered
  }, [items, filterPriority, filterType, sortBy])

  const hasActiveFilters = filterPriority !== 'all' || filterType !== 'all'

  const clearFilters = () => {
    setFilterPriority('all')
    setFilterType('all')
  }

  if (loading) {
    return (
      <div className="border-t border-brand-border px-5 py-12 text-center">
        <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-3 border-brand-primary border-t-transparent" />
        <p className="text-sm font-medium text-brand-text">Loading field actions...</p>
        <p className="mt-1 text-sm text-brand-text-muted">Fetching your assigned work items</p>
      </div>
    )
  }

  if (!items.length) {
    return (
      <div className="border-t border-brand-border px-5 py-12 text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-50 dark:bg-emerald-950">
          <CheckCircle2 className="h-8 w-8 text-emerald-600 dark:text-emerald-400" strokeWidth={2} />
        </div>
        <h3 className="text-base font-semibold text-brand-text">All clear!</h3>
        <p className="mt-2 text-sm text-brand-text-muted">No field action items at this time.</p>
        <p className="mt-1 text-sm text-brand-text-muted">Your assigned LGUs and requirements are up to date.</p>
      </div>
    )
  }

  return (
    <>
      {/* Filter and Sort Controls */}
      <div className="border-t border-brand-border bg-brand-surface px-5 py-4">
        <div className="flex flex-wrap items-center gap-3">
          {/* Priority Filter */}
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-brand-text-muted" />
            <select
              value={filterPriority}
              onChange={(e) => setFilterPriority(e.target.value)}
              className="rounded-md border border-brand-border bg-brand-surface-solid px-3 py-1.5 text-sm text-brand-text focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
            >
              <option value="all">All Priorities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          {/* Type Filter */}
          <div className="flex items-center gap-2">
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="rounded-md border border-brand-border bg-brand-surface-solid px-3 py-1.5 text-sm text-brand-text focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
            >
              <option value="all">All Types</option>
              <option value="deadline">Deadlines</option>
              <option value="monitoring">Monitoring</option>
              <option value="requirement">Requirements</option>
            </select>
          </div>

          {/* Sort */}
          <div className="flex items-center gap-2">
            <SortAsc className="h-4 w-4 text-brand-text-muted" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="rounded-md border border-brand-border bg-brand-surface-solid px-3 py-1.5 text-sm text-brand-text focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
            >
              <option value="priority">Sort by Priority</option>
              <option value="due_date">Sort by Due Date</option>
              <option value="type">Sort by Type</option>
            </select>
          </div>

          {/* Clear Filters */}
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="inline-flex items-center gap-1.5 rounded-md bg-brand-primary/10 px-3 py-1.5 text-sm font-medium text-brand-primary hover:bg-brand-primary/20"
            >
              <X className="h-3.5 w-3.5" />
              Clear filters
            </button>
          )}

          {/* Results count */}
          <div className="ml-auto text-sm text-brand-text-muted">
            Showing <span className="font-semibold text-brand-text">{filteredAndSortedItems.length}</span> of {items.length} items
          </div>
        </div>
      </div>

      {filteredAndSortedItems.length === 0 ? (
        <div className="border-t border-brand-border px-5 py-12 text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-slate-50 dark:bg-slate-900">
            <Filter className="h-8 w-8 text-slate-400" strokeWidth={2} />
          </div>
          <h3 className="text-base font-semibold text-brand-text">No items match your filters</h3>
          <p className="mt-2 text-sm text-brand-text-muted">Try adjusting your filters to see more results.</p>
          <button
            onClick={clearFilters}
            className="mt-4 inline-flex items-center gap-2 rounded-md border border-brand-border bg-brand-surface-solid px-4 py-2 text-sm font-medium text-brand-text hover:bg-brand-surface"
          >
            Clear all filters
          </button>
        </div>
      ) : (
        <ul className="border-t border-brand-border">
          {filteredAndSortedItems.map((item) => {
        const tone = priorityTone[item.priority] || priorityTone.low
        const meta = actionMeta(item)
        const Icon = meta.icon
        const projectId = item.project_id || item.payload?.project_id
        const requirementId = item.project_requirement_id
        const projectName = item.payload?.project_name || item.description || 'Assigned project'
        const lguName = item.payload?.lgu_name || 'Assigned LGU'

        return (
          <li key={`${item.type}-${item.entity_id}-${projectId || 'project'}`} className="relative border-b border-brand-border bg-brand-surface-solid px-5 py-4 pl-6 dark:bg-brand-surface">
            <span className={`absolute inset-y-0 left-0 w-1 ${tone.rail}`} aria-hidden="true" />
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`status-badge ${tone.badge}`}>{formatStatus(item.priority)}</span>
                  <span className="inline-flex items-center gap-1.5 rounded-sm border border-brand-border bg-brand-surface px-2 py-0.5 text-xs font-semibold text-brand-text">
                    <Icon className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden="true" />
                    {meta.label}
                  </span>
                  {item.due_at && (
                    <span className="text-xs font-medium text-brand-text-muted">Due {formatDate(item.due_at)}</span>
                  )}
                </div>
                <h3 className="mt-2 text-sm font-semibold text-brand-text">{item.title}</h3>
                {item.payload?.requirement_name && (
                  <p className="mt-1 text-sm font-medium text-brand-text">{item.payload.requirement_name}</p>
                )}
                <p className="mt-1 text-sm text-brand-text-muted">{truncate(item.description)}</p>
                <p className="mt-2 text-xs text-brand-text-muted">
                  {projectName}
                  {lguName ? ` / ${lguName}` : ''}
                </p>
              </div>
              <div className="flex flex-wrap gap-2 lg:justify-end">
                {projectId && (
                  <Link
                    to={`${ROUTES.projectDetail(projectId)}${requirementId ? `?tab=requirements&req=${requirementId}` : ''}`}
                    className="inline-flex min-h-10 items-center justify-center gap-2 rounded-md border border-brand-border bg-brand-surface-solid px-3 py-2 text-sm font-medium text-brand-text shadow-sm transition-colors hover:bg-brand-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/35"
                  >
                    Open project
                    <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden="true" />
                  </Link>
                )}
                {requirementId && (
                  <Button variant="outline" size="sm" icon={MessageSquarePlus} onClick={() => onComment(item)}>
                    Add field note
                  </Button>
                )}
              </div>
            </div>
          </li>
        )
      })}
        </ul>
      )}
    </>
  )
}

function AssignedLguList({ lgus }) {
  const [searchTerm, setSearchTerm] = useState('')

  const filteredLgus = useMemo(() => {
    if (!searchTerm.trim()) return lgus
    const term = searchTerm.toLowerCase()
    return lgus.filter(lgu =>
      lgu.name.toLowerCase().includes(term) ||
      (lgu.municipality && lgu.municipality.toLowerCase().includes(term)) ||
      (lgu.province && lgu.province.toLowerCase().includes(term)) ||
      (lgu.cluster_name && lgu.cluster_name.toLowerCase().includes(term))
    )
  }, [lgus, searchTerm])

  if (!lgus.length) {
    return (
      <div className="border-t border-brand-border px-5 py-12 text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-amber-50 dark:bg-amber-950">
          <Building2 className="h-8 w-8 text-amber-600 dark:text-amber-400" strokeWidth={2} />
        </div>
        <h3 className="text-base font-semibold text-brand-text">No LGU assignments</h3>
        <p className="mt-2 text-sm text-brand-text-muted">This account has no active LGU assignments.</p>
        <p className="mt-1 text-sm text-brand-text-muted">Contact your administrator for access.</p>
      </div>
    )
  }

  return (
    <>
      {/* Search Bar */}
      {lgus.length > 3 && (
        <div className="border-t border-brand-border bg-brand-surface px-5 py-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-brand-text-muted" />
            <input
              type="text"
              placeholder="Search LGUs by name, municipality, province..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full rounded-md border border-brand-border bg-brand-surface-solid py-2 pl-10 pr-4 text-sm text-brand-text placeholder-brand-text-muted focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-brand-text-muted hover:text-brand-text"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
          {searchTerm && (
            <p className="mt-2 text-xs text-brand-text-muted">
              Found <span className="font-semibold text-brand-text">{filteredLgus.length}</span> of {lgus.length} LGUs
            </p>
          )}
        </div>
      )}

      {filteredLgus.length === 0 ? (
        <div className="border-t border-brand-border px-5 py-12 text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-slate-50 dark:bg-slate-900">
            <Search className="h-8 w-8 text-slate-400" strokeWidth={2} />
          </div>
          <h3 className="text-base font-semibold text-brand-text">No LGUs found</h3>
          <p className="mt-2 text-sm text-brand-text-muted">No LGUs match "{searchTerm}"</p>
          <button
            onClick={() => setSearchTerm('')}
            className="mt-4 inline-flex items-center gap-2 rounded-md border border-brand-border bg-brand-surface-solid px-4 py-2 text-sm font-medium text-brand-text hover:bg-brand-surface"
          >
            Clear search
          </button>
        </div>
      ) : (
        <ul className="divide-y divide-brand-border border-t border-brand-border">
          {filteredLgus.map((lgu) => (
        <li key={lgu.id} className="px-5 py-5 transition-colors hover:bg-brand-surface">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="min-w-0 flex-1">
              <Link to={ROUTES.lguDetail(lgu.id)} className="inline-flex items-center gap-2 text-base font-semibold text-brand-text hover:text-brand-primary transition-colors">
                <Building2 className="h-4 w-4 flex-shrink-0" strokeWidth={2} />
                <span className="truncate">{lgu.name}</span>
              </Link>
              <p className="mt-1.5 text-sm text-brand-text-muted">
                {lgu.municipality && lgu.province ? `${lgu.municipality}, ${lgu.province}` : (lgu.cluster_name || 'No cluster label')}
              </p>
            </div>
            <span className={badgeClassForStatus(lgu.is_active ? 'active' : 'inactive')}>
              {lgu.is_active ? 'Active' : 'Inactive'}
            </span>
          </div>
          <dl className="grid grid-cols-3 gap-4 rounded-lg border border-brand-border bg-brand-surface px-4 py-3">
            <div>
              <dt className="text-xs font-medium text-brand-text-muted">Projects</dt>
              <dd className="mt-1 text-lg font-bold text-brand-text">{formatNumber(lgu.project_count)}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-brand-text-muted">Open reqs</dt>
              <dd className="mt-1 text-lg font-bold text-brand-text">{formatNumber(lgu.open_requirement_count)}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-brand-text-muted">Overdue</dt>
              <dd className={`mt-1 text-lg font-bold ${lgu.overdue_deadline_count > 0 ? 'text-red-600 dark:text-red-400' : 'text-brand-text'}`}>
                {formatNumber(lgu.overdue_deadline_count)}
              </dd>
            </div>
          </dl>
        </li>
      ))}
        </ul>
      )}
    </>
  )
}

function RecentComments({ comments }) {
  if (!comments.length) {
    return (
      <div className="border-t border-brand-border px-5 py-12 text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-blue-50 dark:bg-blue-950">
          <MessageSquarePlus className="h-8 w-8 text-blue-600 dark:text-blue-400" strokeWidth={2} />
        </div>
        <h3 className="text-base font-semibold text-brand-text">No field notes yet</h3>
        <p className="mt-2 text-sm text-brand-text-muted">Field notes will appear here once recorded.</p>
      </div>
    )
  }

  return (
    <ul className="divide-y divide-brand-border border-t border-brand-border">
      {comments.map((comment) => (
        <li key={comment.id} className="px-5 py-5 transition-colors hover:bg-brand-surface">
          <div className="flex items-start justify-between gap-3 mb-3">
            <span className="inline-flex items-center gap-2 rounded-md bg-brand-primary/10 px-3 py-1.5 text-xs font-semibold uppercase text-brand-primary">
              <MessageSquarePlus className="h-3.5 w-3.5" strokeWidth={2} />
              {formatStatus(comment.comment_type)}
            </span>
            <span className="text-xs font-medium text-brand-text-muted">{formatDate(comment.created_at)}</span>
          </div>
          <p className="mb-1 text-sm font-medium text-brand-text">{comment.requirement_name || 'Project field note'}</p>
          <p className="mb-2 text-xs text-brand-text-muted">
            {comment.project_name || 'Assigned project'}{comment.lgu_name ? ` / ${comment.lgu_name}` : ''}
          </p>
          <p className="text-sm leading-relaxed text-brand-text">{truncate(comment.body, 200)}</p>
          {comment.project_id && (
            <Link className="mt-2 inline-block text-sm text-brand-primary underline" to={`${ROUTES.projectDetail(comment.project_id)}?tab=requirements${comment.project_requirement_id ? `&req=${comment.project_requirement_id}` : ''}`}>
              Open related record
            </Link>
          )}
        </li>
      ))}
    </ul>
  )
}

export default function FieldOfficerDashboardPage() {
  const [summary, setSummary] = useState(null)
  const [actionItems, setActionItems] = useState([])
  const [lgus, setLgus] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [noteTarget, setNoteTarget] = useState(null)
  const [noteBody, setNoteBody] = useState('')
  const [noteType, setNoteType] = useState('field_follow_up')
  const [noteError, setNoteError] = useState('')
  const [submittingNote, setSubmittingNote] = useState(false)

  const loadFieldWorkspace = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [summaryRes, actionsRes, lgusRes] = await Promise.all([
        fieldApi.getFieldSummary(),
        fieldApi.listFieldActionItems({ limit: 75 }),
        fieldApi.listAssignedLgus(),
      ])
      setSummary(summaryRes.data || null)
      setActionItems(actionsRes.data || [])
      setLgus(lgusRes.data || [])
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to load the field officer workspace.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadFieldWorkspace()
  }, [loadFieldWorkspace])

  const assignedScopeLgus = summary?.scope?.lgus || []
  const counters = summary?.summary || {}
  const recentComments = summary?.recent_comments || []
  const overdueCount = Number(counters.overdue_deadlines || 0)
  const returnedCount = Number(counters.returned_requirements || 0)

  const groupedCounts = useMemo(() => {
    const counts = { critical: 0, high: 0, medium: 0, low: 0 }
    actionItems.forEach((item) => {
      counts[item.priority] = (counts[item.priority] || 0) + 1
    })
    return counts
  }, [actionItems])

  const openNoteModal = (item) => {
    setNoteTarget(item)
    setNoteBody('')
    setNoteType(item.type === 'deadline' ? 'field_follow_up' : 'submission_update')
    setNoteError('')
  }

  const closeNoteModal = () => {
    if (submittingNote) return
    setNoteTarget(null)
    setNoteBody('')
    setNoteError('')
  }

  const handleSubmitNote = async (event) => {
    event.preventDefault()
    if (!noteTarget?.project_requirement_id) return
    if (!noteBody.trim()) {
      setNoteError('Field note is required.')
      return
    }

    setSubmittingNote(true)
    setNoteError('')
    setMessage('')
    try {
      await fieldApi.createRequirementComment(noteTarget.project_requirement_id, {
        body: noteBody.trim(),
        comment_type: noteType,
        visibility: 'field_visible',
      })
      setMessage('Field note recorded.')
      setNoteTarget(null)
      setNoteBody('')
      setNoteError('')
      await loadFieldWorkspace()
    } catch (requestError) {
      setNoteError(requestError.response?.data?.message || 'Unable to record the field note.')
    } finally {
      setSubmittingNote(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="Field Officer Workspace"
        description="Monitor assigned LGUs, track documentary requirements, manage follow-ups, and record field observations."
        actions={(
          <Button variant="outline" size="sm" icon={RefreshCw} onClick={loadFieldWorkspace} disabled={loading}>
            Refresh workspace
          </Button>
        )}
      />

      {error && (
        <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>
          {error}
        </InlineAlert>
      )}
      <FeedbackToast type="success" message={message} onDismiss={() => setMessage('')} />

      <ErrorBoundary>
        <GlassPanel className="mb-6 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-text-muted">Current Assignment Scope</p>
            <h2 className="mt-2 text-lg font-bold leading-snug text-brand-text">
              {assignedScopeLgus.length ? assignedScopeLgus.map((lgu) => lgu.name).join(', ') : 'No active LGU assignment'}
            </h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {groupedCounts.critical > 0 && (
              <div className="inline-flex items-center gap-2 rounded-lg bg-red-50 px-4 py-2 dark:bg-red-950">
                <span className="text-2xl font-bold text-red-700 dark:text-red-300">{formatNumber(groupedCounts.critical)}</span>
                <span className="text-xs font-semibold uppercase text-red-600 dark:text-red-400">Critical</span>
              </div>
            )}
            {groupedCounts.high > 0 && (
              <div className="inline-flex items-center gap-2 rounded-lg bg-amber-50 px-4 py-2 dark:bg-amber-950">
                <span className="text-2xl font-bold text-amber-700 dark:text-amber-300">{formatNumber(groupedCounts.high)}</span>
                <span className="text-xs font-semibold uppercase text-amber-600 dark:text-amber-400">High</span>
              </div>
            )}
            <div className="inline-flex items-center gap-2 rounded-lg border-2 border-brand-border bg-brand-surface px-4 py-2">
              <span className="text-2xl font-bold text-brand-text">{formatNumber(actionItems.length)}</span>
              <span className="text-xs font-semibold uppercase text-brand-text-muted">Total</span>
            </div>
          </div>
        </div>
      </GlassPanel>

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <KpiCard
          title="Assigned LGUs"
          value={loading ? '...' : formatNumber(counters.assigned_lgus)}
          subtitle="in current scope"
          icon={Building2}
          color="blue"
        />
        <KpiCard
          title="Ongoing Projects"
          value={loading ? '...' : formatNumber(counters.ongoing_projects ?? counters.active_projects)}
          subtitle="assigned projects"
          icon={ClipboardList}
          color="cyan"
        />
        <KpiCard
          title="Returned"
          value={loading ? '...' : formatNumber(returnedCount)}
          subtitle="needs follow-up"
          icon={AlertTriangle}
          color="amber"
        />
        <KpiCard
          title="Overdue"
          value={loading ? '...' : formatNumber(overdueCount)}
          subtitle="deadline timers"
          icon={Clock}
          color={overdueCount > 0 ? 'red' : 'emerald'}
        />
        <KpiCard
          title="Monitoring"
          value={loading ? '...' : formatNumber(counters.monitoring_action_projects)}
          subtitle="action projects"
          icon={ShieldCheck}
          color="slate"
        />
      </div>

      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <GlassPanel noPadding className="shadow-sm">
          <div className="section-header">
            <div className="flex-1">
              <h2 className="section-title">Field Action Queue</h2>
              <p className="section-description">Priority follow-up work for requirements, deadlines, and monitoring records.</p>
            </div>
            {actionItems.length > 0 && (
              <span className="status-badge status-badge-warning text-sm">{actionItems.length} open items</span>
            )}
          </div>
          <ActionQueue items={actionItems} loading={loading} onComment={openNoteModal} />
        </GlassPanel>

        <div className="grid gap-4">
          <GlassPanel noPadding className="shadow-sm">
            <div className="section-header">
              <div>
                <h2 className="section-title">Assigned LGUs</h2>
                <p className="section-description">Local government units under your field responsibility.</p>
              </div>
              {lgus.length > 0 && (
                <span className="status-badge status-badge-info text-sm">{lgus.length} assigned</span>
              )}
            </div>
            <AssignedLguList lgus={lgus} />
          </GlassPanel>

          <GlassPanel noPadding className="shadow-sm">
            <div className="section-header">
              <div>
                <h2 className="section-title">Recent Field Notes</h2>
                <p className="section-description">Latest documented field observations and follow-ups.</p>
              </div>
            </div>
            <RecentComments comments={recentComments} />
          </GlassPanel>
        </div>
      </div>

      <Modal
        open={Boolean(noteTarget)}
        title="Record Field Note"
        description={(
          <div className="mt-2 space-y-1">
            <p className="text-sm font-medium text-brand-text">{noteTarget?.payload?.requirement_name || noteTarget?.title}</p>
            {noteTarget?.payload?.project_name && (
              <p className="text-xs text-brand-text-muted">
                Project: {noteTarget.payload.project_name}
                {noteTarget.payload?.lgu_name && ` • LGU: ${noteTarget.payload.lgu_name}`}
              </p>
            )}
          </div>
        )}
        onClose={closeNoteModal}
        footer={
          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={closeNoteModal} disabled={submittingNote}>
              Cancel
            </Button>
            <Button type="submit" form="field-note-form" loading={submittingNote}>
              <MessageSquarePlus className="h-4 w-4" />
              Save field note
            </Button>
          </div>
        }
      >
        <form id="field-note-form" className="space-y-5" onSubmit={handleSubmitNote}>
          {noteError && (noteError.toLowerCase().includes('paused') || noteError.toLowerCase().includes('inactive')) && (
            <ProgramPausedBanner role="field_officer" message={noteError} className="w-full" />
          )}
          <FormField id="field-note-type" label="Note Type">
            <select
              id="field-note-type"
              className="input-field"
              value={noteType}
              onChange={(event) => setNoteType(event.target.value)}
            >
              {COMMENT_TYPES.map((type) => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
            <p className="mt-2 text-xs text-brand-text-muted">
              Select the category that best describes this field note.
            </p>
          </FormField>
          <FormField id="field-note-body" label="Field Note Details" required error={noteError && !(noteError.toLowerCase().includes('paused') || noteError.toLowerCase().includes('inactive')) ? noteError : undefined}>
            <textarea
              id="field-note-body"
              className="input-field min-h-40"
              value={noteBody}
              onChange={(event) => setNoteBody(event.target.value)}
              placeholder="Describe the LGU follow-up, submitted correction, clarification needed, or other field observations..."
            />
            <p className="mt-2 text-xs text-brand-text-muted">
              {noteBody.trim().length} characters • Be specific and detailed for better tracking.
            </p>
          </FormField>
        </form>
      </Modal>
      </ErrorBoundary>
    </div>
  )
}
