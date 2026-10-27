import { Sparkles, XCircle } from 'lucide-react'
import { Button } from '../../../../components'
import { AiRewriteControl } from '../../../ai/components/AiRewriteControl'

/**
 * RevisionNotesPanel — slide-down panel under the action bar that lets the
 * reviewer compose return notes (with AI rewrite) before confirming the
 * Return for Revision action.
 */
export function RevisionNotesPanel({
  open,
  value,
  onChange,
  onCancel,
  onConfirm,
  isConfirming,
  hasSuggestedNotes,
  onApplySuggestedNotes,
  disabled,
}) {
  if (!open) return null
  return (
    <div
      data-testid="revision-notes-panel"
      className="rounded-xl border border-amber-300 bg-amber-50/40 p-4 dark:border-amber-300/40 dark:bg-amber-300/5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-brand-text">Return Notes</div>
          <p className="text-xs text-brand-text-muted">
            Explain what must be corrected or resubmitted. The notes are sent with the return action.
          </p>
        </div>
        {hasSuggestedNotes && (
          <Button size="sm" variant="ghost" icon={Sparkles} onClick={onApplySuggestedNotes}>
            Use Checker Notes
          </Button>
        )}
      </div>
      <div className="mt-3">
        <AiRewriteControl
          label="Return Notes"
          value={value}
          onTextChange={onChange}
          contextLabel="Requirement revision notes"
          disabled={disabled || isConfirming}
          placeholder="Explain what must be corrected or resubmitted."
          autoFocus
        >
          <Button size="sm" variant="outline" disabled={isConfirming} onClick={onCancel}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant="warning"
            icon={XCircle}
            loading={Boolean(isConfirming)}
            disabled={disabled}
            onClick={onConfirm}
          >
            Confirm Return
          </Button>
        </AiRewriteControl>
      </div>
    </div>
  )
}

export default RevisionNotesPanel
