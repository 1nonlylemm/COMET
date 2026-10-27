import api from '../../../lib/api'

export function listCompletionProjects(params = {}) {
  return api.get('/completion/projects', { params }).then((res) => res.data)
}

export function getCompletionProject(projectId) {
  return api.get(`/completion/projects/${projectId}`).then((res) => res.data)
}

export function updateCompletionProject(projectId, data) {
  return api.put(`/completion/projects/${projectId}`, data).then((res) => res.data)
}

// ---------------------------------------------------------------------------
// Phase 2C: Completion Matrix (Final SWA, FIR, COFA, Final SORD, Proof of
// Return of Funds). Workflow transitions reuse the shared Phase 1 endpoints
// under /projects/requirements/<id>/workflow/* via each row's
// project_requirement_id -- see monitoringApi.js for those wrappers.
// ---------------------------------------------------------------------------

export function listCompletionDocuments(projectId) {
  return api.get(`/completion/projects/${projectId}/documents`).then((res) => res.data)
}

export function getCompletionDocument(projectId, documentType) {
  return api.get(`/completion/projects/${projectId}/documents/${documentType}`).then((res) => res.data)
}

export function updateCompletionDocumentApplicability(projectId, documentType, data) {
  return api.put(`/completion/projects/${projectId}/documents/${documentType}/applicability`, data).then((res) => res.data)
}

export function updateCompletionDocumentMetadata(projectId, documentType, data) {
  return api.put(`/completion/projects/${projectId}/documents/${documentType}/metadata`, data).then((res) => res.data)
}
