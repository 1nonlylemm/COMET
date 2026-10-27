import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Search, Plus, FolderKanban, CheckCircle2, AlertTriangle, Archive } from 'lucide-react'
import { AmountInput, Button, FormField, InlineAlert, KpiCard, Modal, PageHeader, useToast } from '../../../components'
import { isAdmin, isStaff } from '../../../lib/auth'
import { ROUTES } from '../../../config/routes'
import { apiErrorMessage } from '../../../lib/formErrors'
import * as projectApi from '../api/projectApi'
import * as lguApi from '../../lgus/api/lguApi'
import * as programApi from '../../programs/api/programApi'
import { hasProjectValidationErrors, validateProjectFields } from '../utils/projectValidation'
import { PROJECT_STATUS_FILTERS, PROJECT_STATUS_OPTIONS } from '../constants/projectStatus'
import { ProjectsTable } from '../components/ProjectsTable'

const PHASE_FILTERS = [
  { value: '', label: 'All Phases' },
  { value: 'pre_implementation', label: 'Pre-Implementation' },
  { value: 'implementation', label: 'Implementation' },
  { value: 'completion', label: 'Completion' },
]

const ALL_PROJECT_KIND_OPTIONS = [
  { value: 'infrastructure', label: 'Infrastructure (Civil Works)' },
  { value: 'goods', label: 'Goods / Equipment' },
  { value: 'vehicle', label: 'Motor Vehicles' },
  { value: 'financial_assistance', label: 'Financial / Social Assistance' },
]

const NON_INFRA_PROJECT_KIND_OPTIONS = [
  { value: 'goods', label: 'Goods / Equipment' },
  { value: 'vehicle', label: 'Motor Vehicles' },
  { value: 'financial_assistance', label: 'Financial / Social Assistance' },
]

const INFRA_PROJECT_KIND_OPTIONS = [
  { value: 'infrastructure', label: 'Infrastructure (Civil Works)' },
]


export default function ProjectListPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const toast = useToast()
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)

  const initialSearch = searchParams.get('search') || ''
  const initialPhase = searchParams.get('current_phase') || searchParams.get('phase') || ''
  const initialStatus = searchParams.get('overall_status') || searchParams.get('status') || ''
  const initialLgu = searchParams.get('lgu_id') || ''
  const initialProgram = searchParams.get('program_id') || ''
  const initialPage = Number(searchParams.get('page')) || 1

  const appliedSearch = searchParams.get('search') || ''
  const [search, setSearch] = useState(initialSearch)
  const [filterPhase, setFilterPhase] = useState(initialPhase)
  const [filterStatus, setFilterStatus] = useState(initialStatus)
  const [filterLgu, setFilterLgu] = useState(initialLgu)
  const [filterProgram, setFilterProgram] = useState(initialProgram)
  const [page, setPage] = useState(initialPage)
  const [meta, setMeta] = useState({ total: 0, pages: 1 })
  const [lgus, setLgus] = useState([])
  const [programs, setPrograms] = useState([])
  const [programCycles, setProgramCycles] = useState([])

  useEffect(() => {
    const s = searchParams.get('search') || ''
    const p = searchParams.get('current_phase') || searchParams.get('phase') || ''
    const st = searchParams.get('overall_status') || searchParams.get('status') || ''
    const l = searchParams.get('lgu_id') || ''
    const pr = searchParams.get('program_id') || ''
    const pg = Number(searchParams.get('page')) || 1

    setSearch((prev) => (prev !== s ? s : prev))
    setFilterPhase((prev) => (prev !== p ? p : prev))
    setFilterStatus((prev) => (prev !== st ? st : prev))
    setFilterLgu((prev) => (prev !== l ? l : prev))
    setFilterProgram((prev) => (prev !== pr ? pr : prev))
    setPage((prev) => (prev !== pg ? pg : prev))
  }, [searchParams])

  // Create form state
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({
    lgu_id: '', program_id: '', program_cycle_id: '', project_name: '', source_project_code: '', fiscal_year: new Date().getFullYear(),
    current_phase: 'pre_implementation', overall_status: 'not_yet_started', budget_amount: '',
    target_start_date: '', target_end_date: '', notes: '', project_kind: '',
  })
  const [formError, setFormError] = useState('')
  const [formErrors, setFormErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const fetchData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = { page, per_page: 20 }
      if (appliedSearch) params.search = appliedSearch
      if (filterPhase) params.current_phase = filterPhase
      if (filterStatus) params.overall_status = filterStatus
      if (filterLgu) params.lgu_id = filterLgu
      if (filterProgram) params.program_id = filterProgram
      const res = await projectApi.listProjects(params)
      setProjects(res.data || [])
      if (res.meta) setMeta(res.meta)
    } catch (err) {
      setError(apiErrorMessage(err, 'Unable to load projects. Please try again.'))
    } finally {
      setLoading(false)
    }
  }, [page, appliedSearch, filterPhase, filterStatus, filterLgu, filterProgram])

  useEffect(() => { fetchData() }, [fetchData])

  // Load LGUs and programs for filters and create form
  useEffect(() => {
    Promise.all([
      lguApi.listLgus({ per_page: 200 }).catch(() => ({ data: [] })),
      programApi.listPrograms({ per_page: 200 }).catch(() => ({ data: [] })),
    ]).then(([lguRes, progRes]) => {
      setLgus(lguRes.data || [])
      setPrograms(progRes.data || [])
    })
  }, [])

  useEffect(() => {
    let cancelled = false
    if (!form.program_id) {
      setProgramCycles([])
      setForm((current) => (current.program_cycle_id ? { ...current, program_cycle_id: '' } : current))
      return () => { cancelled = true }
    }

    const fiscalYear = Number(form.fiscal_year)
    const params = Number.isInteger(fiscalYear) ? { fiscal_year: fiscalYear } : {}
    programApi.listProgramCycles(form.program_id, params)
      .then((res) => {
        if (cancelled) return
        const cycles = res.data || []
        setProgramCycles(cycles)
        setForm((current) => {
          if (cycles.length === 0) {
            return current.program_cycle_id ? { ...current, program_cycle_id: '' } : current
          }
          if (cycles.length === 1) {
            const singleCycleId = String(cycles[0].id)
            return current.program_cycle_id === singleCycleId ? current : { ...current, program_cycle_id: singleCycleId }
          }
          const hasValidSelection = cycles.some((cycle) => String(cycle.id) === String(current.program_cycle_id))
          return hasValidSelection ? current : { ...current, program_cycle_id: '' }
        })
      })
      .catch(() => {
        if (!cancelled) {
          setProgramCycles([])
          setForm((current) => (current.program_cycle_id ? { ...current, program_cycle_id: '' } : current))
        }
      })

    return () => { cancelled = true }
  }, [form.program_id, form.fiscal_year])

  const handleCreate = async (e) => {
    e.preventDefault()
    const selectedProgram = programs.find((p) => String(p.id) === String(form.program_id))
    const isProjectKindRequired = Boolean(selectedProgram)
    const validationErrors = validateProjectFields(form, {
      requireCore: true,
      requireProjectKind: isProjectKindRequired,
      requireProjectCode: true,
    })
    if (programCycles.length > 1 && !form.program_cycle_id) {
      validationErrors.program_cycle_id = 'Please select a program cycle.'
    }
    if (hasProjectValidationErrors(validationErrors)) {
      setFormErrors(validationErrors)
      setFormError('Please correct the highlighted fields.')
      return
    }
    setFormErrors({})
    setSubmitting(true)
    try {
      const payload = {
        ...form,
        source_project_code: form.source_project_code.trim(),
        lgu_id: parseInt(form.lgu_id),
        program_id: parseInt(form.program_id),
        program_cycle_id: form.program_cycle_id ? parseInt(form.program_cycle_id) : null,
        fiscal_year: parseInt(form.fiscal_year),
        budget_amount: form.budget_amount ? parseFloat(String(form.budget_amount).replace(/,/g, '')) : null,
        target_start_date: form.target_start_date || null,
        target_end_date: form.target_end_date || null,
        project_kind: form.project_kind || null,
      }
      if (!payload.notes) delete payload.notes
      if (payload.budget_amount === null) delete payload.budget_amount
      if (payload.program_cycle_id === null) delete payload.program_cycle_id
      await projectApi.createProject(payload)
      setShowCreate(false)
      setForm({
        lgu_id: '', program_id: '', program_cycle_id: '', project_name: '', source_project_code: '', fiscal_year: new Date().getFullYear(),
        current_phase: 'pre_implementation', overall_status: 'not_yet_started', budget_amount: '',
        target_start_date: '', target_end_date: '', notes: '', project_kind: '',
      })
      setFormError('')
      setFormErrors({})
      fetchData()
      toast.success('Project created successfully.')
    } catch (err) {
      const data = err.response?.data
      setFormErrors(data?.errors || {})
      setFormError(data?.message || (data?.errors ? Object.values(data.errors).join(', ') : 'Unable to create the project.'))
    } finally {
      setSubmitting(false)
    }
  }

  const hasErrorNoData = Boolean(error && projects.length === 0)
  const notStartedCount = hasErrorNoData ? '—' : projects.filter(p => p.overall_status === 'not_yet_started').length
  const ongoingCount = hasErrorNoData ? '—' : projects.filter(p => p.overall_status === 'ongoing').length
  const completedCount = hasErrorNoData ? '—' : projects.filter(p => p.overall_status === 'completed').length
  const totalCount = hasErrorNoData ? '—' : (meta.total || projects.length)

  const updateUrlParams = useCallback((updates) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if ('current_phase' in updates) next.delete('phase')
      if ('overall_status' in updates) next.delete('status')
      Object.entries(updates).forEach(([k, v]) => {
        if (v !== '' && v !== null && v !== undefined && v !== 1) {
          next.set(k, String(v))
        } else {
          next.delete(k)
        }
      })
      return next
    }, { replace: true })
  }, [setSearchParams])

  return (
    <div>
      <PageHeader
        title="Projects"
        description="Track LGU projects by program, funding year, phase, and documentary standing."
        actions={(isAdmin() || isStaff()) && (
          <Button icon={Plus} onClick={() => { setFormError(''); setFormErrors({}); setShowCreate(true) }}>New Project</Button>
        )}
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <KpiCard title="Projects" value={totalCount} subtitle="in registry" icon={FolderKanban} color="blue" />
        <KpiCard title="Ongoing" value={ongoingCount} subtitle="on this page" icon={CheckCircle2} color="emerald" />
        <KpiCard title="Not Yet Started" value={notStartedCount} subtitle="on this page" icon={AlertTriangle} color="amber" />
        <KpiCard title="Completed" value={completedCount} subtitle="on this page" icon={Archive} color="cyan" />
      </div>

      {error && (
        <InlineAlert type="error" className="mb-4">
          <div className="flex items-center justify-between gap-4">
            <span>{error}</span>
            <Button size="sm" variant="outline" onClick={fetchData}>Retry</Button>
          </div>
        </InlineAlert>
      )}

      {/* Filters */}
      <div className="mb-4 space-y-4 rounded-lg border border-brand-border bg-brand-surface-solid p-4">
        <form
          onSubmit={(e) => { e.preventDefault(); setPage(1); updateUrlParams({ search: search.trim(), page: 1 }) }}
          className="flex gap-2"
        >
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600 dark:text-slate-400" />
            <input
              id="project-search"
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by project name or code…"
              className="input-field pl-10"
              aria-label="Search"
            />
          </div>
          <Button variant="outline" type="submit" className="self-center">Search</Button>
        </form>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <label className="min-w-0 space-y-1.5 text-xs font-medium text-brand-text-muted" htmlFor="project-phase">
          <span className="block">Phase</span>
          <select
          id="project-phase"
          value={filterPhase}
          onChange={(e) => { setFilterPhase(e.target.value); setPage(1); updateUrlParams({ current_phase: e.target.value, page: 1 }) }}
          className="input-field w-full"
          aria-label="Filter by phase"
        >
          {PHASE_FILTERS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
        </select>
        </label>
        <label className="min-w-0 space-y-1.5 text-xs font-medium text-brand-text-muted" htmlFor="project-status">
          <span className="block">Status</span>
          <select
          id="project-status"
          value={filterStatus}
          onChange={(e) => { setFilterStatus(e.target.value); setPage(1); updateUrlParams({ overall_status: e.target.value, page: 1 }) }}
          className="input-field w-full"
          aria-label="Filter by status"
        >
          {PROJECT_STATUS_FILTERS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        </label>
        {lgus.length > 0 && (
          <label className="min-w-0 space-y-1.5 text-xs font-medium text-brand-text-muted" htmlFor="project-lgu">
          <span className="block">LGU</span>
          <select
            id="project-lgu"
            value={filterLgu}
            onChange={(e) => { setFilterLgu(e.target.value); setPage(1); updateUrlParams({ lgu_id: e.target.value, page: 1 }) }}
            className="input-field w-full"
            aria-label="Filter by LGU"
          >
            <option value="">All LGUs</option>
            {lgus.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </label>
        )}
        {programs.length > 0 && (
          <label className="min-w-0 space-y-1.5 text-xs font-medium text-brand-text-muted" htmlFor="project-program">
          <span className="block">Program</span>
          <select
            id="project-program"
            value={filterProgram}
            onChange={(e) => { setFilterProgram(e.target.value); setPage(1); updateUrlParams({ program_id: e.target.value, page: 1 }) }}
            className="input-field w-full"
            aria-label="Filter by program"
          >
            <option value="">All Programs</option>
            {programs.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        )}
        </div>
      </div>

      <ProjectsTable
        projects={projects}
        programs={programs}
        lgus={lgus}
        isLoading={loading}
        emptyMessage={error ? 'Unable to load projects. Please retry.' : 'No projects found. Create a project or import a program workbook to begin tracking.'}
      />

      {/* Pagination */}
      {meta.pages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-4">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => updateUrlParams({ page: page - 1 })}>Previous</Button>
          <span className="text-sm text-brand-text-muted">Page {page} of {meta.pages}</span>
          <Button variant="outline" size="sm" disabled={page >= meta.pages} onClick={() => updateUrlParams({ page: page + 1 })}>Next</Button>
        </div>
      )}

      {/* Create Modal */}
      <Modal
        open={showCreate}
        title="Create project"
        description="Create a project record for an LGU and program."
        size="lg"
        onClose={() => setShowCreate(false)}
      >
            <InlineAlert type="error" className="mb-3" onDismiss={() => setFormError('')}>
              {formError}
            </InlineAlert>
            <form onSubmit={handleCreate} className="space-y-4">
              <FormField id="project-form-lgu" label="LGU" required error={formErrors.lgu_id}>
                <select id="project-form-lgu" value={form.lgu_id} onChange={(e) => setForm({ ...form, lgu_id: e.target.value })} className="input-field">
                  <option value="">Select LGU</option>
                  {lgus.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
              </FormField>
              <FormField id="project-form-program" label="Program" required error={formErrors.program_id}>
                <select
                  id="project-form-program"
                  value={form.program_id}
                  onChange={(e) => {
                    const progId = e.target.value
                    const prog = programs.find((p) => String(p.id) === String(progId))
                    let newKind = form.project_kind
                    if (prog?.program_type === 'infrastructure') {
                      newKind = 'infrastructure'
                    } else if (prog?.program_type === 'non_infrastructure') {
                      if (newKind === 'infrastructure' || !newKind) {
                        newKind = ''
                      }
                    } else if (prog?.program_type === 'hybrid') {
                      newKind = ''
                    }
                    setForm({ ...form, program_id: progId, program_cycle_id: '', project_kind: newKind })
                  }}
                  className="input-field"
                >
                  <option value="">Select Program</option>
                  {programs.filter(p => p.is_active).map(p => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
                </select>
              </FormField>
              {(() => {
                const selectedProg = programs.find((p) => String(p.id) === String(form.program_id))
                const isInfraProg = selectedProg?.program_type === 'infrastructure'
                const isNonInfraProg = selectedProg?.program_type === 'non_infrastructure'
                const kindOptions = isInfraProg
                  ? INFRA_PROJECT_KIND_OPTIONS
                  : isNonInfraProg
                    ? NON_INFRA_PROJECT_KIND_OPTIONS
                    : ALL_PROJECT_KIND_OPTIONS
                const isKindRequired = Boolean(selectedProg)
                return (
                  <FormField
                    id="project-form-kind"
                    label="Project Classification"
                    required={isKindRequired}
                    error={formErrors.project_kind}
                  >
                    <select
                      id="project-form-kind"
                      value={form.project_kind}
                      onChange={(e) => setForm({ ...form, project_kind: e.target.value })}
                      className="input-field"
                    >
                      <option value="">Select Project Classification</option>
                      {kindOptions.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </FormField>
                )
              })()}
              {programCycles.length > 0 && (
                <FormField
                  id="project-form-cycle"
                  label="Program cycle"
                  required={programCycles.length > 1}
                  error={formErrors.program_cycle_id}
                >
                  <select
                    id="project-form-cycle"
                    value={form.program_cycle_id}
                    onChange={(e) => {
                      const selectedCycle = programCycles.find((cycle) => String(cycle.id) === e.target.value)
                      setForm({
                        ...form,
                        program_cycle_id: e.target.value,
                        fiscal_year: selectedCycle ? selectedCycle.fiscal_year : form.fiscal_year,
                      })
                      if (formErrors.program_cycle_id) {
                        setFormErrors((prev) => {
                          const next = { ...prev }
                          delete next.program_cycle_id
                          return next
                        })
                      }
                    }}
                    className="input-field"
                  >
                    {programCycles.length > 1 ? (
                      <option value="">Select a Program Cycle</option>
                    ) : (
                      <option value="">No cycle selected</option>
                    )}
                    {programCycles.map((cycle) => (
                      <option key={cycle.id} value={cycle.id}>
                        {cycle.name} ({cycle.cycle_code || `FY ${cycle.fiscal_year}`})
                      </option>
                    ))}
                  </select>
                </FormField>
              )}
              <FormField id="project-form-code" label="Project code" required error={formErrors.source_project_code}>
                <input id="project-form-code" type="text" value={form.source_project_code} onChange={(e) => setForm({ ...form, source_project_code: e.target.value })} maxLength={120} className="input-field" placeholder="e.g. COMET-2026-001" aria-describedby="project-form-code-help" />
                <p id="project-form-code-help" className="mt-1 text-xs text-slate-600 dark:text-slate-400">Use a unique reference for this project. The official SubayBAYAN code can be recorded separately when issued.</p>
              </FormField>
              <FormField id="project-form-name" label="Project name" required error={formErrors.project_name}>
                <input id="project-form-name" type="text" value={form.project_name} onChange={(e) => setForm({ ...form, project_name: e.target.value })} className="input-field" placeholder="e.g. LGSF - Santa Cruz FY2026" />
              </FormField>
              <div className="grid grid-cols-2 gap-4">
                <FormField id="project-form-fy" label="Fiscal year" required error={formErrors.fiscal_year}>
                  <input id="project-form-fy" type="number" value={form.fiscal_year} onChange={(e) => setForm({ ...form, fiscal_year: e.target.value, program_cycle_id: '' })} className="input-field" min="2000" max="2100" />
                </FormField>
                <FormField id="project-form-budget" label="Budget amount" error={formErrors.budget_amount}>
                  <AmountInput
                    id="project-form-budget"
                    value={form.budget_amount}
                    onChange={(e) => setForm({ ...form, budget_amount: e.target.value })}
                    placeholder="e.g. 5,000,000"
                  />
                </FormField>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <FormField id="project-form-start" label="Target start date" error={formErrors.target_start_date}>
                  <input id="project-form-start" type="date" value={form.target_start_date} onChange={(e) => setForm({ ...form, target_start_date: e.target.value })} className="input-field" />
                </FormField>
                <FormField id="project-form-end" label="Target end date" error={formErrors.target_end_date}>
                  <input id="project-form-end" type="date" value={form.target_end_date} onChange={(e) => setForm({ ...form, target_end_date: e.target.value })} className="input-field" />
                </FormField>
              </div>
              <FormField id="project-form-notes" label="Notes">
                <textarea id="project-form-notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="input-field" rows={3} placeholder="Optional notes..." />
              </FormField>
              <FormField id="project-form-status" label="Status" error={formErrors.overall_status}>
                <select id="project-form-status" value={form.overall_status} onChange={(e) => setForm({ ...form, overall_status: e.target.value })} className="input-field">
                  {PROJECT_STATUS_OPTIONS.map((status) => (
                    <option key={status.value} value={status.value}>{status.label}</option>
                  ))}
                </select>
              </FormField>
              <div className="flex gap-3 justify-end pt-2">
                <Button variant="outline" type="button" onClick={() => setShowCreate(false)}>Cancel</Button>
                <Button type="submit" loading={submitting}>Create Project</Button>
              </div>
            </form>
      </Modal>
    </div>
  )
}
