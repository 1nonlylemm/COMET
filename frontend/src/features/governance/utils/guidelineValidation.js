const VALID_GUIDELINE_TYPES = new Set([
  'memorandum',
  'circular',
  'annex',
  'local_budget_circular',
  'omnibus_guideline',
  'other',
])

const ALLOWED_UPLOAD_EXTENSIONS = new Set([
  'pdf',
  'doc',
  'docx',
  'xls',
  'xlsx',
  'ppt',
  'pptx',
  'jpg',
  'jpeg',
  'png',
  'csv',
])

function cleanText(value) {
  if (value === null || value === undefined) {
    return ''
  }
  return String(value).trim()
}

function isValidDateString(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false
  }
  const [year, month, day] = value.split('-').map(Number)
  const candidate = new Date(Date.UTC(year, month - 1, day))
  return (
    candidate.getUTCFullYear() === year &&
    candidate.getUTCMonth() === month - 1 &&
    candidate.getUTCDate() === day
  )
}

function isExternalUrl(value) {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

function uploadExtension(file) {
  const name = file?.name || ''
  const dotIndex = name.lastIndexOf('.')
  if (dotIndex === -1) {
    return ''
  }
  return name.slice(dotIndex + 1).toLowerCase()
}

export function validateGuidelineForm(form, uploadFile) {
  const errors = {}
  const programId = cleanText(form.program_id)
  const title = cleanText(form.title)
  const guidelineType = cleanText(form.guideline_type)
  const effectiveDate = cleanText(form.effective_date)
  const filePath = cleanText(form.file_path)

  if (!programId) {
    errors.program_id = 'Program is required.'
  }
  if (!title) {
    errors.title = 'Title is required.'
  }
  if (!guidelineType) {
    errors.guideline_type = 'Type is required.'
  } else if (!VALID_GUIDELINE_TYPES.has(guidelineType)) {
    errors.guideline_type = 'Select a supported reference type.'
  }
  if (effectiveDate && !isValidDateString(effectiveDate)) {
    errors.effective_date = 'Effective date must use YYYY-MM-DD.'
  }
  if (filePath && !isExternalUrl(filePath)) {
    errors.file_path = 'Use an http:// or https:// URL, or upload the file instead.'
  }
  if (uploadFile && !ALLOWED_UPLOAD_EXTENSIONS.has(uploadExtension(uploadFile))) {
    errors.file = 'Upload a PDF, Office document, image, or CSV file.'
  }

  return errors
}

export function buildGuidelinePayload(form, uploadFile, options = {}) {
  const { preserveStoredFilePath = false } = options
  const payload = new FormData()
  const fields = {
    program_id: cleanText(form.program_id),
    title: cleanText(form.title),
    guideline_type: cleanText(form.guideline_type),
    reference_number: cleanText(form.reference_number),
    issuing_body: cleanText(form.issuing_body),
    effective_date: cleanText(form.effective_date),
    is_current: Boolean(form.is_current),
    file_name: cleanText(form.file_name),
    file_path: cleanText(form.file_path),
    description: cleanText(form.description),
  }

  Object.entries(fields).forEach(([key, value]) => {
    if (key === 'file_path' && preserveStoredFilePath && !value && !uploadFile) {
      return
    }
    payload.append(key, value)
  })
  if (uploadFile) {
    payload.append('file', uploadFile)
  }
  return payload
}
