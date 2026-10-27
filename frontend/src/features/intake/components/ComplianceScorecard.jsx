import { Gauge, Info } from 'lucide-react'
import { badgeClassForTone } from '../../../lib/statusStyles'
import { selectReviewFindings } from '../lib/reviewFindings'

const DIMENSION_LABELS = {
  file_health: 'File Health',
  readability_ocr: 'Readability / OCR',
  evidence_type_mapping: 'Evidence Type & Mapping',
  required_content_fields: 'Required Content',
  format_template_layout: 'Format & Layout',
  project_lgu_context: 'Project / LGU Context',
  language_clarity: 'Language & Clarity',
}

const CONFIDENCE_TONES = {
  high: 'success',
  medium: 'info',
  low: 'warning',
  not_assessed: 'neutral',
}

function dimensionLabel(key) {
  return DIMENSION_LABELS[key] || formatLabel(key)
}

function formatLabel(value) {
  return String(value || '')
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(' ')
}

export function ComplianceScorecard({ result }) {
  const details = result?.score_details
  if (!details || typeof details !== 'object' || !Object.keys(details).length) {
    return null
  }

  const dimensions = Object.entries(details.weights || details.subscores || {})
  const topReasons = Array.isArray(details.top_reasons) ? details.top_reasons : []
  const counts = selectReviewFindings(result)
  const notAssessed = result?.requirement_checks_configured === false
    || details.requirement_checks_configured === false || details.confidence_label === 'not_assessed'
  const configured = !notAssessed && counts.configured_check_count > 0
  const confidenceLabel = notAssessed ? 'not_assessed' : !configured ? '' : Array.isArray(result.findings)
    ? (counts.critical_count ? 'low' : counts.attention_count ? 'medium' : 'high')
    : String(details.confidence_label || '').toLowerCase()
  const confidenceTone = CONFIDENCE_TONES[confidenceLabel] || 'neutral'
  const coverage = result?.analysis_coverage || details.analysis_coverage

  return (
    <section
      data-testid="compliance-scorecard"
      className="mt-3 rounded-lg border border-brand-border bg-brand-surface-solid p-3"
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Gauge className="h-4 w-4 text-brand-primary" strokeWidth={1.7} />
          <span className="text-sm font-medium text-brand-text">Analysis Breakdown</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className="inline-flex items-center rounded-full border border-brand-border bg-brand-surface px-2.5 py-0.5 text-xs font-semibold text-brand-text"
            data-testid="scorecard-overall"
          >
            {configured ? `${counts.detected_check_count} of ${counts.configured_check_count} evidence items detected` : 'No requirement-specific checks configured'}
          </span>
          {confidenceLabel && (
            <span className={badgeClassForTone(confidenceTone)} data-testid="scorecard-confidence">
              {confidenceLabel === 'not_assessed' ? 'Not assessed' : `${confidenceLabel} confidence`}
            </span>
          )}
        </div>
      </header>

      <p className="mt-2 text-xs text-brand-text-muted">Recorded scope: {(result.technical_checks || details.technical_checks || []).length} technical check(s) · {counts.advisory_count} advisory finding(s){coverage?.label ? ` · ${coverage.label}` : ''}. Manual compliance review required.</p>

      {coverage?.notice && (
        <div className="mt-3 rounded-md border border-amber-200 bg-amber-50/70 p-2.5 text-xs text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-300">
          {coverage.notice}
        </div>
      )}

      {dimensions.length > 0 && (
        <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2" data-testid="scorecard-dimensions">
          {dimensions.map(([key]) => (
            <li
              key={key}
              className="flex items-center justify-between gap-2 rounded-md border border-brand-border bg-brand-surface px-2.5 py-2 text-xs"
            >
              <span className="font-medium text-brand-text">{dimensionLabel(key)}</span>
              <span className="text-[11px] text-brand-text-muted">Evaluated</span>
            </li>
          ))}
        </ul>
      )}

      {topReasons.length > 0 && (
        <div className="mt-3" data-testid="scorecard-top-reasons">
          <div className="flex items-center gap-1.5 text-xs font-medium text-brand-text">
            <Info className="h-3.5 w-3.5 text-brand-text-muted" strokeWidth={1.7} />
            Analysis Observations
          </div>
          <ul className="mt-1.5 space-y-1 text-xs text-brand-text-muted">
            {topReasons.map((reason) => (
              <li key={reason} className="flex gap-1.5">
                <span aria-hidden="true">•</span>
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

export default ComplianceScorecard
