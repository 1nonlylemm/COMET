import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  Bot,
  Calendar,
  CheckCircle2,
  Clock,
  Database,
  ExternalLink,
  HardDrive,
  RefreshCw,
  Server,
  ServerCog,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  XCircle,
} from 'lucide-react'
import { Button, DataTable, EmptyState, GlassPanel, InlineAlert, KpiCard, PageHeader } from '../../../components'
import { ROUTES } from '../../../config/routes'
import { badgeClassForTone } from '../../../lib/statusStyles'
import { formatDateTime, formatMachineLabel, formatRelativeTime, formatStatus } from '../../../lib/formatters'
import * as systemAdminApi from '../api/systemAdminApi'

function formatCount(value) {
  if (value === null || value === undefined) return '-'
  return new Intl.NumberFormat().format(value)
}

function healthBadge(status, label = null) {
  const norm = String(status || '').toLowerCase()
  let tone = 'neutral'
  if (norm === 'healthy' || norm === 'ready' || norm === 'ok') tone = 'success'
  else if (norm === 'degraded' || norm === 'warning') tone = 'warning'
  else if (norm === 'unavailable' || norm === 'failed' || norm === 'error' || norm === 'critical') tone = 'danger'
  else if (norm === 'not_verified') tone = 'neutral'

  return <span className={badgeClassForTone(tone)}>{label || formatStatus(status)}</span>
}

function formatLatency(ms) {
  if (ms === null || ms === undefined) return '-'
  if (ms < 1) return '< 1 ms'
  return `${ms.toFixed(1)} ms`
}

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return '-'
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

export default function SystemAdminOverviewPage() {
  const [overview, setOverview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadOverview = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await systemAdminApi.getSystemAdminOverview()
      setOverview(response.data || null)
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to load technical System Administration overview.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadOverview()
  }, [loadOverview])

  const systemHealth = overview?.system_health || {}
  const background = overview?.background_processing || {}
  const recentIncidents = overview?.recent_incidents || []
  const recentAdminActivity = overview?.recent_admin_activity || []
  const databaseBackup = overview?.database_backup || {}
  const providers = overview?.providers || {}
  const aiProviders = providers.ai?.providers || []
  const configuredProviders = aiProviders.filter((p) => p.configured).length

  // KPI calculations
  const healthStatus = systemHealth.status || 'unknown'
  const healthKpiColor = healthStatus === 'healthy' ? 'emerald' : healthStatus === 'degraded' ? 'amber' : 'rose'

  const workerStatus = background.workers?.status || 'unknown'
  const workerCount = background.workers?.count || 0
  const schedulerStatus = background.scheduler?.status || 'unknown'
  const backgroundKpiColor = workerStatus === 'healthy' && schedulerStatus === 'healthy' ? 'emerald' : 'amber'

  const latestBackup = databaseBackup.latest
  const backupKpiColor = latestBackup && latestBackup.status === 'completed' ? 'emerald' : databaseBackup.total_count > 0 ? 'amber' : 'blue'

  const aiKpiColor = configuredProviders > 0 ? 'emerald' : 'amber'

  // Dependency table rows
  const dependencyRows = useMemo(() => {
    const deps = overview?.dependencies || {}
    return Object.entries(deps).map(([key, item]) => ({
      key,
      name: item.name || formatMachineLabel(key),
      status: item.status,
      status_label: item.status_label || formatStatus(item.status),
      latency_ms: item.latency_ms,
      is_live_probe: item.is_live_probe,
      checked_at: item.checked_at,
      message: item.message,
    }))
  }, [overview?.dependencies])

  const dependencyColumns = [
    {
      key: 'name',
      label: 'Dependency',
      render: (row) => (
        <div>
          <div className="font-medium text-brand-text">{row.name}</div>
          <div className="text-xs text-brand-text-muted">
            {row.is_live_probe ? 'Live health probe' : 'Configuration check'}
          </div>
        </div>
      ),
    },
    {
      key: 'status',
      label: 'Health Status',
      render: (row) => healthBadge(row.status, row.status_label),
    },
    {
      key: 'latency_ms',
      label: 'Response Time',
      render: (row) => (
        <span className="font-mono text-xs text-brand-text-muted">
          {formatLatency(row.latency_ms)}
        </span>
      ),
    },
    {
      key: 'checked_at',
      label: 'Last Checked',
      render: (row) => (
        <span className="text-xs text-brand-text-muted" title={formatDateTime(row.checked_at)}>
          {formatRelativeTime(row.checked_at, 'Recently')}
        </span>
      ),
    },
    {
      key: 'message',
      label: 'Diagnostic Details',
      render: (row) => (
        <span className="text-sm text-brand-text-muted">{row.message}</span>
      ),
    },
  ]

  // Incidents table columns
  const incidentColumns = [
    {
      key: 'severity',
      label: 'Severity',
      render: (row) => healthBadge(row.severity, row.severity?.toUpperCase()),
    },
    {
      key: 'component',
      label: 'Component',
      render: (row) => <span className="font-medium text-brand-text">{formatMachineLabel(row.component)}</span>,
    },
    {
      key: 'event_name',
      label: 'Event Type',
      render: (row) => <span className="text-xs font-mono text-brand-text-muted">{row.event_name || row.event_type}</span>,
    },
    {
      key: 'message',
      label: 'Summary',
      render: (row) => (
        <span className="text-sm text-brand-text truncate max-w-xs block" title={row.message}>
          {row.message}
        </span>
      ),
    },
    {
      key: 'created_at',
      label: 'Timestamp',
      render: (row) => (
        <span className="text-xs text-brand-text-muted whitespace-nowrap" title={formatDateTime(row.created_at)}>
          {formatRelativeTime(row.created_at, 'Recently')}
        </span>
      ),
    },
  ]

  // Admin audit activity columns
  const auditColumns = [
    {
      key: 'action',
      label: 'Action',
      render: (row) => (
        <span className="font-medium text-brand-text">{row.action_label || formatMachineLabel(row.action)}</span>
      ),
    },
    {
      key: 'entity_type',
      label: 'Target',
      render: (row) => (
        <span className="text-xs font-mono text-brand-text-muted">
          {formatMachineLabel(row.entity_type)} {row.entity_id ? `#${row.entity_id}` : ''}
        </span>
      ),
    },
    {
      key: 'user',
      label: 'Administrator',
      render: (row) => (
        <div>
          <div className="text-sm font-medium text-brand-text">{row.user_name || 'System Admin'}</div>
          <div className="text-xs text-brand-text-muted">{row.user_email || '-'}</div>
        </div>
      ),
    },
    {
      key: 'created_at',
      label: 'Time',
      render: (row) => (
        <span className="text-xs text-brand-text-muted whitespace-nowrap" title={formatDateTime(row.created_at)}>
          {formatRelativeTime(row.created_at, 'Recently')}
        </span>
      ),
    },
  ]

  return (
    <div className="space-y-6">
      {/* 1. Page Header with Timestamp and Refresh */}
      <PageHeader
        title="System Administration"
        description="Comprehensive technical operational health, verified dependency connectivity, background processing, and administrative controls."
        actions={
          <div className="flex items-center gap-3">
            {systemHealth.checked_at && (
              <span className="text-xs text-brand-text-muted flex items-center gap-1">
                <Clock className="h-3.5 w-3.5" />
                Updated {formatRelativeTime(systemHealth.checked_at, 'just now')}
              </span>
            )}
            <Button variant="outline" icon={RefreshCw} onClick={loadOverview} loading={loading}>
              Refresh
            </Button>
          </div>
        }
      />

      <InlineAlert type="error" onDismiss={() => setError('')}>
        {error}
      </InlineAlert>

      {/* 2. Key Health Indicator KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          title="System Health"
          value={systemHealth.status_label || formatStatus(healthStatus)}
          subtitle={`${formatCount(systemHealth.healthy_checks || systemHealth.ready_checks || 0)} of ${formatCount(systemHealth.total_checks || 0)} dependencies healthy`}
          icon={Activity}
          color={healthKpiColor}
        />
        <KpiCard
          title="Background Processing"
          value={workerStatus === 'healthy' ? `${formatCount(workerCount)} Worker(s)` : formatStatus(workerStatus)}
          subtitle={
            schedulerStatus === 'healthy'
              ? `Beat scheduler active (${background.scheduler?.task_count || 0} tasks)`
              : 'Beat scheduler inactive'
          }
          icon={ServerCog}
          color={backgroundKpiColor}
        />
        <KpiCard
          title="Database Backups"
          value={latestBackup ? formatStatus(latestBackup.status) : 'No Backups'}
          subtitle={
            latestBackup
              ? `${formatBytes(latestBackup.size_bytes)} • ${formatRelativeTime(latestBackup.created_at, 'recently')}`
              : 'Scheduled daily backup active'
          }
          icon={Database}
          color={backupKpiColor}
        />
        <KpiCard
          title="AI Providers"
          value={`${formatCount(configuredProviders)}/${formatCount(aiProviders.length)} Ready`}
          subtitle={
            configuredProviders > 0
              ? `${providers.ai?.provider_order?.join(', ') || 'Configured'} (no live calls)`
              : 'Needs configuration'
          }
          icon={Bot}
          color={aiKpiColor}
        />
      </div>

      {/* 3. Actionable Warnings / Recent Incidents */}
      <GlassPanel className="p-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            <div>
              <h2 className="section-title">Operational Incidents & Warnings</h2>
              <p className="text-xs text-brand-text-muted">
                Recent unresolved operational events and critical system anomalies.
              </p>
            </div>
          </div>
          <Link
            to={ROUTES.SYSTEM_ADMIN_DIAGNOSTICS}
            className="text-xs font-medium text-brand-primary hover:underline flex items-center gap-1"
          >
            Open System Diagnostics <ArrowRight className="h-3 w-3" />
          </Link>
        </div>

        {recentIncidents.length > 0 ? (
          <DataTable
            columns={incidentColumns}
            data={recentIncidents}
            keyField="id"
            isLoading={loading}
            caption="Recent operational incidents"
            density="compact"
          />
        ) : (
          <EmptyState
            icon={CheckCircle2}
            title="All systems operational"
            description="No recent ERROR or CRITICAL operational events have been recorded."
            className="py-6"
          />
        )}
      </GlassPanel>

      {/* 4. Verified Dependency Health Checks Table */}
      <GlassPanel className="p-5">
        <div className="mb-4">
          <div className="flex items-center gap-2">
            <Server className="h-5 w-5 text-brand-primary" />
            <h2 className="section-title">Verified Dependency Health Checks</h2>
          </div>
          <p className="mt-1 text-sm text-brand-text-muted">
            Live bounded connectivity probes for core infrastructure and storage. Probed with safe, bounded timeouts.
          </p>
        </div>
        <DataTable
          columns={dependencyColumns}
          data={dependencyRows}
          keyField="key"
          isLoading={loading}
          emptyMessage="No dependency health checks available."
          caption="Verified dependency health checks"
          density="compact"
        />
      </GlassPanel>

      {/* 5. Background Processing & AI Configuration Summaries */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Celery Background Processing */}
        <GlassPanel className="p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-brand-border/60 pb-3">
            <div className="flex items-center gap-2">
              <ServerCog className="h-5 w-5 text-brand-primary" />
              <div>
                <h3 className="font-semibold text-brand-text">Celery Background Processing</h3>
                <p className="text-xs text-brand-text-muted">Asynchronous tasks and scheduled jobs</p>
              </div>
            </div>
            {healthBadge(workerStatus, workerStatus === 'healthy' ? 'Active' : formatStatus(workerStatus))}
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="p-3 rounded-lg bg-surface-muted/50 border border-brand-border/40">
              <div className="text-xs text-brand-text-muted">Active Workers</div>
              <div className="text-lg font-bold text-brand-text mt-0.5">
                {background.workers?.count || 0}
              </div>
              <div className="text-xs text-brand-text-muted truncate mt-1">
                {background.workers?.active_workers?.join(', ') || 'None reporting'}
              </div>
            </div>
            <div className="p-3 rounded-lg bg-surface-muted/50 border border-brand-border/40">
              <div className="text-xs text-brand-text-muted">Beat Scheduler</div>
              <div className="text-lg font-bold text-brand-text mt-0.5">
                {background.scheduler?.task_count || 0} Tasks
              </div>
              <div className="text-xs text-brand-text-muted mt-1">
                {background.scheduler?.status_label || formatStatus(schedulerStatus)}
              </div>
            </div>
          </div>

          {/* Registered Periodic Tasks List */}
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-brand-text-muted mb-2">
              Configured Periodic Tasks
            </div>
            <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
              {background.scheduler?.tasks && background.scheduler.tasks.length > 0 ? (
                background.scheduler.tasks.map((task) => (
                  <div
                    key={task.name}
                    className="flex items-center justify-between p-2 rounded bg-surface/40 text-xs border border-brand-border/20"
                  >
                    <span className="font-medium text-brand-text">{formatMachineLabel(task.name)}</span>
                    <span className="font-mono text-brand-text-muted">{task.schedule}</span>
                  </div>
                ))
              ) : (
                <div className="text-xs text-brand-text-muted italic py-2">No periodic tasks registered.</div>
              )}
            </div>
          </div>
        </GlassPanel>

        {/* AI & Integration Readiness */}
        <GlassPanel className="p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-brand-border/60 pb-3">
            <div className="flex items-center gap-2">
              <Bot className="h-5 w-5 text-brand-primary" />
              <div>
                <h3 className="font-semibold text-brand-text">AI & Integration Configuration</h3>
                <p className="text-xs text-brand-text-muted">Model definitions and failover hierarchy</p>
              </div>
            </div>
            {healthBadge(configuredProviders > 0 ? 'healthy' : 'degraded', `${configuredProviders} Configured`)}
          </div>

          <div className="p-3 rounded-lg bg-surface-muted/50 border border-brand-border/40 text-xs text-brand-text-muted">
            <span className="font-medium text-brand-text">Safe Inspection Notice: </span>
            {providers.ai?.probe_note ||
              'Configuration presence verified without exposing credentials; live AI prompts are never issued on dashboard load.'}
          </div>

          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-brand-text-muted mb-2">
              Configured AI Providers
            </div>
            <div className="space-y-2">
              {aiProviders.map((prov) => (
                <div
                  key={prov.name}
                  className="flex items-center justify-between p-2.5 rounded bg-surface/40 border border-brand-border/30"
                >
                  <div>
                    <div className="font-medium text-sm text-brand-text">{formatMachineLabel(prov.name)}</div>
                    <div className="font-mono text-xs text-brand-text-muted">{prov.model || 'Default'}</div>
                  </div>
                  {prov.configured ? (
                    <span className={badgeClassForTone('success')}>Ready</span>
                  ) : (
                    <span className={badgeClassForTone('neutral')}>Not Configured</span>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="pt-2 border-t border-brand-border/40 flex items-center justify-between text-xs text-brand-text-muted">
            <span>Failover Order:</span>
            <span className="font-medium text-brand-text font-mono">
              {providers.ai?.provider_order?.join(' → ') || 'None'}
            </span>
          </div>
        </GlassPanel>
      </div>

      {/* 6. Recent Administrative Activity & Database Backups */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Admin Audit Trail Preview (2 cols) */}
        <div className="lg:col-span-2">
          <GlassPanel className="p-5 h-full flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5 text-brand-primary" />
                  <div>
                    <h2 className="section-title">Privileged Administrative Activity</h2>
                    <p className="text-xs text-brand-text-muted">
                      Recent technical configuration, role change, and security-boundary audit logs.
                    </p>
                  </div>
                </div>
                <Link
                  to={ROUTES.AUDIT}
                  className="text-xs font-medium text-brand-primary hover:underline flex items-center gap-1"
                >
                  Full Audit Log <ArrowRight className="h-3 w-3" />
                </Link>
              </div>

              {recentAdminActivity.length > 0 ? (
                <DataTable
                  columns={auditColumns}
                  data={recentAdminActivity}
                  keyField="id"
                  isLoading={loading}
                  caption="Recent administrative activity"
                  density="compact"
                />
              ) : (
                <EmptyState
                  icon={ShieldCheck}
                  title="No recent administrative events"
                  description="No privileged system administration actions recorded recently."
                  className="py-6"
                />
              )}
            </div>
          </GlassPanel>
        </div>

        {/* Database Backups Snapshot & Quick Nav (1 col) */}
        <div className="space-y-6">
          <GlassPanel className="p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <HardDrive className="h-5 w-5 text-brand-primary" />
                <h3 className="font-semibold text-brand-text">Database Backups</h3>
              </div>
              {latestBackup && healthBadge(latestBackup.status)}
            </div>

            {latestBackup ? (
              <div className="space-y-2 text-xs">
                <div className="p-3 rounded-lg bg-surface-muted/50 border border-brand-border/40">
                  <div className="text-brand-text-muted">Latest Backup File:</div>
                  <div className="font-mono font-medium text-brand-text truncate mt-0.5" title={latestBackup.filename}>
                    {latestBackup.filename}
                  </div>
                  <div className="flex justify-between mt-2 pt-2 border-t border-brand-border/30 text-brand-text-muted">
                    <span>Size: {formatBytes(latestBackup.size_bytes)}</span>
                    <span>{formatRelativeTime(latestBackup.created_at, 'Recently')}</span>
                  </div>
                </div>
                <div className="flex justify-between text-brand-text-muted px-1">
                  <span>Completed: {databaseBackup.completed_count || 0}</span>
                  <span>Failed: {databaseBackup.failed_count || 0}</span>
                </div>
              </div>
            ) : (
              <div className="p-4 rounded-lg bg-surface-muted/40 text-center text-xs text-brand-text-muted">
                No database backups recorded yet. Automatic daily backups are scheduled.
              </div>
            )}
          </GlassPanel>

          {/* Quick Administration Navigation Links */}
          <GlassPanel className="p-5 space-y-4">
            <h3 className="font-semibold text-brand-text">System Admin Navigation</h3>
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-brand-text-muted mb-2">
                System Administration
              </div>
              <div className="grid grid-cols-1 gap-2">
                <Link
                  className="btn-outline flex items-center justify-between px-3 py-2 text-xs"
                  to={ROUTES.SYSTEM_ADMIN_TECHNICAL_SETTINGS}
                >
                  <span className="flex items-center gap-2">
                    <SlidersHorizontal className="h-4 w-4 text-brand-primary" />
                    Technical Settings
                  </span>
                  <ArrowRight className="h-3 w-3 text-brand-text-muted" />
                </Link>
                <Link
                  className="btn-outline flex items-center justify-between px-3 py-2 text-xs"
                  to={ROUTES.USERS}
                >
                  <span className="flex items-center gap-2">
                    <Users className="h-4 w-4 text-blue-500" />
                    User Management
                  </span>
                  <ArrowRight className="h-3 w-3 text-brand-text-muted" />
                </Link>
              </div>
            </div>

            <div className="pt-2 border-t border-brand-border/40">
              <div className="text-xs font-semibold uppercase tracking-wider text-brand-text-muted mb-2">
                System Operations
              </div>
              <div className="grid grid-cols-1 gap-2">
                <Link
                  className="btn-outline flex items-center justify-between px-3 py-2 text-xs"
                  to={ROUTES.SYSTEM_ADMIN_DIAGNOSTICS}
                >
                  <span className="flex items-center gap-2">
                    <Activity className="h-4 w-4 text-amber-500" />
                    System Diagnostics
                  </span>
                  <ArrowRight className="h-3 w-3 text-brand-text-muted" />
                </Link>
                <Link
                  className="btn-outline flex items-center justify-between px-3 py-2 text-xs"
                  to={ROUTES.AUDIT}
                >
                  <span className="flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-emerald-500" />
                    Audit Trail
                  </span>
                  <ArrowRight className="h-3 w-3 text-brand-text-muted" />
                </Link>
              </div>
            </div>
          </GlassPanel>
        </div>
      </div>
    </div>
  )
}
