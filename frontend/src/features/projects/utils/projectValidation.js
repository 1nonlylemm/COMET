const MIN_FISCAL_YEAR = 2000
const MAX_FISCAL_YEAR = 2100
const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/
const VALID_PROJECT_STATUSES = new Set(['not_yet_started', 'ongoing', 'completed', 'cancelled'])
export const SUBMITTABLE_PROJECT_KINDS = ['infrastructure', 'goods', 'vehicle', 'financial_assistance']

function normalizeIsoDate(value) {
  if (!value) return ''
  if (typeof value !== 'string' || !ISO_DATE_PATTERN.test(value)) return null
  const parsed = new Date(`${value}T00:00:00Z`)
  if (Number.isNaN(parsed.getTime())) return null
  return parsed.toISOString().slice(0, 10) === value ? value : null
}

function validateDateField(values, field, label, errors) {
  if (!(field in values) || !values[field]) return ''
  const normalized = normalizeIsoDate(values[field])
  if (!normalized) errors[field] = `${label} must use YYYY-MM-DD.`
  return normalized || ''
}

export function validateProjectFields(values, { requireCore = false, requireProjectKind = false, requireProjectCode = false } = {}) {
  const errors = {}

  if (requireCore && !values.lgu_id) errors.lgu_id = 'LGU is required.'
  if (requireCore && !values.program_id) errors.program_id = 'Program is required.'
  const projectCode = String(values.source_project_code || '').trim()
  if (requireProjectCode && !projectCode) {
    errors.source_project_code = 'Project code is required.'
  } else if (projectCode.length > 120) {
    errors.source_project_code = 'Project code must be 120 characters or less.'
  }

  if (requireProjectKind && !values.project_kind) {
    errors.project_kind = 'Project classification is required.'
  } else if (values.project_kind && !SUBMITTABLE_PROJECT_KINDS.includes(values.project_kind)) {
    errors.project_kind = 'Select Infrastructure, Goods, Motor Vehicles, or Financial Assistance.'
  }

  if ((requireCore || 'project_name' in values) && !String(values.project_name || '').trim()) {
    errors.project_name = 'Project name is required.'
  } else if (values.project_name && String(values.project_name).trim().length > 300) {
    errors.project_name = 'Project name must be 300 characters or less.'
  }

  if (requireCore || ('fiscal_year' in values && values.fiscal_year !== '')) {
    const fiscalYear = Number(values.fiscal_year)
    if (!Number.isInteger(fiscalYear) || fiscalYear < MIN_FISCAL_YEAR || fiscalYear > MAX_FISCAL_YEAR) {
      errors.fiscal_year = `Fiscal year must be between ${MIN_FISCAL_YEAR} and ${MAX_FISCAL_YEAR}.`
    }
  }

  if ('budget_amount' in values && values.budget_amount !== '' && values.budget_amount !== null && values.budget_amount !== undefined) {
    const rawBudget = typeof values.budget_amount === 'string'
      ? values.budget_amount.replace(/,/g, '').trim()
      : values.budget_amount
    const budget = Number(rawBudget)
    if (!Number.isFinite(budget) || budget < 0) errors.budget_amount = 'Budget amount must be non-negative.'
  }

  if ('physical_completion_pct' in values && values.physical_completion_pct !== '' && values.physical_completion_pct !== null && values.physical_completion_pct !== undefined) {
    const completion = Number(values.physical_completion_pct)
    if (!Number.isFinite(completion) || completion < 0 || completion > 100) {
      errors.physical_completion_pct = 'Physical completion must be between 0 and 100.'
    }
  }

  if ('overall_status' in values && values.overall_status && !VALID_PROJECT_STATUSES.has(values.overall_status)) {
    errors.overall_status = 'Use Not Yet Started, Ongoing, Completed, or Cancelled.'
  }

  const targetStart = validateDateField(values, 'target_start_date', 'Target start date', errors)
  const targetEnd = validateDateField(values, 'target_end_date', 'Target end date', errors)
  const actualStart = validateDateField(values, 'actual_start_date', 'Actual start date', errors)
  const actualEnd = validateDateField(values, 'actual_end_date', 'Actual end date', errors)

  if (targetStart && targetEnd && targetEnd < targetStart) {
    errors.target_end_date = 'Target end date cannot be earlier than target start date.'
  }
  if (actualStart && actualEnd && actualEnd < actualStart) {
    errors.actual_end_date = 'Actual end date cannot be earlier than actual start date.'
  }

  return errors
}

export function hasProjectValidationErrors(errors) {
  return Object.keys(errors).length > 0
}
