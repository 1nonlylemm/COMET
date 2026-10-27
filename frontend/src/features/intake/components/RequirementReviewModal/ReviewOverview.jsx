import { Button } from '../../../../components'
import { selectReviewFindings } from '../../lib/reviewFindings'

/** A compact summary of coverage and limitations, without implying compliance. */
export function ReviewOverview({ result, canRun, running, onRun, findingReviews = {} }) {
  const details = result?.score_details || {}
  const { configured_check_count: requiredCount, detected_check_count: detected,
    manual_check_count: manualCount, advisory_count: advisoryCount } = selectReviewFindings(result)
  const coverage = result?.analysis_coverage || details.analysis_coverage
  const state = result?.document_state || details.document_state
  const technical = result?.technical_summary || details.technical_summary
  const blank = state === 'blank_or_empty' || technical?.is_blank
  const visualOnly = state === 'visual_content_only' || technical?.is_visual_only
  const reviews = Object.values(findingReviews)

  return (
    <section aria-label="Review overview" className="space-y-2 border-b border-brand-border pb-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold text-brand-text">Review findings</h3>
        {canRun && <Button size="sm" variant="outline" loading={running} onClick={onRun}>{result ? 'Re-run Check' : 'Run Checker'}</Button>}
      </div>
      {!result ? <p className="text-brand-text-muted">No checker result yet. Inspect the document or run the checker to begin.</p> : blank ? (
        <p className="font-medium text-red-700 dark:text-red-300">The document appears blank or empty. Evidence checks were suppressed; inspect the uploaded file.</p>
      ) : (
        <>
          <p className="text-brand-text-muted">{requiredCount > 0 ? `Automated checks: ${detected} of ${requiredCount} required evidence items detected. Verify the findings before deciding.` : 'Requirement-specific checks are not configured. Manual verification required.'}</p>
          {visualOnly && <p className="text-brand-text-muted">Visual content only. Inspect the document manually; language checks may be unavailable.</p>}
        </>
      )}
      {coverage && <p className={`text-xs ${coverage.is_partial ? 'font-medium text-amber-800 dark:text-amber-200' : 'text-brand-text-muted'}`}>Coverage: {coverage.label || `${coverage.pages_analyzed} pages`}{coverage.notice ? ` · ${coverage.notice}` : ''}</p>}
      {manualCount > 0 && <p className="text-xs text-brand-text-muted">{manualCount} signatory or evidence check(s) require manual verification. Detected wording does not verify a signature or official mark.</p>}
      {advisoryCount > 0 && <p className="text-xs text-brand-text-muted">{advisoryCount} advisory finding(s); excluded from review attention and confidence.</p>}
      {reviews.length > 0 && <p className="text-xs text-brand-text-muted">Reviewer assessments: {reviews.filter(review => review.status === 'confirmed').length} confirmed · {reviews.filter(review => review.status === 'incorrect_flag').length} incorrect flags · {reviews.filter(review => review.status === 'needs_verification').length} need verification.</p>}
      <p className="text-xs text-brand-text-muted">Automated findings assist review. You decide documentary compliance.</p>
    </section>
  )
}
