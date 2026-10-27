import { CheckCircle2, Search, XCircle } from 'lucide-react'
import { Button } from '../../../../components'
import { formatConfidence, matchTier, scanStatusClass, scanStatusLabel } from '../../lib/intakeFormatters.js'
import { MatcherReviewNotice } from '../MatcherReviewNotice.jsx'

/**
 * ScanMappingCard — extraction of the per-submission scan mapping block.
 * Shows the suggested requirement, confidence, mapping mismatch hint, and
 * the Accept Mapping / Reject Mapping / Rescan controls (admin/staff only).
 */
export function ScanMappingCard({
  submissionId,
  scan,
  canReviewScan,
  reviewingScanId,
  onRescanSubmission,
  onReviewScan,
}) {
  if (!scan) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-md border border-dashed border-brand-border bg-brand-surface px-3 py-3 text-xs text-brand-text-muted">
        <span>No scan result yet for this submission.</span>
        <Button
          size="sm"
          variant="outline"
          icon={Search}
          loading={reviewingScanId === `rescan-${submissionId}`}
          onClick={() => onRescanSubmission?.(submissionId)}
        >
          Scan
        </Button>
      </div>
    )
  }

  const tier = scan.scan_metadata?.match_tier || scan.match_tier || matchTier(scan.confidence_score)

  return (
    <div className="rounded-md border border-brand-border bg-brand-surface p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-brand-text">
            {scan.suggested_requirement_name || 'Manual Review Needed'}
          </div>
          <div className="mt-1 text-xs text-brand-text-muted" title="Heuristic lexical match score, not statistical probability">
            Match: {formatConfidence(scan.confidence_score)} ({tier})
            {scan.mapping_mismatch ? ' · selected requirement differs' : ''}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className={scanStatusClass(scan)}>{scanStatusLabel(scan)}</span>
          <Button
            size="sm"
            variant="outline"
            icon={Search}
            loading={reviewingScanId === `rescan-${submissionId}`}
            onClick={() => onRescanSubmission?.(submissionId)}
          >
            Rescan
          </Button>
        </div>
      </div>
      <div className="mt-2"><MatcherReviewNotice scan={scan} /></div>
      {canReviewScan && scan.is_accepted === null && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            size="sm"
            icon={CheckCircle2}
            disabled={!scan.suggested_project_requirement_id}
            loading={reviewingScanId === scan.id}
            onClick={() => onReviewScan?.(scan, 'accepted')}
          >
            Accept Mapping
          </Button>
          <Button
            size="sm"
            variant="outline"
            icon={XCircle}
            loading={reviewingScanId === scan.id}
            onClick={() => onReviewScan?.(scan, 'rejected')}
          >
            Reject Mapping
          </Button>
        </div>
      )}
    </div>
  )
}

export default ScanMappingCard
