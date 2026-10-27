import { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2, Upload } from 'lucide-react'
import { Button, FormField, InlineAlert, Modal, StyledSelect } from '../../../components'
import { apiErrorMessage, extractApiFieldErrors, hasFieldErrors } from '../../../lib/formErrors'
import * as libraryApi from '../api/libraryApi'

const DOCX_ACCEPT = '.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document'

function emptyForm() {
  return {
    template_subtype: '',
    label: '',
    is_default: true,
  }
}

function placeholderRowsToObject(rows) {
  return rows.reduce((acc, { key, value }) => {
    const trimmedKey = key.trim()
    if (!trimmedKey) return acc
    acc[trimmedKey] = value
    return acc
  }, {})
}

function placeholderDefinitionsToRows(definitions, defaults, existingRows) {
  const existingValues = new Map(
    existingRows
      .map((row) => [row.key.trim(), row.value])
      .filter(([key]) => key),
  )
  const seen = new Set()
  const detectedRows = (definitions || [])
    .filter((definition) => definition?.key)
    .map((definition) => {
      const key = definition.key
      seen.add(key)
      return {
        key,
        value: existingValues.get(key) ?? String(defaults?.[key] ?? ''),
      }
    })

  const extraRows = existingRows.filter((row) => {
    const key = row.key.trim()
    return key && !seen.has(key)
  })
  return [...detectedRows, ...extraRows]
}

export default function TemplateUploadModal({ open, onClose, onSuccess }) {
  const [form, setForm] = useState(emptyForm())
  const [file, setFile] = useState(null)
  const [placeholderRows, setPlaceholderRows] = useState([])
  const [placeholderDefinitions, setPlaceholderDefinitions] = useState([])
  const [placeholderScanMessage, setPlaceholderScanMessage] = useState('')
  const [subtypes, setSubtypes] = useState([])
  const [loadingSubtypes, setLoadingSubtypes] = useState(false)
  const [scanningPlaceholders, setScanningPlaceholders] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const [formErrors, setFormErrors] = useState({})

  useEffect(() => {
    if (!open) return
    setForm(emptyForm())
    setFile(null)
    setPlaceholderRows([])
    setPlaceholderDefinitions([])
    setPlaceholderScanMessage('')
    setFormError('')
    setFormErrors({})
  }, [open])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoadingSubtypes(true)
    libraryApi
      .listTemplateSubtypes()
      .then((response) => {
        if (cancelled) return
        const items = response.data || []
        setSubtypes(items)
        // Pre-select the first available subtype so the form is usable
        // without an extra click.
        setForm((current) => ({
          ...current,
          template_subtype: current.template_subtype || items[0]?.template_subtype || '',
        }))
      })
      .catch(() => {
        if (cancelled) return
        setSubtypes([])
      })
      .finally(() => {
        if (!cancelled) setLoadingSubtypes(false)
      })
    return () => {
      cancelled = true
    }
  }, [open])

  useEffect(() => {
    if (!open || !file || !form.template_subtype) return undefined

    let cancelled = false
    const payload = new FormData()
    payload.append('template_subtype', form.template_subtype)
    payload.append('file', file)

    setScanningPlaceholders(true)
    setPlaceholderScanMessage('')
    setPlaceholderDefinitions([])
    clearFieldError('file')

    libraryApi
      .previewTemplatePlaceholders(payload)
      .then((response) => {
        if (cancelled) return
        const data = response.data || {}
        const definitions = data.placeholder_definitions || []
        const defaults = data.placeholder_defaults || {}
        setPlaceholderDefinitions(definitions)
        setPlaceholderRows((current) => placeholderDefinitionsToRows(definitions, defaults, current))
        setPlaceholderScanMessage(
          definitions.length > 0
            ? `Detected ${definitions.length} placeholder${definitions.length === 1 ? '' : 's'} from this DOCX.`
            : 'No placeholders were detected in this DOCX. You can still add defaults manually.',
        )
      })
      .catch((requestError) => {
        if (cancelled) return
        const fieldErrors = extractApiFieldErrors(requestError)
        setPlaceholderDefinitions([])
        setPlaceholderScanMessage('')
        setFormErrors((current) => ({
          ...current,
          ...fieldErrors,
          file: fieldErrors.file || apiErrorMessage(requestError, 'Unable to scan this DOCX.'),
        }))
        setFormError('Unable to scan the template placeholders before upload.')
      })
      .finally(() => {
        if (!cancelled) setScanningPlaceholders(false)
      })

    return () => {
      cancelled = true
    }
  }, [file, form.template_subtype, open])

  const selectedSubtype = useMemo(
    () => subtypes.find((item) => item.template_subtype === form.template_subtype),
    [form.template_subtype, subtypes],
  )

  const acceptedExtension = selectedSubtype?.allowed_extension
    ? `.${selectedSubtype.allowed_extension}`
    : DOCX_ACCEPT

  const clearFieldError = (field) => {
    setFormErrors((current) => {
      if (!current[field]) return current
      const next = { ...current }
      delete next[field]
      return next
    })
  }

  const updateField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }))
    clearFieldError(field)
  }

  const handleFileChange = (event) => {
    const nextFile = event.target.files?.[0] || null
    setFile(nextFile)
    setPlaceholderDefinitions([])
    setPlaceholderScanMessage('')
    if (!nextFile) {
      setPlaceholderRows([])
    }
    clearFieldError('file')
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

    const localErrors = {}
    if (!form.template_subtype) {
      localErrors.template_subtype = 'Template subtype is required.'
    }
    if (!file) {
      localErrors.file = 'Choose a DOCX template file before uploading.'
    }
    if (hasFieldErrors(localErrors)) {
      setFormErrors(localErrors)
      setFormError('Please correct the highlighted fields.')
      return
    }

    setSubmitting(true)
    setFormError('')
    setFormErrors({})

    const payload = new FormData()
    payload.append('reference_type', 'template')
    payload.append('template_subtype', form.template_subtype)
    if (form.label) payload.append('label', form.label)
    payload.append('is_default', String(Boolean(form.is_default)))
    const placeholderDefaults = placeholderRowsToObject(placeholderRows)
    if (Object.keys(placeholderDefaults).length > 0) {
      payload.append('placeholder_defaults', JSON.stringify(placeholderDefaults))
    }
    payload.append('file', file)

    try {
      const response = await libraryApi.createReference(payload)
      onSuccess?.(response)
    } catch (requestError) {
      const fieldErrors = extractApiFieldErrors(requestError)
      setFormErrors(fieldErrors)
      setFormError(
        hasFieldErrors(fieldErrors)
          ? 'Please correct the highlighted fields.'
          : apiErrorMessage(requestError, 'Unable to upload the template.'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      title="Upload template"
      description="Upload a DOCX template, choose its subtype, and optionally seed placeholder defaults."
      size="lg"
      onClose={onClose}
    >
      <InlineAlert type="error" className="mb-4" onDismiss={() => setFormError('')}>
        {formError}
      </InlineAlert>
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <FormField
          id="template-upload-subtype"
          label="Template subtype"
          required
          error={formErrors.template_subtype}
          hint={selectedSubtype?.description}
        >
          {(controlProps) => (
            <StyledSelect
              id="template-upload-subtype"
              value={form.template_subtype}
              onChange={(event) => updateField('template_subtype', event.target.value)}
              options={subtypes.map((option) => ({
                value: option.template_subtype,
                label: option.label,
              }))}
              placeholder="Select subtype"
              disabled={loadingSubtypes}
              error={Boolean(formErrors.template_subtype)}
              {...controlProps}
            />
          )}
        </FormField>
        <FormField id="template-upload-label" label="Label" error={formErrors.label}>
          {(controlProps) => (
            <input
              id="template-upload-label"
              className="input-field"
              value={form.label}
              onChange={(event) => updateField('label', event.target.value)}
              placeholder="Display name for this template version"
              {...controlProps}
            />
          )}
        </FormField>
        <FormField id="template-upload-file" label="Template file" required error={formErrors.file}>
          {(controlProps) => (
            <label
              htmlFor="template-upload-file"
              className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-brand-border px-3 py-3 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800/50"
            >
              <Upload className="h-4 w-4" strokeWidth={1.5} />
              {file ? file.name : 'Upload DOCX template file'}
              <input
                id="template-upload-file"
                className="sr-only"
                type="file"
                accept={acceptedExtension}
                onChange={handleFileChange}
                {...controlProps}
              />
            </label>
          )}
        </FormField>
        {scanningPlaceholders && (
          <p className="text-xs text-brand-text-muted">Scanning placeholders from the selected DOCX...</p>
        )}
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          <input
            type="checkbox"
            checked={form.is_default}
            onChange={(event) => updateField('is_default', event.target.checked)}
          />
          Use as default template for this subtype
        </label>
        <FormField
          id="template-upload-placeholders"
          label="Placeholder defaults"
          hint="Pre-fill placeholder values for this template. Keys must match placeholders inside the DOCX."
          error={formErrors.placeholder_defaults}
        >
          <div className="space-y-2">
            {placeholderScanMessage && (
              <p className="text-xs text-brand-text-muted">{placeholderScanMessage}</p>
            )}
            {placeholderRows.length === 0 && (
              <p className="text-xs text-brand-text-muted">
                No defaults yet. Add a row to seed values for placeholders found inside the DOCX.
              </p>
            )}
            {placeholderRows.map((row, index) => (
              <div key={index} className="grid grid-cols-1 gap-2 md:grid-cols-[1fr_2fr_auto]">
                <input
                  className="input-field"
                  placeholder="placeholder_key"
                  value={row.key}
                  title={placeholderDefinitions.find((item) => item.key === row.key)?.label || row.key}
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
          <Button type="submit" icon={Upload} loading={submitting} disabled={scanningPlaceholders}>
            Upload template
          </Button>
        </div>
      </form>
    </Modal>
  )
}
