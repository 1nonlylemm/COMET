import {
  File,
  FileArchive,
  FileCode2,
  FileImage,
  FileSpreadsheet,
  FileText,
  Presentation,
} from 'lucide-react'
import { formatDate } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'

export { formatDate }

export function getFileExtension(fileName = '') {
  const normalized = String(fileName).trim()
  const lastDot = normalized.lastIndexOf('.')
  if (lastDot <= 0 || lastDot === normalized.length - 1) return ''
  return normalized.slice(lastDot + 1).toLowerCase()
}

export function fileMeta(fileName = '') {
  const extension = getFileExtension(fileName)
  if (['pdf'].includes(extension)) {
    return { Icon: FileText, label: 'PDF', className: 'border-red-300 bg-red-50 text-red-700 dark:border-red-400/40 dark:bg-red-400/10 dark:text-red-200' }
  }
  if (['doc', 'docx', 'odt', 'rtf', 'txt'].includes(extension)) {
    return { Icon: FileText, label: extension || 'DOC', className: 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-400/40 dark:bg-blue-400/10 dark:text-blue-200' }
  }
  if (['xls', 'xlsx', 'csv', 'ods'].includes(extension)) {
    return { Icon: FileSpreadsheet, label: extension || 'XLS', className: 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-400/40 dark:bg-emerald-400/10 dark:text-emerald-200' }
  }
  if (['ppt', 'pptx', 'odp'].includes(extension)) {
    return { Icon: Presentation, label: extension || 'PPT', className: 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-300/40 dark:bg-amber-300/10 dark:text-amber-100' }
  }
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(extension)) {
    return { Icon: FileImage, label: extension || 'IMG', className: 'border-cyan-300 bg-cyan-50 text-cyan-800 dark:border-cyan-300/40 dark:bg-cyan-300/10 dark:text-cyan-100' }
  }
  if (['zip', 'rar', '7z'].includes(extension)) {
    return { Icon: FileArchive, label: extension || 'ZIP', className: 'border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-500/50 dark:bg-slate-500/15 dark:text-slate-200' }
  }
  if (['json', 'xml', 'html'].includes(extension)) {
    return { Icon: FileCode2, label: extension || 'FILE', className: 'border-cyan-300 bg-cyan-50 text-cyan-800 dark:border-cyan-300/40 dark:bg-cyan-300/10 dark:text-cyan-100' }
  }
  return { Icon: File, label: extension || 'FILE', className: 'border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-500/50 dark:bg-slate-500/15 dark:text-slate-200' }
}

export function canPreviewInline(fileName = '', mimeType = '') {
  const extension = getFileExtension(fileName)
  const normalizedMime = String(mimeType || '').toLowerCase()
  return (
    normalizedMime.includes('pdf')
    || normalizedMime.startsWith('image/')
    || normalizedMime.startsWith('text/')
    || ['pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'txt', 'csv'].includes(extension)
  )
}

export function formatConfidence(value) {
  const numeric = Number(value || 0)
  if (!Number.isFinite(numeric) || numeric <= 0) return '—'
  return `${Math.round(numeric * 100)}%`
}

export function matchTier(value) {
  const numeric = Number(value || 0)
  if (!Number.isFinite(numeric) || numeric < 0.50) return 'Review Needed'
  if (numeric >= 0.80) return 'Strong Match'
  return 'Possible Match'
}

export function matchTierBadgeClass(tier) {
  if (tier === 'Strong Match') {
    return 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-400/40 dark:bg-emerald-400/10 dark:text-emerald-200'
  }
  if (tier === 'Possible Match') {
    return 'border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-400/40 dark:bg-blue-400/10 dark:text-blue-200'
  }
  return 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-400/40 dark:bg-amber-400/10 dark:text-amber-200'
}

export function scanStatusLabel(scan) {
  if (!scan) return 'No Scan'
  if (scan.is_accepted === true) return 'Accepted'
  if (scan.is_accepted === false) return 'Mapping Rejected'
  if (scan.mapping_mismatch) return 'Needs Mapping Review'
  if (scan.needs_review) return 'Needs Review'
  return 'Suggested'
}

export function scanStatusClass(scan) {
  if (!scan) return 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
  if (scan.is_accepted === true) return badgeClassForStatus('compliant')
  if (scan.is_accepted === false) return badgeClassForStatus('non_compliant')
  if (scan.mapping_mismatch || scan.needs_review) return badgeClassForStatus('under_review')
  return badgeClassForStatus('pending')
}

export function complianceStatusLabel(result) {
  if (!result) return 'No Checker Result'
  if (result.status === 'check_failed') return 'Check Failed'
  return 'Review Required'
}

export function complianceStatusClass(result) {
  if (!result) return 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
  if (result.status === 'check_failed') return badgeClassForStatus('failed')
  return badgeClassForStatus('under_review')
}

export function formatEvidenceSummary(result) {
  const summary = result?.evidence_summary || result?.score_details?.evidence_summary
  if (summary && typeof summary === 'object' && Number.isFinite(Number(summary.required_count))) {
    const detected = summary.detected_count ?? 0
    const required = summary.required_count ?? 0
    if (required > 0) {
      return `${detected}/${required} Evidence Detected`
    }
  }
  return 'Evidence Checked'
}

export function formatComplianceScore(result) {
  return formatEvidenceSummary(result)
}

export function reviewTask(row, isFieldOfficer = false) {
  if (row.status === 'compliant') {
    return {
      label: isFieldOfficer ? 'Approved' : 'Approved for Handoff',
      detail: isFieldOfficer ? 'Approved by reviewing office' : 'Ready for regional handoff',
      tone: 'compliant',
    }
  }
  if (row.status === 'waived') {
    return {
      label: 'Waived',
      detail: 'No attachment review needed',
      tone: 'waived',
    }
  }
  if (row.status === 'non_compliant') {
    return {
      label: 'Non-Compliant',
      detail: isFieldOfficer ? 'Non-compliant status recorded' : 'Overdue escalation state',
      tone: 'non_compliant',
    }
  }
  if (row.workflow_status === 'returned_for_revision') {
    return {
      label: 'Needs Revision',
      detail: row.workflow_return_reason || row.current_return?.notes || row.latest_revision?.notes || 'Correction requested',
      tone: 'under_review',
    }
  }
  if (row.workflow_status === 'resubmitted') {
    return {
      label: 'Resubmitted',
      detail: isFieldOfficer ? 'Awaiting staff re-evaluation' : 'Evaluate resubmitted document',
      tone: 'under_review',
    }
  }
  if (row.has_documentary_evidence) {
    return {
      label: isFieldOfficer ? 'Under Review' : 'Evaluate Attachment',
      detail: isFieldOfficer ? 'Awaiting staff evaluation' : 'Approve or return with feedback',
      tone: 'under_review',
    }
  }
  return {
    label: 'Awaiting Document',
    detail: isFieldOfficer ? 'Upload required documentary file' : 'Record DMS or field evidence',
    tone: 'pending',
  }
}

export function phaseBadgeClass(phaseName = '') {
  const normalized = String(phaseName).toLowerCase()
  if (normalized.includes('pre')) {
    return 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-300/40 dark:bg-blue-300/10 dark:text-blue-100'
  }
  if (normalized.includes('completion')) {
    return 'border-cyan-300 bg-cyan-50 text-cyan-800 dark:border-cyan-300/40 dark:bg-cyan-300/10 dark:text-cyan-100'
  }
  if (normalized.includes('implementation')) {
    return 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-300/40 dark:bg-emerald-300/10 dark:text-emerald-100'
  }
  return 'border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-500/50 dark:bg-slate-500/15 dark:text-slate-200'
}
