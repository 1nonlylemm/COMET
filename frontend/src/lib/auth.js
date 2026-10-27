const TOKEN_KEY = 'brand_access_token'
const REFRESH_KEY = 'brand_refresh_token'
const USER_KEY = 'brand_user'

export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY)
}

export function getUser() {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    clearAuthData()
    return null
  }
}

export function setAuthData(data) {
  localStorage.setItem(TOKEN_KEY, data.access_token)
  localStorage.setItem(REFRESH_KEY, data.refresh_token)
  localStorage.setItem(USER_KEY, JSON.stringify(data.user))
}

export function setUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function updateStoredUser(updates) {
  const current = getUser()
  if (!current) return
  setUser({ ...current, ...updates })
}

export function clearAuthData() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
}

export function isAuthenticated() {
  return !!getAccessToken()
}

export function getUserRole() {
  const user = getUser()
  return user?.role || null
}

export function hasRole(...roles) {
  const role = getUserRole()
  return roles.includes(role)
}

export function isAdmin() {
  return getUserRole() === 'admin'
}

export function isSystemAdmin() {
  return getUserRole() === 'system_admin'
}

export function isStaff() {
  const role = getUserRole()
  return role === 'admin' || role === 'staff'
}

export function isAdminOrStaff() {
  return isStaff()
}

export function isPlainStaff() {
  return getUserRole() === 'staff'
}

export function isFieldOfficer() {
  return getUserRole() === 'field_officer'
}

export function isInternalUser() {
  const role = getUserRole()
  return role === 'system_admin' || role === 'admin' || role === 'staff' || role === 'field_officer'
}

export function needsPasswordChange() {
  return !!getUser()?.must_change_password
}
