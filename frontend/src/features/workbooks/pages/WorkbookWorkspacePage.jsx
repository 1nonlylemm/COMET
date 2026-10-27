import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Calculator,
  Check,
  Columns3,
  Download,
  FileSpreadsheet,
  GitCompareArrows,
  History,
  Lock,
  Pin,
  PinOff,
  RefreshCw,
  Save,
  Settings2,
  Unlock,
  Upload,
  X,
} from 'lucide-react'
import { Breadcrumb, Button, EmptyState, FeedbackToast, FormField, GlassPanel, InlineAlert, KpiCard, Modal } from '../../../components'
import { ROUTES } from '../../../config/routes'
import { isAdmin } from '../../../lib/auth'
import { formatMachineLabel } from '../../../lib/formatters'
import * as programApi from '../../programs/api/programApi'
import * as workbookApi from '../api/workbookApi'
import { fileTransferErrorMessage } from '../../../lib/fileTransfer'
import { useBranding } from '../../../hooks/useBranding'

const ROW_HEADER_WIDTH = 56
const COLUMN_WIDTH = 176
const MIN_COLUMN_WIDTH = 96
const MAX_COLUMN_WIDTH = 520
const DISPLAY_FORMAT_OPTIONS = [
  { value: 'auto', label: 'Auto format' },
  { value: 'money', label: 'Money' },
  { value: 'year', label: 'Year' },
  { value: 'number', label: 'Number' },
]
const DATA_TYPE_OPTIONS = [
  { value: 'text', label: 'Text' },
  { value: 'number', label: 'Number' },
  { value: 'currency', label: 'Currency' },
  { value: 'percent', label: 'Percent' },
  { value: 'date', label: 'Date' },
  { value: 'datetime', label: 'Date and time' },
  { value: 'boolean', label: 'Boolean' },
  { value: 'status', label: 'Status' },
  { value: 'formula', label: 'Formula' },
  { value: 'json', label: 'JSON' },
]
const FORMULA_POLICY_OPTIONS = [
  { value: 'manual', label: 'Manual' },
  { value: 'preserve_only', label: 'Preserve only' },
  { value: 'system_calculated', label: 'System calculated' },
  { value: 'manual_override_allowed', label: 'Manual override allowed' },
]

const currencyFormatter = new Intl.NumberFormat('en-PH', {
  style: 'currency',
  currency: 'PHP',
  maximumFractionDigits: 2,
})

const AMOUNT_LABEL_PATTERN = /(amount|allocation|budget|cost|saro|subsidy|obligation|disbursement|balance|counterpart|unutilized|utilized)/

function normalizeColumnLabel(column) {
  return `${column?.display_label || ''} ${column?.normalized_header || ''} ${column?.binding_target || ''}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function numericValue(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value !== 'string') return null
  const cleaned = value.replace(/[,%\s]/g, '')
  if (!cleaned) return null
  const parsed = Number(cleaned)
  return Number.isFinite(parsed) ? parsed : null
}

function decimalPlacesFromFormat(numberFormat) {
  const decimalPart = String(numberFormat || '').match(/\.([0#]+)/)?.[1]
  if (!decimalPart) return null
  return {
    minimumFractionDigits: (decimalPart.match(/0/g) || []).length,
    maximumFractionDigits: decimalPart.length,
  }
}

function isYearColumn(column) {
  if (column?.display_format === 'year' || column?.binding_config?.display_format === 'year') return true
  const label = normalizeColumnLabel(column)
  return (
    column?.binding_target === 'program_cycle.fiscal_year'
    || label.includes('funding year')
    || label.includes('fiscal year')
    || label === 'year'
  )
}

function numericFormatOptions(column) {
  const displayFormat = column?.display_format || column?.binding_config?.display_format
  if (displayFormat === 'money') return { minimumFractionDigits: 2, maximumFractionDigits: 2 }
  if (displayFormat === 'number') return { maximumFractionDigits: 2 }
  const formatOptions = decimalPlacesFromFormat(column?.number_format)
  if (formatOptions) return formatOptions
  if (AMOUNT_LABEL_PATTERN.test(normalizeColumnLabel(column))) {
    return { minimumFractionDigits: 2, maximumFractionDigits: 2 }
  }
  return { maximumFractionDigits: 2 }
}

function formatNumberLikeValue(value, column) {
  const numeric = numericValue(value)
  if (numeric === null) return String(value)
  if (isYearColumn(column)) return String(Math.trunc(numeric))
  return new Intl.NumberFormat('en-PH', numericFormatOptions(column)).format(numeric)
}

function formatCellValue(cell, column) {
  const value = cell?.current_value ?? cell?.typed_value
  if (value === null || value === undefined || value === '') {
    return cell?.formula || ''
  }
  const displayFormat = column?.display_format || column?.binding_config?.display_format
  if (displayFormat === 'money') return formatNumberLikeValue(value, column)
  if (displayFormat === 'year') return formatNumberLikeValue(value, column)
  if (displayFormat === 'number') return formatNumberLikeValue(value, column)
  if (column?.data_type === 'currency') return currencyFormatter.format(Number(value) || 0)
  if (column?.data_type === 'percent') {
    const numeric = Number(value) || 0
    const percentOptions = decimalPlacesFromFormat(column?.number_format) || { maximumFractionDigits: 2 }
    return `${new Intl.NumberFormat('en-PH', percentOptions).format(Math.abs(numeric) <= 1 ? numeric * 100 : numeric)}%`
  }
  if (column?.data_type === 'number' || column?.data_type === 'formula') return formatNumberLikeValue(value, column)
  if (column?.data_type === 'boolean') return value ? 'Yes' : 'No'
  if (AMOUNT_LABEL_PATTERN.test(normalizeColumnLabel(column))) {
    const cleaned = String(value).replace(/,/g, '').trim()
    if (/^-?\d+(\.\d+)?$/.test(cleaned)) {
      return formatNumberLikeValue(value, column)
    }
  }
  return String(value)
}

function draftValue(cell) {
  const value = cell?.current_value ?? cell?.typed_value
  if (value === null || value === undefined) return ''
  return String(value)
}

function cellTone(cell, column) {
  if (cell?.is_editable) return 'bg-white text-brand-text hover:bg-blue-50 dark:bg-slate-950 dark:hover:bg-blue-950/40'
  if (cell?.formula || column?.is_formula) return 'bg-slate-50 text-slate-700 dark:bg-slate-900/60 dark:text-slate-200'
  return 'bg-slate-50 text-brand-text-muted dark:bg-slate-900/60'
}

function syncsToSystemRecord(bindingTarget) {
  return (
    ['project.project_name', 'project.budget_amount', 'project.overall_status', 'project.physical_completion_pct'].includes(bindingTarget)
    || bindingTarget?.startsWith('project.custom_fields.')
    || bindingTarget?.startsWith('project_requirement.status:')
  )
}

function columnSettingsFromColumn(column) {
  return {
    display_label: column?.display_label || column?.source_column || '',
    data_type: column?.data_type || 'text',
    number_format: column?.number_format || '',
    formula_text: column?.binding_config?.formula || '',
    binding_target: column?.binding_target || 'import_only',
    binding_config_text: JSON.stringify(column?.binding_config || {}, null, 2),
    validation_rules_text: JSON.stringify(column?.validation_rules || {}, null, 2),
    validation_options_text: (column?.validation_options || []).join('\n'),
    is_editable: Boolean(column?.is_editable),
    is_required: Boolean(column?.is_required),
    is_formula: Boolean(column?.is_formula),
    formula_policy: column?.formula_policy || 'manual',
  }
}

function parseJsonObject(text, label) {
  const trimmed = String(text || '').trim()
  if (!trimmed) return {}
  let parsed
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    throw new Error(`${label} must be valid JSON.`)
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error(`${label} must be a JSON object.`)
  }
  return parsed
}

function validationOptionsFromText(text) {
  return String(text || '')
    .split(/\r?\n/)
    .map(item => item.trim())
    .filter(Boolean)
}

function formatPlainValue(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'object') return JSON.stringify(value)
  if (typeof value === 'number') {
    if (Number.isInteger(value) && value >= 1900 && value <= 2100) return String(value)
    return value.toLocaleString('en-PH')
  }
  const str = String(value).trim()
  if (/^-?\d+(\.\d+)?$/.test(str) && !(str.length === 4 && Number(str) >= 1900 && Number(str) <= 2100)) {
    const num = Number(str)
    if (Number.isFinite(num)) {
      return num.toLocaleString('en-PH')
    }
  }
  return str
}

function formatDateTime(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('en-PH', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    })
  } catch {
    return value
  }
}

export default function WorkbookWorkspacePage() {
  const { programId, cycleId } = useParams()
  const navigate = useNavigate()
  const { branding } = useBranding()
  const [program, setProgram] = useState(null)
  const [cycle, setCycle] = useState(null)
  const [workspace, setWorkspace] = useState(null)
  const [sheets, setSheets] = useState([])
  const [activeSheetId, setActiveSheetId] = useState(null)
  const [grid, setGrid] = useState(null)
  const [selectedCell, setSelectedCell] = useState(null)
  const [editingCell, setEditingCell] = useState(null)
  const [draft, setDraft] = useState('')
  const [frozenColumnIds, setFrozenColumnIds] = useState([])
  const [selectedColumnIds, setSelectedColumnIds] = useState([])
  const [columnSelectionAnchorId, setColumnSelectionAnchorId] = useState(null)
  const [columnWidths, setColumnWidths] = useState({})
  const [columnSettingsColumn, setColumnSettingsColumn] = useState(null)
  const [columnSettingsForm, setColumnSettingsForm] = useState(columnSettingsFromColumn(null))
  const [columnSettingsError, setColumnSettingsError] = useState('')
  const [conflictModalOpen, setConflictModalOpen] = useState(false)
  const [conflicts, setConflicts] = useState([])
  const [conflictLoading, setConflictLoading] = useState(false)
  const [conflictError, setConflictError] = useState('')
  const [resolvingConflictId, setResolvingConflictId] = useState(null)
  const [cellHistory, setCellHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [resizingColumnId, setResizingColumnId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [gridLoading, setGridLoading] = useState(false)
  const [savingCellId, setSavingCellId] = useState(null)
  const [updatingColumnId, setUpdatingColumnId] = useState(null)
  const [savingColumnSettings, setSavingColumnSettings] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const canAdminEditColumns = isAdmin()
  const resizeStateRef = useRef(null)
  const exportingRef = useRef(false)

  const activeSheet = useMemo(
    () => sheets.find(sheet => String(sheet.id) === String(activeSheetId)) || null,
    [activeSheetId, sheets],
  )

  const columnWidthStorageKey = workspace && activeSheetId
    ? `system.workbook.${workspace.id}.sheet.${activeSheetId}.columnWidths`
    : null

  const getColumnWidth = useCallback(
    (column) => columnWidths[column.id] || COLUMN_WIDTH,
    [columnWidths],
  )

  const persistColumnWidths = useCallback((widths) => {
    if (!columnWidthStorageKey) return
    try {
      window.localStorage.setItem(columnWidthStorageKey, JSON.stringify(widths))
    } catch {
      // Local storage may be unavailable in private or restricted contexts.
    }
  }, [columnWidthStorageKey])

  useEffect(() => {
    if (!columnWidthStorageKey) {
      setColumnWidths({})
      return
    }
    try {
      const stored = window.localStorage.getItem(columnWidthStorageKey)
      setColumnWidths(stored ? JSON.parse(stored) : {})
    } catch {
      setColumnWidths({})
    }
  }, [columnWidthStorageKey])

  useEffect(() => {
    const handlePointerMove = (event) => {
      const resizeState = resizeStateRef.current
      if (!resizeState) return
      const nextWidth = Math.min(
        MAX_COLUMN_WIDTH,
        Math.max(MIN_COLUMN_WIDTH, resizeState.startWidth + event.clientX - resizeState.startX),
      )
      resizeState.currentWidth = nextWidth
      setColumnWidths(prev => ({ ...prev, [resizeState.columnId]: nextWidth }))
    }

    const handlePointerUp = () => {
      const resizeState = resizeStateRef.current
      if (!resizeState) return
      setColumnWidths(prev => {
        const next = { ...prev, [resizeState.columnId]: resizeState.currentWidth || resizeState.startWidth }
        persistColumnWidths(next)
        return next
      })
      resizeStateRef.current = null
      setResizingColumnId(null)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)
    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [persistColumnWidths])

  const loadContext = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [programRes, cyclesRes, workspaceRes] = await Promise.all([
        programApi.getProgram(programId),
        programApi.listProgramCycles(programId),
        workbookApi.listWorkspaces({ program_cycle_id: cycleId }),
      ])
      const foundCycle = (cyclesRes.data || []).find(item => String(item.id) === String(cycleId)) || null
      const foundWorkspace = (workspaceRes.data || [])[0] || null
      setProgram(programRes.data)
      setCycle(foundCycle)
      setWorkspace(foundWorkspace)
      if (foundWorkspace) {
        const sheetsRes = await workbookApi.listSheets(foundWorkspace.id)
        const loadedSheets = sheetsRes.data || []
        setSheets(loadedSheets)
        setActiveSheetId(prev => prev || loadedSheets[0]?.id || null)
      } else {
        setSheets([])
        setActiveSheetId(null)
        setGrid(null)
      }
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to load this workbook workspace.')
    } finally {
      setLoading(false)
    }
  }, [cycleId, programId])

  const loadGrid = useCallback(async () => {
    if (!workspace || !activeSheetId) return
    setGridLoading(true)
    setError('')
    try {
      const gridRes = await workbookApi.getSheetGrid(workspace.id, activeSheetId, { per_page: 200 })
      setGrid(gridRes.data)
      setFrozenColumnIds(prev => prev.filter(id => (gridRes.data?.columns || []).some(column => column.id === id)))
      setSelectedColumnIds(prev => prev.filter(id => (gridRes.data?.columns || []).some(column => column.id === id)))
      setSelectedCell(null)
      setEditingCell(null)
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to load this workbook sheet.')
    } finally {
      setGridLoading(false)
    }
  }, [activeSheetId, workspace])

  const loadConflicts = useCallback(async () => {
    if (!workspace) {
      setConflicts([])
      return
    }
    setConflictLoading(true)
    setConflictError('')
    try {
      const response = await workbookApi.listConflicts(workspace.id, { status: 'open', per_page: 100 })
      setConflicts(response.data?.items || [])
    } catch (err) {
      setConflictError(err.response?.data?.message || 'Unable to load workbook conflicts.')
      setConflicts([])
    } finally {
      setConflictLoading(false)
    }
  }, [workspace])

  const loadCellHistory = useCallback(async (cellId) => {
    if (!workspace || !cellId) {
      setCellHistory([])
      return
    }
    setHistoryLoading(true)
    try {
      const response = await workbookApi.listCellHistory(workspace.id, cellId, { per_page: 10 })
      setCellHistory(response.data?.items || [])
    } catch {
      setCellHistory([])
    } finally {
      setHistoryLoading(false)
    }
  }, [workspace])

  useEffect(() => { loadContext() }, [loadContext])
  useEffect(() => { loadGrid() }, [loadGrid])
  useEffect(() => { loadConflicts() }, [loadConflicts])
  useEffect(() => { loadCellHistory(selectedCell?.cell?.id) }, [loadCellHistory, selectedCell?.cell?.id])

  const startEditing = (row, column, cell) => {
    setSelectedCell({ row, column, cell })
    if (!cell?.is_editable) return
    setEditingCell({ rowId: row.id, columnId: column.id, cellId: cell.id })
    setDraft(draftValue(cell))
    setNotice('')
  }

  const toggleFrozenColumn = (column) => {
    setFrozenColumnIds(prev => (
      prev.includes(column.id)
        ? prev.filter(id => id !== column.id)
        : [...prev, column.id]
    ))
  }

  const selectColumn = (event, column) => {
    if (event.shiftKey && columnSelectionAnchorId) {
      const anchorIndex = columns.findIndex(item => item.id === columnSelectionAnchorId)
      const currentIndex = columns.findIndex(item => item.id === column.id)
      if (anchorIndex !== -1 && currentIndex !== -1) {
        const start = Math.min(anchorIndex, currentIndex)
        const end = Math.max(anchorIndex, currentIndex)
        setSelectedColumnIds(columns.slice(start, end + 1).map(item => item.id))
        return
      }
    }
    setSelectedColumnIds(prev => (
      prev.includes(column.id) && prev.length === 1 ? [] : [column.id]
    ))
    setColumnSelectionAnchorId(column.id)
  }

  const pinSelectedColumns = () => {
    setFrozenColumnIds(prev => {
      const next = [...prev]
      columns.forEach(column => {
        if (selectedColumnIds.includes(column.id) && !next.includes(column.id)) {
          next.push(column.id)
        }
      })
      return next
    })
  }

  const unpinSelectedColumns = () => {
    setFrozenColumnIds(prev => prev.filter(id => !selectedColumnIds.includes(id)))
  }

  const applySelectedColumnFormat = async (displayFormat) => {
    if (!workspace || !canAdminEditColumns || selectedColumnIds.length === 0) return
    setUpdatingColumnId('format')
    setError('')
    setNotice('')
    try {
      await Promise.all(
        selectedColumnIds.map(columnId => (
          workbookApi.updateColumn(workspace.id, columnId, { display_format: displayFormat })
        )),
      )
      setNotice(`Format applied to ${selectedColumnIds.length} column${selectedColumnIds.length === 1 ? '' : 's'}.`)
      await loadGrid()
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to update selected column formats.')
    } finally {
      setUpdatingColumnId(null)
    }
  }

  const openColumnSettings = (column) => {
    if (!column || !canAdminEditColumns) return
    setColumnSettingsColumn(column)
    setColumnSettingsForm(columnSettingsFromColumn(column))
    setColumnSettingsError('')
  }

  const closeColumnSettings = () => {
    setColumnSettingsColumn(null)
    setColumnSettingsError('')
  }

  const saveColumnSettings = async (event) => {
    event.preventDefault()
    if (!workspace || !columnSettingsColumn) return
    setSavingColumnSettings(true)
    setColumnSettingsError('')
    setError('')
    setNotice('')
    try {
      const bindingConfig = parseJsonObject(columnSettingsForm.binding_config_text, 'Binding config')
      const validationRules = parseJsonObject(columnSettingsForm.validation_rules_text, 'Validation rules')
      if (columnSettingsForm.formula_text?.trim()) {
        bindingConfig.formula = columnSettingsForm.formula_text.trim()
      } else {
        delete bindingConfig.formula
      }
      await workbookApi.updateColumn(workspace.id, columnSettingsColumn.id, {
        display_label: columnSettingsForm.display_label,
        data_type: columnSettingsForm.data_type,
        number_format: columnSettingsForm.number_format,
        binding_target: columnSettingsForm.binding_target,
        binding_config: bindingConfig,
        validation_rules: validationRules,
        validation_options: validationOptionsFromText(columnSettingsForm.validation_options_text),
        is_editable: columnSettingsForm.is_editable,
        is_required: columnSettingsForm.is_required,
        is_formula: columnSettingsForm.is_formula || columnSettingsForm.data_type === 'formula',
        formula_policy: columnSettingsForm.formula_policy,
      })
      setNotice(`${columnSettingsColumn.source_column} column settings saved.`)
      closeColumnSettings()
      await loadGrid()
    } catch (err) {
      setColumnSettingsError(err.response?.data?.message || err.message || 'Unable to update this workbook column.')
    } finally {
      setSavingColumnSettings(false)
    }
  }

  const startColumnResize = (event, column) => {
    event.preventDefault()
    event.stopPropagation()
    resizeStateRef.current = {
      columnId: column.id,
      startX: event.clientX,
      startWidth: getColumnWidth(column),
      currentWidth: getColumnWidth(column),
    }
    setResizingColumnId(column.id)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  const resetColumnWidth = (event, column) => {
    event.preventDefault()
    event.stopPropagation()
    setColumnWidths(prev => {
      const next = { ...prev }
      delete next[column.id]
      persistColumnWidths(next)
      return next
    })
  }

  const cancelEditing = () => {
    setEditingCell(null)
    setDraft('')
  }

  const toggleColumnEditability = async (column) => {
    if (!workspace || !canAdminEditColumns) return
    const nextEditable = !column.is_editable
    setUpdatingColumnId(column.id)
    setError('')
    setNotice('')
    try {
      await workbookApi.updateColumn(workspace.id, column.id, { is_editable: nextEditable })
      if (editingCell?.columnId === column.id && !nextEditable) {
        cancelEditing()
      }
      setNotice(nextEditable ? `${column.source_column} unlocked for workbook edits.` : `${column.source_column} locked as read-only.`)
      await loadGrid()
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to update this workbook column.')
    } finally {
      setUpdatingColumnId(null)
    }
  }

  const saveCell = async () => {
    if (!workspace || !editingCell) return
    setSavingCellId(editingCell.cellId)
    setError('')
    setNotice('')
    try {
      const res = await workbookApi.updateCell(workspace.id, editingCell.cellId, { value: draft })
      const updated = res.data
      setGrid(prev => ({
        ...prev,
        rows: (prev?.rows || []).map(row => {
          if (row.id !== editingCell.rowId) return row
          const nextCells = { ...row.cells }
          const sourceColumn = Object.entries(nextCells).find(([, cell]) => cell.id === editingCell.cellId)?.[0]
          if (sourceColumn) nextCells[sourceColumn] = updated
          return { ...row, cells: nextCells }
        }),
      }))
      setSelectedCell(prev => prev ? { ...prev, cell: updated } : prev)
      setEditingCell(null)
      setNotice(syncsToSystemRecord(selectedCell?.column?.binding_target) ? 'Cell saved and synced to the project record.' : 'Cell saved as a workbook override.')
      await loadCellHistory(updated.id)
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to save this cell.')
    } finally {
      setSavingCellId(null)
    }
  }

  const handleEditorKeyDown = (event) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      saveCell()
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      cancelEditing()
    }
  }

  const handleExportWorkbook = async () => {
    if (!workspace) return
    if (exportingRef.current) return
    exportingRef.current = true
    setExporting(true)
    setError('')
    setNotice('')
    try {
      const result = await workbookApi.exportWorkbook(workspace.id)
      const url = window.URL.createObjectURL(result.blob)
      const link = document.createElement('a')
      link.href = url
      link.download = result.filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      setNotice('Workbook export prepared from the current COMET-backed state.')
    } catch (err) {
      const errorMsg = await fileTransferErrorMessage(err, 'Unable to export this workbook.')
      setError(errorMsg)
    } finally {
      exportingRef.current = false
      setExporting(false)
    }
  }

  const resolveConflict = async (conflict, decision) => {
    if (!workspace || !conflict) return
    setResolvingConflictId(`${conflict.id}-${decision}`)
    setConflictError('')
    setError('')
    setNotice('')
    try {
      await workbookApi.resolveConflict(workspace.id, conflict.id, { decision })
      setNotice(decision === 'accept_import' ? 'Conflict resolved with the imported workbook value.' : `Conflict resolved by keeping the ${branding.app_name}-edited value.`)
      setWorkspace(prev => prev ? { ...prev, conflict_count: Math.max((prev.conflict_count || 0) - 1, 0) } : prev)
      await Promise.all([loadConflicts(), loadGrid()])
      if (selectedCell?.cell?.id === conflict.cell_id) {
        await loadCellHistory(conflict.cell_id)
      }
    } catch (err) {
      setConflictError(err.response?.data?.message || 'Unable to resolve this workbook conflict.')
    } finally {
      setResolvingConflictId(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-primary border-t-transparent" />
      </div>
    )
  }

  const columns = grid?.columns || []
  const rows = grid?.rows || []
  const editableColumnCount = columns.filter(column => column.is_editable).length
  const formulaColumnCount = columns.filter(column => column.is_formula).length
  const selectedColumns = columns.filter(column => selectedColumnIds.includes(column.id))
  const selectedFormat = selectedColumns.length > 0
    ? selectedColumns.reduce((format, column) => {
        const value = column.display_format || column.binding_config?.display_format || 'auto'
        if (format === null) return value
        return format === value ? format : 'mixed'
      }, null)
    : ''
  const frozenOffsets = columns.reduce((acc, column) => {
    if (frozenColumnIds.includes(column.id)) {
      acc.offsets[column.id] = acc.nextLeft
      acc.nextLeft += getColumnWidth(column)
    }
    return acc
  }, { offsets: {}, nextLeft: ROW_HEADER_WIDTH }).offsets

  return (
    <div className="animate-fade-in">
      <Breadcrumb
        items={[
          { label: 'Programs', to: ROUTES.PROGRAMS },
          { label: program?.name || 'Program', to: ROUTES.programDetail(programId) },
          { label: cycle?.name || 'Selected Cycle' },
          { label: 'Workbook Workbench' },
        ]}
      />

      <div className="mb-6 flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="page-title">Workbook Workbench</h1>
          <p className="mt-1 truncate text-sm text-brand-text-muted">
            {program?.name || 'Program'} {cycle ? `· ${cycle.name}` : ''}
          </p>
        </div>
        <Button variant="outline" icon={RefreshCw} onClick={() => { loadContext(); loadGrid() }}>
          Refresh
        </Button>
        {workspace && (
          <>
            <Button variant="outline" icon={Download} loading={exporting} onClick={handleExportWorkbook}>
              Export
            </Button>
            <Button
              variant={(workspace.conflict_count || conflicts.length) > 0 ? 'warning' : 'outline'}
              icon={GitCompareArrows}
              onClick={() => {
                setConflictModalOpen(true)
                loadConflicts()
              }}
            >
              Conflicts {workspace.conflict_count || conflicts.length || 0}
            </Button>
          </>
        )}
      </div>

      <FeedbackToast type="success" message={notice} onDismiss={() => setNotice('')} />
      <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>
        {error}
      </InlineAlert>

      {!workspace ? (
        <GlassPanel>
          <EmptyState
            icon={FileSpreadsheet}
            title="No workbook workspace yet"
            description="Import and apply a program-cycle workbook to create an editable workbench tied to project records."
            action={
              <Button icon={Upload} onClick={() => navigate(ROUTES.programCycleImport(programId, cycleId))}>
                Import Workbook
              </Button>
            }
          />
        </GlassPanel>
      ) : (
        <>
          <div className="mb-5 grid grid-cols-1 gap-4 md:grid-cols-4">
            <KpiCard title="Sheets" value={sheets.length} subtitle="in workbook" icon={FileSpreadsheet} color="blue" />
            <KpiCard title="Rows" value={grid?.total ?? activeSheet?.row_count ?? 0} subtitle="total" color="slate" />
            <KpiCard title="Editable" value={editableColumnCount} subtitle="columns" icon={Save} color="emerald" />
            <KpiCard title="Formulas" value={formulaColumnCount} subtitle="columns" icon={Calculator} color="amber" />
          </div>

          <GlassPanel noPadding className="mb-4 overflow-hidden">
            <div className="flex flex-col gap-3 border-b border-brand-border px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h2 className="section-title">{workspace.name}</h2>
                <p className="section-description">
                  Source batch #{workspace.source_import_batch_id} · {workspace.conflict_count || 0} open conflicts
                </p>
              </div>
              <div className="flex max-w-full gap-2 overflow-x-auto">
                {sheets.map(sheet => (
                  <button
                    key={sheet.id}
                    onClick={() => {
                      setActiveSheetId(sheet.id)
                      setFrozenColumnIds([])
                      setSelectedColumnIds([])
                      setColumnSelectionAnchorId(null)
                    }}
                    className={`rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                      String(sheet.id) === String(activeSheetId)
                        ? 'border-brand-primary bg-brand-primary text-white dark:bg-blue-500 dark:text-slate-950'
                        : 'border-brand-border bg-brand-surface-solid text-brand-text-muted hover:bg-brand-surface hover:text-brand-text'
                    }`}
                  >
                    {sheet.display_name}
                  </button>
                ))}
              </div>
            </div>

            {selectedColumns.length > 0 && (
              <div className="flex flex-col gap-3 border-b border-brand-border bg-brand-surface px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex items-center gap-2 text-sm text-brand-text">
                  <Columns3 className="h-4 w-4 text-brand-text-muted" />
                  <span className="font-medium">{selectedColumns.length} column{selectedColumns.length === 1 ? '' : 's'} selected</span>
                  <span className="hidden text-brand-text-muted sm:inline">Shift-click a header to select a range.</span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button size="sm" variant="outline" icon={Pin} onClick={pinSelectedColumns}>
                    Pin Selected
                  </Button>
                  <Button size="sm" variant="outline" icon={PinOff} onClick={unpinSelectedColumns}>
                    Unpin Selected
                  </Button>
                  {canAdminEditColumns && (
                    <>
                      {selectedColumns.length === 1 && (
                        <Button size="sm" variant="outline" icon={Settings2} onClick={() => openColumnSettings(selectedColumns[0])}>
                          Settings
                        </Button>
                      )}
                      <label className="flex items-center gap-2 text-sm text-brand-text-muted">
                        Format
                        <select
                          className="input-field h-9 min-w-36 py-1 text-sm"
                          value={selectedFormat || 'auto'}
                          onChange={(event) => applySelectedColumnFormat(event.target.value)}
                          disabled={updatingColumnId === 'format'}
                        >
                          {selectedFormat === 'mixed' && <option value="mixed" disabled>Mixed</option>}
                          {DISPLAY_FORMAT_OPTIONS.map(option => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                      </label>
                    </>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={X}
                    onClick={() => {
                      setSelectedColumnIds([])
                      setColumnSelectionAnchorId(null)
                    }}
                  >
                    Clear
                  </Button>
                </div>
              </div>
            )}

            <div className={`grid gap-0 ${selectedCell ? 'xl:grid-cols-[minmax(0,1fr)_320px]' : 'grid-cols-1'}`}>
              <div className="min-h-[520px] overflow-auto">
                {gridLoading ? (
                  <div className="flex min-h-[520px] items-center justify-center">
                    <div className="h-7 w-7 animate-spin rounded-full border-2 border-brand-primary border-t-transparent" />
                  </div>
                ) : rows.length === 0 ? (
                  <EmptyState
                    icon={FileSpreadsheet}
                    title="No rows visible"
                    description="This sheet has no imported rows available for your current access scope."
                  />
                ) : (
                  <table className="min-w-full border-separate border-spacing-0 text-sm">
                    <thead>
                      <tr>
                        <th
                          className="sticky left-0 top-0 z-40 h-10 border-b border-r border-brand-border bg-slate-100 px-2 text-xs font-semibold text-brand-text-muted dark:bg-slate-900"
                          style={{ width: ROW_HEADER_WIDTH, minWidth: ROW_HEADER_WIDTH, maxWidth: ROW_HEADER_WIDTH }}
                        >
                          Row
                        </th>
                        {columns.map(column => {
                          const frozen = frozenColumnIds.includes(column.id)
                          const selected = selectedColumnIds.includes(column.id)
                          const width = getColumnWidth(column)
                          return (
                            <th
                              key={column.id}
                              className={`sticky top-0 border-b border-r border-brand-border bg-slate-100 px-2 py-2 text-left align-bottom dark:bg-slate-900 ${
                                frozen ? 'z-30 shadow-[4px_0_0_rgba(148,163,184,0.28)]' : 'z-20'
                              } ${resizingColumnId === column.id ? 'ring-2 ring-inset ring-brand-primary/40' : ''} ${
                                selected ? 'bg-blue-50 ring-2 ring-inset ring-brand-primary/50 dark:bg-blue-950/40' : ''
                              }`}
                              onClick={(event) => selectColumn(event, column)}
                              style={{
                                width,
                                minWidth: width,
                                maxWidth: width,
                                ...(frozen ? { left: frozenOffsets[column.id] } : {}),
                              }}
                            >
                              <div className="flex items-center justify-between gap-2 pr-1">
                                <span className="text-xs font-semibold text-brand-text-muted">{column.source_column}</span>
                                <div className="flex items-center gap-1">
                                  {canAdminEditColumns && (
                                    <button
                                      type="button"
                                      className="icon-button h-7 w-7"
                                      onClick={(event) => {
                                        event.stopPropagation()
                                        openColumnSettings(column)
                                      }}
                                      title="Edit column settings"
                                      aria-label={`Edit settings for column ${column.source_column}`}
                                    >
                                      <Settings2 className="h-3.5 w-3.5" />
                                    </button>
                                  )}
                                  <button
                                    type="button"
                                    className={`icon-button h-7 w-7 ${frozen ? 'text-brand-primary' : ''}`}
                                    onClick={(event) => {
                                      event.stopPropagation()
                                      toggleFrozenColumn(column)
                                    }}
                                    title={frozen ? 'Unfreeze column' : 'Freeze column'}
                                    aria-label={frozen ? `Unfreeze column ${column.source_column}` : `Freeze column ${column.source_column}`}
                                  >
                                    {frozen ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
                                  </button>
                                  {column.is_formula && <Calculator className="h-3.5 w-3.5 text-brand-text-muted" aria-label="Formula column" />}
                                  {canAdminEditColumns ? (
                                    <button
                                      type="button"
                                      className={`icon-button h-7 w-7 ${column.is_editable ? 'text-emerald-600 dark:text-emerald-300' : ''}`}
                                      onClick={(event) => {
                                        event.stopPropagation()
                                        toggleColumnEditability(column)
                                      }}
                                      disabled={updatingColumnId === column.id}
                                      title={column.is_editable ? 'Lock column edits' : 'Unlock column edits'}
                                      aria-label={column.is_editable ? `Lock edits for column ${column.source_column}` : `Unlock edits for column ${column.source_column}`}
                                    >
                                      {column.is_editable ? <Unlock className="h-3.5 w-3.5" /> : <Lock className="h-3.5 w-3.5" />}
                                    </button>
                                  ) : !column.is_editable ? (
                                    <Lock className="h-3.5 w-3.5 text-brand-text-muted" aria-label="Read-only column" />
                                  ) : null}
                                </div>
                              </div>
                              <div className="mt-1 line-clamp-2 pr-2 text-xs font-semibold leading-4 text-brand-text">
                                {column.display_label || column.source_column}
                              </div>
                              <button
                                type="button"
                                className="absolute right-0 top-0 h-full w-2 cursor-col-resize border-0 bg-transparent p-0 hover:bg-brand-primary/20 focus:bg-brand-primary/30 focus:outline-none"
                                onPointerDown={(event) => startColumnResize(event, column)}
                                onDoubleClick={(event) => resetColumnWidth(event, column)}
                                title="Drag to resize column. Double-click to reset width."
                                aria-label={`Resize column ${column.source_column}`}
                              />
                          </th>
                          )
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map(row => (
                        <tr key={row.id}>
                          <th
                            className="sticky left-0 z-20 border-b border-r border-brand-border bg-slate-100 px-2 text-right text-xs font-semibold text-brand-text-muted dark:bg-slate-900"
                            style={{ width: ROW_HEADER_WIDTH, minWidth: ROW_HEADER_WIDTH, maxWidth: ROW_HEADER_WIDTH }}
                          >
                            {row.source_row_number}
                          </th>
                          {columns.map(column => {
                            const cell = row.cells[column.source_column]
                            const isEditing = Boolean(cell?.id && editingCell?.cellId === cell.id)
                            const isSelected = Boolean(cell?.id && selectedCell?.cell?.id === cell.id)
                            const frozen = frozenColumnIds.includes(column.id)
                            const width = getColumnWidth(column)
                            return (
                              <td
                                key={`${row.id}-${column.id}`}
                                className={`h-12 border-b border-r border-brand-border p-0 align-top ${cellTone(cell, column)} ${
                                  frozen ? 'sticky z-10 shadow-[4px_0_0_rgba(148,163,184,0.18)]' : ''
                                } ${isSelected ? 'ring-2 ring-inset ring-brand-primary/50' : ''}`}
                                style={{
                                  width,
                                  minWidth: width,
                                  maxWidth: width,
                                  ...(frozen ? { left: frozenOffsets[column.id] } : {}),
                                }}
                              >
                                {isEditing ? (
                                  <div className="flex h-full min-h-12 items-stretch">
                                    <input
                                      autoFocus
                                      className="min-h-12 min-w-0 flex-1 bg-white px-2 text-sm text-brand-text outline-none ring-2 ring-brand-primary/40 dark:bg-slate-950"
                                      value={draft}
                                      onChange={(event) => setDraft(event.target.value)}
                                      onKeyDown={handleEditorKeyDown}
                                      aria-label={`Edit cell ${cell.cell_ref || `${column.source_column} row ${row.source_row_number}`}`}
                                    />
                                    <button
                                      type="button"
                                      className="icon-button h-auto min-h-12 rounded-none border-0 border-l"
                                      onClick={saveCell}
                                      disabled={savingCellId === cell?.id}
                                      title="Save cell"
                                      aria-label={`Save cell ${cell.cell_ref || `${column.source_column} row ${row.source_row_number}`}`}
                                    >
                                      <Check className="h-4 w-4" aria-hidden="true" />
                                    </button>
                                    <button
                                      type="button"
                                      className="icon-button h-auto min-h-12 rounded-none border-0 border-l"
                                      onClick={cancelEditing}
                                      title="Cancel edit"
                                      aria-label={`Cancel editing cell ${cell.cell_ref || `${column.source_column} row ${row.source_row_number}`}`}
                                    >
                                      <X className="h-4 w-4" aria-hidden="true" />
                                    </button>
                                  </div>
                                ) : (
                                  <button
                                    type="button"
                                    className={`block h-full min-h-12 w-full px-2 py-2 text-left ${cell?.is_editable ? 'cursor-text' : 'cursor-default'}`}
                                    onClick={() => cell && startEditing(row, column, cell)}
                                    title={cell?.is_editable ? 'Edit cell' : column.is_formula ? 'Formula cell' : cell ? 'Read-only cell' : 'Blank read-only cell'}
                                    aria-label={`${cell?.is_editable ? 'Edit' : 'View'} cell ${cell?.cell_ref || `${column.source_column} row ${row.source_row_number}`}`}
                                  >
                                    <span className="block truncate">{formatCellValue(cell, column)}</span>
                                  </button>
                                )}
                              </td>
                            )
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              {selectedCell && (
                <aside className="border-t border-brand-border bg-brand-surface-solid p-4 xl:border-l xl:border-t-0">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-sm font-semibold text-brand-text">Cell Details</h3>
                    <button
                      type="button"
                      className="icon-button h-8 w-8"
                      onClick={() => setSelectedCell(null)}
                      title="Close cell details"
                      aria-label="Close cell details"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="mt-4 space-y-4 text-sm">
                    <div>
                      <p className="micro-text">Reference</p>
                      <p className="mt-1 font-medium text-brand-text">{selectedCell.cell.cell_ref}</p>
                    </div>
                    <div>
                      <p className="micro-text">Column</p>
                      <p className="mt-1 text-brand-text">{selectedCell.column.display_label}</p>
                    </div>
                    <div>
                      <p className="micro-text">Binding</p>
                      <p className="mt-1 text-brand-text">{formatMachineLabel(selectedCell.column.binding_target)}</p>
                    </div>
                    <div>
                      <p className="micro-text">Type</p>
                      <p className="mt-1 text-brand-text">{formatMachineLabel(selectedCell.column.data_type)}</p>
                    </div>
                    {selectedCell.cell.formula && (
                      <div>
                        <p className="micro-text">Formula</p>
                        <code className="mt-1 block rounded-md border border-brand-border bg-brand-surface p-2 text-xs text-brand-text">
                          {selectedCell.cell.formula}
                        </code>
                      </div>
                    )}
                    <div className="flex flex-wrap gap-2">
                      <span className={`status-badge ${selectedCell.cell.is_editable ? 'status-badge-success' : 'status-badge-neutral'}`}>
                        {selectedCell.cell.is_editable ? 'Editable' : 'Read-only'}
                      </span>
                      {selectedCell.cell.is_dirty && <span className="status-badge status-badge-warning">Edited</span>}
                    </div>
                    <div className="border-t border-brand-border pt-4">
                      <div className="flex items-center gap-2">
                        <History className="h-4 w-4 text-brand-text-muted" aria-hidden="true" />
                        <p className="text-sm font-semibold text-brand-text">Cell History</p>
                      </div>
                      {historyLoading ? (
                        <p className="mt-3 text-sm text-brand-text-muted">Loading history...</p>
                      ) : cellHistory.length === 0 ? (
                        <p className="mt-3 text-sm text-brand-text-muted">No edits recorded for this cell.</p>
                      ) : (
                        <div className="mt-3 space-y-3">
                          {cellHistory.map(change => (
                            <div key={change.id} className="rounded-md border border-brand-border bg-brand-surface p-3">
                              <div className="flex items-center justify-between gap-3">
                                <span className="status-badge status-badge-neutral">{formatMachineLabel(change.change_source)}</span>
                                <span className="text-xs text-brand-text-muted">{formatDateTime(change.changed_at)}</span>
                              </div>
                              <p className="mt-2 text-xs text-brand-text-muted">
                                {change.changed_by_name || 'System'} changed {formatPlainValue(change.old_value)} to {formatPlainValue(change.new_value)}
                              </p>
                              {change.reason && <p className="mt-1 text-xs text-brand-text-muted">Reason: {change.reason}</p>}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </aside>
              )}
            </div>
          </GlassPanel>
        </>
      )}

      <Modal
        open={Boolean(columnSettingsColumn)}
        title={columnSettingsColumn ? `Column ${columnSettingsColumn.source_column} Settings` : 'Column Settings'}
        onClose={closeColumnSettings}
        size="lg"
      >
        <InlineAlert type="error" className="mb-4" onDismiss={() => setColumnSettingsError('')}>
          {columnSettingsError}
        </InlineAlert>
        <form onSubmit={saveColumnSettings} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <FormField id="column-display-label" label="Column Label" required>
              <input
                id="column-display-label"
                className="input-field mt-1"
                value={columnSettingsForm.display_label}
                onChange={(event) => setColumnSettingsForm(prev => ({ ...prev, display_label: event.target.value }))}
              />
            </FormField>
            <FormField id="column-data-type" label="Data Type" required>
              <select
                id="column-data-type"
                className="input-field mt-1"
                value={columnSettingsForm.data_type}
                onChange={(event) => {
                  const nextType = event.target.value
                  setColumnSettingsForm(prev => ({
                    ...prev,
                    data_type: nextType,
                    is_formula: nextType === 'formula' ? true : prev.is_formula,
                  }))
                }}
              >
                {DATA_TYPE_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </FormField>
            <FormField id="column-number-format" label="Number Format">
              <input
                id="column-number-format"
                className="input-field mt-1"
                value={columnSettingsForm.number_format}
                onChange={(event) => setColumnSettingsForm(prev => ({ ...prev, number_format: event.target.value }))}
              />
            </FormField>
            <FormField id="column-formula-policy" label="Formula Policy">
              <select
                id="column-formula-policy"
                className="input-field mt-1"
                value={columnSettingsForm.formula_policy}
                onChange={(event) => setColumnSettingsForm(prev => ({ ...prev, formula_policy: event.target.value }))}
              >
                {FORMULA_POLICY_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </FormField>
          </div>

          <FormField id="column-formula-text" label="Formula Text">
            <input
              id="column-formula-text"
              className="input-field mt-1 font-mono text-sm"
              value={columnSettingsForm.formula_text}
              onChange={(event) => setColumnSettingsForm(prev => ({ ...prev, formula_text: event.target.value }))}
            />
          </FormField>

          <FormField id="column-binding-target" label="Binding Target">
            <input
              id="column-binding-target"
              className="input-field mt-1"
              value={columnSettingsForm.binding_target}
              onChange={(event) => setColumnSettingsForm(prev => ({ ...prev, binding_target: event.target.value }))}
            />
          </FormField>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="flex items-center gap-2 rounded-md border border-brand-border bg-brand-surface px-3 py-2 text-sm text-brand-text">
              <input
                type="checkbox"
                className="rounded border-slate-300 bg-white text-brand-primary focus:ring-brand-primary dark:border-slate-600 dark:bg-slate-800"
                checked={columnSettingsForm.is_editable}
                onChange={(event) => setColumnSettingsForm(prev => ({ ...prev, is_editable: event.target.checked }))}
              />
              Editable
            </label>
            <label className="flex items-center gap-2 rounded-md border border-brand-border bg-brand-surface px-3 py-2 text-sm text-brand-text">
              <input
                type="checkbox"
                className="rounded border-slate-300 bg-white text-brand-primary focus:ring-brand-primary dark:border-slate-600 dark:bg-slate-800"
                checked={columnSettingsForm.is_required}
                onChange={(event) => setColumnSettingsForm(prev => ({ ...prev, is_required: event.target.checked }))}
              />
              Required
            </label>
            <label className="flex items-center gap-2 rounded-md border border-brand-border bg-brand-surface px-3 py-2 text-sm text-brand-text">
              <input
                type="checkbox"
                className="rounded border-slate-300 bg-white text-brand-primary focus:ring-brand-primary dark:border-slate-600 dark:bg-slate-800"
                checked={columnSettingsForm.is_formula}
                onChange={(event) => setColumnSettingsForm(prev => ({
                  ...prev,
                  is_formula: event.target.checked,
                  data_type: event.target.checked ? 'formula' : (prev.data_type === 'formula' ? 'text' : prev.data_type),
                }))}
              />
              Formula
            </label>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <FormField id="column-binding-config" label="Binding Config">
              <textarea
                id="column-binding-config"
                className="input-field mt-1 font-mono text-xs"
                rows={5}
                value={columnSettingsForm.binding_config_text}
                onChange={(event) => setColumnSettingsForm(prev => ({ ...prev, binding_config_text: event.target.value }))}
              />
            </FormField>
            <FormField id="column-validation-rules" label="Validation Rules">
              <textarea
                id="column-validation-rules"
                className="input-field mt-1 font-mono text-xs"
                rows={5}
                value={columnSettingsForm.validation_rules_text}
                onChange={(event) => setColumnSettingsForm(prev => ({ ...prev, validation_rules_text: event.target.value }))}
              />
            </FormField>
          </div>

          <FormField id="column-validation-options" label="Validation Options">
            <textarea
              id="column-validation-options"
              className="input-field mt-1"
              rows={4}
              value={columnSettingsForm.validation_options_text}
              onChange={(event) => setColumnSettingsForm(prev => ({ ...prev, validation_options_text: event.target.value }))}
            />
          </FormField>

          <div className="flex justify-end gap-3 pt-2">
            <Button variant="outline" onClick={closeColumnSettings}>Cancel</Button>
            <Button type="submit" loading={savingColumnSettings}>Save Column</Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={conflictModalOpen}
        title="Re-import Conflicts"
        description={`Resolve cells where a re-import touched values already edited inside ${branding.app_name}.`}
        onClose={() => setConflictModalOpen(false)}
        size="xl"
      >
        <InlineAlert type="error" className="mb-4" onDismiss={() => setConflictError('')}>
          {conflictError}
        </InlineAlert>

        {conflictLoading ? (
          <div className="flex min-h-40 items-center justify-center">
            <div className="h-7 w-7 animate-spin rounded-full border-2 border-brand-primary border-t-transparent" />
          </div>
        ) : conflicts.length === 0 ? (
          <EmptyState
            icon={GitCompareArrows}
            title="No open workbook conflicts"
            description={`Re-import conflicts will appear here when source workbook values overlap with ${branding.app_name}-edited cells.`}
          />
        ) : (
          <div className="space-y-3">
            {conflicts.map(conflict => (
              <div key={conflict.id} className="rounded-md border border-brand-border bg-brand-surface p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-brand-text">
                      {conflict.cell_ref} · {conflict.column_label}
                    </p>
                    <p className="mt-1 text-xs text-brand-text-muted">
                      Row {conflict.source_row_number} · {formatMachineLabel(conflict.binding_target)}
                    </p>
                  </div>
                  <span className="status-badge status-badge-warning">{formatMachineLabel(conflict.conflict_type)}</span>
                </div>
                <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
                  <div className="rounded-md border border-brand-border bg-brand-surface-solid p-3">
                    <p className="micro-text">Previous Source</p>
                    <p className="mt-1 break-words text-sm text-brand-text">{formatPlainValue(conflict.source_value)}</p>
                  </div>
                  <div className="rounded-md border border-brand-border bg-brand-surface-solid p-3">
                    <p className="micro-text">{branding.app_name} Value</p>
                    <p className="mt-1 break-words text-sm font-semibold text-brand-text">{formatPlainValue(conflict.current_value)}</p>
                  </div>
                  <div className="rounded-md border border-brand-border bg-brand-surface-solid p-3">
                    <p className="micro-text">Incoming Workbook</p>
                    <p className="mt-1 break-words text-sm font-semibold text-brand-text">{formatPlainValue(conflict.incoming_value)}</p>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap justify-end gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    loading={resolvingConflictId === `${conflict.id}-keep_comet`}
                    onClick={() => resolveConflict(conflict, 'keep_comet')}
                  >
                    Keep {branding.app_name} Value
                  </Button>
                  <Button
                    size="sm"
                    loading={resolvingConflictId === `${conflict.id}-accept_import`}
                    onClick={() => resolveConflict(conflict, 'accept_import')}
                  >
                    Accept Import Value
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Modal>
    </div>
  )
}
