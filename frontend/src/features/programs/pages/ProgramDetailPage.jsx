import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { AlertTriangle, Edit2, ToggleLeft, ToggleRight, Plus, Trash2, GripVertical, FileText, Layers, ChevronDown, ChevronRight, Upload, Copy, Table2 } from 'lucide-react'
import { Breadcrumb, GlassPanel, Button, CategoryBadge, FeedbackToast, KpiCard, FormField, InlineAlert, Modal, ConfirmationModal } from '../../../components'
import { isAdmin } from '../../../lib/auth'
import { ROUTES } from '../../../config/routes'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import { apiErrorMessage } from '../../../lib/formErrors'
import * as programApi from '../api/programApi'
import { DocumentCheckerConfigFields } from '../components/DocumentCheckerConfigFields'
import { defaultCheckerConfig } from '../components/checkerConfigDefaults'

const REQ_TYPES = [
  { value: 'document', label: 'Document' },
  { value: 'certificate', label: 'Certificate' },
  { value: 'resolution', label: 'Resolution' },
  { value: 'financial', label: 'Financial' },
  { value: 'engineering', label: 'Engineering' },
  { value: 'inspection', label: 'Inspection Report' },
  { value: 'other', label: 'Other' },
]

const TYPE_BADGE = {
  infrastructure: { label: 'Infrastructure' },
  non_infrastructure: { label: 'Non-Infrastructure' },
  hybrid: { label: 'Hybrid' },
}

function emptyRequirementForm(sortOrder = 1) {
  return {
    name: '',
    description: '',
    requirement_type: 'document',
    annex_reference: '',
    sort_order: sortOrder,
    is_mandatory: true,
    has_sla: false,
    sla_days: null,
    checker_configuration: defaultCheckerConfig(),
  }
}

function requirementPayload(form, confirmSimilar = false) {
  const hasSla = Boolean(form.has_sla)
  return {
    name: form.name,
    description: form.description || '',
    requirement_type: form.requirement_type || 'document',
    annex_reference: form.annex_reference || '',
    sort_order: parseInt(form.sort_order) || 0,
    is_mandatory: Boolean(form.is_mandatory),
    has_sla: hasSla,
    sla_days: hasSla ? parseInt(form.sla_days) || null : null,
    confirm_similar: confirmSimilar,
    checker_configuration: form.checker_configuration || defaultCheckerConfig(),
  }
}

function parseFiscalYear(value) {
  const fiscalYear = Number(value)
  if (!Number.isInteger(fiscalYear) || fiscalYear < 2000 || fiscalYear > 2100) {
    return null
  }
  return fiscalYear
}

export default function ProgramDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [program, setProgram] = useState(null)
  const [matrix, setMatrix] = useState(null)
  const [cycles, setCycles] = useState([])
  const [selectedMatrixCycleId, setSelectedMatrixCycleId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editingProgram, setEditingProgram] = useState(false)
  const [form, setForm] = useState({})
  const [formError, setFormError] = useState('')
  const [pageMessage, setPageMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submittingCycle, setSubmittingCycle] = useState(false)
  const [submittingClone, setSubmittingClone] = useState(false)
  const [togglingActive, setTogglingActive] = useState(false)
  const [cloneCycle, setCloneCycle] = useState(null)
  const [cloneFiscalYear, setCloneFiscalYear] = useState('')
  const [deleteTarget, setDeleteTarget] = useState(null)

  // Phase/requirement modals
  const [showAddPhase, setShowAddPhase] = useState(false)
  const [editingPhase, setEditingPhase] = useState(null)
  const [phaseForm, setPhaseForm] = useState({ name: '', phase_order: 1, description: '' })
  const [phaseError, setPhaseError] = useState('')
  const [showAddCycle, setShowAddCycle] = useState(false)
  const [cycleForm, setCycleForm] = useState({ name: '', fiscal_year: new Date().getFullYear(), cycle_code: '' })
  const [cycleError, setCycleError] = useState('')
  const [expandedPhases, setExpandedPhases] = useState({})
  const [showAddReq, setShowAddReq] = useState(null)  // phaseId or null
  const [editingRequirement, setEditingRequirement] = useState(null)
  const [reqForm, setReqForm] = useState(emptyRequirementForm())
  const [reqError, setReqError] = useState('')
  const [reqSimilarity, setReqSimilarity] = useState(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [progRes, cyclesRes] = await Promise.all([
        programApi.getProgram(id),
        programApi.listProgramCycles(id),
      ])
      const loadedCycles = cyclesRes.data || []
      const targetCycleId = selectedMatrixCycleId === null ? (loadedCycles[0]?.id || '') : selectedMatrixCycleId
      const matrixParams = targetCycleId ? { program_cycle_id: targetCycleId } : { baseline_only: true }
      const matRes = await programApi.getProgramMatrix(id, matrixParams)
      setProgram(progRes.data)
      setMatrix(matRes.data)
      setCycles(loadedCycles)
      if (selectedMatrixCycleId === null && targetCycleId) {
        setSelectedMatrixCycleId(String(targetCycleId))
      }
      setForm({
        name: progRes.data.name || '',
        code: progRes.data.code || '',
        program_type: progRes.data.program_type || 'infrastructure',
        description: progRes.data.description || '',
        funding_agency: progRes.data.funding_agency || '',
      })
      // Expand all phases by default
      const expanded = {}
      ;(matRes.data.phases || []).forEach(p => { expanded[p.id] = true })
      setExpandedPhases(expanded)
    } catch (err) {
      if (err?.response?.status === 404) {
        navigate(ROUTES.PROGRAMS)
        return
      }
      setError(apiErrorMessage(err, 'Unable to load program details. Please try again.'))
    } finally {
      setLoading(false)
    }
  }, [id, navigate, selectedMatrixCycleId])

  useEffect(() => { fetchData() }, [fetchData])

  const handleToggle = async () => {
    if (togglingActive) return
    setTogglingActive(true)
    setFormError('')
    setPageMessage('')
    try {
      await programApi.toggleProgramActive(program.id)
      setPageMessage(`Program ${program.is_active ? 'deactivated' : 'activated'} successfully.`)
      fetchData()
    } catch (err) {
      setFormError(err.response?.data?.message || 'Unable to update the program status.')
    } finally {
      setTogglingActive(false)
    }
  }

  const handleUpdateProgram = async (e) => {
    e.preventDefault()
    setFormError('')
    const payload = {
      ...form,
      name: String(form.name || '').trim(),
      code: String(form.code || '').trim(),
      description: String(form.description || '').trim(),
      funding_agency: String(form.funding_agency || '').trim(),
    }
    if (!payload.name) {
      setFormError('Program name is required.')
      return
    }
    if (!payload.code) {
      setFormError('Program code is required.')
      return
    }
    if (!payload.program_type) {
      setFormError('Program type is required.')
      return
    }
    setSubmitting(true)
    try {
      await programApi.updateProgram(program.id, payload)
      setEditingProgram(false)
      fetchData()
    } catch (err) {
      setFormError(err.response?.data?.message || 'Unable to update the program details.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleAddPhase = async (e) => {
    e.preventDefault()
    setPhaseError('')
    if (!phaseForm.name.trim()) {
      setPhaseError('Phase name is required.')
      return
    }
    try {
      await programApi.createPhase(id, {
        ...phaseForm,
        phase_order: parseInt(phaseForm.phase_order) || 1,
      })
      setShowAddPhase(false)
      setPhaseForm({ name: '', phase_order: (matrix?.phases?.length || 0) + 1, description: '' })
      fetchData()
    } catch (err) {
      setPhaseError(err.response?.data?.message || 'Unable to add this phase.')
    }
  }

  const openEditPhase = (phase) => {
    setEditingPhase(phase)
    setPhaseForm({
      name: phase.name || '',
      phase_order: phase.phase_order || 1,
      description: phase.description || '',
    })
    setPhaseError('')
  }

  const handleUpdatePhase = async (e) => {
    e.preventDefault()
    if (!editingPhase) return
    setPhaseError('')
    if (!phaseForm.name.trim()) {
      setPhaseError('Phase name is required.')
      return
    }
    try {
      await programApi.updatePhase(editingPhase.id, {
        ...phaseForm,
        phase_order: parseInt(phaseForm.phase_order) || 1,
      })
      setEditingPhase(null)
      setPhaseForm({ name: '', phase_order: (matrix?.phases?.length || 0) + 1, description: '' })
      setPageMessage('Phase updated successfully.')
      fetchData()
    } catch (err) {
      setPhaseError(err.response?.data?.message || 'Unable to update this phase.')
    }
  }

  const handleAddCycle = async (e) => {
    e.preventDefault()
    if (submittingCycle) return
    setCycleError('')
    const name = String(cycleForm.name || '').trim()
    const cycleCode = String(cycleForm.cycle_code || '').trim()
    const fiscalYear = parseFiscalYear(cycleForm.fiscal_year)
    if (!name || !cycleCode) {
      setCycleError('Cycle name and code are required.')
      return
    }
    if (!fiscalYear) {
      setCycleError('Funding year must be a whole year between 2000 and 2100.')
      return
    }
    setSubmittingCycle(true)
    try {
      await programApi.createProgramCycle(id, {
        ...cycleForm,
        name,
        cycle_code: cycleCode,
        fiscal_year: fiscalYear,
      })
      setShowAddCycle(false)
      setCycleForm({ name: '', fiscal_year: new Date().getFullYear(), cycle_code: '' })
      fetchData()
    } catch (err) {
      setCycleError(err.response?.data?.message || 'Unable to add this funding-year cycle.')
    } finally {
      setSubmittingCycle(false)
    }
  }

  const handleCloneCycle = async (cycle) => {
    setCloneCycle(cycle)
    setCloneFiscalYear(String((cycle.fiscal_year || new Date().getFullYear()) + 1))
    setCycleError('')
  }

  const confirmCloneCycle = async (event) => {
    event.preventDefault()
    if (!cloneCycle || submittingClone) return
    setCycleError('')
    const fiscalYear = parseFiscalYear(cloneFiscalYear)
    if (!fiscalYear) {
      setCycleError('Funding year must be a whole year between 2000 and 2100.')
      return
    }
    setSubmittingClone(true)
    try {
      await programApi.cloneProgramCycle(cloneCycle.id, {
        fiscal_year: fiscalYear,
        name: `${program.name} FY ${fiscalYear}`,
      })
      setCloneCycle(null)
      setPageMessage('Funding-year cycle cloned successfully.')
      fetchData()
    } catch (err) {
      setCycleError(err.response?.data?.message || 'Unable to clone this funding-year cycle.')
    } finally {
      setSubmittingClone(false)
    }
  }

  const handleDeletePhase = async (phaseId) => {
    setDeleteTarget({ type: 'phase', id: phaseId, title: 'Delete phase', description: 'Delete this phase and all of its requirements? This cannot be undone.' })
  }

  const confirmDeleteTarget = async () => {
    if (!deleteTarget) return
    setFormError('')
    setPageMessage('')
    try {
      if (deleteTarget.type === 'phase') {
        await programApi.deletePhase(deleteTarget.id)
      } else {
        await programApi.deleteRequirement(deleteTarget.id)
      }
      setPageMessage(deleteTarget.type === 'phase' ? 'Phase deleted successfully.' : 'Requirement deleted successfully.')
      setDeleteTarget(null)
      fetchData()
    } catch (err) {
      setFormError(err.response?.data?.message || `Unable to delete this ${deleteTarget.type}.`)
    }
  }

  const handleAddRequirement = async (e, confirmSimilar = false) => {
    e.preventDefault()
    setReqError('')
    if (!confirmSimilar) setReqSimilarity(null)
    if (!reqForm.name.trim()) {
      setReqError('Requirement name is required.')
      return
    }
    try {
      const payload = requirementPayload(reqForm, confirmSimilar)
      await programApi.createRequirement(showAddReq, payload)
      setShowAddReq(null)
      setReqForm(emptyRequirementForm())
      setReqSimilarity(null)
      fetchData()
    } catch (err) {
      const similarity = err.response?.data?.errors?.requirement_similarity
      if (similarity) {
        setReqSimilarity(similarity)
        setReqError('')
        return
      }
      setReqError(err.response?.data?.message || 'Unable to add this requirement.')
    }
  }

  const openEditRequirement = (req) => {
    setEditingRequirement(req)
    setReqForm({
      name: req.name || '',
      description: req.description || '',
      requirement_type: req.requirement_type || 'document',
      annex_reference: req.annex_reference || '',
      sort_order: req.sort_order || 1,
      is_mandatory: req.is_mandatory !== false,
      has_sla: Boolean(req.has_sla),
      sla_days: req.sla_days || null,
      checker_configuration: req.checker_configuration || req.custom_field_schema?.checker_configuration || defaultCheckerConfig(),
    })
    setReqError('')
    setReqSimilarity(null)
  }

  const handleUpdateRequirement = async (e, confirmSimilar = false) => {
    e.preventDefault()
    if (!editingRequirement) return
    setReqError('')
    if (!confirmSimilar) setReqSimilarity(null)
    if (!reqForm.name.trim()) {
      setReqError('Requirement name is required.')
      return
    }
    try {
      await programApi.updateRequirement(editingRequirement.id, requirementPayload(reqForm, confirmSimilar))
      setEditingRequirement(null)
      setReqForm(emptyRequirementForm())
      setReqSimilarity(null)
      setPageMessage('Requirement updated successfully.')
      fetchData()
    } catch (err) {
      const similarity = err.response?.data?.errors?.requirement_similarity
      if (similarity) {
        setReqSimilarity(similarity)
        setReqError('')
        return
      }
      setReqError(err.response?.data?.message || 'Unable to update this requirement.')
    }
  }

  const handleDeleteRequirement = async (reqId) => {
    setDeleteTarget({ type: 'requirement', id: reqId, title: 'Delete requirement', description: 'Delete this requirement? This cannot be undone.' })
  }

  const togglePhase = (phaseId) => {
    setExpandedPhases(prev => ({ ...prev, [phaseId]: !prev[phaseId] }))
  }

  if (loading) {
    return (
      <div className="animate-fade-in">
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin h-8 w-8 border-2 border-brand-primary border-t-transparent rounded-full" />
        </div>
      </div>
    )
  }

  if (error && (!program || !matrix)) {
    return (
      <div className="animate-fade-in">
        <Breadcrumb
          items={[
            { label: 'Programs', to: ROUTES.PROGRAMS },
            { label: 'Program Profile' },
          ]}
        />
        <div className="mt-4">
          <InlineAlert type="error">
            <div className="flex items-center justify-between gap-4">
              <span>{error}</span>
              <Button size="sm" variant="outline" onClick={fetchData}>Retry</Button>
            </div>
          </InlineAlert>
        </div>
      </div>
    )
  }

  if (!program || !matrix) return null

  const typeInfo = TYPE_BADGE[program.program_type] || TYPE_BADGE.infrastructure
  const totalRequirements = (matrix.phases || []).reduce((sum, p) => sum + (p.requirements?.length || 0), 0)

  return (
    <div className="animate-fade-in">
      <Breadcrumb
        items={[
          { label: 'Programs', to: ROUTES.PROGRAMS },
          { label: program.name },
        ]}
      />

      {error && (
        <InlineAlert type="error" className="mt-4">
          <div className="flex items-center justify-between gap-4">
            <span>{error}</span>
            <Button size="sm" variant="outline" onClick={fetchData}>Retry</Button>
          </div>
        </InlineAlert>
      )}

      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="flex-1">
          <h1 className="page-title">{program.name}</h1>
          <p className="text-sm text-brand-text-muted">
            <span className="mr-2">{typeInfo.label}</span>
            {program.funding_agency && <span>· {program.funding_agency}</span>}
          </p>
        </div>
        {isAdmin() && (
          <div className="flex gap-2">
            <Button variant="outline" icon={editingProgram ? null : Edit2} onClick={() => { setEditingProgram(!editingProgram); setFormError('') }}>
              {editingProgram ? 'Cancel' : 'Edit'}
            </Button>
            <Button
              variant={program.is_active ? 'danger' : 'primary'}
              icon={program.is_active ? ToggleRight : ToggleLeft}
              onClick={handleToggle}
              loading={togglingActive}
              disabled={togglingActive}
            >
              {program.is_active ? 'Deactivate' : 'Activate'}
            </Button>
          </div>
        )}
      </div>

      {/* Status badge */}
      <FeedbackToast type="success" message={pageMessage} onDismiss={() => setPageMessage('')} />
      {!editingProgram && (
        <InlineAlert type="error" className="mb-4" onDismiss={() => setFormError('')}>
          {formError}
        </InlineAlert>
      )}

      <div className="mb-4">
        <span className={badgeClassForStatus(program.is_active ? 'active' : 'inactive')}>
          <span className={`status-dot ${program.is_active ? 'bg-emerald-600 dark:bg-emerald-300' : 'bg-slate-500 dark:bg-slate-300'}`} />
          {program.is_active ? 'Active' : 'Inactive'}
        </span>
        <span className="ml-2 status-badge status-badge-info">
          {program.code}
        </span>
      </div>

      {/* Edit form */}
      {editingProgram ? (
        <GlassPanel className="mb-4">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Edit Program Details</h2>
          <InlineAlert type="error" className="mb-3" onDismiss={() => setFormError('')}>
            {formError}
          </InlineAlert>
          <form onSubmit={handleUpdateProgram} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label-text">Program Name *</label>
                <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="input-field mt-1" required />
              </div>
              <div>
                <label className="label-text">Program Code *</label>
                <input type="text" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} className="input-field mt-1" required />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label-text">Program Type *</label>
                <select value={form.program_type} onChange={(e) => setForm({ ...form, program_type: e.target.value })} className="input-field mt-1" required>
                  <option value="infrastructure">Infrastructure</option>
                  <option value="non_infrastructure">Non-Infrastructure</option>
                  <option value="hybrid">Hybrid</option>
                </select>
              </div>
              <div>
                <label className="label-text">Funding Agency</label>
                <input type="text" value={form.funding_agency} onChange={(e) => setForm({ ...form, funding_agency: e.target.value })} className="input-field mt-1" />
              </div>
            </div>
            <div>
              <label className="label-text">Description</label>
              <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="input-field mt-1" rows={3} />
            </div>
            <div className="flex gap-3 justify-end pt-2">
              <Button type="submit" loading={submitting}>Save Changes</Button>
            </div>
          </form>
        </GlassPanel>
      ) : (
        program.description && (
          <GlassPanel className="mb-4">
            <p className="text-sm text-brand-text">{program.description}</p>
          </GlassPanel>
        )
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <KpiCard title="Phases" value={matrix.phases?.length || 0} subtitle="in matrix" icon={Layers} color="blue" />
        <KpiCard title="Requirements" value={totalRequirements} subtitle="documentary" icon={FileText} color="cyan" />
        <KpiCard title="Mandatory" value={(matrix.phases || []).reduce((n, p) => n + (p.requirements || []).filter(r => r.is_mandatory).length, 0)} subtitle="required" icon={null} color="amber" />
      </div>

      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Program Cycles</h2>
        {isAdmin() && (
          <Button size="sm" icon={Plus} onClick={() => {
            setCycleForm({
              name: `${program.name} FY ${new Date().getFullYear()}`,
              fiscal_year: new Date().getFullYear(),
              cycle_code: program.code,
            })
            setCycleError('')
            setShowAddCycle(true)
          }}>Add Cycle</Button>
        )}
      </div>

      {cycles.length === 0 ? (
        <GlassPanel className="mb-6">
          <p className="text-slate-600 dark:text-slate-400 text-sm">No funding-year cycles yet. Add one before importing workbook data.</p>
        </GlassPanel>
      ) : (
        <div className="space-y-2 mb-6">
          {cycles.map((cycle) => (
            <GlassPanel key={cycle.id}>
              <div className="flex flex-col md:flex-row md:items-center gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-slate-900 dark:text-white">{cycle.name}</span>
                    <span className="px-2 py-0.5 rounded border border-slate-300 dark:border-slate-700 text-xs text-slate-600 dark:text-slate-400">FY {cycle.fiscal_year}</span>
                    {cycle.cloned_from_cycle_id && (
                      <span className="status-badge status-badge-info">Cloned</span>
                    )}
                  </div>
                  <p className="text-xs text-slate-600 dark:text-slate-400 mt-1">
                    {cycle.cycle_code} · {cycle.projects_count || 0} projects · {cycle.import_templates_count || 0} templates
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" icon={Table2} onClick={() => navigate(ROUTES.programCycleWorkbook(program.id, cycle.id))}>Workbook</Button>
                  {isAdmin() && (
                    <>
                      <Button size="sm" variant="outline" icon={Copy} onClick={() => handleCloneCycle(cycle)}>Clone</Button>
                      <Button size="sm" icon={Upload} onClick={() => navigate(ROUTES.programCycleImport(program.id, cycle.id))}>Import</Button>
                    </>
                  )}
                </div>
              </div>
            </GlassPanel>
          ))}
        </div>
      )}

      {/* Phase & Requirement Matrix */}
      <div className="flex flex-col gap-3 mb-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Requirement Matrix</h2>
          {matrix.selected_program_cycle && (
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
              Showing FY {matrix.selected_program_cycle.fiscal_year} requirements plus baseline program requirements.
            </p>
          )}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          {cycles.length > 0 && (
            <select
              className="input-field h-9 min-w-[220px]"
              value={selectedMatrixCycleId || ''}
              onChange={(event) => setSelectedMatrixCycleId(event.target.value)}
            >
              <option value="">All baseline requirements</option>
              {cycles.map(cycle => (
                <option key={cycle.id} value={cycle.id}>FY {cycle.fiscal_year} · {cycle.name}</option>
              ))}
            </select>
          )}
        {isAdmin() && (
          <Button size="sm" icon={Plus} onClick={() => {
            setPhaseForm({ name: '', phase_order: (matrix?.phases?.length || 0) + 1, description: '' })
            setPhaseError('')
            setEditingPhase(null)
            setShowAddPhase(true)
          }}>Add Phase</Button>
        )}
        </div>
      </div>

      {matrix.phases?.length === 0 ? (
        <GlassPanel>
          <div className="text-center py-8">
            <Layers className="h-10 w-10 text-slate-600 dark:text-slate-300 mx-auto mb-3" />
            <p className="text-brand-text-muted">No phases yet. Add pre-implementation, implementation, or completion phases to organize this program's requirements.</p>
          </div>
        </GlassPanel>
      ) : (
        <div className="space-y-3">
          {matrix.phases.map((phase) => (
            <GlassPanel key={phase.id} className="overflow-hidden">

              {/* Phase Header */}
              <div
                className="flex items-center gap-3 cursor-pointer group"
                onClick={() => togglePhase(phase.id)}
              >
                <button
                  className="text-brand-text-muted transition-colors group-hover:text-brand-text"
                  aria-label={expandedPhases[phase.id] !== false ? `Collapse phase ${phase.name}` : `Expand phase ${phase.name}`}
                  title={expandedPhases[phase.id] !== false ? "Collapse phase" : "Expand phase"}
                >
                  {expandedPhases[phase.id] !== false
                    ? <ChevronDown className="h-4 w-4" />
                    : <ChevronRight className="h-4 w-4" />}
                </button>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-slate-900 dark:text-white font-medium">{phase.name}</span>
                    <span className="text-xs text-slate-600 dark:text-slate-400">Order {phase.phase_order}</span>
                    {phase.is_required && (
                      <span className="status-badge status-badge-warning">Required</span>
                    )}
                  </div>
                  {phase.description && (
                    <p className="mt-0.5 text-xs text-brand-text-muted">{phase.description}</p>
                  )}
                  <p className="text-xs text-slate-600 dark:text-slate-400">{phase.requirements?.length || 0} requirements</p>
                </div>
                {isAdmin() && (
                  <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    <button
                      onClick={(e) => { e.stopPropagation(); openEditPhase(phase) }}
                      className="p-1 text-brand-text-muted transition-colors hover:text-brand-primary"
                      title="Edit phase"
                      aria-label={`Edit phase ${phase.name}`}
                    >
                      <Edit2 className="h-4 w-4" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeletePhase(phase.id) }}
                      className="p-1 text-brand-text-muted transition-colors hover:text-red-700 dark:hover:text-red-200"
                      title="Delete phase"
                      aria-label={`Delete phase ${phase.name}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                )}
              </div>

              {/* Requirements list */}
              {expandedPhases[phase.id] !== false && (
                <div className="mt-3 border-t border-brand-border pt-3">
                  {phase.requirements?.length > 0 ? (
                    <div className="space-y-2">
                      {phase.requirements.map((req) => (
                        <div key={req.id} className="flex items-center gap-3 rounded-md bg-slate-100 p-2.5 transition-colors hover:bg-slate-50 dark:bg-slate-800/50 dark:hover:bg-slate-800 group/req">
                          <GripVertical className="h-4 w-4 text-slate-600 dark:text-slate-300 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm text-slate-900 dark:text-white">{req.name}</span>
                              <CategoryBadge category="requirement_type" value={req.requirement_type} />
                              {req.is_mandatory && (
                                <span className="status-badge status-badge-success">Mandatory</span>
                              )}
                              {req.has_sla && req.sla_days && (
                                <span className="status-badge status-badge-warning">{req.sla_days} working days</span>
                              )}
                            </div>
                            {req.annex_reference && (
                              <p className="text-xs text-slate-600 dark:text-slate-400 mt-0.5">Annex: {req.annex_reference}</p>
                            )}
                          </div>
                          {isAdmin() && (
                            <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover/req:opacity-100">
                              <button
                                onClick={() => openEditRequirement(req)}
                                className="p-1 text-brand-text-muted transition-colors hover:text-brand-primary"
                                title="Edit requirement"
                                aria-label={`Edit requirement ${req.name}`}
                              >
                                <Edit2 className="h-3.5 w-3.5" />
                              </button>
                              <button
                                onClick={() => handleDeleteRequirement(req.id)}
                                className="p-1 text-brand-text-muted transition-colors hover:text-red-700 dark:hover:text-red-200"
                                title="Delete requirement"
                                aria-label={`Delete requirement ${req.name}`}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-slate-600 dark:text-slate-400 text-sm py-2">No requirements in this phase.</p>
                  )}
                  {isAdmin() && (
                    <button
                      onClick={() => {
                        setReqForm(emptyRequirementForm((phase.requirements?.length || 0) + 1))
                        setReqError('')
                        setReqSimilarity(null)
                        setEditingRequirement(null)
                        setShowAddReq(phase.id)
                      }}
                      className="action-link mt-2 text-sm"
                    >
                      <Plus className="h-3.5 w-3.5" /> Add Requirement
                    </button>
                  )}
                </div>
              )}
            </GlassPanel>
          ))}
        </div>
      )}

      {/* Add Cycle Modal */}
      <Modal
        open={Boolean(cloneCycle)}
        title="Clone funding-year cycle"
        description={cloneCycle ? `Create a new cycle from ${cloneCycle.name}.` : ''}
        onClose={() => setCloneCycle(null)}
      >
        <InlineAlert type="error" className="mb-3" onDismiss={() => setCycleError('')}>
          {cycleError}
        </InlineAlert>
        <form onSubmit={confirmCloneCycle} className="space-y-4">
          <FormField id="clone-fiscal-year" label="New funding year" required>
            <input
              id="clone-fiscal-year"
              type="number"
              className="input-field"
              min={2000}
              max={2100}
              required
              value={cloneFiscalYear}
              onChange={(event) => setCloneFiscalYear(event.target.value)}
            />
          </FormField>
          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setCloneCycle(null)}>Cancel</Button>
            <Button type="submit" loading={submittingClone} disabled={submittingClone}>Clone Cycle</Button>
          </div>
        </form>
      </Modal>

      <ConfirmationModal
        open={Boolean(deleteTarget)}
        title={deleteTarget?.title}
        description={deleteTarget?.description}
        confirmLabel="Delete"
        isDestructive={true}
        onConfirm={confirmDeleteTarget}
        onClose={() => setDeleteTarget(null)}
      />

      {/* Add Cycle Modal */}
      <Modal
        open={showAddCycle}
        title="Add Program Cycle"
        description="Create a new funding-year cycle for this program."
        onClose={() => setShowAddCycle(false)}
      >
        <InlineAlert type="error" className="mb-3" onDismiss={() => setCycleError('')}>
          {cycleError}
        </InlineAlert>
        <form onSubmit={handleAddCycle} className="space-y-4">
          <FormField id="add-cycle-name" label="Cycle Name" required>
            <input id="add-cycle-name" type="text" value={cycleForm.name} onChange={(e) => setCycleForm({ ...cycleForm, name: e.target.value })} className="input-field" placeholder="e.g. LGSF-FALGU FY 2025" required />
          </FormField>
          <div className="grid grid-cols-2 gap-4">
            <FormField id="add-cycle-fy" label="Funding Year" required>
              <input id="add-cycle-fy" type="number" value={cycleForm.fiscal_year} onChange={(e) => setCycleForm({ ...cycleForm, fiscal_year: e.target.value })} className="input-field" min={2000} max={2100} required />
            </FormField>
            <FormField id="add-cycle-code" label="Cycle Code" required>
              <input id="add-cycle-code" type="text" value={cycleForm.cycle_code} onChange={(e) => setCycleForm({ ...cycleForm, cycle_code: e.target.value })} className="input-field" placeholder="e.g. FALGU-2025" required />
            </FormField>
          </div>
          <div className="flex gap-3 justify-end pt-2">
            <Button variant="outline" type="button" onClick={() => setShowAddCycle(false)}>Cancel</Button>
            <Button type="submit" loading={submittingCycle} disabled={submittingCycle}>Add Cycle</Button>
          </div>
        </form>
      </Modal>

      {/* Phase Modal */}
      <Modal
        open={showAddPhase || Boolean(editingPhase)}
        title={editingPhase ? 'Edit Phase' : 'Add Phase'}
        description={editingPhase ? 'Update phase details.' : 'Add a new phase to this program.'}
        onClose={() => { setShowAddPhase(false); setEditingPhase(null) }}
      >
        <InlineAlert type="error" className="mb-3" onDismiss={() => setPhaseError('')}>
          {phaseError}
        </InlineAlert>
        <form onSubmit={editingPhase ? handleUpdatePhase : handleAddPhase} className="space-y-4">
          <FormField id="phase-name" label="Phase Name" required>
            <input id="phase-name" type="text" value={phaseForm.name} onChange={(e) => setPhaseForm({ ...phaseForm, name: e.target.value })} className="input-field" placeholder="e.g. Pre-Implementation" />
          </FormField>
          <FormField id="phase-order" label="Order">
            <input id="phase-order" type="number" value={phaseForm.phase_order} onChange={(e) => setPhaseForm({ ...phaseForm, phase_order: parseInt(e.target.value) || 1 })} className="input-field" min={1} />
          </FormField>
          <FormField id="phase-description" label="Description">
            <textarea id="phase-description" value={phaseForm.description} onChange={(e) => setPhaseForm({ ...phaseForm, description: e.target.value })} className="input-field" rows={3} />
          </FormField>
          <div className="flex gap-3 justify-end pt-2">
            <Button variant="outline" type="button" onClick={() => { setShowAddPhase(false); setEditingPhase(null) }}>Cancel</Button>
            <Button type="submit">{editingPhase ? 'Save Phase' : 'Add Phase'}</Button>
          </div>
        </form>
      </Modal>

      {/* Requirement Modal */}
      <Modal
        open={Boolean(showAddReq) || Boolean(editingRequirement)}
        title={editingRequirement ? 'Edit Requirement' : 'Add Requirement'}
        description={editingRequirement ? 'Update this requirement.' : 'Add a new documentary requirement.'}
        size="lg"
        onClose={() => { setShowAddReq(null); setEditingRequirement(null); setReqSimilarity(null) }}
      >
        <InlineAlert type="error" className="mb-3" onDismiss={() => setReqError('')}>
          {reqError}
        </InlineAlert>
        {reqSimilarity && (
          <div className="mb-4 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800/50 dark:bg-amber-950/30 dark:text-amber-100">
            <div className="mb-2 flex items-center gap-2 font-medium">
              <AlertTriangle className="h-4 w-4" />
              {reqSimilarity.type === 'exact' ? 'Requirement already exists' : 'Similar requirement found'}
            </div>
            <div className="space-y-1">
              {(reqSimilarity.candidates || []).slice(0, 4).map(candidate => (
                <div key={`${candidate.id}-${candidate.name}`}>
                  {candidate.name}
                  {candidate.phase_name ? ` · ${candidate.phase_name}` : ''}
                  {candidate.annex_reference ? ` · ${candidate.annex_reference}` : ''}
                </div>
              ))}
            </div>
            {reqSimilarity.requires_confirmation && (
              <div className="mt-3 flex justify-end">
                <Button
                  size="sm"
                  variant="outline"
                  type="button"
                  onClick={(event) => (editingRequirement ? handleUpdateRequirement(event, true) : handleAddRequirement(event, true))}
                >
                  {editingRequirement ? 'Save Anyway' : 'Create Anyway'}
                </Button>
              </div>
            )}
          </div>
        )}
        <form onSubmit={editingRequirement ? handleUpdateRequirement : handleAddRequirement} className="space-y-4">
          <FormField id="req-name" label="Requirement Name" required>
            <input id="req-name" type="text" value={reqForm.name} onChange={(e) => setReqForm({ ...reqForm, name: e.target.value })} className="input-field" placeholder="e.g. Sangguniang Bayan Resolution" />
          </FormField>
          <FormField id="req-description" label="Description">
            <textarea id="req-description" value={reqForm.description} onChange={(e) => setReqForm({ ...reqForm, description: e.target.value })} className="input-field" rows={3} />
          </FormField>
          <div className="grid grid-cols-2 gap-4">
            <FormField id="req-type" label="Requirement Type" required>
              <select id="req-type" value={reqForm.requirement_type} onChange={(e) => setReqForm({ ...reqForm, requirement_type: e.target.value })} className="input-field">
                {REQ_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </FormField>
            <FormField id="req-order" label="Sort Order">
              <input id="req-order" type="number" value={reqForm.sort_order} onChange={(e) => setReqForm({ ...reqForm, sort_order: parseInt(e.target.value) || 1 })} className="input-field" min={1} />
            </FormField>
          </div>
          <FormField id="req-annex" label="Annex Reference">
            <input id="req-annex" type="text" value={reqForm.annex_reference} onChange={(e) => setReqForm({ ...reqForm, annex_reference: e.target.value })} className="input-field" placeholder="e.g. Annex A" />
          </FormField>
          <div className="flex items-center gap-6">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={reqForm.is_mandatory} onChange={(e) => setReqForm({ ...reqForm, is_mandatory: e.target.checked })} className="rounded border-slate-300 bg-white text-brand-primary focus:ring-brand-primary dark:border-slate-600 dark:bg-slate-800" />
              <span className="text-sm text-brand-text">Mandatory</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={reqForm.has_sla} onChange={(e) => setReqForm({ ...reqForm, has_sla: e.target.checked })} className="rounded border-slate-300 bg-white text-brand-primary focus:ring-brand-primary dark:border-slate-600 dark:bg-slate-800" />
              <span className="text-sm text-brand-text">Has working-day deadline</span>
            </label>
          </div>
          {reqForm.has_sla && (
            <FormField id="req-sla-days" label="Working Days">
              <input id="req-sla-days" type="number" value={reqForm.sla_days || ''} onChange={(e) => setReqForm({ ...reqForm, sla_days: parseInt(e.target.value) || null })} className="input-field" min={1} placeholder="Number of days" />
            </FormField>
          )}
          <DocumentCheckerConfigFields
            value={reqForm.checker_configuration}
            onChange={(cfg) => setReqForm({ ...reqForm, checker_configuration: cfg })}
          />
          <div className="flex gap-3 justify-end pt-2">
            <Button variant="outline" type="button" onClick={() => { setShowAddReq(null); setEditingRequirement(null); setReqSimilarity(null) }}>Cancel</Button>
            <Button type="submit">{editingRequirement ? 'Save Requirement' : 'Add Requirement'}</Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
