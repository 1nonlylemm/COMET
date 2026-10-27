import { useEffect, useRef, useState } from 'react'
import { Button, FormField, InlineAlert, Modal } from '../../../components'
import { formatStatus } from '../../../lib/formatters'
import * as projectApi from '../api/projectApi'
import { checkApplicabilityEligibility, validateApplicabilityReason } from '../utils/applicability'

export function ChangeApplicabilityModal({
  open,
  onClose,
  requirement,
  project,
  mode = 'set_not_applicable',
  onSuccess,
}) {
  const [reason, setReason] = useState('')
  const [clientError, setClientError] = useState('')
  const [serverError, setServerError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const isSubmittingRef = useRef(false)

  const isRestore = mode === 'restore_applicable' || requirement?.applicability === 'not_applicable'

  useEffect(() => {
    if (open) {
      setServerError('')
      setClientError('')
      if (isRestore) {
        setReason('')
      }
    }
  }, [open, isRestore, requirement?.id])

  if (!open || !requirement) return null

  const eligibility = !isRestore ? checkApplicabilityEligibility(requirement) : { eligible: true, reason: null }

  const handleSubmit = async (event) => {
    if (event) event.preventDefault()
    if (isSubmittingRef.current || submitting) return

    setServerError('')
    setClientError('')

    if (!isRestore) {
      if (!eligibility.eligible) {
        setClientError(eligibility.reason)
        return
      }
      const validationError = validateApplicabilityReason(reason)
      if (validationError) {
        setClientError(validationError)
        return
      }
    }

    try {
      isSubmittingRef.current = true
      setSubmitting(true)

      const payload = isRestore
        ? { applicability: 'applicable' }
        : { applicability: 'not_applicable', reason: reason.trim() }

      const res = await projectApi.updateProjectRequirementApplicability(requirement.id, payload)
      if (onSuccess) {
        await onSuccess(res.data)
      }
      onClose()
    } catch (err) {
      const data = err.response?.data
      const message =
        data?.message ||
        (data?.errors
          ? (typeof data.errors === 'string'
              ? data.errors
              : Object.values(data.errors).flat().join(', '))
          : null) ||
        err.message ||
        'Failed to update requirement applicability.'
      setServerError(message)
    } finally {
      isSubmittingRef.current = false
      setSubmitting(false)
    }
  }

  const title = isRestore ? 'Restore Requirement Applicability' : 'Mark Requirement as Not Applicable'

  return (
    <Modal
      open={open}
      title={title}
      size="lg"
      onClose={() => {
        if (!submitting) onClose()
      }}
      footer={
        <div className="flex items-center justify-end gap-3">
          <Button
            type="button"
            variant="outline"
            disabled={submitting}
            onClick={onClose}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant={isRestore ? 'primary' : 'warning'}
            loading={submitting}
            disabled={submitting || (!isRestore && !eligibility.eligible)}
            onClick={handleSubmit}
          >
            {isRestore ? 'Restore Applicability' : 'Mark Not Applicable'}
          </Button>
        </div>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {serverError && (
          <InlineAlert type="error" onDismiss={() => setServerError('')}>
            {serverError}
          </InlineAlert>
        )}

        {/* Target context banner */}
        <div className="rounded-lg border border-brand-border bg-brand-surface p-3.5 space-y-1.5 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-semibold text-brand-text text-sm">
              {requirement.requirement_name}
            </span>
            {requirement.annex_reference && (
              <span className="text-brand-text-muted">{requirement.annex_reference}</span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-brand-text-muted">
            <span>Project: <strong className="font-medium text-brand-text">{project?.project_name || 'Current Project'}</strong></span>
            {project?.source_project_code && (
              <span className="border-l border-brand-border pl-3">Code: {project.source_project_code}</span>
            )}
            <span className="border-l border-brand-border pl-3">
              Phase: {requirement.phase_name || 'General'}
            </span>
            <span className="border-l border-brand-border pl-3">
              Status: {formatStatus(requirement.status)}
            </span>
          </div>
        </div>

        {isRestore ? (
          <div className="space-y-4 text-sm">
            <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-3.5 text-xs text-blue-900 dark:border-blue-900/40 dark:bg-blue-950/20 dark:text-blue-200">
              <p className="font-medium">
                Restoring this requirement to Applicable will return it to the active project compliance checklist.
              </p>
              <p className="mt-1 text-blue-800 dark:text-blue-300">
                It will be counted toward mandatory submission tracking and must be satisfied or validly waived before advancing project phases.
              </p>
            </div>

            {requirement.applicability_reason && (
              <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3.5 dark:border-amber-900/40 dark:bg-amber-950/20">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-amber-800 dark:text-amber-300">
                  Current Exemption Justification
                </h4>
                <p className="mt-1 text-xs text-amber-900 dark:text-amber-200">
                  {requirement.applicability_reason}
                </p>
                {(requirement.applicability_set_by_name || requirement.applicability_set_at) && (
                  <p className="mt-1.5 text-[11px] text-amber-700 dark:text-amber-400">
                    Exemption set by {requirement.applicability_set_by_name || 'Authorized user'}
                    {requirement.applicability_set_at && (
                      ` on ${new Date(requirement.applicability_set_at).toLocaleDateString('en-PH', { month: 'short', day: 'numeric', year: 'numeric' })}`
                    )}
                  </p>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4 text-sm">
            <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3.5 text-xs text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
              <p className="font-medium">
                Marking this requirement as Not Applicable excludes it from mandatory submission requirements and statutory compliance deadlines for this project.
              </p>
              <p className="mt-1 text-amber-800 dark:text-amber-300">
                It will not block phase progression or final completion approval, but remains recorded with full audit trail justification.
              </p>
            </div>

            {!eligibility.eligible && (
              <InlineAlert type="warning">
                {eligibility.reason}
              </InlineAlert>
            )}

            <FormField
              id="applicability-justification"
              label="Exemption Justification"
              required
              hint="Provide a clear, meaningful reason explaining why this requirement is not applicable to this project (minimum 3 meaningful words)."
              error={clientError}
            >
              <textarea
                id="applicability-justification"
                rows={3}
                value={reason}
                onChange={(e) => {
                  setReason(e.target.value)
                  if (clientError) setClientError('')
                }}
                disabled={submitting || !eligibility.eligible}
                placeholder="e.g. Environmental clearance not required because the project scope is entirely confined to existing building interior refurbishment without ground disturbance."
                className="input-field mt-1 w-full text-sm"
              />
            </FormField>
          </div>
        )}
      </form>
    </Modal>
  )
}
