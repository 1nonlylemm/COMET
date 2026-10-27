import { useState } from 'react'
import { Check, CheckCircle2, FileCheck2, Info, ShieldCheck } from 'lucide-react'
import { Button } from '../../../components'
import { deficiencyCategoryLabel } from './workflowStatus'

export function ReReviewDeficiencyChecklist({
  deficiencies = [],
  onResolve,
  loading = false,
}) {
  const [activeNotes, setActiveNotes] = useState({})
  const [resolvingId, setResolvingId] = useState(null)

  if (!deficiencies || deficiencies.length === 0) return null

  const openItems = deficiencies.filter((d) => d.resolution_state === 'open')

  const handleResolveClick = async (deficiencyId) => {
    setResolvingId(deficiencyId)
    const note = activeNotes[deficiencyId] || ''
    try {
      await onResolve(deficiencyId, {
        resolution_state: 'resolved',
        resolution_notes: note.trim() || undefined,
      })
      setActiveNotes((prev) => {
        const next = { ...prev }
        delete next[deficiencyId]
        return next
      })
    } finally {
      setResolvingId(null)
    }
  }

  return (
    <div className="rounded-lg border border-brand-border bg-brand-surface p-4 space-y-3">
      <div className="flex items-center justify-between border-b border-brand-border pb-2">
        <div className="flex items-center gap-2">
          <FileCheck2 className="h-4 w-4 text-brand-primary" />
          <h4 className="text-xs font-semibold text-brand-text">
            Verify Resolution of Prior Deficiencies
          </h4>
        </div>
        <span className="text-[11px] font-medium text-brand-text-muted">
          {openItems.length === 0 ? (
            <span className="text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1">
              <CheckCircle2 className="h-3.5 w-3.5" /> All Resolved
            </span>
          ) : (
            <span className="text-amber-600 dark:text-amber-400 font-medium">
              {openItems.length} open item(s) to verify
            </span>
          )}
        </span>
      </div>

      <p className="text-[11px] text-brand-text-muted">
        Review revised documentary attachments against each cited finding. Mark items as resolved once verified before issuing Staff Approval.
      </p>

      <div className="space-y-2.5">
        {deficiencies.map((d) => {
          const isOpen = d.resolution_state === 'open'
          const isResolving = resolvingId === d.id

          return (
            <div
              key={d.id}
              className={`rounded-md border p-3 text-xs transition-colors ${
                isOpen
                  ? 'border-amber-200 bg-amber-50/40 dark:border-amber-900/40 dark:bg-amber-950/20'
                  : 'border-emerald-200 bg-emerald-50/30 dark:border-emerald-900/40 dark:bg-emerald-950/20'
              }`}
            >
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <div>
                  <span className="font-semibold text-brand-text">
                    {deficiencyCategoryLabel(d.category)}
                  </span>
                  <p className="mt-0.5 text-brand-text-muted">
                    <strong className="text-brand-text">Finding:</strong> {d.finding_observation}
                  </p>
                  <p className="text-brand-text-muted">
                    <strong>Required Action:</strong> {d.corrective_instruction}
                  </p>
                </div>
                <div>
                  {isOpen ? (
                    <Button
                      size="xs"
                      variant="outline"
                      icon={Check}
                      disabled={loading || isResolving}
                      onClick={() => handleResolveClick(d.id)}
                    >
                      {isResolving ? 'Resolving...' : 'Mark Resolved'}
                    </Button>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300">
                      <CheckCircle2 className="h-3 w-3" /> Resolved
                    </span>
                  )}
                </div>
              </div>

              {isOpen ? (
                <div className="mt-2 pt-2 border-t border-brand-border/40">
                  <input
                    type="text"
                    className="input-field w-full text-xs"
                    placeholder="Resolution verification note (e.g., Verified page 2 now signed)..."
                    value={activeNotes[d.id] || ''}
                    onChange={(e) =>
                      setActiveNotes((prev) => ({ ...prev, [d.id]: e.target.value }))
                    }
                    disabled={loading || isResolving}
                  />
                </div>
              ) : d.resolution_notes ? (
                <div className="mt-1.5 text-[11px] text-emerald-700 dark:text-emerald-400">
                  <strong>Verification Note:</strong> {d.resolution_notes}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}
