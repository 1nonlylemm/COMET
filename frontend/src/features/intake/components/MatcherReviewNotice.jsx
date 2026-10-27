import { Button } from '../../../components'

const REVIEW_MESSAGES = {
  project_scope_empty: 'The document does not identify a project clearly enough to search its checklist. Select the project to continue reviewing requirements.',
  no_active_requirements: 'No active applicable requirements were found for the candidate projects. Ask an administrator to review their checklists.',
  missing_compatible_requirement: 'The readable document type has no compatible requirement in the available project checklist. Review the project and checklist instead of choosing an unrelated requirement.',
  partial_type_coverage: 'This file contains document types that are not all represented in the available checklist. Review each document before mapping.',
  insufficient_requirement_evidence: 'The available requirements have conflicting or insufficient document-type evidence. Project-name overlap alone cannot establish a match.',
  ai_refinement_unavailable: 'AI verification was unavailable. No requirement was automatically selected; inspect the document and available candidates manually.',
  missing_fund_return_requirement: 'This is proof of return of unutilized funds, but no matching active requirement was found in the resolved project checklist. Ask the program administrator to review the checklist; do not map it to a completion or acceptance certificate.',
  possible_document_bundle: 'This file may contain several document types. Review each page before confirming its mapping.',
  incomplete_extraction: 'Some document content was not retained or could not be read. Review the original file.',
  unreadable_or_unknown_page_coverage: 'Some pages could not be read reliably, or page coverage could not be verified.',
  no_readable_text: 'No readable text was found. Inspect the document visually before confirming its mapping.',
  page_limit_exceeded: 'The document exceeds the extraction page limit. Review the remaining pages.',
  ai_abstained: 'The AI could not choose a requirement. Any remaining suggestion needs manual verification.',
  document_identity_conflict: 'The document content conflicts with the suggested document type.',
  filename_content_conflict: 'The filename and document content indicate different document types.',
  mapping_mismatch: 'The suggested requirement differs from the selected requirement.',
  destination_lgu_mismatch: 'Possible wrong LGU: the document names an LGU that differs from the selected destination.',
  destination_project_title_mismatch: 'Possible wrong project: the document’s project title differs from the selected destination.',
  destination_project_code_mismatch: 'Possible wrong project: the document’s project code differs from the selected destination.',
  destination_requirement_mismatch: 'Possible wrong requirement: the document type differs from the selected requirement.',
  destination_identity_unverified: 'The readable text does not establish the selected project or LGU. Verify the original document before confirming its mapping.',
  overlapping_procurement_requirements: 'This invitation to bid matches both generic and goods procurement posting entries. Review which requirement applies to this project.',
  catalog_scope_conflict: 'The selected active requirement has catalog applicability that differs from this project’s category. Review the catalog and project context before confirming.',
}

const KIND_LABELS = { infrastructure: 'Infrastructure', goods: 'Goods', vehicle: 'Vehicle', financial_assistance: 'Financial assistance', '*': 'All categories', all: 'All categories' }

const ROLE_LABELS = {
  nadai: 'NADAI', receipt: 'Receipt confirmation',
  trust_transfer: 'Trust fund transfer', bank_statement: 'Bank statement',
}

export function MatcherReviewNotice({
  scan,
  submissionId,
  canReviewScan = false,
  onRefreshDestination,
  refreshing = false,
}) {
  const reasons = scan?.review_reasons || []
  const duplicateProjectGroups = scan?.project_duplicate_groups || []
  const hasDestinationConflict = reasons.some((reason) => reason.startsWith('destination_') && reason.endsWith('_mismatch'))
  const messages = [...new Set(reasons.filter((reason) => !(hasDestinationConflict && reason === 'mapping_mismatch')).map((reason) => REVIEW_MESSAGES[reason]).filter(Boolean))]
  const lguCheck = scan?.destination_check?.checks?.find(check => check.field === 'lgu')
  const neutralLgu = ['unverified', 'not_applicable'].includes(lguCheck?.status)

  const destCheck = scan?.destination_check
  const staleness = scan?.destination_staleness
  const isStale = Boolean(staleness?.is_stale || destCheck?.is_stale)
  const staleReasons = staleness?.reasons || destCheck?.stale_reasons || []
  const checkerVersion = destCheck?.checker_version

  if (!messages.length && !neutralLgu && !isStale && !duplicateProjectGroups.length) return null

  const neutral = neutralLgu && !duplicateProjectGroups.length && reasons.every(reason => reason === 'destination_identity_unverified')
  const isStaleOnly = isStale && !messages.length && !neutralLgu
  const suggestions = scan?.document_evidence?.page_requirement_suggestions || []
  const pages = scan?.document_evidence?.page_roles || []
  const ambiguities = scan?.document_evidence?.requirement_ambiguities || []
  const scope = scan?.document_evidence?.catalog_scope
  const activity = scan?.document_evidence?.procurement_activity?.classifications || []
  const identities = scan?.document_evidence?.candidate_guard?.detected_identities || []

  const aiAbstained = reasons.includes('ai_abstained')
  const aiReason = scan?.ai_metadata?.reason

  return (
    <div className={neutral ? 'rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-700 dark:bg-slate-900 dark:text-slate-200' : 'rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-300/40 dark:bg-amber-300/10 dark:text-amber-100'} role="note">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">{neutral ? 'Destination not verified' : isStaleOnly ? 'Destination check out of date' : 'Document review needed'}</p>
        {checkerVersion && (
          <span className="text-xs opacity-75" data-testid="destination-checker-version">
            Checker v{checkerVersion}
          </span>
        )}
      </div>
      {neutralLgu && <p className="text-slate-600 dark:text-slate-300" data-testid="lgu-destination-status">LGU: {lguCheck.status === 'not_applicable' ? 'Not applicable' : 'Unverified'}. {lguCheck.reason}</p>}
      <ul className="mt-1 list-disc pl-5">{messages.map((message) => <li key={message}>{message}</li>)}</ul>
      {duplicateProjectGroups.map((group, index) => (
        <div className="mt-2 rounded border border-amber-400/50 bg-amber-100/60 p-2 text-xs text-amber-950 dark:bg-amber-900/30 dark:text-amber-100" data-testid="possible-duplicate-project-group" key={`${group.project_name}-${group.fiscal_year}-${index}`}>
          <p className="font-medium">{group.project_name} · {group.lgu_name} · FY{group.fiscal_year}</p>
          <p>Program: {group.program_name}</p>
          <p><strong>Possible duplicate project records:</strong> These catalog entries share the same project, LGU, program, and fiscal year, but have different source codes. The Matcher keeps them separate; verify the source records or ask an administrator to reconcile them.</p>
          <ul className="mt-1 list-disc pl-5">{(group.projects || []).map((project) => (
            <li key={project.project_id}>Project #{project.project_id}{project.project_code ? ` · ${project.project_code}` : ''}</li>
          ))}</ul>
        </div>
      ))}
      {aiAbstained && aiReason && (
        <p className="mt-1 text-xs opacity-90" data-testid="ai-abstention-reason">AI abstention reason: {aiReason}</p>
      )}
      {identities.length > 0 && scan?.review_reasons?.includes('missing_compatible_requirement') && (
        <p className="mt-1">Detected document types: {identities.map((identity) => identity.replaceAll('_', ' ')).join(', ')}.</p>
      )}
      {scan?.destination_check?.checks?.filter((check) => check.status === 'mismatch').map((check, index) => (
        <div className="mt-2 text-xs" key={`${check.field}-${index}`}>
          <p>Selected: <strong>{check.expected}</strong></p>
          <p>Document: <strong>{(check.conflicts || []).map((item) => `${item.text}${item.page ? ` (page ${item.page})` : ''}`).join('; ')}</strong></p>
        </div>
      ))}
      {isStale && (
        <div className="mt-2 rounded border border-amber-400/50 bg-amber-100/60 p-2 text-xs text-amber-950 dark:bg-amber-900/30 dark:text-amber-200" data-testid="destination-stale-notice">
          <p className="font-medium">Destination check was run against earlier project details or checker version:</p>
          <ul className="mt-0.5 list-disc pl-4">
            {staleReasons.map((reason, idx) => <li key={idx}>{reason}</li>)}
          </ul>
        </div>
      )}
      {canReviewScan && onRefreshDestination && (
        <div className="mt-3 flex items-center justify-end gap-2 border-t border-amber-200/60 pt-2 dark:border-amber-400/20">
          <Button
            size="sm"
            variant="outline"
            loading={refreshing}
            onClick={() => onRefreshDestination(submissionId)}
          >
            Re-check destination
          </Button>
        </div>
      )}
      {(scope?.status === 'mismatch' || ambiguities.length > 0) && (
        <details className="mt-2">
          <summary className="cursor-pointer">View project and procurement context</summary>
          <p className="mt-1">Project category: {KIND_LABELS[scope?.project_kind] || 'Unavailable'}</p>
          <p>Document procurement classification: {activity.length ? activity.map((kind) => KIND_LABELS[kind] || kind).join(', ') : 'Not established from readable text'}</p>
          {scope?.status !== 'unknown' && scope?.declared_project_kinds !== undefined && (
            <p>Selected requirement catalog categories: {scope.declared_project_kinds === null ? 'All categories' : scope.declared_project_kinds.map((kind) => KIND_LABELS[kind] || kind).join(', ') || 'No categories declared'}</p>
          )}
          <p className="mt-1 text-xs">Procurement activity and project category can differ. This evidence does not change project requirements or establish compliance.</p>
        </details>
      )}
      {ambiguities.map((ambiguity, index) => (
        <details className="mt-2" key={`${ambiguity.kind}-${index}`}>
          <summary className="cursor-pointer">View overlapping requirements</summary>
          <p className="mt-1 text-xs">Policy review is needed to determine acceptance. These entries have not been treated as equivalent.</p>
          <ul className="mt-1 list-disc pl-5">{(ambiguity.alternatives || []).map((item) => (
            <li key={item.project_requirement_id}>{item.requirement_name}</li>
          ))}</ul>
        </details>
      ))}
      {scan?.document_evidence?.possible_bundle && (suggestions.length > 0 || pages.some((page) => page.roles?.length)) && (
        <details className="mt-2">
          <summary className="cursor-pointer">View page evidence suggestions</summary>
          <p className="mt-1 text-xs">These suggestions require review and do not mark requirements compliant.</p>
          <ul className="mt-1 list-disc pl-5">{suggestions.map((item, index) => (
            <li key={`${item.page}-${item.project_requirement_id}-${index}`}>Page {item.page}: {item.requirement_name}</li>
          ))}</ul>
          {pages.flatMap((page) => (page.roles || []).filter((role) => !suggestions.some((item) => item.page === page.page && item.role === role)).map((role) => (
            <p className="mt-1 text-xs" key={`${page.page}-${role}`}>Page {page.page}: {ROLE_LABELS[role] || 'Document evidence'} observed; no matching requirement among the available candidates.</p>
          )))}
        </details>
      )}
    </div>
  )
}
