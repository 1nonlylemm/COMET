import api from '../../../lib/api'

function buildConfig(data) {
  return data instanceof FormData
    ? { headers: { 'Content-Type': 'multipart/form-data' } }
    : undefined
}

export function listReferences(params = {}) {
  return api.get('/library/references', { params }).then((res) => res.data)
}

export function getReference(uri) {
  return api
    .get(`/library/references/${encodeURIComponent(uri)}`)
    .then((res) => res.data)
}

export function createReference(formData) {
  return api
    .post('/library/references', formData, buildConfig(formData))
    .then((res) => res.data)
}

export function updateReference(uri, formData) {
  return api
    .put(
      `/library/references/${encodeURIComponent(uri)}`,
      formData,
      buildConfig(formData),
    )
    .then((res) => res.data)
}

export function deleteReference(uri) {
  return api
    .delete(`/library/references/${encodeURIComponent(uri)}`)
    .then((res) => res.data)
}

export function downloadReferenceFile(uri) {
  return api
    .get(`/library/references/${encodeURIComponent(uri)}/download`, {
      responseType: 'blob',
    })
    .then((res) => ({
      data: res.data,
      headers: res.headers,
    }))
}

export function getReferenceCheckerProfile(uri) {
  return api
    .get(`/library/references/${encodeURIComponent(uri)}/checker-profile`)
    .then((res) => res.data)
}

export function updateReferenceCheckerProfile(uri, data) {
  return api
    .put(`/library/references/${encodeURIComponent(uri)}/checker-profile`, data)
    .then((res) => res.data)
}

export function listTemplateSubtypes() {
  return api.get('/library/template-subtypes').then((res) => res.data)
}

export function previewTemplatePlaceholders(formData) {
  return api
    .post('/library/template-placeholders/preview', formData, buildConfig(formData))
    .then((res) => res.data)
}
