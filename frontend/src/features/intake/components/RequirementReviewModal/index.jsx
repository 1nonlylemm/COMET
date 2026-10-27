import { useMemo, useRef, useState } from 'react'
import { CheckCircle2, Download, FileText, Gauge, History, Info, Layers, Map, Sparkles, Upload } from 'lucide-react'
import { Button, Modal, InlineAlert } from '../../../../components'
import * as projectApi from '../../../projects/api/projectApi'
import { formatDate } from '../../lib/intakeFormatters'
import { AiRewriteControl } from '../../../ai/components/AiRewriteControl'
import { ComplianceScorecard } from '../ComplianceScorecard'
import { DocumentAnnotationViewer } from '../DocumentAnnotationViewer'
import { AddVersionForm } from './AddVersionForm'
import { DetailsAccordion } from './DetailsAccordion'
import { FieldOfficerTransmittalCard } from './FieldOfficerTransmittalCard'
import { FindingsTabs } from './FindingsTabs'
import { RequirementHeader } from './RequirementHeader'
import { ReviewOverview } from './ReviewOverview'
import { ReviewActionsBar } from './ReviewActionsBar'
import { ReviewSnapshot } from './ReviewSnapshot'
import { ReviewerDecisionPanel } from './ReviewerDecisionPanel'
import { ScanMappingCard } from './ScanMappingCard'
import { MatcherReviewNotice } from '../MatcherReviewNotice.jsx'
import { SubmissionFilesList } from './SubmissionFilesList'
import { SubmissionHistoryList } from './SubmissionHistoryList'
import { StatusChangeModal } from './StatusChangeModal'

/** Document-first workspace with contextual return preparation. */
export default function RequirementReviewModal({
  open,
  selectedRequirement,
  submissions = [],
  submissionsLoading,
  canReviewScan: requestedCanReviewScan,
  canUpload = true,
  selectedHasEvidence,
  selectedReviewLocked: requestedReviewLocked,
  reviewUploadOpen,
  setReviewUploadOpen,
  uploadForm,
  setUploadForm,
  uploading,
  scanPreview,
  scanPreviewLoading,
  scanPreviewError,
  setScanPreviewError,
  previewMatchesSelected,
  revisionNotes,
  setRevisionNotes,
  requirementReviewing,
  reviewingScanId,
  checkingSubmissionId,
  reviewingComplianceResultId,
  filePreviewLoadingId,
  userRole = 'staff',
  error = '',
  onDismissError,
  onClose,
  onUploadSubmission,
  onApproveRequirement,
  onReturnRequirementForRevision,
  onApplyCheckerReturnNotes,
  onRecordComplianceReview,
  onRunComplianceCheck,
  onRescanSubmission,
  onRefreshDestination,
  onReviewScan,
  onPreview,
  onDownload,
  onStatusChange,
  onRefreshRequirement,
}) {
  const latestSubmission = submissions[0] || null
  const latestScan = latestSubmission?.nlp_scan_results?.[0] || latestSubmission?.latest_nlp_scan
  const neutralLguDestination = latestScan?.destination_check?.checks?.some(check =>
    check.field === 'lgu' && ['unverified', 'not_applicable'].includes(check.status))
  const isDestinationStale = Boolean(
    latestScan?.destination_staleness?.is_stale || latestScan?.destination_check?.is_stale
  )
  const hasMappingWarning = Boolean(
    latestScan?.mapping_mismatch ||
    (latestScan?.review_reasons || []).includes('mapping_mismatch')
  )
  const olderSubmissions = useMemo(() => submissions.slice(1), [submissions])
  const latestCompliance = latestSubmission?.latest_compliance_result || latestSubmission?.compliance_results?.[0] || null
  const findings = latestCompliance?.findings || []
  const scoreDetails = latestCompliance?.score_details || null
  const findingReviews = latestCompliance?.finding_reviews || scoreDetails?.finding_reviews || {}
  const [previewFileId, setPreviewFileId] = useState(null)
  const primaryFile = latestSubmission?.document_files?.find(file => file.id === latestCompliance?.document_file_id)
    || latestSubmission?.document_files?.[latestSubmission.document_files.length - 1] || null
  const latestFile = latestSubmission?.document_files?.find(file => file.id === previewFileId) || primaryFile
  const hasComplianceResult = Boolean(latestCompliance)
  const hasPriorYearAvailable = Boolean(latestCompliance?.reference_basis?.prior_profiles_available?.length)
  const isCheckerRunning = checkingSubmissionId === `${latestSubmission?.id}:current`
  const isPriorRunning = checkingSubmissionId === `${latestSubmission?.id}:prior`

  // Controlled finding citation selection and custom deficiency state
  const [selectedFindingKeys, setSelectedFindingKeys] = useState(new Set())
  const [customDeficiencies, setCustomDeficiencies] = useState([])
  const [returnPreparing, setReturnPreparing] = useState(false)
  const [focusTarget, setFocusTarget] = useState(null)
  const [mobilePanel, setMobilePanel] = useState('review')
  const returnNotesRef = useRef(null)
  const previewRef = useRef(null)
  const reviewScope = `${open}:${selectedRequirement?.id}:${latestSubmission?.id}:${latestCompliance?.id}`
  const [prevRequirementId, setPrevRequirementId] = useState(reviewScope)

  if (reviewScope !== prevRequirementId) {
    setPrevRequirementId(reviewScope)
    setReturnPreparing(false)
    setFocusTarget(null)
    setPreviewFileId(null)
    setMobilePanel('review')
    setSelectedFindingKeys(new Set())
    setCustomDeficiencies([])
  }

  const [downloadingReport, setDownloadingReport] = useState(false)
  const [downloadReportError, setDownloadReportError] = useState('')
  const [statusChangeModalOpen, setStatusChangeModalOpen] = useState(false)

  const handleStatusChangeSubmit = async (data) => {
    if (onStatusChange) {
      await onStatusChange(selectedRequirement.id, data)
    } else {
      await projectApi.createChangeStatusRequest(selectedRequirement.id, data)
      if (data.auto_approve) {
        if (selectedRequirement) {
          selectedRequirement.status = data.requested_status
          if (data.requested_status === 'under_review') {
            selectedRequirement.workflow_status = 'submitted'
          } else if (data.requested_status === 'compliant') {
            selectedRequirement.workflow_status = 'approved'
          }
        }
        await onRefreshRequirement?.(selectedRequirement)
      }
    }
  }

  const isFieldOfficer = userRole === 'field_officer'
  const isProgramInactive = selectedRequirement?.program_is_active === false || selectedRequirement?.program?.is_active === false
  const isNotApplicable = selectedRequirement?.applicability === 'not_applicable'
  const uploadAllowed = canUpload && !isProgramInactive && !isNotApplicable
  const canReviewScan = requestedCanReviewScan && !isNotApplicable
  const selectedReviewLocked = requestedReviewLocked || isNotApplicable
  const currentWorkflowStatus = selectedRequirement?.workflow_status || selectedRequirement?.status
  const isReturnedForRevision = currentWorkflowStatus === 'returned_for_revision'
  const latestRevision = selectedRequirement?.current_return || (isReturnedForRevision ? (selectedRequirement?.custom_fields?.latest_revision || selectedRequirement?.latest_revision) : null)
  const returnHistory = selectedRequirement?.return_history || selectedRequirement?.custom_fields?.revision_history || []
  const isSubmittedAwaitingReview = ['submitted', 'under_verification', 'resubmitted', 'pending_provincial_approval', 'staff_approved'].includes(currentWorkflowStatus)
  const isApproved = ['approved', 'compliant'].includes(currentWorkflowStatus)

  const handleDownloadCorrectionReport = async (options = {}) => {
    if (!selectedRequirement?.id) return
    const safeOptions = (options && typeof options === 'object' && !('nativeEvent' in options)) ? options : {}
    setDownloadingReport(true)
    setDownloadReportError('')
    try {
      const response = Object.keys(safeOptions).length > 0
        ? await projectApi.downloadRequirementCorrectionReport(selectedRequirement.id, safeOptions)
        : await projectApi.downloadRequirementCorrectionReport(selectedRequirement.id)
      const blob = new Blob([response.data], {
        type: response.headers?.['content-type'] || 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
      const disposition = response.headers?.['content-disposition'] || ''
      const match = disposition.match(/filename="?([^"]+)"?/i)
      const fileName = match?.[1] || `requirement-${selectedRequirement.id}-correction-report.docx`
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = fileName
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      setTimeout(() => window.URL.revokeObjectURL(url), 1500)
    } catch (err) {
      setDownloadReportError(err.response?.data?.message || 'Unable to download the correction report.')
    } finally {
      setDownloadingReport(false)
    }
  }

  const isDismissed = key => (findingReviews[key] || findingReviews[String(key).replace('missing_evidence:', 'missing_evidence_')])?.status === 'incorrect_flag'
  const citedFindingKeys = new Set([...selectedFindingKeys].filter(key => !isDismissed(key)))

  const handleToggleSelectFinding = (findingKey) => {
    if (isDismissed(findingKey)) return
    setSelectedFindingKeys((prev) => {
      const next = new Set(prev)
      if (next.has(findingKey)) {
        next.delete(findingKey)
      } else {
        next.add(findingKey)
      }
      return next
    })
  }

  const handleSaveFindingReview = async (update) => {
    const saved = await onRecordComplianceReview?.(latestCompliance.id, { finding_reviews: [update] })
    if (saved !== false && update.status === 'incorrect_flag') {
      setSelectedFindingKeys(previous => {
        const next = new Set(previous)
        next.delete(update.finding_id)
        next.delete(update.finding_id.replace('missing_evidence_', 'missing_evidence:'))
        return next
      })
    }
    return saved
  }

  const handleSelectAllFindings = (activeFindings) => {
    setSelectedFindingKeys((prev) => {
      const next = new Set(prev)
      ;(activeFindings || []).forEach((f) => {
        const key = f.id || f.message
        next.add(key)
      })
      return next
    })
  }

  const handleClearSelection = () => {
    setSelectedFindingKeys(new Set())
  }

  const handleAddCustomDeficiency = () => {
    setCustomDeficiencies((prev) => [
      ...prev,
      {
        category: 'missing_attachment',
        finding_observation: '',
        corrective_instruction: '',
      },
    ])
  }

  const handleRemoveCustomDeficiency = (index) => {
    setCustomDeficiencies((prev) => prev.filter((_, idx) => idx !== index))
  }

  const handleUpdateCustomDeficiency = (index, field, value) => {
    setCustomDeficiencies((prev) => {
      const next = [...prev]
      next[index] = { ...next[index], [field]: value }
      return next
    })
  }

  const totalSelectedCount = citedFindingKeys.size + customDeficiencies.length
  const customItemsComplete = customDeficiencies.every(item => item.finding_observation?.trim() && item.corrective_instruction?.trim())
  const canReturnDirectly = customItemsComplete && (totalSelectedCount > 0 || (revisionNotes || '').trim().length >= 3)

  const handleExecuteReturn = () => {
    if (!canReturnDirectly || selectedReviewLocked || requirementReviewing) return
    const selectedFindings = (findings || []).filter((f) => {
      const key = f.id || f.message
      if (citedFindingKeys.has(key)) return true
      const colonKey = String(key).replace('missing_evidence_', 'missing_evidence:')
      const underscoreKey = String(key).replace('missing_evidence:', 'missing_evidence_')
      return citedFindingKeys.has(colonKey) || citedFindingKeys.has(underscoreKey)
    })

    const deficienciesFromFindings = selectedFindings.map((f) => ({
      category: f.deficiency_category || f.category || 'other_documented_defect',
      finding_observation: f.finding_observation || f.observation || f.message || 'Identified compliance issue',
      corrective_instruction: f.corrective_instruction || f.reviewer_action || f.detail || f.message || 'Please correct identified issue and resubmit.',
      severity: f.severity,
      citation: f.citation,
      field_key: f.field_key,
    }))

    const deficienciesFromCustom = customDeficiencies.map((c) => ({
      category: c.category || 'other_documented_defect',
      finding_observation: c.finding_observation?.trim() || '',
      corrective_instruction: c.corrective_instruction?.trim() || '',
    }))

    // Checklist citations may exist without a corresponding finding in older results.
    const evidenceChecks = latestCompliance?.evidence_checks || scoreDetails?.evidence_checks || []
    const deficienciesFromChecks = evidenceChecks.filter(check => check.state === 'not_detected'
      && (citedFindingKeys.has(`missing_evidence:${check.key}`) || citedFindingKeys.has(`missing_evidence_${check.key}`))
      && !selectedFindings.some(finding => String(finding.id || '').replace('missing_evidence_', 'missing_evidence:') === `missing_evidence:${check.key}`)
    ).map(check => ({
      category: check.deficiency_category || 'other_documented_defect',
      finding_observation: check.label || check.key,
      corrective_instruction: check.explanation || `Provide the required evidence: ${check.label || check.key}.`,
      field_key: check.key,
    }))
    const allDeficiencies = [...deficienciesFromFindings, ...deficienciesFromChecks, ...deficienciesFromCustom]
    const trimmedNotes = (revisionNotes || '').trim()

    onReturnRequirementForRevision?.({
      reason: trimmedNotes || undefined,
      deficiencies: allDeficiencies,
    })
  }

  if (isFieldOfficer) {
    return (
      <Modal
        open={open}
        title="Documentary Requirement"
        description={selectedRequirement ? `${selectedRequirement.project_name} · ${selectedRequirement.lgu_name}` : ''}
        onClose={onClose}
        size="lg"
      >
        {selectedRequirement && (
          <div className="flex h-full flex-col gap-5">
            <RequirementHeader requirement={selectedRequirement} userRole={userRole} />

            {error && (
              <InlineAlert type="error" onDismiss={onDismissError}>
                {error}
              </InlineAlert>
            )}

            {/* Formal Return Transmittal Card if returned for revision */}
            {isReturnedForRevision && (
              <FieldOfficerTransmittalCard
                requirement={selectedRequirement}
                latestRevision={latestRevision}
                onDownloadReport={handleDownloadCorrectionReport}
                downloading={downloadingReport}
                downloadError={downloadReportError}
              />
            )}

            {/* Submitted status notice if awaiting review */}
            {selectedRequirement.status === 'non_compliant' && (
              <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
                This requirement is marked Non-Compliant. A reviewer must obtain an approved status-change request before reopening its review. Recording a corrected file does not clear this status.
              </div>
            )}
            {isSubmittedAwaitingReview && !isReturnedForRevision && selectedRequirement.status !== 'non_compliant' && (
              <div className="flex items-start gap-3 rounded-xl border border-blue-200 bg-blue-50/60 p-4 text-xs dark:border-blue-800/40 dark:bg-blue-950/20">
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-600 dark:text-blue-400" />
                <div>
                  <div className="font-semibold text-blue-900 dark:text-blue-200">
                    {currentWorkflowStatus === 'resubmitted'
                      ? `Version ${latestSubmission?.version_number || latestSubmission?.current_version || (olderSubmissions.length + 1)} Resubmitted — Awaiting Review`
                      : 'Document Submitted — Awaiting Review'}
                  </div>
                  <div className="mt-0.5 text-blue-800/80 dark:text-blue-300/80">
                    {currentWorkflowStatus === 'resubmitted'
                      ? 'Your revised documentary submission has been received and is queued for staff evaluation.'
                      : 'Your documentary submission has been received and is queued for evaluation.'}
                  </div>
                </div>
              </div>
            )}

            {/* Approved status notice */}
            {isApproved && (
              <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50/60 p-4 text-xs dark:border-emerald-800/40 dark:bg-emerald-950/20">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                <div>
                  <div className="font-semibold text-emerald-900 dark:text-emerald-200">
                    Requirement Approved
                  </div>
                  <div className="mt-0.5 text-emerald-800/80 dark:text-emerald-300/80">
                    This documentary requirement has been verified and approved by the reviewing office.
                  </div>
                </div>
              </div>
            )}

            {/* Uploaded Documents */}
            {submissionsLoading ? (
              <div className="text-sm text-brand-text-muted">Loading documents...</div>
            ) : latestSubmission ? (
              <div className="rounded-xl border border-brand-border bg-brand-surface p-4">
                <div className="mb-3 text-sm font-semibold text-brand-text">Submitted Document</div>
                <SubmissionFilesList
                  files={latestSubmission?.document_files || []}
                  filePreviewLoadingId={filePreviewLoadingId}
                  onPreview={onPreview}
                  onDownload={onDownload}
                />
              </div>
            ) : (
              <div className="rounded-md border border-dashed border-brand-border bg-brand-surface px-4 py-6 text-center text-sm text-brand-text-muted">
                No documentary evidence has been uploaded for this requirement yet.
              </div>
            )}

            {/* Previous versions if any */}
            {olderSubmissions.length > 0 && (
              <DetailsAccordion
                sections={[
                  {
                    id: 'history',
                    label: 'Previous versions',
                    icon: Layers,
                    count: olderSubmissions.length,
                    content: (
                      <SubmissionHistoryList
                        submissions={olderSubmissions}
                        filePreviewLoadingId={filePreviewLoadingId}
                        onPreview={onPreview}
                        onDownload={onDownload}
                      />
                    ),
                  },
                ]}
              />
            )}

            {/* Previous return history if applicable */}
            {!isReturnedForRevision && returnHistory.length > 0 && (
              <DetailsAccordion
                sections={[
                  {
                    id: 'return_history',
                    label: `Previous Return History (${returnHistory.length})`,
                    icon: History,
                    content: (
                      <div className="space-y-3 p-1">
                        {returnHistory.map((rev, idx) => (
                          <div
                            key={idx}
                            className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 text-xs dark:border-slate-700/60 dark:bg-slate-800/40"
                          >
                            <div className="flex items-center justify-between font-medium text-slate-800 dark:text-slate-200">
                              <span>Return #{returnHistory.length - idx} {rev.returned_at ? `· ${formatDate(rev.returned_at)}` : ''}</span>
                              {rev.report_id && (
                                <Button
                                  size="xs"
                                  variant="outline"
                                  icon={Download}
                                  onClick={() => handleDownloadCorrectionReport({ report_id: rev.report_id })}
                                >
                                  Report
                                </Button>
                              )}
                            </div>
                            {rev.notes && (
                              <p className="mt-1 text-slate-600 dark:text-slate-300 whitespace-pre-wrap">
                                {rev.notes}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    ),
                  },
                ]}
              />
            )}

            {/* Add version / resubmit form */}
            {uploadAllowed && (
              <div className="rounded-xl border border-brand-border bg-brand-surface p-4">
                <div className="mb-3 text-sm font-semibold text-brand-text">
                  {isReturnedForRevision ? 'Resubmit Corrected Document' : 'Upload Document'}
                </div>
                <AddVersionForm
                  uploadForm={uploadForm}
                  setUploadForm={setUploadForm}
                  uploading={uploading}
                  scanPreview={scanPreview}
                  scanPreviewLoading={scanPreviewLoading}
                  scanPreviewError={scanPreviewError}
                  setScanPreviewError={setScanPreviewError}
                  previewMatchesSelected={previewMatchesSelected}
                  onUploadSubmission={onUploadSubmission}
                />
              </div>
            )}

            <div className="flex justify-end border-t border-brand-border pt-3">
              <Button variant="outline" onClick={onClose}>
                Close
              </Button>
            </div>
          </div>
        )}
      </Modal>
    )
  }

  const sections = []
  if (scoreDetails) {
    sections.push({
      id: 'scorecard',
      label: 'Scorecard breakdown',
      icon: Gauge,
      content: <ComplianceScorecard result={latestCompliance} />,
    })
  }
  if (latestSubmission) {
    sections.push({
      id: 'scan_mapping',
      label: (() => { const scan = latestSubmission?.nlp_scan_results?.[0] || latestSubmission?.latest_nlp_scan; return scan?.is_accepted == null ? 'Scan mapping · Needs review' : 'Scan mapping' })(),
      icon: Map,
      content: (
        <ScanMappingCard
          submissionId={latestSubmission?.id}
          scan={latestSubmission?.nlp_scan_results?.[0] || latestSubmission?.latest_nlp_scan}
          canReviewScan={canReviewScan}
          reviewingScanId={reviewingScanId}
          onRescanSubmission={onRescanSubmission}
          onReviewScan={onReviewScan}
        />
      ),
    })
    sections.push({
      id: 'files',
      label: 'Files',
      icon: FileText,
      count: latestSubmission?.document_files?.length || 0,
      content: (
        <SubmissionFilesList
          files={latestSubmission?.document_files || []}
          filePreviewLoadingId={filePreviewLoadingId}
          onPreview={onPreview}
          onDownload={onDownload}
        />
      ),
    })
  }
  if (olderSubmissions.length > 0) {
    sections.push({
      id: 'history',
      label: 'Previous versions',
      icon: Layers,
      count: olderSubmissions.length,
      content: (
        <SubmissionHistoryList
          submissions={olderSubmissions}
          filePreviewLoadingId={filePreviewLoadingId}
          onPreview={onPreview}
          onDownload={onDownload}
        />
      ),
    })
  }
  if (returnHistory.length > 0) {
    sections.push({
      id: 'return_history',
      label: `Return history (${returnHistory.length})`,
      icon: History,
      count: returnHistory.length,
      content: (
        <div className="space-y-3 p-1">
          {returnHistory.map((rev, idx) => (
            <div
              key={idx}
              className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 text-xs dark:border-slate-700/60 dark:bg-slate-800/40"
            >
              <div className="flex items-center justify-between font-medium text-slate-800 dark:text-slate-200">
                <span>Return #{returnHistory.length - idx} {rev.returned_at ? `· ${formatDate(rev.returned_at)}` : ''}</span>
                {rev.report_id && (
                  <Button
                    size="xs"
                    variant="outline"
                    icon={Download}
                    onClick={() => handleDownloadCorrectionReport({ report_id: rev.report_id })}
                  >
                    Download Report
                  </Button>
                )}
              </div>
              {rev.notes && (
                <p className="mt-1 text-slate-600 dark:text-slate-300 whitespace-pre-wrap">
                  {rev.notes}
                </p>
              )}
            </div>
          ))}
        </div>
      ),
    })
  }
  if (uploadAllowed) {
    sections.push({
      id: 'add_version',
      label: reviewUploadOpen ? 'Add new version (open)' : 'Add new version',
      icon: Upload,
      defaultOpen: reviewUploadOpen,
      content: (
        <AddVersionForm
          uploadForm={uploadForm}
          setUploadForm={setUploadForm}
          uploading={uploading}
          scanPreview={scanPreview}
          scanPreviewLoading={scanPreviewLoading}
          scanPreviewError={scanPreviewError}
          setScanPreviewError={setScanPreviewError}
          previewMatchesSelected={previewMatchesSelected}
          onUploadSubmission={(event) => {
            setReviewUploadOpen?.(true)
            onUploadSubmission?.(event)
          }}
        />
      ),
    })
  }

  const handleApply = () => {
    if (latestCompliance?.suggested_return_notes) {
      setRevisionNotes?.(latestCompliance.suggested_return_notes)
      onApplyCheckerReturnNotes?.(latestCompliance)
    }
  }

  const handlePrepareReturn = () => {
    setMobilePanel('review')
    setReturnPreparing(true)
    requestAnimationFrame(() => {
      returnNotesRef.current?.scrollIntoView?.({ block: 'nearest' })
      returnNotesRef.current?.querySelector('textarea')?.focus()
    })
  }

  const handleViewFinding = (finding) => {
    const page = finding.page || finding.locations?.[0]?.page
    setPreviewFileId(finding.document_file_id || primaryFile?.id)
    setFocusTarget({ page, findingId: finding.id, annotationId: finding.annotationId })
    setMobilePanel('document')
    requestAnimationFrame(() => previewRef.current?.scrollIntoView?.({ block: 'nearest' }))
  }

  const actions = latestSubmission && !submissionsLoading && !isNotApplicable ? (
    <div className="space-y-2">
      {returnPreparing && <Button size="sm" variant="ghost" disabled={Boolean(requirementReviewing)} onClick={() => setReturnPreparing(false)}>Cancel return</Button>}
      <ReviewActionsBar
        role={userRole}
        hasComplianceResult={hasComplianceResult}
        locked={selectedReviewLocked}
        hasEvidence={selectedHasEvidence}
        isApproveLoading={requirementReviewing === 'approve'}
        isReturnLoading={requirementReviewing === 'revision'}
        isProgramInactive={Boolean(selectedRequirement?.program_is_active === false || selectedRequirement?.program?.is_active === false)}
        programId={selectedRequirement?.program_id || selectedRequirement?.program?.id}
        onApprove={onApproveRequirement}
        onReturn={returnPreparing ? handleExecuteReturn : handlePrepareReturn}
        workflowStatus={selectedRequirement?.workflow_status}
        selectedCount={totalSelectedCount}
        canReturnDirectly={canReturnDirectly}
        contained
        hideApprove={returnPreparing}
        preparingReturn={!returnPreparing}
        returnLabel={returnPreparing ? 'Confirm Return for Revision' : undefined}
        onReopen={() => setStatusChangeModalOpen(true)}
      />
    </div>
  ) : null

  return (
    <>
      <Modal
      open={open}
      title="Requirement Review"
      description={selectedRequirement ? `${selectedRequirement.project_name} · ${selectedRequirement.lgu_name}` : ''}
      onClose={onClose}
      size="review"
      workspace
      footer={actions}
    >
      {selectedRequirement && (
        <div className="flex h-full flex-col gap-5">
          <RequirementHeader requirement={selectedRequirement} userRole={userRole} compact />

          {error && (
            <InlineAlert type="error" onDismiss={onDismissError}>
              {error}
            </InlineAlert>
          )}

          {isNotApplicable && (
            <InlineAlert type="info">
              This requirement is Not Applicable. Historical evidence remains available.
              Restore applicability from the project requirements list before uploading or reviewing evidence.
            </InlineAlert>
          )}

          {selectedReviewLocked && !isFieldOfficer && !isNotApplicable && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-300 bg-amber-50/80 p-3.5 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
              <div className="flex items-start gap-2.5">
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                <div>
                  <div className="font-semibold text-amber-950 dark:text-amber-100">
                    This requirement is marked {selectedRequirement.status === 'non_compliant' ? 'Non-Compliant' : selectedRequirement.status === 'compliant' ? 'Compliant' : 'Waived'}
                  </div>
                  <div className="mt-0.5 text-amber-800/90 dark:text-amber-300/90">
                    A status-change request is required before reversing or reopening review on this requirement.
                  </div>
                </div>
              </div>
              <Button
                size="sm"
                variant="default"
                onClick={() => setStatusChangeModalOpen(true)}
              >
                {userRole === 'admin' ? 'Reopen for Review' : 'Request Status Reversal'}
              </Button>
            </div>
          )}

          {submissionsLoading ? (
            <div className="text-sm text-brand-text-muted">Loading submissions...</div>
          ) : latestSubmission ? (
            <>
              <div className="flex flex-wrap gap-2 lg:hidden" role="group" aria-label="Review workspace view">
                <Button size="sm" variant={mobilePanel === 'review' ? 'default' : 'outline'} aria-pressed={mobilePanel === 'review'} onClick={() => setMobilePanel('review')}>Review findings</Button>
                <Button size="sm" variant={mobilePanel === 'document' ? 'default' : 'outline'} aria-pressed={mobilePanel === 'document'} onClick={() => setMobilePanel('document')}>Document</Button>
              </div>
              <div className="grid min-w-0 grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
                <div ref={previewRef} className={`${mobilePanel === 'document' ? 'block' : 'hidden'} min-w-0 space-y-3 lg:sticky lg:top-0 lg:block`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    {latestSubmission.document_files?.length > 1 ? <label className="min-w-0 flex-1 text-xs text-brand-text-muted">Document
                      <select aria-label="Document to preview" className="input-field mt-1 w-full" value={latestFile?.id || ''} onChange={event => { setPreviewFileId(Number(event.target.value)); setFocusTarget(null) }}>
                        {latestSubmission.document_files.map(file => <option key={file.id} value={file.id}>{file.file_name}{file.id === primaryFile?.id ? ' (reviewed primary)' : ''}</option>)}
                      </select>
                    </label> : <p className="min-w-0 break-all text-sm font-medium text-brand-text">{latestFile?.file_name || latestSubmission.primary_file_name || 'Recorded evidence'}</p>}
                    {latestFile && <Button size="sm" variant="outline" onClick={() => onPreview?.(latestFile)} loading={filePreviewLoadingId === latestFile.id}>Open document</Button>}
                  </div>
                  <DocumentAnnotationViewer workspace result={latestFile?.id === primaryFile?.id ? latestCompliance : null} file={latestFile} focusTarget={focusTarget} />
                </div>
                <div className={`${mobilePanel === 'review' ? 'block' : 'hidden'} min-w-0 space-y-4 lg:block`}>
                  {(hasMappingWarning || neutralLguDestination || isDestinationStale) && (
                    <MatcherReviewNotice
                      scan={latestScan}
                      submissionId={latestSubmission?.id}
                      canReviewScan={canReviewScan}
                      onRefreshDestination={onRefreshDestination}
                      refreshing={reviewingScanId === `refresh-destination-${latestSubmission?.id}`}
                    />
                  )}
                  <ReviewOverview result={latestCompliance} findingReviews={findingReviews} canRun={canReviewScan} running={isCheckerRunning} onRun={() => onRunComplianceCheck?.(latestSubmission.id)} />
                  <FindingsTabs
                    key={latestCompliance?.id || 'unchecked'}
                    findingReviews={findingReviews}
                    savingReview={reviewingComplianceResultId === latestCompliance?.id}
                    onSaveFindingReview={onRecordComplianceReview && latestCompliance ? handleSaveFindingReview : undefined}
                    findings={findings}
                    selectedKeys={citedFindingKeys}
                    onToggleSelect={handleToggleSelectFinding}
                    onSelectAll={handleSelectAllFindings}
                    onClearSelection={handleClearSelection}
                    customDeficiencies={customDeficiencies}
                    onAddCustomDeficiency={handleAddCustomDeficiency}
                    onRemoveCustomDeficiency={handleRemoveCustomDeficiency}
                    onUpdateCustomDeficiency={handleUpdateCustomDeficiency}
                    disabled={selectedReviewLocked || Boolean(requirementReviewing)}
                    compact
                    onViewFinding={handleViewFinding}
                  />

                  {/* Inline Reviewer Transmittal Instructions (Return Notes) */}
                  {returnPreparing && <div
                    ref={returnNotesRef}
                    data-testid="inline-return-notes"
                    className="rounded-xl border border-brand-border bg-brand-surface p-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <div className="text-sm font-semibold text-brand-text">
                          Reviewer Transmittal Instructions
                        </div>
                        <p className="text-xs text-brand-text-muted">
                          Clear instructions explaining what must be corrected or resubmitted.
                          {totalSelectedCount > 0
                            ? ' (Optional because deficiency items are cited above)'
                            : ' (Required if returning without citing specific findings)'}
                        </p>
                      </div>
                      {canReviewScan && Boolean(latestCompliance?.suggested_return_notes) && (
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={Sparkles}
                          onClick={handleApply}
                        >
                          Use Suggested Notes
                        </Button>
                      )}
                    </div>
                    <div className="mt-3">
                      <p className="mb-3 text-sm text-brand-text">{totalSelectedCount} item{totalSelectedCount === 1 ? '' : 's'} selected for return. Confirm the cited observations and instructions before submitting.</p>
                      {!customItemsComplete && <p role="alert" className="mb-2 text-sm text-amber-800 dark:text-amber-200">Complete the observation and corrective instruction for each custom deficiency before returning.</p>}
                      <AiRewriteControl
                        label="Return Instructions"
                        value={revisionNotes}
                        onTextChange={setRevisionNotes}
                        contextLabel="Requirement revision instructions"
                        disabled={selectedReviewLocked || requirementReviewing === 'revision'}
                        placeholder="Provide reviewer instructions explaining what must be corrected or resubmitted (optional if findings are selected above, required otherwise)..."
                      />
                    </div>
                  </div>}

                  <details className="border-t border-brand-border py-3">
                    <summary className="cursor-pointer text-sm font-medium text-brand-text">Evidence &amp; check details</summary>
                    <div className="mt-3 min-w-0">
                      <ReviewSnapshot latestSubmission={latestSubmission} complianceResult={latestCompliance} hasEvidence={selectedHasEvidence}
                        canRun={false} hasPriorYearAvailable={hasPriorYearAvailable}
                        isPriorRunning={isPriorRunning} isCheckerRunning={isCheckerRunning}
                        onToggleSelectFinding={selectedReviewLocked || requirementReviewing ? undefined : handleToggleSelectFinding} selectedFindingKeys={citedFindingKeys} isFindingDismissed={isDismissed} />
                      {canReviewScan && hasPriorYearAvailable && <Button className="mt-3" size="sm" variant="outline" loading={isPriorRunning} onClick={() => onRunComplianceCheck?.(latestSubmission.id, { use_prior_year_reference: true })}>Use Prior FY</Button>}
                    </div>
                  </details>
                  <ReviewerDecisionPanel
                    key={`${selectedRequirement.id}:${latestCompliance?.id}`}
                    compact
                    result={latestCompliance}
                    role={userRole}
                    isSubmitting={reviewingComplianceResultId === latestCompliance?.id}
                    onRecord={onRecordComplianceReview}
                  />
                  <DetailsAccordion sections={sections} />
                </div>
              </div>
            </>
          ) : (
            <section className="mx-auto w-full max-w-2xl space-y-5 py-8">
              <div className="text-center">
                <FileText className="mx-auto mb-3 h-8 w-8 text-brand-text-muted" />
                <h3 className="text-base font-semibold text-brand-text">No document uploaded</h3>
                <p className="mt-2 text-sm text-brand-text-muted">Upload or record documentary evidence to begin review.</p>
                {!uploadAllowed && <p className="mt-2 text-sm text-brand-text-muted">Uploading is unavailable for this requirement.</p>}
              </div>
              <DetailsAccordion sections={sections.map(section => section.id === 'add_version' ? { ...section, label: 'Upload document', defaultOpen: true } : section)} />
            </section>
          )}
        </div>
      )}
    </Modal>

    <StatusChangeModal
      open={statusChangeModalOpen}
      onClose={() => setStatusChangeModalOpen(false)}
      requirement={selectedRequirement}
      userRole={userRole}
      onSubmit={handleStatusChangeSubmit}
    />
  </>
  )
}
