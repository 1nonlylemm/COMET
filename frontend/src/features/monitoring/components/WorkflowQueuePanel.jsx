import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, ClipboardList, ShieldCheck, Undo2 } from 'lucide-react'
import { Button, DataTable, FeedbackToast, GlassPanel, InlineAlert, KpiCard, Modal, PageHeader } from '../../../components'
import { badgeClassForTone } from '../../../lib/statusStyles'
import { isAdmin, isPlainStaff, isSystemAdmin } from '../../../lib/auth'
import * as monitoringApi from '../api/monitoringApi'
import { RequirementEvidenceList } from './RequirementEvidenceList'
import { WorkflowActionBar } from './WorkflowActionBar'
import { workflowStatusLabel, workflowStatusTone } from './workflowStatus'
import { ReReviewDeficiencyChecklist } from './ReReviewDeficiencyChecklist'
import { DeficiencyAlertBanner } from './DeficiencyAlertBanner'

const DOCUMENT_CATEGORY_LABELS = {
  monthly_progress_report: 'Monthly Progress Report',
  form_3: 'Form 3',
  project_exception_report: 'Project Exception Report',
  apm_template: 'APM Template',
  non_infra_monitoring_evidence: 'Non-Infra Monitoring Template',
  signed_distribution_list: 'Signed Distribution List',
  acknowledgement_receipt: 'Acknowledgement Receipt',
  beneficiary_tracking_record: 'Beneficiary Tracking Record',
  turnover_photos: 'Turnover Photos',
  delivery_invoice: 'Delivery Invoice',
  final_swa: 'Final Statement of Work Accomplished (Final SWA)',
  final_inspection_report: 'Final Inspection Report (FIR)',
  certificate_of_final_acceptance: 'Certificate of Final Acceptance (COFA)',
  final_sord: 'Final Statement of Receipts and Disbursements (Final SORD)',
  proof_of_return_of_funds: 'Proof of Return of Funds / Reversion',
}

function documentCategoryLabel(value) {
  return DOCUMENT_CATEGORY_LABELS[value] || value
}

/**
 * Verification & Validation Queue: a consolidated worklist over the shared
 * document workflow (Monthly Progress Report, Form 3, Project Exception
 * Report), reusing Phase 1 workflow transition endpoints. Staff see items
 * awaiting their verification/staff-approval; Provincial Admin sees items
 * pending their global approval. Both roles can see returned items.
 */
export function WorkflowQueuePanel() {
  const restricted = isSystemAdmin()
  const staff = isPlainStaff()
  const admin = isAdmin()
  const [view, setView] = useState(staff ? 'staff' : 'provincial')
  const [items, setItems] = useState([])
  const [counts, setCounts] = useState({ staff: 0, provincial: 0, returned: 0 })
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [activeItem, setActiveItem] = useState(null)
  const [activeDetail, setActiveDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [evidenceRefreshKey, setEvidenceRefreshKey] = useState(0)

  const load = useCallback(async (roleView) => {
    if (restricted) return
    setLoading(true)
    setError('')
    try {
      const [queueResponse, countsResponse] = await Promise.all([
        monitoringApi.listWorkflowQueue({ role_view: roleView }),
        monitoringApi.getWorkflowQueueCounts(),
      ])
      setItems(queueResponse.data || [])
      setCounts(countsResponse.data || { staff: 0, provincial: 0, returned: 0 })
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to load the V&V Queue.')
    } finally {
      setLoading(false)
    }
  }, [restricted])

  useEffect(() => {
    load(view)
  }, [load, view])

  const runAction = async (requirementId, action, extra) => {
    setBusyId(requirementId)
    setError('')
    setMessage('')
    try {
      if (action === 'verify') await monitoringApi.verifyRequirementWorkflow(requirementId)
      if (action === 'staff_approve') await monitoringApi.staffApproveRequirementWorkflow(requirementId)
      if (action === 'provincial_approve') await monitoringApi.provincialApproveRequirementWorkflow(requirementId)
      if (action === 'return') {
        const payload = typeof extra === 'object' && extra !== null ? extra : { reason: extra }
        await monitoringApi.returnRequirementWorkflow(requirementId, payload)
      }
      setMessage('Workflow updated successfully.')
      await load(view)
      if (activeItem?.id === requirementId) {
        await openDetail({ ...activeItem })
      }
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to update the workflow status.')
    } finally {
      setBusyId(null)
    }
  }

  const openDetail = async (row) => {
    setActiveItem(row)
    setActiveDetail(null)
    setDetailError('')
    setDetailLoading(true)
    try {
      const response = await monitoringApi.getRequirementWorkflow(row.id)
      setActiveDetail(response.data)
      setEvidenceRefreshKey((current) => current + 1)
    } catch (requestError) {
      setDetailError(requestError.response?.data?.message || 'Unable to load the record details.')
    } finally {
      setDetailLoading(false)
    }
  }

  const closeDetail = () => {
    setActiveItem(null)
    setActiveDetail(null)
    setDetailError('')
  }

  const columns = [
    {
      key: 'project_name',
      label: 'Project / LGU',
      render: (row) => (
        <div>
          <div className="font-medium text-brand-text">{row.project_name || '—'}</div>
          <div className="text-xs text-brand-text-muted">{row.lgu_name || '—'}</div>
        </div>
      ),
    },
    {
      key: 'document_category',
      label: 'Document',
      render: (row) => {
        const categoryLabel = documentCategoryLabel(row.document_category)
        const showRecordSubtext = row.requirement_name && row.requirement_name !== categoryLabel
        return (
          <div>
            <div className="flex items-center gap-1.5 font-medium text-brand-text">
              {categoryLabel}
              {row.has_data_discrepancy && (
                <AlertTriangle
                  className="h-4 w-4 text-amber-500"
                  aria-label="QAAR Discrepancy"
                  title="QAAR and self-reported figures differ by points"
                />
              )}
              {row.has_privilege_override && (
                <AlertTriangle
                  className="h-4 w-4 text-amber-500"
                  aria-label="Privilege Override"
                  title="Approved without required technical privileges"
                />
              )}
            </div>
            {showRecordSubtext && (
              <div className="text-xs text-brand-text-muted">{row.requirement_name}</div>
            )}
          </div>
        )
      },
    },
    {
      key: 'workflow_status',
      label: 'Status',
      render: (row) => (
        <span className={badgeClassForTone(workflowStatusTone(row.workflow_status))}>
          {workflowStatusLabel(row.workflow_status)}
        </span>
      ),
    },
    {
      key: 'actions',
      label: '',
      render: (row) => {
        const busy = busyId === row.id
        return (
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => openDetail(row)}>
              Open
            </Button>
            {view === 'staff' && (staff || admin) && (row.workflow_status === 'submitted' || row.workflow_status === 'resubmitted') && (
              <Button size="sm" variant="outline" icon={ShieldCheck} loading={busy} onClick={() => runAction(row.id, 'verify')}>
                Verify
              </Button>
            )}
            {view === 'staff' && (staff || admin) && row.workflow_status === 'under_verification' && (
              <Button size="sm" icon={CheckCircle2} loading={busy} onClick={() => runAction(row.id, 'staff_approve')}>
                Staff Approve
              </Button>
            )}
            {view === 'provincial' && admin && (
              <Button size="sm" icon={CheckCircle2} loading={busy} onClick={() => runAction(row.id, 'provincial_approve')}>
                Provincial Approve
              </Button>
            )}
            {view === 'returned' && (
              <span className="inline-flex items-center gap-1 text-xs text-brand-text-muted">
                <Undo2 className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden="true" />
                Awaiting resubmission
              </span>
            )}
          </div>
        )
      },
    },
  ]

  const detailRequirement = activeDetail?.requirement

  if (restricted) {
    return (
      <div>
        <PageHeader
          title="Verification &amp; Validation Queue"
          description="Consolidated worklist for Monthly Progress Reports, Form 3 requests, Project Exception Reports, and other shared-workflow documents awaiting review."
        />
        <InlineAlert type="info">
          System Administrators do not have operational access to the V&amp;V Queue. This workspace is limited to Staff and Provincial Admin roles.
        </InlineAlert>
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title="Verification &amp; Validation Queue"
        description="Consolidated worklist for Monthly Progress Reports, Form 3 requests, and Project Exception Reports awaiting review, mirroring the existing Staff verify and Provincial Admin approve stages."
        actions={<Button variant="outline" size="sm" onClick={() => load(view)}>Refresh</Button>}
      />

      <FeedbackToast type="success" message={message} onDismiss={() => setMessage('')} />
      <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>{error}</InlineAlert>

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <KpiCard title="Staff Queue" value={counts.staff} subtitle="awaiting verification" icon={ShieldCheck} color="blue" />
        <KpiCard title="Provincial Queue" value={counts.provincial} subtitle="awaiting approval" icon={CheckCircle2} color="amber" />
        <KpiCard title="Returned" value={counts.returned} subtitle="awaiting resubmission" icon={Undo2} color="red" />
      </div>

      <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="V&amp;V Queue views">
        {[
          { value: 'staff', label: 'Staff Queue', visible: staff || admin },
          { value: 'provincial', label: 'Provincial Queue', visible: admin || staff },
          { value: 'returned', label: 'Returned', visible: true },
        ].filter((tab) => tab.visible).map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={view === tab.value}
            onClick={() => setView(tab.value)}
            className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              view === tab.value
                ? 'bg-brand-primary/10 text-brand-primary ring-1 ring-brand-primary/30'
                : 'text-brand-text-muted hover:bg-brand-surface hover:text-brand-text'
            }`}
          >
            <ClipboardList className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden="true" />
            {tab.label}
          </button>
        ))}
      </div>

      <GlassPanel noPadding>
        <DataTable
          columns={columns}
          data={items}
          keyField="id"
          isLoading={loading}
          emptyMessage="No items are currently in this queue."
          caption="V&V Queue items"
          density="compact"
        />
      </GlassPanel>

      <Modal
        open={Boolean(activeItem)}
        title={activeItem ? `${documentCategoryLabel(activeItem.document_category)} — ${activeItem.project_name || ''}` : ''}
        onClose={closeDetail}
        size="lg"
        footer={activeItem && (
          <WorkflowActionBar
            workflowStatus={activeItem.workflow_status}
            hasEvidence
            requirementName={activeItem.requirement_name}
            disabled={busyId === activeItem.id}
            onVerify={() => runAction(activeItem.id, 'verify')}
            onStaffApprove={() => runAction(activeItem.id, 'staff_approve')}
            onProvincialApprove={() => runAction(activeItem.id, 'provincial_approve')}
            onReturn={(payload) => runAction(activeItem.id, 'return', payload)}
          />
        )}
      >
        {activeItem && (
          <div className="space-y-4">
            {detailError && (
              <InlineAlert type="error" onDismiss={() => setDetailError('')}>{detailError}</InlineAlert>
            )}
            {detailRequirement?.workflow_return_reason && (!activeDetail?.deficiencies || activeDetail.deficiencies.length === 0) && (
              <InlineAlert type="warning" title="Returned for revision">
                {detailRequirement.workflow_return_reason}
              </InlineAlert>
            )}

            {activeDetail?.deficiencies?.length > 0 && (
              <div>
                {(isPlainStaff() || isAdmin()) && (activeItem.workflow_status === 'under_verification' || activeItem.workflow_status === 'resubmitted') ? (
                  <ReReviewDeficiencyChecklist
                    deficiencies={activeDetail.deficiencies}
                    onResolve={async (deficiencyId, payload) => {
                      await monitoringApi.resolveRequirementDeficiency(activeItem.id, deficiencyId, payload)
                      await openDetail({ ...activeItem })
                      await load(view)
                    }}
                  />
                ) : (
                  <DeficiencyAlertBanner
                    requirement={detailRequirement || activeItem}
                    deficiencies={activeDetail.deficiencies}
                  />
                )}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-brand-text-muted">LGU</dt><dd className="font-medium text-brand-text">{activeItem.lgu_name || '—'}</dd></div>
              <div><dt className="text-brand-text-muted">Workflow Status</dt><dd className="font-medium text-brand-text">{workflowStatusLabel(activeItem.workflow_status)}</dd></div>
              <div className="col-span-2"><dt className="text-brand-text-muted">Record</dt><dd className="text-brand-text">{activeItem.requirement_name}</dd></div>
            </div>
            {detailLoading ? (
              <p className="text-sm text-brand-text-muted">Loading record history...</p>
            ) : activeDetail?.transitions?.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand-text-muted">Workflow history</p>
                <ul className="space-y-1.5 rounded-md border border-brand-border bg-brand-surface px-3 py-2 text-xs">
                  {activeDetail.transitions.map((transition) => (
                    <li key={transition.id} className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-brand-text">
                        {transition.actor_name || 'System'} — {workflowStatusLabel(transition.to_status)}
                      </span>
                      <span className="text-brand-text-muted">
                        {transition.created_at ? new Date(transition.created_at).toLocaleDateString('en-PH', { year: 'numeric', month: 'short', day: 'numeric' }) : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <RequirementEvidenceList requirementId={activeItem.id} refreshKey={evidenceRefreshKey} />
          </div>
        )}
      </Modal>
    </div>
  )
}
