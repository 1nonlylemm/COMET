import { X } from 'lucide-react'
import { useEffect, useId, useRef } from 'react'

export function Modal({
  open,
  title,
  description,
  children,
  footer,
  onClose,
  size = 'md',
  workspace = false,
  fitContent = false,
}) {
  const titleId = useId()
  const panelRef = useRef(null)
  useEffect(() => {
    if (!open || !workspace) return
    const previousFocus = document.activeElement
    panelRef.current?.querySelector('button')?.focus()
    return () => previousFocus?.focus?.()
  }, [open, workspace])
  if (!open) return null

  const sizes = {
    sm: 'max-w-md',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
    '2xl': 'max-w-5xl',
    review: 'max-w-[1440px]',
  }

  return (
    <div ref={panelRef} className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 px-4 py-6" role="dialog" aria-modal="true" aria-labelledby={titleId}
      onKeyDown={workspace ? (event) => {
        if (event.key === 'Escape') { event.stopPropagation(); onClose?.() }
        if (event.key !== 'Tab') return
        const focusable = [...event.currentTarget.querySelectorAll('button, input, select, textarea, a[href], summary, iframe, [tabindex="0"]')].filter(element => !element.disabled && element.tabIndex >= 0 && element.getClientRects().length)
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
      } : undefined}>
      <div className={`${workspace ? `flex ${fitContent ? 'max-h-[90vh]' : 'h-[90vh]'} min-h-0 flex-col` : 'max-h-[90vh]'} w-full overflow-hidden rounded-lg border border-brand-border bg-brand-surface-solid shadow-xl ${sizes[size] || sizes.md}`}>
        <div className="flex items-start justify-between gap-4 border-b border-brand-border px-5 py-4">
          <div>
            <h2 id={titleId} className="text-base font-semibold text-brand-text">{title}</h2>
            {description && <p className="mt-1 text-sm text-brand-text-muted">{description}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-brand-text-muted transition-colors hover:bg-brand-surface hover:text-brand-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/35"
            aria-label="Close dialog"
          >
            <X strokeWidth={1.7} className="h-4 w-4" />
          </button>
        </div>
        <div className={workspace ? 'min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-5 py-4' : 'max-h-[calc(90vh-9rem)] overflow-y-auto px-5 py-4'}>{children}</div>
        {footer && <div className="shrink-0 border-t border-brand-border bg-brand-surface px-5 py-4">{footer}</div>}
      </div>
    </div>
  )
}
