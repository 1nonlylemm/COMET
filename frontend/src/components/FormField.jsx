export function FormField({
  id,
  label,
  hint,
  error,
  required = false,
  children,
  className = '',
}) {
  const errorId = id && error ? `${id}-error` : undefined
  const hintId = id && hint && !error ? `${id}-hint` : undefined
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined
  const controlProps = {
    'aria-invalid': error ? 'true' : undefined,
    'aria-describedby': describedBy,
  }

  return (
    <div className={className}>
      {label && (
        <label htmlFor={id} className="label-text">
          {label}
          {required && (
            <span className="ml-1 text-red-500/80 dark:text-red-400/80 font-normal" aria-hidden="true">
              *
            </span>
          )}
        </label>
      )}
      {typeof children === 'function' ? children(controlProps) : children}
      {hint && !error && <p id={hintId} className="mt-1 text-xs text-brand-text-muted">{hint}</p>}
      {error && <p id={errorId} className="mt-1 text-xs font-medium text-red-700 dark:text-red-300">{error}</p>}
    </div>
  )
}
