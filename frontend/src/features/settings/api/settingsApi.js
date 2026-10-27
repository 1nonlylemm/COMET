import api from '../../../lib/api'

export function getReadiness() {
  return api.get('/settings/readiness').then((res) => res.data)
}

export function getBranding() {
  return api.get('/settings/branding').then((res) => res.data)
}

export function updateBranding(data) {
  return api.put('/settings/branding', data).then((res) => res.data)
}

export function uploadBrandAsset(assetType, file) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post(`/settings/branding/${assetType}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then((res) => res.data)
}

export function listSystemConfigs() {
  return api.get('/settings/configs').then((res) => res.data)
}

export function listOperationalDefaults() {
  return api.get('/settings/defaults').then((res) => res.data)
}

export function listDocumentTemplates() {
  return api.get('/settings/document-templates').then((res) => res.data)
}

export function listReportTemplates() {
  return api.get('/settings/report-templates').then((res) => res.data)
}

export function uploadDocumentTemplate(templateType, file, options = {}) {
  const formData = new FormData()
  formData.append('file', file)
  if (options.label) formData.append('label', options.label)
  if (options.placeholder_defaults) {
    formData.append('placeholder_defaults', JSON.stringify(options.placeholder_defaults))
  }
  if (options.is_default !== undefined) formData.append('is_default', String(options.is_default))
  return api.post(`/settings/document-templates/${templateType}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then((res) => res.data)
}

export function uploadReportTemplate(templateType, file, options = {}) {
  return uploadDocumentTemplate(templateType, file, options)
}

export function updateDocumentTemplate(templateType, templateId, data) {
  return api.put(`/settings/document-templates/${templateType}/${templateId}`, data).then((res) => res.data)
}

export function updateReportTemplate(templateType, templateId, data) {
  return updateDocumentTemplate(templateType, templateId, data)
}

export function deleteDocumentTemplate(templateType, templateId) {
  return api.delete(`/settings/document-templates/${templateType}/${templateId}`).then((res) => res.data)
}

export function deleteReportTemplate(templateType, templateId) {
  return deleteDocumentTemplate(templateType, templateId)
}

export function createSystemConfig(data) {
  return api.post('/settings/configs', data).then((res) => res.data)
}

export function updateSystemConfig(id, data) {
  return api.put(`/settings/configs/${id}`, data).then((res) => res.data)
}

export function getDriveConnection() {
  return api.get('/drive/connection').then((res) => res.data)
}

export function updateDriveConnection(data) {
  return api.put('/drive/connection', data).then((res) => res.data)
}

export function startDriveOAuth() {
  return api.post('/drive/oauth/start').then((res) => res.data)
}

export function disconnectDriveOAuth() {
  return api.post('/drive/oauth/disconnect').then((res) => res.data)
}
