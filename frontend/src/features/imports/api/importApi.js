import api from '../../../lib/api'

export function uploadWorkbook(formData) {
  return api.post('/imports/workbooks', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(res => res.data)
}

export function getImportBatch(batchId) {
  return api.get(`/imports/workbooks/${batchId}`).then(res => res.data)
}

export function mapWorkbook(batchId, payload = {}) {
  return api.post(`/imports/workbooks/${batchId}/map`, payload).then(res => res.data)
}

export function previewWorkbook(batchId, payload = {}) {
  return api.post(`/imports/workbooks/${batchId}/preview`, payload).then(res => res.data)
}

export function commitWorkbook(batchId, payload = {}) {
  return api.post(`/imports/workbooks/${batchId}/commit`, payload).then(res => res.data)
}

export function getSchemaDiff(batchId, templateId) {
  return api.get(`/imports/workbooks/${batchId}/schema-diff`, {
    params: { template_id: templateId },
  }).then(res => res.data)
}

export function getMappingWorkshop(batchId) {
  return api.get(`/imports/workbooks/${batchId}/mapping-workshop`).then(res => res.data)
}

export function saveMappingDecisions(batchId, decisions = []) {
  return api.put(`/imports/workbooks/${batchId}/mapping-decisions`, { decisions }).then(res => res.data)
}

export function listMappingHistory(params = {}) {
  return api.get('/imports/mapping-history', { params }).then(res => res.data)
}

export function listImportTemplates(params = {}) {
  return api.get('/imports/templates', { params }).then(res => res.data)
}

export function createImportTemplate(data) {
  return api.post('/imports/templates', data).then(res => res.data)
}

export function updateImportTemplate(templateId, data) {
  return api.put(`/imports/templates/${templateId}`, data).then(res => res.data)
}

export function cloneImportTemplate(templateId, data = {}) {
  return api.post(`/imports/templates/${templateId}/clone`, data).then(res => res.data)
}
