import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Download, FileUp, Plus, Users } from 'lucide-react'
import { Button, DataTable, FeedbackToast, FormField, GlassPanel, InlineAlert, Modal, PageHeader } from '../../../components'
import { isSystemAdmin } from '../../../lib/auth'
import { badgeClassForTone } from '../../../lib/statusStyles'
import * as monitoringApi from '../api/monitoringApi'
import { RequirementEvidenceList } from './RequirementEvidenceList'
import { WorkflowActionBar } from './WorkflowActionBar'
import { workflowStatusLabel, workflowStatusTone } from './workflowStatus'

const EVIDENCE_TYPE_OPTIONS = [
  { value: '', label: 'Select an evidence type' },
  { value: 'signed_distribution_list', label: 'Signed Distribution List' },
  { value: 'acknowledgement_receipt', label: 'Acknowledgement Receipt' },
  { value: 'beneficiary_tracking_record', label: 'Beneficiary Tracking Record' },
  { value: 'turnover_photos', label: 'Turnover Photos' },
  { value: 'delivery_invoice', label: 'Delivery Invoice' },
]

const EMPTY_FORM = {
  project_id: '',
  evidence_type: '',
  appendix_reference: '',
  beneficiary_count: '',
  distribution_date: '',
  description: '',
}

function evidenceTypeLabel(value) {
  return EVIDENCE_TYPE_OPTIONS.find((option) => option.value === value)?.label || value
}

export function BeneficiaryEvidencePanel({ projects }) {
  const restricted = isSystemAdmin()
  const readOnly = false
  const [items, setItems] = useState([])
  const [appendixTemplates, setAppendixTemplates] = useState([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [createFile, setCreateFile] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [activeItem, setActiveItem] = useState(null)
  const [evidenceFile, setEvidenceFile] = useState(null)
  const [uploadingEvidence, setUploadingEvidence] = useState(false)
  const [evidenceRefreshKey, setEvidenceRefreshKey] = useState(0)
  const [evidenceCount, setEvidenceCount] = useState(0)
  const [workflowBusy, setWorkflowBusy] = useState(false)

  const submittingRef = useRef(false)
  const uploadingEvidenceRef = useRef(false)
  const workflowBusyRef = useRef(false)

  const load = useCallback(async () => {
    if (restricted) return
    setLoading(true)
    setError('')
    try {
      const [response, tplRes] = await Promise.all([
        monitoringApi.listBeneficiaryEvidenceRecords({ per_page: 100 }),
        monitoringApi.listAppendixTemplates().catch(() => ({ data: [] })),
      ])
      setItems(response.data || [])
      setAppendixTemplates(tplRes.data || [])
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to load beneficiary evidence records.')
    } finally {
      setLoading(false)
    }
  }, [restricted])

  useEffect(() => {
    load()
  }, [load])

  const projectOptions = useMemo(
    () => projects.filter((project) => project.current_phase !== 'pre_implementation'),
    [projects],
  )

  const selectedProject = useMemo(
    () => projects.find((project) => String(project.id) === String(form.project_id)),
    [projects, form.project_id],
  )

  const availableAppendices = useMemo(() => {
    if (!selectedProject?.project_kind) return appendixTemplates
    return appendixTemplates.filter((tpl) => {
      const kinds = tpl.applicable_kinds || tpl.applicable_project_kinds || []
      return !kinds.length || kinds.includes(selectedProject.project_kind)
    })
  }, [appendixTemplates, selectedProject])

  const handleDownloadAppendix = async (appendixRef) => {
    if (!appendixRef) return
    const match = appendixRef.match(/\d+/)
    if (!match) return
    const num = parseInt(match[0], 10)
    try {
      const res = await monitoringApi.downloadAppendixTemplate(num)
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      const dispo = res.headers?.['content-disposition'] || ''
      const nameMatch = dispo.match(/filename=(?:["']?)([^"';\n]+)(?:["']?)/)
      link.download = nameMatch ? nameMatch[1] : `${appendixRef}.xlsx`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      setTimeout(() => window.URL.revokeObjectURL(url), 1500)
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to download the appendix template.')
    }
  }

  const openCreateForm = () => {
    setForm(EMPTY_FORM)
    setCreateFile(null)
    setError('')
    setMessage('')
    setFormOpen(true)
  }

  const closeForm = () => {
    setFormOpen(false)
    setForm(EMPTY_FORM)
    setCreateFile(null)
    setError('')
  }

  const submitForm = async (event) => {
    event.preventDefault()
    setError('')
    setMessage('')
    if (!form.project_id) {
      setError('Select a project before continuing.')
      return
    }
    if (!form.evidence_type) {
      setError('Select an evidence type before continuing.')
      return
    }
    if (submittingRef.current) return
    submittingRef.current = true
    setSubmitting(true)
    try {
      if (createFile) {
        const formData = new FormData()
        Object.entries(form).forEach(([key, val]) => {
          if (val !== '' && val !== null && val !== undefined) {
            formData.append(key, val)
          }
        })
        formData.append('file', createFile)
        await monitoringApi.createBeneficiaryEvidenceRecord(formData)
        setMessage('Beneficiary evidence record saved with attached evidence.')
      } else {
        await monitoringApi.createBeneficiaryEvidenceRecord({
          ...form,
          project_id: Number(form.project_id),
          beneficiary_count: form.beneficiary_count === '' ? null : Number(form.beneficiary_count),
          appendix_reference: form.appendix_reference || null,
        })
        setMessage('Beneficiary evidence record saved as draft. Upload the supporting file, then submit for verification.')
      }
      closeForm()
      await load()
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to save the beneficiary evidence record.')
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  const handleUploadEvidence = async () => {
    if (!activeItem || !evidenceFile || uploadingEvidenceRef.current) return
    uploadingEvidenceRef.current = true
    setUploadingEvidence(true)
    setError('')
    try {
      const formData = new FormData()
      formData.append('file', evidenceFile)
      formData.append('source', 'field_upload')
      formData.append('description', `${evidenceTypeLabel(activeItem.evidence_type)} evidence`)
      await monitoringApi.uploadRequirementEvidence(activeItem.project_requirement_id, formData)
      setMessage('Evidence uploaded successfully.')
      setEvidenceFile(null)
      setEvidenceRefreshKey((current) => current + 1)
      await load()
      const refreshed = (await monitoringApi.listBeneficiaryEvidenceRecords({ per_page: 100 })).data
        .find((item) => item.id === activeItem.id)
      if (refreshed) setActiveItem(refreshed)
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to upload evidence.')
    } finally {
      uploadingEvidenceRef.current = false
      setUploadingEvidence(false)
    }
  }

  const runWorkflowAction = async (action, extra) => {
    if (!activeItem || workflowBusyRef.current) return
    workflowBusyRef.current = true
    setWorkflowBusy(true)
    setError('')
    setMessage('')
    try {
      const requirementId = activeItem.project_requirement_id
      if (action === 'submit') await monitoringApi.submitRequirementWorkflow(requirementId)
      if (action === 'verify') await monitoringApi.verifyRequirementWorkflow(requirementId)
      if (action === 'staff_approve') await monitoringApi.staffApproveRequirementWorkflow(requirementId)
      if (action === 'provincial_approve') await monitoringApi.provincialApproveRequirementWorkflow(requirementId)
      if (action === 'return') {
        const payload = typeof extra === 'object' && extra !== null ? extra : { reason: extra }
        await monitoringApi.returnRequirementWorkflow(requirementId, payload)
      }
      setMessage('Workflow updated successfully.')
      const refreshed = (await monitoringApi.listBeneficiaryEvidenceRecords({ per_page: 100 })).data
      setItems(refreshed)
      setActiveItem(refreshed.find((item) => item.id === activeItem.id) || null)
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to update the workflow status.')
    } finally {
      workflowBusyRef.current = false
      setWorkflowBusy(false)
    }
  }

  const columns = [
    { key: 'project_id', label: 'Project', render: (row) => projects.find((project) => project.id === row.project_id)?.project_name || `Project #${row.project_id}` },
    { key: 'evidence_type', label: 'Evidence Type', render: (row) => evidenceTypeLabel(row.evidence_type) },
    {
      key: 'appendix_reference',
      label: 'Appendix',
      render: (row) => {
        if (!row.appendix_reference) return <span className="text-brand-text-muted">—</span>
        return (
          <div className="flex items-center gap-1.5">
            <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-semibold bg-brand-surface-muted text-brand-text">
              {row.appendix_reference}
            </span>
            <button
              type="button"
              className="text-brand-text-muted hover:text-brand-primary p-0.5 rounded transition-colors"
              title={`Download blank ${row.appendix_reference}`}
              onClick={(e) => {
                e.stopPropagation()
                handleDownloadAppendix(row.appendix_reference)
              }}
            >
              <Download className="h-3.5 w-3.5" />
            </button>
          </div>
        )
      },
    },
    {
      key: 'beneficiary_count',
      label: 'Beneficiaries',
      render: (row) => (
        row.beneficiary_count === null || row.beneficiary_count === undefined
          ? <span className="text-brand-text-muted">—</span>
          : <span className="inline-flex items-center gap-1"><Users className="h-3.5 w-3.5 text-brand-text-muted" strokeWidth={1.8} aria-hidden="true" />{row.beneficiary_count}</span>
      ),
    },
    { key: 'distribution_date', label: 'Distribution Date', render: (row) => row.distribution_date || '—' },
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
      render: (row) => (
        <Button size="sm" variant="outline" onClick={() => { setActiveItem(row); setEvidenceFile(null); setEvidenceCount(0); setError(''); setMessage('') }}>
          Open
        </Button>
      ),
    },
  ]

  if (restricted) {
    return (
      <div>
        <PageHeader
          title="Beneficiary Records &amp; Evidence"
          description="Track Signed Distribution Lists, Acknowledgement Receipts, Beneficiary Tracking Records, Turnover Photos, and Delivery Invoices for Non-Infrastructure and direct assistance projects."
        />
        <InlineAlert type="info">
          System Administrators do not have operational access to beneficiary records. This workspace is limited to Staff and Provincial Admin roles. (Field Officers have read-only access).
        </InlineAlert>
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title="Beneficiary Records &amp; Evidence"
        description="Track Signed Distribution Lists, Acknowledgement Receipts, Beneficiary Tracking Records, Turnover Photos, and Delivery Invoices for Non-Infrastructure and direct assistance projects."
        actions={(
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={load}>Refresh</Button>
            {!readOnly && <Button size="sm" icon={Plus} onClick={openCreateForm}>New Record</Button>}
          </div>
        )}
      />

      <FeedbackToast type="success" message={message} onDismiss={() => setMessage('')} />
      <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>{error}</InlineAlert>

      <GlassPanel noPadding>
        <DataTable
          columns={columns}
          data={items}
          keyField="id"
          isLoading={loading}
          emptyMessage="No beneficiary evidence records have been recorded yet."
          caption="Beneficiary evidence records"
          density="compact"
        />
      </GlassPanel>

      <Modal open={formOpen} title="New Beneficiary Evidence Record" onClose={closeForm} size="lg">
        <form onSubmit={submitForm} className="space-y-4">
          <InlineAlert type="error" onDismiss={() => setError('')}>{error}</InlineAlert>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <FormField id="bev-project" label="Project" required className="md:col-span-2">
              <select
                id="bev-project"
                className="input-field"
                value={form.project_id}
                onChange={(event) => setForm((current) => ({ ...current, project_id: event.target.value }))}
                required
              >
                <option value="">Select a project</option>
                {projectOptions.map((project) => (
                  <option key={project.id} value={project.id}>{project.project_name}</option>
                ))}
              </select>
            </FormField>
            <FormField id="bev-evidence-type" label="Evidence type" required>
              <select
                id="bev-evidence-type"
                className="input-field"
                value={form.evidence_type}
                onChange={(event) => setForm((current) => ({ ...current, evidence_type: event.target.value }))}
                required
              >
                {EVIDENCE_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </FormField>
            <FormField id="bev-count" label="Beneficiary count">
              <input
                id="bev-count"
                type="number"
                min="0"
                className="input-field"
                value={form.beneficiary_count}
                onChange={(event) => setForm((current) => ({ ...current, beneficiary_count: event.target.value }))}
              />
            </FormField>
            <FormField id="bev-date" label="Distribution date" className="md:col-span-2">
              <input
                id="bev-date"
                type="date"
                className="input-field"
                value={form.distribution_date}
                onChange={(event) => setForm((current) => ({ ...current, distribution_date: event.target.value }))}
              />
            </FormField>
            <FormField
              id="bev-appendix"
              label="Official Appendix Template (optional)"
              hint={selectedProject?.project_kind ? `Filtered to templates for ${selectedProject.project_kind}` : 'Omnibus Guidelines monitoring template'}
              className="md:col-span-2"
            >
              <div className="flex gap-2">
                <select
                  id="bev-appendix"
                  className="input-field flex-1"
                  value={form.appendix_reference}
                  onChange={(event) => setForm((current) => ({ ...current, appendix_reference: event.target.value }))}
                >
                  <option value="">No specific appendix</option>
                  {availableAppendices.map((tpl) => (
                    <option key={tpl.appendix_reference} value={tpl.appendix_reference}>
                      {tpl.appendix_reference}: {tpl.title}
                    </option>
                  ))}
                </select>
                {form.appendix_reference && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    icon={Download}
                    onClick={() => handleDownloadAppendix(form.appendix_reference)}
                    title="Download blank template"
                  >
                    Download Blank
                  </Button>
                )}
              </div>
            </FormField>
            <FormField id="bev-description" label="Description" className="md:col-span-2">
              <textarea
                id="bev-description"
                className="input-field min-h-[80px]"
                placeholder="e.g. Distribution of livelihood cash assistance to 500 farmers in Barangay San Isidro."
                value={form.description}
                onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
              />
            </FormField>
            <FormField
              id="bec-create-file"
              label="Supporting evidence (optional)"
              hint="Attach initial documentary evidence now, or upload it later from the record details."
              className="md:col-span-2"
            >
              <input
                id="bec-create-file"
                type="file"
                aria-label="Supporting evidence file"
                className="input-field text-sm text-brand-text-muted"
                onChange={(event) => setCreateFile(event.target.files?.[0] || null)}
              />
            </FormField>
          </div>
          <div className="flex justify-end gap-2 border-t border-brand-border pt-3">
            <Button type="button" variant="ghost" onClick={closeForm}>Cancel</Button>
            <Button type="submit" loading={submitting}>Save Draft</Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={!!activeItem}
        title={activeItem ? evidenceTypeLabel(activeItem.evidence_type) : ''}
        onClose={() => setActiveItem(null)}
        size="lg"
        footer={!readOnly && activeItem && (
          <WorkflowActionBar
            workflowStatus={activeItem.workflow_status}
            hasEvidence={evidenceCount > 0 || activeItem.workflow_status !== 'draft'}
            disabled={workflowBusy}
            onSubmit={() => runWorkflowAction('submit')}
            onVerify={() => runWorkflowAction('verify')}
            onStaffApprove={() => runWorkflowAction('staff_approve')}
            onProvincialApprove={() => runWorkflowAction('provincial_approve')}
            onReturn={(reason) => runWorkflowAction('return', reason)}
          />
        )}
      >
        {activeItem && (
          <div className="space-y-4">
            {activeItem.workflow_return_reason && (
              <InlineAlert type="warning" title="Returned for revision">
                {activeItem.workflow_return_reason}
              </InlineAlert>
            )}
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-brand-text-muted">Beneficiary Count</dt><dd className="font-medium text-brand-text">{activeItem.beneficiary_count ?? '—'}</dd></div>
              <div><dt className="text-brand-text-muted">Distribution Date</dt><dd className="font-medium text-brand-text">{activeItem.distribution_date || '—'}</dd></div>
              <div><dt className="text-brand-text-muted">Workflow Status</dt><dd className="font-medium text-brand-text">{workflowStatusLabel(activeItem.workflow_status)}</dd></div>
              <div className="col-span-2"><dt className="text-brand-text-muted">Description</dt><dd className="text-brand-text">{activeItem.description || '—'}</dd></div>
            </div>
            {activeItem.appendix_reference && (
              <div className="flex items-center justify-between rounded-md border border-brand-border bg-brand-surface-muted px-4 py-2.5">
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wider text-brand-text-muted">Tagged Template</dt>
                  <dd className="text-sm font-semibold text-brand-text">{activeItem.appendix_reference}</dd>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  icon={Download}
                  onClick={() => handleDownloadAppendix(activeItem.appendix_reference)}
                >
                  Download Blank Template
                </Button>
              </div>
            )}
            {!readOnly && (
              <div className="rounded-md border border-brand-border bg-brand-surface px-4 py-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand-text-muted">Supporting evidence</p>
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
              requirementId={activeItem.project_requirement_id}
              refreshKey={evidenceRefreshKey}
              onFileCountChange={setEvidenceCount}
            />
          </div>
        )}
      </Modal>
    </div>
  )
}
