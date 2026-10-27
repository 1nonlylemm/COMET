import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, FileSpreadsheet, Loader2, Table2, Upload } from 'lucide-react'
import { Breadcrumb, Button, DataTable, GlassPanel, InlineAlert, KpiCard, useToast } from '../../../components'
import { ROUTES } from '../../../config/routes'
import { formatMachineLabel, formatStatus } from '../../../lib/formatters'
import { apiErrorMessage } from '../../../lib/formErrors'
import * as importApi from '../api/importApi'
import * as programApi from '../../programs/api/programApi'

function requirementWarningKey(item, index = 0) {
  return item.warning_key || item.imported_name || item.standardized_name || String(index)
}

function formatCandidateScore(score) {
  if (score === null || score === undefined) return '—'
  return `${Math.round(score * 100)}%`
}

const IMPORT_STEPS = [
  { key: 'upload', label: 'Upload' },
  { key: 'map', label: 'Map' },
  { key: 'preview', label: 'Preview' },
  { key: 'commit', label: 'Apply' },
]

const COLUMN_CLASSIFICATIONS = [
  { value: 'project_field', label: 'Project Field' },
  { value: 'lgu_field', label: 'LGU Field' },
  { value: 'cycle_field', label: 'Cycle Field' },
  { value: 'requirement', label: 'Requirement' },
  { value: 'context', label: 'Project Detail' },
  { value: 'ignored', label: 'Ignore' },
]

export default function WorkbookImportPage() {
  const { programId, cycleId } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const [program, setProgram] = useState(null)
  const [cycle, setCycle] = useState(null)
  const [file, setFile] = useState(null)
  const [batch, setBatch] = useState(null)
  const [mapping, setMapping] = useState(null)
  const [mappingDecisions, setMappingDecisions] = useState([])
  const [mappingSaved, setMappingSaved] = useState(false)
  const [preview, setPreview] = useState(null)
  const [commitResult, setCommitResult] = useState(null)
  const [requirementWarnings, setRequirementWarnings] = useState([])
  const [confirmedRequirementWarnings, setConfirmedRequirementWarnings] = useState({})
  const [error, setError] = useState('')
  const [contextError, setContextError] = useState('')
  const [working, setWorking] = useState(false)
  const [operation, setOperation] = useState(null)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)

  const loadContext = useCallback(async () => {
    setContextError('')
    try {
      const [programRes, cyclesRes] = await Promise.all([
        programApi.getProgram(programId),
        programApi.listProgramCycles(programId),
      ])
      setProgram(programRes.data)
      setCycle((cyclesRes.data || []).find(item => String(item.id) === String(cycleId)) || null)
    } catch (err) {
      if (err?.response?.status === 404) {
        navigate(ROUTES.PROGRAMS)
        return
      }
      setContextError(apiErrorMessage(err, 'Unable to load program import context. Please try again.'))
    }
  }, [programId, cycleId, navigate])

  useEffect(() => {
    loadContext()
  }, [loadContext])

  useEffect(() => {
    if (!operation) {
      setElapsedSeconds(0)
      return undefined
    }
    setElapsedSeconds(0)
    const startedAt = operation.startedAt
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [operation])

  useEffect(() => {
    if (!working) return undefined

    const warnBeforeUnload = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }

    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [working])

  const startOperation = (step, detail) => {
    setWorking(true)
    setOperation({ step, detail, startedAt: Date.now() })
  }

  const updateOperation = (step, detail) => {
    setOperation(previous => ({
      step,
      detail,
      startedAt: previous?.startedAt || Date.now(),
    }))
  }

  const finishOperation = () => {
    setWorking(false)
    setOperation(null)
  }

  const handleUpload = async (event) => {
    event.preventDefault()
    if (!file) {
      setError('Select a CSV or Excel workbook first.')
      return
    }
    startOperation('upload', 'Uploading and profiling workbook sheets.')
    setError('')
    try {
      const payload = new FormData()
      payload.append('program_id', programId)
      payload.append('program_cycle_id', cycleId)
      payload.append('file', file)
      const uploadRes = await importApi.uploadWorkbook(payload)
      setBatch(uploadRes.data)
      updateOperation('map', 'Preparing suggested column mappings.')
      const mapRes = await importApi.mapWorkbook(uploadRes.data.id)
      setMapping(mapRes.data)
      setMappingDecisions(mapRes.data?.mapping_decisions || mapRes.data?.field_mappings || [])
      setMappingSaved(false)
      setPreview(null)
      setCommitResult(null)
      setRequirementWarnings([])
      setConfirmedRequirementWarnings({})
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to upload and detect this workbook.')
    } finally {
      finishOperation()
    }
  }

  const handlePreview = async () => {
    if (!batch) return
    startOperation('preview', 'Validating rows, LGUs, projects, and requirement matches.')
    setError('')
    try {
      const effectiveMapping = {
        ...(mapping || {}),
        field_mappings: mappingDecisions.length ? mappingDecisions : (mapping?.field_mappings || []),
      }
      const previewRes = await importApi.previewWorkbook(batch.id, effectiveMapping)
      setPreview(previewRes.data)
      setRequirementWarnings(previewRes.data?.summary?.requirements?.review_items || [])
      setConfirmedRequirementWarnings({})
      const refreshed = await importApi.getImportBatch(batch.id)
      setBatch(refreshed.data)
      setMapping(refreshed.data.mapping_preview || mapping)
      setMappingDecisions(refreshed.data.mapping_preview?.mapping_decisions || refreshed.data.mapping_preview?.field_mappings || mappingDecisions)
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to preview the workbook import.')
    } finally {
      finishOperation()
    }
  }

  const updateDecision = (index, patch) => {
    setMappingSaved(false)
    setMappingDecisions(previous => previous.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...patch } : item
    )))
  }

  const applyHistorySuggestion = (index) => {
    const suggestion = mappingDecisions[index]?.history_suggestion
    if (!suggestion) return
    updateDecision(index, {
      classification: suggestion.classification,
      canonical_label: suggestion.canonical_label,
      target_field: suggestion.target_field,
      suggested_role: suggestion.suggested_role,
      binding_target: suggestion.binding_target,
      binding_config: suggestion.binding_config || {},
      requirement_metadata: suggestion.requirement_metadata || {},
      value_mapping_rules: suggestion.value_mapping_rules || {},
      requires_confirmation: false,
      decision_source: 'confirmed_from_history',
    })
  }

  const handleSaveMappingDecisions = async () => {
    if (!batch) return
    startOperation('map', 'Saving confirmed column names, roles, and requirement settings.')
    setError('')
    try {
      const saveRes = await importApi.saveMappingDecisions(batch.id, mappingDecisions)
      setMapping(saveRes.data.mapping)
      setMappingDecisions(saveRes.data.mapping?.mapping_decisions || saveRes.data.mapping?.field_mappings || [])
      setMappingSaved(true)
      setPreview(null)
      toast.success('Column mapping decisions saved.')
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to save the column mapping decisions.')
    } finally {
      finishOperation()
    }
  }

  const handleCommit = async (confirmSimilar = false) => {
    if (!batch) return
    startOperation('commit', 'Writing project records and creating the workbook workspace.')
    setError('')
    try {
      const commitRes = await importApi.commitWorkbook(batch.id, {
        confirm_similar_requirements: confirmSimilar,
      })
      setCommitResult(commitRes.data)
      toast.success('Workbook import applied successfully.')
      setRequirementWarnings([])
      setConfirmedRequirementWarnings({})
      const refreshed = await importApi.getImportBatch(batch.id)
      setBatch(refreshed.data)
    } catch (err) {
      const warnings = err.response?.data?.errors?.requirement_warnings
      if (warnings?.length) {
        setRequirementWarnings(warnings)
        setConfirmedRequirementWarnings({})
        setError('')
        return
      }
      setError(err.response?.data?.message || 'Unable to apply the workbook import.')
    } finally {
      finishOperation()
    }
  }

  const sheets = batch?.workbook_profile?.sheets || []
  const mappings = (mappingDecisions.length ? mappingDecisions : (mapping?.field_mappings || [])).map((item, index) => ({
    ...item,
    mapping_key: `${item.source_sheet}-${item.source_column}-${item.target_field || item.suggested_role || index}`,
  }))
  const summary = preview?.summary
  const hasInvalidRows = (summary?.projects?.invalid || 0) > 0
  const hasRequirementWarnings = requirementWarnings.length > 0
  const allRequirementWarningsConfirmed = !hasRequirementWarnings || requirementWarnings.every((item, index) => {
    return confirmedRequirementWarnings[requirementWarningKey(item, index)]
  })
  const confirmedRequirementWarningCount = requirementWarnings.filter((item, index) => {
    return confirmedRequirementWarnings[requirementWarningKey(item, index)]
  }).length
  const operationStepIndex = IMPORT_STEPS.findIndex(step => step.key === operation?.step)
  const operationStepLabel = IMPORT_STEPS[operationStepIndex]?.label || 'Processing'

  const toggleRequirementWarning = (item, index) => {
    const key = requirementWarningKey(item, index)
    setConfirmedRequirementWarnings(previous => ({
      ...previous,
      [key]: !previous[key],
    }))
  }

  const sheetColumns = [
    { key: 'name', label: 'Sheet' },
    { key: 'sheet_type', label: 'Detected Type', render: row => formatMachineLabel(row.sheet_type || 'unknown') },
    { key: 'max_row', label: 'Rows' },
    { key: 'max_column', label: 'Columns' },
    { key: 'data_start_row', label: 'Data Starts' },
  ]

  const previewColumns = [
    { key: 'row_number', label: 'Row' },
    { key: 'action', label: 'Action', render: row => formatMachineLabel(row.action) },
    {
      key: 'project',
      label: 'Project',
      render: row => row.mapped_data?.project?.project_name || row.mapped_data?.project?.source_project_code || '—',
    },
    {
      key: 'lgu',
      label: 'LGU',
      render: row => row.mapped_data?.lgu?.name || row.mapped_data?.lgu?.municipality || '—',
    },
    {
      key: 'validation_errors',
      label: 'Errors',
      render: row => row.validation_errors?.length ? row.validation_errors.join('; ') : '—',
    },
  ]

  return (
    <div className="animate-fade-in">
      <Breadcrumb
        items={[
          { label: 'Programs', to: ROUTES.PROGRAMS, disabled: working },
          { label: program?.name || 'Program', to: ROUTES.programDetail(programId), disabled: working },
          { label: cycle?.name || 'Selected Cycle' },
          { label: 'Workbook Import' },
        ]}
      />

      <div className="flex items-center gap-3 mb-6">
        <div className="flex-1">
          <h1 className="page-title">Program Workbook Import</h1>
          <p className="mt-1 text-sm text-brand-text-muted">
            {program?.name || 'Program'} {cycle ? `· ${cycle.name}` : ''}
          </p>
        </div>
      </div>

      {contextError && (
        <InlineAlert type="error" className="mb-4">
          <div className="flex items-center justify-between gap-4">
            <span>{contextError}</span>
            <Button size="sm" variant="outline" onClick={loadContext}>Retry</Button>
          </div>
        </InlineAlert>
      )}

      <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>
        {error}
      </InlineAlert>

      {operation && (
        <GlassPanel className="mb-4 border border-blue-200 bg-blue-50/70 dark:border-blue-900/60 dark:bg-blue-950/20">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-start gap-3">
              <Loader2 className="mt-1 h-5 w-5 animate-spin text-blue-600 dark:text-blue-300" />
              <div>
                <div className="text-sm font-semibold text-slate-950 dark:text-white">
                  {operationStepLabel} in progress
                </div>
                <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">
                  {operation.detail}
                </p>
                <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
                  Keep this page open. The server is still processing the workbook.
                </p>
              </div>
            </div>
            <div className="shrink-0 text-xs font-medium text-slate-600 dark:text-slate-300">
              Elapsed {elapsedSeconds}s
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4">
            {IMPORT_STEPS.map((step, index) => {
              const isCurrent = index === operationStepIndex
              const isDone = operationStepIndex > index
              return (
                <div
                  key={step.key}
                  className={`rounded border px-3 py-2 text-xs font-medium ${
                    isCurrent
                      ? 'border-blue-300 bg-white text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-200'
                      : isDone
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200'
                        : 'border-slate-200 bg-white/60 text-slate-600 dark:text-slate-400 dark:border-slate-800 dark:bg-slate-950/20'
                  }`}
                >
                  {step.label}
                </div>
              )
            })}
          </div>
        </GlassPanel>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <KpiCard title="Sheets" value={sheets.length} subtitle="detected" icon={FileSpreadsheet} color="blue" />
        <KpiCard title="Mapped" value={mappings.length} subtitle="columns" color="cyan" />
        <KpiCard title="New projects" value={summary?.projects?.new ?? '—'} subtitle="to import" color="emerald" />
        <KpiCard title="Invalid" value={summary?.projects?.invalid ?? '—'} subtitle="rows" color="red" />
      </div>

      <GlassPanel className="mb-4">
        <form onSubmit={handleUpload} className="flex flex-col md:flex-row gap-3 md:items-end">
          <div className="flex-1">
            <label className="label-text">CSV / XLSX Workbook</label>
            <input
              type="file"
              accept=".csv,.xlsx"
              disabled={working}
              onChange={(event) => setFile(event.target.files?.[0] || null)}
              className="input-field mt-1"
            />
          </div>
          <Button type="submit" icon={Upload} loading={working}>
            Upload and Detect
          </Button>
        </form>
      </GlassPanel>

      {batch && (
        <div className="space-y-4">
          <GlassPanel>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Detected Sheets</h2>
              <span className="text-xs text-slate-600 dark:text-slate-400">Batch #{batch.id} · {formatStatus(batch.status)}</span>
            </div>
            <DataTable columns={sheetColumns} data={sheets} keyField="name" emptyMessage="No sheets detected." />
          </GlassPanel>

          <GlassPanel>
            <div className="flex items-center justify-between mb-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Column Mapping Review</h2>
                {mappingSaved && <p className="mt-1 text-xs text-emerald-700 dark:text-emerald-300">Confirmed mapping decisions saved for this import.</p>}
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={handleSaveMappingDecisions} loading={working}>
                  Save Decisions
                </Button>
                <Button size="sm" variant="outline" onClick={handlePreview} loading={working}>
                  Preview Import
                </Button>
              </div>
            </div>
            {mappings.length === 0 ? (
              <p className="py-6 text-center text-sm text-slate-600 dark:text-slate-400">No mappings prepared.</p>
            ) : (
              <div className="overflow-x-auto rounded border border-slate-200 dark:border-slate-800">
                <table className="w-full min-w-[980px] text-left text-xs">
                  <thead className="bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-200">
                    <tr>
                      <th className="px-3 py-2 font-semibold">Source</th>
                      <th className="px-3 py-2 font-semibold">Final Name</th>
                      <th className="px-3 py-2 font-semibold">Role</th>
                      <th className="px-3 py-2 font-semibold">Target</th>
                      <th className="px-3 py-2 font-semibold">Requirement</th>
                      <th className="px-3 py-2 font-semibold">Suggestion</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                    {mappings.map((item, index) => (
                      <tr key={item.mapping_key}>
                        <td className="px-3 py-2 align-top">
                          <div className="font-medium text-slate-900 dark:text-white">{item.source_header || item.source_column}</div>
                          <div className="mt-1 text-[11px] text-slate-600 dark:text-slate-400">{item.source_sheet} · {item.source_column}</div>
                        </td>
                        <td className="px-3 py-2 align-top">
                          <input
                            className="input-field h-9 min-w-[190px]"
                            value={item.canonical_label || ''}
                            onChange={(event) => updateDecision(index, { canonical_label: event.target.value })}
                          />
                        </td>
                        <td className="px-3 py-2 align-top">
                          <select
                            className="input-field h-9 min-w-[150px]"
                            value={item.classification || 'context'}
                            onChange={(event) => updateDecision(index, { classification: event.target.value })}
                          >
                            {COLUMN_CLASSIFICATIONS.map(option => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </select>
                        </td>
                        <td className="px-3 py-2 align-top">
                          <div className="text-slate-700 dark:text-slate-200">{formatMachineLabel(item.target_field || item.binding_target || item.suggested_role || 'none')}</div>
                          <div className="mt-1 text-[11px] text-slate-600 dark:text-slate-400">{Math.round((item.confidence || 0) * 100)}% confidence</div>
                        </td>
                        <td className="px-3 py-2 align-top">
                          {item.classification === 'requirement' ? (
                            <label className="flex items-center gap-2 text-slate-700 dark:text-slate-200">
                              <input
                                type="checkbox"
                                checked={Boolean(item.requirement_metadata?.is_mandatory)}
                                onChange={(event) => updateDecision(index, {
                                  requirement_metadata: {
                                    ...(item.requirement_metadata || {}),
                                    is_mandatory: event.target.checked,
                                  },
                                })}
                              />
                              Required in matrix
                            </label>
                          ) : (
                            <span className="text-slate-600 dark:text-slate-400">Project detail only</span>
                          )}
                        </td>
                        <td className="px-3 py-2 align-top">
                          {item.history_suggestion ? (
                            <Button size="sm" variant="outline" onClick={() => applyHistorySuggestion(index)}>
                              Apply {item.history_suggestion.canonical_label}
                            </Button>
                          ) : (
                            <span className="text-slate-600 dark:text-slate-400">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </GlassPanel>
        </div>
      )}

      {preview && (
        <GlassPanel className="mt-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Preview</h2>
            <Button
              size="sm"
              icon={CheckCircle2}
              disabled={hasInvalidRows || commitResult || !allRequirementWarningsConfirmed}
              onClick={() => handleCommit(hasRequirementWarnings)}
              loading={working}
            >
              {hasRequirementWarnings ? 'Apply Reviewed Import' : 'Apply Import'}
            </Button>
          </div>
          {summary?.requirements && (
            <div className="mb-3 grid grid-cols-2 gap-2 text-xs md:grid-cols-5">
              <div className="rounded border border-slate-200 p-2 dark:border-slate-700">Requirement cells: {summary.requirements.detected || 0}</div>
              <div className="rounded border border-slate-200 p-2 dark:border-slate-700">Matrix matches: {summary.requirements.matched_existing || 0}</div>
              <div className="rounded border border-slate-200 p-2 dark:border-slate-700">Imported matches: {summary.requirements.matched_imported || 0}</div>
              <div className="rounded border border-slate-200 p-2 dark:border-slate-700">New: {summary.requirements.new_imported || 0}</div>
              <div className="rounded border border-amber-200 bg-amber-50 p-2 text-amber-800 dark:border-amber-800/50 dark:bg-amber-950/30 dark:text-amber-200">Review: {summary.requirements.similar_warnings || 0}</div>
            </div>
          )}
          {requirementWarnings.length > 0 && (
            <div className="mb-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800/50 dark:bg-amber-950/30 dark:text-amber-100">
              <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="flex items-center gap-2 font-medium">
                    <AlertTriangle className="h-4 w-4" />
                    Review similar imported requirements
                  </div>
                  <p className="mt-1 text-xs text-amber-800 dark:text-amber-200">
                    Confirm each imported column only when it should remain separate from the existing requirement candidates.
                  </p>
                </div>
                <span className="rounded border border-amber-300 px-2 py-1 text-xs font-medium dark:border-amber-700">
                  {confirmedRequirementWarningCount}/{requirementWarnings.length} confirmed
                </span>
              </div>
              <div className="space-y-3">
                {requirementWarnings.map((item, index) => (
                  <div key={requirementWarningKey(item, index)} className="rounded border border-amber-200 bg-white/70 p-3 dark:border-amber-800/70 dark:bg-slate-950/30">
                    <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                      <div>
                        <div className="text-xs uppercase tracking-wide text-amber-700 dark:text-amber-300">Imported column</div>
                        <div className="font-semibold text-slate-900 dark:text-white">{item.standardized_name}</div>
                        {item.source_columns?.length > 0 && (
                          <div className="mt-1 text-xs text-amber-800 dark:text-amber-200">
                            Source column{item.source_columns.length > 1 ? 's' : ''}: {item.source_columns.join(', ')}
                          </div>
                        )}
                      </div>
                      <label className="flex items-center gap-2 rounded border border-amber-200 bg-amber-100/70 px-3 py-2 text-xs font-medium text-amber-950 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-100">
                        <input
                          type="checkbox"
                          checked={Boolean(confirmedRequirementWarnings[requirementWarningKey(item, index)])}
                          onChange={() => toggleRequirementWarning(item, index)}
                        />
                        Apply as separate
                      </label>
                    </div>
                    <div className="mt-3 grid gap-2 text-xs md:grid-cols-3">
                      <div className="rounded border border-amber-100 bg-amber-50/70 p-2 dark:border-amber-800/60 dark:bg-amber-950/20">
                        <span className="font-medium">Reason: </span>{item.reason}
                      </div>
                      <div className="rounded border border-amber-100 bg-amber-50/70 p-2 dark:border-amber-800/60 dark:bg-amber-950/20">
                        <span className="font-medium">Recommended: </span>{item.recommended_action}
                      </div>
                      <div className="rounded border border-amber-100 bg-amber-50/70 p-2 dark:border-amber-800/60 dark:bg-amber-950/20">
                        <span className="font-medium">Apply anyway: </span>{item.apply_anyway_effect}
                      </div>
                    </div>
                    <div className="mt-3 overflow-x-auto rounded border border-amber-200 dark:border-amber-800/60">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-amber-100/80 text-amber-950 dark:bg-amber-900/40 dark:text-amber-100">
                          <tr>
                            <th className="px-3 py-2 font-semibold">Existing requirement</th>
                            <th className="px-3 py-2 font-semibold">Phase</th>
                            <th className="px-3 py-2 font-semibold">Annex</th>
                            <th className="px-3 py-2 font-semibold">Reason</th>
                            <th className="px-3 py-2 font-semibold">Score</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-amber-100 dark:divide-amber-800/50">
                          {(item.candidates || []).map(candidate => (
                            <tr key={`${candidate.name}-${candidate.phase_name}-${candidate.annex_reference}`}>
                              <td className="px-3 py-2 align-top font-medium text-slate-900 dark:text-white">
                                {candidate.name}
                                {(candidate.occurrence_count || 0) > 1 && (
                                  <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-800 dark:bg-amber-900/50 dark:text-amber-100">
                                    Seen {candidate.occurrence_count}x
                                  </span>
                                )}
                              </td>
                              <td className="px-3 py-2 align-top">{candidate.phase_name || '—'}</td>
                              <td className="px-3 py-2 align-top">{candidate.annex_reference || '—'}</td>
                              <td className="px-3 py-2 align-top">{candidate.reason}</td>
                              <td className="px-3 py-2 align-top">{formatCandidateScore(candidate.score)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex justify-end">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!allRequirementWarningsConfirmed}
                  onClick={() => handleCommit(true)}
                  loading={working}
                >
                  Apply Import Anyway
                </Button>
              </div>
            </div>
          )}
          <DataTable columns={previewColumns} data={preview.rows || []} keyField="id" emptyMessage="No importable rows detected." />
        </GlassPanel>
      )}

      {commitResult && (
        <GlassPanel className="mt-4">
          <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Import Applied</h2>
            {commitResult.committed?.workbook_workspace_id && (
              <Button
                size="sm"
                icon={Table2}
                onClick={() => navigate(ROUTES.programCycleWorkbook(programId, cycleId))}
              >
                Open Workbook
              </Button>
            )}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div className="rounded border border-slate-200 dark:border-slate-700 p-3">Created: {commitResult.committed?.created_projects || 0}</div>
            <div className="rounded border border-slate-200 dark:border-slate-700 p-3">Updated: {commitResult.committed?.updated_projects || 0}</div>
            <div className="rounded border border-slate-200 dark:border-slate-700 p-3">Requirements: {commitResult.committed?.requirements || 0}</div>
            <div className="rounded border border-slate-200 dark:border-slate-700 p-3">Skipped: {commitResult.committed?.skipped || 0}</div>
          </div>
        </GlassPanel>
      )}
    </div>
  )
}
