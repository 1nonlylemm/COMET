function stringifyErrorValue(value) {
  if (Array.isArray(value)) {
    return value.map(stringifyErrorValue).filter(Boolean).join(', ')
  }
  if (value && typeof value === 'object') {
    return Object.values(value).map(stringifyErrorValue).filter(Boolean).join(', ')
  }
  if (value === null || value === undefined) {
    return ''
  }
  return String(value)
}

export function normalizeFieldErrors(errors) {
  if (!errors || typeof errors !== 'object') {
    return {}
  }
  return Object.entries(errors).reduce((normalized, [field, value]) => {
    const message = stringifyErrorValue(value)
    if (message) {
      normalized[field] = message
    }
    return normalized
  }, {})
}

export function extractApiFieldErrors(error) {
  return normalizeFieldErrors(error?.response?.data?.errors)
}

export function firstFieldError(errors) {
  const normalized = normalizeFieldErrors(errors)
  return Object.values(normalized).find(Boolean) || ''
}

export function apiErrorMessage(error, fallback = 'Unable to complete this action.') {
  const data = error?.response?.data
  const fieldMessage = firstFieldError(data?.errors)
  const rawMessage = (typeof data === 'object' && data !== null)
    ? (data.message || data.msg || data.detail)
    : (typeof data === 'string' ? data : '')
  const message = stringifyErrorValue(rawMessage)

  if (fieldMessage && (!message || message.toLowerCase() === 'validation failed')) {
    return fieldMessage
  }
  return message || fieldMessage || fallback
}

export function hasFieldErrors(errors) {
  return Object.keys(normalizeFieldErrors(errors)).length > 0
}
