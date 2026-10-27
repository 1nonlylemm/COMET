const TONE_BADGE_CLASS = {
  success: 'status-badge-success',
  warning: 'status-badge-warning',
  danger: 'status-badge-danger',
  info: 'status-badge-info',
  handoff: 'status-badge-handoff',
  neutral: 'status-badge-neutral',
}

const TONE_TEXT_CLASS = {
  success: 'status-text-success',
  warning: 'status-text-warning',
  danger: 'status-text-danger',
  info: 'status-text-info',
  handoff: 'text-cyan-700 dark:text-cyan-200',
  neutral: 'status-text-neutral',
}

const STATUS_TONES = {
  active: 'success',
  approved: 'success',
  complete: 'success',
  compliant: 'success',
  resolved: 'success',
  reviewed: 'success',
  ready: 'success',
  valid: 'success',

  acknowledged: 'warning',
  due_today: 'warning',
  implementation: 'warning',
  pending: 'warning',
  rectification_period: 'warning',
  standard_15day: 'warning',
  suspended: 'warning',
  waiting: 'warning',

  blocked: 'danger',
  breached: 'danger',
  deficient: 'danger',
  expired: 'danger',
  failed: 'danger',
  cancelled: 'danger',
  missing: 'danger',
  non_compliant: 'danger',
  notice_of_eligibility_5day: 'danger',
  overdue: 'danger',
  returned: 'danger',
  terminated: 'danger',

  custom_sla: 'info',
  draft: 'info',
  in_progress: 'info',
  ongoing: 'info',
  open: 'info',
  pre_implementation: 'info',
  submitted: 'info',
  under_review: 'info',

  completion: 'handoff',
  completed: 'handoff',
  handed_off: 'handoff',
  pushed: 'handoff',
  sent: 'handoff',
  transmitted: 'handoff',

  archived: 'neutral',
  disabled: 'neutral',
  flagged: 'danger',
  inactive: 'neutral',
  not_required: 'neutral',
  not_yet_started: 'neutral',
  not_started: 'neutral',
  not_applicable: 'neutral',
  skipped: 'neutral',
  waived: 'neutral',
}

function normalizeStatus(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
}

export function toneForStatus(value, fallbackTone = 'neutral') {
  return STATUS_TONES[normalizeStatus(value)] || fallbackTone
}

export function badgeClassForStatus(value, fallbackTone = 'neutral') {
  return `status-badge ${TONE_BADGE_CLASS[toneForStatus(value, fallbackTone)] || TONE_BADGE_CLASS.neutral}`
}

export function badgeClassForTone(tone = 'neutral') {
  return `status-badge ${TONE_BADGE_CLASS[tone] || TONE_BADGE_CLASS.neutral}`
}

export function textClassForStatus(value, fallbackTone = 'neutral') {
  return TONE_TEXT_CLASS[toneForStatus(value, fallbackTone)] || TONE_TEXT_CLASS.neutral
}
