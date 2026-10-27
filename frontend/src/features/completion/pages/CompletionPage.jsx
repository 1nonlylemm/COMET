import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Archive, CheckCircle2, ClipboardCheck, Lock, Search } from 'lucide-react'
import { Button, DataTable, GlassPanel, InlineAlert, KpiCard, Modal, useToast } from '../../../components'
import { isAdmin, isStaff } from '../../../lib/auth'
import { formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import { apiErrorMessage } from '../../../lib/formErrors'
import * as completionApi from '../api/completionApi'
import * as projectApi from '../../projects/api/projectApi'
import { CompletionMatrixPanel } from '../components/CompletionMatrixPanel'
import { getCompletionProgressLabel, isInfrastructureProject } from '../utils/completionProgress'

function formatDate(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleDateString('en-PH', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return value
  }
}

function statusBadge(value, label = 'Verified', { applicable = true } = {}) {
  if (!applicable) {
    return <span className={badgeClassForStatus('not_required')}>N/A</span>
  }
  return value
    ? <span className={badgeClassForStatus('approved')}>{label}</span>
    : <span className={badgeClassForStatus('pending')}>Pending</span>
}

function parseRequiredPercentInput(value, label = 'Physical completion') {
  const text = String(value ?? '').trim()
  if (!text) return { error: `${label} percentage is required.` }
  const parsed = Number(text)
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100) {
    return { error: `${label} must be between 0 and 100.` }
  }
  return { value: parsed }
}

export default function CompletionPage() {
  const [searchParams] = useSearchParams()
  const initialSearch = searchParams.get('search') || ''
  const toast = useToast()
  const [projects, setProjects] = useState([])
  const [meta, setMeta] = useState({ total: 0, page: 1, pages: 1 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState(initialSearch)
  const [page, setPage] = useState(1)
  const [selectedProject, setSelectedProject] = useState(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    physical_completion_pct: 0,
    has_certificate_of_completion: false,
    is_final_swa_applicable: false,
    has_final_swa: false,
    has_annex_j: false,
    punchlist_items_total: '',
    punchlist_items_resolved: '',
    punchlist_notes: '',
    is_vault_ready: false,
    final_approval: false,
  })

  const canEdit = isAdmin() || isStaff()

  const loadProjects = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await completionApi.listCompletionProjects({
        page,
        per_page: 20,
        search: search || undefined,
      })
      setProjects(response.data || [])
      setMeta(response.meta || { total: 0, page: 1, pages: 1 })
    } catch (err) {
      setError(apiErrorMessage(err, 'Unable to load completion projects. Please try again.'))
    } finally {
      setLoading(false)
    }
  }, [page, search])

  useEffect(() => {
    loadProjects()
  }, [loadProjects])

  const openDetail = useCallback(async (projectId) => {
    setDetailOpen(true)
    setDetailLoading(true)
    setDetailError('')
    setSelectedProject(null)
    try {
      const [response, projResponse] = await Promise.all([
        completionApi.getCompletionProject(projectId),
        projectApi.getProject(projectId).catch(() => null),
      ])
      const projData = projResponse?.data || projResponse || {}
      const detail = {
        ...response.data,
        project_kind: response.data?.project_kind || projData.project_kind,
        progress_metric: response.data?.progress_metric || projData.progress_metric,
      }
      setSelectedProject(detail)
      setForm({
        physical_completion_pct: detail.completion?.physical_completion_pct ?? detail.physical_completion_pct ?? 0,
        has_certificate_of_completion: !!detail.completion?.has_certificate_of_completion,
        is_final_swa_applicable: !!detail.completion?.is_final_swa_applicable,
        has_final_swa: !!detail.completion?.has_final_swa,
        has_annex_j: !!detail.completion?.has_annex_j,
        punchlist_items_total: detail.completion?.punchlist_items_total ?? '',
        punchlist_items_resolved: detail.completion?.punchlist_items_resolved ?? '',
        punchlist_notes: detail.completion?.punchlist_notes ?? '',
        is_vault_ready: !!detail.completion?.is_vault_ready,
        final_approval: !!detail.completion?.final_approval_at,
      })
    } catch (error) {
      setDetailError(error.response?.data?.message || 'Unable to load completion document details.')
    } finally {
      setDetailLoading(false)
    }
  }, [])

  useEffect(() => {
    const pid = searchParams.get('project_id')
    if (pid && !detailOpen && !selectedProject) {
      openDetail(Number(pid))
    }
  }, [searchParams, openDetail, detailOpen, selectedProject])

  const closeDetail = () => {
    if (saving) return
    setDetailOpen(false)
    setDetailError('')
  }

  async function handleSave(event) {
    event.preventDefault()
    if (!selectedProject || !canEdit) return

    setDetailError('')
    const progressLabel = getCompletionProgressLabel(selectedProject).replace(' %', '')
    const physicalCompletion = parseRequiredPercentInput(form.physical_completion_pct, progressLabel)
    if (physicalCompletion.error) {
      setDetailError(physicalCompletion.error)
      return
    }

    setSaving(true)
    try {
      const response = await completionApi.updateCompletionProject(selectedProject.project_id, {
        physical_completion_pct: physicalCompletion.value,
        has_certificate_of_completion: form.has_certificate_of_completion,
        is_final_swa_applicable: form.is_final_swa_applicable,
        has_final_swa: form.has_final_swa,
        has_annex_j: form.has_annex_j,
        punchlist_items_total: form.punchlist_items_total === '' ? null : Number(form.punchlist_items_total),
        punchlist_items_resolved: form.punchlist_items_resolved === '' ? null : Number(form.punchlist_items_resolved),
        punchlist_notes: form.punchlist_notes,
        is_vault_ready: form.is_vault_ready,
        final_approval: form.final_approval,
        reopen_reason: (!form.final_approval && (selectedProject.overall_status === 'completed' || selectedProject.completion?.final_approval_at)) ? (form.reopen_reason || form.punchlist_notes || 'Reopened from completion review') : undefined,
      })
      setSelectedProject(response.data)
      await loadProjects()
      setDetailOpen(false)
      toast.success('Completion record saved successfully.')
    } catch (error) {
      setDetailError(error.response?.data?.message || 'Unable to update the completion record.')
    } finally {
      setSaving(false)
    }
  }

  const hasErrorNoData = Boolean(error && projects.length === 0)
  const displayTotal = hasErrorNoData ? '—' : (meta.total || projects.length)
  const vaultReadyCount = hasErrorNoData ? '—' : projects.filter((project) => project.completion?.is_vault_ready).length
  const fullyApprovedCount = hasErrorNoData ? '—' : projects.filter((project) => project.completion?.final_approval_at).length
  const trackedMilestonesCount = hasErrorNoData ? '—' : projects.filter((project) => project.completion?.id).length

  const columns = [
    { key: 'project_name', label: 'Project' },
    { key: 'program', label: 'Program', render: (row) => row.program?.code || row.program?.name || '—' },
    { key: 'lgu', label: 'LGU', render: (row) => row.lgu?.name || '—' },
    { key: 'physical_completion_pct', label: 'Progress', render: (row) => `${row.physical_completion_pct || 0}%` },
    { key: 'certificate', label: 'Certificate', render: (row) => statusBadge(row.completion?.has_certificate_of_completion) },
    {
      key: 'final_swa',
      label: 'Final SWA',
      render: (row) => statusBadge(row.completion?.has_final_swa, 'Verified', {
        applicable: row.completion?.is_final_swa_applicable !== false,
      }),
    },
    { key: 'annex_j', label: 'Annex J', render: (row) => statusBadge(row.completion?.has_annex_j) },
    {
      key: 'actions',
      label: '',
      render: (row) => (
        <Button size="sm" variant="outline" onClick={() => openDetail(row.project_id)}>
          Open
        </Button>
      ),
    },
  ]

  return (
    <div className="animate-fade-in">
      <div className="mb-6">
        <h1 className="page-title">Completion & Reportorial Tracking</h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Track completion documents, punchlist status, final reportorial readiness, and closeout approval.
        </p>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-4">
        <KpiCard title="Completion Projects" value={displayTotal} icon={Archive} color="blue" />
        <KpiCard title="Record Set Ready" value={vaultReadyCount} icon={Lock} color="cyan" />
        <KpiCard title="Final Approval" value={fullyApprovedCount} icon={CheckCircle2} color="emerald" />
        <KpiCard title="Tracked Milestones" value={trackedMilestonesCount} icon={ClipboardCheck} color="amber" />
      </div>

      {error && (
        <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>
          <div className="flex items-center justify-between gap-3">
            <span>{error}</span>
            <Button size="sm" variant="outline" onClick={loadProjects}>
              Retry
            </Button>
          </div>
        </InlineAlert>
      )}

      <div className="mb-4 flex flex-wrap gap-3">
        <form
          onSubmit={(event) => {
            event.preventDefault()
            setPage(1)
            loadProjects()
          }}
          className="flex min-w-[260px] flex-1 gap-2"
        >
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600 dark:text-slate-400" />
            <input
              className="input-field pl-10"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search completion-stage projects"
            />
          </div>
          <Button type="submit" variant="outline" className="self-center">Search</Button>
        </form>
      </div>

      <GlassPanel>
        <DataTable
          columns={columns}
          data={projects}
          keyField="project_id"
          isLoading={loading}
          emptyMessage={error ? 'Unable to load completion projects. Please retry.' : 'No projects are currently in the completion phase.'}
        />

        {meta.pages > 1 && (
          <div className="mt-4 flex items-center justify-center gap-3">
            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>
              Previous
            </Button>
            <span className="text-sm text-brand-text-muted">Page {page} of {meta.pages}</span>
            <Button size="sm" variant="outline" disabled={page >= meta.pages} onClick={() => setPage((current) => current + 1)}>
              Next
            </Button>
          </div>
        )}
      </GlassPanel>

      <Modal
        open={detailOpen}
        title="Completion milestone"
        description="Review closeout documents, punchlist status, and final reportorial readiness for the selected project."
        size="lg"
        onClose={closeDetail}
      >
        {detailLoading ? (
          <div className="text-sm text-slate-400">Loading project detail...</div>
        ) : selectedProject ? (
          <form onSubmit={handleSave} className="space-y-4">
            <InlineAlert type="error" onDismiss={() => setDetailError('')}>
              {detailError}
            </InlineAlert>

            <div className="rounded-lg border border-brand-border bg-brand-surface p-4">
              <div className="text-sm font-semibold text-brand-text">{selectedProject.project_name}</div>
              <div className="mt-1 text-sm text-brand-text-muted">{selectedProject.lgu?.name} · {selectedProject.program?.code || selectedProject.program?.name}</div>
              <div className="mt-2 text-xs text-slate-600 dark:text-slate-400">
                Latest Regional Handoff: {selectedProject.latest_google_drive_push?.push_status ? formatStatus(selectedProject.latest_google_drive_push.push_status) : 'No handoff yet'}
                {selectedProject.latest_google_drive_push?.drive_folder_url ? ` · ${selectedProject.latest_google_drive_push.drive_folder_url}` : ''}
              </div>
            </div>

            <CompletionMatrixPanel projectId={selectedProject.project_id} />

            <div className="border-t border-brand-border pt-4">
              <h3 className="text-sm font-semibold text-brand-text">Additional Closeout Checklist</h3>
              <p className="mt-0.5 text-xs text-brand-text-muted">
                Separate from the Completion Matrix above — these track progress milestones,
                punchlist resolution (for civil works), and record-set readiness required before final approval.
              </p>
            </div>

            <div>
              <label className="label-text">{getCompletionProgressLabel(selectedProject)}</label>
              <input
                type="number"
                min="0"
                max="100"
                step="0.01"
                className="input-field mt-1"
                value={form.physical_completion_pct}
                onChange={(event) => setForm((current) => ({ ...current, physical_completion_pct: event.target.value }))}
                disabled={!canEdit}
                required
              />
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex items-center gap-2 text-sm text-brand-text">
                <input
                  type="checkbox"
                  checked={form.has_certificate_of_completion}
                  onChange={(event) => setForm((current) => ({ ...current, has_certificate_of_completion: event.target.checked }))}
                  disabled={!canEdit}
                />
                Certificate of Completion
                {!isInfrastructureProject(selectedProject) && (
                  <span className="text-xs text-brand-text-muted font-normal">(Civil Works — Not Applicable)</span>
                )}
              </label>
              <label className="flex items-center gap-2 text-sm text-brand-text">
                <input
                  type="checkbox"
                  checked={form.is_final_swa_applicable}
                  onChange={(event) => {
                    const checked = event.target.checked
                    setForm((current) => ({
                      ...current,
                      is_final_swa_applicable: checked,
                      has_final_swa: checked ? current.has_final_swa : false,
                    }))
                  }}
                  disabled={!canEdit}
                />
                Final SWA applies to this project
                {!isInfrastructureProject(selectedProject) && (
                  <span className="text-xs text-brand-text-muted font-normal">(Civil Works — Not Applicable)</span>
                )}
              </label>
              <label className="flex items-center gap-2 text-sm text-brand-text">
                <input
                  type="checkbox"
                  checked={form.has_final_swa}
                  onChange={(event) => setForm((current) => ({ ...current, has_final_swa: event.target.checked }))}
                  disabled={!canEdit || !form.is_final_swa_applicable}
                />
                Final SWA verified
              </label>
              <label className="flex items-center gap-2 text-sm text-brand-text">
                <input
                  type="checkbox"
                  checked={form.has_annex_j}
                  onChange={(event) => setForm((current) => ({ ...current, has_annex_j: event.target.checked }))}
                  disabled={!canEdit}
                />
                Annex J / Project Completion Report
              </label>
              <label className="flex items-center gap-2 text-sm text-brand-text">
                <input
                  type="checkbox"
                  checked={form.is_vault_ready}
                  onChange={(event) => setForm((current) => ({ ...current, is_vault_ready: event.target.checked }))}
                  disabled={!canEdit}
                />
                Completion record set is ready
              </label>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="label-text">
                  Punchlist Items
                  {!isInfrastructureProject(selectedProject) && (
                    <span className="ml-1.5 text-xs text-brand-text-muted font-normal">(Civil Works only)</span>
                  )}
                </label>
                <input
                  type="number"
                  min="0"
                  className="input-field mt-1"
                  value={form.punchlist_items_total}
                  onChange={(event) => setForm((current) => ({ ...current, punchlist_items_total: event.target.value }))}
                  disabled={!canEdit}
                />
              </div>
              <div>
                <label className="label-text">
                  Resolved Items
                  {!isInfrastructureProject(selectedProject) && (
                    <span className="ml-1.5 text-xs text-brand-text-muted font-normal">(Civil Works only)</span>
                  )}
                </label>
                <input
                  type="number"
                  min="0"
                  className="input-field mt-1"
                  value={form.punchlist_items_resolved}
                  onChange={(event) => setForm((current) => ({ ...current, punchlist_items_resolved: event.target.value }))}
                  disabled={!canEdit}
                />
              </div>
            </div>

            <div>
              <label className="label-text">Completion Notes</label>
              <textarea
                className="input-field mt-1 min-h-[120px]"
                value={form.punchlist_notes}
                onChange={(event) => setForm((current) => ({ ...current, punchlist_notes: event.target.value }))}
                disabled={!canEdit}
                placeholder="Document remaining punchlist work, reportorial notes, or closeout instructions."
              />
            </div>

            <div>
              <label className="flex items-center gap-2 text-sm text-brand-text">
                <input
                  type="checkbox"
                  checked={form.final_approval}
                  onChange={(event) => setForm((current) => ({ ...current, final_approval: event.target.checked }))}
                  disabled={!canEdit}
                />
                Mark as fully approved for completion
              </label>
              <p className="mt-1 text-xs text-brand-text-muted">
                Blocked until every applicable Completion Matrix document above has an approved submission.
              </p>
            </div>

            <div className="rounded-lg border border-brand-border bg-brand-surface p-4 text-sm text-brand-text">
              <div>Record set locked: {formatDate(selectedProject.completion?.vault_locked_at)}</div>
              <div className="mt-1">Final approval: {formatDate(selectedProject.completion?.final_approval_at)}</div>
            </div>

            {canEdit ? (
              <div className="flex justify-end gap-3 pt-2">
                <Button type="button" variant="outline" onClick={closeDetail} disabled={saving}>
                  Cancel
                </Button>
                <Button type="submit" loading={saving}>
                  Save Completion Record
                </Button>
              </div>
            ) : (
              <div className="rounded-lg border border-brand-border bg-brand-surface px-4 py-3 text-sm text-brand-text-muted">
                Completion milestones are visible here, but only PDMU staff can update them.
              </div>
            )}
          </form>
        ) : detailError ? (
          <InlineAlert type="error" onDismiss={() => setDetailError('')}>
            {detailError}
          </InlineAlert>
        ) : (
          <div className="rounded-lg border border-dashed border-brand-border px-4 py-10 text-center text-sm text-brand-text-muted">
            Select a completion-stage project to review its closeout documents.
          </div>
        )}
      </Modal>
    </div>
  )
}
