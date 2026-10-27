import {
  Bell,
  Upload,
  FileEdit,
  Clock,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ShieldAlert,
} from 'lucide-react'

export const NOTIFICATION_CATEGORIES = {
  revision_needed: {
    icon: FileEdit,
    color: 'amber',
    label: 'Revisions Needed',
    bgClass: 'bg-amber-50 dark:bg-amber-950/30',
    iconClass: 'text-amber-700 dark:text-amber-400',
    borderClass: 'border-amber-200 dark:border-amber-800',
  },
  approval: {
    icon: CheckCircle2,
    color: 'green',
    label: 'Approvals',
    bgClass: 'bg-green-50 dark:bg-green-950/30',
    iconClass: 'text-green-700 dark:text-green-400',
    borderClass: 'border-green-200 dark:border-green-800',
  },
  rejection: {
    icon: XCircle,
    color: 'red',
    label: 'Non-Compliance',
    bgClass: 'bg-red-50 dark:bg-red-950/30',
    iconClass: 'text-red-700 dark:text-red-400',
    borderClass: 'border-red-200 dark:border-red-800',
  },
  deadline: {
    icon: Clock,
    color: 'orange',
    label: 'Deadlines & Overdue',
    bgClass: 'bg-orange-50 dark:bg-orange-950/30',
    iconClass: 'text-orange-700 dark:text-orange-400',
    borderClass: 'border-orange-200 dark:border-orange-800',
  },
  alert: {
    icon: AlertTriangle,
    color: 'red',
    label: 'Alerts & Escalations',
    bgClass: 'bg-red-50 dark:bg-red-950/30',
    iconClass: 'text-red-700 dark:text-red-400',
    borderClass: 'border-red-200 dark:border-red-800',
  },
  security: {
    icon: ShieldAlert,
    color: 'purple',
    label: 'Security Alerts',
    bgClass: 'bg-purple-50 dark:bg-purple-950/30',
    iconClass: 'text-purple-600 dark:text-purple-400',
    borderClass: 'border-purple-200 dark:border-purple-800',
  },
  upload: {
    icon: Upload,
    color: 'blue',
    label: 'Submissions & Uploads',
    bgClass: 'bg-blue-50 dark:bg-blue-950/30',
    iconClass: 'text-blue-600 dark:text-blue-400',
    borderClass: 'border-blue-200 dark:border-blue-800',
  },
  information: {
    icon: Bell,
    color: 'slate',
    label: 'Information & Notices',
    bgClass: 'bg-slate-50 dark:bg-slate-950/30',
    iconClass: 'text-slate-600 dark:text-slate-400',
    borderClass: 'border-slate-200 dark:border-slate-800',
  },
  default: {
    icon: Bell,
    color: 'slate',
    label: 'General',
    bgClass: 'bg-slate-50 dark:bg-slate-950/30',
    iconClass: 'text-slate-600 dark:text-slate-400',
    borderClass: 'border-slate-200 dark:border-slate-800',
  },
}

/**
 * Determine semantic presentation category for a notification.
 * Evaluates authoritative notification_type first, before falling back
 * to legacy title/message substring matching.
 *
 * Guaranteed: 'returned' notifications are classified as 'revision_needed' (amber),
 * never conflated with 'rejection' (red).
 */
export function getNotificationCategory(notification) {
  if (!notification) return 'default'

  // Primary: evaluate authoritative notification_type
  const ntype = notification.notification_type
  if (ntype) {
    // 1. Revision needed (explicitly non-punitive, distinct from rejection)
    if (
      ntype === 'workflow_document_returned' ||
      ntype === 'revision_pending_reminder'
    ) {
      return 'revision_needed'
    }

    // 2. Approvals
    if (
      ntype === 'workflow_document_approved' ||
      ntype === 'workflow_staff_approved' ||
      ntype === 'submission_approved'
    ) {
      return 'approval'
    }

    // 3. Rejection / Non-compliance
    if (
      ntype === 'compliance_breach' ||
      ntype === 'default_entered'
    ) {
      return 'rejection'
    }

    // 4. Deadlines & Overdue
    if (
      ntype === 'project_deadline_approaching' ||
      ntype === 'milestone_overdue' ||
      ntype === 'site_visit_overdue' ||
      ntype === 'progress_report_overdue' ||
      ntype === 'notice_follow_up_due' ||
      ntype === 'submission_unreviewed_reminder' ||
      ntype === 'resubmission_unreviewed_reminder' ||
      ntype === 'requirement_missing_reminder' ||
      ntype === 'provincial_approval_reminder'
    ) {
      return 'deadline'
    }

    // 5. Alerts & Escalations
    if (
      ntype === 'sla_warning' ||
      ntype === 'sla_breached' ||
      ntype === 'sla_critical_alert' ||
      ntype === 'sla_breach_warning' ||
      ntype === 'escalation_recommended' ||
      ntype === 'compliance_warning' ||
      ntype === 'project_risk_alert'
    ) {
      return 'alert'
    }

    // 6. Security
    if (ntype === 'security_alert') {
      return 'security'
    }

    // 7. Uploads / Submissions
    if (
      ntype === 'workflow_document_submitted' ||
      ntype === 'submission_received'
    ) {
      return 'upload'
    }

    // 8. Information & Notices
    if (
      ntype === 'workflow_pending_provincial_approval' ||
      ntype === 'notice_pending_release' ||
      ntype === 'notice_pending_receipt' ||
      ntype === 'notice_issued' ||
      ntype === 'notice_served' ||
      ntype === 'notice_acknowledged' ||
      ntype === 'notice_appealed' ||
      ntype === 'appeal_decided' ||
      ntype === 'mar_generated' ||
      ntype === 'mar_submitted' ||
      ntype === 'mar_acted' ||
      ntype === 'mar_closed' ||
      ntype === 'project_reopened' ||
      ntype === 'requirement_privilege_override' ||
      ntype === 'mar_privilege_override' ||
      ntype === 'system_alert'
    ) {
      return 'information'
    }

    // Safe neutral fallback for unknown / future notification_type:
    // Unknown notification types must NEVER be inferred from notification title text as "rejection".
    return 'information'
  }

  // Fallback ONLY when notification_type is completely absent (e.g. legacy fixture data)
  // Rejection is strictly type-driven and NEVER inferred from title text.
  const title = (notification.title || '').toLowerCase()
  const message = (notification.message || '').toLowerCase()

  if (title.includes('returned') || title.includes('revision') || message.includes('returned for revision')) {
    return 'revision_needed'
  }
  if (!title.includes('non-compliant') && !message.includes('non-compliant')) {
    if (title.includes('approved') || title.includes('compliant') || message.includes('approved')) {
      return 'approval'
    }
  }
  if (title.includes('deadline') || title.includes('overdue') || title.includes('due')) {
    return 'deadline'
  }
  if (title.includes('alert') || title.includes('warning')) {
    return 'alert'
  }
  if (title.includes('security') || message.includes('security')) {
    return 'security'
  }
  if (title.includes('uploaded') || message.includes('uploaded') || title.includes('submitted')) {
    return 'upload'
  }

  return 'information'
}
