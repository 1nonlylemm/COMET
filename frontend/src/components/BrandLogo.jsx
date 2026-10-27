import { useState } from 'react'
import { useBranding } from '../hooks/useBranding'

const SIZE_CLASSES = {
  sm: 'h-6 w-6',
  md: 'h-8 w-8',
  lg: 'h-10 w-10',
  xl: 'h-12 w-12',
}

export function BrandLogo({
  showName = true,
  size = 'md',
  className = '',
  imageClassName = '',
  nameClassName = '',
  overrideName = '',
}) {
  const { branding } = useBranding()
  const fallbackSrc = '/default-logo.svg'
  const logoSrc = branding.logo_url || fallbackSrc
  const [failedSrc, setFailedSrc] = useState('')
  const src = failedSrc === logoSrc ? fallbackSrc : logoSrc
  const displayName = overrideName || branding.app_name

  return (
    <div className={`flex min-w-0 items-center gap-2 ${className}`}>
      <img
        src={src}
        alt={branding.logo_alt_text || `${displayName} logo`}
        onError={() => setFailedSrc(logoSrc)}
        className={`${SIZE_CLASSES[size] || SIZE_CLASSES.md} shrink-0 rounded-md object-contain ${imageClassName}`}
      />
      {showName && (
        <span
          className={`min-w-0 truncate font-display font-semibold text-brand-text ${nameClassName}`}
          title={displayName}
        >
          {displayName}
        </span>
      )}
    </div>
  )
}
