import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, Clock3, FileText, ShieldCheck } from 'lucide-react'
import { EmptyState, GlassPanel, InlineAlert, KpiCard } from '../../../components'
import { ROUTES } from '../../../config/routes'
import { formatMachineLabel, formatRole } from '../../../lib/formatters'

function formatDate(value) {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString('en-PH', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    })
  } catch {
    return value
  }
}

function StatusPill({ label, tone = 'slate' }) {
  const tones = {
    red: 'status-badge-danger',
    amber: 'status-badge-warning',
    emerald: 'status-badge-success',
    slate: 'status-badge-neutral',
    blue: 'status-badge-info',
  }
  const dots = {
    red: 'bg-red-600 dark:bg-red-300',
    amber: 'bg-amber-600 dark:bg-amber-300',
    emerald: 'bg-emerald-600 dark:bg-emerald-300',
    slate: 'bg-slate-500 dark:bg-slate-300',
    blue: 'bg-blue-600 dark:bg-blue-300',
  }

  return (
    <span className={`status-badge ${tones[tone] || tones.slate}`}>
      <span className={`status-dot ${dots[tone] || dots.slate}`} />
      {label}
    </span>
  )
}

export default function MagicLinkChecklistPage() {
  const { token } = useParams()
  const [payload, setPayload] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let isMounted = true

    async function loadChecklist() {
      setLoading(true)
      setError('')
      try {
        const apiBase = import.meta.env.VITE_API_URL || '/api'
        const response = await fetch(`${apiBase}/magic-links/${token}`)
        const body = await response.json()
        if (!response.ok) {
          throw new Error(body?.message || 'This checklist link is unavailable.')
        }
        if (isMounted) {
          setPayload(body.data || null)
        }
      } catch (loadError) {
        if (isMounted) {
          setError(loadError.message || 'This checklist link is unavailable.')
        }
      } finally {
        if (isMounted) {
          setLoading(false)
        }
      }
    }

    loadChecklist()
    return () => {
      isMounted = false
    }
  }, [token])

  const cards = useMemo(() => {
    const summary = payload?.compliance_summary || {}
    const baseCards = [
      {
        label: 'Outstanding',
        subtitle: 'still required',
        value: summary.outstanding_requirements || 0,
        color: 'red',
        icon: AlertTriangle,
      },
      {
        label: 'Accepted',
        subtitle: 'verified',
        value: summary.compliant_requirements || 0,
        color: 'emerald',
        icon: CheckCircle2,
      },
      {
        label: 'Required',
        subtitle: 'total items',
        value: summary.total_requirements || 0,
        color: 'blue',
        icon: FileText,
      },
    ]

    if (summary.not_applicable_requirements > 0) {
      baseCards.push({
        label: 'Not Applicable',
        subtitle: 'exempted items',
        value: summary.not_applicable_requirements,
        color: 'slate',
        icon: ShieldCheck,
      })
    }

    return baseCards
  }, [payload])

  return (
    <div className="min-h-screen bg-background text-brand-text">
      <header className="border-b border-brand-border bg-brand-surface-solid">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-5 sm:px-6 lg:px-8">
          <div>
            <p className="micro-text">Read-only checklist</p>
            <h1 className="mt-2 font-display text-2xl font-semibold text-brand-text">Requirement checklist</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-brand-text-muted">
              This page shows the current Annex C requirements that still need action for the referenced project. No login is required and no updates can be made here.
            </p>
          </div>
          <Link to={ROUTES.LOGIN} className="btn-outline">
            Internal Sign In
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
        {loading && (
          <GlassPanel className="px-6 py-10 text-center text-sm text-brand-text-muted">
            Loading the latest project checklist...
          </GlassPanel>
        )}

        {!loading && error && (
          <GlassPanel className="px-6 py-8">
            <EmptyState
              title="Link unavailable"
              description={error}
              icon={AlertTriangle}
            />
          </GlassPanel>
        )}

        {!loading && payload && (
          <div className="space-y-6">
            <GlassPanel className="overflow-hidden" noPadding>
              <div className="grid gap-0 lg:grid-cols-[1.6fr_1fr]">
                <div className="space-y-5 p-6">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusPill label={payload.latest_notice?.title || payload.purpose_label} tone="blue" />
                    <StatusPill label={payload.current_phase ? `${formatMachineLabel(payload.current_phase)} phase` : 'Phase'} tone="slate" />
                    <StatusPill label={`Expires ${formatDate(payload.expires_at)}`} tone="amber" />
                  </div>
                  <div>
                    <h2 className="text-2xl font-semibold text-brand-text">{payload.project_name}</h2>
                    <p className="mt-2 text-sm text-brand-text-muted">
                      {payload.lgu_name} · FY {payload.fiscal_year} · {payload.program_name}
                    </p>
                    <p className="mt-1 text-sm text-brand-text-muted">
                      {payload.municipality}, {payload.province}
                    </p>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="rounded-lg border border-brand-border bg-brand-surface px-4 py-4">
                      <p className="micro-text">Intended Viewer</p>
                      <p className="mt-2 text-sm text-brand-text">{payload.intended_recipient_name || 'Authorized receiving officer'}</p>
                      <p className="mt-1 text-xs text-brand-text-muted">{payload.intended_recipient_role ? formatRole(payload.intended_recipient_role) : 'Read-only external access'}</p>
                    </div>
                    <div className="rounded-lg border border-brand-border bg-brand-surface px-4 py-4">
                      <p className="micro-text">Latest Notice</p>
                      <p className="mt-2 text-sm text-brand-text">{payload.latest_notice?.title || 'No notice linked'}</p>
                      <p className="mt-1 text-xs text-brand-text-muted">Prepared {formatDate(payload.latest_notice?.generated_at)}</p>
                    </div>
                  </div>
                </div>

                <div className="border-t border-brand-border bg-brand-surface p-6 lg:border-l lg:border-t-0">
                  <div className="flex items-center gap-2 text-sm text-brand-text-muted">
                    <ShieldCheck className="h-4 w-4 text-emerald-700 dark:text-emerald-200" />
                    Read-only view prepared for field coordination.
                  </div>
                  <div className="mt-5 grid gap-3">
                    {cards.map((card) => (
                      <KpiCard key={card.label} title={card.label} value={card.value} subtitle={card.subtitle} color={card.color} icon={card.icon} />
                    ))}
                  </div>
                </div>
              </div>
            </GlassPanel>

            <GlassPanel>
              <div className="mb-4 flex items-start gap-3">
                <Clock3 className="mt-0.5 h-5 w-5 text-amber-700 dark:text-amber-200" />
                <div>
                  <h2 className="text-lg font-semibold text-brand-text">Outstanding Annex C requirements</h2>
                  <p className="text-sm text-brand-text-muted">Currently outstanding checklist items that still need action or rectification.</p>
                </div>
              </div>

              {!payload.outstanding_requirements?.length ? (
                <InlineAlert type="success">
                  No outstanding requirements are currently listed for this project.
                </InlineAlert>
              ) : (
                <div className="space-y-3">
                  {payload.outstanding_requirements.map((item) => (
                    <div key={item.id} className="rounded-lg border border-brand-border bg-brand-surface px-4 py-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h3 className="text-base font-semibold text-brand-text">{item.requirement_name}</h3>
                          <p className="mt-1 text-sm text-brand-text-muted">
                            {item.phase_name || 'Unassigned phase'} · {item.annex_reference || 'Annex C'}
                          </p>
                        </div>
                        <StatusPill
                          label={item.public_status_label}
                          tone={item.status === 'non_compliant' ? 'red' : item.status === 'under_review' ? 'amber' : 'blue'}
                        />
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs text-brand-text-muted">
                        <span className="rounded-md border border-brand-border px-2.5 py-1">
                          {item.is_mandatory ? 'Mandatory' : 'Optional'}
                        </span>
                        {item.has_sla && item.sla_days ? (
                          <span className="rounded-md border border-brand-border px-2.5 py-1">
                            Deadline window: {item.sla_days} working days
                          </span>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </GlassPanel>

            {Boolean(payload.not_applicable_requirements?.length) && (
              <GlassPanel>
                <div className="mb-4 flex items-start gap-3">
                  <ShieldCheck className="mt-0.5 h-5 w-5 text-slate-600 dark:text-slate-300" />
                  <div>
                    <h2 className="text-lg font-semibold text-brand-text">Not Applicable requirements</h2>
                    <p className="text-sm text-brand-text-muted">
                      Requirements marked as not applicable to this project scope with their recorded justification.
                    </p>
                  </div>
                </div>

                <div className="space-y-3">
                  {payload.not_applicable_requirements.map((item) => {
                    const reason = item.applicability_reason?.trim()
                    return (
                      <div key={item.id} className="rounded-lg border border-brand-border bg-brand-surface px-4 py-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <h3 className="text-base font-semibold text-brand-text">{item.requirement_name}</h3>
                            <p className="mt-1 text-sm text-brand-text-muted">
                              {item.phase_name || 'Unassigned phase'} · {item.annex_reference || 'Annex C'}
                            </p>
                          </div>
                          <StatusPill
                            label={item.public_status_label || 'Not Applicable'}
                            tone="slate"
                          />
                        </div>

                        {reason ? (
                          <div className="mt-3 rounded-md border border-brand-border/60 bg-brand-surface-muted/40 p-3 text-xs text-brand-text-muted">
                            <span className="font-semibold text-brand-text">Justification: </span>
                            <span>{reason}</span>
                          </div>
                        ) : null}

                        <div className="mt-3 flex flex-wrap gap-2 text-xs text-brand-text-muted">
                          <span className="rounded-md border border-brand-border px-2.5 py-1">
                            {item.is_mandatory ? 'Mandatory' : 'Optional'}
                          </span>
                          <span className="rounded-md border border-brand-border px-2.5 py-1">
                            Exempt from document submission
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </GlassPanel>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
