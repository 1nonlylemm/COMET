import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileCheck2,
  FileText,
  HelpCircle,
  MinusCircle,
  Plus,
  ShieldCheck,
  Sparkles,
  XCircle,
  Eye,
} from 'lucide-react'
import { Button } from '../../../../components'
import { FileSummary } from '../../lib/intakeComponents.jsx'
import { formatDate } from '../../lib/intakeFormatters.js'
import { selectAdvisoryObservations, selectReviewFindings } from '../../lib/reviewFindings.js'

/**
 * DocumentEvidencePanel — Requirement-Driven Documentary Evidence Checker
 *
 * Replaces the score dial, percentage score, and arbitrary bands with a clear,
 * explainable, evidence-based checklist (signatories, certifications, dates, notarization).
 *
 * Assistive only: Staff and Provincial Admin make the compliance decision.
 */
export function DocumentEvidencePanel({
  latestSubmission,
  complianceResult,
  hasEvidence,
  canRun,
  isCheckerRunning,
  isPriorRunning,
  hasPriorYearAvailable,
  onRunChecker,
  onRunPriorYear,
  onToggleSelectFinding,
  selectedFindingKeys = new Set(),
  isFindingDismissed = () => false,
}) {
  const hasSubmission = Boolean(latestSubmission)
  const scoreDetails = complianceResult?.score_details
  const evidenceChecks = complianceResult?.evidence_checks
    || scoreDetails?.evidence_checks
    || []
  const evidenceSummary = complianceResult?.evidence_summary
    || scoreDetails?.evidence_summary
    || null
  const technicalChecks = complianceResult?.technical_checks
    || scoreDetails?.technical_checks
    || []
  const technicalSummary = complianceResult?.technical_summary
    || scoreDetails?.technical_summary
    || null
  const documentState = complianceResult?.document_state
    || scoreDetails?.document_state
    || null
  const isBlankDocument = documentState === 'blank_or_empty' || Boolean(technicalSummary?.is_blank)
  const isVisualOnlyDocument = documentState === 'visual_content_only' || Boolean(technicalSummary?.is_visual_only)
  // Collect advisory language observations (spelling/grammar)
  const languageObservations = useMemo(() => {
    return selectAdvisoryObservations(complianceResult?.findings)
  }, [complianceResult?.findings])


  const [showAllLanguage, setShowAllLanguage] = useState(false)
  const findingsList = complianceResult?.findings || []
  const counts = selectReviewFindings(complianceResult)
  const criticalCount = counts.critical_count
  const attentionCount = counts.attention_count
  const analysisCoverage = complianceResult?.analysis_coverage || scoreDetails?.analysis_coverage || null

  if (!hasEvidence && !hasSubmission) {
    return (
      <section
        data-testid="review-snapshot"
        className="rounded-xl border border-brand-border bg-brand-surface p-5"
      >
        <div className="flex items-start gap-3">
          <ShieldCheck className="h-5 w-5 shrink-0 text-brand-text-muted" strokeWidth={1.7} />
          <div>
            <div className="text-sm font-semibold text-brand-text">No documentary evidence on file</div>
            <p className="mt-1 text-xs text-brand-text-muted">
              Upload or record an attachment to begin evidence verification for this requirement.
            </p>
          </div>
        </div>
      </section>
    )
  }

  const file = latestSubmission?.document_files?.[latestSubmission.document_files.length - 1]
  const fileName = file?.file_name || latestSubmission?.primary_file_name || 'Latest evidence'
  const fileDate = file?.created_at || latestSubmission?.created_at

  const hasResult = Boolean(
    (scoreDetails && Object.keys(scoreDetails).length) ||
    evidenceChecks.length ||
    evidenceSummary ||
    (complianceResult?.findings && complianceResult.findings.length)
  )

  if (!hasResult) {
    return (
      <section
        data-testid="review-snapshot"
        className="rounded-xl border border-brand-border bg-brand-surface p-5"
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0 space-y-1">
            <div className="flex items-center gap-2">
              <FileCheck2 className="h-4 w-4 text-brand-text-muted" strokeWidth={1.7} />
              <span className="text-sm font-semibold text-brand-text">No checker result yet</span>
            </div>
            <p className="text-xs text-brand-text-muted">
              The documentary evidence checker has not evaluated this submission yet. Run it to verify signatories, certifications, dates, and notarization.
            </p>
            {fileName && (
              <div className="pt-2">
                <FileSummary fileName={fileName} date={fileDate} compact />
              </div>
            )}
          </div>
          {canRun && (
            <Button
              size="sm"
              icon={ShieldCheck}
              loading={Boolean(isCheckerRunning)}
              onClick={onRunChecker}
            >
              Run Checker
            </Button>
          )}
        </div>
      </section>
    )
  }

  const requiredChecks = evidenceChecks.filter((c) => c.state !== 'not_required')
  const notRequiredChecks = evidenceChecks.filter((c) => c.state === 'not_required')
  const manualCount = counts.manual_check_count

  const isCheckCited = (check) => {
    const keyColon = `missing_evidence:${check.key}`
    const keyUnderscore = `missing_evidence_${check.key}`
    if (selectedFindingKeys instanceof Set) {
      return selectedFindingKeys.has(keyColon) || selectedFindingKeys.has(keyUnderscore) || selectedFindingKeys.has(check.key)
    }
    if (Array.isArray(selectedFindingKeys)) {
      return selectedFindingKeys.includes(keyColon) || selectedFindingKeys.includes(keyUnderscore) || selectedFindingKeys.includes(check.key)
    }
    return false
  }

  const handleCiteToggle = (check) => {
    const findingKey = `missing_evidence:${check.key}`
    onToggleSelectFinding?.(findingKey)
  }

  const summaryRequired = counts.configured_check_count
  const summaryDetected = counts.detected_check_count
  const allDetected = summaryRequired > 0 && summaryDetected >= summaryRequired

  return (
    <section
      data-testid="review-snapshot"
      className="rounded-xl border border-brand-border bg-brand-surface p-5 space-y-5"
    >
      {/* Header with Title, Assistive Notice, and Actions */}
      <div className="flex flex-col gap-4 border-b border-brand-border/60 pb-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-brand-primary" strokeWidth={1.8} />
            <h3 className="text-sm font-semibold text-brand-text">Document Review Scope</h3>
            {summaryRequired > 0 ? (
              <span
                data-testid="evidence-summary-badge"
                className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                  allDetected && manualCount === 0
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800/40 dark:bg-emerald-950/20 dark:text-emerald-300'
                    : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800/40 dark:bg-amber-950/20 dark:text-amber-300'
                }`}
              >
                {manualCount > 0
                  ? `Text evidence: ${summaryDetected} of ${summaryRequired} detected · Manual verification required`
                  : allDetected
                  ? `All ${summaryRequired} Required Evidence Detected`
                  : `Evidence Status: ${summaryDetected} of ${summaryRequired} Detected`}
              </span>
            ) : (
              <span
                data-testid="evidence-summary-badge"
                className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-medium text-slate-600 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-400"
              >
                No requirement-specific evidence checks configured
              </span>
            )}
            {findingsList.length > 0 && (
              <span
                data-testid="findings-summary-badge"
                className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                  criticalCount > 0
                    ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-800/40 dark:bg-red-950/20 dark:text-red-300'
                    : attentionCount > 0
                      ? 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800/40 dark:bg-amber-950/20 dark:text-amber-300'
                      : 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-300'
                }`}
              >
                {criticalCount > 0
                  ? `${criticalCount} Critical Inspection${criticalCount === 1 ? '' : 's'}`
                  : attentionCount > 0
                    ? `${attentionCount} Review Attention`
                    : `${counts.unverified_count} Unverified · ${counts.advisory_count} Advisory`}
              </span>
            )}
            {analysisCoverage && (
              <span
                data-testid="analysis-coverage-badge"
                className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                  analysisCoverage.is_partial
                    ? 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800/50 dark:bg-amber-950/40 dark:text-amber-300'
                    : 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-900/50 dark:text-slate-300'
                }`}
              >
                Coverage: {analysisCoverage.label || `${analysisCoverage.pages_analyzed} pages`}
              </span>
            )}
          </div>
          <p className="text-xs text-brand-text-muted">
            Assistive check only — Staff and Provincial Admin evaluate and determine documentary compliance.
          </p>
        </div>

        {canRun && (
          <div
            data-testid="score-quick-actions"
            className="flex flex-wrap items-center gap-2"
          >
            <Button
              size="sm"
              variant="outline"
              icon={ShieldCheck}
              loading={Boolean(isCheckerRunning)}
              onClick={onRunChecker}
            >
              Re-run Check
            </Button>
            {hasPriorYearAvailable && (
              <Button
                size="sm"
                variant="outline"
                icon={Sparkles}
                loading={Boolean(isPriorRunning)}
                onClick={onRunPriorYear}
              >
                Use Prior FY
              </Button>
            )}
          </div>
        )}
      </div>

      {/* ── GROUP 1: TECHNICAL / DOCUMENT EXTRACTION STATUS ── */}
      <div className="rounded-lg border border-brand-border/60 bg-brand-surface-solid p-4 space-y-3" data-testid="technical-extraction-group">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-brand-border/40 pb-2.5">
          <div className="flex items-center gap-2.5 min-w-0">
            <FileText className="h-4 w-4 shrink-0 text-brand-primary" />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-brand-text">
                <span className="font-semibold">Evaluated Document:</span>
                {fileName && <FileSummary fileName={fileName} date={null} compact />}
                {fileDate && <span className="text-brand-text-muted">· evaluated {formatDate(fileDate)}</span>}
              </div>
              <p className="text-[11px] text-brand-text-muted mt-0.5">
                Technical document integrity and usability checks evaluated prior to documentary evidence matching.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 self-start sm:self-center">
            <span className="inline-flex items-center rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-slate-600 dark:border-slate-800 dark:bg-slate-900/50 dark:text-slate-400">
              Extraction Active
            </span>
            {documentState && (
              <span className={`inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${
                isBlankDocument
                  ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300'
                  : isVisualOnlyDocument
                    ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300'
                    : summaryRequired > 0
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
                      : 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-300'
              }`} data-testid="technical-status-badge">
                {isBlankDocument ? 'Blank / Empty' : isVisualOnlyDocument ? 'Visual Only' : 'Readable Content'}
              </span>
            )}
          </div>
        </div>

        {analysisCoverage?.notice && (
          <div
            data-testid="partial-coverage-notice"
            className="rounded-md border border-amber-200 bg-amber-50/70 p-2.5 text-xs text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-300"
          >
            <div className="font-semibold">Partial Analysis Coverage</div>
            <p className="mt-0.5">{analysisCoverage.notice}</p>
          </div>
        )}

        {/* 3 Structured Technical Checks (Content Presence, Readability, Text Extraction) */}
        {technicalChecks.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-1" data-testid="technical-checks-grid">
            {technicalChecks.map((tCheck) => {
              const isPass = tCheck.status === 'passed' || tCheck.state === 'detected' || tCheck.state === 'sufficient' || tCheck.state === 'successful'
              const isBlocker = tCheck.status === 'blocker' || tCheck.state === 'failed'
              const isReview = tCheck.status === 'needs_review' || tCheck.state === 'needs_review' || tCheck.state === 'limited'

              return (
                <div
                  key={tCheck.key}
                  data-testid={`technical-check-${tCheck.key}`}
                  className={`rounded-md border p-2.5 flex flex-col justify-between text-xs ${
                    isBlocker
                      ? 'border-red-200 bg-red-50/50 text-red-900 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300'
                      : isReview
                        ? 'border-amber-200 bg-amber-50/50 text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-300'
                        : 'border-slate-200 bg-white/70 text-slate-900 dark:border-slate-800 dark:bg-slate-900/30 dark:text-slate-200'
                  }`}
                >
                  <div className="flex items-center gap-1.5 font-semibold">
                    {isPass && <CheckCircle2 className={`h-3.5 w-3.5 shrink-0 ${summaryRequired > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-500'}`} />}
                    {isReview && <AlertTriangle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400 shrink-0" />}
                    {isBlocker && <XCircle className="h-3.5 w-3.5 text-red-600 dark:text-red-400 shrink-0" />}
                    <span>{tCheck.label}</span>
                  </div>
                  <div className="mt-1 text-[11px] font-medium leading-tight">
                    {tCheck.message}
                  </div>
                  {tCheck.detail && (
                    <div className="mt-1 text-[10px] text-brand-text-muted truncate" title={tCheck.detail}>
                      {tCheck.detail}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ) : (
          <div className="text-[11px] text-brand-text-muted">
            No technical-check details were recorded. {summaryRequired > 0 ? 'See the configured requirement evidence checks below.' : 'Requirement evidence checks were not configured; manual verification is required.'}
          </div>
        )}
      </div>

      {/* ── GROUP 2: REQUIRED EVIDENCE CHECKLIST ── */}
      <div className="space-y-3" data-testid="evidence-checklist">
        <div className="flex items-center justify-between">
          <div className="text-xs font-semibold uppercase tracking-wider text-brand-text-muted">
            Required Evidence Checks
          </div>
          {requiredChecks.length > 0 && !isBlankDocument && (
            <span className="text-xs text-brand-text-muted">
              {summaryDetected} of {summaryRequired} detected
            </span>
          )}
        </div>

        {isBlankDocument ? (
          <div
            data-testid="blank-document-suppression-notice"
            className="rounded-lg border border-red-200 bg-red-50/70 p-3.5 text-xs text-red-900 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300"
          >
            <div className="flex items-center gap-2 font-semibold">
              <AlertTriangle className="h-4 w-4 text-red-600 dark:text-red-400 shrink-0" />
              <span>Downstream Evidence Checks Suppressed</span>
            </div>
            <p className="mt-1 text-red-800 dark:text-red-300">
              The submitted document appears to contain no meaningful content. Secondary evidence checks (signatories, dates, certifications) have been suppressed to prevent misleading deficiency citations.
            </p>
          </div>
        ) : requiredChecks.length === 0 ? (
          <p className="text-xs text-brand-text-muted italic" data-testid="no-checks-configured-msg">
            No requirement-specific evidence checks configured for this documentary requirement.
          </p>
        ) : (
          <ul className="divide-y divide-brand-border/40 rounded-lg border border-brand-border/60 bg-brand-surface-solid">
            {requiredChecks.map((check) => {
              const cited = isCheckCited(check)
              const isDetected = check.state === 'detected'
              const isMissing = check.state === 'not_detected'
              const isReview = check.state === 'needs_review'

              return (
                <li
                  key={check.key}
                  data-testid={`evidence-check-${check.key}`}
                  className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      {isDetected && (
                        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                      )}
                      {isMissing && (
                        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                      )}
                      {isReview && (
                        <HelpCircle className="h-4 w-4 shrink-0 text-blue-600 dark:text-blue-400" />
                      )}
                      <span className="text-xs font-semibold text-brand-text">
                        {check.label}
                      </span>
                      <span
                        className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider ${
                          isDetected
                            ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
                            : isMissing
                              ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300'
                              : 'bg-blue-100 text-blue-800 dark:bg-blue-950/40 dark:text-blue-300'
                        }`}
                      >
                        {isDetected ? (check.human_verification_required ? 'Text detected' : 'Detected') : isMissing ? 'Not Detected' : 'Needs Review'}
                      </span>
                    </div>

                    {/* Detected Snippet or Explanation */}
                    {isDetected && check.snippet && (
                      <p className="text-xs text-brand-text-muted">
                        <span className="font-medium text-brand-text">Snippet:</span>{' '}
                        <span className="font-mono text-[11px] text-emerald-800 dark:text-emerald-300">
                          &ldquo;{check.snippet}&rdquo;
                        </span>
                      </p>
                    )}
                    {isMissing && check.explanation && (
                      <p className="text-xs text-amber-800 dark:text-amber-300">
                        {check.explanation}
                      </p>
                    )}
                    {isDetected && check.human_verification_required && <p className="text-xs text-brand-text-muted">Detected text does not confirm a completed signature, certification mark, or notarial act. Inspect the original document.</p>}
                    {isReview && check.explanation && (
                      <p className="text-xs text-blue-800 dark:text-blue-300">
                        {check.explanation}
                      </p>
                    )}
                  </div>

                  {/* Deficiency Citation Shortcut for missing checks */}
                  {isMissing && (
                    <div className="shrink-0 pt-1 sm:pt-0">
                      <Button
                        size="xs"
                        variant={cited ? 'secondary' : 'outline'}
                        icon={cited ? Check : Plus}
                        onClick={() => handleCiteToggle(check)}
                        disabled={!onToggleSelectFinding || isFindingDismissed(`missing_evidence_${check.key}`)}
                        data-testid={`cite-evidence-${check.key}`}
                      >
                        {isFindingDismissed(`missing_evidence_${check.key}`) ? 'Marked incorrect flag' : cited ? 'Cited as Deficiency' : 'Cite as Deficiency'}
                      </Button>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}

        {/* Optional / Not Required Checks */}
        {notRequiredChecks.length > 0 && (
          <div className="pt-2">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-brand-text-muted">
              Not Required
            </div>
            <ul className="mt-1 space-y-1">
              {notRequiredChecks.map((check) => (
                <li
                  key={check.key}
                  data-testid={`evidence-check-${check.key}`}
                  className="flex items-center gap-2 text-xs text-brand-text-muted"
                >
                  <MinusCircle className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                  <span className="font-medium">{check.label}</span>
                  <span>— Not required</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* ── GROUP 3: ADVISORY LANGUAGE & SPELLING ── */}
      <div className="border-t border-brand-border/60 pt-3" data-testid="advisory-language-checks">
        <div className="flex items-center justify-between">
          <div className="text-xs font-semibold uppercase tracking-wider text-brand-text-muted">
            Advisory Language & Spelling
          </div>
          {languageObservations.length > 0 && (
            <span className="text-[11px] text-brand-text-muted">
              {languageObservations.length} observation{languageObservations.length === 1 ? '' : 's'}
            </span>
          )}
        </div>

        {isBlankDocument || isVisualOnlyDocument ? (
          <p className="mt-1.5 text-xs text-brand-text-muted" data-testid="language-skipped-notice">
            Advisory language check not evaluated — insufficient readable text in {isBlankDocument ? 'blank' : 'visual-only'} document.
          </p>
        ) : languageObservations.length > 0 ? (
          <div className="mt-2 rounded-lg border border-blue-200 bg-blue-50/50 p-3 text-xs dark:border-blue-900/40 dark:bg-blue-950/20">
            <div className="flex items-center gap-2 font-medium text-blue-900 dark:text-blue-200">
              <HelpCircle className="h-4 w-4 shrink-0 text-blue-600 dark:text-blue-400" />
              <span>
                LanguageTool noted {languageObservations.length} advisory language/spelling observation(s).
              </span>
            </div>
            <p className="mt-1 text-blue-800/80 dark:text-blue-300/80">
              Advisory only — these suggestions do not impact compliance status. Reviewers may reference them when providing feedback.
            </p>
            <ul className="mt-2 space-y-1 pl-6 list-disc text-blue-900 dark:text-blue-200">
              {(showAllLanguage ? languageObservations : languageObservations.slice(0, 3)).map((f, i) => (
                <li key={i}>{f.message || f.finding_observation}</li>
              ))}
            </ul>
            {languageObservations.length > 3 && (
              <button
                type="button"
                onClick={() => setShowAllLanguage(!showAllLanguage)}
                className="mt-2 flex items-center gap-1 text-[11px] font-semibold text-blue-700 hover:text-blue-900 dark:text-blue-300 dark:hover:text-blue-100"
              >
                {showAllLanguage ? (
                  <>
                    <ChevronUp className="h-3 w-3" /> Show fewer
                  </>
                ) : (
                  <>
                    <ChevronDown className="h-3 w-3" /> Show {languageObservations.length - 3} more suggestion(s)
                  </>
                )}
              </button>
            )}
          </div>
        ) : (
          <p className="mt-1.5 text-xs text-brand-text-muted">
            No advisory language findings recorded. This does not establish whether a language check ran.
          </p>
        )}
      </div>
    </section>
  )
}

export default DocumentEvidencePanel
