import api from '../../../lib/api'

export function getAccountProfile() {
  return api.get('/auth/me').then((res) => res.data)
}

export function updateAccountProfile(data) {
  return api.put('/auth/me', data).then((res) => res.data)
}

export function changeAccountPassword(data) {
  return api.post('/auth/change-password', data).then((res) => res.data)
}

export function getNotificationPreferences() {
  return api.get('/notifications/preferences').then((res) => res.data)
}

export function updateNotificationPreferences(data) {
  return api.put('/notifications/preferences', data).then((res) => res.data)
}
