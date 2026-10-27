export const STANDARD_SIGNATORY_ROLES = [
  { key: 'prepared_by', label: 'Prepared by' },
  { key: 'reviewed_by', label: 'Reviewed by' },
  { key: 'approved_by', label: 'Approved by' },
  { key: 'certified_by', label: 'Certified by' },
  { key: 'noted_by', label: 'Noted by' },
  { key: 'attested_by', label: 'Attested by' },
]

export function defaultCheckerConfig() {
  return {
    requires_signatories: false,
    signatory_roles: ['prepared_by', 'approved_by'],
    custom_signatory_roles: [],
    requires_certification: false,
    certification_phrases: [],
    requires_notarization: false,
    notarization_phrases: [],
    requires_date: false,
    required_phrases: [],
  }
}
