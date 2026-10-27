export function isWorkflowNotApplicableError(error) {
  if (!error) return false
  const status = error.response?.status
  if (status === 404) return true
  if (status === 422) {
    const data = error.response?.data || {}
    const msg = String(data.message || data.error || error.message || '').toLowerCase()
    return (
      msg.includes('document_category') ||
      msg.includes('not part of the shared document workflow')
    )
  }
  return false
}
