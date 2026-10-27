/**
 * Applicability utilities and client-side guards for project documentary requirements.
 */
import { formatStatus } from '../../../lib/formatters'

export function validateApplicabilityReason(reason) {
  const trimmed = String(reason || '').trim()
  if (!trimmed) {
    return 'A justification is required when marking a requirement as Not Applicable.'
  }
  const words = trimmed.toLowerCase().match(/\b[a-z]+\b/g) || []
  const denylist = new Set(['n/a', 'na', 'none', 'nil', 'tbd', 'test', 'x', 'nothing', 'blank'])
  const validWords = words.filter(
    w => !denylist.has(w) && w.length >= 3 && /[aeiouy]/.test(w)
  )
  if (validWords.length < 3) {
    return 'Justification must contain at least 3 meaningful words (not placeholders or abbreviations).'
  }
  return null
}

export function checkApplicabilityEligibility(requirement) {
  if (!requirement) return { eligible: false, reason: 'No requirement specified.' }
  if (requirement.is_active === false) {
    return {
      eligible: false,
      reason: 'Cannot change applicability of an inactive historical requirement.',
    }
  }
  if (['final_swa', 'final_inspection_report', 'certificate_of_final_acceptance',
    'final_sord', 'proof_of_return_of_funds'].includes(requirement.document_category)) {
    return {
      eligible: false,
      reason: 'Manage Completion Matrix applicability through the Completion controls.',
    }
  }
  const inFlight = [
    'submitted',
    'under_verification',
    'staff_approved',
    'pending_provincial_approval',
    'resubmitted',
  ]
  if (inFlight.includes(requirement.workflow_status)) {
    return {
      eligible: false,
      reason: `Cannot mark Not Applicable while document review is in flight (${formatStatus(requirement.workflow_status)}).`,
    }
  }
  if (requirement.workflow_status === 'approved') {
    return {
      eligible: false,
      reason: 'Cannot mark Not Applicable after document review has been approved.',
    }
  }
  if (requirement.workflow_status === 'returned_for_revision') {
    return {
      eligible: false,
      reason: 'Cannot mark Not Applicable while returned for revision. Resolve or cancel the revision first.',
    }
  }
  if (requirement.has_documentary_evidence || requirement.submission_count > 0) {
    return {
      eligible: false,
      reason: 'Cannot mark Not Applicable when uploaded documents exist. Remove documents first.',
    }
  }
  const reviewedStatuses = ['compliant', 'non_compliant', 'waived', 'under_review']
  if (reviewedStatuses.includes(requirement.status)) {
    return {
      eligible: false,
      reason: `Cannot mark Not Applicable when compliance status is '${formatStatus(requirement.status)}'.`,
    }
  }
  if (requirement.open_deficiencies_count > 0 || requirement.open_deficiencies > 0) {
    return {
      eligible: false,
      reason: 'Cannot mark Not Applicable with open deficiency item(s).',
    }
  }
  return { eligible: true, reason: null }
}
