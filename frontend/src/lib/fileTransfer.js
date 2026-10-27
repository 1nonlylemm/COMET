export async function fileTransferErrorMessage(error, fallback) {
  const responseData = error?.response?.data
  if (responseData instanceof Blob) {
    const contentType = String(responseData.type || '').toLowerCase()
    if (!contentType || contentType.includes('application/json') || contentType.includes('text/')) {
      try {
        const text = await responseData.text()
        const payload = JSON.parse(text)
        if (payload?.errors && typeof payload.errors === 'object') {
          const detail = Object.values(payload.errors).flat().join(', ')
          return payload.message ? `${payload.message}: ${detail}` : detail
        }
        return payload?.message || payload?.error || fallback
      } catch {
        return fallback
      }
    }
  }
  if (responseData?.errors && typeof responseData.errors === 'object') {
    const detail = Object.values(responseData.errors).flat().join(', ')
    return responseData.message ? `${responseData.message}: ${detail}` : detail
  }
  return responseData?.message || responseData?.error || error?.message || fallback
}
