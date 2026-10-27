import { useState } from 'react'
import { CheckCircle2, Send, ShieldCheck, Undo2 } from 'lucide-react'
import { Button, ProgramPausedBanner } from '../../../components'
import { isAdmin, isFieldOfficer, isPlainStaff } from '../../../lib/auth'
import {
  canFieldOfficerSubmit,
  canProvincialApprove,
  canReturn,
  canStaffApprove,
  canStaffVerify,
} from './workflowStatus'
import { ReturnForRevisionModal } from './ReturnForRevisionModal'

/**
 * Role-aware action bar for the Phase 2A shared document workflow.
 * Buttons are only rendered when the caller's role AND the current
 * workflow_status permit the action; the backend re-enforces every rule
 * in requirement_workflow_service regardless of what is shown here.
 */
export function WorkflowActionBar({
  workflowStatus,
  hasEvidence,
  onSubmit,
  onVerify,
  onStaffApprove,
  onProvincialApprove,
  onReturn,
  requirementName = null,
  disabled = false,
  isProgramInactive = false,
  programId = null,
}) {
  const [showReturnModal, setShowReturnModal] = useState(false)
  const [isSubmittingReturn, setIsSubmittingReturn] = useState(false)

  const fieldOfficer = isFieldOfficer()
  const staff = isPlainStaff()
  const admin = isAdmin()

  const showSubmit = fieldOfficer && canFieldOfficerSubmit(workflowStatus)
  const showVerify = (staff || admin) && canStaffVerify(workflowStatus)
  const showStaffApprove = (staff || admin) && canStaffApprove(workflowStatus)
  const showProvincialApprove = admin && canProvincialApprove(workflowStatus)
  const showReturn = (staff || admin) && canReturn(workflowStatus)

  if (isProgramInactive) {
    return (
      <div className="flex flex-wrap items-center gap-2 border-t border-brand-border bg-brand-surface px-4 py-3">
        <ProgramPausedBanner programId={programId} />
      </div>
    )
  }

  if (!showSubmit && !showVerify && !showStaffApprove && !showProvincialApprove && !showReturn) {
    return null
  }

  const handleReturnSubmit = async (payload) => {
    setIsSubmittingReturn(true)
    try {
      await onReturn(payload)
      setShowReturnModal(false)
    } finally {
      setIsSubmittingReturn(false)
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 border-t border-brand-border bg-brand-surface px-4 py-3">
        {showSubmit && (
          <Button
            size="sm"
            icon={Send}
            disabled={disabled || !hasEvidence}
            onClick={onSubmit}
            title={!hasEvidence ? 'Upload supporting evidence before submitting' : undefined}
          >
            {workflowStatus === 'returned_for_revision' ? 'Resubmit' : 'Submit'}
          </Button>
        )}
        {showVerify && (
          <Button size="sm" variant="outline" icon={ShieldCheck} disabled={disabled} onClick={onVerify}>
            Move to Under Verification
          </Button>
        )}
        {showStaffApprove && (
          <Button size="sm" variant="outline" icon={CheckCircle2} disabled={disabled} onClick={onStaffApprove}>
            Staff Approve
          </Button>
        )}
        {showProvincialApprove && (
          <Button size="sm" icon={CheckCircle2} disabled={disabled} onClick={onProvincialApprove}>
            Provincial Approve
          </Button>
        )}
        {showReturn && (
          <Button
            size="sm"
            variant="ghost"
            icon={Undo2}
            disabled={disabled}
            onClick={() => setShowReturnModal(true)}
          >
            Return for Revision
          </Button>
        )}
      </div>

      {showReturn && (
        <ReturnForRevisionModal
          open={showReturnModal}
          onClose={() => setShowReturnModal(false)}
          onSubmit={handleReturnSubmit}
          requirementName={requirementName}
          loading={isSubmittingReturn}
        />
      )}
    </>
  )
}

