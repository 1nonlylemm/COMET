export const FISCAL_YEAR_STORAGE_KEY = 'comet_selected_fiscal_year'

export function getStoredFiscalYear() {
  const rawValue = localStorage.getItem(FISCAL_YEAR_STORAGE_KEY)
  const value = Number(rawValue)
  return Number.isInteger(value) && value >= 2000 && value <= 2100 ? value : null
}

export function setStoredFiscalYear(fiscalYear) {
  if (!fiscalYear) {
    localStorage.removeItem(FISCAL_YEAR_STORAGE_KEY)
    return
  }
  localStorage.setItem(FISCAL_YEAR_STORAGE_KEY, String(fiscalYear))
}

export function shouldAttachFiscalYear(config) {
  if ((config.method || 'get').toLowerCase() !== 'get') return false
  const url = config.url || ''
  const path = url.split('?')[0]
  if (!path || path.includes('/auth/') || path.startsWith('/settings')) return false
  if (path === '/programs/fiscal-years') return false
  if (path === '/ai/tools' || path.startsWith('/ai/conversations')) return false
  return true
}
