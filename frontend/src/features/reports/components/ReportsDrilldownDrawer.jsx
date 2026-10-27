import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileCheck,
  FileText,
  Layers,
  Search,
  ShieldAlert,
  X,
} from 'lucide-react'
import { listProjectRequirements } from '../../projects/api/projectApi'
import { formatCurrency } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'

function formatPercent(value) {
  if (value === 'Not rated') return 'Not rated'
  if (value === null || value === undefined) return 'Not reported'
  return `${Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })}%`
}

function statusBadge(status, label) {
  const norm = (status || '').toLowerCase()
  const text = label || norm.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  return <span className={badgeClassForStatus(norm)}>{text}</span>
}

function filterActiveRequirements(list) {
  if (!Array.isArray(list)) return []
  return list.filter((r) => r && r.is_active !== false && r.is_active !== 0)
}

function ReportsDrilldownDrawerContent({
  onClose,
  title = 'Contributing Projects',
  subtitle = '',
  projects = [],
  returnFocusRef = null,
}) {
  const [selectedProject, setSelectedProject] = useState(null)
  const [requirements, setRequirements] = useState([])
  const [loadingReqs, setLoadingReqs] = useState(false)
  const [reqError, setReqError] = useState(null)
  const [projectSearch, setProjectSearch] = useState('')
  const drawerRef = useRef(null)
  const triggerElementRef = useRef(typeof document !== 'undefined' ? document.activeElement : null)

  const handleSelectProject = (proj) => {
    setSelectedProject(proj)
    const existing = filterActiveRequirements(proj?.requirements)
    setRequirements(existing)
    setReqError(null)
    setLoadingReqs(existing.length === 0)
  }

  const handleBackToProjects = () => {
    setSelectedProject(null)
    setRequirements([])
    setReqError(null)
    setLoadingReqs(false)
  }

  // Accessible keyboard ESC handling, focus containment, and focus restoration
  useEffect(() => {
    const returnTarget = returnFocusRef?.current || returnFocusRef || triggerElementRef.current

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (selectedProject) {
          handleBackToProjects()
        } else if (onClose) {
          onClose()
        }
        return
      }

      if (e.key === 'Tab') {
        const modalElement = drawerRef.current
        if (!modalElement) return
        const focusableElements = Array.from(
          modalElement.querySelectorAll(
            'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
          )
        ).filter((el) => el.offsetParent !== null || el.getClientRects().length > 0)

        if (!focusableElements.length) {
          e.preventDefault()
          return
        }
        const firstElement = focusableElements[0]
        const lastElement = focusableElements[focusableElements.length - 1]

        if (e.shiftKey) {
          if (document.activeElement === firstElement || document.activeElement === modalElement) {
            e.preventDefault()
            lastElement.focus()
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault()
            firstElement.focus()
          }
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    drawerRef.current?.focus()

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      if (returnTarget && typeof returnTarget.focus === 'function' && returnTarget !== document?.body) {
        try {
          returnTarget.focus()
        } catch {
          // ignore
        }
      }
    }
  }, [selectedProject, onClose, returnFocusRef])

  // Load active requirements for selected project
  useEffect(() => {
    if (!selectedProject) return
    const existing = filterActiveRequirements(selectedProject.requirements)
    if (existing.length > 0) {
      return
    }

    let active = true
    const projectId = selectedProject.project_id || selectedProject.id

    listProjectRequirements(projectId)
      .then((res) => {
        if (!active) return
        const reqList = res?.data || res?.requirements || res || []
        setRequirements(filterActiveRequirements(reqList))
      })
      .catch((err) => {
        if (!active) return
        setReqError(err?.message || 'Failed to load project requirements.')
      })
      .finally(() => {
        if (active) setLoadingReqs(false)
      })

    return () => {
      active = false
    }
  }, [selectedProject])

  const filteredProjects = useMemo(() => {
    const q = projectSearch.trim().toLowerCase()
    if (!q) return projects
    return projects.filter((p) => {
      const name = (p.project_name || '').toLowerCase()
      const code = (p.project_code || '').toLowerCase()
      const lgu = (p.lgu_name || '').toLowerCase()
      const prog = (p.program_name || '').toLowerCase()
      return name.includes(q) || code.includes(q) || lgu.includes(q) || prog.includes(q)
    })
  }, [projects, projectSearch])

  return (
    <div
      className="fixed inset-0 z-50 overflow-hidden bg-slate-900/60 backdrop-blur-xs transition-opacity"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={(e) => {
        if (e.target === e.currentTarget && onClose) onClose()
      }}
    >
      <div
        ref={drawerRef}
        tabIndex={-1}
        className="fixed inset-y-0 right-0 flex max-w-full pl-0 sm:pl-10 outline-none"
      >
        <div className="w-screen max-w-2xl lg:max-w-3xl flex flex-col bg-brand-surface-solid dark:bg-slate-900 shadow-2xl border-l border-brand-border">
          {/* ── DRAWER HEADER & BREADCRUMBS ── */}
          <div className="border-b border-brand-border/80 px-5 py-4 bg-slate-50/50 dark:bg-slate-800/40">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                {selectedProject && (
                  <button
                    type="button"
                    onClick={handleBackToProjects}
                    className="inline-flex items-center gap-1 rounded-md p-1.5 text-xs font-semibold text-brand-primary hover:bg-brand-primary/10 transition-colors"
                    title="Back to project list"
                    aria-label="Back to project list"
                  >
                    <ArrowLeft className="h-4 w-4" />
                    <span>Projects</span>
                  </button>
                )}
                <div className="min-w-0">
                  <h2 className="text-base font-bold text-brand-text truncate">
                    {selectedProject ? selectedProject.project_name : title}
                  </h2>
                  <p className="text-xs text-brand-text-muted truncate">
                    {selectedProject
                      ? `Complete documentary requirements checklist (${selectedProject.project_code || 'No code'})`
                      : subtitle || `${projects.length} contributing ${projects.length === 1 ? 'project' : 'projects'}`}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={onClose}
                className="rounded-lg p-1.5 text-brand-text-muted hover:bg-slate-200 hover:text-brand-text dark:hover:bg-slate-700 transition-colors"
                title="Close drawer (Esc)"
                aria-label="Close drawer"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* ── DRAWER BODY ── */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {/* LEVEL 1: CONTRIBUTING PROJECTS LIST */}
            {!selectedProject && (
              <div className="space-y-3">
                {/* Search within drawer */}
                {projects.length > 3 && (
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-brand-text-muted" />
                    <input
                      type="search"
                      value={projectSearch}
                      onChange={(e) => setProjectSearch(e.target.value)}
                      placeholder="Filter projects by title, code, or program…"
                      className="input-field w-full pl-9 text-xs"
                      aria-label="Filter projects in drawer"
                    />
                  </div>
                )}

                {filteredProjects.length === 0 ? (
                  <div className="py-12 text-center text-sm text-brand-text-muted">
                    No contributing projects found for this selection.
                  </div>
                ) : (
                  <div className="divide-y divide-brand-border/60 rounded-xl border border-brand-border bg-brand-surface overflow-hidden shadow-xs">
                    {filteredProjects.map((proj) => {
                      const pId = proj.project_id || proj.id
                      const openDocs = proj.document_open_count ?? proj.documentary_summary?.open ?? 0
                      const compliantDocs = proj.compliant ?? proj.documentary_summary?.compliant ?? 0
                      const applicableDocs = proj.document_applicable_count ?? proj.documentary_summary?.applicable ?? 0
                      const rate = proj.document_compliance_rate ?? (applicableDocs > 0 ? (compliantDocs / applicableDocs) * 100 : 'Not rated')

                      return (
                        <div
                          key={pId}
                          className="p-4 hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-colors"
                        >
                          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                            <div className="space-y-1 min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <button
                                  type="button"
                                  onClick={() => handleSelectProject(proj)}
                                  className="font-semibold text-sm text-brand-text truncate hover:text-brand-primary text-left cursor-pointer"
                                >
                                  {proj.project_name}
                                </button>
                                {statusBadge(proj.overall_status, proj.overall_status_label)}
                              </div>
                              <div className="flex flex-wrap items-center gap-2 text-xs text-brand-text-muted font-mono">
                                <span>{proj.project_code || '—'}</span>
                                {proj.lgu_name && (
                                  <>
                                    <span>•</span>
                                    <span>{proj.lgu_name}</span>
                                  </>
                                )}
                                {proj.program_name && (
                                  <>
                                    <span>•</span>
                                    <span>{proj.program_name}</span>
                                  </>
                                )}
                              </div>
                              <div className="flex flex-wrap items-center gap-3 pt-1 text-xs">
                                <span>
                                  Accomplishment:{' '}
                                  <strong className="text-brand-text font-mono">
                                    {formatPercent(proj.physical_completion_pct || 0)}
                                  </strong>
                                </span>
                                {proj.budget_amount != null && (
                                  <>
                                    <span className="text-slate-300 dark:text-slate-700">•</span>
                                    <span>
                                      Allocation:{' '}
                                      <strong className="text-brand-text font-mono">
                                        {formatCurrency(proj.budget_amount)}
                                      </strong>
                                    </span>
                                  </>
                                )}
                                <span className="text-slate-300 dark:text-slate-700">•</span>
                                <span>
                                  Compliance:{' '}
                                  <strong className="text-brand-text font-mono">
                                    {formatPercent(rate)}
                                  </strong>
                                </span>
                              </div>
                            </div>

                            <div className="flex items-center gap-2 shrink-0 self-end sm:self-start">
                              <button
                                type="button"
                                onClick={() => handleSelectProject(proj)}
                                className="inline-flex items-center gap-1.5 rounded-lg border border-brand-border bg-brand-surface-solid px-3 py-1.5 text-xs font-semibold text-brand-primary hover:bg-brand-primary/10 transition-colors shadow-2xs"
                              >
                                <FileCheck className="h-3.5 w-3.5" />
                                <span>Checklist</span>
                                {openDocs > 0 && (
                                  <span className="rounded-full bg-amber-100 px-1.5 py-0.2 text-[10px] font-bold text-amber-800 dark:bg-amber-950 dark:text-amber-200">
                                    {openDocs} open
                                  </span>
                                )}
                              </button>

                              <Link
                                to={`/dashboard/projects/${pId}`}
                                className="inline-flex items-center gap-1 rounded-lg border border-brand-border/60 p-1.5 text-xs text-brand-text-muted hover:text-brand-primary hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                                title="Open full project record"
                                aria-label={`Open project record for ${proj.project_name}`}
                              >
                                <ExternalLink className="h-4 w-4" />
                              </Link>
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )}

            {/* LEVEL 2: COMPLETE REQUIREMENTS CHECKLIST FOR SELECTED PROJECT */}
            {selectedProject && (
              <div className="space-y-4">
                {/* Project Header Banner */}
                <div className="rounded-xl border border-brand-border bg-brand-surface p-4 shadow-xs">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold text-brand-primary">
                          {selectedProject.project_code || 'NO-CODE'}
                        </span>
                        {statusBadge(selectedProject.overall_status, selectedProject.overall_status_label)}
                      </div>
                      <h3 className="text-sm font-bold text-brand-text mt-1">
                        {selectedProject.project_name}
                      </h3>
                      <p className="text-xs text-brand-text-muted">
                        {selectedProject.lgu_name} — {selectedProject.program_name}
                      </p>
                    </div>

                    <Link
                      to={`/dashboard/projects/${selectedProject.project_id || selectedProject.id}`}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-brand-primary px-3 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-brand-primary/90 transition-colors dark:text-slate-950"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                      <span>Open Project Record</span>
                    </Link>
                  </div>
                </div>

                {/* Requirements Table */}
                <div className="rounded-xl border border-brand-border bg-brand-surface overflow-hidden shadow-xs">
                  <div className="px-4 py-3 border-b border-brand-border bg-slate-50/70 dark:bg-slate-800/50 flex items-center justify-between">
                    <span className="text-xs font-semibold text-brand-text uppercase tracking-wider">
                      Documentary Checklist ({requirements.length} Requirements)
                    </span>
                    <span className="text-[11px] text-brand-text-muted">
                      Includes all active, waived & N/A requirements
                    </span>
                  </div>

                  {loadingReqs ? (
                    <div className="py-12 text-center text-xs text-brand-text-muted">
                      Loading complete project requirements…
                    </div>
                  ) : reqError ? (
                    <div className="p-4 text-center text-xs text-rose-600 dark:text-rose-400">
                      {reqError}
                    </div>
                  ) : requirements.length === 0 ? (
                    <div className="py-12 text-center text-xs text-brand-text-muted">
                      No requirements recorded for this project.
                    </div>
                  ) : (
                    <div className="divide-y divide-brand-border/50">
                      {requirements.map((req) => {
                        const isNa = req.applicability === 'not_applicable' || req.compliance_status === 'not_applicable' || req.status === 'not_applicable'
                        const isWaived = req.applicability === 'waived' || req.compliance_status === 'waived' || req.status === 'waived'
                        const compStatus = req.status || req.compliance_status || 'pending'
                        const wfStatus = req.workflow_status || 'draft'
                        const waiverReason = req.waived_reason || req.waiver_justification || req.waiver_reason || req.applicability_reason || req.notes || req.reason
                        const naReason = req.applicability_reason || req.notes || req.reason

                        return (
                          <div key={req.id} className="p-3.5 space-y-2 hover:bg-slate-50/50 dark:hover:bg-slate-800/30 transition-colors">
                            <div className="flex flex-wrap items-start justify-between gap-2">
                              <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="text-xs font-semibold text-brand-text">
                                    {req.requirement_name || req.name}
                                  </span>
                                  {req.requirement_type && (
                                    <span className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.2 text-[10px] text-slate-600 dark:text-slate-400 font-mono">
                                      {req.requirement_type}
                                    </span>
                                  )}
                                  {isNa ? (
                                    <span className="rounded-full bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 px-2 py-0.5 text-[10px] font-semibold">
                                      Not Applicable
                                    </span>
                                  ) : isWaived ? (
                                    <span className="rounded-full bg-purple-50 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300 px-2 py-0.5 text-[10px] font-semibold">
                                      Waived
                                    </span>
                                  ) : (
                                    statusBadge(compStatus)
                                  )}
                                </div>
                              </div>

                              <div className="flex items-center gap-2 shrink-0">
                                <span className="inline-flex items-center rounded-full bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300 px-2 py-0.5 text-[10px] font-medium">
                                  Workflow: {wfStatus.replace(/_/g, ' ')}
                                </span>
                              </div>
                            </div>

                            {/* Justification reasons for Waived or Not Applicable */}
                            {isWaived && waiverReason && (
                              <div className="text-[11px] text-purple-900 dark:text-purple-200 bg-purple-50/60 dark:bg-purple-950/20 border border-purple-200/50 dark:border-purple-800/40 rounded p-2">
                                <strong>Waiver Justification:</strong> {waiverReason}
                              </div>
                            )}

                            {isNa && naReason && (
                              <div className="text-[11px] text-brand-text-muted bg-slate-100/60 dark:bg-slate-800/40 rounded p-2 font-mono">
                                <strong className="text-brand-text">N/A Justification:</strong> {naReason}
                              </div>
                            )}

                            {/* Return reason if returned for revision */}
                            {req.workflow_return_reason && (
                              <div className="text-[11px] text-rose-700 dark:text-rose-400 bg-rose-50/60 dark:bg-rose-950/30 rounded p-2">
                                <strong>Return remarks:</strong> {req.workflow_return_reason}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function ReportsDrilldownDrawer({ isOpen = false, ...props }) {
  if (!isOpen) return null
  return <ReportsDrilldownDrawerContent {...props} />
}
