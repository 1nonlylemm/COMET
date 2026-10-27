import { ChevronRight } from 'lucide-react'
import { formatMachineLabel } from '../../../../lib/formatters'
import { formatDate, scanStatusClass, scanStatusLabel } from '../../lib/intakeFormatters.js'
import { SubmissionFilesList } from './SubmissionFilesList'

/**
 * SubmissionHistoryList — older submissions, each rendered as a collapsed
 * <details>/<summary> so the modal does not balloon vertically when a
 * requirement has many revisions.
 */
export function SubmissionHistoryList({
  submissions = [],
  filePreviewLoadingId,
  onPreview,
  onDownload,
}) {
  if (!submissions.length) {
    return (
      <div className="text-xs text-brand-text-muted">No previous submission versions.</div>
    )
  }
  return (
    <ul className="space-y-2">
      {submissions.map((submission) => {
        const latestScan = submission.nlp_scan_results?.[0]
        const findingsCount = (submission.latest_compliance_result?.findings || []).length
        return (
          <li key={submission.id}>
            <details className="group rounded-md border border-brand-border bg-brand-surface">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-xs font-medium text-brand-text-muted hover:bg-brand-surface-solid">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="text-brand-text">{submission.description || formatMachineLabel(submission.source)}</span>
                  <span>· {formatDate(submission.created_at)}</span>
                  {findingsCount > 0 && (
                    <span className="inline-flex items-center rounded-full border border-brand-border bg-brand-surface-solid px-1.5 py-0.5 text-[10px] font-medium">
                      {findingsCount} findings
                    </span>
                  )}
                  {latestScan && (
                    <span className={scanStatusClass(latestScan)}>{scanStatusLabel(latestScan)}</span>
                  )}
                </span>
                <ChevronRight className="h-3.5 w-3.5 transition-transform duration-200 group-open:rotate-90" strokeWidth={1.7} />
              </summary>
              <div className="border-t border-brand-border px-3 py-3">
                <SubmissionFilesList
                  files={submission.document_files || []}
                  filePreviewLoadingId={filePreviewLoadingId}
                  onPreview={onPreview}
                  onDownload={onDownload}
                />
              </div>
            </details>
          </li>
        )
      })}
    </ul>
  )
}

export default SubmissionHistoryList
