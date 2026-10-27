import { AlertTriangle, Download, FileText, CheckCircle2 } from 'lucide-react'
import { Button, InlineAlert } from '../../../../components'
import { deficiencyCategoryLabel } from '../../../monitoring/components/workflowStatus'
import { formatDate } from '../../lib/intakeFormatters'

/**
 * FieldOfficerTransmittalCard — Clean, formal display of reviewer return transmittal
 * specifically designed for Field Officers and LGU users.
 *
 * Displays:
 * 1. Formal return notice (timestamp + reviewer)
 * 2. Official reviewer instructions
 * 3. Ratified deficiencies with observation and corrective guidance
 * 4. Direct download of the generated DOCX correction report
 */
export function FieldOfficerTransmittalCard({
  requirement,
  latestRevision,
  onDownloadReport,
  downloading = false,
  downloadError = '',
}) {
  if (!requirement) return null

  const returnedAt = latestRevision?.returned_at || requirement.workflow_returned_at
  const reviewerName = latestRevision?.returned_by_user?.full_name || requirement.last_action_by_name
  const reviewNotes = latestRevision?.review_notes || requirement.workflow_return_reason
  const deficiencies = latestRevision?.deficiencies || requirement.deficiencies || []

  return (
    <div
      data-testid="field-officer-transmittal-card"
      className="space-y-4 rounded-xl border border-amber-300 bg-amber-50/40 p-4 dark:border-amber-700/50 dark:bg-amber-950/20"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200">
            <AlertTriangle className="h-4 w-4" strokeWidth={2} />
          </div>
          <div>
            <div className="text-sm font-semibold text-amber-950 dark:text-amber-100">
              Requirement Returned for Revision
            </div>
            <div className="text-xs text-amber-800/80 dark:text-amber-300/80">
              {returnedAt ? `Returned on ${formatDate(returnedAt)}` : 'Formal transmittal issued'}
              {reviewerName ? ` by ${reviewerName}` : ''}
            </div>
          </div>
        </div>

        <Button
          size="sm"
          variant="outline"
          icon={Download}
          loading={downloading}
          disabled={downloading}
          onClick={onDownloadReport}
          className="shrink-0 border-amber-300 bg-white hover:bg-amber-50 dark:border-amber-700 dark:bg-brand-surface dark:hover:bg-amber-950/40"
        >
          Download Correction Report (.docx)
        </Button>
      </div>

      {downloadError && (
        <InlineAlert type="error" onDismiss={() => {}}>
          {downloadError}
        </InlineAlert>
      )}

      {reviewNotes && (
        <div className="rounded-lg border border-amber-200 bg-white/80 p-3.5 dark:border-amber-800/40 dark:bg-brand-surface">
          <div className="text-xs font-semibold uppercase tracking-wider text-amber-900 dark:text-amber-200">
            Reviewer Instructions
          </div>
          <p className="mt-1.5 whitespace-pre-wrap text-sm leading-relaxed text-brand-text">
            {reviewNotes}
          </p>
        </div>
      )}

      {deficiencies.length > 0 && (
        <div className="space-y-2.5">
          <div className="text-xs font-semibold uppercase tracking-wider text-amber-900/90 dark:text-amber-300/90">
            Specific Deficiencies to Address ({deficiencies.length})
          </div>
          <div className="space-y-2">
            {deficiencies.map((d, index) => (
              <div
                key={index}
                data-testid={`deficiency-item-${index}`}
                className="rounded-lg border border-amber-200/80 bg-white p-3.5 space-y-2 shadow-xs dark:border-amber-800/40 dark:bg-brand-surface"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="inline-flex items-center rounded-md bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-900/50 dark:text-amber-200">
                    {deficiencyCategoryLabel(d.category)}
                  </span>
                  {d.severity && (
                    <span className="text-[11px] font-medium uppercase tracking-wider text-brand-text-muted">
                      {d.severity}
                    </span>
                  )}
                </div>

                {d.finding_observation && (
                  <div>
                    <div className="text-xs font-medium text-brand-text-muted">Observation:</div>
                    <p className="text-sm text-brand-text">{d.finding_observation}</p>
                  </div>
                )}

                {d.corrective_instruction && (
                  <div className="rounded-md border border-amber-200/60 bg-amber-50/50 p-2 text-xs text-amber-950 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-100">
                    <span className="font-semibold">Corrective action: </span>
                    {d.corrective_instruction}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default FieldOfficerTransmittalCard
