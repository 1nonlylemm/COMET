/**
 * ComplianceScoreDial
 * --------------------
 * Pure SVG circular ring with the integer compliance score in the centre.
 * Stroke colour is driven by the score band; no charting library is used.
 *
 * Props:
 *   score          number | null         the overall_score value (0..100)
 *   band           string | null         score_details.score_band
 *   confidence     string | null         score_details.confidence_label
 *   size           number                 outer diameter in px (default 96)
 *   strokeWidth    number                 ring stroke width in px (default 8)
 *   isPulsing      boolean                add motion-safe pulse animation
 */

const STROKE_BY_BAND = {
  ready_for_approval: 'stroke-emerald-500',
  review_required: 'stroke-amber-500',
  likely_return: 'stroke-orange-500',
  invalid_evidence: 'stroke-red-500',
  check_failed: 'stroke-slate-400',
}

const BAND_LABEL = {
  ready_for_approval: 'ready for approval',
  review_required: 'review required',
  likely_return: 'likely return',
  invalid_evidence: 'invalid evidence',
  check_failed: 'check failed',
}

function dialAriaLabel({ score, band, confidence }) {
  if (score === null) return 'Compliance score not available.'
  const bandLabel = BAND_LABEL[band] || 'no band'
  const confidenceLabel = confidence ? `${String(confidence).toLowerCase()} confidence` : 'unknown confidence'
  return `Compliance score ${Math.round(score)} of 100, ${bandLabel}, ${confidenceLabel}.`
}

export function ComplianceScoreDial({
  score,
  band = null,
  confidence = null,
  size = 96,
  strokeWidth = 8,
  isPulsing = false,
}) {
  const numericInput = score
  const isMissing = numericInput === null || numericInput === undefined || numericInput === ''
  const numeric = !isMissing && Number.isFinite(Number(numericInput))
    ? Math.max(0, Math.min(100, Number(numericInput)))
    : null
  const radius = Math.max(1, (size - strokeWidth) / 2)
  const circumference = 2 * Math.PI * radius
  const offset = numeric === null ? circumference : circumference * (1 - numeric / 100)
  const stroke = STROKE_BY_BAND[band] || STROKE_BY_BAND.check_failed

  return (
    <div
      role="img"
      aria-label={dialAriaLabel({ score: numeric, band, confidence })}
      data-testid="compliance-score-dial"
      className="relative inline-flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          className="stroke-slate-200 dark:stroke-slate-700"
          strokeWidth={strokeWidth}
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          className={`transition-all duration-500 ease-out ${stroke} ${isPulsing ? 'motion-safe:animate-pulse' : ''}`}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          strokeWidth={strokeWidth}
          fill="none"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold leading-none text-brand-text tabular-nums">
          {numeric === null ? '–' : Math.round(numeric)}
        </span>
        <span className="mt-0.5 text-[10px] font-medium uppercase tracking-wider text-brand-text-muted">
          /100
        </span>
      </div>
    </div>
  )
}

export default ComplianceScoreDial
