import { useEffect, useState } from 'react'
import { Upload } from 'lucide-react'
import {
  Button,
  FormField,
  InlineAlert,
  Modal,
  StyledDateInput,
  StyledSelect,
} from '../../../components'
import { apiErrorMessage, extractApiFieldErrors, hasFieldErrors } from '../../../lib/formErrors'
import {
  buildGuidelinePayload,
  validateGuidelineForm,
} from '../../governance/utils/guidelineValidation'
import * as libraryApi from '../api/libraryApi'
import * as programApi from '../../programs/api/programApi'

// Six valid Reference_Type values minus 'template'. Templates have a
// dedicated upload form because they require a different field set
// (DOCX file, template_subtype, placeholder defaults).
const VIEW_ONLY_REFERENCE_TYPES = [
  { value: 'memorandum', label: 'Memorandum' },
  { value: 'circular', label: 'Circular' },
  { value: 'annex', label: 'Annex' },
  { value: 'local_budget_circular', label: 'Local Budget Circular' },
  { value: 'omnibus_guideline', label: 'Omnibus Guideline' },
  { value: 'other', label: 'Other' },
]

const DOCUMENT_UPLOAD_ACCEPT = '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.csv'

const EMPTY_FORM = {
  program_id: '',
  title: '',
  reference_type: 'memorandum',
  reference_number: '',
  issuing_body: '',
  effective_date: '',
  is_current: true,
  file_name: '',
  file_path: '',
  description: '',
}

function buildReferencePayload(form, uploadFile, options = {}) {
  // Reuse the guideline payload builder so multipart shape stays in
  // lock-step with the legacy /api/governance/guidelines route. The
  // only public-facing rename is reference_type -> guideline_type for
  // the underlying program_guidelines record; the library backend
  // accepts reference_type directly, so we send both names so a single
  // FormData works against either shape.
  const guidelineForm = {
    ...form,
    guideline_type: form.reference_type,
  }
  const payload = buildGuidelinePayload(guidelineForm, uploadFile, options)
  payload.append('reference_type', form.reference_type)
  return payload
}

function isExternalReference(value) {
  return value?.startsWith('http://') || value?.startsWith('https://')
}

export default function ReferenceCreateModal({
  open,
  onClose,
  onSuccess,
  defaultReferenceType,
  editingReference = null,
}) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [uploadFile, setUploadFile] = useState(null)
  const [existingFilePath, setExistingFilePath] = useState('')
  const [programs, setPrograms] = useState([])
  const [loadingPrograms, setLoadingPrograms] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const [formErrors, setFormErrors] = useState({})

  const isEditing = Boolean(editingReference?.reference_uri)

  useEffect(() => {
    if (!open) return
    if (editingReference) {
      const filePath = editingReference.file_path || ''
      const isExternal = isExternalReference(filePath)
      setForm({
        program_id: editingReference.program_id ?? '',
        title: editingReference.title || '',
        reference_type: editingReference.reference_type || EMPTY_FORM.reference_type,
        reference_number: editingReference.reference_number || '',
        issuing_body: editingReference.issuing_body || '',
        effective_date: editingReference.effective_date || '',
        is_current: editingReference.is_current ?? true,
        file_name: editingReference.file_name || '',
        file_path: isExternal ? filePath : '',
        description: editingReference.description || '',
      })
      setExistingFilePath(filePath)
    } else {
      setForm({
        ...EMPTY_FORM,
        reference_type: defaultReferenceType && defaultReferenceType !== 'template'
          ? defaultReferenceType
          : EMPTY_FORM.reference_type,
      })
      setExistingFilePath('')
    }
    setUploadFile(null)
    setFormError('')
    setFormErrors({})
  }, [open, defaultReferenceType, editingReference])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoadingPrograms(true)
    programApi
      .listPrograms({ per_page: 100 })
      .then((response) => {
        if (cancelled) return
        setPrograms(response.data || [])
      })
      .catch(() => {
        if (cancelled) return
        setPrograms([])
      })
      .finally(() => {
        if (!cancelled) setLoadingPrograms(false)
      })
    return () => {
      cancelled = true
    }
  }, [open])

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

  const handleUploadChange = (event) => {
    setUploadFile(event.target.files?.[0] || null)
    clearFieldError('file')
  }

  const handleSubmit = async (event) => {
    event.preventDefault()

    // Reuse the existing client-side guideline validator so the user
    // sees the same field-scoped errors they got on the legacy page.
    const guidelineForm = {
      ...form,
      guideline_type: form.reference_type,
    }
    const validationErrors = validateGuidelineForm(guidelineForm, uploadFile)
    if (validationErrors.guideline_type) {
      validationErrors.reference_type = validationErrors.guideline_type
      delete validationErrors.guideline_type
    }
    if (hasFieldErrors(validationErrors)) {
      setFormErrors(validationErrors)
      setFormError('Please correct the highlighted fields.')
      return
    }

    setSubmitting(true)
    setFormError('')
    setFormErrors({})

    try {
      const payload = buildReferencePayload(form, uploadFile, {
        preserveStoredFilePath: Boolean(
          isEditing && existingFilePath && !isExternalReference(existingFilePath),
        ),
      })
      const response = isEditing
        ? await libraryApi.updateReference(editingReference.reference_uri, payload)
        : await libraryApi.createReference(payload)
      onSuccess?.(response)
    } catch (requestError) {
      const fieldErrors = extractApiFieldErrors(requestError)
      // Translate guideline_type -> reference_type for any 422 echo
      // coming from the legacy validator path.
      if (fieldErrors.guideline_type && !fieldErrors.reference_type) {
        fieldErrors.reference_type = fieldErrors.guideline_type
        delete fieldErrors.guideline_type
      }
      setFormErrors(fieldErrors)
      setFormError(
        hasFieldErrors(fieldErrors)
          ? 'Please correct the highlighted fields.'
          : apiErrorMessage(requestError, 'Unable to save the reference item.'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      title={isEditing ? 'Edit reference' : 'Add reference'}
      description={
        isEditing
          ? 'Update the metadata for this reference. Replace the file or external URL only if needed.'
          : 'Create a memorandum, circular, annex, or other view-only reference. To upload a reusable template, use the Upload Template action.'
      }
      size="xl"
      onClose={onClose}
    >
      <InlineAlert type="error" className="mb-4" onDismiss={() => setFormError('')}>
        {formError}
      </InlineAlert>
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <FormField id="reference-program" label="Program" required error={formErrors.program_id}>
            {(controlProps) => (
              <StyledSelect
                id="reference-program"
                value={form.program_id}
                onChange={(event) => updateField('program_id', event.target.value)}
                options={programs.map((p) => ({ value: p.id, label: p.name }))}
                placeholder="Select program"
                searchable
                disabled={loadingPrograms}
                error={Boolean(formErrors.program_id)}
                {...controlProps}
              />
            )}
          </FormField>
          <FormField id="reference-type" label="Reference type" required error={formErrors.reference_type}>
            {(controlProps) => (
              <StyledSelect
                id="reference-type"
                value={form.reference_type}
                onChange={(event) => updateField('reference_type', event.target.value)}
                options={VIEW_ONLY_REFERENCE_TYPES}
                placeholder="Select type"
                error={Boolean(formErrors.reference_type)}
                {...controlProps}
              />
            )}
          </FormField>
          <FormField id="reference-effective-date" label="Effective date" error={formErrors.effective_date}>
            {(controlProps) => (
              <StyledDateInput
                id="reference-effective-date"
                value={form.effective_date}
                onChange={(event) => updateField('effective_date', event.target.value)}
                error={Boolean(formErrors.effective_date)}
                {...controlProps}
              />
            )}
          </FormField>
          <FormField id="reference-title" label="Title" required error={formErrors.title} className="md:col-span-2">
            {(controlProps) => (
              <input
                id="reference-title"
                className="input-field"
                value={form.title}
                onChange={(event) => updateField('title', event.target.value)}
                {...controlProps}
              />
            )}
          </FormField>
          <FormField id="reference-number" label="Reference number" error={formErrors.reference_number}>
            {(controlProps) => (
              <input
                id="reference-number"
                className="input-field"
                value={form.reference_number}
                onChange={(event) => updateField('reference_number', event.target.value)}
                {...controlProps}
              />
            )}
          </FormField>
          <FormField id="reference-issuing-body" label="Issuing body" error={formErrors.issuing_body}>
            {(controlProps) => (
              <input
                id="reference-issuing-body"
                className="input-field"
                value={form.issuing_body}
                onChange={(event) => updateField('issuing_body', event.target.value)}
                {...controlProps}
              />
            )}
          </FormField>
          <FormField id="reference-file-name" label="File name" error={formErrors.file_name}>
            {(controlProps) => (
              <input
                id="reference-file-name"
                className="input-field"
                value={form.file_name}
                onChange={(event) => updateField('file_name', event.target.value)}
                {...controlProps}
              />
            )}
          </FormField>
          <FormField
            id="reference-file-path"
            label="External URL (use instead of upload)"
            error={formErrors.file_path}
            className="md:col-span-3"
          >
            {(controlProps) => (
              <input
                id="reference-file-path"
                className="input-field"
                placeholder="https://example.com/document.pdf"
                value={form.file_path}
                onChange={(event) => updateField('file_path', event.target.value)}
                {...controlProps}
              />
            )}
          </FormField>
          <FormField id="reference-file" label="Upload file" error={formErrors.file} className="md:col-span-3">
            {(controlProps) => (
              <label
                htmlFor="reference-file"
                className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-brand-border px-3 py-3 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800/50"
              >
                <Upload className="h-4 w-4" strokeWidth={1.5} />
                {uploadFile ? uploadFile.name : 'Upload memorandum, circular, annex, or other reference file'}
                <input
                  id="reference-file"
                  className="sr-only"
                  type="file"
                  accept={DOCUMENT_UPLOAD_ACCEPT}
                  onChange={handleUploadChange}
                  {...controlProps}
                />
              </label>
            )}
          </FormField>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          <input
            type="checkbox"
            checked={form.is_current}
            onChange={(event) => updateField('is_current', event.target.checked)}
          />
          Treat as current issuance
        </label>
        <FormField id="reference-description" label="Description or reviewer notes" error={formErrors.description}>
          {(controlProps) => (
            <textarea
              id="reference-description"
              className="input-field min-h-[96px]"
              value={form.description}
              onChange={(event) => updateField('description', event.target.value)}
              {...controlProps}
            />
          )}
        </FormField>
        <div className="flex flex-wrap justify-end gap-3">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={submitting}>
            {isEditing ? 'Update Reference' : 'Save Reference'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
