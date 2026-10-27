import api from '../../../lib/api'

// --- SLA Dashboard ---

export function getSlaDashboard() {
  return api.get('/sla/dashboard').then(res => res.data)
}

// --- SLA Deadlines ---

export function listSlaDeadlines(params = {}) {
  return api.get('/sla/deadlines', { params }).then(res => res.data)
}

export function getSlaDeadline(id) {
  return api.get(`/sla/deadlines/${id}`).then(res => res.data)
}

export function createSlaDeadline(data) {
  return api.post('/sla/deadlines', data).then(res => res.data)
}

export function updateSlaDeadline(id, data) {
  return api.put(`/sla/deadlines/${id}`, data).then(res => res.data)
}

export function resolveSlaDeadline(id, data = {}) {
  return api.post(`/sla/deadlines/${id}/resolve`, data).then(res => res.data)
}

// --- Overdue ---

export function getOverdueDeadlines(params = {}) {
  return api.get('/sla/overdue', { params }).then(res => res.data)
}

// --- Auto-create ---

export function autoCreateSla(requirementId, data = {}) {
  return api.post(`/sla/deadlines/auto-create/${requirementId}`, data).then(res => res.data)
}