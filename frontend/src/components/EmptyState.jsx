import { Inbox } from 'lucide-react'

export function EmptyState({
  title = 'No records found',
  description,
  icon,
  action,
  className = '',
}) {
  const Icon = icon || Inbox

  return (
    <div className={`flex min-h-36 flex-col items-center justify-center px-6 py-8 text-center ${className}`}>
      <Icon strokeWidth={1.7} className="mb-3 h-6 w-6 text-brand-text-muted" aria-hidden="true" />
      <p className="text-sm font-semibold text-brand-text">{title}</p>
      {description && <p className="mt-1 max-w-md text-sm text-brand-text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
