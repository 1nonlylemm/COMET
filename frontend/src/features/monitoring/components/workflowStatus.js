// Shared helpers for the Phase 2A document workflow (Monthly Progress
// Report, Form 3, Project Exception Report) reused across their panels.
// Mirrors the Phase 1 shared workflow states exactly.

export const WORKFLOW_STATUS_LABELS = {
  draft: 'Draft',
  submitted: 'Submitted',
  under_verification: 'Under Verification',
  staff_approved: 'Staff Approved',
  pending_provincial_approval: 'Pending Provincial Approval',
  approved: 'Approved',
  returned_for_revision: 'Returned for Revision',
  resubmitted: 'Resubmitted',
}

export function workflowStatusLabel(status) {
  return WORKFLOW_STATUS_LABELS[status] || status || 'Draft'
}

export function workflowStatusTone(status) {
  switch (status) {
    case 'approved':
      return 'success'
    case 'returned_for_revision':
      return 'warning'
    case 'draft':
      return 'neutral'
    case 'staff_approved':
    case 'pending_provincial_approval':
      return 'warning'
    default:
      return 'info'
  }
}

export const RISK_LEVEL_LABELS = {
  none: 'No Risk',
  minor: 'Low Risk',
  major: 'Moderate Risk',
  severe: 'High Risk',
}

export function riskLevelLabel(level) {
  if (!level) return 'Not yet assessed'
  return RISK_LEVEL_LABELS[level] || level
}

export function riskLevelTone(level) {
  switch (level) {
    case 'severe':
      return 'danger'
    case 'major':
      return 'warning'
    case 'minor':
      return 'info'
    case 'none':
      return 'success'
    default:
      return 'neutral'
  }
}

export function canFieldOfficerSubmit(status) {
  return !status || status === 'draft' || status === 'returned_for_revision'
}

export function canStaffVerify(status) {
  return status === 'submitted' || status === 'resubmitted'
}
export const canVerify = canStaffVerify

export function canStaffApprove(status) {
  return status === 'under_verification'
}
export const canPreliminaryApprove = canStaffApprove

export function canProvincialApprove(status) {
  return status === 'pending_provincial_approval' || status === 'staff_approved'
}

export function canReturn(status) {
  return ['submitted', 'under_verification', 'staff_approved', 'pending_provincial_approval', 'resubmitted'].includes(status)
}

export const DEFICIENCY_CATEGORY_LABELS = {
  missing_attachment: 'Missing Required Attachment',
  missing_signature_notarization: 'Missing Signature or Notarization',
  cross_document_inconsistency: 'Cross-Document Inconsistency',
  costing_dupa_defect: 'Costing / DUPA Defect',
  missing_statutory_clearance: 'Missing Statutory Clearance',
  program_specific_non_conformity: 'Program Guidelines Non-Conformity',
  financial_reconciliation_defect: 'Financial Reconciliation Discrepancy',
  scan_quality_defect: 'Scan Quality / Legibility Defect',
  other_documented_defect: 'Other Documented Technical Defect',
}

export function deficiencyCategoryLabel(cat) {
  return DEFICIENCY_CATEGORY_LABELS[cat] || cat || 'Documented Defect'
}

export const DEFICIENCY_STATE_LABELS = {
  open: 'Open Finding',
  resolved: 'Resolved',
  waived: 'Waived',
}

export function deficiencyStateTone(state) {
  switch (state) {
    case 'resolved':
      return 'success'
    case 'waived':
      return 'neutral'
    case 'open':
    default:
      return 'warning'
  }
}

