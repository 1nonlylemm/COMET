import api from '../../../lib/api'

export function getDriveRoot() {
  return api.get('/drive/root').then(res => res.data)
}

export function listDriveChildren(params = {}) {
  return api.get('/drive/children', { params }).then(res => res.data)
}

export function getDriveReadiness() {
  return api.get('/drive/readiness').then(res => res.data)
}

export function createDriveFolder(data) {
  return api.post('/drive/folders', data).then(res => res.data)
}

export function moveDriveItem(fileId, data) {
  return api.post(`/drive/files/${fileId}/move`, data).then(res => res.data)
}
