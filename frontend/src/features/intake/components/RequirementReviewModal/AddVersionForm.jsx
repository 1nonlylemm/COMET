import { Upload } from 'lucide-react'
import { Button, InlineAlert } from '../../../../components'
import { AiRewriteControl } from '../../../ai/components/AiRewriteControl'
import { formatConfidence, matchTier, scanStatusClass } from '../../lib/intakeFormatters.js'
import { MatcherReviewNotice } from '../MatcherReviewNotice.jsx'

const DOCUMENT_UPLOAD_ACCEPT = '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.csv'

function EvidenceWarning({ candidate }) {
  if (!candidate) return null
  const alreadyReviewed = ['compliant', 'non_compliant', 'waived'].includes(candidate.status)
  if (!candidate.has_documentary_evidence && !alreadyReviewed) return null
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-300/40 dark:bg-amber-300/10 dark:text-amber-100">
      This requirement already has {candidate.has_documentary_evidence ? 'documentary evidence' : 'a reviewed status'}.
      Recording another file adds a new intake record and scan result; it does not change the requirement status by itself.
    </div>
  )
}

/**
 * AddVersionForm — extraction of the "Upload New Version" block.
 * Mirrors the original behavior: source select, file picker, AI-rewrite
 * version notes, and the version-mapping preview.
 */
export function AddVersionForm({
  uploadForm = { source: 'direct_upload', description: '', file: null },
  setUploadForm,
  uploading,
  scanPreview,
  scanPreviewLoading,
  scanPreviewError,
  setScanPreviewError,
  previewMatchesSelected,
  showScanPreview = true,
  onUploadSubmission,
}) {
  return (
    <form onSubmit={onUploadSubmission} className="space-y-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[180px_1fr]">
        <div>
          <label className="label-text">Source</label>
          <select
            className="input-field mt-1"
            value={uploadForm?.source || 'direct_upload'}
            onChange={(event) => setUploadForm((current) => ({ ...current, source: event.target.value }))}
          >
            <option value="dms_ingestion">DMS Ingestion</option>
            <option value="direct_upload">Direct Upload</option>
            <option value="field_upload">Field Upload</option>
            <option value="api_push">API Push</option>
          </select>
        </div>
        <div>
          <label className="label-text">Document File</label>
          <input
            type="file"
            accept={DOCUMENT_UPLOAD_ACCEPT}
            className="input-field mt-1"
            onChange={(event) => setUploadForm((current) => ({ ...current, file: event.target.files?.[0] || null }))}
          />
        </div>
      </div>
      <AiRewriteControl
        label="Version Notes"
        value={uploadForm?.description || ''}
        onTextChange={(text) => setUploadForm?.((current) => ({ ...current, description: text }))}
        contextLabel="Document version notes"
        disabled={uploading}
        placeholder="Add DMS reference, routing context, or version remarks."
        rows={2}
      />
      {showScanPreview && (uploadForm?.file || scanPreviewLoading || scanPreviewError) && (
        <div className="rounded-lg border border-brand-border bg-brand-surface p-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-brand-text">Version Mapping Check</div>
              <div className="mt-1 text-xs text-brand-text-muted">
                {scanPreviewLoading
                  ? 'Scanning filename and readable document text...'
                  : scanPreview?.suggested_requirement_name || 'Manual review needed'}
              </div>
            </div>
            {scanPreview && (
              <span className={scanStatusClass({
                is_accepted: null,
                needs_review: scanPreview.needs_review,
                mapping_mismatch: !previewMatchesSelected,
              })}>
                {previewMatchesSelected && !scanPreview.needs_review ? 'Matches This Requirement' : 'Review Mapping'}
              </span>
            )}
          </div>
          {scanPreviewError && (
            <InlineAlert type="warning" className="mt-3" onDismiss={() => setScanPreviewError?.('')}>
              {scanPreviewError}
            </InlineAlert>
          )}
          {scanPreview && (
            <div className="mt-3 space-y-2 text-sm">
              <MatcherReviewNotice scan={scanPreview} />
              <div className="grid grid-cols-2 gap-2 text-xs text-brand-text-muted">
                <div>Suggested: <span className="font-medium text-brand-text">{scanPreview.suggested_requirement_name || 'Manual Review Needed'}</span></div>
                <div title="Heuristic lexical match score, not statistical probability">
                  Match: <span className="font-medium text-brand-text">{scanPreview.match_tier || matchTier(scanPreview.confidence_score)} ({formatConfidence(scanPreview.confidence_score)})</span>
                </div>
              </div>
              <EvidenceWarning candidate={{
                status: scanPreview.suggested_requirement_status,
                has_documentary_evidence: scanPreview.suggested_has_documentary_evidence,
              }} />
            </div>
          )}
        </div>
      )}
      <Button type="submit" icon={Upload} loading={uploading} disabled={showScanPreview && scanPreviewLoading}>
        Record New Version
      </Button>
    </form>
  )
}

export default AddVersionForm
