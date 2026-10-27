/**
 * Authoritative shared project implementation status palette and metadata.
 * Keep in sync with backend/app/services/reporting_visuals.py (STATUS_COLORS).
 */

export const PROJECT_STATUS_CONFIG = {
  completed: {
    key: 'completed',
    label: 'Completed',
    color: '#10b981', // emerald-500
    hoverColor: '#059669', // emerald-600
    bgClass: 'bg-emerald-500',
    textClass: 'text-emerald-700 dark:text-emerald-400',
    ringClass: 'ring-emerald-500/50',
    badge: 'bg-emerald-500',
  },
  ongoing: {
    key: 'ongoing',
    label: 'Ongoing',
    color: '#3b82f6', // blue-500
    hoverColor: '#2563eb', // blue-600
    bgClass: 'bg-blue-500',
    textClass: 'text-blue-700 dark:text-blue-400',
    ringClass: 'ring-blue-500/50',
    badge: 'bg-blue-500',
  },
  not_yet_started: {
    key: 'not_yet_started',
    label: 'Not Yet Started',
    color: '#f59e0b', // amber-500
    hoverColor: '#d97706', // amber-600
    bgClass: 'bg-amber-500',
    textClass: 'text-amber-700 dark:text-amber-400',
    ringClass: 'ring-amber-500/50',
    badge: 'bg-amber-500',
  },
  cancelled: {
    key: 'cancelled',
    label: 'Cancelled',
    color: '#ef4444', // red-500
    hoverColor: '#dc2626', // red-600
    bgClass: 'bg-red-500',
    textClass: 'text-rose-700 dark:text-rose-400',
    ringClass: 'ring-red-500/50',
    badge: 'bg-red-500',
  },
}

export const CANONICAL_STATUS_ORDER = ['completed', 'ongoing', 'not_yet_started', 'cancelled']

export function getProjectStatusConfig(status) {
  return PROJECT_STATUS_CONFIG[status] || {
    key: status,
    label: status ? String(status).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : 'Unknown',
    color: '#94a3b8',
    hoverColor: '#64748b',
    bgClass: 'bg-slate-500',
    textClass: 'text-slate-700 dark:text-slate-400',
    ringClass: 'ring-slate-500/50',
    badge: 'bg-slate-500',
  }
}
