import { Calendar, X } from 'lucide-react'

/**
 * StyledDateInput - A polished date input with calendar icon adornment,
 * clear action, and cohesive COMET design-system styling.
 */
export function StyledDateInput({
  id,
  value = '',
  onChange,
  disabled = false,
  error = false,
  className = '',
  placeholder = 'YYYY-MM-DD',
  ...restProps
}) {
  const handleClear = (event) => {
    event.stopPropagation()
    const syntheticEvent = {
      target: { id, name: id, value: '' },
      currentTarget: { id, name: id, value: '' },
    }
    onChange?.(syntheticEvent)
  }

  return (
    <div className={`relative flex w-full items-center ${className}`}>
      <div className="pointer-events-none absolute left-3 flex items-center text-brand-text-muted">
        <Calendar className="h-4 w-4" strokeWidth={1.7} />
      </div>

      <input
        id={id}
        type="date"
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        disabled={disabled}
        className={`w-full rounded-md border bg-white py-2 pl-9 pr-8 text-sm text-brand-text transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/20 dark:bg-slate-900 ${
          error
            ? 'border-red-600 focus-visible:border-red-600 dark:border-red-400'
            : 'border-brand-border hover:border-slate-400 focus-visible:border-brand-primary'
        } ${disabled ? 'cursor-not-allowed opacity-60 bg-slate-100 dark:bg-slate-800' : ''}`}
        {...restProps}
      />

      {value && !disabled && (
        <button
          type="button"
          onClick={handleClear}
          className="absolute right-2.5 rounded p-0.5 text-brand-text-muted hover:bg-slate-100 hover:text-brand-text dark:hover:bg-slate-800"
          aria-label="Clear date"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  )
}
export default StyledDateInput
