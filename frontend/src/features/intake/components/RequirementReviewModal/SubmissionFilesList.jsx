import { Download, Eye } from 'lucide-react'
import { Button } from '../../../../components'
import { FileSummary } from '../../lib/intakeComponents.jsx'

/**
 * SubmissionFilesList — extraction of the per-file Preview/Download row used
 * inside the Submission History accordion.
 */
export function SubmissionFilesList({
  files = [],
  filePreviewLoadingId,
  onPreview,
  onDownload,
}) {
  if (!files.length) {
    return (
      <div className="text-xs text-brand-text-muted">No files attached to this submission.</div>
    )
  }
  return (
    <div className="space-y-2">
      {files.map((file) => (
        <div
          key={file.id}
          className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-md border border-brand-border bg-brand-surface px-3 py-2 text-sm"
        >
          <FileSummary fileName={file.file_name} date={file.created_at} />
          <div className="flex shrink-0 gap-2">
            <Button
              size="sm"
              variant="outline"
              icon={Eye}
              loading={filePreviewLoadingId === file.id}
              onClick={() => onPreview?.(file)}
            >
              Preview
            </Button>
            <Button size="sm" variant="outline" icon={Download} onClick={() => onDownload?.(file)}>
              Download
            </Button>
          </div>
        </div>
      ))}
    </div>
  )
}

export default SubmissionFilesList
