import { useState, useEffect } from 'react'
import { AlertCircle, RotateCcw, CheckCircle2, ShieldAlert } from 'lucide-react'
import { Button, Modal, InlineAlert } from '../../../../components'

export function StatusChangeModal({
  open,
  onClose,
  requirement,
  userRole = 'staff',
  onSubmit,
}) {
  const isAdmin = userRole === 'admin'
  const currentStatus = requirement?.status || 'non_compliant'

  const [requestedStatus, setRequestedStatus] = useState('under_review')
  const [justification, setJustification] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (open) {
      setRequestedStatus('under_review')
      setJustification(
        isAdmin
          ? 'Reopened for evaluation of updated documentary submission.'
          : 'Requesting status reversal to evaluate updated documentary submission.'
      )
      setError('')
      setSubmitting(false)
    }
  }, [open, isAdmin])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!justification.trim()) {
      setError('A justification is required for the audit ledger.')
      return
    }

    setSubmitting(true)
    setError('')
    try {
      await onSubmit?.({
        requested_status: requestedStatus,
        justification: justification.trim(),
        auto_approve: isAdmin,
      })
      onClose?.()
    } catch (err) {
      setError(
        err.response?.data?.message ||
        err.response?.data?.error ||
        err.message ||
        'Unable to update requirement status.'
      )
    } finally {
      setSubmitting(false)
    }
  }

  const options = [
    {
      value: 'under_review',
      label: 'Reopen for Review (Under Review)',
      desc: 'Clears the review lock and returns requirement to Under Review so staff can evaluate and verify newly uploaded evidence.',
      icon: RotateCcw,
      iconClass: 'text-blue-500 dark:text-blue-400',
    },
    ...(isAdmin ? [{
      value: 'compliant',
      label: 'Direct Approval (Compliant)',
      desc: 'Officially approves this requirement attachment and marks it Compliant via audited administrative action.',
      icon: CheckCircle2,
      iconClass: 'text-emerald-500 dark:text-emerald-400',
    }] : []),
    {
      value: 'waived',
      label: isAdmin ? 'Waive Requirement (Waived)' : 'Request Waiver (Waived)',
      desc: 'Officially waives the requirement.',
      icon: ShieldAlert,
      iconClass: 'text-purple-500 dark:text-purple-400',
    },
  ]

  return (
    <Modal
      open={open}
      title={isAdmin ? 'Reopen / Update Requirement Status' : 'Request Status Reversal'}
      description={requirement ? `${requirement.requirement_name || requirement.name || 'Requirement'} · ${requirement.project_name || ''}` : ''}
      onClose={onClose}
      size="md"
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {error && (
          <InlineAlert type="error" onDismiss={() => setError('')}>
            {error}
          </InlineAlert>
        )}

        <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-3.5 text-xs text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
          <div className="flex items-start gap-2">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
            <div>
              <p className="font-semibold text-amber-950 dark:text-amber-100">
                Current Status: <span className="uppercase">{currentStatus.replace('_', ' ')}</span>
              </p>
              <p className="mt-0.5 text-amber-800/90 dark:text-amber-300/90">
                {isAdmin
                  ? 'All changes to reviewed compliance statuses are recorded in the audit ledger and immediately take effect.'
                  : 'Submitted status reversal requests are routed to Provincial Administrators for review and approval.'}
              </p>
            </div>
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-brand-text mb-2">
            Target Status
          </label>
          <div className="space-y-2">
            {options.map((opt) => {
              const Icon = opt.icon
              const isSelected = requestedStatus === opt.value
              return (
                <label
                  key={opt.value}
                  className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition-colors ${
                    isSelected
                      ? 'border-brand-primary bg-blue-50/50 dark:border-blue-500 dark:bg-blue-950/30'
                      : 'border-brand-border bg-brand-surface hover:bg-slate-50 dark:hover:bg-slate-800/40'
                  }`}
                >
                  <input
                    type="radio"
                    name="requested_status"
                    value={opt.value}
                    checked={isSelected}
                    onChange={(e) => setRequestedStatus(e.target.value)}
                    className="mt-1 h-4 w-4 text-brand-primary focus:ring-brand-primary"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-brand-text">
                      <Icon className={`h-3.5 w-3.5 ${opt.iconClass}`} />
                      <span>{opt.label}</span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-brand-text-muted">
                      {opt.desc}
                    </p>
                  </div>
                </label>
              )
            })}
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-brand-text mb-1">
            Justification <span className="text-red-500">*</span>
          </label>
          <textarea
            rows={3}
            value={justification}
            onChange={(e) => setJustification(e.target.value)}
            placeholder="Provide justification for this status change (recorded in audit ledger)..."
            className="input-field w-full text-xs"
            required
          />
          <p className="mt-1 text-[11px] text-brand-text-muted">
            Required for audit trail and compliance governance records.
          </p>
        </div>

        <div className="flex justify-end gap-2 border-t border-brand-border pt-3">
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" variant="default" loading={submitting}>
            {isAdmin
              ? (requestedStatus === 'under_review' ? 'Reopen for Review' : 'Apply Status Change')
              : 'Submit Request'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

export default StatusChangeModal
