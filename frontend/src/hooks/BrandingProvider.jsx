import { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../lib/api'
import { BrandingContext, DEFAULT_BRANDING } from './branding-context'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

function assetUrl(url, fallback) {
  const value = url || fallback
  if (!value) return null
  if (/^(https?:|data:|blob:)/i.test(value)) {
    return value
  }
  if (value.startsWith('/api/') && API_BASE !== '/api') {
    return `${API_BASE.replace(/\/api\/?$/, '')}${value}`
  }
  return value
}

function normalizeBranding(data = {}) {
  const appName = (data.app_name || DEFAULT_BRANDING.app_name).trim()
  const appTagline = (data.app_tagline || DEFAULT_BRANDING.app_tagline).trim()
  return {
    ...DEFAULT_BRANDING,
    ...data,
    app_name: appName,
    app_tagline: appTagline,
    logo_alt_text: data.logo_alt_text || `${appName} logo`,
    assistant_name: data.assistant_name || `${appName} Assistant`,
    logo_url: assetUrl(data.logo_url, DEFAULT_BRANDING.logo_url),
    favicon_url: assetUrl(data.favicon_url, data.logo_url || DEFAULT_BRANDING.favicon_url),
  }
}

export function BrandingProvider({ children }) {
  const [branding, setBranding] = useState(DEFAULT_BRANDING)
  const [isBrandingLoading, setIsBrandingLoading] = useState(true)

  const refreshBranding = useCallback(async () => {
    const response = await api.get('/settings/branding')
    const nextBranding = normalizeBranding(response.data?.data)
    setBranding(nextBranding)
    return nextBranding
  }, [])

  useEffect(() => {
    let ignore = false

    async function loadBranding() {
      setIsBrandingLoading(true)
      try {
        const response = await api.get('/settings/branding')
        if (!ignore) {
          setBranding(normalizeBranding(response.data?.data))
        }
      } catch {
        if (!ignore) {
          setBranding(DEFAULT_BRANDING)
        }
      } finally {
        if (!ignore) {
          setIsBrandingLoading(false)
        }
      }
    }

    loadBranding()
    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    document.title = branding.app_tagline
      ? `${branding.app_name} - ${branding.app_tagline}`
      : branding.app_name

    let icon = document.querySelector('link[rel~="icon"]')
    if (!icon) {
      icon = document.createElement('link')
      icon.rel = 'icon'
      document.head.appendChild(icon)
    }
    const targetUrl = branding.favicon_url || branding.logo_url || DEFAULT_BRANDING.favicon_url
    if (targetUrl.includes('.svg')) {
      icon.type = 'image/svg+xml'
    } else if (targetUrl.includes('.png')) {
      icon.type = 'image/png'
    } else if (targetUrl.includes('.ico')) {
      icon.type = 'image/x-icon'
    } else {
      icon.removeAttribute('type')
    }
    icon.href = targetUrl
  }, [branding])

  const value = useMemo(() => ({
    branding,
    isBrandingLoading,
    refreshBranding,
  }), [branding, isBrandingLoading, refreshBranding])

  return (
    <BrandingContext.Provider value={value}>
      {children}
    </BrandingContext.Provider>
  )
}

export default BrandingProvider
