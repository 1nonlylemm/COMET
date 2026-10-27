import api from '../../../lib/api'

export function getFieldSummary(params = {}) {
  return api.get('/field/summary', { params }).then((res) => res.data)
}

export function listAssignedLgus(params = {}) {
  return api.get('/field/lgus', { params }).then((res) => res.data)
}

export function listFieldActionItems(params = {}) {
  return api.get('/field/action-items', { params }).then((res) => res.data)
}

export function listRequirementComments(requirementId) {
  return api.get(`/field/requirements/${requirementId}/comments`).then((res) => res.data)
}

export function createRequirementComment(requirementId, data) {
  return api.post(`/field/requirements/${requirementId}/comments`, data).then((res) => res.data)
}
