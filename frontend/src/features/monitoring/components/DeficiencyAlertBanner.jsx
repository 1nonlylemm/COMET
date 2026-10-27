import { AlertTriangle, Calendar, CheckCircle, FileText, UploadCloud, User } from 'lucide-react'
import { Button } from '../../../components'
import { deficiencyCategoryLabel } from './workflowStatus'

export function DeficiencyAlertBanner({
  requirement,
  deficiencies = [],
  onUploadAndResubmit,
  isFieldOfficer = false,
}) {
  if (!deficiencies || deficiencies.length === 0) {
    if (requirement?.workflow_status !== 'returned_for_revision') return null
  }

  const openDeficiencies = deficiencies.filter((d) => d.resolution_state === 'open')
  const isReturned = requirement?.workflow_status === 'returned_for_revision'

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50/70 p-4 dark:border-amber-800/60 dark:bg-amber-950/25 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-200/80 pb-3 dark:border-amber-800/40">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400 shrink-0" />
          <div>
            <h3 className="text-sm font-semibold text-amber-900 dark:text-amber-200">
              {isReturned
                ? 'Action Required: Returned for Documentary Revision'
                : 'Recorded Documentary Deficiencies'}
            </h3>
            <p className="text-xs text-amber-700 dark:text-amber-300">
              {openDeficiencies.length > 0
                ? `${openDeficiencies.length} item(s) require correction before this document can be approved.`
                : 'All cited deficiencies on previous submissions have been resolved.'}
            </p>
          </div>
        </div>
        {isFieldOfficer && isReturned && onUploadAndResubmit && (
          <Button
            size="sm"
            variant="warning"
            icon={UploadCloud}
            onClick={onUploadAndResubmit}
          >
            Upload Revision & Resubmit
          </Button>
        )}
      </div>

      <div className="space-y-2">
        {deficiencies.map((d, index) => {
          const isOpen = d.resolution_state === 'open'
          return (
            <div
              key={d.id || index}
              className={`rounded-md border p-3 text-xs transition-colors ${
                isOpen
                  ? 'border-amber-200 bg-white/80 dark:border-amber-900/40 dark:bg-brand-surface'
                  : 'border-slate-200 bg-slate-50/80 dark:border-slate-800 dark:bg-brand-surface/50'
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
                <span className="font-semibold text-brand-text">
                  Item #{index + 1}: {deficiencyCategoryLabel(d.category)}
                </span>
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${
                    d.resolution_state === 'resolved'
                      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
                      : d.resolution_state === 'waived'
                      ? 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
                      : 'bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300'
                  }`}
                >
                  {d.resolution_state === 'resolved' && <CheckCircle className="h-3 w-3 mr-1" />}
                  {d.resolution_state ? d.resolution_state.toUpperCase() : 'OPEN'}
                </span>
              </div>

              <div className="space-y-1 text-brand-text-muted">
                <p>
                  <strong className="text-brand-text">Finding / Observation:</strong>{' '}
                  {d.finding_observation}
                </p>
                <p>
                  <strong className="text-brand-text">Corrective Action:</strong>{' '}
                  <span className="text-amber-800 dark:text-amber-300">{d.corrective_instruction}</span>
                </p>
                {d.resolution_notes && (
                  <p className="text-emerald-700 dark:text-emerald-400">
                    <strong>Resolution Note:</strong> {d.resolution_notes}
                  </p>
                )}
              </div>

              <div className="mt-2 pt-2 border-t border-brand-border/40 flex flex-wrap items-center gap-4 text-[11px] text-brand-text-muted/80">
                {d.created_at && (
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    Returned {new Date(d.created_at).toLocaleDateString()}
                  </span>
                )}
                {d.created_by_name && (
                  <span className="flex items-center gap-1">
                    <User className="h-3 w-3" />
                    Reviewer: {d.created_by_name}
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
