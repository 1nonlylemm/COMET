import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react'
import { FeedbackContext, useToast } from './feedbackContext'

const TYPE_ALIASES = {
  danger: 'error',
  destructive: 'error',
  warn: 'warning',
  notice: 'info',
}

const FEEDBACK_META = {
  success: {
    title: 'Success',
    icon: CheckCircle2,
    toastClass: 'border-emerald-200 bg-emerald-50 text-emerald-950 dark:border-emerald-900/60 dark:bg-emerald-950/90 dark:text-emerald-50',
    iconClass: 'text-emerald-600 dark:text-emerald-300',
    alertClass: 'border-emerald-200 bg-emerald-50 text-emerald-950 dark:border-emerald-900/60 dark:bg-emerald-950/50 dark:text-emerald-50',
    duration: 5200,
  },
  error: {
    title: 'Needs Attention',
    icon: XCircle,
    toastClass: 'border-red-200 bg-red-50 text-red-950 dark:border-red-900/60 dark:bg-red-950/90 dark:text-red-50',
    iconClass: 'text-red-600 dark:text-red-300',
    alertClass: 'border-red-200 bg-red-50 text-red-950 dark:border-red-900/60 dark:bg-red-950/50 dark:text-red-50',
    duration: 9000,
  },
  warning: {
    title: 'Warning',
    icon: AlertTriangle,
    toastClass: 'border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/90 dark:text-amber-50',
    iconClass: 'text-amber-600 dark:text-amber-300',
    alertClass: 'border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/50 dark:text-amber-50',
    duration: 8000,
  },
  info: {
    title: 'Notice',
    icon: Info,
    toastClass: 'border-blue-200 bg-blue-50 text-blue-950 dark:border-blue-900/60 dark:bg-blue-950/90 dark:text-blue-50',
    iconClass: 'text-blue-600 dark:text-blue-300',
    alertClass: 'border-blue-200 bg-blue-50 text-blue-950 dark:border-blue-900/60 dark:bg-blue-950/50 dark:text-blue-50',
    duration: 6500,
  },
}

function normalizeType(type) {
  const value = TYPE_ALIASES[type] || type
  return FEEDBACK_META[value] ? value : 'info'
}

function getMessageText(message) {
  if (message == null) return ''
  if (typeof message === 'string') return message
  return String(message)
}

function ToastItem({ toast, onDismiss }) {
  const type = normalizeType(toast.type)
  const meta = FEEDBACK_META[type]
  const Icon = meta.icon

  useEffect(() => {
    if (toast.duration === Infinity) return undefined
    const timer = window.setTimeout(() => onDismiss(toast.id), toast.duration ?? meta.duration)
    return () => window.clearTimeout(timer)
  }, [meta.duration, onDismiss, toast.duration, toast.id])

  return (
    <div
      role={type === 'error' || type === 'warning' ? 'alert' : 'status'}
      className={`pointer-events-auto flex w-full gap-3 rounded-md border px-4 py-3 shadow-lg shadow-slate-900/10 ring-1 ring-white/40 ${meta.toastClass}`}
    >
      <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${meta.iconClass}`} strokeWidth={1.8} />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold">{toast.title || meta.title}</div>
        <div className="mt-0.5 whitespace-pre-wrap text-sm leading-5">{toast.message}</div>
      </div>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        className="mt-[-0.125rem] rounded-md p-1 text-current opacity-70 transition hover:bg-black/5 hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current/25 dark:hover:bg-white/10"
        aria-label="Dismiss notification"
      >
        <X className="h-4 w-4" strokeWidth={1.8} />
      </button>
    </div>
  )
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idRef = useRef(0)
  const toastsRef = useRef([])
  const dismissedIdsRef = useRef(new Set())

  useEffect(() => {
    toastsRef.current = toasts
  }, [toasts])

  const dismissToast = useCallback((id) => {
    const dismissedToast = toastsRef.current.find((toast) => toast.id === id) || null
    setToasts((current) => current.filter((toast) => toast.id !== id))
    if (dismissedToast && !dismissedIdsRef.current.has(id)) {
      dismissedIdsRef.current.add(id)
      dismissedToast.onDismiss?.()
    }
  }, [])

  const showToast = useCallback((input) => {
    const message = getMessageText(input?.message)
    if (!message.trim()) return null

    idRef.current += 1
    const id = `${Date.now()}-${idRef.current}`
    const type = normalizeType(input.type || input.variant || 'info')
    const toast = {
      id,
      type,
      title: input.title,
      message,
      duration: input.duration,
      onDismiss: input.onDismiss,
    }

    dismissedIdsRef.current.delete(id)
    setToasts((current) => [...current, toast].slice(-5))
    return id
  }, [])

  const value = useMemo(() => ({
    showToast,
    dismissToast,
    success: (message, options = {}) => showToast({ ...options, type: 'success', message }),
    error: (message, options = {}) => showToast({ ...options, type: 'error', message }),
    warning: (message, options = {}) => showToast({ ...options, type: 'warning', message }),
    info: (message, options = {}) => showToast({ ...options, type: 'info', message }),
  }), [dismissToast, showToast])

  return (
    <FeedbackContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed right-4 top-4 z-[80] flex w-[min(28rem,calc(100vw-2rem))] flex-col gap-3 sm:right-6 sm:top-6"
        aria-live="polite"
        aria-relevant="additions"
      >
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onDismiss={dismissToast} />
        ))}
      </div>
    </FeedbackContext.Provider>
  )
}

export function FeedbackToast({ type = 'info', message, title, duration, onDismiss }) {
  const { showToast } = useToast()
  const lastMessageRef = useRef('')

  useEffect(() => {
    const text = getMessageText(message)
    if (!text.trim()) {
      lastMessageRef.current = ''
      return undefined
    }
    if (lastMessageRef.current === text) return undefined

    lastMessageRef.current = text
    showToast({
      type,
      title,
      message: text,
      duration,
      onDismiss: () => {
        lastMessageRef.current = ''
        onDismiss?.()
      },
    })
    return undefined
  }, [duration, message, onDismiss, showToast, title, type])

  return null
}

export function InlineAlert({
  children,
  className = '',
  onDismiss,
  title,
  type = 'info',
  variant,
}) {
  const content = children || ''
  if (!content) return null

  const normalizedType = normalizeType(variant || type)
  const meta = FEEDBACK_META[normalizedType]
  const Icon = meta.icon

  return (
    <div
      role={normalizedType === 'error' || normalizedType === 'warning' ? 'alert' : 'status'}
      className={`flex items-start gap-3 rounded-md border px-4 py-3 text-sm ${meta.alertClass} ${className}`}
    >
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${meta.iconClass}`} strokeWidth={1.8} />
      <div className="min-w-0 flex-1">
        {title && <div className="mb-0.5 font-semibold">{title}</div>}
        <div className="leading-5">{content}</div>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="-mr-1 rounded-md p-1 text-current opacity-70 transition hover:bg-black/5 hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current/25 dark:hover:bg-white/10"
          aria-label="Dismiss message"
        >
          <X className="h-4 w-4" strokeWidth={1.8} />
        </button>
      )}
    </div>
  )
}
