import { createContext } from 'react'

export const DEFAULT_BRANDING = {
  app_name: 'DILG Operations Workspace',
  app_tagline: 'DILG Laguna PDMU Operations System',
  logo_alt_text: 'DILG Operations Workspace logo',
  assistant_name: 'DILG Operations Workspace Assistant',
  logo_url: '/default-logo.svg',
  favicon_url: '/favicon.svg?v=2',
}

export const BrandingContext = createContext({
  branding: DEFAULT_BRANDING,
  isBrandingLoading: false,
  refreshBranding: async () => DEFAULT_BRANDING,
})
