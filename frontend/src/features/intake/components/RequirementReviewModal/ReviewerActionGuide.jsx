import { AlertTriangle, CheckCircle2, ClipboardCheck, FileText, ListChecks, Search, ShieldCheck, Sparkles, XCircle } from 'lucide-react'
import { Button } from '../../../../components'
import { badgeClassForTone } from '../../../../lib/statusStyles'


function fileNameFor(submission) {
  const latestFile = submission?.document_files?.[submission.document_files.length - 1]
  return latestFile?.file_name || submission?.primary_file_name || 'Latest evidence'
}

function latestScanFor(submission) {
  return submission?.nlp_scan_results?.[0] || submission?.latest_nlp_scan || null
}

function scoreDetailsFor(result) {
  const details = result?.score_details
  return details && Object.keys(details).length ? details : null
}

function scanStep(submission) {
  const scan = latestScanFor(submission)
  if (!submission) {
    return {
      id: 'mapping',
      label: 'Scan mapping',
      title: 'No submission',
      detail: 'Upload evidence before reviewing document mapping.',
      tone: 'neutral',
      Icon: Search,
    }
  }
  if (!scan) {
    return {
      id: 'mapping',
      label: 'Scan mapping',
      title: 'Scan pending',
      detail: 'Run or review document intelligence before relying on mapping.',
      tone: 'warning',
      Icon: Search,
    }
  }
  if (scan.is_accepted === true) {
    return {
      id: 'mapping',
      label: 'Scan mapping',
      title: 'Mapping accepted',
      detail: scan.suggested_requirement_name || 'Reviewer accepted the suggested requirement.',
      tone: 'success',
      Icon: CheckCircle2,
    }
  }
  if (scan.is_accepted === false) {
    return {
      id: 'mapping',
      label: 'Scan mapping',
      title: 'Mapping rejected',
      detail: 'Reviewer rejected the suggested mapping; use manual judgment.',
      tone: 'neutral',
      Icon: XCircle,
    }
  }
  if (scan.mapping_mismatch) {
    return {
      id: 'mapping',
      label: 'Scan mapping',
      title: 'Mapping mismatch',
      detail: scan.suggested_requirement_name || 'Suggested requirement differs from the selected review item.',
      tone: 'warning',
      Icon: AlertTriangle,
    }
  }
  if (scan.suggested_project_requirement_id) {
    return {
      id: 'mapping',
      label: 'Scan mapping',
      title: 'Mapping needs decision',
      detail: scan.suggested_requirement_name || 'Review the suggested requirement before final action.',
      tone: 'warning',
      Icon: Search,
    }
  }
  return {
    id: 'mapping',
    label: 'Scan mapping',
    title: 'Manual mapping needed',
    detail: 'No confident requirement suggestion was found.',
    tone: 'warning',
    Icon: AlertTriangle,
  }
}

function checkerStep(result) {
  const scoreDetails = scoreDetailsFor(result)
  const evidenceSummary = result?.evidence_summary || scoreDetails?.evidence_summary
  const findings = result?.findings || []

  if (!scoreDetails && !evidenceSummary && !findings.length) {
    return {
      id: 'checker',
      label: 'Findings check',
      title: 'Checker not run',
      detail: 'Run the assistant to inspect documentary findings and evidence.',
      tone: 'warning',
      Icon: ShieldCheck,
    }
  }
  if (evidenceSummary && typeof evidenceSummary === 'object' && Number.isFinite(Number(evidenceSummary.required_count))) {
    const allDetected = evidenceSummary.all_required_detected
    const missing = evidenceSummary.missing_count || 0
    return {
      id: 'checker',
      label: 'Evidence checks',
      title: allDetected ? 'All evidence detected' : `${missing} missing item(s)`,
      detail: `${evidenceSummary.detected_count} of ${evidenceSummary.required_count} required items detected`,
      tone: allDetected ? 'success' : 'warning',
      Icon: ShieldCheck,
    }
  }

  const critical = findings.filter((f) => f.severity === 'blocker').length
  const attention = findings.filter((f) => f.severity === 'warning').length
  const info = findings.filter((f) => f.severity === 'info').length
  const coverage = result?.analysis_coverage?.label

  let title = 'Review required'
  if (critical > 0) {
    title = `${critical} Critical inspection(s)`
  } else if (attention > 0) {
    title = `${attention} Review attention`
  } else if (findings.length === 0) {
    title = 'No issues flagged'
  }

  const detailParts = []
  if (critical > 0 || attention > 0 || info > 0) {
    detailParts.push(`${critical} critical, ${attention} attention, ${info} notes`)
  } else {
    detailParts.push('All checks passed')
  }
  if (coverage) {
    detailParts.push(coverage)
  }

  return {
    id: 'checker',
    label: 'Findings summary',
    title,
    detail: detailParts.join(' · '),
    tone: critical > 0 ? 'danger' : attention > 0 ? 'warning' : 'success',
    Icon: ShieldCheck,
  }
}

function evidenceStep({ latestSubmission, hasEvidence }) {
  if (!hasEvidence && !latestSubmission) {
    return {
      id: 'evidence',
      label: 'Evidence',
      title: 'No evidence',
      detail: 'Upload documentary evidence before review.',
      tone: 'warning',
      Icon: FileText,
    }
  }
  return {
    id: 'evidence',
    label: 'Evidence',
    title: 'Latest file ready',
    detail: fileNameFor(latestSubmission),
    tone: 'success',
    Icon: FileText,
  }
}

function actionStep({ complianceResult, hasEvidence, locked }) {
  if (locked) {
    return {
      id: 'action',
      label: 'Reviewer path',
      title: 'Status locked',
      detail: 'Use a status-change request before reversing this requirement.',
      tone: 'neutral',
      Icon: ListChecks,
    }
  }
  if (!hasEvidence) {
    return {
      id: 'action',
      label: 'Reviewer path',
      title: 'Evidence needed',
      detail: 'Final review actions are unavailable until evidence is uploaded.',
      tone: 'warning',
      Icon: ListChecks,
    }
  }
  if (!complianceResult) {
    return {
      id: 'action',
      label: 'Reviewer path',
      title: 'Run checker',
      detail: 'Reviewer can still decide manually, but checker findings are missing.',
      tone: 'warning',
      Icon: ListChecks,
    }
  }
  return {
    id: 'action',
    label: 'Reviewer path',
    title: 'Reviewer judgment',
    detail: 'Inspect findings and record human evaluation decision.',
    tone: 'neutral',
    Icon: ListChecks,
  }
}

function GuideStep({ step }) {
  const Icon = step.Icon
  return (
    <div className="flex min-w-0 items-start gap-3 px-4 py-3" data-testid={`review-guide-${step.id}`}>
      <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-brand-border bg-brand-surface-solid text-brand-text-muted">
        <Icon className="h-4 w-4" strokeWidth={1.7} />
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase text-brand-text-muted">{step.label}</span>
          <span className={badgeClassForTone(step.tone)}>{step.title}</span>
        </div>
        <div className="mt-1 truncate text-xs text-brand-text-muted" title={step.detail}>
          {step.detail}
        </div>
      </div>
    </div>
  )
}

export function ReviewerActionGuide({
  latestSubmission,
  complianceResult,
  hasEvidence,
  locked,
  canReviewScan,
  canRunChecker,
  isCheckerRunning,
  onRunChecker,
  onUseReturnNotes,
}) {
  const hasSuggestedNotes = Boolean(complianceResult?.suggested_return_notes)
  const steps = [
    evidenceStep({ latestSubmission, hasEvidence }),
    scanStep(latestSubmission),
    checkerStep(complianceResult),
    actionStep({ complianceResult, hasEvidence, locked }),
  ]
  const showRunChecker = Boolean(canRunChecker && !complianceResult)
  const showUseReturnNotes = Boolean(canReviewScan && hasSuggestedNotes && !locked)

  return (
    <section
      data-testid="reviewer-action-guide"
      className="overflow-hidden rounded-xl border border-brand-border bg-brand-surface"
    >
      <div className="flex flex-col gap-2 border-b border-brand-border px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-brand-text">
            <ClipboardCheck className="h-4 w-4 text-brand-primary" strokeWidth={1.7} />
            Review guide
          </div>
          <p className="mt-1 text-xs leading-5 text-brand-text-muted">
            Scan and checker signals support triage; final compliance action remains a reviewer decision.
          </p>
        </div>
        {(showRunChecker || showUseReturnNotes) && (
          <div className="flex flex-wrap gap-2">
            {showRunChecker && (
              <Button
                size="sm"
                variant="outline"
                icon={ShieldCheck}
                loading={Boolean(isCheckerRunning)}
                onClick={onRunChecker}
              >
                Run Checker
              </Button>
            )}
            {showUseReturnNotes && (
              <Button
                size="sm"
                variant="outline"
                icon={ClipboardCheck}
                onClick={() => onUseReturnNotes?.(complianceResult)}
              >
                Use Return Notes
              </Button>
            )}
          </div>
        )}
      </div>
      <div className="grid divide-y divide-brand-border sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-4">
        {steps.map((step) => (
          <GuideStep key={step.id} step={step} />
        ))}
      </div>
      {complianceResult?.explanation?.summary && (
        <div
          data-testid="reviewer-guide-explanation"
          className="border-t border-brand-border bg-indigo-50/40 px-4 py-2.5 dark:bg-indigo-950/20"
        >
          <div className="flex items-start gap-2">
            <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-indigo-600 dark:text-indigo-400" strokeWidth={1.8} />
            <div className="min-w-0 flex-1">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-indigo-700 dark:text-indigo-300">
                Reviewer Summary
              </div>
              <p className="mt-0.5 text-xs leading-relaxed text-brand-text">
                {complianceResult.explanation.summary}
              </p>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

export default ReviewerActionGuide
