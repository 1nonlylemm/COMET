import { useCallback, useEffect, useState } from 'react'
import { FileUp } from 'lucide-react'
import { Button, InlineAlert, Modal } from '../../../components'
import { isAdmin, isFieldOfficer, isPlainStaff } from '../../../lib/auth'
import { badgeClassForTone } from '../../../lib/statusStyles'
import { RequirementEvidenceList } from '../../monitoring/components/RequirementEvidenceList'
import { WorkflowActionBar } from '../../monitoring/components/WorkflowActionBar'
import { workflowStatusLabel, workflowStatusTone } from '../../monitoring/components/workflowStatus'
import * as monitoringApi from '../../monitoring/api/monitoringApi'
import * as completionApi from '../api/completionApi'

const REVIEW_STATUS_LABELS = {
  submitted: { label: 'Awaiting Staff Verification', tone: 'info' },
  resubmitted: { label: 'Awaiting Staff Verification', tone: 'info' },
  under_verification: { label: 'Under Staff Verification', tone: 'warning' },
  staff_approved: { label: 'Awaiting Provincial Approval', tone: 'warning' },
  pending_provincial_approval: { label: 'Awaiting Provincial Approval', tone: 'warning' },
  approved: { label: 'Verified', tone: 'success' },
}

function effectiveWorkflowStatus(row) {
  if (!row) return 'draft'
  if (row.status === 'compliant' || row.workflow_status === 'approved') {
    return 'approved'
  }
  return row.workflow_status || 'draft'
}

function reviewStatusBadge(row) {
  if (row.workflow_return_reason) {
    return <span className={badgeClassForTone('danger')} title={row.workflow_return_reason}>Returned for Revision</span>
  }
  if (row.status === 'compliant' || row.workflow_status === 'approved') {
    return <span className={badgeClassForTone('success')}>Verified</span>
  }
  const entry = REVIEW_STATUS_LABELS[row.workflow_status]
  if (!entry) {
    return <span className={badgeClassForTone('neutral')}>Not Yet Submitted</span>
  }
  return <span className={badgeClassForTone(entry.tone)}>{entry.label}</span>
}

function applicabilityBadge(applicability) {
  if (applicability === 'not_applicable') {
    return <span className={badgeClassForTone('neutral')}>Not Applicable</span>
  }
  if (applicability === 'pending_confirmation') {
    return <span className={badgeClassForTone('warning')}>Confirm Applicability</span>
  }
  return <span className={badgeClassForTone('info')}>Required</span>
}

/**
 * Phase 2C Completion Matrix -- extends the existing Completion page with
 * one compact row per closeout document (Final SWA, FIR, COFA, Final
 * SORD, Proof of Return of Funds). Reuses the same evidence upload,
 * evidence preview/download, and workflow action components already used
 * by the Phase 2A/2B monitoring panels, so reviewers get the identical
 * upload -> submit -> verify -> approve/return experience they already
 * know from those panels.
 */
export function CompletionMatrixPanel({ projectId }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [activeRow, setActiveRow] = useState(null)
  const [evidenceFile, setEvidenceFile] = useState(null)
  const [uploadingEvidence, setUploadingEvidence] = useState(false)
  const [evidenceRefreshKey, setEvidenceRefreshKey] = useState(0)
  const [evidenceCount, setEvidenceCount] = useState(0)
  const [workflowBusy, setWorkflowBusy] = useState(false)
  const [applicabilityChoice, setApplicabilityChoice] = useState('required')
  const [applicabilityReason, setApplicabilityReason] = useState('')
  const [applicabilitySaving, setApplicabilitySaving] = useState(false)
  const [returnedAmount, setReturnedAmount] = useState('')
  const [receiptNumber, setReceiptNumber] = useState('')
  const [metadataSaving, setMetadataSaving] = useState(false)

  const canReview = isAdmin() || isPlainStaff()
  const fieldOfficer = isFieldOfficer()

  const load = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    setError('')
    try {
      const response = await completionApi.listCompletionDocuments(projectId)
      setRows(response.data || [])
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to load the Completion Matrix.')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

  const openRow = (row) => {
    setActiveRow(row)
    setEvidenceFile(null)
    setEvidenceCount(0)
    setApplicabilityChoice(row.applicability === 'not_applicable' ? 'not_applicable' : 'required')
    setApplicabilityReason(row.applicability_reason || '')
    setReturnedAmount(row.returned_amount != null ? String(row.returned_amount) : '')
    setReceiptNumber(row.receipt_number || '')
    setError('')
    setMessage('')
  }

  const refreshActiveRow = async () => {
    const response = await completionApi.listCompletionDocuments(projectId)
    setRows(response.data || [])
    const refreshed = (response.data || []).find((item) => item.document_type === activeRow?.document_type)
    if (refreshed) {
      setActiveRow(refreshed)
      setReturnedAmount(refreshed.returned_amount != null ? String(refreshed.returned_amount) : '')
      setReceiptNumber(refreshed.receipt_number || '')
    }
    return refreshed
  }

  const handleUploadEvidence = async () => {
    if (!activeRow || !evidenceFile) return
    setUploadingEvidence(true)
    setError('')
    try {
      const formData = new FormData()
      formData.append('file', evidenceFile)
      formData.append('source', 'field_upload')
      formData.append('description', `${activeRow.document_label} evidence`)
      await monitoringApi.uploadRequirementEvidence(activeRow.project_requirement_id, formData)
      setMessage('Evidence uploaded successfully.')
      setEvidenceFile(null)
      setEvidenceRefreshKey((current) => current + 1)
      await refreshActiveRow()
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to upload evidence.')
    } finally {
      setUploadingEvidence(false)
    }
  }

  const runWorkflowAction = async (action, extra) => {
    if (!activeRow) return
    setWorkflowBusy(true)
    setError('')
    setMessage('')
    try {
      const requirementId = activeRow.project_requirement_id
      if (action === 'submit') await monitoringApi.submitRequirementWorkflow(requirementId)
      if (action === 'verify') await monitoringApi.verifyRequirementWorkflow(requirementId)
      if (action === 'staff_approve') await monitoringApi.staffApproveRequirementWorkflow(requirementId)
      if (action === 'provincial_approve') await monitoringApi.provincialApproveRequirementWorkflow(requirementId)
      if (action === 'return') {
        const payload = typeof extra === 'object' && extra !== null ? extra : { reason: extra }
        await monitoringApi.returnRequirementWorkflow(requirementId, payload)
      }
      setMessage('Workflow updated successfully.')
      await refreshActiveRow()
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to update the workflow status.')
    } finally {
      setWorkflowBusy(false)
    }
  }

  const saveApplicability = async () => {
    if (!activeRow) return
    if (applicabilityChoice === 'not_applicable' && !applicabilityReason.trim()) {
      setError('A reason is required when marking this document as not applicable.')
      return
    }
    setApplicabilitySaving(true)
    setError('')
    setMessage('')
    try {
      await completionApi.updateCompletionDocumentApplicability(projectId, activeRow.document_type, {
        applicability: applicabilityChoice,
        reason: applicabilityReason.trim() || undefined,
      })
      setMessage('Applicability updated successfully.')
      await refreshActiveRow()
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to update applicability.')
    } finally {
      setApplicabilitySaving(false)
    }
  }

  const saveMetadata = async () => {
    if (!activeRow) return
    setMetadataSaving(true)
    setError('')
    setMessage('')
    try {
      const parsedAmount = returnedAmount.trim() === '' ? null : Number(returnedAmount)
      if (parsedAmount !== null && (!Number.isFinite(parsedAmount) || parsedAmount < 0)) {
        setError('Returned amount must be a non-negative number.')
        setMetadataSaving(false)
        return
      }
      await completionApi.updateCompletionDocumentMetadata(projectId, activeRow.document_type, {
        returned_amount: parsedAmount,
        receipt_number: receiptNumber.trim() || null,
      })
      setMessage('Document details saved successfully.')
      await refreshActiveRow()
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to update document details.')
    } finally {
      setMetadataSaving(false)
    }
  }

  if (!projectId) return null

  return (
    <div className="rounded-lg border border-brand-border">
      <div className="border-b border-brand-border px-4 py-3">
        <h3 className="text-sm font-semibold text-brand-text">Completion Matrix</h3>
        <p className="mt-0.5 text-xs text-brand-text-muted">
          Final closeout documents required before this project can be marked fully approved for completion.
        </p>
      </div>

      {error && !activeRow && (
        <div className="px-4 pt-3">
          <InlineAlert type="error" onDismiss={() => setError('')}>{error}</InlineAlert>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-brand-border text-left text-xs uppercase tracking-wide text-brand-text-muted">
              <th className="px-4 py-2 font-medium">Requirement</th>
              <th className="px-4 py-2 font-medium">Required</th>
              <th className="px-4 py-2 font-medium">Submission status</th>
              <th className="px-4 py-2 font-medium">Review status</th>
              <th className="px-4 py-2 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-sm text-brand-text-muted">
                  Loading Completion Matrix...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-sm text-brand-text-muted">
                  No closeout documents found for this project.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.document_type} className="border-b border-brand-border last:border-0">
                  <td className="px-4 py-2.5 font-medium text-brand-text">{row.document_label}</td>
                  <td className="px-4 py-2.5">{applicabilityBadge(row.applicability)}</td>
                  <td className="px-4 py-2.5">
                    {row.applicability === 'not_applicable' ? (
                      <span className="text-brand-text-muted">—</span>
                    ) : (
                      <span className={badgeClassForTone(workflowStatusTone(effectiveWorkflowStatus(row)))}>
                        {workflowStatusLabel(effectiveWorkflowStatus(row))}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {row.applicability === 'not_applicable' ? (
                      <span className="text-brand-text-muted">—</span>
                    ) : (
                      reviewStatusBadge(row)
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Button size="sm" variant="outline" onClick={() => openRow(row)}>
                      Open
                    </Button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Modal
        open={!!activeRow}
        title={activeRow ? activeRow.document_label : ''}
        onClose={() => setActiveRow(null)}
        size="lg"
        footer={activeRow && activeRow.applicability !== 'not_applicable' && (
          <WorkflowActionBar
            workflowStatus={effectiveWorkflowStatus(activeRow)}
            hasEvidence={evidenceCount > 0 || effectiveWorkflowStatus(activeRow) !== 'draft'}
            disabled={workflowBusy}
            onSubmit={() => runWorkflowAction('submit')}
            onVerify={() => runWorkflowAction('verify')}
            onStaffApprove={() => runWorkflowAction('staff_approve')}
            onProvincialApprove={() => runWorkflowAction('provincial_approve')}
            onReturn={(reason) => runWorkflowAction('return', reason)}
          />
        )}
      >
        {activeRow && (
          <div className="space-y-4">
            <InlineAlert type="error" onDismiss={() => setError('')}>{error}</InlineAlert>
            <InlineAlert type="success" onDismiss={() => setMessage('')}>{message}</InlineAlert>

            {activeRow.workflow_return_reason && (
              <InlineAlert type="warning" title="Returned for revision">
                {activeRow.workflow_return_reason}
              </InlineAlert>
            )}

            {activeRow.is_applicability_configurable && (
              <div className="rounded-md border border-brand-border bg-brand-surface px-4 py-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand-text-muted">
                  Applicability
                </p>
                <p className="mb-2 text-xs text-brand-text-muted">
                  The PDMU Manual does not define a fixed rule for when this document applies. Confirm whether
                  this project has unspent funds requiring proof of return, or mark it not applicable.
                </p>
                {canReview ? (
                  <div className="space-y-2">
                    <div className="flex flex-wrap gap-3 text-sm">
                      <label className="flex items-center gap-1.5">
                        <input
                          type="radio"
                          name="applicability"
                          checked={applicabilityChoice === 'required'}
                          onChange={() => setApplicabilityChoice('required')}
                        />
                        Required (unspent funds exist)
                      </label>
                      <label className="flex items-center gap-1.5">
                        <input
                          type="radio"
                          name="applicability"
                          checked={applicabilityChoice === 'not_applicable'}
                          onChange={() => setApplicabilityChoice('not_applicable')}
                        />
                        Not applicable (no unspent funds)
                      </label>
                    </div>
                    {applicabilityChoice === 'not_applicable' && (
                      <textarea
                        className="input-field min-h-[64px] w-full"
                        placeholder="Reason (required) -- e.g. full disbursement confirmed against Final SORD."
                        value={applicabilityReason}
                        onChange={(event) => setApplicabilityReason(event.target.value)}
                      />
                    )}
                    <Button size="sm" loading={applicabilitySaving} onClick={saveApplicability}>
                      Save Applicability
                    </Button>
                  </div>
                ) : (
                  <p className="text-sm text-brand-text">
                    Current state: {applicabilityBadge(activeRow.applicability)}
                    {activeRow.applicability_reason ? ` — ${activeRow.applicability_reason}` : ''}
                  </p>
                )}
              </div>
            )}

            {activeRow.document_type === 'proof_of_return_of_funds' && activeRow.applicability !== 'not_applicable' && (
              <div className="rounded-md border border-brand-border bg-brand-surface px-4 py-3">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-brand-text-muted">
                  Return of Funds Details (Optional)
                </p>
                <p className="mb-3 text-xs text-brand-text-muted">
                  Record the unutilized funds amount and official receipt or deposit reference number if funds were reverted.
                </p>
                {(canReview || fieldOfficer) ? (
                  <div className="space-y-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <label className="block text-xs font-medium text-brand-text mb-1">
                          Returned Amount (PHP)
                        </label>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          placeholder="e.g. 2000000.00"
                          className="input-field w-full text-sm"
                          value={returnedAmount}
                          onChange={(event) => setReturnedAmount(event.target.value)}
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-brand-text mb-1">
                          Receipt / Reference Number
                        </label>
                        <input
                          type="text"
                          placeholder="e.g. BTr-OR-2026-08942"
                          className="input-field w-full text-sm"
                          value={receiptNumber}
                          onChange={(event) => setReceiptNumber(event.target.value)}
                        />
                      </div>
                    </div>
                    <Button size="sm" loading={metadataSaving} onClick={saveMetadata}>
                      Save Return Details
                    </Button>
                  </div>
                ) : (
                  <div className="text-sm text-brand-text">
                    <p>Returned Amount: {activeRow.returned_amount != null ? `PHP ${Number(activeRow.returned_amount).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : 'Not recorded'}</p>
                    <p className="mt-1">Receipt Number: {activeRow.receipt_number || 'Not recorded'}</p>
                  </div>
                )}
              </div>
            )}

            {activeRow.applicability === 'not_applicable' ? (
              <InlineAlert type="info">
                This document has been marked not applicable for this project.
                {activeRow.applicability_reason ? ` Reason: ${activeRow.applicability_reason}` : ''}
              </InlineAlert>
            ) : (
              <>
                {fieldOfficer && (
                  <div className="rounded-md border border-brand-border bg-brand-surface px-4 py-3">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand-text-muted">
                      Upload document
                    </p>
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        type="file"
                        aria-label="Evidence file"
                        onChange={(event) => setEvidenceFile(event.target.files?.[0] || null)}
                        className="text-sm text-brand-text-muted"
                      />
                      <Button
                        size="sm"
                        variant="outline"
                        icon={FileUp}
                        loading={uploadingEvidence}
                        disabled={!evidenceFile}
                        onClick={handleUploadEvidence}
                      >
                        Upload
                      </Button>
                    </div>
                  </div>
                )}
                <RequirementEvidenceList
                  requirementId={activeRow.project_requirement_id}
                  refreshKey={evidenceRefreshKey}
                  onFileCountChange={setEvidenceCount}
                />
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
