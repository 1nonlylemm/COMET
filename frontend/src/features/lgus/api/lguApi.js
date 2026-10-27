import api from '../../../lib/api'

// --- Clusters ---

export function listClusters(search = '') {
  const params = {}
  if (search) params.search = search
  return api.get('/lgus/clusters', { params }).then(res => res.data)
}

export function getCluster(id) {
  return api.get(`/lgus/clusters/${id}`).then(res => res.data)
}

export function createCluster(data) {
  return api.post('/lgus/clusters', data).then(res => res.data)
}

export function updateCluster(id, data) {
  return api.put(`/lgus/clusters/${id}`, data).then(res => res.data)
}

export function deleteCluster(id) {
  return api.delete(`/lgus/clusters/${id}`).then(res => res.data)
}

// --- LGUs ---

export function listLgus(params = {}) {
  return api.get('/lgus', { params }).then(res => res.data)
}

export function getLgu(id) {
  return api.get(`/lgus/${id}`).then(res => res.data)
}

export function createLgu(data) {
  return api.post('/lgus', data).then(res => res.data)
}

export function updateLgu(id, data) {
  return api.put(`/lgus/${id}`, data).then(res => res.data)
}

export function toggleLguActive(id, isActive) {
  return api.post(`/lgus/${id}/toggle-active`, { is_active: isActive }).then(res => res.data)
}

// --- Staff Assignments ---

export function listStaffAssignments(params = {}) {
  return api.get('/lgus/staff-assignments', { params }).then(res => res.data)
}

export function assignStaffToCluster(data) {
  return api.post('/lgus/staff-assignments', data).then(res => res.data)
}

export function removeStaffAssignment(id) {
  return api.delete(`/lgus/staff-assignments/${id}`).then(res => res.data)
}

// --- Field Officer LGU Assignments ---

export function listFieldAssignments(params = {}) {
  return api.get('/lgus/field-assignments', { params }).then(res => res.data)
}

export function assignFieldOfficerToLgu(data) {
  return api.post('/lgus/field-assignments', data).then(res => res.data)
}

export function removeFieldAssignment(id) {
  return api.delete(`/lgus/field-assignments/${id}`).then(res => res.data)
}
