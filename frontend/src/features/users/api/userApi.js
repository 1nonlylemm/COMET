import api from '../../../lib/api'

export function listUsers(params = {}) {
  return api.get('/auth/users', { params }).then((res) => res.data)
}

export function getUser(userId) {
  return api.get(`/auth/users/${userId}`).then((res) => res.data)
}

export function createUser(data) {
  return api.post('/auth/users', data).then((res) => res.data)
}

export function toggleUserActive(userId, isActive) {
  return api.post(`/auth/users/${userId}/toggle-active`, { is_active: isActive }).then((res) => res.data)
}

export function changeUserRole(userId, role, scope = {}) {
  return api.post(`/auth/users/${userId}/change-role`, { role, ...scope }).then((res) => res.data)
}
