import { useState } from 'react'
import { AlertCircle, Plus, Trash2, Undo2 } from 'lucide-react'
import { Button, Modal } from '../../../components'
import { DEFICIENCY_CATEGORY_LABELS } from './workflowStatus'

const INITIAL_ITEM = {
  category: 'missing_attachment',
  finding_observation: '',
  corrective_instruction: '',
}

export function ReturnForRevisionModal({
  open,
  onClose,
  onSubmit,
  requirementName,
  loading = false,
  initialDeficiencies = null,
}) {
  const [deficiencies, setDeficiencies] = useState([{ ...INITIAL_ITEM }])
  const [summaryReason, setSummaryReason] = useState('')
  const [validationError, setValidationError] = useState('')
  const [prevOpen, setPrevOpen] = useState(open)
  const [prevInitial, setPrevInitial] = useState(initialDeficiencies)

  if (open !== prevOpen || initialDeficiencies !== prevInitial) {
    setPrevOpen(open)
    setPrevInitial(initialDeficiencies)
    if (open && initialDeficiencies && initialDeficiencies.length > 0) {
      setDeficiencies(
        initialDeficiencies.map((d) => ({
          category: d.deficiency_category || d.category || 'missing_attachment',
          finding_observation: d.finding_observation || d.message || '',
          corrective_instruction: d.corrective_instruction || d.detail || '',
        }))
      )
    } else if (open && (!initialDeficiencies || initialDeficiencies.length === 0)) {
      setDeficiencies([{ ...INITIAL_ITEM }])
    }
  }

  const handleAddItem = () => {
    setDeficiencies((prev) => [...prev, { ...INITIAL_ITEM }])
    setValidationError('')
  }

  const handleRemoveItem = (index) => {
    if (deficiencies.length <= 1) return
    setDeficiencies((prev) => prev.filter((_, idx) => idx !== index))
    setValidationError('')
  }

  const handleItemChange = (index, field, value) => {
    setDeficiencies((prev) => {
      const next = [...prev]
      next[index] = { ...next[index], [field]: value }
      return next
    })
    setValidationError('')
  }

  const handleSubmit = (e) => {
    e.preventDefault()

    // Validate each deficiency item
    for (let i = 0; i < deficiencies.length; i++) {
      const item = deficiencies[i]
      if (!item.finding_observation.trim()) {
        setValidationError(`Finding observation is required for Deficiency Item #${i + 1}.`)
        return
      }
      if (!item.corrective_instruction.trim()) {
        setValidationError(`Corrective action instruction is required for Deficiency Item #${i + 1}.`)
        return
      }
    }

    onSubmit({
      reason: summaryReason.trim() || undefined,
      deficiencies: deficiencies.map((d) => ({
        category: d.category,
        finding_observation: d.finding_observation.trim(),
        corrective_instruction: d.corrective_instruction.trim(),
      })),
    })
  }

  const handleClose = () => {
    setDeficiencies([{ ...INITIAL_ITEM }])
    setSummaryReason('')
    setValidationError('')
    onClose()
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Return Requirement for Revision"
      description={requirementName ? `Returning "${requirementName}" to the LGU for documentary correction` : undefined}
      size="xl"
      footer={
        <div className="flex items-center justify-between gap-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            icon={Plus}
            onClick={handleAddItem}
            disabled={loading}
          >
            Add Another Finding
          </Button>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleClose}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="warning"
              size="sm"
              icon={Undo2}
              onClick={handleSubmit}
              disabled={loading}
            >
              {loading ? 'Submitting...' : 'Submit Return for Revision'}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
          <p className="font-medium">Documentary Review & Deficiency Finding Notice (Annex E)</p>
          <p className="mt-0.5">
            Specify each discrete deficiency observed during verification. The LGU Focal Person and assigned Field Officer will receive these actionable items to prepare and resubmit a corrected version.
          </p>
        </div>

        {validationError && (
          <div className="flex items-center gap-2 rounded-md border border-rose-200 bg-rose-50 p-2.5 text-xs text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-300">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{validationError}</span>
          </div>
        )}

        <div className="space-y-3">
          {deficiencies.map((item, index) => (
            <div
              key={index}
              className="rounded-lg border border-brand-border bg-brand-surface p-3.5 space-y-3"
            >
              <div className="flex items-center justify-between border-b border-brand-border/60 pb-2">
                <span className="text-xs font-semibold text-brand-text">
                  Deficiency Item #{index + 1}
                </span>
                {deficiencies.length > 1 && (
                  <button
                    type="button"
                    onClick={() => handleRemoveItem(index)}
                    className="flex items-center gap-1 text-xs text-rose-600 hover:text-rose-700 dark:text-rose-400"
                    title="Remove item"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    <span>Remove</span>
                  </button>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-brand-text-muted mb-1">
                  Deficiency Category <span className="text-rose-600 dark:text-rose-300">*</span>
                </label>
                <select
                  className="input-field w-full text-xs"
                  value={item.category}
                  onChange={(e) => handleItemChange(index, 'category', e.target.value)}
                  disabled={loading}
                >
                  {Object.entries(DEFICIENCY_CATEGORY_LABELS).map(([catKey, label]) => (
                    <option key={catKey} value={catKey}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-brand-text-muted mb-1">
                  Finding / Observation <span className="text-rose-600 dark:text-rose-300">*</span>
                </label>
                <textarea
                  rows={2}
                  className="input-field w-full text-xs"
                  placeholder="Describe the specific missing element, defect, or inconsistency identified..."
                  value={item.finding_observation}
                  onChange={(e) => handleItemChange(index, 'finding_observation', e.target.value)}
                  disabled={loading}
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-brand-text-muted mb-1">
                  Corrective Action Required <span className="text-rose-600 dark:text-rose-300">*</span>
                </label>
                <textarea
                  rows={2}
                  className="input-field w-full text-xs"
                  placeholder="Provide concrete instructions for the LGU to cure this deficiency..."
                  value={item.corrective_instruction}
                  onChange={(e) => handleItemChange(index, 'corrective_instruction', e.target.value)}
                  disabled={loading}
                />
              </div>
            </div>
          ))}
        </div>

        <div>
          <label className="block text-xs font-medium text-brand-text-muted mb-1">
            Overall Transmittal Remarks <span className="text-brand-text-muted/70">(Optional Summary)</span>
          </label>
          <input
            type="text"
            className="input-field w-full text-xs"
            placeholder="High-level return transmittal note (auto-synthesized if left blank)..."
            value={summaryReason}
            onChange={(e) => setSummaryReason(e.target.value)}
            disabled={loading}
          />
        </div>
      </div>
    </Modal>
  )
}
