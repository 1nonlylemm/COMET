const DISPLAY_FALLBACK = '—'

const ACRONYM_LABELS = new Map([
  ['ai', 'AI'],
  ['aip', 'AIP'],
  ['api', 'API'],
  ['csv', 'CSV'],
  ['db', 'DB'],
  ['dilg', 'DILG'],
  ['dms', 'DMS'],
  ['docx', 'DOCX'],
  ['dpwh', 'DPWH'],
  ['drsl', 'DRSL'],
  ['fy', 'FY'],
  ['id', 'ID'],
  ['json', 'JSON'],
  ['jwt', 'JWT'],
  ['lbc', 'LBC'],
  ['ldip', 'LDIP'],
  ['lgu', 'LGU'],
  ['lgus', 'LGUs'],
  ['mgb', 'MGB'],
  ['noa', 'NOA'],
  ['noe', 'NoE'],
  ['ntp', 'NTP'],
  ['pdf', 'PDF'],
  ['pdmu', 'PDMU'],
  ['qaar', 'QAAR'],
  ['rrow', 'RROW'],
  ['rssa', 'RSSA'],
  ['sbr', 'SBR'],
  ['sla', 'Deadline'],
  ['slas', 'Deadlines'],
  ['smtp', 'SMTP'],
  ['sord', 'SORD'],
  ['ssl', 'SSL'],
  ['swa', 'SWA'],
  ['url', 'URL'],
  ['xls', 'XLS'],
  ['xlsx', 'XLSX'],
])

const EXACT_LABELS = new Map([
  ['acknowledged', 'Acknowledged'],
  ['aide_memoire', 'Aide Memoire'],
  ['annex_e', 'Notice of Deficiencies (Annex E)'],
  ['annex_m', 'Notice of Non-Compliance No. 1 (Annex M)'],
  ['annex_n', 'Notice of Non-Compliance No. 2 (Annex N)'],
  ['annex_o', 'Notice of Non-Compliance No. 3 (Annex O)'],
  ['api_push', 'API Upload'],
  ['custom_sla', 'Internal Tracking Timer'],
  ['custom_field', 'Custom Field'],
  ['custom_numeric_field', 'Custom Numeric Field'],
  ['direct_upload', 'Direct Upload'],
  ['dms_ingestion', 'DMS Ingestion'],
  ['field_officer', 'Field Officer'],
  ['field_upload', 'Field Upload'],
  ['follow_up', 'Follow-Up / Corrective Action'],
  ['google_drive', 'Google Drive'],
  ['in_progress', 'In Progress'],
  ['local_budget_circular', 'Local Budget Circular'],
  ['manual_print', 'Manual Print'],
  ['non_compliant', 'Non-Compliant'],
  ['non_infrastructure', 'Non-Infrastructure'],
  ['not_required', 'Not Required'],
  ['not_yet_started', 'Not Yet Started'],
  ['not_started', 'Not Started'],
  ['ongoing', 'Ongoing'],
  ['cancelled', 'Cancelled'],
  ['generate_notice_for_sla', 'Prepare Notice for Deadline'],
  ['get_sla_summary', 'Review Deadline Summary'],
  ['list_handoff_queue', 'Review Regional Handoff Queue'],
  ['list_import_batches', 'Review Workbook Import Batches'],
  ['list_monitoring_inspections', 'Review Monitoring Records'],
  ['list_non_infra_monitoring_records', 'Review Non-Infrastructure Monitoring Records'],
  ['list_beneficiary_evidence_records', 'Review Beneficiary Evidence Records'],
  ['query_requirements', 'Query Requirements'],
  ['get_requirement_detail', 'Requirement Details'],
  ['list_overdue_slas', 'List Overdue Deadlines'],
  ['magic_link', 'Read-Only Checklist Link'],
  ['magic_link_dispatch', 'Read-Only Checklist Link Dispatch'],
  ['magic_links', 'Read-Only Checklist Links'],
  ['monitoring_workbench', 'Review Monitoring Workbench'],
  ['notice_of_eligibility_5day', 'Notice of Eligibility (5 Working Days)'],
  ['omnibus_guideline', 'Omnibus Guideline'],
  ['openrouter', 'OpenRouter'],
  ['pending_confirmation', 'Pending Confirmation'],
  ['pre_implementation', 'Pre-Implementation'],
  ['rectification_period', 'Rectification Period'],
  ['reference_lookup', 'Reference Lookup'],
  ['project_reporting', 'Project Reporting'],
  ['project_monitoring', 'Project Monitoring'],
  ['lgu.name', 'LGU Name'],
  ['lgu.province', 'LGU Province'],
  ['monitoring.disbursement_amount', 'Disbursement Amount'],
  ['monitoring.financial_accomplishment_pct', 'Financial Accomplishment %'],
  ['monitoring.obligation_amount', 'Obligation Amount'],
  ['monitoring.physical_completion_pct', 'Physical Completion %'],
  ['site_validation', 'Site Validation'],
  ['program_cycle.fiscal_year', 'Program Cycle Fiscal Year'],
  ['project.budget_amount', 'Project Budget'],
  ['project.implementation_period', 'Implementation Period'],
  ['project.location', 'Project Location'],
  ['project.mode_of_implementation', 'Mode of Implementation'],
  ['project.overall_status', 'Project Status'],
  ['project.project_name', 'Project Name'],
  ['project.source_project_code', 'Project Source Code'],
  ['project.target_beneficiaries', 'Target Beneficiaries'],
  ['push_requirement_handoff', 'Upload Requirement for Regional Handoff'],
  ['resolve_sla_deadline', 'Close Compliance Deadline'],
  ['settings_readiness', 'Review System Checks'],
  ['standard_15day', '15-Working-Day Notice Window'],
  ['under_review', 'Under Review'],
])

const ROLE_LABELS = new Map([
  ['system_admin', 'System Admin'],
  ['admin', 'Admin'],
  ['staff', 'Staff'],
  ['field_officer', 'Field Officer'],
])

const SMALL_WORDS = new Set(['a', 'an', 'and', 'as', 'at', 'by', 'for', 'from', 'in', 'of', 'on', 'or', 'the', 'to', 'with'])

const MACHINE_KEY_PATTERN = /(^|_)(action|category|channel|delivery|detected|entity|flow|phase|priority|role|scope|source|state|status|type|value)($|_)/
const PRESERVE_KEY_PATTERN = /(^|_)(code|description|destination|email|file|hash|id|link|name|notes|path|phone|reference|subject|title|url)($|_)/
const MACHINE_VALUE_PATTERN = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$/

function normalize(value, fallback = DISPLAY_FALLBACK) {
  if (value === null || value === undefined) return fallback
  const text = String(value).trim().replace(/\s+/g, ' ')
  return text || fallback
}

function formatWord(word, index) {
  const lower = word.toLowerCase()
  const fiscalYear = lower.match(/^fy(\d{4})$/)
  const dayCount = lower.match(/^(\d+)(day|days)$/)

  if (ACRONYM_LABELS.has(lower)) return ACRONYM_LABELS.get(lower)
  if (fiscalYear) return `FY ${fiscalYear[1]}`
  if (dayCount) return `${dayCount[1]}-${dayCount[2] === 'days' ? 'Days' : 'Day'}`
  if (/^\d+$/.test(word)) return word
  if (index > 0 && SMALL_WORDS.has(lower)) return lower

  return `${lower.charAt(0).toUpperCase()}${lower.slice(1)}`
}

function titleizeWords(text) {
  return text.split(' ').map((word, index) => formatWord(word, index)).join(' ')
}

export function formatMachineLabel(value, fallback = DISPLAY_FALLBACK) {
  const normalized = normalize(value, fallback)
  if (normalized === fallback) return fallback

  const exactKey = normalized.toLowerCase()
  if (EXACT_LABELS.has(exactKey)) return EXACT_LABELS.get(exactKey)

  return titleizeWords(normalized.replace(/[_.-]+/g, ' '))
}

export function formatStatus(value, fallback = DISPLAY_FALLBACK) {
  return formatMachineLabel(value, fallback)
}

export function formatRole(value, fallback = DISPLAY_FALLBACK) {
  const normalized = normalize(value, fallback)
  if (normalized === fallback) return fallback

  const exactKey = normalized.toLowerCase()
  if (ROLE_LABELS.has(exactKey)) return ROLE_LABELS.get(exactKey)

  return formatMachineLabel(value, fallback)
}

export function formatBoolean(value) {
  return value ? 'Yes' : 'No'
}

export function formatPlainText(value, fallback = DISPLAY_FALLBACK) {
  return normalize(value, fallback)
}

const AMOUNT_KEY_PATTERN = /(amount|budget|cost|price|balance|counterpart|subsidy|disbursement|obligation|allocation|revenue|expenditure|fund|fee|contract|total_project_cost)/i
const PRESERVE_NUMERIC_PATTERN = /(^|_)(year|fy|id|code|order|seq|step|count|total_count|pct|percent|percentage|ratio|version)($|_)/i

/**
 * Format a number or numeric string as an amount with commas (thousands separators).
 * Example: 10000000 -> "10,000,000", 10000000.5 -> "10,000,000.5", 10000000.50 -> "10,000,000.50"
 */
export function formatAmount(value, options = {}) {
  const {
    fallback = DISPLAY_FALLBACK,
    withSymbol = false,
    symbol = '₱',
    minimumFractionDigits,
    maximumFractionDigits = 2,
  } = options

  if (value === null || value === undefined || value === '') return fallback

  const rawStr = String(value).trim()
  if (!rawStr) return fallback

  // Strip non-digit characters except negative sign and decimal point
  const clean = rawStr.replace(/[^\d.-]/g, '')
  if (!clean || clean === '-' || clean === '.') return fallback

  const num = Number(clean)
  if (!Number.isFinite(num)) return fallback

  const hasDecimals = clean.includes('.')
  const rawDecimals = hasDecimals ? clean.split('.')[1].length : 0
  const minDigits = minimumFractionDigits !== undefined
    ? minimumFractionDigits
    : (hasDecimals ? Math.min(rawDecimals, maximumFractionDigits) : 0)
  const maxDigits = Math.max(minDigits, maximumFractionDigits)

  const formatted = num.toLocaleString('en-PH', {
    minimumFractionDigits: minDigits,
    maximumFractionDigits: maxDigits,
  })

  return withSymbol ? `${symbol}${formatted}` : formatted
}

/**
 * Format a number or numeric string as currency with PHP symbol (default 2 decimal places).
 * Example: 10000000 -> "₱10,000,000.00"
 */
export function formatCurrency(value, options = {}) {
  return formatAmount(value, {
    withSymbol: true,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    ...options,
  })
}

/**
 * Parse an amount or money string into a clean float number, removing commas and symbols.
 * Example: "10,000,000.50" -> 10000000.5, "₱5,000" -> 5000, "" -> null
 */
export function parseAmount(value) {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  const clean = String(value).replace(/[^\d.-]/g, '')
  if (!clean || clean === '-' || clean === '.') return null
  const num = parseFloat(clean)
  return Number.isFinite(num) ? num : null
}

/**
 * Live formatter for input fields as users type amounts / money.
 * Inserts commas into the integer portion while preserving trailing decimal points and zeroes.
 * Example:
 * "10000000" -> "10,000,000"
 * "10000000." -> "10,000,000."
 * "10000000.5" -> "10,000,000.5"
 */
export function formatAmountInput(raw, maxDecimals = 2) {
  if (raw === null || raw === undefined) return ''
  const str = String(raw).trim()
  if (!str) return ''

  const isNegative = str.startsWith('-')
  const clean = str.replace(/[^\d.]/g, '')
  if (!clean) return isNegative ? '-' : ''

  const parts = clean.split('.')
  const rawInteger = parts[0] || '0'
  const decimalPart = parts.length > 1 ? parts.slice(1).join('').slice(0, maxDecimals) : null

  // Strip leading zeroes unless the whole integer part is '0'
  const integerPart = rawInteger.replace(/^0+(?=\d)/, '')
  const formattedInteger = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')

  let result = (isNegative ? '-' : '') + formattedInteger
  if (decimalPart !== null) {
    result += `.${decimalPart}`
  } else if (clean.endsWith('.')) {
    result += '.'
  }

  return result
}

export function formatTableCell(value, key = '', fallback = DISPLAY_FALLBACK) {
  if (value === null || value === undefined || value === '') return fallback
  if (typeof value === 'boolean') return formatBoolean(value)

  const normalizedKey = String(key || '').toLowerCase()

  // If column key indicates an amount/budget/cost/price, format with commas
  if (AMOUNT_KEY_PATTERN.test(normalizedKey) && !PRESERVE_NUMERIC_PATTERN.test(normalizedKey)) {
    return formatAmount(value, { fallback })
  }

  if (typeof value === 'number') {
    // Preserve year or id or count as plain numbers
    if (PRESERVE_NUMERIC_PATTERN.test(normalizedKey) || (Number.isInteger(value) && value >= 1900 && value <= 2100 && normalizedKey.includes('year'))) {
      return value
    }
    return value.toLocaleString('en-PH')
  }

  if (Array.isArray(value)) {
    return value.length ? value.map((item) => formatTableCell(item, '', '')).filter(Boolean).join(', ') : fallback
  }
  if (typeof value === 'object') return JSON.stringify(value)

  const text = normalize(value, fallback)
  if (MACHINE_KEY_PATTERN.test(normalizedKey) && !PRESERVE_KEY_PATTERN.test(normalizedKey)) {
    return formatMachineLabel(text, fallback)
  }
  if (MACHINE_VALUE_PATTERN.test(text)) {
    return formatMachineLabel(text, fallback)
  }

  // If text is a pure numeric string and key is an amount
  if (/^-?\d+(\.\d+)?$/.test(text) && AMOUNT_KEY_PATTERN.test(normalizedKey)) {
    return formatAmount(text, { fallback })
  }

  return text
}

export function parseDate(value) {
  if (value === null || value === undefined || value === '') return null
  if (value instanceof Date) return isNaN(value.getTime()) ? null : value

  if (typeof value === 'number') {
    const d = new Date(value)
    return isNaN(d.getTime()) ? null : d
  }

  let str = String(value).trim()
  if (!str) return null

  // If string contains date-time format (with 'T' or space separating date and time)
  // and does not have a timezone indicator (no 'Z' and no +/- offset), treat as UTC
  if (str.includes('T')) {
    if (!str.endsWith('Z') && !/[+-]\d{2}(:?\d{2})?$/.test(str)) {
      str += 'Z'
    }
  } else if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(str)) {
    str = str.replace(' ', 'T') + 'Z'
  }

  const date = new Date(str)
  return isNaN(date.getTime()) ? null : date
}

export function formatDateTime(value, fallback = DISPLAY_FALLBACK) {
  const date = parseDate(value)
  if (!date) return fallback
  return date.toLocaleString('en-PH', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Manila',
  })
}

export function formatDate(value, fallback = DISPLAY_FALLBACK) {
  const date = parseDate(value)
  if (!date) return fallback
  return date.toLocaleDateString('en-PH', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'Asia/Manila',
  })
}

export function formatTimestamp(value, fallback = DISPLAY_FALLBACK) {
  const date = parseDate(value)
  if (!date) return fallback
  return date.toLocaleString('en-PH', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Manila',
  })
}

export function formatRelativeTime(value, fallback = '') {
  const date = parseDate(value)
  if (!date) return fallback
  const ts = date.getTime()
  const diff = Date.now() - ts
  if (diff < 0 && diff > -30000) return 'just now'
  if (diff < 0) return 'in the future'
  const sec = Math.max(0, Math.round(diff / 1000))
  if (sec < 60) return `${sec}s ago`
  const min = Math.round(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.round(hr / 24)
  if (day < 30) return `${day}d ago`
  const mo = Math.round(day / 30)
  if (mo < 12) return `${mo}mo ago`
  return `${Math.round(mo / 12)}y ago`
}
