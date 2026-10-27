import { ROUTES } from '../config/routes'

export const RETURN_TO_PARAM = 'return_to'

const EXCLUDED_RETURN_PATHS = new Set([
  ROUTES.HOME,
  ROUTES.LOGIN,
  ROUTES.ERROR_401,
  ROUTES.ERROR_403,
  ROUTES.ERROR_404,
  ROUTES.ERROR_405,
  ROUTES.ERROR_500,
])

const ROLE_RULES = [
  {
    pattern: /^\/dashboard\/system-admin(?:\/.*)?$/,
    roles: ['system_admin'],
  },
  {
    pattern: /^\/dashboard\/(?:users|audit)(?:\/.*)?$/,
    roles: ['system_admin', 'admin'],
  },
  {
    pattern: /^\/dashboard\/(?:clusters(?:\/.*)?|settings(?:\/.*)?|programs\/[^/]+\/cycles\/[^/]+\/import(?:\/.*)?)$/,
    roles: ['admin'],
  },
  {
    pattern: /^\/system-admin(?:\/.*)?$/,
    roles: ['system_admin'],
  },
  {
    pattern: /^\/(?:users|audit)(?:\/.*)?$/,
    roles: ['system_admin', 'admin'],
  },
  {
    pattern: /^\/(?:clusters|settings)(?:\/.*)?$/,
    roles: ['admin'],
  },
  {
    pattern: /^\/dashboard\/(?:handoff(?:\/.*)?|reports(?:\/.*)?|escalation(?:\/.*)?|programs\/[^/]+\/cycles\/[^/]+\/workbook(?:\/.*)?)$/,
    roles: ['admin', 'staff'],
  },
  {
    pattern: /^\/(?:handoff|reports|escalation)(?:\/.*)?$/,
    roles: ['admin', 'staff'],
  },
  {
    pattern: /^\/dashboard\/field(?:\/.*)?$/,
    roles: ['field_officer'],
  },
  {
    pattern: /^\/field(?:\/.*)?$/,
    roles: ['field_officer'],
  },
]

const LEGACY_PROTECTED_PATHS = [
  /^\/projects(?:\/.*)?$/,
  /^\/ai(?:\/.*)?$/,
  /^\/field(?:\/.*)?$/,
  /^\/intake(?:\/.*)?$/,
  /^\/monitoring(?:\/.*)?$/,
  /^\/reports(?:\/.*)?$/,
  /^\/handoff(?:\/.*)?$/,
  /^\/programs(?:\/.*)?$/,
  /^\/lgus(?:\/.*)?$/,
  /^\/clusters(?:\/.*)?$/,
  /^\/sla(?:\/.*)?$/,
  /^\/completion(?:\/.*)?$/,
  /^\/escalation(?:\/.*)?$/,
  /^\/users(?:\/.*)?$/,
  /^\/audit(?:\/.*)?$/,
  /^\/archive(?:\/.*)?$/,
  /^\/guidelines(?:\/.*)?$/,
  /^\/settings(?:\/.*)?$/,
  /^\/system-admin(?:\/.*)?$/,
  /^\/account(?:\/.*)?$/,
]

function appOrigin() {
  return typeof window === 'undefined' ? 'http://localhost' : window.location.origin
}

function isWorkspacePath(pathname) {
  return (
    pathname === ROUTES.DASHBOARD ||
    pathname.startsWith(`${ROUTES.DASHBOARD}/`) ||
    LEGACY_PROTECTED_PATHS.some((pattern) => pattern.test(pathname))
  )
}

export function sanitizeReturnTo(value) {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed || !trimmed.startsWith('/') || trimmed.startsWith('//') || trimmed.includes('\\')) {
    return null
  }

  try {
    const url = new URL(trimmed, appOrigin())
    if (url.origin !== appOrigin()) return null
    if (EXCLUDED_RETURN_PATHS.has(url.pathname)) return null
    if (!isWorkspacePath(url.pathname)) return null
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return null
  }
}

export function currentPathFromLocation(location) {
  if (!location) return null
  return sanitizeReturnTo(`${location.pathname || ''}${location.search || ''}${location.hash || ''}`)
}

export function currentBrowserReturnTo() {
  if (typeof window === 'undefined') return null
  return currentPathFromLocation(window.location)
}

export function getReturnToFromLocation(location) {
  const params = new URLSearchParams(location?.search || '')
  return sanitizeReturnTo(params.get(RETURN_TO_PARAM) || location?.state?.from)
}

export function appendReturnTo(path, returnTo) {
  const safeReturnTo = sanitizeReturnTo(returnTo)
  if (!safeReturnTo) return path
  const separator = path.includes('?') ? '&' : '?'
  return `${path}${separator}${RETURN_TO_PARAM}=${encodeURIComponent(safeReturnTo)}`
}

export function loginPath(returnTo) {
  return appendReturnTo(ROUTES.LOGIN, returnTo)
}

export function unauthorizedPath(returnTo) {
  return appendReturnTo(ROUTES.ERROR_401, returnTo)
}

export function isReturnToAllowedForRole(returnTo, role) {
  const safeReturnTo = sanitizeReturnTo(returnTo)
  if (!safeReturnTo || !['system_admin', 'admin', 'staff', 'field_officer'].includes(role)) return false

  const pathname = new URL(safeReturnTo, appOrigin()).pathname
  const matchingRule = ROLE_RULES.find((rule) => rule.pattern.test(pathname))
  if (!matchingRule) return true
  return matchingRule.roles.includes(role)
}

export function resolvePostLoginRedirect(user, returnTo) {
  return isReturnToAllowedForRole(returnTo, user?.role)
    ? sanitizeReturnTo(returnTo)
    : ROUTES.DASHBOARD
}
