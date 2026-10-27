import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FileUp, Plus } from 'lucide-react'
import { Button, DataTable, FeedbackToast, FormField, GlassPanel, InlineAlert, Modal, PageHeader } from '../../../components'
import { isSystemAdmin } from '../../../lib/auth'
import { badgeClassForTone } from '../../../lib/statusStyles'
import * as monitoringApi from '../api/monitoringApi'
import { RequirementEvidenceList } from './RequirementEvidenceList'
import { WorkflowActionBar } from './WorkflowActionBar'
import { workflowStatusLabel, workflowStatusTone } from './workflowStatus'

const EXCEPTION_CATEGORY_OPTIONS = [
  { value: '', label: 'Select a category' },
  { value: 'force_majeure', label: 'Force Majeure' },
  { value: 'right_of_way', label: 'Right-of-Way Issue' },
  { value: 'procurement_delay', label: 'Procurement Delay' },
  { value: 'weather', label: 'Weather Disturbance' },
  { value: 'funding_delay', label: 'Funding Delay' },
  { value: 'design_change', label: 'Design Change' },
  { value: 'scope_change', label: 'Scope Change' },
  { value: 'other', label: 'Other' },
]

const EMPTY_FORM = {
  project_id: '',
  reporting_period: new Date().toISOString().slice(0, 7),
  exception_category: '',
  description: '',
}

export function ProjectExceptionPanel({ projects }) {
  const restricted = isSystemAdmin()
  const readOnly = false
  const [items, setItems] = useState([])
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
      const response = await monitoringApi.listExceptionReports({ per_page: 100 })
      setItems(response.data || [])
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to load Project Exception Reports.')
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
        await monitoringApi.createExceptionReport(formData)
        setMessage('Project Exception Report saved with attached document.')
      } else {
        await monitoringApi.createExceptionReport({ ...form, project_id: Number(form.project_id) })
        setMessage('Project Exception Report saved as draft.')
      }
      closeForm()
      await load()
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to save the Project Exception Report.')
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
      formData.append('description', `Project Exception Report for ${activeItem.reporting_period}`)
      await monitoringApi.uploadRequirementEvidence(activeItem.project_requirement_id, formData)
      setMessage('Supporting document uploaded successfully.')
      setEvidenceFile(null)
      setEvidenceRefreshKey((current) => current + 1)
      await load()
      const refreshed = (await monitoringApi.listExceptionReports({ per_page: 100 })).data
        .find((item) => item.id === activeItem.id)
      if (refreshed) setActiveItem(refreshed)
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to upload the supporting document.')
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
      const refreshed = (await monitoringApi.listExceptionReports({ per_page: 100 })).data
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
    { key: 'reporting_period', label: 'Period' },
    {
      key: 'exception_category',
      label: 'Category',
      render: (row) => EXCEPTION_CATEGORY_OPTIONS.find((option) => option.value === row.exception_category)?.label || '—',
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
          title="Project Exception Report"
          description="Document unusual project conditions or deviations for the record. This report is informational only and does not suppress risk tagging or Management Action Report escalation."
        />
        <InlineAlert type="info">
          System Administrators do not have operational access to Project Exception Reports. This workspace is limited to Staff and Provincial Admin roles. (Field Officers have read-only access).
        </InlineAlert>
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title="Project Exception Report"
        description="Document unusual project conditions or deviations for the record. This report is informational only and does not suppress risk tagging or Management Action Report escalation."
        actions={(
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={load}>Refresh</Button>
            {!readOnly && <Button size="sm" icon={Plus} onClick={openCreateForm}>New Exception Report</Button>}
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
          emptyMessage="No Project Exception Reports have been recorded yet."
          caption="Project Exception Reports"
          density="compact"
        />
      </GlassPanel>

      <Modal open={formOpen} title="New Project Exception Report" onClose={closeForm} size="lg">
        <form onSubmit={submitForm} className="space-y-4">
          <InlineAlert type="error" onDismiss={() => setError('')}>{error}</InlineAlert>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <FormField id="per-project" label="Project" required className="md:col-span-2">
              <select
                id="per-project"
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
            <FormField id="per-period" label="Reporting period" required>
              <input
                id="per-period"
                type="month"
                className="input-field"
                value={form.reporting_period}
                onChange={(event) => setForm((current) => ({ ...current, reporting_period: event.target.value }))}
                required
              />
            </FormField>
            <FormField id="per-category" label="Exception category">
              <select
                id="per-category"
                className="input-field"
                value={form.exception_category}
                onChange={(event) => setForm((current) => ({ ...current, exception_category: event.target.value }))}
              >
                {EXCEPTION_CATEGORY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </FormField>
            <FormField id="per-description" label="Description" className="md:col-span-2">
              <textarea
                id="per-description"
                className="input-field min-h-[96px]"
                value={form.description}
                onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
              />
            </FormField>
            <FormField
              id="per-create-file"
              label="Supporting document (optional)"
              hint="Attach initial supporting documentation now, or upload it later from the report details."
              className="md:col-span-2"
            >
              <input
                id="per-create-file"
                type="file"
                aria-label="Supporting document file"
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
        title={activeItem ? `Project Exception Report — ${activeItem.reporting_period}` : ''}
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
              <div><dt className="text-brand-text-muted">Category</dt><dd className="font-medium text-brand-text">{EXCEPTION_CATEGORY_OPTIONS.find((option) => option.value === activeItem.exception_category)?.label || '—'}</dd></div>
              <div><dt className="text-brand-text-muted">Workflow Status</dt><dd className="font-medium text-brand-text">{workflowStatusLabel(activeItem.workflow_status)}</dd></div>
              <div className="col-span-2"><dt className="text-brand-text-muted">Description</dt><dd className="text-brand-text">{activeItem.description || '—'}</dd></div>
            </div>
            {!readOnly && (
              <div className="rounded-md border border-brand-border bg-brand-surface px-4 py-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand-text-muted">Supporting document (optional)</p>
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    type="file"
                    aria-label="Supporting document"
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
