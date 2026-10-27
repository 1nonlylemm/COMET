import { CheckCircle2, XCircle } from 'lucide-react'
import { Button, ProgramPausedBanner } from '../../../../components'
import { canReturn } from '../../../monitoring/components/workflowStatus'

const HELPER_LOCKED = 'Reviewed requirements need a status-change request before reversal.'
const HELPER_NO_EVIDENCE = 'Upload or record documentary evidence before approving or returning this requirement.'

/**
 * ReviewActionsBar — sticky-footer action bar for documentary review.
 *
 * In Phase 1 (Score Purge & Neutralization):
 * Evaluators retain 100% of final compliance authority.
 * Both Approve Attachment and Return for Revision are presented neutrally without
 * automated score-driven bias, artificial primary/secondary weighting, or
 * automated score-band confirmation intercepts.
 */
export function ReviewActionsBar({
  role,
  locked,
  hasEvidence,
  isApproveLoading,
  isReturnLoading,
  isProgramInactive,
  programId,
  onApprove,
  onReturn,
  workflowStatus,
  selectedCount = 0,
  canReturnDirectly = true,
  preparingReturn = false,
  returnLabel: customReturnLabel,
  contained = false,
  hideApprove = false,
  onReopen,
}) {
  if (role === 'field_officer') return null

  if (isProgramInactive) {
    return (
      <div
        data-testid="review-actions-bar"
        className={contained ? 'min-w-0' : 'sticky bottom-0 z-10 mt-2 border-t border-brand-border bg-brand-surface-solid px-5 py-3'}
      >
        <ProgramPausedBanner programId={programId} role={role} />
      </div>
    )
  }

  const isAlreadyReturned = workflowStatus === 'returned_for_revision'
  const isReturnBlocked = isAlreadyReturned || (workflowStatus ? !canReturn(workflowStatus) : false)

  const helper = locked
    ? HELPER_LOCKED
    : !hasEvidence
      ? HELPER_NO_EVIDENCE
      : null

  const handleApproveClick = () => {
    onApprove?.()
  }

  const sharedDisabled = !hasEvidence || locked
  const returnLabel = customReturnLabel || (selectedCount > 0 ? `Return for Revision (${selectedCount})` : 'Return for Revision')
  const returnDisabled = sharedDisabled || (!preparingReturn && !canReturnDirectly) || Boolean(isReturnLoading) || Boolean(isApproveLoading) || isReturnBlocked
  const returnTitle = isAlreadyReturned
    ? 'This requirement is already returned for revision and awaiting resubmission.'
    : isReturnBlocked
      ? `Cannot return requirement with workflow status "${workflowStatus}".`
      : !preparingReturn && !canReturnDirectly
        ? 'Add return notes or select at least one finding to return.'
        : undefined

  const renderApprove = () => (
    <Button
      key="approve"
      icon={CheckCircle2}
      variant="default"
      loading={Boolean(isApproveLoading)}
      disabled={sharedDisabled || Boolean(isReturnLoading) || Boolean(isApproveLoading)}
      onClick={handleApproveClick}
    >
      Approve Attachment
    </Button>
  )

  const renderReturn = () => (
    <span key="return-wrap" title={returnTitle} className="inline-flex">
      <Button
        key="return"
        icon={XCircle}
        variant="outline"
        loading={Boolean(isReturnLoading)}
        disabled={returnDisabled}
        onClick={onReturn}
        title={returnTitle}
      >
        {returnLabel}
      </Button>
    </span>
  )

  return (
    <div
      data-testid="review-actions-bar"
      className={contained ? 'flex flex-wrap items-center justify-end gap-3' : 'sticky bottom-0 z-10 mt-2 flex flex-col gap-2 border-t border-brand-border bg-brand-surface-solid px-5 py-3 sm:flex-row sm:items-center justify-end'}
    >
      <div className="flex flex-wrap items-center gap-2 text-xs text-brand-text-muted sm:mr-auto">
        {isAlreadyReturned && (
          <span className="inline-flex items-center gap-1.5 font-medium text-amber-600 dark:text-amber-400">
            <XCircle className="h-4 w-4 text-amber-500" strokeWidth={2} />
            Returned for revision — awaiting LGU resubmission
          </span>
        )}
        {!isAlreadyReturned && helper && (
          <div className="flex flex-wrap items-center gap-2">
            <span>{helper}</span>
            {locked && onReopen && (
              <Button
                type="button"
                size="xs"
                variant="outline"
                onClick={onReopen}
                className="whitespace-nowrap"
              >
                {role === 'admin' ? 'Reopen for Review' : 'Request Status Reversal'}
              </Button>
            )}
          </div>
        )}
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        {!hideApprove && renderApprove()}
        {renderReturn()}
      </div>
    </div>
  )
}

export default ReviewActionsBar
