import { useId, useState } from 'react'

const LABELS = { confirmed: 'Confirmed', incorrect_flag: 'Incorrect flag', needs_verification: 'Needs verification' }

export function FindingDecision({ finding, review, disabled, saving, onSave }) {
  const id = useId()
  const [status, setStatus] = useState(review?.status || 'needs_verification')
  const [note, setNote] = useState(review?.note || '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  if (!onSave) return null
  const save = async () => {
    if (status === 'incorrect_flag' && !note.trim()) { setError('Explain why this is an incorrect flag.'); return }
    setError('')
    setBusy(true)
    try {
      const result = await onSave({ finding_id: String(finding.id || finding.finding_id), status, note: note.trim() })
      if (result === false) setError('Decision was not saved. See the review error above.')
    } catch {
      setError('Unable to save the finding decision. Try again.')
    } finally { setBusy(false) }
  }
  return <details className="border-t border-brand-border pt-2 text-xs">
    <summary className="cursor-pointer py-1 font-medium text-brand-primary">Reviewer decision{review ? ` · ${LABELS[review.status] || review.status}` : ''}</summary>
    <div className="mt-2 space-y-2">
      <label className="block" htmlFor={`${id}-status`}>Decision</label>
      <select id={`${id}-status`} className="input-field w-full" value={status} disabled={disabled || saving || busy} onChange={event => setStatus(event.target.value)}>
        {Object.entries(LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <label className="block" htmlFor={`${id}-note`}>Reason{status === 'incorrect_flag' ? ' (required)' : ' (optional)'}</label>
      <textarea id={`${id}-note`} className="input-field w-full" rows={2} maxLength={2000} value={note} disabled={disabled || saving || busy} onChange={event => setNote(event.target.value)} />
      {error && <p role="alert" className="text-red-700 dark:text-red-300">{error}</p>}
      {review && <p className="text-brand-text-muted">Saved decision: {LABELS[review.status]}. {review.note}</p>}
      <button type="button" className="btn-outline px-3 py-2" disabled={disabled || saving || busy} onClick={save}>{busy || saving ? 'Saving…' : 'Save finding decision'}</button>
      <p className="text-brand-text-muted">Records your assessment of this finding. Approval and return remain separate actions.</p>
    </div>
  </details>
}
