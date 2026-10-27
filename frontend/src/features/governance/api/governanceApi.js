import api from '../../../lib/api'

export function listArchiveRecords(params = {}) {
  return api.get('/governance/archive', { params }).then((res) => res.data)
}

export function getArchiveRecord(projectRequirementId) {
  return api.get(`/governance/archive/${projectRequirementId}`).then((res) => res.data)
}

export function listCommunications(params = {}) {
  return api.get('/governance/communications', { params }).then((res) => res.data)
}

export function listGuidelines(params = {}) {
  return api.get('/governance/guidelines', { params }).then((res) => res.data)
}

export function createGuideline(data) {
  const config = data instanceof FormData ? { headers: { 'Content-Type': 'multipart/form-data' } } : undefined
  return api.post('/governance/guidelines', data, config).then((res) => res.data)
}

export function updateGuideline(id, data) {
  const config = data instanceof FormData ? { headers: { 'Content-Type': 'multipart/form-data' } } : undefined
  return api.put(`/governance/guidelines/${id}`, data, config).then((res) => res.data)
}

export function downloadGuidelineFile(id) {
  return api.get(`/governance/guidelines/${id}/download`, {
    responseType: 'blob',
  }).then((res) => ({
    data: res.data,
    headers: res.headers,
  }))
}
