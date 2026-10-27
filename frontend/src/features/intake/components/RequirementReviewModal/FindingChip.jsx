import { AlertCircle, AlertTriangle, HelpCircle, Info, Sparkles } from 'lucide-react'
import { DEFICIENCY_CATEGORY_LABELS } from '../../../monitoring/components/workflowStatus'
import { isLanguageAdvisory, reviewFindingGroup } from '../../lib/reviewFindings'
import { FindingDecision } from './FindingDecision'

const REVIEW_CATEGORY_LABELS = {
  file_document_quality: 'File & Document Quality',
  layout_structural_integrity: 'Layout & Structural Integrity',
  required_information_keyword_occurrence: 'Required Information & Keyword Occurrence',
  signatory_official_mark_evidence: 'Signatory & Official-Mark Evidence',
  date_temporal_consistency: 'Date & Temporal Consistency',
  internal_cross_document_consistency: 'Internal & Cross-Document Consistency',
  calculation_arithmetic_consistency: 'Calculation & Arithmetic Consistency',
}

/**

 * Split a detail string into discrete sentences so long, fact-dense
 * messages (e.g. the photo evidence summary) can render as a scannable
 * bullet list instead of a wall of prose.
 *
 * The split rule uses a lookbehind on terminal punctuation followed by
 * whitespace and an uppercase letter, which keeps decimals like
 * "121.34334" and abbreviations without trailing periods intact.
 */
function splitIntoSentences(text) {
  if (typeof text !== 'string') return []
  const trimmed = text.trim()
  if (!trimmed) return []
  return trimmed
    .split(/(?<=[.!?])\s+(?=[A-Z])/g)
    .map((part) => part.trim())
    .filter(Boolean)
}

const SEVERITY_META = {
  advisory: {
    Icon: Info,
    badge: 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-400/40 dark:bg-blue-400/10 dark:text-blue-200',
    label: 'Advisory',
  },
  blocker: {
    Icon: AlertTriangle,
    badge: 'border-red-300 bg-red-50 text-red-700 dark:border-red-400/40 dark:bg-red-400/10 dark:text-red-200',
    label: 'Critical Inspection',
  },
  needs_verification: {
    Icon: HelpCircle,
    badge: 'border-purple-300 bg-purple-50 text-purple-700 dark:border-purple-400/40 dark:bg-purple-400/10 dark:text-purple-200',
    label: 'Unverified',
  },
  manual_verification_required: {
    Icon: HelpCircle,
    badge: 'border-fuchsia-300 bg-fuchsia-50 text-fuchsia-700 dark:border-fuchsia-400/40 dark:bg-fuchsia-400/10 dark:text-fuchsia-200',
    label: 'Needs Manual Review',
  },
  warning: {
    Icon: AlertCircle,
    badge: 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-300/40 dark:bg-amber-300/10 dark:text-amber-100',
    label: 'Review Attention',
  },
  info: {
    Icon: Info,
    badge: 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-400/40 dark:bg-blue-400/10 dark:text-blue-200',
    label: 'Informational Note',
  },
}

const DEFAULT_META = {
  Icon: Info,
  badge: 'border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-500/50 dark:bg-slate-500/15 dark:text-slate-200',
  label: 'Note',
}

const SEVERITY_BORDER = {
  blocker: 'border-l-red-500', warning: 'border-l-amber-500',
  needs_verification: 'border-l-purple-500', advisory: 'border-l-blue-500', info: 'border-l-slate-400',
}

// Compare aliases without punctuation/case/whitespace differences. Keep distinct
// instructions; do not guess semantic equivalence or discard new evidence.
function presentationFields(finding) {
  const seen = new Set()
  const once = value => {
    const text = String(value || '').trim()
    const key = text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim()
    if (!key || seen.has(key)) return ''
    seen.add(key)
    return text
  }
  const observation = once(finding.message || finding.observation || finding.finding_observation)
  const action = once(finding.reviewer_action || finding.corrective_instruction || finding.detail || finding.review_instruction)
  const detail = once(finding.detail)
  const instruction = once(finding.review_instruction)
  const explanation = once(finding.ai_explanation)
  return { observation, action, detail, instruction, explanation }
}

export function FindingChip({
  finding,
  findingNumber,
  selectable = false,
  selected = false,
  onToggleSelect = null,
  compact = false,
  disabled = false,
  onViewFinding,
  review,
  onSaveReview,
  savingReview,
}) {
  if (!finding) return null
  const group = reviewFindingGroup(finding)
  const meta = SEVERITY_META[group] || DEFAULT_META
  const Icon = meta.Icon
  const page = finding.page ?? finding.locations?.[0]?.page
  const fields = presentationFields(finding)
  const detailSentences = splitIntoSentences(fields.detail)
  const showAsList = detailSentences.length >= 3

  if (compact) {
    const isAdvisory = isLanguageAdvisory(finding)
    const reviewAction = fields.action
    const needsVerification = reviewFindingGroup(finding) === 'needs_verification'
    return (
      <article data-testid="finding-chip" data-severity={finding.severity || 'info'} className={`min-w-0 space-y-2 border-b border-l-2 border-brand-border pl-3 py-4 text-sm ${SEVERITY_BORDER[group]} ${selected ? 'bg-brand-primary/5' : ''}`}>
        <div className="flex items-start gap-2">
          <span className={`mt-0.5 rounded-full border p-0.5 ${meta.badge}`}><Icon className="h-4 w-4 shrink-0" /></span>
          <div className="min-w-0 flex-1 break-words">
            <h4 className="font-medium text-brand-text">{findingNumber && <span className="mr-2" data-testid="finding-number">{findingNumber}.</span>}{fields.observation}</h4>
            <p className="mt-1 text-xs text-brand-text-muted">{isAdvisory ? 'Language advisory' : needsVerification ? 'Needs verification' : meta.label}{page ? ` · Page ${page}` : ' · Location not available'}</p>
          </div>
        </div>
        {isAdvisory && <p className="text-xs text-brand-text-muted">Verify against the source record. Automated language suggestions may flag correctly spelled names.</p>}
        {finding.requirement_basis?.expected && <p className="text-xs text-brand-text-muted"><span className="font-medium text-brand-text">Requirement: </span>{finding.requirement_basis.expected}{finding.requirement_basis.annex_reference ? ` · ${finding.requirement_basis.annex_reference}` : ''}</p>}
        {finding.evidence_text && <p className="break-words text-xs text-brand-text-muted"><span className="font-medium text-brand-text">Document text: </span>{String(finding.evidence_text).slice(0, 240)}{String(finding.evidence_text).length > 240 ? '…' : ''}</p>}
        {reviewAction && <p className="text-sm text-brand-text-muted"><span className="font-medium text-brand-text">Reviewer action: </span>{reviewAction}</p>}
        {finding.id === 'language_quality_review' && finding.locations?.length > 0 && <ol className="space-y-1 text-xs">{finding.locations.map((location, index) => <li key={index}><button type="button" className="py-1 text-brand-primary hover:underline" disabled={!location.page} onClick={() => onViewFinding?.({ ...finding, page: location.page, annotationId: `${finding.id}:${index}` })}>{findingNumber}.{index + 1} · {location.matched_text || 'Language observation'}{location.page ? ` · Page ${location.page}` : ' · Location unavailable'}</button></li>)}</ol>}
        {finding.annotation_more_count > 0 && <p className="text-xs text-brand-text-muted">+{finding.annotation_more_count} more language issues; inspect the document manually.</p>}
        {(fields.detail || fields.explanation || fields.instruction || finding.category || finding.deficiency_category) && (
          <details className="text-xs text-brand-text-muted">
            <summary className="cursor-pointer py-1 font-medium text-brand-primary">Explanation &amp; details</summary>
            {fields.detail && <p className="mt-2 whitespace-pre-wrap break-words">{fields.detail}</p>}
            {fields.explanation && <div data-testid="finding-ai-explanation" className="mt-2"><p className="font-medium">Reviewer Explanation</p><p>{fields.explanation}</p></div>}
            {fields.instruction && <p className="mt-1">Inspection Action: {fields.instruction}</p>}
            {finding.category && <p className="mt-2">Category: {REVIEW_CATEGORY_LABELS[finding.category] || finding.category.replace(/_/g, ' ')}</p>}
            {finding.deficiency_category && <p className="mt-1">Return category: {DEFICIENCY_CATEGORY_LABELS[finding.deficiency_category] || finding.deficiency_category.replace(/_/g, ' ')}</p>}
          </details>
        )}
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
          {selectable && <label className="flex cursor-pointer items-center gap-2 py-2"><input type="checkbox" checked={selected} disabled={disabled || review?.status === 'incorrect_flag'} onChange={onToggleSelect} aria-label={`Select finding: ${finding.message}`} />Include in return notes</label>}
          {page && onViewFinding && <button type="button" onClick={() => onViewFinding(finding)} className="py-2 font-medium text-brand-primary hover:underline">View in document</button>}
        </div>
        {finding.supporting_evidence?.length > 0 && <details className="text-xs"><summary className="cursor-pointer py-1 font-medium text-brand-primary">Supporting attachment evidence</summary>{finding.supporting_evidence.map(item => <div className="py-2" key={item.document_file_id}><button type="button" onClick={() => onViewFinding?.({ ...finding, document_file_id: item.document_file_id, page: item.page })} className="font-medium text-brand-primary hover:underline">{item.file_name}{item.page ? ` · Page ${item.page}` : ''}</button><p className="mt-1 break-words text-brand-text-muted">{item.snippet}</p></div>)}</details>}
        <FindingDecision key={review?.reviewed_at || 'unreviewed'} finding={finding} review={review} onSave={onSaveReview} disabled={disabled} saving={savingReview} />
      </article>
    )
  }

  return (
    <div
      data-testid="finding-chip"
      data-severity={finding.severity || 'info'}
      className={`flex items-start gap-2.5 rounded-md border border-l-2 ${SEVERITY_BORDER[group]} bg-brand-surface px-3 py-2.5 text-xs transition-colors ${
        selected
          ? 'border-brand-primary/60 bg-brand-primary/5 dark:bg-brand-primary/10'
          : 'border-brand-border'
      }`}
    >
      {selectable && (
        <input
          type="checkbox"
          checked={selected}
          disabled={disabled}
          onChange={onToggleSelect}
          className="mt-1 h-3.5 w-3.5 rounded border-brand-border text-brand-primary focus:ring-brand-primary/30"
          aria-label={`Select finding: ${finding.message}`}
        />
      )}
      <span className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${meta.badge}`}>
        <Icon className="h-3 w-3" strokeWidth={1.8} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">
            {meta.label}
          </span>
          {finding.category && (
            <span className="text-[10px] uppercase tracking-wider text-brand-text-muted opacity-80">
              · {REVIEW_CATEGORY_LABELS[finding.category] || String(finding.category).replace(/_/g, ' ')}
            </span>
          )}
          {finding.deficiency_category && (
            <span className="inline-flex items-center rounded-md border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 dark:border-amber-800/50 dark:bg-amber-950/40 dark:text-amber-300">
              {DEFICIENCY_CATEGORY_LABELS[finding.deficiency_category] || finding.deficiency_category.replace(/_/g, ' ')}
            </span>
          )}
          {finding.automation_level && (
            finding.automation_level === 'human_verification' ? (
              <span className="inline-flex items-center rounded-md border border-purple-200 bg-purple-50 px-1.5 py-0.5 text-[10px] font-medium text-purple-700 dark:border-purple-800/50 dark:bg-purple-950/40 dark:text-purple-300">
                Needs Human Verification
              </span>
            ) : (
              <span className="inline-flex items-center rounded-md border border-sky-200 bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium text-sky-700 dark:border-sky-800/50 dark:bg-sky-950/40 dark:text-sky-300">
                Automated Check
              </span>
            )
          )}
          {page !== undefined && page !== null && (
            <span className="ml-auto inline-flex items-center rounded-full border border-brand-border bg-brand-surface-solid px-1.5 py-0.5 text-[10px] font-medium text-brand-text-muted">
              Page {page}
            </span>
          )}
        </div>
        <div className="mt-1 font-medium text-brand-text">{findingNumber && <span className="mr-2">{findingNumber}.</span>}{fields.observation}</div>
        {fields.action && <p className="mt-1 text-brand-text-muted"><span className="font-medium">Reviewer action: </span>{fields.action}</p>}
        {fields.detail && (
          showAsList ? (
            <ul
              data-testid="finding-detail-list"
              className="mt-1 list-disc space-y-0.5 pl-4 text-brand-text-muted marker:text-brand-text-muted/70"
            >
              {detailSentences.map((sentence, index) => (
                <li key={index} className="leading-snug">
                  {sentence}
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-0.5 text-brand-text-muted">{fields.detail}</div>
          )
        )}
        {fields.explanation && (
          <details
            data-testid="finding-ai-explanation"
            className="mt-2 rounded-md border border-indigo-200/70 bg-indigo-50/60 p-2 text-indigo-950 dark:border-indigo-800/40 dark:bg-indigo-950/30 dark:text-indigo-200"
          >
            <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-wider text-indigo-700 dark:text-indigo-300">
              <Sparkles className="h-3 w-3" strokeWidth={1.8} />
              Reviewer Explanation
            </summary>
            <div className="mt-0.5 text-xs leading-relaxed text-indigo-900 dark:text-indigo-100">
              {fields.explanation}
            </div>
          </details>
        )}
        {fields.instruction && <p className="mt-1 text-brand-text-muted">Inspection Action: {fields.instruction}</p>}
      </div>
    </div>
  )
}

export default FindingChip
