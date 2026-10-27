import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'

export function PasswordInput({
  id,
  className = 'input-field',
  wrapperClassName = '',
  disabled = false,
  ...props
}) {
  const [isVisible, setIsVisible] = useState(false)
  const ToggleIcon = isVisible ? EyeOff : Eye
  const toggleLabel = isVisible ? 'Hide password' : 'Show password'

  return (
    <div className={`relative ${wrapperClassName}`}>
      <input
        id={id}
        type={isVisible ? 'text' : 'password'}
        className={`${className} pr-12`}
        disabled={disabled}
        {...props}
      />
      <button
        type="button"
        className="absolute right-1.5 top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-brand-text-muted transition-colors hover:bg-brand-surface hover:text-brand-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/35 disabled:cursor-not-allowed disabled:opacity-50"
        aria-label={toggleLabel}
        aria-pressed={isVisible}
        aria-controls={id}
        title={toggleLabel}
        onClick={() => setIsVisible((current) => !current)}
        disabled={disabled}
      >
        <ToggleIcon strokeWidth={1.8} className="h-4 w-4" />
      </button>
    </div>
  )
}
