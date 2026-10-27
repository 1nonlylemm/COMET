export function isLanguageAdvisory(finding) {
  return finding.advisory_only === true
    || finding.severity === 'advisory'
    || finding.id === 'language_quality_review'
}

export function reviewFindingGroup(finding) {
  if (isLanguageAdvisory(finding) || finding.severity === 'advisory') return 'advisory'
  if (finding.severity !== 'blocker' && (finding.automation_level === 'human_verification'
    || ['needs_verification', 'manual_verification_required'].includes(finding.severity))) return 'needs_verification'
  return ['blocker', 'warning', 'info'].includes(finding.severity) ? finding.severity : 'needs_verification'
}

/**
 * Normalizes language advisory findings into individual displayable observations.
 * When an advisory contains multiple locations, each location is represented as an
 * individual observation using its specific message and contextual attributes.
 * When an advisory has no locations, the finding itself is retained as a single observation.
 */
export function selectAdvisoryObservations(findings) {
  const list = findings || []
  const advisories = list.filter(isLanguageAdvisory)
  const observations = []
  for (const finding of advisories) {
    const locations = Array.isArray(finding?.locations) ? finding.locations : []
    if (locations.length > 0) {
      for (const loc of locations) {
        observations.push({
          ...loc,
          id: finding.id,
          category: finding.category,
          severity: finding.severity,
          message: loc.message || loc.reason || loc.matched_text || finding.message || finding.finding_observation,
          finding_observation: loc.message || loc.reason || loc.matched_text || finding.finding_observation || finding.message,
          page: loc.page ?? finding.page,
        })
      }
    } else {
      observations.push(finding)
    }
  }
  return observations
}

/** Shared presentation counts. Stored severities and compliance decisions are unchanged. */
export function selectReviewFindings(result) {
  const details = result?.score_details || {}
  const checks = result?.evidence_checks ?? details.evidence_checks
  const summary = result?.evidence_summary ?? details.evidence_summary ?? {}
  const required = (checks || []).filter(check => check.state !== 'not_required')
  const count = value => Math.max(0, Number(value) || 0)
  // Prefer the evaluated check list; summary-only legacy results remain supported.
  const configuredFlag = result?.requirement_checks_configured ?? details.requirement_checks_configured
  const configured = configuredFlag === false ? 0 : checks ? required.length : count(summary.required_count)
  const detected = checks ? required.filter(check => check.state === 'detected').length : count(summary.detected_count)
  const groups = { blocker: 0, warning: 0, needs_verification: 0, advisory: 0, info: 0, all: 0 }
  for (const finding of result?.findings || []) {
    groups[reviewFindingGroup(finding)] += 1
    groups.all += 1
  }
  return {
    configured_check_count: configured,
    detected_check_count: Math.min(configured, detected),
    critical_count: groups.blocker,
    attention_count: groups.warning,
    unverified_count: groups.needs_verification,
    advisory_count: groups.advisory,
    manual_check_count: checks ? required.filter(check => check.human_verification_required).length : count(summary.manual_verification_count),
    groups,
  }
}
