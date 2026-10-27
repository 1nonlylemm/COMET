import axios from 'axios'
import { getStoredFiscalYear, shouldAttachFiscalYear } from './fiscalYear'
import { currentBrowserReturnTo, unauthorizedPath } from './authRedirect'

const API_BASE = import.meta.env.VITE_API_URL || '/api'
const TOKEN_KEY = 'brand_access_token'
const REFRESH_KEY = 'brand_refresh_token'
const USER_KEY = 'brand_user'
const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
})

let refreshPromise = null
let sessionFailureHandled = false

export function clearStoredSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
}

function redirectToLogin() {
  if (window.location.pathname !== '/401') {
    window.location.href = unauthorizedPath(currentBrowserReturnTo())
  }
}

export function handleSessionFailure() {
  clearStoredSession()
  if (sessionFailureHandled) {
    return
  }
  sessionFailureHandled = true
  redirectToLogin()
}

export function isAccountDeactivated(error) {
  if (error?.response?.status !== 403) {
    return false
  }
  const data = error?.response?.data
  const message = [data?.message, data?.msg]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return message.includes('account is deactivated')
}

export function isSessionFailure(error) {
  if (error?.config?.url?.includes('/auth/login')) {
    return false
  }

  const status = error?.response?.status
  if (status === 401) {
    return true
  }

  if (isAccountDeactivated(error)) {
    return true
  }

  return false
}

export function _resetSessionStateForTest() {
  sessionFailureHandled = false
  refreshPromise = null
}

api.interceptors.request.use((config) => {
  if (config.url?.includes('/auth/login')) {
    return config
  }

  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const skipFiscalYear = Boolean(config.skipFiscalYear)
  if (skipFiscalYear) {
    delete config.skipFiscalYear
  }

  const selectedFiscalYear = getStoredFiscalYear()
  if (selectedFiscalYear && !skipFiscalYear && shouldAttachFiscalYear(config)) {
    config.params = {
      ...(config.params || {}),
      fiscal_year: config.params?.fiscal_year ?? selectedFiscalYear,
    }
  }
  return config
})

api.interceptors.response.use(
  (response) => {
    if (response.config?.url?.includes('/auth/login')) {
      sessionFailureHandled = false
    }
    return response
  },
  async (error) => {
    if (!isSessionFailure(error)) {
      return Promise.reject(error)
    }

    if (isAccountDeactivated(error)) {
      handleSessionFailure()
      return Promise.reject(error)
    }

    const originalRequest = error.config || {}
    if (originalRequest._retry || originalRequest.url?.includes('/auth/refresh')) {
      handleSessionFailure()
      return Promise.reject(error)
    }

    originalRequest._retry = true

    const refreshToken = localStorage.getItem(REFRESH_KEY)
    if (!refreshToken) {
      handleSessionFailure()
      return Promise.reject(error)
    }

    try {
      if (!refreshPromise) {
        refreshPromise = axios.post(
          `${API_BASE}/auth/refresh`,
          {},
          {
            headers: { Authorization: `Bearer ${refreshToken}` },
          },
        ).finally(() => {
          refreshPromise = null
        })
      }

      const res = await refreshPromise

      if (res.data?.data) {
        const { access_token, refresh_token: new_refresh } = res.data.data
        localStorage.setItem(TOKEN_KEY, access_token)
        if (new_refresh) {
          localStorage.setItem(REFRESH_KEY, new_refresh)
        }
        sessionFailureHandled = false
        originalRequest.headers = {
          ...(originalRequest.headers || {}),
          Authorization: `Bearer ${access_token}`,
        }
        return api(originalRequest)
      }
    } catch (refreshError) {
      handleSessionFailure()
      return Promise.reject(refreshError)
    }

    handleSessionFailure()
    return Promise.reject(error)
  }
)

export default api
