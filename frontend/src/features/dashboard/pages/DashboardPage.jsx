import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, BarChart3, Check, CheckCircle2, ChevronDown, ClipboardList, ExternalLink, ShieldAlert, ShieldCheck, TrendingUp, X } from 'lucide-react'
import { Button, FeedbackToast, GlassPanel, InlineAlert, KpiCard, PageHeader } from '../../../components'
import { ROUTES } from '../../../config/routes'
import { isAdmin } from '../../../lib/auth'
import { formatStatus } from '../../../lib/formatters'
import { PROJECT_STATUS_CONFIG } from '../../../lib/projectStatus'
import * as dashboardApi from '../api/dashboardApi'
import * as auditApi from '../../audit/api/auditApi'
import * as projectApi from '../../projects/api/projectApi'
import * as slaApi from '../../sla/api/slaApi'

function formatDate(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleDateString('en-PH', { year: 'numeric', month: 'short', day: 'numeric' })
  } catch {
    return value
  }
}

function getOverdueDays(row) {
  const days = Number(row?.days_remaining)
  if (!Number.isFinite(days)) return 0
  return Math.abs(days)
}

function formatWorkingDays(days) {
  const value = Number(days)
  if (!Number.isFinite(value)) return 'Working-day window not recorded'
  return `${value} working ${value === 1 ? 'day' : 'days'}`
}

function formatNumber(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '0'
  return numeric.toLocaleString('en-PH')
}

function truncateText(value, length = 72) {
  if (!value) return 'No justification recorded.'
  return value.length > length ? `${value.slice(0, length).trim()}...` : value
}

const STATUS_VISUALS = PROJECT_STATUS_CONFIG

function statusItems(summary) {
  return summary?.status_summary?.items || []
}

function statusCount(summary, key, fallback = 0) {
  const item = statusItems(summary).find((entry) => entry.key === key)
  return item?.count ?? fallback
}

function ProjectStatusDonut({ summary, isLoading }) {
  const items = statusItems(summary)
  const total = summary?.status_summary?.total || 0
  const radius = 70
  const circumference = 2 * Math.PI * radius
  const { segments } = items.reduce((state, item) => {
    const value = Number(item.count || 0)
    const length = total ? (value / total) * circumference : 0
    return {
      cursor: state.cursor + length,
      segments: [...state.segments, { key: item.key, length, offset: state.cursor }],
    }
  }, { cursor: 0, segments: [] })

  return (
    <div className="flex flex-col items-center gap-5">
      <div className="relative h-40 w-40">
        <svg viewBox="0 0 200 200" className="h-full w-full -rotate-90">
          <circle cx="100" cy="100" r={radius} fill="none" strokeWidth="22" className="stroke-slate-200 dark:stroke-slate-800" />
          {segments.map((seg) => (
            <circle
              key={seg.key}
              cx="100" cy="100" r={radius}
              fill="none"
              strokeWidth="22"
              stroke={STATUS_VISUALS[seg.key]?.color || '#94a3b8'}
              strokeDasharray={`${seg.length} ${circumference - seg.length}`}
              strokeDashoffset={-seg.offset}
              strokeLinecap="butt"
            />
          ))}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <p className="text-3xl font-bold leading-none text-brand-text">{isLoading ? '—' : formatNumber(total)}</p>
          <p className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">Projects</p>
        </div>
      </div>
      <div className="grid w-full gap-1.5">
        {items.map((item) => (
          <div key={item.key} className="flex items-center justify-between gap-3 text-sm">
            <span className="flex min-w-0 items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: STATUS_VISUALS[item.key]?.color || '#94a3b8' }} />
              <span className="truncate text-brand-text">{STATUS_VISUALS[item.key]?.label || item.label}</span>
            </span>
            <span className="whitespace-nowrap font-semibold tabular-nums text-brand-text">
              {formatNumber(item.count)}
              <span className="ml-1 text-xs font-medium text-brand-text-muted">({item.percentage || 0}%)</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ClusterStatusBars({ rows = [] }) {
  const visibleRows = rows.slice(0, 6)
  if (!visibleRows.length) {
    return <p className="py-6 text-sm text-brand-text-muted">No cluster project status yet.</p>
  }
  return (
    <div className="space-y-3">
      {visibleRows.map((row) => (
        <div key={row.cluster_id || row.cluster_name}>
          <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
            <span className="truncate font-medium text-brand-text">{row.cluster_name}</span>
            <span className="text-xs tabular-nums text-brand-text-muted">{formatNumber(row.total)} projects</span>
          </div>
          <div className="flex h-2.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800" role="img" aria-label={`${row.cluster_name} status mix`}>
            {Object.entries(row.statuses || {}).map(([key, count]) => {
              const width = row.total ? (Number(count || 0) / row.total) * 100 : 0
              if (width <= 0) return null
              return (
                <span
                  key={key}
                  title={`${STATUS_VISUALS[key]?.label || key}: ${count}`}
                  style={{ width: `${width}%`, backgroundColor: STATUS_VISUALS[key]?.color || '#94a3b8' }}
                />
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

function StatusLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11px] text-brand-text-muted">
      {Object.entries(STATUS_VISUALS).map(([key, visual]) => (
        <span key={key} className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: visual.color }} />
          {visual.label}
        </span>
      ))}
    </div>
  )
}

function ProgressBands({ bands = [] }) {
  const total = bands.reduce((sum, band) => sum + Number(band.count || 0), 0)
  const max = Math.max(1, ...bands.map((band) => Number(band.count || 0)))
  if (!bands.length) {
    return <p className="py-6 text-sm text-brand-text-muted">No progress band data yet.</p>
  }
  return (
    <div className="space-y-2.5">
      {bands.map((band) => {
        const count = Number(band.count || 0)
        const pct = total ? Math.round((count / total) * 100) : 0
        return (
          <div key={band.key} className="grid grid-cols-[3.5rem_minmax(0,1fr)_4rem] items-center gap-3 text-xs">
            <span className="font-medium text-brand-text-muted">{band.label}</span>
            <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
              <div className="h-full rounded-full bg-brand-primary" style={{ width: `${(count / max) * 100}%` }} />
            </div>
            <span className="text-right tabular-nums text-brand-text">
              <span className="font-semibold">{formatNumber(count)}</span>
              <span className="ml-1 text-brand-text-muted">({pct}%)</span>
            </span>
          </div>
        )
      })}
    </div>
  )
}

function DashboardVisualSummary({ summary, isLoading, error }) {
  if (error && !summary) {
    return (
      <GlassPanel noPadding>
        <div className="section-header">
          <div>
            <h2 className="section-title">Project status snapshot</h2>
            <p className="section-description">Compact monitoring view by official project status, cluster, and progress band.</p>
          </div>
          <div className="flex items-center gap-3">
            <StatusLegend />
            <BarChart3 className="h-5 w-5 text-brand-text-muted" />
          </div>
        </div>
        <div className="border-t border-brand-border p-5">
          <InlineAlert type="warning">
            Project status snapshot data could not be loaded. Other dashboard sections may still be current.
          </InlineAlert>
        </div>
      </GlassPanel>
    )
  }

  return (
    <GlassPanel noPadding>
      <div className="section-header">
        <div>
          <h2 className="section-title">Project status snapshot</h2>
          <p className="section-description">Compact monitoring view by official project status, cluster, and progress band.</p>
        </div>
        <div className="flex items-center gap-3">
          <StatusLegend />
          <BarChart3 className="h-5 w-5 text-brand-text-muted" />
        </div>
      </div>
      <div className="grid border-t border-brand-border lg:grid-cols-3 lg:divide-x lg:divide-brand-border">
        <div className="border-b border-brand-border p-5 lg:border-b-0">
          <h3 className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-brand-text-muted">Status mix</h3>
          <ProjectStatusDonut summary={summary} isLoading={isLoading} />
        </div>
        <div className="border-b border-brand-border p-5 lg:border-b-0">
          <h3 className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-brand-text-muted">Cluster / PGL mix</h3>
          <ClusterStatusBars rows={summary?.cluster_status_summary || []} />
        </div>
        <div className="p-5">
          <h3 className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-brand-text-muted">Progress bands</h3>
          <ProgressBands bands={summary?.progress_bands || []} />
        </div>
      </div>
    </GlassPanel>
  )
}

function getInitials(value) {
  if (!value) return 'AR'
  const parts = value.trim().split(/\s+/).filter(Boolean)
  const initials = parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join('')
  return initials || 'AR'
}

function overdueToneClasses(days) {
  if (days >= 15) {
    return {
      rail: 'bg-red-700 dark:bg-red-300',
      badge: 'border-red-300 bg-red-50 text-red-800 dark:border-red-400/40 dark:bg-red-400/10 dark:text-red-100',
      text: 'text-red-800 dark:text-red-100',
    }
  }
  if (days >= 5) {
    return {
      rail: 'bg-amber-600 dark:bg-amber-300',
      badge: 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-300/40 dark:bg-amber-300/10 dark:text-amber-100',
      text: 'text-amber-800 dark:text-amber-100',
    }
  }
  return {
    rail: 'bg-orange-500 dark:bg-orange-300',
    badge: 'border-orange-300 bg-orange-50 text-orange-800 dark:border-orange-300/40 dark:bg-orange-300/10 dark:text-orange-100',
    text: 'text-orange-800 dark:text-orange-100',
  }
}

const OVERDUE_FILTERS = [
  {
    key: 'all',
    label: 'All',
    matches: () => true,
  },
  {
    key: 'escalated',
    label: 'Escalated',
    matches: (row) => Boolean(row.escalation_triggered),
  },
  {
    key: 'mid_overdue',
    label: '5-14 days',
    matches: (row) => {
      const days = getOverdueDays(row)
      return days >= 5 && days < 15
    },
  },
  {
    key: 'long_overdue',
    label: '15+ days',
    matches: (row) => getOverdueDays(row) >= 15,
  },
]

const OVERDUE_GROUPS = [
  {
    key: 'long_overdue',
    title: '15+ working days overdue',
    description: 'Oldest items. Check notice or escalation history first.',
    matches: (days) => days >= 15,
    headerClass: 'border-red-300 bg-red-50 text-red-900 dark:border-red-400/40 dark:bg-red-400/10 dark:text-red-100',
  },
  {
    key: 'mid_overdue',
    title: '5-14 working days overdue',
    description: 'Needs active deadline follow-up.',
    matches: (days) => days >= 5 && days < 15,
    headerClass: 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-300/40 dark:bg-amber-300/10 dark:text-amber-100',
  },
  {
    key: 'recent_overdue',
    title: '1-4 working days overdue',
    description: 'Recently missed timers to clear early.',
    matches: (days) => days < 5,
    headerClass: 'border-orange-300 bg-orange-50 text-orange-900 dark:border-orange-300/40 dark:bg-orange-300/10 dark:text-orange-100',
  },
]

function groupedDeadlines(deadlines) {
  return OVERDUE_GROUPS.map((group) => ({
    ...group,
    rows: deadlines.filter((row) => group.matches(getOverdueDays(row))),
  })).filter((group) => group.rows.length > 0)
}

function OverdueDeadlineWatchlist({ deadlines, isLoading, error }) {
  const [activeFilter, setActiveFilter] = useState('all')
  const flaggedCount = deadlines.filter((row) => row.escalation_triggered).length
  const filterOptions = OVERDUE_FILTERS.map((filter) => ({
    ...filter,
    count: deadlines.filter(filter.matches).length,
  }))
  const selectedFilter = filterOptions.find((filter) => filter.key === activeFilter) || filterOptions[0]
  const visibleDeadlines = deadlines.filter(selectedFilter.matches)
  const groups = groupedDeadlines(visibleDeadlines)

  if (isLoading) {
    return (
      <div className="border-t border-brand-border px-5 py-8 text-center text-sm text-brand-text-muted">
        <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-brand-primary border-t-transparent" />
        Loading overdue deadlines...
      </div>
    )
  }

  if (error) {
    return (
      <div className="border-t border-brand-border p-5">
        <InlineAlert type="warning">
          Overdue deadlines could not be loaded. Other dashboard sections may still be current.
        </InlineAlert>
      </div>
    )
  }

  if (!deadlines.length) {
    return (
      <div className="border-t border-brand-border px-5 py-8 text-center">
        <CheckCircle2 className="mx-auto mb-3 h-8 w-8 text-emerald-700 dark:text-emerald-200" strokeWidth={1.6} />
        <p className="text-sm font-medium text-brand-text">No overdue working-day deadlines right now.</p>
        <p className="mt-1 text-sm text-brand-text-muted">The queue is clear for unresolved overdue timers.</p>
      </div>
    )
  }

  return (
    <div className="border-t border-brand-border">
      <div className="flex flex-wrap gap-2 border-b border-brand-border bg-brand-surface px-5 py-3">
        {filterOptions.map((filter) => {
          const isActive = filter.key === selectedFilter.key
          return (
            <button
              key={filter.key}
              type="button"
              className={`min-h-10 rounded-md border px-4 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/35 ${
                isActive
                  ? 'border-brand-primary bg-brand-primary text-white dark:border-blue-300 dark:bg-blue-300 dark:text-slate-950'
                  : 'border-brand-border bg-brand-surface-solid text-brand-text hover:bg-brand-surface'
              }`}
              aria-pressed={isActive}
              onClick={() => setActiveFilter(filter.key)}
            >
              {filter.label}
              <span className={`ml-2 text-xs ${isActive ? 'text-white/80 dark:text-slate-800' : 'text-brand-text-muted'}`}>
                {filter.count}
              </span>
            </button>
          )
        })}
      </div>

      <div className="flex flex-col border-b border-brand-border bg-brand-surface px-5 py-3 text-sm text-brand-text-muted sm:flex-row sm:items-center sm:justify-between">
        <span>
          Showing {visibleDeadlines.length} of {deadlines.length} unresolved overdue {deadlines.length === 1 ? 'deadline' : 'deadlines'}.
        </span>
        <span className="inline-flex items-center gap-1.5 font-medium text-brand-text">
          <ShieldAlert className="h-4 w-4 text-amber-700 dark:text-amber-200" strokeWidth={1.7} />
          {flaggedCount} escalation {flaggedCount === 1 ? 'flag' : 'flags'}
        </span>
      </div>

      <div className="max-h-[38rem] overflow-y-auto bg-brand-surface-solid" aria-label="Overdue deadline watchlist">
        {!visibleDeadlines.length ? (
          <div className="px-5 py-8 text-center text-sm text-brand-text-muted">
            No overdue deadlines match the selected filter.
          </div>
        ) : groups.map((group) => (
          <section key={group.key} aria-labelledby={`${group.key}-heading`}>
            <div className={`sticky top-0 z-10 grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-b px-5 py-2.5 ${group.headerClass}`}>
              <ChevronDown className="h-4 w-4" strokeWidth={1.8} aria-hidden="true" />
              <div className="min-w-0">
                <h3 id={`${group.key}-heading`} className="truncate text-sm font-semibold">{group.title}</h3>
                <p className="truncate text-xs opacity-80">{group.description}</p>
              </div>
              <span className="whitespace-nowrap text-xs font-semibold">
                {group.rows.length} {group.rows.length === 1 ? 'item' : 'items'}
              </span>
            </div>

            <ul className="flex flex-col">
              {group.rows.map((row) => {
                const overdueDays = getOverdueDays(row)
                const tone = overdueToneClasses(overdueDays)
                const projectName = row.project_name || `Project #${row.project_id}`
                const requirementName = row.requirement_name || 'General deadline'

                return (
                  <li key={row.id} className="relative grid gap-3 border-b border-brand-border bg-brand-surface-solid px-5 py-2.5 pl-6 hover:bg-slate-50 dark:hover:bg-slate-800/60 sm:grid-cols-[minmax(0,1fr)_auto]">
                    <div className={`absolute inset-y-0 left-0 w-1 ${tone.rail}`} aria-hidden="true" />

                    <div className="min-w-0 self-center">
                      <div className="truncate text-sm font-semibold text-brand-text" title={projectName}>
                        {projectName}
                      </div>
                      <div className="mt-0.5 truncate text-sm text-brand-text-muted" title={requirementName}>
                        {requirementName}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-2">
                        <span className={`inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-[11px] font-bold ${tone.badge}`}>
                          <AlertTriangle className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
                          {overdueDays || 'Overdue'} {overdueDays === 1 ? 'day' : 'days'} overdue
                        </span>
                        {row.escalation_triggered && (
                          <span className="inline-flex items-center gap-1 rounded-sm border border-red-200 bg-red-50 px-2 py-0.5 text-[11px] font-bold text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-300">
                            <ShieldAlert className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
                            Escalated
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-col gap-2 sm:w-40 sm:items-end">
                      <div className="text-left sm:text-right">
                        <p className={`whitespace-nowrap text-sm font-bold ${tone.text}`}>
                          Due {formatDate(row.deadline_date)}
                        </p>
                        <p className="mt-0.5 whitespace-nowrap text-xs text-brand-text-muted">
                          {formatWorkingDays(row.sla_working_days)} window
                        </p>
                      </div>
                      {row.project_id ? (
                        <Link
                          className="inline-flex min-h-8 w-full items-center justify-center gap-1.5 rounded-md border border-brand-border bg-brand-surface-solid px-3 py-1.5 text-sm font-medium text-brand-text shadow-sm transition-colors hover:bg-brand-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/35 sm:w-24"
                          to={ROUTES.projectDetail(row.project_id)}
                        >
                          Open
                          <ExternalLink className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
                        </Link>
                      ) : (
                        <Link
                          className="inline-flex min-h-8 w-full items-center justify-center rounded-md border border-brand-border bg-brand-surface-solid px-3 py-1.5 text-sm font-medium text-brand-text shadow-sm transition-colors hover:bg-brand-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/35 sm:w-24"
                          to={ROUTES.SLA}
                        >
                          Timers
                        </Link>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </div>
    </div>
  )
}

function getAuditActionBars(stats) {
  const actionCounts = stats?.action_counts || {}
  const entries = Object.entries(actionCounts)
    .map(([key, value]) => ({ key, value: Number(value) || 0 }))
    .filter((entry) => entry.value > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)

  if (!entries.length) {
    return Array.from({ length: 10 }, (_, index) => ({
      key: `empty-${index}`,
      value: 0,
      ratio: 0,
      label: 'No activity recorded',
    }))
  }

  const max = Math.max(...entries.map((entry) => entry.value))
  return entries.map((entry) => ({
    ...entry,
    ratio: entry.value / max,
    label: `${formatStatus(entry.key)}: ${formatNumber(entry.value)}`,
  }))
}

function AuditTrailPanel({ stats, chain, isLoading, error }) {
  const isValid = Boolean(chain?.is_valid)
  const actionCounts = stats?.action_counts || {}
  const flaggedEvents = Number(actionCounts.escalate || actionCounts.escalation || actionCounts.flag || 0)
  const bars = getAuditActionBars(stats)
  const topActions = bars.filter((bar) => bar.value > 0).slice(0, 3)

  return (
    <GlassPanel noPadding className="self-start">
      <div className="section-header">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-brand-text-muted">Integrity</p>
          <h2 className="section-title mt-1">Audit trail</h2>
          <p className="section-description">Hash-chain integrity and recent operator activity.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="px-5 py-8 text-center text-sm text-brand-text-muted">
          <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-brand-primary border-t-transparent" />
          Loading audit status...
        </div>
      ) : error ? (
        <div className="border-t border-brand-border p-5">
          <InlineAlert type="warning">
            Audit trail status could not be loaded. Other dashboard sections may still be current.
          </InlineAlert>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-3 border-b border-brand-border px-5 py-5">
            <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full border ${
              isValid
                ? 'border-emerald-600 bg-emerald-50 text-emerald-800 dark:border-emerald-300/60 dark:bg-emerald-300/10 dark:text-emerald-100'
                : 'border-amber-500 bg-amber-50 text-amber-800 dark:border-amber-300/60 dark:bg-amber-300/10 dark:text-amber-100'
            }`}>
              {isValid ? <Check className="h-5 w-5" strokeWidth={2} /> : <ShieldAlert className="h-5 w-5" strokeWidth={1.8} />}
            </div>
            <div>
              <p className={`text-sm font-semibold ${isValid ? 'text-emerald-800 dark:text-emerald-100' : 'text-amber-800 dark:text-amber-100'}`}>
                {isValid ? 'Chain valid' : 'Integrity check needed'}
              </p>
              <p className="text-sm text-brand-text-muted">
                {isValid ? 'No integrity issues detected' : 'Open the audit log to review chain status.'}
              </p>
            </div>
          </div>

          <dl className="grid grid-cols-2 border-b border-brand-border">
            <div className="border-b border-r border-brand-border px-5 py-4">
              <dt className="text-xs font-semibold uppercase text-brand-text-muted">Entries</dt>
              <dd className="mt-1 text-2xl font-semibold text-brand-text">{formatNumber(stats?.total)}</dd>
            </div>
            <div className="border-b border-brand-border px-5 py-4">
              <dt className="text-xs font-semibold uppercase text-brand-text-muted">Last 24 hours</dt>
              <dd className="mt-1 text-2xl font-semibold text-blue-700 dark:text-blue-200">{formatNumber(stats?.recent_count_24h)}</dd>
            </div>
            <div className="border-r border-brand-border px-5 py-4">
              <dt className="text-xs font-semibold uppercase text-brand-text-muted">Unique actors</dt>
              <dd className="mt-1 text-2xl font-semibold text-brand-text">{formatNumber(stats?.unique_users)}</dd>
            </div>
            <div className="px-5 py-4">
              <dt className="text-xs font-semibold uppercase text-brand-text-muted">Flagged events</dt>
              <dd className="mt-1 text-2xl font-semibold text-brand-text">{formatNumber(flaggedEvents)}</dd>
            </div>
          </dl>

          <div className="px-5 py-5">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="text-xs font-semibold uppercase text-brand-text-muted">Activity mix</h3>
              <span className="inline-flex items-center gap-1 text-xs text-brand-text-muted">
                <TrendingUp className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden="true" />
                by action type
              </span>
            </div>
            <div className="flex h-14 items-end gap-1.5" aria-label="Audit action count bars">
              {bars.map((bar, index) => {
                const isTop = index === 0 && bar.value > 0
                const heightPct = bar.value > 0 ? Math.max(18, Math.round(bar.ratio * 100)) : 18
                return (
                  <div
                    key={bar.key}
                    className={`flex-1 rounded-md ${
                      isTop
                        ? 'bg-blue-200 dark:bg-blue-300/50'
                        : 'bg-blue-50 ring-1 ring-inset ring-blue-100 dark:bg-blue-300/10 dark:ring-blue-300/20'
                    }`}
                    style={{ height: isTop ? `${heightPct}%` : '28%' }}
                    title={bar.label}
                  />
                )
              })}
            </div>
            {topActions.length > 0 && (
              <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
                {topActions.map((action) => (
                  <div key={action.key} className="inline-flex items-center gap-2 text-xs text-brand-text">
                    <span className="h-2 w-2 rounded-full bg-blue-500 dark:bg-blue-300" aria-hidden="true" />
                    <span className="font-medium">{formatStatus(action.key)}</span>
                    <span className="text-brand-text-muted">{formatNumber(action.value)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </GlassPanel>
  )
}

function groupChangeRequestsByProject(requests) {
  const groups = new Map()
  requests.forEach((request) => {
    const projectId = request.requirement?.project_id || 'unassigned'
    const existing = groups.get(projectId) || {
      projectId,
      projectName: request.requirement?.project_name || 'Unassigned project',
      rows: [],
    }
    existing.rows.push(request)
    groups.set(projectId, existing)
  })
  return Array.from(groups.values())
}

function PendingStatusChangeQueue({
  requests,
  isLoading,
  error,
  selectedIds,
  reviewingIds,
  canReview,
  onToggleRequest,
  onToggleAll,
  onReview,
  onBulkReview,
}) {
  const pendingIds = requests.filter((request) => request.status === 'pending').map((request) => request.id)
  const selectedPendingIds = selectedIds.filter((id) => pendingIds.includes(id))
  const allSelected = pendingIds.length > 0 && selectedPendingIds.length === pendingIds.length
  const selectedSet = new Set(selectedIds)
  const reviewingSet = new Set(reviewingIds)
  const groups = groupChangeRequestsByProject(requests)

  if (isLoading) {
    return (
      <div className="border-t border-brand-border px-5 py-8 text-center text-sm text-brand-text-muted">
        <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-brand-primary border-t-transparent" />
        Loading pending status changes...
      </div>
    )
  }

  if (error) {
    return (
      <div className="border-t border-brand-border p-5">
        <InlineAlert type="warning">
          Pending status change requests could not be loaded. Other dashboard sections may still be current.
        </InlineAlert>
      </div>
    )
  }

  if (!requests.length) {
    return (
      <div className="border-t border-brand-border px-5 py-8 text-center">
        <ShieldCheck className="mx-auto mb-3 h-8 w-8 text-emerald-700 dark:text-emerald-200" strokeWidth={1.6} />
        <p className="text-sm font-medium text-brand-text">No pending status change requests.</p>
        <p className="mt-1 text-sm text-brand-text-muted">Administrator review queue is clear.</p>
      </div>
    )
  }

  return (
    <>
      {canReview && selectedPendingIds.length > 0 && (
        <div className="flex flex-col gap-3 border-t border-brand-border bg-brand-surface px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-xs font-semibold text-brand-text">{selectedPendingIds.length} selected</span>
          <div className="flex gap-2">
            <Button size="sm" variant="success" onClick={() => onBulkReview('approved')} disabled={selectedPendingIds.some((id) => reviewingSet.has(id))}>
              Approve selected
            </Button>
            <Button size="sm" variant="outline" onClick={() => onBulkReview('rejected')} disabled={selectedPendingIds.some((id) => reviewingSet.has(id))}>
              Reject selected
            </Button>
          </div>
        </div>
      )}

      <div className="bg-brand-surface-solid">
        {groups.map((group) => (
          <section key={group.projectId} aria-labelledby={`change-group-${group.projectId}`}>
            <div className="grid grid-cols-[auto_auto_minmax(0,1fr)_auto] items-center gap-3 border-t border-brand-border bg-brand-surface px-5 py-3">
              {canReview ? (
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-brand-border text-brand-primary focus:ring-brand-primary/30"
                  checked={allSelected}
                  onChange={(event) => onToggleAll(pendingIds, event.target.checked)}
                  aria-label={`Select all in ${group.projectName}`}
                />
              ) : (
                <span className="h-4 w-4" aria-hidden="true" />
              )}
              <ChevronDown className="h-4 w-4 text-brand-text-muted" strokeWidth={1.8} aria-hidden="true" />
              <h3 id={`change-group-${group.projectId}`} className="truncate text-sm font-semibold text-brand-text" title={group.projectName}>
                {group.projectName}
              </h3>
              <span className="text-xs font-semibold text-blue-700 dark:text-blue-200">
                {group.rows.length} pending
              </span>
            </div>

            <ul>
              {group.rows.map((request) => {
                const requirementName = request.requirement?.requirement_name || 'Requirement status change'
                const isSelected = selectedSet.has(request.id)
                const isReviewing = reviewingSet.has(request.id)

                return (
                  <li key={request.id} className="grid gap-4 border-b border-brand-border px-5 py-4 md:grid-cols-[auto_minmax(0,1fr)_auto_auto] md:items-center">
                    <div className="flex items-start md:items-center">
                      {canReview ? (
                        <input
                          type="checkbox"
                          className="mt-1 h-4 w-4 rounded border-brand-border text-brand-primary focus:ring-brand-primary/30 md:mt-0"
                          checked={isSelected}
                          disabled={isReviewing}
                          aria-label={`Select ${requirementName}`}
                          onChange={(event) => onToggleRequest(request.id, event.target.checked)}
                        />
                      ) : (
                        <ShieldCheck className="h-4 w-4 text-brand-text-muted" strokeWidth={1.8} aria-hidden="true" />
                      )}
                    </div>

                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-brand-text" title={requirementName}>
                        {requirementName}
                      </p>
                      <p className="mt-1 truncate text-sm text-brand-text-muted" title={request.justification}>
                        {truncateText(request.justification)}
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <div className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-800 dark:bg-blue-300/15 dark:text-blue-100" title={request.requested_by_name || 'Requester'}>
                        {getInitials(request.requested_by_name)}
                      </div>
                      <span className="status-badge status-badge-neutral">{formatStatus(request.current_status)}</span>
                      <span className="max-w-48 break-words text-xs font-medium text-brand-text">{request.requested_by_name || 'Requester'}</span>
                      <span className="text-xs font-semibold text-brand-text-muted">to</span>
                      <span className="status-badge status-badge-warning">{formatStatus(request.requested_status)}</span>
                    </div>

                    <div className="flex items-center gap-1 md:justify-end">
                      {canReview && request.status === 'pending' ? (
                        <>
                          <button
                            type="button"
                            onClick={() => onReview(request.id, 'approved')}
                            disabled={isReviewing}
                            className="inline-flex items-center gap-1.5 rounded-md border border-brand-border bg-brand-surface-solid px-2.5 py-1.5 text-sm font-medium text-brand-text shadow-sm transition hover:border-emerald-400 hover:bg-emerald-50 hover:text-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 disabled:opacity-50 dark:bg-brand-surface dark:hover:border-emerald-300/60 dark:hover:bg-emerald-300/10 dark:hover:text-emerald-200"
                          >
                            <Check className="h-4 w-4" strokeWidth={2} aria-hidden="true" />
                            Approve
                          </button>
                          <button
                            type="button"
                            onClick={() => onReview(request.id, 'rejected')}
                            disabled={isReviewing}
                            className="inline-flex items-center gap-1.5 rounded-md border border-brand-border bg-brand-surface-solid px-2.5 py-1.5 text-sm font-medium text-brand-text shadow-sm transition hover:border-red-400 hover:bg-red-50 hover:text-red-700 focus:outline-none focus:ring-2 focus:ring-red-500/30 disabled:opacity-50 dark:bg-brand-surface dark:hover:border-red-300/60 dark:hover:bg-red-300/10 dark:hover:text-red-200"
                          >
                            <X className="h-4 w-4" strokeWidth={2} aria-hidden="true" />
                            Reject
                          </button>
                        </>
                      ) : (
                        <span className="status-badge status-badge-neutral">{formatStatus(request.status)}</span>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </div>
    </>
  )
}

export default function DashboardPage() {
  const [loading, setLoading] = useState(true)
  const [projects, setProjects] = useState([])
  const [projectsError, setProjectsError] = useState(false)
  const [operationsDashboard, setOperationsDashboard] = useState(null)
  const [opsError, setOpsError] = useState(false)
  const [slaDashboard, setSlaDashboard] = useState(null)
  const [slaError, setSlaError] = useState(false)
  const [overdueDeadlines, setOverdueDeadlines] = useState([])
  const [overdueError, setOverdueError] = useState(false)
  const [changeRequests, setChangeRequests] = useState([])
  const [changeRequestsError, setChangeRequestsError] = useState(false)
  const [auditStats, setAuditStats] = useState(null)
  const [auditChain, setAuditChain] = useState(null)
  const [auditError, setAuditError] = useState(false)
  const [dashboardError, setDashboardError] = useState('')
  const [reviewError, setReviewError] = useState('')
  const [reviewMessage, setReviewMessage] = useState('')
  const [selectedRequestIds, setSelectedRequestIds] = useState([])
  const [reviewingRequestIds, setReviewingRequestIds] = useState([])
  const canViewAuditTrail = isAdmin()

  const loadDashboard = useCallback(async () => {
    setLoading(true)
    setDashboardError('')
    try {
      const results = await Promise.allSettled([
        projectApi.listProjects({ per_page: 100 }),
        dashboardApi.getOperationsDashboard(),
        slaApi.getSlaDashboard(),
        slaApi.getOverdueDeadlines(),
        projectApi.listChangeStatusRequests({ status: 'pending' }),
        canViewAuditTrail ? auditApi.getAuditStats() : Promise.resolve({ data: null }),
        canViewAuditTrail ? auditApi.verifyAuditChain() : Promise.resolve({ data: null }),
      ])

      const [projectsRes, operationsRes, slaRes, overdueRes, requestRes, statsRes, chainRes] = results

      let hasFailures = false

      if (projectsRes.status === 'fulfilled') {
        setProjects(projectsRes.value.data || [])
        setProjectsError(false)
      } else {
        setProjectsError(true)
        hasFailures = true
      }

      if (operationsRes.status === 'fulfilled') {
        setOperationsDashboard(operationsRes.value.data || null)
        setOpsError(false)
      } else {
        setOpsError(true)
        hasFailures = true
      }

      if (slaRes.status === 'fulfilled') {
        setSlaDashboard(slaRes.value.data || null)
        setSlaError(false)
      } else {
        setSlaError(true)
        hasFailures = true
      }

      if (overdueRes.status === 'fulfilled') {
        setOverdueDeadlines(overdueRes.value.data || [])
        setOverdueError(false)
      } else {
        setOverdueError(true)
        hasFailures = true
      }

      if (requestRes.status === 'fulfilled') {
        setChangeRequests(requestRes.value.data || [])
        setChangeRequestsError(false)
      } else {
        setChangeRequestsError(true)
        hasFailures = true
      }

      if (canViewAuditTrail) {
        if (statsRes.status === 'fulfilled' && chainRes.status === 'fulfilled') {
          setAuditStats(statsRes.value.data || null)
          setAuditChain(chainRes.value.data || null)
          setAuditError(false)
        } else {
          setAuditError(true)
          hasFailures = true
        }
      }

      setSelectedRequestIds([])

      if (hasFailures) {
        setDashboardError('Some dashboard data could not be loaded. Showing latest available information.')
      }
    } catch {
      setDashboardError('Unable to load dashboard data. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [canViewAuditTrail])

  useEffect(() => {
    loadDashboard()
  }, [loadDashboard])

  const handleReview = async (requestId, decision) => {
    setReviewError('')
    setReviewMessage('')
    setReviewingRequestIds((current) => Array.from(new Set([...current, requestId])))
    try {
      await projectApi.reviewChangeStatusRequest(requestId, { decision })
      setReviewMessage(`Status change request ${decision}.`)
      setSelectedRequestIds((current) => current.filter((id) => id !== requestId))
      await loadDashboard()
    } catch (err) {
      setReviewError(err.response?.data?.message || 'Unable to review the status change request.')
    } finally {
      setReviewingRequestIds((current) => current.filter((id) => id !== requestId))
    }
  }

  const handleBulkReview = async (decision) => {
    const pendingIds = changeRequests.filter((request) => request.status === 'pending').map((request) => request.id)
    const requestIds = selectedRequestIds.filter((id) => pendingIds.includes(id))
    if (!requestIds.length) return

    setReviewError('')
    setReviewMessage('')
    setReviewingRequestIds((current) => Array.from(new Set([...current, ...requestIds])))

    try {
      const results = await Promise.allSettled(
        requestIds.map((requestId) => projectApi.reviewChangeStatusRequest(requestId, { decision })),
      )
      const successCount = results.filter((result) => result.status === 'fulfilled').length
      const failedCount = results.length - successCount

      if (successCount > 0) {
        setReviewMessage(`${successCount} status change ${successCount === 1 ? 'request' : 'requests'} ${decision}.`)
      }
      if (failedCount > 0) {
        setReviewError(`${failedCount} selected ${failedCount === 1 ? 'request' : 'requests'} could not be reviewed.`)
      }

      await loadDashboard()
    } finally {
      setReviewingRequestIds((current) => current.filter((id) => !requestIds.includes(id)))
    }
  }

  const handleToggleRequest = (requestId, checked) => {
    setSelectedRequestIds((current) => (
      checked
        ? Array.from(new Set([...current, requestId]))
        : current.filter((id) => id !== requestId)
    ))
  }

  const handleToggleAllRequests = (requestIds, checked) => {
    setSelectedRequestIds((current) => {
      if (checked) return Array.from(new Set([...current, ...requestIds]))
      return current.filter((id) => !requestIds.includes(id))
    })
  }

  const dashboardProjectTotal = (opsError && projectsError && !operationsDashboard && projects.length === 0)
    ? '—'
    : (operationsDashboard?.status_summary?.total ?? (projectsError && projects.length === 0 ? '—' : projects.length))

  const ongoingProjects = (opsError && projectsError && !operationsDashboard && projects.length === 0)
    ? '—'
    : statusCount(
        operationsDashboard,
        'ongoing',
        projectsError && projects.length === 0 ? '—' : projects.filter((project) => project.overall_status === 'ongoing').length,
      )

  const overdueKpi = (slaError && !slaDashboard) ? '—' : (slaDashboard?.overdue ?? 0)

  const pendingRequestsCount = changeRequests.filter((request) => request.status === 'pending').length
  const pendingRequestsKpi = (changeRequestsError && changeRequests.length === 0) ? '—' : pendingRequestsCount
  const canReviewStatusRequests = canViewAuditTrail

  return (
    <div>
      <PageHeader
        title="Operations Dashboard"
        description="Provincial view of project status, working-day deadlines, audit history, and pending status change requests."
        actions={<Button variant="outline" size="sm" onClick={loadDashboard}>Refresh</Button>}
      />

      {dashboardError && (
        <InlineAlert type="warning" className="mb-6">
          <div className="flex items-center justify-between gap-4">
            <span>{dashboardError}</span>
            <Button size="sm" variant="outline" onClick={loadDashboard}>Retry</Button>
          </div>
        </InlineAlert>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <KpiCard title="Projects" value={loading ? '—' : dashboardProjectTotal} subtitle={loading ? 'Loading…' : 'in registry'} icon={ClipboardList} color="blue" />
        <KpiCard title="Ongoing" value={loading ? '—' : ongoingProjects} subtitle={loading ? 'Loading…' : 'in progress'} icon={CheckCircle2} color="blue" />
        <KpiCard title="Overdue deadlines" value={loading ? '—' : overdueKpi} subtitle={loading ? 'Loading…' : 'escalated'} icon={AlertTriangle} color="red" />
        <KpiCard title="Status changes" value={loading ? '—' : pendingRequestsKpi} subtitle={loading ? 'Loading…' : 'awaits your review'} icon={ShieldCheck} color="amber" />
      </div>

      <div className="mb-4">
        <DashboardVisualSummary summary={operationsDashboard} isLoading={loading} error={opsError} />
      </div>

      <div className={`grid grid-cols-1 items-start gap-4 mb-6 ${canViewAuditTrail ? 'lg:grid-cols-3' : ''}`}>
        <GlassPanel className={canViewAuditTrail ? 'lg:col-span-2' : undefined} noPadding>
          <div className="section-header">
            <div>
              <h2 className="section-title">Overdue deadline watchlist</h2>
              <p className="section-description">Oldest unresolved working-day deadlines first.</p>
            </div>
            <div className="flex flex-wrap gap-2 text-xs font-semibold">
              <span className="status-badge status-badge-danger">
                {overdueError && !overdueDeadlines.length ? '—' : `${overdueDeadlines.length} overdue`}
              </span>
              <span className="status-badge status-badge-neutral">
                {overdueError && !overdueDeadlines.length ? '—' : `${overdueDeadlines.filter((row) => row.escalation_triggered).length} flagged`}
              </span>
            </div>
          </div>
          <OverdueDeadlineWatchlist deadlines={overdueDeadlines} isLoading={loading} error={overdueError} />
        </GlassPanel>

        {canViewAuditTrail && <AuditTrailPanel stats={auditStats} chain={auditChain} isLoading={loading} error={auditError} />}
      </div>

      <FeedbackToast type="error" message={reviewError} onDismiss={() => setReviewError('')} />
      <FeedbackToast type="success" message={reviewMessage} onDismiss={() => setReviewMessage('')} />

      <GlassPanel noPadding>
        <div className="section-header">
          <div>
            <h2 className="section-title">Pending status changes</h2>
            <p className="section-description">Review queue for proposed requirement status changes. Select rows to act in bulk.</p>
          </div>
          {pendingRequestsKpi !== '—' && pendingRequestsCount > 0 && (
            <span className="status-badge status-badge-warning">{pendingRequestsCount} pending</span>
          )}
        </div>
        <PendingStatusChangeQueue
          requests={changeRequests}
          isLoading={loading}
          error={changeRequestsError}
          selectedIds={selectedRequestIds}
          reviewingIds={reviewingRequestIds}
          canReview={canReviewStatusRequests}
          onToggleRequest={handleToggleRequest}
          onToggleAll={handleToggleAllRequests}
          onReview={handleReview}
          onBulkReview={handleBulkReview}
        />
      </GlassPanel>
    </div>
  )
}
