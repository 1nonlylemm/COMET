import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Download, FileUp, Plus } from 'lucide-react'
import { Button, DataTable, FeedbackToast, FormField, GlassPanel, InlineAlert, Modal, PageHeader } from '../../../components'
import { isSystemAdmin } from '../../../lib/auth'
import { badgeClassForTone } from '../../../lib/statusStyles'
import * as monitoringApi from '../api/monitoringApi'
import { RequirementEvidenceList } from './RequirementEvidenceList'
import { WorkflowActionBar } from './WorkflowActionBar'
import { workflowStatusLabel, workflowStatusTone } from './workflowStatus'

const TEMPLATE_TYPE_OPTIONS = [
  { value: '', label: 'Select a template type' },
  { value: 'apm_template', label: 'APM Template' },
  { value: 'infrastructure_monitoring_template', label: 'Infrastructure Monitoring Template' },
  { value: 'non_infrastructure_monitoring_template', label: 'Non-Infrastructure Monitoring Template' },
  { value: 'other_monitoring_template', label: 'Other Applicable Monitoring Template' },
]

const SPECIFICATIONS_OPTIONS = [
  { value: '', label: 'Not yet assessed' },
  { value: 'true', label: 'Meets specifications' },
  { value: 'false', label: 'Does not meet specifications' },
]

const EMPTY_FORM = {
  project_id: '',
  template_type: '',
  appendix_reference: '',
  reporting_period: new Date().toISOString().slice(0, 7),
  items_verified_summary: '',
  specifications_met: '',
  remarks: '',
}

export function NonInfraMonitoringPanel({ projects }) {
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
        monitoringApi.listNonInfraMonitoringRecords({ per_page: 100 }),
        monitoringApi.listAppendixTemplates().catch(() => ({ data: [] })),
      ])
      setItems(response.data || [])
      setAppendixTemplates(tplRes.data || [])
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to load Non-Infra Monitoring records.')
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
    if (!form.template_type) {
      setError('Select a template type before continuing.')
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
        await monitoringApi.createNonInfraMonitoringRecord(formData)
        setMessage('Monitoring template saved with attached evidence.')
      } else {
        await monitoringApi.createNonInfraMonitoringRecord({
          ...form,
          project_id: Number(form.project_id),
          specifications_met: form.specifications_met === '' ? null : form.specifications_met === 'true',
          appendix_reference: form.appendix_reference || null,
        })
        setMessage('Monitoring template saved as draft. Upload supporting evidence, then submit for verification.')
      }
      closeForm()
      await load()
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to save the monitoring template.')
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
      formData.append('description', `Non-Infra Monitoring evidence (${activeItem.template_type})`)
      await monitoringApi.uploadRequirementEvidence(activeItem.project_requirement_id, formData)
      setMessage('Evidence uploaded successfully.')
      setEvidenceFile(null)
      setEvidenceRefreshKey((current) => current + 1)
      await load()
      const refreshed = (await monitoringApi.listNonInfraMonitoringRecords({ per_page: 100 })).data
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
      const refreshed = (await monitoringApi.listNonInfraMonitoringRecords({ per_page: 100 })).data
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
    {
      key: 'template_type',
      label: 'Template Type',
      render: (row) => TEMPLATE_TYPE_OPTIONS.find((option) => option.value === row.template_type)?.label || '—',
    },
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
    { key: 'reporting_period', label: 'Period', render: (row) => row.reporting_period || '—' },
    {
      key: 'specifications_met',
      label: 'Specifications',
      render: (row) => {
        if (row.specifications_met === null || row.specifications_met === undefined) return <span className="text-brand-text-muted">Not assessed</span>
        return (
          <span className={badgeClassForTone(row.specifications_met ? 'success' : 'danger')}>
            {row.specifications_met ? 'Meets specifications' : 'Does not meet specifications'}
          </span>
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
          title="Non-Infra Monitoring / APM Template"
          description="Submit APM and monitoring templates for Non-Infrastructure and other applicable projects, verifying that delivered goods, equipment, or assistance meet the required specifications."
        />
        <InlineAlert type="info">
          System Administrators do not have operational access to monitoring templates. This workspace is limited to Staff and Provincial Admin roles. (Field Officers have read-only access).
        </InlineAlert>
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title="Non-Infra Monitoring / APM Template"
        description="Submit APM and monitoring templates for Non-Infrastructure and other applicable projects, verifying that delivered goods, equipment, or assistance meet the required specifications."
        actions={(
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={load}>Refresh</Button>
            {!readOnly && <Button size="sm" icon={Plus} onClick={openCreateForm}>New Template</Button>}
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
          emptyMessage="No Non-Infra Monitoring templates have been recorded yet."
          caption="Non-Infra Monitoring / APM Template records"
          density="compact"
        />
      </GlassPanel>

      <Modal open={formOpen} title="New Monitoring Template" onClose={closeForm} size="lg">
        <form onSubmit={submitForm} className="space-y-4">
          <InlineAlert type="error" onDismiss={() => setError('')}>{error}</InlineAlert>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <FormField id="nim-project" label="Project" required className="md:col-span-2">
              <select
                id="nim-project"
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
            <FormField id="nim-template-type" label="Template type" required>
              <select
                id="nim-template-type"
                className="input-field"
                value={form.template_type}
                onChange={(event) => setForm((current) => ({ ...current, template_type: event.target.value }))}
                required
              >
                {TEMPLATE_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </FormField>
            <FormField id="nim-period" label="Reporting period">
              <input
                id="nim-period"
                type="month"
                className="input-field"
                value={form.reporting_period}
                onChange={(event) => setForm((current) => ({ ...current, reporting_period: event.target.value }))}
              />
            </FormField>
            <FormField
              id="nim-appendix"
              label="Official Appendix Template (optional)"
              hint={selectedProject?.project_kind ? `Filtered to templates for ${selectedProject.project_kind}` : 'Omnibus Guidelines monitoring template'}
              className="md:col-span-2"
            >
              <div className="flex gap-2">
                <select
                  id="nim-appendix"
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
            <FormField id="nim-specifications" label="Specifications assessment" className="md:col-span-2">
              <select
                id="nim-specifications"
                className="input-field"
                value={form.specifications_met}
                onChange={(event) => setForm((current) => ({ ...current, specifications_met: event.target.value }))}
              >
                {SPECIFICATIONS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </FormField>
            <FormField id="nim-items-verified" label="Items verified summary" className="md:col-span-2">
              <textarea
                id="nim-items-verified"
                className="input-field min-h-[80px]"
                placeholder="e.g. Rescue vehicle delivered, engine specifications and unit count confirmed against purchase order."
                value={form.items_verified_summary}
                onChange={(event) => setForm((current) => ({ ...current, items_verified_summary: event.target.value }))}
              />
            </FormField>
            <FormField id="nim-remarks" label="Remarks" className="md:col-span-2">
              <textarea
                id="nim-remarks"
                className="input-field min-h-[72px]"
                value={form.remarks}
                onChange={(event) => setForm((current) => ({ ...current, remarks: event.target.value }))}
              />
            </FormField>
            <FormField
              id="nim-create-file"
              label="Supporting evidence (optional)"
              hint="Attach initial documentary evidence now, or upload it later from the record details."
              className="md:col-span-2"
            >
              <input
                id="nim-create-file"
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
        title={activeItem ? `Monitoring Template — ${TEMPLATE_TYPE_OPTIONS.find((option) => option.value === activeItem.template_type)?.label || ''}` : ''}
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
              <div><dt className="text-brand-text-muted">Reporting Period</dt><dd className="font-medium text-brand-text">{activeItem.reporting_period || '—'}</dd></div>
              <div><dt className="text-brand-text-muted">Workflow Status</dt><dd className="font-medium text-brand-text">{workflowStatusLabel(activeItem.workflow_status)}</dd></div>
              <div className="col-span-2"><dt className="text-brand-text-muted">Items Verified</dt><dd className="text-brand-text">{activeItem.items_verified_summary || '—'}</dd></div>
              <div className="col-span-2"><dt className="text-brand-text-muted">Remarks</dt><dd className="text-brand-text">{activeItem.remarks || '—'}</dd></div>
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
