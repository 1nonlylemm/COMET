import api from '../../../lib/api'

export function listBatchImportTargets() {
  return api.get('/batch-imports/targets').then(res => res.data)
}

export function importTarget(target, formData) {
  return api.post(`/batch-imports/${target}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(res => res.data)
}
