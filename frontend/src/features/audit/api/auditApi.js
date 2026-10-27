import api from '../../../lib/api'

export function getAuditStats() {
  return api.get('/audit/stats').then((res) => res.data)
}

export function listAuditLogs(params = {}) {
  return api.get('/audit/logs', { params }).then((res) => res.data)
}

export function getAuditLog(logId) {
  return api.get(`/audit/logs/${logId}`).then((res) => res.data)
}

export function verifyAuditChain() {
  return api.get('/audit/verify-chain').then((res) => res.data)
}

export function listIntegrityIncidents(params = {}) {
  return api.get('/audit/integrity-incidents', { params }).then((res) => res.data)
}

export function openIntegrityIncident(payload = {}) {
  return api.post('/audit/integrity-incidents/open', payload).then((res) => res.data)
}

export function rebaselineIntegrityIncident(incidentId, payload = {}) {
  return api.post(`/audit/integrity-incidents/${incidentId}/rebaseline`, payload).then((res) => res.data)
}
