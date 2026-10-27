import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  AlertTriangle,
  Archive,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  FileCheck,
  FileClock,
  HardHat,
  Info,
  Lock,
  Sparkles,
} from 'lucide-react'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatPercent(value) {
  return `${Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })}%`
}

const STAGE_CONFIG = {
  punchlist_unassessed: { label: 'Punchlist Not Assessed', shortLabel: 'Not Assessed', icon: Info, color: 'bg-slate-400', card: 'border-brand-border bg-brand-surface', text: 'text-brand-text-muted', ring: 'ring-slate-400', description: 'Infrastructure project has no recorded punchlist assessment' },
  physically_complete: {
    label: 'Physically Complete',
    shortLabel: '100% Physical',
    icon: HardHat,
    color: 'bg-blue-500',
    card: 'border-blue-200 bg-blue-50/50 hover:bg-blue-50 dark:border-blue-900/50 dark:bg-blue-950/20',
    text: 'text-blue-700 dark:text-blue-300',
    ring: 'ring-blue-500',
    description: 'Projects with 100% physical accomplishment or in completion phase',
  },
  punchlist_cleared: {
    label: 'Punchlist Cleared',
    shortLabel: 'Punchlist Cleared',
    icon: ClipboardCheck,
    color: 'bg-yellow-500',
    card: 'border-yellow-200 bg-yellow-50/50 hover:bg-yellow-50 dark:border-yellow-900/50 dark:bg-yellow-950/20',
    text: 'text-yellow-800 dark:text-yellow-300',
    ring: 'ring-yellow-500',
    description: 'Civil works defects 100% rectified or non-infra exempt',
  },
  docs_ready: {
    label: 'Closeout Docs Ready',
    shortLabel: 'Docs Ready',
    icon: FileCheck,
    color: 'bg-emerald-500',
    card: 'border-emerald-200 bg-emerald-50/50 hover:bg-emerald-50 dark:border-emerald-900/50 dark:bg-emerald-950/20',
    text: 'text-emerald-700 dark:text-emerald-300',
    ring: 'ring-emerald-500',
    description: 'All applicable matrix documents accepted under current completion rules',
  },
  docs_pending: {
    label: 'Closeout Docs Pending',
    shortLabel: 'Docs Pending',
    icon: FileClock,
    color: 'bg-amber-500',
    card: 'border-amber-200 bg-amber-50/50 hover:bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20',
    text: 'text-amber-700 dark:text-amber-300',
    ring: 'ring-amber-500',
    description: 'Completion documents in draft, under verification, or unconfirmed',
  },
  vault_ready: {
    label: 'Vault Locked / Ready',
    shortLabel: 'Vault Locked',
    icon: Lock,
    color: 'bg-purple-500',
    card: 'border-purple-200 bg-purple-50/50 hover:bg-purple-50 dark:border-purple-900/50 dark:bg-purple-950/20',
    text: 'text-purple-700 dark:text-purple-300',
    ring: 'ring-purple-500',
    description: 'Project document vault finalized and locked for provincial closeout',
  },
  final_approved: {
    label: 'Final Closeout Approved',
    shortLabel: 'Closeout Approved',
    icon: CheckCircle2,
    color: 'bg-emerald-600',
    card: 'border-emerald-300 bg-emerald-100/50 hover:bg-emerald-100 dark:border-emerald-800 dark:bg-emerald-950/40',
    text: 'text-emerald-800 dark:text-emerald-200',
    ring: 'ring-emerald-600',
    description: 'Provincial Admin signed-off final closeout milestone',
  },
}

export default function CloseoutReadinessChart({
  closeoutData = {},
  selectedStage = null,
  onStageSelect,
  emptyMessage = 'No closeout readiness telemetry available for current filter scope.',
  clientScopeOnly = false,
}) {
  const {
    total_projects = 0,
    physically_complete_count = 0,
    punchlist_cleared_count = 0,
    docs_ready_count = 0,
    docs_pending_count = 0,
    vault_ready_count = 0,
    final_approved_count = 0,
    readiness_rate = 0.0,
    stages = [],
    projects = [],
  } = closeoutData

  const handleStageClick = (stageKey, event) => {
    if (onStageSelect) {
      onStageSelect(selectedStage === stageKey ? null : stageKey, event)
    }
  }

  const visibleStages = useMemo(() => {
    if (!clientScopeOnly) return stages
    const clientAllowed = ['physically_complete', 'docs_ready', 'docs_pending', 'final_approved']
    return stages.filter((s) => clientAllowed.includes(s.key))
  }, [stages, clientScopeOnly])

  const displayProjects = useMemo(() => {
    if (!selectedStage) return projects
    const stageObj = stages.find((s) => s.key === selectedStage)
    if (stageObj?.project_ids) {
      return projects.filter((p) => stageObj.project_ids.includes(p.id ?? p.project_id))
    }
    return projects
  }, [projects, selectedStage, stages])

  if (!total_projects && (!stages || stages.length === 0)) {
    return (
      <div className="py-8 text-center text-sm text-brand-text-muted">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header Info & Metrics */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-1.5 text-brand-text-muted">
          <Info className="h-3.5 w-3.5 shrink-0" />
          <span>
            {clientScopeOnly
              ? '100% physically completed projects and completion matrix deliverables (Final SWA, Final Inspection Report / IAR, Certificate of Final Acceptance, Final SORD, and Proof of Fund Return where applicable)'
              : 'Physical accomplishment, civil works punchlist rectification, completion matrix documents, and vault lock verification'}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3 font-semibold text-brand-text">
          <span>
            Portfolio Total: <strong className="tabular-nums text-brand-text">{formatNumber(total_projects)}</strong>
          </span>
          <span className="text-slate-300 dark:text-slate-700">•</span>
          <span>
            100% Physical: <strong className="tabular-nums text-blue-600 dark:text-blue-400">{formatNumber(physically_complete_count)}</strong>
          </span>
          <span className="text-slate-300 dark:text-slate-700">•</span>
          <span>
            Docs Ready: <strong className="tabular-nums text-emerald-700 dark:text-emerald-400">{formatNumber(docs_ready_count)}</strong>
          </span>
          <span className="text-slate-300 dark:text-slate-700">•</span>
          <span>
            Docs Readiness Rate: <strong className="tabular-nums text-emerald-700 dark:text-emerald-400">{formatPercent(readiness_rate)}</strong>
          </span>
        </div>
      </div>

      {/* Primary KPI Grid */}
      <div className={`grid grid-cols-2 gap-3 sm:grid-cols-3 ${clientScopeOnly ? 'lg:grid-cols-4' : 'lg:grid-cols-6'}`}>
        {visibleStages.map((st) => {
          const cfg = STAGE_CONFIG[st.key] || {
            label: st.label,
            shortLabel: st.label,
            icon: CheckCircle2,
            card: 'border-brand-border bg-brand-surface',
            text: 'text-brand-text',
            color: 'bg-brand-primary',
            ring: 'ring-brand-primary',
          }
          const IconComponent = cfg.icon
          const isSelected = selectedStage === st.key
          const count = st.count || 0

          return (
            <button
              key={st.key}
              type="button"
              onClick={(event) => handleStageClick(st.key, event)}
              className={`flex flex-col justify-between rounded-xl border p-3.5 text-left transition-all relative ${cfg.card} ${
                isSelected ? `ring-2 ${cfg.ring} shadow-md scale-[1.02]` : 'hover:shadow-sm'
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className={`rounded-lg p-1.5 bg-white/80 dark:bg-black/20 ${cfg.text}`}>
                    <IconComponent className="h-4 w-4" />
                  </span>
                  <span className="text-xs font-semibold tabular-nums text-brand-text-muted">
                    {formatPercent(st.percentage)}
                  </span>
                </div>
                <div className="text-xs font-medium text-brand-text-muted">{cfg.shortLabel}</div>
                <div className="mt-1 text-2xl font-bold tabular-nums text-brand-text">
                  {formatNumber(count)}
                </div>
              </div>
              <div className="mt-3 flex items-center justify-between text-[11px] font-medium text-brand-text-muted">
                <span>{st.key === 'physically_complete' ? 'of portfolio' : 'of complete'}</span>
                <span className="text-brand-primary text-[10px] uppercase tracking-wider font-semibold">
                  {isSelected ? 'Active' : 'Filter'}
                </span>
              </div>
            </button>
          )
        })}
      </div>

      {/* Pipeline Stage Bar */}
      <div className="rounded-xl border border-brand-border bg-brand-surface p-4 shadow-xs">
        <div className="mb-2 flex items-center justify-between text-xs">
          <span className="font-semibold text-brand-text">Closeout Milestone Progression ({formatNumber(physically_complete_count)} Physically Complete Projects)</span>
          <span className="text-brand-text-muted">
            {formatNumber(docs_ready_count)} of {formatNumber(physically_complete_count)} verified for closeout ({formatPercent(readiness_rate)})
          </span>
        </div>
        <div className="flex h-3 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
          <div
            className="bg-emerald-500 transition-all"
            style={{ width: `${readiness_rate}%` }}
            title={`Docs Ready: ${docs_ready_count} projects (${formatPercent(readiness_rate)})`}
          />
          <div
            className="bg-amber-400 transition-all"
            style={{ width: `${100 - readiness_rate}%` }}
            title={`Docs Pending: ${docs_pending_count} projects (${formatPercent(100 - readiness_rate)})`}
          />
        </div>
        <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 text-xs">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 text-emerald-700 dark:text-emerald-400 font-medium">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
              Docs Ready ({docs_ready_count})
            </span>
            <span className="flex items-center gap-1.5 text-amber-700 dark:text-amber-400 font-medium">
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
              Docs Pending ({docs_pending_count})
            </span>
          </div>
          <div className="flex items-center gap-3 text-brand-text-muted">
            {clientScopeOnly ? (
              <span>Approved: <strong>{final_approved_count}/{physically_complete_count} Approved</strong></span>
            ) : (
              <>
                <span>Punchlist: <strong>{punchlist_cleared_count}/{physically_complete_count} Cleared</strong></span>
                <span>•</span>
                <span>Vault: <strong>{vault_ready_count}/{physically_complete_count} Locked</strong></span>
                <span>•</span>
                <span>Approved: <strong>{final_approved_count}/{physically_complete_count} Approved</strong></span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Completion Projects Table / Detail Summary — Rendered only upon category selection when clientScopeOnly */}
      {(Boolean(selectedStage) || !clientScopeOnly) && displayProjects && (
        <div className="rounded-xl border border-brand-border bg-brand-surface overflow-hidden shadow-xs">
          <div className="px-4 py-3 border-b border-brand-border flex flex-wrap items-center justify-between gap-2">
            <div>
              <h4 className="text-sm font-semibold text-brand-text">Completion Documents & Closeout</h4>
              <p className="text-xs text-brand-text-muted">
                {clientScopeOnly
                  ? 'COMET internal completion matrix deliverables for 100% physically accomplished projects (Final SWA, Final Inspection Report / IAR, Certificate of Final Acceptance, Final SORD, and Proof of Fund Return where applicable)'
                  : 'Granular status of civil works punchlists, completion documents, vault lock readiness, and provincial approvals'}
              </p>
            </div>
            {selectedStage && (
              <button
                type="button"
                onClick={() => handleStageClick(selectedStage)}
                className="text-xs font-semibold text-brand-primary hover:underline"
              >
                Clear stage filter ({STAGE_CONFIG[selectedStage]?.shortLabel || selectedStage})
              </button>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-brand-text">
              <thead className="bg-slate-50 dark:bg-slate-800/60 text-brand-text-muted font-medium border-b border-brand-border uppercase tracking-wider text-[11px]">
                <tr>
                  <th className="px-3.5 py-2.5">Project</th>
                  <th className="px-3 py-2.5">LGU</th>
                  <th className="px-3 py-2.5">Type</th>
                  <th className="px-3 py-2.5 text-center">Progress</th>
                  {!clientScopeOnly && <th className="px-3 py-2.5 text-center">Punchlist</th>}
                  <th className="px-3 py-2.5 text-center">Closeout Docs</th>
                  {!clientScopeOnly && <th className="px-3 py-2.5 text-center">Vault Ready</th>}
                  <th className="px-3 py-2.5 text-center">Closeout Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border">
                {displayProjects.length === 0 ? (
                  <tr>
                    <td colSpan={clientScopeOnly ? 6 : 8} className="py-6 text-center text-xs text-brand-text-muted">
                      No projects currently at milestone "{STAGE_CONFIG[selectedStage]?.label || selectedStage}".
                    </td>
                  </tr>
                ) : (
                  displayProjects.map((proj) => {
                  const isInfra = proj.effective_project_kind === 'infrastructure'
                  const punchlistLabel = !isInfra
                    ? 'Exempt (Non-Infra)'
                    : proj.punchlist_total !== null && proj.punchlist_total !== undefined
                      ? `${proj.punchlist_resolved || 0}/${proj.punchlist_total} Resolved`
                      : 'Not assessed'
                  const isDocsReady = proj.docs_pending === 0

                  return (
                    <tr key={proj.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30 transition-colors">
                      <td className="px-3.5 py-2.5 max-w-[15rem]">
                        <Link
                          to={`/dashboard/projects/${proj.id}`}
                          className="font-semibold text-brand-text truncate hover:text-brand-primary block"
                          title={proj.project_name}
                        >
                          {proj.project_name}
                        </Link>
                        <div className="text-[11px] text-brand-text-muted font-mono">{proj.project_code || '—'}</div>
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap text-brand-text-muted">
                        {proj.lgu_name}
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium ${
                          isInfra ? 'bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300' : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'
                        }`}>
                          {isInfra ? 'Infra' : 'Non-Infra'}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-center whitespace-nowrap">
                        <span className="inline-flex items-center rounded-full bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 px-2 py-0.5 text-xs font-semibold">
                          100%
                        </span>
                      </td>
                      {!clientScopeOnly && (
                        <td className="px-3 py-2.5 text-center whitespace-nowrap">
                          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                            ['unresolved', 'unassessed'].includes(proj.punchlist_status)
                              ? 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300'
                              : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'
                          }`}>
                            {punchlistLabel}
                          </span>
                        </td>
                      )}
                      <td className="px-3 py-2.5 text-center whitespace-nowrap">
                        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
                          isDocsReady
                            ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'
                            : 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'
                        }`}>
                          {isDocsReady ? 'Accepted (All)' : `${proj.docs_pending} Pending`}
                        </span>
                      </td>
                      {!clientScopeOnly && (
                        <td className="px-3 py-2.5 text-center whitespace-nowrap">
                          {proj.is_vault_ready ? (
                            <span className="inline-flex items-center gap-1 text-purple-700 dark:text-purple-300 font-semibold text-xs">
                              <Lock className="h-3 w-3" /> Locked
                            </span>
                          ) : (
                            <span className="text-slate-400 text-xs">Unlocked</span>
                          )}
                        </td>
                      )}
                      <td className="px-3 py-2.5 text-center whitespace-nowrap">
                        <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold ${
                          proj.is_final_approved
                            ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200'
                            : isDocsReady
                              ? 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200'
                              : 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200'
                        }`}>
                          {proj.closeout_stage_label}
                        </span>
                      </td>
                    </tr>
                  )
                }))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
