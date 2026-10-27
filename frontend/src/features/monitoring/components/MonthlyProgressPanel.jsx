import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, Calculator, FileUp, Plus, TrendingDown } from 'lucide-react'
import { AmountInput, Button, DataTable, FeedbackToast, FormField, GlassPanel, InlineAlert, Modal, PageHeader } from '../../../components'
import { isSystemAdmin } from '../../../lib/auth'
import { formatCurrency } from '../../../lib/formatters'
import { badgeClassForTone } from '../../../lib/statusStyles'

import * as monitoringApi from '../api/monitoringApi'
import { RequirementEvidenceList } from './RequirementEvidenceList'
import { WorkflowActionBar } from './WorkflowActionBar'
import { riskLevelLabel, riskLevelTone, workflowStatusLabel, workflowStatusTone } from './workflowStatus'

const EMPTY_FORM = {
  project_id: '',
  reporting_period: new Date().toISOString().slice(0, 7),
  assessment_date: new Date().toISOString().slice(0, 10),
  physical_accomplishment_pct: '',
  target_to_date_pct: '',
  actual_to_date_pct: '',
  budget_utilization_pct: '',
  financial_progress_amount: '',
}

function formatPercent(value) {
  if (value === null || value === undefined) return '—'
  return `${value}%`
}

function VarianceBadge({ variance }) {
  if (variance === null || variance === undefined) return <span className="text-brand-text-muted">—</span>
  const behind = variance > 0
  return (
    <span className={`inline-flex items-center gap-1 text-sm font-medium ${behind ? 'text-red-700 dark:text-red-300' : 'text-emerald-700 dark:text-emerald-300'}`}>
      {behind && <TrendingDown className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden="true" />}
      {behind ? `${variance}% behind` : `${Math.abs(variance)}% ahead/on target`}
    </span>
  )
}

function RiskBadge({ level }) {
  return <span className={badgeClassForTone(riskLevelTone(level))}>{riskLevelLabel(level)}</span>
}

export function MonthlyProgressPanel({ projects }) {
  const restricted = isSystemAdmin()
  const readOnly = false
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [createFile, setCreateFile] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [activeReport, setActiveReport] = useState(null)
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
      const response = await monitoringApi.listMonthlyProgressReports({ per_page: 100 })
      setReports(response.data || [])
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to load Monthly Progress Reports.')
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

  const computedVariance = useMemo(() => {
    const target = form.target_to_date_pct === '' ? null : Number(form.target_to_date_pct)
    const actual = form.actual_to_date_pct === '' ? null : Number(form.actual_to_date_pct)
    if (target === null || actual === null || Number.isNaN(target) || Number.isNaN(actual)) return null
    return Number((target - actual).toFixed(2))
  }, [form.target_to_date_pct, form.actual_to_date_pct])

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
      const cleanForm = {
        ...form,
        financial_progress_amount:
          form.financial_progress_amount !== '' && form.financial_progress_amount !== null && form.financial_progress_amount !== undefined
            ? Number(String(form.financial_progress_amount).replace(/,/g, ''))
            : null,
      }
      if (createFile) {
        const formData = new FormData()
        Object.entries(cleanForm).forEach(([key, val]) => {
          if (val !== '' && val !== null && val !== undefined) {
            formData.append(key, val)
          }
        })
        formData.append('file', createFile)
        await monitoringApi.createMonthlyProgressReport(formData)
        setMessage('Monthly Progress Report saved with attached evidence.')
      } else {
        await monitoringApi.createMonthlyProgressReport({
          ...cleanForm,
          project_id: Number(form.project_id),
        })
        setMessage('Monthly Progress Report saved as draft. Upload evidence, then submit for verification.')
      }
      closeForm()
      await load()
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to save the Monthly Progress Report.')
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  const handleUploadEvidence = async () => {
    if (!activeReport || !evidenceFile || uploadingEvidenceRef.current) return
    uploadingEvidenceRef.current = true
    setUploadingEvidence(true)
    setError('')
    try {
      const formData = new FormData()
      formData.append('file', evidenceFile)
      formData.append('source', 'field_upload')
      formData.append('description', `Monthly Progress Report evidence for ${activeReport.reporting_period}`)
      await monitoringApi.uploadRequirementEvidence(activeReport.project_requirement_id, formData)
      setMessage('Evidence uploaded successfully.')
      setEvidenceFile(null)
      setEvidenceRefreshKey((current) => current + 1)
      await load()
      const refreshed = (await monitoringApi.listMonthlyProgressReports({ per_page: 100 })).data
        .find((item) => item.id === activeReport.id)
      if (refreshed) setActiveReport(refreshed)
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to upload evidence.')
    } finally {
      uploadingEvidenceRef.current = false
      setUploadingEvidence(false)
    }
  }

  const runWorkflowAction = async (action, extra) => {
    if (!activeReport || workflowBusyRef.current) return
    workflowBusyRef.current = true
    setWorkflowBusy(true)
    setError('')
    setMessage('')
    try {
      const requirementId = activeReport.project_requirement_id
      if (action === 'submit') await monitoringApi.submitRequirementWorkflow(requirementId)
      if (action === 'verify') await monitoringApi.verifyRequirementWorkflow(requirementId)
      if (action === 'staff_approve') await monitoringApi.staffApproveRequirementWorkflow(requirementId)
      if (action === 'provincial_approve') await monitoringApi.provincialApproveRequirementWorkflow(requirementId)
      if (action === 'return') {
        const payload = typeof extra === 'object' && extra !== null ? extra : { reason: extra }
        await monitoringApi.returnRequirementWorkflow(requirementId, payload)
      }
      setMessage('Workflow updated successfully.')
      const refreshed = (await monitoringApi.listMonthlyProgressReports({ per_page: 100 })).data
      setReports(refreshed)
      setActiveReport(refreshed.find((item) => item.id === activeReport.id) || null)
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
    { key: 'target_to_date_pct', label: 'Target to Date', render: (row) => formatPercent(row.target_to_date_pct) },
    { key: 'actual_to_date_pct', label: 'Actual to Date', render: (row) => formatPercent(row.actual_to_date_pct) },
    { key: 'variance_pct', label: 'Variance / Slippage', render: (row) => <VarianceBadge variance={row.variance_pct} /> },
    { key: 'risk_level', label: 'Risk', render: (row) => <RiskBadge level={row.risk_level} /> },
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
        <Button size="sm" variant="outline" onClick={() => { setActiveReport(row); setEvidenceFile(null); setEvidenceCount(0); setError(''); setMessage('') }}>
          Open
        </Button>
      ),
    },
  ]

  if (restricted) {
    return (
      <div>
        <PageHeader
          title="Monthly Progress Report"
          description="Record monthly physical and financial progress for any project type. Target to Date, Actual to Date, and the resulting Variance and Risk Level are calculated by the system."
        />
        <InlineAlert type="info">
          System Administrators do not have operational access to Monthly Progress Reports. This workspace is limited to Staff and Provincial Admin roles. (Field Officers have read-only access).
        </InlineAlert>
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title="Monthly Progress Report"
        description="Record monthly physical and financial progress for any project type. Target to Date, Actual to Date, and the resulting Variance and Risk Level are calculated by the system."
        actions={(
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={load}>Refresh</Button>
            {!readOnly && <Button size="sm" icon={Plus} onClick={openCreateForm}>New Report</Button>}
          </div>
        )}
      />

      <FeedbackToast type="success" message={message} onDismiss={() => setMessage('')} />
      <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>{error}</InlineAlert>

      <GlassPanel noPadding>
        <DataTable
          columns={columns}
          data={reports}
          keyField="id"
          isLoading={loading}
          emptyMessage="No Monthly Progress Reports have been recorded yet."
          caption="Monthly Progress Reports"
          density="compact"
        />
      </GlassPanel>

      <Modal open={formOpen} title="New Monthly Progress Report" onClose={closeForm} size="lg">
        <form onSubmit={submitForm} className="space-y-4">
          <InlineAlert type="error" onDismiss={() => setError('')}>{error}</InlineAlert>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <FormField id="mpr-project" label="Project" required className="md:col-span-2">
              <select
                id="mpr-project"
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
            <FormField id="mpr-period" label="Reporting period" required>
              <input
                id="mpr-period"
                type="month"
                className="input-field"
                value={form.reporting_period}
                onChange={(event) => setForm((current) => ({ ...current, reporting_period: event.target.value }))}
                required
              />
            </FormField>
            <FormField id="mpr-assessment-date" label="Assessment date">
              <input
                id="mpr-assessment-date"
                type="date"
                className="input-field"
                value={form.assessment_date}
                onChange={(event) => setForm((current) => ({ ...current, assessment_date: event.target.value }))}
              />
            </FormField>
            <FormField id="mpr-physical" label="Physical accomplishment %">
              <input
                id="mpr-physical"
                type="number"
                min="0"
                max="100"
                step="0.01"
                className="input-field"
                value={form.physical_accomplishment_pct}
                onChange={(event) => setForm((current) => ({ ...current, physical_accomplishment_pct: event.target.value }))}
              />
            </FormField>
            <FormField id="mpr-budget" label="Budget utilization %">
              <input
                id="mpr-budget"
                type="number"
                min="0"
                max="100"
                step="0.01"
                className="input-field"
                value={form.budget_utilization_pct}
                onChange={(event) => setForm((current) => ({ ...current, budget_utilization_pct: event.target.value }))}
              />
            </FormField>
            <FormField id="mpr-target" label="Target to Date %" required hint="Planned cumulative accomplishment expected as of this period.">
              <input
                id="mpr-target"
                type="number"
                min="0"
                max="100"
                step="0.01"
                className="input-field"
                value={form.target_to_date_pct}
                onChange={(event) => setForm((current) => ({ ...current, target_to_date_pct: event.target.value }))}
              />
            </FormField>
            <FormField id="mpr-actual" label="Actual to Date %" required hint="Cumulative accomplishment actually completed as of this period.">
              <input
                id="mpr-actual"
                type="number"
                min="0"
                max="100"
                step="0.01"
                className="input-field"
                value={form.actual_to_date_pct}
                onChange={(event) => setForm((current) => ({ ...current, actual_to_date_pct: event.target.value }))}
              />
            </FormField>
            <FormField id="mpr-financial" label="Financial progress amount">
              <AmountInput
                id="mpr-financial"
                className="input-field"
                placeholder="0.00"
                value={form.financial_progress_amount}
                onChange={(event) => setForm((current) => ({ ...current, financial_progress_amount: event.target.value }))}
              />
            </FormField>
            <FormField
              id="mpr-create-file"
              label="Supporting evidence (optional)"
              hint="Attach an initial documentary evidence file now, or upload it later from the report details."
              className="md:col-span-2"
            >
              <input
                id="mpr-create-file"
                type="file"
                aria-label="Supporting evidence file"
                className="input-field text-sm text-brand-text-muted"
                onChange={(event) => setCreateFile(event.target.files?.[0] || null)}
              />
            </FormField>
          </div>

          <div className="rounded-md border border-dashed border-brand-border bg-brand-surface px-4 py-3">
            <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-brand-text-muted">
              <Calculator className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden="true" />
              Calculated by the system on save
            </div>
            <p className="text-sm text-brand-text">
              Variance (Target - Actual): {computedVariance === null ? 'Enter Target and Actual to preview' : `${computedVariance}%`}
            </p>
            <p className="mt-1 text-xs text-brand-text-muted">
              Risk level is derived from the configured slippage thresholds after saving.
            </p>
          </div>

          <div className="flex justify-end gap-2 border-t border-brand-border pt-3">
            <Button type="button" variant="ghost" onClick={closeForm}>Cancel</Button>
            <Button type="submit" loading={submitting}>Save Draft</Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={!!activeReport}
        title={activeReport ? `Monthly Progress Report — ${activeReport.reporting_period}` : ''}
        onClose={() => setActiveReport(null)}
        size="lg"
        footer={!readOnly && activeReport && (
          <WorkflowActionBar
            workflowStatus={activeReport.workflow_status}
            hasEvidence={evidenceCount > 0 || activeReport.workflow_status !== 'draft'}
            disabled={workflowBusy}
            onSubmit={() => runWorkflowAction('submit')}
            onVerify={() => runWorkflowAction('verify')}
            onStaffApprove={() => runWorkflowAction('staff_approve')}
            onProvincialApprove={() => runWorkflowAction('provincial_approve')}
            onReturn={(reason) => runWorkflowAction('return', reason)}
          />
        )}
      >
        {activeReport && (
          <div className="space-y-4">
            {activeReport.workflow_return_reason && (
              <InlineAlert type="warning" title="Returned for revision">
                {activeReport.workflow_return_reason}
              </InlineAlert>
            )}
            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
              <div><dt className="text-brand-text-muted">Target to Date</dt><dd className="font-medium text-brand-text">{formatPercent(activeReport.target_to_date_pct)}</dd></div>
              <div><dt className="text-brand-text-muted">Actual to Date</dt><dd className="font-medium text-brand-text">{formatPercent(activeReport.actual_to_date_pct)}</dd></div>
              <div><dt className="text-brand-text-muted">Variance</dt><dd><VarianceBadge variance={activeReport.variance_pct} /></dd></div>
              <div><dt className="text-brand-text-muted">Risk Level</dt><dd><RiskBadge level={activeReport.risk_level} /></dd></div>
              <div><dt className="text-brand-text-muted">Budget Utilization</dt><dd className="font-medium text-brand-text">{formatPercent(activeReport.budget_utilization_pct)}</dd></div>
              <div><dt className="text-brand-text-muted">Financial Progress</dt><dd className="font-medium text-brand-text">{activeReport.financial_progress_amount !== null && activeReport.financial_progress_amount !== undefined && activeReport.financial_progress_amount !== '' ? formatCurrency(activeReport.financial_progress_amount) : '—'}</dd></div>
              <div><dt className="text-brand-text-muted">Workflow Status</dt><dd className="font-medium text-brand-text">{workflowStatusLabel(activeReport.workflow_status)}</dd></div>
            </div>
            {activeReport.risk_level && ['major', 'severe'].includes(activeReport.risk_level) && (
              <InlineAlert type="warning" title="Elevated risk">
                <span className="inline-flex items-center gap-1">
                  <AlertTriangle className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden="true" />
                  This report may trigger a Management Action Report unless an approved Form 3 justification covers this period.
                </span>
              </InlineAlert>
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
              requirementId={activeReport.project_requirement_id}
              refreshKey={evidenceRefreshKey}
              onFileCountChange={setEvidenceCount}
            />
          </div>
        )}
      </Modal>
    </div>
  )
}
