import api from '../../../lib/api'

export function getSystemAdminOverview() {
  return api.get('/system-admin/overview').then((res) => res.data)
}

export function getSystemAdminTechnicalSettings() {
  return api.get('/system-admin/technical-settings').then((res) => res.data)
}

export function updateSystemAdminTechnicalSettings(data, headers = {}) {
  return api.put('/system-admin/technical-settings', data, { headers }).then((res) => res.data)
}

export function deleteSystemAdminTechnicalSettingOverride(key, headers = {}) {
  return api.delete(`/system-admin/technical-settings/${encodeURIComponent(key)}`, { headers }).then((res) => res.data)
}

export function validateAiCredential(data, headers = {}) {
  return api.post('/system-admin/technical-settings/validate-credential', data, { headers }).then((res) => res.data)
}

export function validateStorageCredentials(data, headers = {}) {
  return api.post('/system-admin/technical-settings/validate-storage', data, { headers }).then((res) => res.data)
}

export function validateEmailCredentials(data, headers = {}) {
  return api.post('/system-admin/technical-settings/validate-email', data, { headers }).then((res) => res.data)
}

export function getDriveConnection() {
  return api.get('/drive/connection').then((res) => res.data)
}

export function updateDriveConnection(data, headers = {}) {
  return api.put('/drive/connection', data, { headers }).then((res) => res.data)
}

export function startDriveOAuth(headers = {}) {
  return api.post('/drive/oauth/start', {}, { headers }).then((res) => res.data)
}

export function disconnectDriveOAuth(headers = {}) {
  return api.post('/drive/oauth/disconnect', {}, { headers }).then((res) => res.data)
}

export function listBackups(params) {
  return api.get('/system-admin/backups', { params }).then((res) => res.data)
}

export function triggerBackup() {
  return api.post('/system-admin/backups').then((res) => res.data)
}

export function downloadBackup(backupId) {
  return api.get(`/system-admin/backups/${backupId}/download`, { responseType: 'blob' })
}

export function listOperationalEvents(params) {
  return api.get('/system-admin/operational-events', { params }).then((res) => res.data)
}

export function getOperationalEvent(eventId) {
  return api.get(`/system-admin/operational-events/${eventId}`).then((res) => res.data)
}

