import { useEffect, useRef } from 'react'

export function Drawer({
  isOpen,
  onClose,
  children,
  maxWidthClass = 'max-w-xl',
}) {
  const drawerRef = useRef(null)

  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    if (isOpen) {
      document.addEventListener('keydown', handleEscape)
      // Prevent scrolling on body when drawer is open
      document.body.style.overflow = 'hidden'
    }
    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = ''
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/20 p-3 sm:p-4 animate-in fade-in duration-200"
      onClick={onClose}
      aria-modal="true"
      role="dialog"
    >
      <aside
        ref={drawerRef}
        onClick={(e) => e.stopPropagation()}
        className={`flex h-[calc(100dvh-1.5rem)] max-h-[calc(100dvh-1.5rem)] min-h-0 w-full ${maxWidthClass} flex-col overflow-hidden rounded-xl border border-brand-border bg-white shadow-xl dark:border-slate-800 dark:bg-slate-950 sm:h-[calc(100dvh-2rem)] sm:max-h-[calc(100dvh-2rem)] animate-in slide-in-from-right duration-300`}
      >
        {children}
      </aside>
    </div>
  )
}
