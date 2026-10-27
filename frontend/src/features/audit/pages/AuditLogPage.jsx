import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Activity,
  Download,
  Eye,
  Filter,
  Link2,
  RefreshCw,
  ScrollText,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
  Users,
  X,
} from 'lucide-react'
import {
  Button,
  DataTable,
  FormField,
  GlassPanel,
  InlineAlert,
  KpiCard,
  Modal,
  PageHeader,
} from '../../../components'
import {
  formatMachineLabel,
  formatRelativeTime as formatRelative,
  formatStatus,
  formatTimestamp,
} from '../../../lib/formatters'
import { isSystemAdmin } from '../../../lib/auth'
import * as auditApi from '../api/auditApi'

const ACTION_TONE = {
  create: 'status-badge-success',
  created: 'status-badge-success',
  approve: 'status-badge-success',
  approved: 'status-badge-success',
  restore: 'status-badge-success',
  login: 'status-badge-info',
  logout: 'status-badge-neutral',
  view: 'status-badge-neutral',
  read: 'status-badge-neutral',
  update: 'status-badge-info',
  updated: 'status-badge-info',
  edit: 'status-badge-info',
  status_change: 'status-badge-info',
  handoff: 'status-badge-handoff',
  handed_off: 'status-badge-handoff',
  archive: 'status-badge-neutral',
  archived: 'status-badge-neutral',
  delete: 'status-badge-danger',
  deleted: 'status-badge-danger',
  reject: 'status-badge-danger',
  rejected: 'status-badge-danger',
  return: 'status-badge-danger',
  returned: 'status-badge-danger',
  escalate: 'status-badge-warning',
  escalated: 'status-badge-warning',
  flag: 'status-badge-warning',
}

const QUICK_ACTIONS = ['create', 'update', 'delete', 'login', 'escalate', 'handoff']
const QUICK_ENTITIES = ['project', 'user', 'lgu', 'document', 'notice', 'handoff']

const EMPTY_FILTERS = { search: '', entity_type: '', action: '', start_date: '', end_date: '', user_id: '' }

function ActionBadge({ action }) {
  const key = (action || '').toLowerCase()
  const tone = ACTION_TONE[key] || 'status-badge-neutral'
  return <span className={`status-badge ${tone}`}>{formatMachineLabel(action)}</span>
}

function getInitials(value) {
  if (!value) return 'SY'
  const parts = String(value).trim().split(/[\s.@]+/).filter(Boolean)
  return (parts.slice(0, 2).map((p) => p[0]?.toUpperCase()).join('') || 'SY').slice(0, 2)
}

function formatNumber(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n.toLocaleString('en-PH') : '0'
}

function shortHash(value) {
  if (!value) return '—'
  return `${String(value).slice(0, 12)}…`
}

function getBrokenAtId(brokenAt) {
  if (!brokenAt) return null
  if (typeof brokenAt === 'number' || typeof brokenAt === 'string') return brokenAt
  return brokenAt.broken_at_id ?? null
}

function getIntegrityIssueType(brokenAt) {
  if (!brokenAt || typeof brokenAt !== 'object') return ''
  if ('expected_hash' in brokenAt || 'actual_hash' in brokenAt) return 'Record hash mismatch'
  if ('expected_previous_hash' in brokenAt || 'actual_previous_hash' in brokenAt) return 'Previous hash link mismatch'
  return 'Integrity mismatch'
}

function getIntegrityIssueSummary(brokenAt) {
  const id = getBrokenAtId(brokenAt)
  if (!id) return 'Chain verification failed. Investigate before any further writes.'
  const issueType = getIntegrityIssueType(brokenAt)
  return `${issueType || 'Chain verification failed'} at entry #${id}. Investigate before any further writes.`
}

function buildBars(counts, limit = 10) {
  const entries = Object.entries(counts || {})
    .map(([key, value]) => ({ key, value: Number(value) || 0 }))
    .filter((e) => e.value > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, limit)
  if (!entries.length) return []
  const max = Math.max(...entries.map((e) => e.value))
  return entries.map((e) => ({ ...e, ratio: e.value / max }))
}

function exportCsv(rows) {
  const headers = ['Timestamp', 'Actor', 'Email', 'Action', 'Entity', 'Entity ID', 'IP Address', 'Record Hash']
  const escape = (v) => {
    const s = v === null || v === undefined ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [headers.join(',')]
  rows.forEach((r) => {
    lines.push([
      r.created_at,
      r.user_name || 'System',
      r.user_email || '',
      r.action,
      r.entity_type,
      r.entity_id,
      r.ip_address || '',
      r.record_hash || '',
    ].map(escape).join(','))
  })
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `audit-log-${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export default function AuditLogPage() {
  const [searchParams] = useSearchParams()
  const initialFilters = {
    search: searchParams.get('search') || '',
    entity_type: searchParams.get('entity_type') || '',
    action: searchParams.get('action') || '',
    start_date: searchParams.get('start_date') || '',
    end_date: searchParams.get('end_date') || '',
    user_id: searchParams.get('user_id') || '',
  }
  const [logs, setLogs] = useState([])
  const [stats, setStats] = useState(null)
  const [chain, setChain] = useState(null)
  const [compromisedEntry, setCompromisedEntry] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [filters, setFilters] = useState(initialFilters)
  const [draft, setDraft] = useState(initialFilters)
  const [selected, setSelected] = useState(null)
  const [incidentAction, setIncidentAction] = useState(null)
  const [incidentNotes, setIncidentNotes] = useState('')
  const [incidentConfirmPassword, setIncidentConfirmPassword] = useState('')
  const [incidentError, setIncidentError] = useState('')
  const [incidentLoading, setIncidentLoading] = useState(false)
  const canManageIntegrity = isSystemAdmin()

  const loadAudit = useCallback(async () => {
    if (logs.length) setRefreshing(true)
    else setLoading(true)
    setError('')
    try {
      const params = { per_page: 50 }
      Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v })

      const [statsRes, chainRes, logsRes] = await Promise.all([
        auditApi.getAuditStats(),
        auditApi.verifyAuditChain(),
        auditApi.listAuditLogs(params),
      ])
      const chainData = chainRes.data || null
      const nextLogs = logsRes.data || []
      const brokenAtId = getBrokenAtId(chainData?.broken_at)
      const visibleBrokenRow = brokenAtId
        ? nextLogs.find((row) => String(row.id) === String(brokenAtId))
        : null
      let pinnedBrokenRow = visibleBrokenRow || null
      if (brokenAtId && !visibleBrokenRow) {
        try {
          const brokenRes = await auditApi.getAuditLog(brokenAtId)
          pinnedBrokenRow = brokenRes.data || null
        } catch {
          pinnedBrokenRow = null
        }
      }
      setStats(statsRes.data || null)
      setChain(chainData)
      setCompromisedEntry(pinnedBrokenRow)
      setLogs(nextLogs)
    } catch (err) {
      setError(err?.response?.data?.message || 'Unable to load audit log entries.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters])

  useEffect(() => {
    loadAudit()
  }, [loadAudit])

  useEffect(() => {
    const nextFilters = {
      search: searchParams.get('search') || '',
      entity_type: searchParams.get('entity_type') || '',
      action: searchParams.get('action') || '',
      start_date: searchParams.get('start_date') || '',
      end_date: searchParams.get('end_date') || '',
      user_id: searchParams.get('user_id') || '',
    }
    setFilters(nextFilters)
    setDraft(nextFilters)
  }, [searchParams])

  const applyFilters = () => setFilters(draft)
  const clearFilters = () => { setDraft(EMPTY_FILTERS); setFilters(EMPTY_FILTERS) }
  const setQuickAction = (action) => {
    const next = { ...draft, action: draft.action === action ? '' : action }
    setDraft(next)
    setFilters(next)
  }
  const setQuickEntity = (entity) => {
    const next = { ...draft, entity_type: draft.entity_type === entity ? '' : entity }
    setDraft(next)
    setFilters(next)
  }

  const openIncidentDialog = (action) => {
    if (!canManageIntegrity) return
    setIncidentAction(action)
    setIncidentNotes('')
    setIncidentConfirmPassword('')
    setIncidentError('')
  }

  const closeIncidentDialog = () => {
    if (incidentLoading) return
    setIncidentAction(null)
    setIncidentNotes('')
    setIncidentConfirmPassword('')
    setIncidentError('')
  }

  const submitIncidentAction = async () => {
    setIncidentError('')
    const notes = incidentNotes.trim()
    if (incidentAction === 'rebaseline' && !notes) {
      setIncidentError('Rebaseline notes are required so future admins know why the checkpoint was accepted.')
      return
    }
    setIncidentLoading(true)
    try {
      const payload = { notes }
      if (incidentConfirmPassword.trim()) {
        payload.confirm_password = incidentConfirmPassword.trim()
      }
      if (incidentAction === 'open') {
        await auditApi.openIntegrityIncident(payload)
      } else if (incidentAction === 'rebaseline') {
        const incidentId = chain?.active_incident?.id
        if (!incidentId) throw new Error('No open integrity incident is available to rebaseline.')
        await auditApi.rebaselineIntegrityIncident(incidentId, payload)
      }
      closeIncidentDialog()
      await loadAudit()
    } catch (err) {
      setIncidentError(err?.response?.data?.message || err?.message || 'Unable to update the integrity incident.')
    } finally {
      setIncidentLoading(false)
    }
  }

  const hasActiveFilters = useMemo(
    () => Object.values(filters).some((v) => Boolean(v)),
    [filters],
  )

  const isValid = Boolean(chain?.is_valid)
  const brokenAtId = getBrokenAtId(chain?.broken_at)
  const displayedLogs = useMemo(() => {
    if (!brokenAtId) return logs
    const markRow = (row, pinned = false) => (
      String(row.id) === String(brokenAtId)
        ? { ...row, __integrityIssue: true, __integrityPinned: pinned }
        : row
    )
    const hasBrokenRow = logs.some((row) => String(row.id) === String(brokenAtId))
    if (hasBrokenRow) return logs.map((row) => markRow(row))
    if (compromisedEntry) return [markRow(compromisedEntry, true), ...logs]
    return logs
  }, [brokenAtId, compromisedEntry, logs])
  const totalEntries = Number(stats?.total || 0)
  const recent24 = Number(stats?.recent_count_24h || 0)
  const uniqueUsers = Number(stats?.unique_users || 0)
  const flaggedEvents = useMemo(() => {
    const a = stats?.action_counts || {}
    return Number(a.escalate || 0) + Number(a.escalation || 0) + Number(a.flag || 0)
  }, [stats])

  const actionBars = useMemo(() => buildBars(stats?.action_counts), [stats])
  const entityBars = useMemo(() => buildBars(stats?.entity_counts), [stats])

  const columns = [
    {
      key: 'integrity',
      label: 'Integrity',
      render: (row) => (
        row.__integrityIssue ? (
          <span className="status-badge status-badge-warning">
            <ShieldAlert className="h-3 w-3" strokeWidth={2} />
            {row.__integrityPinned ? 'Pinned issue' : 'Issue'}
          </span>
        ) : (
          <span className="text-xs text-brand-text-muted">—</span>
        )
      ),
    },
    {
      key: 'created_at',
      label: 'When',
      render: (row) => (
        <div>
          <div className="text-sm font-medium text-brand-text">{formatTimestamp(row.created_at)}</div>
          <div className="text-xs text-brand-text-muted">{formatRelative(row.created_at)}</div>
        </div>
      ),
    },
    {
      key: 'user_name',
      label: 'Actor',
      render: (row) => {
        const name = row.user_name || row.user_email || 'System'
        const isSystem = !row.user_id
        return (
          <div className="flex items-center gap-2.5">
            <span
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                isSystem
                  ? 'bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-200'
                  : 'bg-blue-50 text-blue-700 dark:bg-blue-300/15 dark:text-blue-200'
              }`}
              aria-hidden="true"
            >
              {getInitials(name)}
            </span>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-brand-text">{name}</div>
              {row.user_email && row.user_name && (
                <div className="truncate text-xs text-brand-text-muted">{row.user_email}</div>
              )}
            </div>
          </div>
        )
      },
    },
    { key: 'action', label: 'Action', render: (row) => <ActionBadge action={row.action} /> },
    {
      key: 'entity_type',
      label: 'Entity',
      render: (row) => (
        <div>
          <div className="text-sm font-medium text-brand-text">{formatMachineLabel(row.entity_type)}</div>
          <div className="text-xs text-brand-text-muted">ID #{row.entity_id}</div>
        </div>
      ),
    },
    {
      key: 'ip_address',
      label: 'IP',
      render: (row) => (
        <span className="font-mono text-xs text-brand-text-muted">{row.ip_address || '—'}</span>
      ),
    },
    {
      key: 'actions',
      label: '',
      render: (row) => (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setSelected(row) }}
          className="inline-flex items-center gap-1 rounded-md border border-brand-border bg-brand-surface-solid px-2 py-1 text-xs font-medium text-brand-text-muted transition-colors hover:bg-brand-surface hover:text-brand-text"
          aria-label={`View audit entry ${row.id}`}
        >
          <Eye className="h-3.5 w-3.5" strokeWidth={1.8} />
          Details
        </button>
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        title="Audit Log"
        description="Tamper-evident history of status changes, user access, documentary review, notices, and handoff activity."
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              icon={Download}
              onClick={() => exportCsv(displayedLogs)}
              disabled={!displayedLogs.length}
            >
              Export CSV
            </Button>
            <Button
              variant="outline"
              size="sm"
              icon={RefreshCw}
              onClick={loadAudit}
              loading={refreshing}
            >
              Refresh
            </Button>
          </>
        }
      />

      {error && (
        <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>
          {error}
        </InlineAlert>
      )}

      {!isValid && brokenAtId && compromisedEntry && (
        <InlineAlert type="warning" className="mb-4">
          Audit entry #{brokenAtId} is the first compromised row. It is pinned in the table below
          {logs.some((row) => String(row.id) === String(brokenAtId)) ? '' : ' because it is outside the latest page of audit records'}.
        </InlineAlert>
      )}

      {/* Chain integrity strip */}
      <IntegrityStrip
        chain={chain}
        isValid={isValid}
        latestEntry={logs[0]}
        canManageIntegrity={canManageIntegrity}
        onOpenIncident={() => openIncidentDialog('open')}
        onRebaseline={() => openIncidentDialog('rebaseline')}
      />


      {/* KPIs */}
      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <KpiCard title="Total Entries" value={formatNumber(totalEntries)} subtitle="logged events" icon={ScrollText} color="blue" />
        <KpiCard title="Last 24 hours" value={formatNumber(recent24)} subtitle="recent activity" icon={Activity} color="cyan" />
        <KpiCard title="Unique Actors" value={formatNumber(uniqueUsers)} subtitle="distinct users" icon={Users} color="emerald" />
        <KpiCard
          title="Flagged Events"
          value={formatNumber(flaggedEvents)}
          subtitle="escalations & flags"
          icon={flaggedEvents > 0 ? ShieldAlert : ShieldCheck}
          color={flaggedEvents > 0 ? 'amber' : 'slate'}
        />
      </div>

      {/* Activity mix (compact, tabbed) */}
      <ActivityMixPanel
        actionBars={actionBars}
        entityBars={entityBars}
        isLoading={loading}
        activeAction={filters.action}
        activeEntity={filters.entity_type}
        onSelectAction={setQuickAction}
        onSelectEntity={setQuickEntity}
      />

      {/* Filter bar */}
      <div className="filter-bar mb-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-brand-text-muted">
            <Filter className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden="true" />
            Quick filters
          </span>
          {QUICK_ACTIONS.map((a) => (
            <button
              key={a}
              type="button"
              onClick={() => setQuickAction(a)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                filters.action === a
                  ? 'border-brand-primary bg-brand-primary/10 text-brand-primary dark:bg-brand-primary/20'
                  : 'border-brand-border bg-brand-surface-solid text-brand-text-muted hover:bg-brand-surface hover:text-brand-text'
              }`}
            >
              {formatStatus(a)}
            </button>
          ))}
          {hasActiveFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-brand-text-muted hover:text-brand-text"
            >
              <X className="h-3.5 w-3.5" /> Clear all
            </button>
          )}
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_1fr_auto] lg:items-end">
          <FormField id="audit-search" label="Search">
            <input
              id="audit-search"
              className="input-field"
              placeholder="Action, actor, or entity"
              value={draft.search}
              onChange={(e) => setDraft({ ...draft, search: e.target.value })}
              onKeyDown={(e) => { if (e.key === 'Enter') applyFilters() }}
            />
          </FormField>
          <FormField id="audit-entity" label="Entity">
            <select
              id="audit-entity"
              className="input-field"
              value={draft.entity_type}
              onChange={(e) => setDraft({ ...draft, entity_type: e.target.value })}
            >
              <option value="">All entities</option>
              {QUICK_ENTITIES.map((e) => (
                <option key={e} value={e}>{formatMachineLabel(e)}</option>
              ))}
            </select>
          </FormField>
          <FormField id="audit-action" label="Action">
            <input
              id="audit-action"
              className="input-field"
              placeholder="e.g. update"
              value={draft.action}
              onChange={(e) => setDraft({ ...draft, action: e.target.value })}
              onKeyDown={(e) => { if (e.key === 'Enter') applyFilters() }}
            />
          </FormField>
          <FormField id="audit-start" label="From">
            <input
              id="audit-start"
              type="date"
              className="input-field"
              value={draft.start_date}
              onChange={(e) => setDraft({ ...draft, start_date: e.target.value })}
            />
          </FormField>
          <FormField id="audit-end" label="To">
            <input
              id="audit-end"
              type="date"
              className="input-field"
              value={draft.end_date}
              onChange={(e) => setDraft({ ...draft, end_date: e.target.value })}
            />
          </FormField>
          <Button onClick={applyFilters} loading={refreshing}>Apply</Button>
        </div>
      </div>

      {hasActiveFilters && (
        <p className="mb-3 text-xs text-brand-text-muted">
          Showing <span className="font-semibold text-brand-text">{formatNumber(displayedLogs.length)}</span> matching entries.
        </p>
      )}

      <DataTable
        columns={columns}
        data={displayedLogs}
        keyField="id"
        isLoading={loading}
        emptyMessage={hasActiveFilters ? 'No audit entries match these filters.' : 'No audit entries recorded yet.'}
        caption="Audit log entries"
        onRowClick={(row) => setSelected(row)}
        getRowClassName={(row) => (
          row.__integrityIssue
            ? 'bg-amber-50/80 outline outline-1 outline-amber-300 dark:bg-amber-300/10 dark:outline-amber-300/30'
            : ''
        )}
      />

      <AuditDetailModal entry={selected} chain={chain} onClose={() => setSelected(null)} />
      <IntegrityIncidentModal
        action={incidentAction}
        chain={chain}
        notes={incidentNotes}
        confirmPassword={incidentConfirmPassword}
        error={incidentError}
        loading={incidentLoading}
        onChangeNotes={setIncidentNotes}
        onChangeConfirmPassword={setIncidentConfirmPassword}
        onClose={closeIncidentDialog}
        onSubmit={submitIncidentAction}
      />
    </div>
  )
}

function IntegrityStrip({ chain, isValid, latestEntry, canManageIntegrity, onOpenIncident, onRebaseline }) {
  const totalEntries = Number(chain?.total_entries || 0)
  const brokenAt = chain?.broken_at
  const brokenAtId = getBrokenAtId(brokenAt)
  const issueType = getIntegrityIssueType(brokenAt)
  const activeIncident = chain?.active_incident
  const latestCheckpoint = chain?.latest_checkpoint
  const postCheckpoint = chain?.post_checkpoint
  const accent = isValid
    ? {
        ring: 'ring-emerald-200 dark:ring-emerald-400/30',
        gradient: 'from-emerald-50 via-white to-white dark:from-emerald-400/10 dark:via-brand-surface dark:to-brand-surface',
        chip: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-300/15 dark:text-emerald-100',
        dot: 'bg-emerald-500 dark:bg-emerald-300',
        title: 'text-emerald-900 dark:text-emerald-100',
        icon: 'text-emerald-700 dark:text-emerald-300',
      }
    : {
        ring: 'ring-amber-200 dark:ring-amber-400/30',
        gradient: 'from-amber-50 via-white to-white dark:from-amber-300/10 dark:via-brand-surface dark:to-brand-surface',
        chip: 'bg-amber-100 text-amber-900 dark:bg-amber-300/15 dark:text-amber-100',
        dot: 'bg-amber-500 dark:bg-amber-300',
        title: 'text-amber-900 dark:text-amber-100',
        icon: 'text-amber-700 dark:text-amber-300',
      }

  return (
    <div
      className={`relative mb-6 overflow-hidden rounded-lg border border-brand-border bg-gradient-to-r ${accent.gradient} shadow-sm ring-1 ${accent.ring}`}
      role="status"
    >
      <div className="pointer-events-none absolute inset-y-0 right-0 hidden w-1/3 opacity-40 sm:block" aria-hidden="true">
        <ChainPattern color={isValid ? 'emerald' : 'amber'} />
      </div>
      <div className="relative flex flex-col gap-4 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className={`relative flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${accent.chip}`}>
            {isValid ? <ShieldCheck className="h-5 w-5" strokeWidth={1.8} /> : <ShieldAlert className="h-5 w-5" strokeWidth={1.8} />}
            <span className={`absolute -bottom-0.5 -right-0.5 inline-flex h-3 w-3 items-center justify-center rounded-full ring-2 ring-white dark:ring-brand-surface ${accent.dot}`}>
              <span className={`h-1.5 w-1.5 animate-ping rounded-full ${accent.dot} opacity-70`} />
            </span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <p className={`text-sm font-semibold ${accent.title}`}>
                {isValid ? 'Hash chain verified' : 'Chain integrity issue'}
              </p>
              <span className={`status-badge ${isValid ? 'status-badge-success' : 'status-badge-warning'}`}>
                <Link2 className="h-3 w-3" strokeWidth={2} />
                SHA-256
              </span>
            </div>
            <p className="text-xs text-brand-text-muted">
              {isValid
                ? 'Every entry is cryptographically linked to the previous one.'
                : getIntegrityIssueSummary(brokenAt)}
            </p>
            {!isValid && brokenAt && typeof brokenAt === 'object' && (
              <p className="mt-1 text-[11px] text-brand-text-muted">
                {issueType || 'Mismatch'}{brokenAtId ? ` · entry #${brokenAtId}` : ''}
                {'expected_hash' in brokenAt && ` · expected ${shortHash(brokenAt.expected_hash)}`}
                {'actual_hash' in brokenAt && ` · stored ${shortHash(brokenAt.actual_hash)}`}
                {'expected_previous_hash' in brokenAt && ` · expected previous ${shortHash(brokenAt.expected_previous_hash)}`}
                {'actual_previous_hash' in brokenAt && ` · stored previous ${shortHash(brokenAt.actual_previous_hash)}`}
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-col items-stretch gap-3 sm:items-end">
          <dl className="grid grid-cols-3 gap-4 sm:gap-6 sm:text-right">
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">Verified</dt>
              <dd className="mt-0.5 font-display text-lg font-semibold leading-none text-brand-text">{formatNumber(totalEntries)}</dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">Latest</dt>
              <dd className={`mt-0.5 text-sm font-semibold leading-tight ${accent.title}`}>
                {latestEntry ? formatRelative(latestEntry.created_at) : '—'}
              </dd>
            </div>
            <div>
              <dt className="text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">Status</dt>
              <dd className={`mt-0.5 inline-flex items-center gap-1 text-sm font-semibold ${accent.title}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${accent.dot}`} aria-hidden="true" />
                {isValid ? 'Healthy' : activeIncident ? 'Incident open' : latestCheckpoint ? 'Rebaselined' : 'Action needed'}
              </dd>
            </div>
          </dl>

          {!isValid && (
            <div className="flex flex-col gap-2 sm:items-end">
              {canManageIntegrity ? (
                activeIncident ? (
                  <>
                    <p className="text-xs text-brand-text-muted">
                      Incident #{activeIncident.id} opened {formatRelative(activeIncident.opened_at)}.
                    </p>
                    <Button size="sm" variant="warning" onClick={onRebaseline}>
                      Rebaseline checkpoint
                    </Button>
                  </>
                ) : latestCheckpoint ? (
                  <p className="max-w-sm text-right text-xs text-brand-text-muted">
                    Checkpoint #{latestCheckpoint.id} at entry #{latestCheckpoint.checkpoint_audit_log_id}.
                    Future chain {postCheckpoint?.is_valid ? 'is valid' : 'needs review'} from that point.
                  </p>
                ) : (
                  <Button size="sm" variant="warning" onClick={onOpenIncident}>
                    Open integrity incident
                  </Button>
                )
              ) : (
                <p className="max-w-sm text-right text-xs text-brand-text-muted">
                  Integrity incident management is restricted to System Administrators.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ChainPattern({ color }) {
  const stroke = color === 'emerald' ? '#10b981' : '#f59e0b'
  return (
    <svg viewBox="0 0 320 80" className="h-full w-full" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <pattern id={`chain-${color}`} x="0" y="0" width="44" height="40" patternUnits="userSpaceOnUse">
          <circle cx="14" cy="20" r="9" fill="none" stroke={stroke} strokeWidth="1.4" opacity="0.45" />
          <circle cx="34" cy="20" r="9" fill="none" stroke={stroke} strokeWidth="1.4" opacity="0.45" />
        </pattern>
      </defs>
      <rect width="320" height="80" fill={`url(#chain-${color})`} />
    </svg>
  )
}

function ActivityMixPanel({
  actionBars,
  entityBars,
  isLoading,
  activeAction,
  activeEntity,
  onSelectAction,
  onSelectEntity,
}) {
  const [tab, setTab] = useState('action')
  const isActionTab = tab === 'action'
  const bars = (isActionTab ? actionBars : entityBars).slice(0, 6)
  const activeKey = isActionTab ? activeAction : activeEntity
  const onSelect = isActionTab ? onSelectAction : onSelectEntity
  const total = bars.reduce((sum, b) => sum + b.value, 0)

  return (
    <GlassPanel noPadding className="mb-6">
      <div className="flex items-center justify-between gap-3 border-b border-brand-border px-5 py-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-brand-text-muted" strokeWidth={1.8} aria-hidden="true" />
          <h2 className="text-sm font-semibold text-brand-text">Activity mix</h2>
          <span className="text-xs text-brand-text-muted">— click a bar to filter</span>
        </div>
        <div role="tablist" className="inline-flex rounded-md border border-brand-border bg-brand-surface p-0.5 text-xs">
          {[
            { id: 'action', label: 'By action' },
            { id: 'entity', label: 'By entity' },
          ].map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={`rounded px-3 py-1 font-medium transition-colors ${
                tab === t.id
                  ? 'bg-brand-surface-solid text-brand-text shadow-sm'
                  : 'text-brand-text-muted hover:text-brand-text'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <div className="px-5 py-3">
        {isLoading ? (
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-7 animate-pulse rounded bg-brand-surface" />
            ))}
          </div>
        ) : bars.length === 0 ? (
          <p className="py-3 text-center text-sm text-brand-text-muted">No activity recorded yet.</p>
        ) : (
          <ul className="grid grid-cols-1 gap-x-5 gap-y-1 sm:grid-cols-2">
            {bars.map((bar) => {
              const isActive = activeKey === bar.key
              const widthPct = Math.max(6, Math.round(bar.ratio * 100))
              const sharePct = total > 0 ? Math.round((bar.value / total) * 100) : 0
              return (
                <li key={bar.key}>
                  <button
                    type="button"
                    onClick={() => onSelect?.(bar.key)}
                    className={`group block w-full rounded-md px-2 py-1.5 text-left transition-colors ${
                      isActive ? 'bg-brand-primary/5 ring-1 ring-brand-primary/30' : 'hover:bg-brand-surface'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className={`truncate text-xs font-medium ${isActive ? 'text-brand-primary' : 'text-brand-text'}`}>
                        {formatStatus(bar.key)}
                      </span>
                      <span className="shrink-0 text-[11px] tabular-nums text-brand-text-muted">
                        {formatNumber(bar.value)} <span className="opacity-70">· {sharePct}%</span>
                      </span>
                    </div>
                    <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-brand-surface">
                      <div
                        className={`h-full rounded-full transition-all ${
                          isActive ? 'bg-brand-primary' : 'bg-blue-400 dark:bg-blue-300/70 group-hover:bg-blue-500'
                        }`}
                        style={{ width: `${widthPct}%` }}
                      />
                    </div>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </GlassPanel>
  )
}

function AuditDetailModal({ entry, chain, onClose }) {
  if (!entry) return null
  const brokenAt = chain?.broken_at
  const brokenAtId = getBrokenAtId(brokenAt)
  const isBrokenEntry = String(brokenAtId || '') === String(entry.id)
  const issueType = getIntegrityIssueType(brokenAt)
  const renderJson = (value) => {
    if (value === null || value === undefined) return <p className="text-sm italic text-brand-text-muted">No data</p>
    return (
      <pre className="max-h-64 overflow-auto rounded-md border border-brand-border bg-brand-surface p-3 text-xs leading-relaxed text-brand-text">
        {JSON.stringify(value, null, 2)}
      </pre>
    )
  }
  return (
    <Modal
      open
      title={`Audit entry #${entry.id}`}
      description={`${formatMachineLabel(entry.action)} on ${formatMachineLabel(entry.entity_type)} #${entry.entity_id}`}
      size="xl"
      onClose={onClose}
      footer={
        <div className="flex justify-end">
          <Button variant="outline" onClick={onClose}>Close</Button>
        </div>
      }
    >
      <div className="space-y-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <DetailField label="Timestamp" value={formatTimestamp(entry.created_at)} hint={formatRelative(entry.created_at)} />
          <DetailField
            label="Actor"
            value={entry.user_name || entry.user_email || 'System'}
            hint={entry.user_email && entry.user_name ? entry.user_email : entry.user_id ? `User #${entry.user_id}` : 'No authenticated user'}
          />
          <DetailField label="Action" value={<ActionBadge action={entry.action} />} />
          <DetailField label="Entity" value={`${formatMachineLabel(entry.entity_type)} #${entry.entity_id}`} />
          <DetailField label="IP Address" value={entry.ip_address || '—'} mono />
          <DetailField label="User Agent" value={entry.user_agent || '—'} small />
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div>
            <p className="label-text">Old value</p>
            {renderJson(entry.old_value)}
          </div>
          <div>
            <p className="label-text">New value</p>
            {renderJson(entry.new_value)}
          </div>
        </div>

        <div className="rounded-lg border border-brand-border bg-brand-surface px-4 py-3">
          <div className="mb-2 flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-700 dark:text-emerald-300" strokeWidth={1.8} />
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-text-muted">Hash chain</span>
          </div>
          <dl className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-[8rem_1fr]">
            <dt className="font-semibold text-brand-text-muted">Record hash</dt>
            <dd className="break-all font-mono text-brand-text">{entry.record_hash || '—'}</dd>
            <dt className="font-semibold text-brand-text-muted">Previous hash</dt>
            <dd className="break-all font-mono text-brand-text">{entry.previous_hash || '—'}</dd>
          </dl>
        </div>

        {isBrokenEntry && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm dark:border-amber-300/30 dark:bg-amber-300/10">
            <div className="mb-2 flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-amber-700 dark:text-amber-300" strokeWidth={1.8} />
              <span className="text-xs font-semibold uppercase tracking-wider text-amber-900 dark:text-amber-100">
                Integrity issue on this entry
              </span>
            </div>
            <p className="text-xs text-brand-text-muted">
              {issueType || 'This entry is the first point where verification fails.'}
              {' '}Direct database edits can prove the row changed, but cannot recover the overwritten original field value without a backup or external anchor.
            </p>
            {brokenAt && typeof brokenAt === 'object' && (
              <dl className="mt-3 grid grid-cols-1 gap-2 text-xs sm:grid-cols-[10rem_1fr]">
                {'expected_hash' in brokenAt && (
                  <>
                    <dt className="font-semibold text-brand-text-muted">Expected hash</dt>
                    <dd className="break-all font-mono text-brand-text">{brokenAt.expected_hash}</dd>
                  </>
                )}
                {'actual_hash' in brokenAt && (
                  <>
                    <dt className="font-semibold text-brand-text-muted">Stored hash</dt>
                    <dd className="break-all font-mono text-brand-text">{brokenAt.actual_hash}</dd>
                  </>
                )}
                {'expected_previous_hash' in brokenAt && (
                  <>
                    <dt className="font-semibold text-brand-text-muted">Expected previous</dt>
                    <dd className="break-all font-mono text-brand-text">{brokenAt.expected_previous_hash}</dd>
                  </>
                )}
                {'actual_previous_hash' in brokenAt && (
                  <>
                    <dt className="font-semibold text-brand-text-muted">Stored previous</dt>
                    <dd className="break-all font-mono text-brand-text">{brokenAt.actual_previous_hash}</dd>
                  </>
                )}
              </dl>
            )}
          </div>
        )}
      </div>
    </Modal>
  )
}

function IntegrityIncidentModal({
  action,
  chain,
  notes,
  confirmPassword = '',
  error,
  loading,
  onChangeNotes,
  onChangeConfirmPassword,
  onClose,
  onSubmit,
}) {
  if (!action) return null
  const isRebaseline = action === 'rebaseline'
  const activeIncident = chain?.active_incident
  const brokenAt = chain?.broken_at
  const brokenAtId = getBrokenAtId(brokenAt)
  const issueType = getIntegrityIssueType(brokenAt)

  return (
    <Modal
      open
      title={isRebaseline ? 'Rebaseline audit chain' : 'Open integrity incident'}
      description={
        isRebaseline
          ? `Incident #${activeIncident?.id || '—'} will keep the old break visible and checkpoint future writes.`
          : `${issueType || 'Integrity mismatch'}${brokenAtId ? ` at audit entry #${brokenAtId}` : ''}.`
      }
      size="lg"
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button variant={isRebaseline ? 'warning' : 'primary'} onClick={onSubmit} loading={loading}>
            {isRebaseline ? 'Create checkpoint' : 'Open incident'}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {error && <InlineAlert type="error">{error}</InlineAlert>}

        <div className="rounded-lg border border-brand-border bg-brand-surface px-4 py-3">
          <dl className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-[9rem_1fr]">
            <dt className="font-semibold text-brand-text-muted">Broken entry</dt>
            <dd className="font-mono text-brand-text">{brokenAtId ? `#${brokenAtId}` : '—'}</dd>
            <dt className="font-semibold text-brand-text-muted">Mismatch</dt>
            <dd className="text-brand-text">{issueType || 'Integrity mismatch'}</dd>
            {brokenAt?.expected_hash && (
              <>
                <dt className="font-semibold text-brand-text-muted">Expected hash</dt>
                <dd className="break-all font-mono text-brand-text">{brokenAt.expected_hash}</dd>
              </>
            )}
            {brokenAt?.actual_hash && (
              <>
                <dt className="font-semibold text-brand-text-muted">Stored hash</dt>
                <dd className="break-all font-mono text-brand-text">{brokenAt.actual_hash}</dd>
              </>
            )}
          </dl>
        </div>

        {isRebaseline && (
          <InlineAlert type="warning">
            Rebaseline does not repair entry #{brokenAtId || '—'} or hide the tamper. It records that the incident was investigated and makes the current audit tail the checkpoint for future verification.
          </InlineAlert>
        )}

        <FormField
          id="audit-integrity-notes"
          label={isRebaseline ? 'Rebaseline notes' : 'Investigation notes'}
          hint={isRebaseline ? 'Required. Include why restoring the original row is not being done.' : 'Optional but recommended.'}
        >
          <textarea
            id="audit-integrity-notes"
            className="input-field min-h-[120px]"
            value={notes}
            onChange={(event) => onChangeNotes(event.target.value)}
            placeholder={
              isRebaseline
                ? 'Example: Direct DB tamper was confirmed in pgAdmin; no trusted backup is being restored, so future writes are anchored from the current tail.'
                : 'Example: Row was edited directly in PostgreSQL during integrity testing.'
            }
          />
        </FormField>

        <FormField
          id="audit-integrity-confirm-password"
          label="Confirmation Password"
          hint="Required if your session has been active for more than 15 minutes."
        >
          <input
            id="audit-integrity-confirm-password"
            type="password"
            autoComplete="current-password"
            className="input-field"
            value={confirmPassword}
            onChange={(event) => onChangeConfirmPassword?.(event.target.value)}
            placeholder="Account password"
          />
        </FormField>
      </div>
    </Modal>
  )
}

function DetailField({ label, value, hint, mono, small }) {
  return (
    <div>
      <p className="label-text">{label}</p>
      <div className={`text-sm text-brand-text ${mono ? 'font-mono' : ''} ${small ? 'break-words text-xs' : ''}`}>
        {value}
      </div>
      {hint && <p className="mt-0.5 text-xs text-brand-text-muted">{hint}</p>}
    </div>
  )
}
