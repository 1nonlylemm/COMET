import api from '../../../lib/api'

export function getEscalationDashboard() {
  return api.get('/escalation/dashboard').then((res) => res.data)
}

export function listEscalationBreaches(params = {}) {
  return api.get('/escalation/breaches', { params }).then((res) => res.data)
}

export function listEscalationNotices(params = {}) {
  return api.get('/escalation/notices', { params }).then((res) => res.data)
}

export function listNoticeDocumentTemplates() {
  return api.get('/escalation/document-templates').then((res) => res.data)
}

export function getEscalationNotice(id) {
  return api.get(`/escalation/notices/${id}`).then((res) => res.data)
}

export function createEscalationNotice(data) {
  return api.post('/escalation/notices', data).then((res) => res.data)
}

export function updateEscalationNotice(id, data) {
  return api.put(`/escalation/notices/${id}`, data).then((res) => res.data)
}

export function releaseEscalationNotice(id, data) {
  return api.post(`/escalation/notices/${id}/release`, data).then((res) => res.data)
}

export function recordEscalationNoticeReceipt(id, data) {
  return api.post(`/escalation/notices/${id}/receipt`, data).then((res) => res.data)
}

export function draftEscalationFinding(id, data) {
  return api.post(`/escalation/notices/${id}/ai-draft`, data).then((res) => res.data)
}

export function createMagicLink(data) {
  return api.post('/magic-links', data).then((res) => res.data)
}

export function previewNoticeDispatch(id, data) {
  return api.post(`/escalation/notices/${id}/dispatch-preview`, data).then((res) => res.data)
}

export function recordNoticeDispatch(id, data) {
  return api.post(`/escalation/notices/${id}/dispatch-log`, data).then((res) => res.data)
}

export function generateNextEscalationNotice(data) {
  return api.post('/escalation/generate-notice', data).then((res) => res.data)
}

export function fetchNoticeDocument(id, format = 'pdf', options = {}) {
  const responseType = format === 'html' ? 'text' : 'blob'
  const config = {
    params: { format, download: format === 'docx' ? 'true' : 'false' },
    responseType,
    transformResponse: format === 'html' ? [(data) => data] : undefined,
  }
  const hasOptions = !!(options.template_id || Object.keys(options.placeholder_overrides || {}).length)
  if (!hasOptions) {
    return api.get(`/escalation/notices/${id}/document`, config)
  }
  return api.post(`/escalation/notices/${id}/document`, {
    format,
    template_id: options.template_id,
    placeholder_overrides: options.placeholder_overrides || {},
  }, config)
}

export function previewNoticeDocument(id, options = {}) {
  return api.post(`/escalation/notices/${id}/document/preview`, options).then((res) => res.data)
}
