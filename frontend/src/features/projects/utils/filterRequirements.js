const PHASE_LABELS = new Set(['Pre-Implementation', 'Implementation', 'Completion'])

export const SUPPORTED_PHASES = PHASE_LABELS

export function matchesFilters(row, filterState = {}) {
  if (!row) return false

  const {
    search = '',
    phase = '',
    status = '',
    mandatory = '',
  } = filterState || {}

  if (phase && row.phase_name !== phase) return false
  if (status && row.status !== status) return false
  if (mandatory === 'yes' && !row.is_mandatory) return false
  if (mandatory === 'no' && row.is_mandatory) return false

  const needle = String(search).trim().toLowerCase()
  if (needle) {
    const requirementName = String(row.requirement_name ?? '').toLowerCase()
    const annexReference = row.annex_reference ? String(row.annex_reference).toLowerCase() : ''
    return requirementName.includes(needle) || annexReference.includes(needle)
  }

  return true
}

export function filterRequirements(requirements, filterState = {}) {
  if (!Array.isArray(requirements)) return []
  return requirements.filter((row) => matchesFilters(row, filterState))
}

export function countActiveFilters(filterState = {}) {
  if (!filterState) return 0

  const {
    search = '',
    phase = '',
    status = '',
    mandatory = '',
  } = filterState

  return [
    String(search).trim(),
    phase,
    status,
    mandatory,
  ].filter(Boolean).length
}
