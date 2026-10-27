import { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Button, FormField, InlineAlert, Modal } from '../../../components'
import { formatMachineLabel } from '../../../lib/formatters'
import { apiErrorMessage, extractApiFieldErrors, hasFieldErrors } from '../../../lib/formErrors'
import * as libraryApi from '../api/libraryApi'

function objectToRows(object) {
  return Object.entries(object || {}).map(([key, value]) => ({ key, value: String(value ?? '') }))
}

function rowsToObject(rows) {
  return rows.reduce((acc, { key, value }) => {
    const trimmed = key.trim()
    if (!trimmed) return acc
    acc[trimmed] = value
    return acc
  }, {})
}

function buildInitialState(reference) {
  const definitions = Array.isArray(reference?.placeholder_definitions)
    ? reference.placeholder_definitions
    : []
  const definitionRows = definitions
    .filter((definition) => definition?.key)
    .map((definition) => ({
      key: definition.key,
      value: String(reference?.placeholder_defaults?.[definition.key] ?? ''),
    }))

  // Include any extra defaults that are not in the canonical definition
  // list so existing values don't silently disappear.
  const knownKeys = new Set(definitionRows.map((row) => row.key))
  const extras = Object.entries(reference?.placeholder_defaults || {})
    .filter(([key]) => !knownKeys.has(key))
    .map(([key, value]) => ({ key, value: String(value ?? '') }))

  return {
    label: reference?.template_label || reference?.title || '',
    is_default: !!reference?.is_default,
    placeholderRows: definitionRows.length || extras.length
      ? [...definitionRows, ...extras]
      : objectToRows(reference?.placeholder_defaults),
  }
}

export default function TemplateEditModal({ open, reference, onClose, onSuccess }) {
  const [label, setLabel] = useState('')
  const [isDefault, setIsDefault] = useState(false)
  const [placeholderRows, setPlaceholderRows] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const [formErrors, setFormErrors] = useState({})

  useEffect(() => {
    if (!open || !reference) return
    const initial = buildInitialState(reference)
    setLabel(initial.label)
    setIsDefault(initial.is_default)
    setPlaceholderRows(initial.placeholderRows)
    setFormError('')
    setFormErrors({})
  }, [open, reference])

  const definitionLabels = useMemo(() => {
    const map = {}
    for (const definition of reference?.placeholder_definitions || []) {
      if (definition?.key) {
        map[definition.key] = definition.label || formatMachineLabel(definition.key)
      }
    }
    return map
  }, [reference])

  const clearFieldError = (field) => {
    setFormErrors((current) => {
      if (!current[field]) return current
      const next = { ...current }
      delete next[field]
      return next
    })
  }

  const updatePlaceholderRow = (index, field, value) => {
    setPlaceholderRows((current) => {
      const next = [...current]
      next[index] = { ...next[index], [field]: value }
      return next
    })
    clearFieldError('placeholder_defaults')
  }

  const addPlaceholderRow = () => {
    setPlaceholderRows((current) => [...current, { key: '', value: '' }])
  }

  const removePlaceholderRow = (index) => {
    setPlaceholderRows((current) => current.filter((_, i) => i !== index))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!reference?.reference_uri) return

    setSubmitting(true)
    setFormError('')
    setFormErrors({})

    const payload = new FormData()
    payload.append('reference_type', 'template')
    payload.append('label', label.trim())
    payload.append('is_default', String(Boolean(isDefault)))
    payload.append('placeholder_defaults', JSON.stringify(rowsToObject(placeholderRows)))

    try {
      const response = await libraryApi.updateReference(reference.reference_uri, payload)
      onSuccess?.(response)
    } catch (requestError) {
      const fieldErrors = extractApiFieldErrors(requestError)
      setFormErrors(fieldErrors)
      setFormError(
        hasFieldErrors(fieldErrors)
          ? 'Please correct the highlighted fields.'
          : apiErrorMessage(requestError, 'Unable to update the template.'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open && !!reference}
      title={reference?.template_label ? `Edit ${reference.template_label}` : 'Edit template'}
      description="Update the display label, default flag, and placeholder defaults."
      size="lg"
      onClose={onClose}
    >
      {reference && (
        <>
          <InlineAlert type="error" className="mb-4" onDismiss={() => setFormError('')}>
            {formError}
          </InlineAlert>
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div className="rounded-lg border border-brand-border bg-brand-surface px-3 py-2 text-sm text-brand-text-muted">
              <p className="font-medium text-brand-text">{reference.file_name || 'Template DOCX'}</p>
              <p className="mt-1 text-xs">
                Subtype: {reference.template_subtype_label || formatMachineLabel(reference.template_subtype)}
              </p>
            </div>
            <FormField id="template-edit-label" label="Label" error={formErrors.label}>
              {(controlProps) => (
                <input
                  id="template-edit-label"
                  className="input-field"
                  value={label}
                  onChange={(event) => {
                    setLabel(event.target.value)
                    clearFieldError('label')
                  }}
                  {...controlProps}
                />
              )}
            </FormField>
            <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                checked={isDefault}
                onChange={(event) => {
                  setIsDefault(event.target.checked)
                  clearFieldError('is_default')
                }}
              />
              Use as default template for this subtype
            </label>
            <FormField
              id="template-edit-placeholders"
              label="Placeholder defaults"
              hint="Edit values that pre-fill when this template is applied."
              error={formErrors.placeholder_defaults}
            >
              <div className="space-y-2">
                {placeholderRows.length === 0 && (
                  <p className="text-xs text-brand-text-muted">
                    No placeholders configured yet.
                  </p>
                )}
                {placeholderRows.map((row, index) => (
                  <div key={index} className="grid grid-cols-1 gap-2 md:grid-cols-[1fr_2fr_auto]">
                    <input
                      className="input-field"
                      placeholder="placeholder_key"
                      value={row.key}
                      title={definitionLabels[row.key] || row.key}
                      onChange={(event) => updatePlaceholderRow(index, 'key', event.target.value)}
                    />
                    <input
                      className="input-field"
                      placeholder="Default value"
                      value={row.value}
                      onChange={(event) => updatePlaceholderRow(index, 'value', event.target.value)}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      icon={Trash2}
                      onClick={() => removePlaceholderRow(index)}
                      aria-label={`Remove placeholder default ${index + 1}`}
                    >
                      Remove
                    </Button>
                  </div>
                ))}
                <Button type="button" variant="outline" size="sm" icon={Plus} onClick={addPlaceholderRow}>
                  Add placeholder default
                </Button>
              </div>
            </FormField>
            <div className="flex flex-wrap justify-end gap-3">
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" loading={submitting}>
                Save template
              </Button>
            </div>
          </form>
        </>
      )}
    </Modal>
  )
}
