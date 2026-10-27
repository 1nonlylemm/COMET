import { useMemo, useState } from 'react'
import { ClipboardCheck, ShieldCheck } from 'lucide-react'
import { Button, FormField, InlineAlert } from '../../../../components'
import { formatDate } from '../../lib/intakeFormatters.js'

const DECISION_LABELS = {
  accept_checker_result: 'Accept checker result',
  override_approve: 'Override to approve',
  override_return: 'Override to return',
  mark_false_positive: 'Checker false positive',
  mark_checker_missed_evidence: 'Checker missed evidence',
}

const REASON_LABELS = {
  missing_amount: 'Missing amount',
  wrong_lgu: 'Wrong LGU',
  unreadable_scan: 'Unreadable scan',
  wrong_project: 'Wrong project',
  missing_signature: 'Missing signature',
  obsolete_template: 'Obsolete template',
  incomplete_attachment: 'Incomplete attachment',
  checker_false_positive: 'Checker false positive',
  checker_missed_evidence: 'Checker missed evidence',
  no_issue: 'No issue',
}

const DEFAULT_DECISIONS = [
  'accept_checker_result',
  'override_approve',
  'override_return',
  'mark_false_positive',
  'mark_checker_missed_evidence',
]

const DEFAULT_REASONS = [
  'missing_amount',
  'wrong_lgu',
  'unreadable_scan',
  'wrong_project',
  'missing_signature',
  'obsolete_template',
  'incomplete_attachment',
  'checker_false_positive',
  'checker_missed_evidence',
  'no_issue',
]

function labelFor(value, labels) {
  return labels[value] || String(value || '').replace(/_/g, ' ')
}

function uniqueList(values, fallback) {
  const source = Array.isArray(values) && values.length ? values : fallback
  return [...new Set(source.filter(Boolean))]
}

export function ReviewerDecisionPanel({
  result,
  role = 'staff',
  isSubmitting = false,
  onRecord,
  compact = false,
}) {
  const policy = result?.reviewer_decision_policy || result?.score_details?.reviewer_decision_policy || {}
  const existing = result?.reviewer_decision || result?.score_details?.reviewer_decision || null
  const decisions = useMemo(
    () => uniqueList(policy.allowed_decisions, DEFAULT_DECISIONS),
    [policy.allowed_decisions],
  )
  const availableReasons = useMemo(
    () => uniqueList(policy.reason_codes, DEFAULT_REASONS),
    [policy.reason_codes],
  )
  const [decision, setDecision] = useState(existing?.decision || decisions[0] || 'accept_checker_result')
  const [reasonCodes, setReasonCodes] = useState(existing?.reason_codes || [])
  const [reviewNotes, setReviewNotes] = useState(existing?.review_notes || '')
  const [error, setError] = useState('')
  const [formOpen, setFormOpen] = useState(false)

  if (!result) return null
  if (role === 'field_officer') return null

  const toggleReason = (reasonCode) => {
    setReasonCodes((current) => (
      current.includes(reasonCode)
        ? current.filter((item) => item !== reasonCode)
        : [...current, reasonCode]
    ))
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    const notes = reviewNotes.trim()
    if (decision.startsWith('override') && reasonCodes.length === 0 && !notes) {
      setError('Override decisions require a reason code or reviewer note.')
      return
    }
    setError('')
    onRecord?.(result.id, {
      decision,
      reason_codes: reasonCodes,
      review_notes: notes,
    })
  }

  if (!formOpen && compact) {
    return (
      <section data-testid="reviewer-decision-panel" className="text-xs text-brand-text-muted">
        <button type="button" onClick={() => setFormOpen(true)} className="py-2 font-medium text-brand-primary hover:underline">
          {existing ? 'View or edit reviewer note' : 'Disagree with checker result'}
        </button>
        {existing && <p>Reviewer note recorded: {labelFor(existing.decision, DECISION_LABELS)}</p>}
      </section>
    )
  }

  if (!formOpen) {
    return (
      <section
        data-testid="reviewer-decision-panel"
        className="rounded-xl border border-brand-border bg-brand-surface p-4"
      >
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-brand-text">
              <ShieldCheck className="h-4 w-4 text-brand-primary" strokeWidth={1.7} />
              Need to flag the checker result?
            </div>
            <p className="mt-1 text-xs leading-5 text-brand-text-muted">
              Add a reviewer note only when the checker missed evidence, raised the wrong issue, or needs an override.
            </p>
            {existing && (
              <div className="mt-2 inline-flex max-w-full items-center rounded-md border border-brand-border bg-brand-surface-solid px-3 py-1.5 text-xs text-brand-text-muted">
                <span className="truncate">
                  <span className="font-semibold text-brand-text">Reviewer note recorded:</span>{' '}
                  {labelFor(existing.decision, DECISION_LABELS)}
                  {existing.reviewed_at && <span> · {formatDate(existing.reviewed_at)}</span>}
                </span>
              </div>
            )}
          </div>
          <button
            type="button"
            className="self-start text-sm font-semibold text-brand-primary underline-offset-4 transition-colors hover:text-brand-primary/80 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/35 lg:self-auto"
            onClick={() => setFormOpen(true)}
          >
            {existing ? 'View or edit reviewer note' : 'Disagree with checker result'}
          </button>
        </div>
      </section>
    )
  }

  return (
    <section
      data-testid="reviewer-decision-panel"
      className="rounded-xl border border-brand-border bg-brand-surface p-4"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-brand-text">
            <ShieldCheck className="h-4 w-4 text-brand-primary" strokeWidth={1.7} />
            Reviewer decision
          </div>
          <p className="mt-1 text-xs leading-5 text-brand-text-muted">
            Checker output is advisory. Final compliance authority remains with the human evaluator.
          </p>
        </div>
        <button
          type="button"
          className="self-start text-xs font-semibold text-brand-text-muted underline-offset-4 transition-colors hover:text-brand-text hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/35 lg:self-auto"
          onClick={() => setFormOpen(false)}
        >
          Hide reviewer note
        </button>
      </div>

      <form className="mt-4 space-y-4" onSubmit={handleSubmit}>
        {error && <InlineAlert type="warning">{error}</InlineAlert>}
        <div className="grid gap-4 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
          <FormField id="reviewer-decision" label="Reviewer decision">
            {(controlProps) => (
              <select
                id="reviewer-decision"
                className="input-field"
                value={decision}
                onChange={(event) => setDecision(event.target.value)}
                {...controlProps}
              >
                {decisions.map((item) => (
                  <option key={item} value={item}>
                    {labelFor(item, DECISION_LABELS)}
                  </option>
                ))}
              </select>
            )}
          </FormField>

          <FormField id="reviewer-notes" label="Reviewer notes">
            {(controlProps) => (
              <textarea
                id="reviewer-notes"
                className="input-field min-h-20 resize-y"
                value={reviewNotes}
                onChange={(event) => setReviewNotes(event.target.value)}
                placeholder="Record reviewer rationale for the audit trail."
                {...controlProps}
              />
            )}
          </FormField>
        </div>

        <fieldset className="space-y-2">
          <legend className="label-text">Reason codes</legend>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {availableReasons.map((item) => {
              const inputId = `review-reason-${item}`
              return (
                <label
                  key={item}
                  htmlFor={inputId}
                  className="flex min-h-10 items-center gap-2 rounded-md border border-brand-border bg-brand-surface-solid px-3 py-2 text-sm text-brand-text"
                >
                  <input
                    id={inputId}
                    type="checkbox"
                    className="h-4 w-4 rounded border-brand-border text-brand-primary focus:ring-brand-primary"
                    checked={reasonCodes.includes(item)}
                    onChange={() => toggleReason(item)}
                  />
                  <span>{labelFor(item, REASON_LABELS)}</span>
                </label>
              )
            })}
          </div>
        </fieldset>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-xs text-brand-text-muted">
            This records review rationale only; approve or return still uses the action bar below.
          </div>
          <Button type="submit" size="sm" icon={ClipboardCheck} loading={isSubmitting}>
            Record Reviewer Decision
          </Button>
        </div>
      </form>
    </section>
  )
}

export default ReviewerDecisionPanel
