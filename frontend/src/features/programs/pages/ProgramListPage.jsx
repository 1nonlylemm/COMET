import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Search, Plus, FolderKanban, ToggleLeft, ToggleRight, Upload } from 'lucide-react'
import { Button, CategoryBadge, DataTable, FeedbackToast, FormField, InlineAlert, KpiCard, Modal, PageHeader } from '../../../components'
import { isAdmin } from '../../../lib/auth'
import { ROUTES } from '../../../config/routes'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import { BatchImportModal } from '../../imports/components/BatchImportModal'
import { apiErrorMessage } from '../../../lib/formErrors'
import * as programApi from '../api/programApi'

const PROGRAM_TYPES = [
  { value: '', label: 'All Types' },
  { value: 'infrastructure', label: 'Infrastructure' },
  { value: 'non_infrastructure', label: 'Non-Infrastructure' },
  { value: 'hybrid', label: 'Hybrid' },
]

export default function ProgramListPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const initialType = searchParams.get('program_type') || ''
  const initialSearch = searchParams.get('search') || ''
  const [programs, setPrograms] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState(initialSearch)
  const [filterType, setFilterType] = useState(initialType)
  const [filterActive, setFilterActive] = useState('')
  const [page, setPage] = useState(1)
  const [meta, setMeta] = useState({ total: 0, pages: 1 })
  const [showCreate, setShowCreate] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [form, setForm] = useState({
    name: '', code: '', program_type: 'infrastructure',
    description: '', funding_agency: '',
  })
  const [formError, setFormError] = useState('')
  const [pageMessage, setPageMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [togglingId, setTogglingId] = useState(null)
  const [error, setError] = useState('')

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = { page, per_page: 20 }
      if (search) params.search = search
      if (filterType) params.program_type = filterType
      if (filterActive !== '') params.is_active = filterActive
      const res = await programApi.listPrograms(params)
      setPrograms(res.data || [])
      if (res.meta) setMeta(res.meta)
    } catch (err) {
      setError(apiErrorMessage(err, 'Unable to load programs. Please try again.'))
    } finally {
      setLoading(false)
    }
  }, [page, search, filterType, filterActive])

  useEffect(() => { fetchData() }, [fetchData])

  useEffect(() => {
    const t = searchParams.get('program_type') || ''
    const s = searchParams.get('search') || ''
    if (t) setFilterType(t)
    if (s) setSearch(s)
  }, [searchParams])

  const handleCreate = async (e) => {
    e.preventDefault()
    if (submitting) return
    if (!form.name.trim() || !form.code.trim()) {
      setFormError('Program name and code are required.')
      return
    }
    setSubmitting(true)
    try {
      const payload = { ...form }
      if (!payload.description) delete payload.description
      if (!payload.funding_agency) delete payload.funding_agency
      await programApi.createProgram(payload)
      setShowCreate(false)
      setForm({ name: '', code: '', program_type: 'infrastructure', description: '', funding_agency: '' })
      setFormError('')
      fetchData()
    } catch (err) {
      setFormError(err.response?.data?.message || 'Unable to create the program.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggle = async (prog) => {
    if (togglingId) return
    setTogglingId(prog.id)
    setFormError('')
    setPageMessage('')
    try {
      await programApi.toggleProgramActive(prog.id)
      setPageMessage(`Program ${prog.is_active ? 'deactivated' : 'activated'} successfully.`)
      fetchData()
    } catch (err) {
      setFormError(err.response?.data?.message || 'Unable to update the program status.')
    } finally {
      setTogglingId(null)
    }
  }

  const hasErrorNoData = Boolean(error && programs.length === 0)
  const displayTotal = hasErrorNoData ? '—' : (meta.total || programs.length)
  const activeCount = hasErrorNoData ? '—' : programs.filter(p => p.is_active).length
  const inactiveCount = hasErrorNoData ? '—' : (typeof activeCount === 'number' ? programs.length - activeCount : '—')
  const infraCount = hasErrorNoData ? '—' : programs.filter(p => p.program_type === 'infrastructure').length

  const columns = [
    { key: 'id', label: '#' },
    { key: 'name', label: 'Program Name' },
    {
      key: 'program_type', label: 'Type', render: (row) => (
        <CategoryBadge category="program_type" value={row.program_type} />
      )
    },
    { key: 'funding_agency', label: 'Funding Agency', render: (row) => row.funding_agency || '—' },
    {
      key: 'is_active', label: 'Status', render: (row) => (
        <span className={badgeClassForStatus(row.is_active ? 'active' : 'inactive')}>
          <span className={`status-dot ${row.is_active ? 'bg-emerald-600 dark:bg-emerald-300' : 'bg-slate-500 dark:bg-slate-300'}`} />
          {row.is_active ? 'Active' : 'Inactive'}
        </span>
      )
    },
    {
      key: 'actions', label: '', render: (row) => (
        <div className="flex items-center gap-2">
          <button onClick={() => navigate(ROUTES.programDetail(row.id))} className="action-link text-sm">
            View
          </button>
          {(isAdmin()) && (
            <button
              onClick={() => handleToggle(row)}
              disabled={togglingId === row.id}
              className={`text-slate-400 hover:text-amber-400 transition-colors ${togglingId === row.id ? 'opacity-50 cursor-not-allowed' : ''}`}
              title={row.is_active ? 'Deactivate' : 'Activate'}
            >
              {row.is_active ? <ToggleRight className="h-4 w-4 text-emerald-400" /> : <ToggleLeft className="h-4 w-4 text-red-400" />}
            </button>
          )}
        </div>
      )
    },
  ]

  return (
    <div>
      <PageHeader
        title="Programs, Cycles & Requirements"
        description="Manage DILG programs, funding-year cycles, phases, and documentary requirements."
        actions={isAdmin() && (
          <>
            <Button variant="outline" icon={Upload} onClick={() => { setFormError(''); setPageMessage(''); setShowImport(true) }}>Batch Import</Button>
            <Button icon={Plus} onClick={() => { setFormError(''); setPageMessage(''); setShowCreate(true) }}>Add Program</Button>
          </>
        )}
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <KpiCard title="Programs" value={displayTotal} subtitle="registered" icon={FolderKanban} color="blue" />
        <KpiCard title="Active" value={activeCount} subtitle="running" color="emerald" />
        <KpiCard title="Inactive" value={inactiveCount} subtitle="paused" color="red" />
        <KpiCard title="Infrastructure" value={infraCount} subtitle="programs" color="cyan" />
      </div>

      <FeedbackToast type="success" message={pageMessage} onDismiss={() => setPageMessage('')} />
      {error && (
        <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>
          <div className="flex items-center justify-between gap-3">
            <span>{error}</span>
            <Button size="sm" variant="outline" onClick={fetchData}>
              Retry
            </Button>
          </div>
        </InlineAlert>
      )}
      {!showCreate && (
        <InlineAlert type="error" className="mb-4" onDismiss={() => setFormError('')}>
          {formError}
        </InlineAlert>
      )}

      {/* Filters */}
      <div className="mb-4 flex flex-wrap gap-3">
        <form
          onSubmit={(e) => { e.preventDefault(); setPage(1); fetchData() }}
          className="flex min-w-[260px] flex-1 gap-2"
        >
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-600 dark:text-slate-400" />
            <input
              id="program-search"
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search programs..."
              className="input-field pl-10"
              aria-label="Search programs"
            />
          </div>
          <Button variant="outline" type="submit" className="self-center">Search</Button>
        </form>
        <select
          id="program-type-filter"
          value={filterType}
          onChange={(e) => { setFilterType(e.target.value); setPage(1) }}
          className="input-field w-auto min-w-[160px]"
          aria-label="Filter by program type"
        >
          {PROGRAM_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
        <select
          id="program-status-filter"
          value={filterActive}
          onChange={(e) => { setFilterActive(e.target.value); setPage(1) }}
          className="input-field w-auto"
          aria-label="Filter by status"
        >
          <option value="">All Status</option>
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>
      </div>

      <DataTable
        columns={columns}
        data={programs}
        keyField="id"
        isLoading={loading}
        emptyMessage={error ? 'Unable to load programs. Please retry.' : 'No programs found. Add a program before creating projects or importing workbook data.'}
        caption="Programs"
        hidePagination
        density="compact"
      />

      {/* Pagination */}
      {meta.pages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-4">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</Button>
          <span className="text-sm text-brand-text-muted">Page {page} of {meta.pages}</span>
          <Button variant="outline" size="sm" disabled={page >= meta.pages} onClick={() => setPage(p => p + 1)}>Next</Button>
        </div>
      )}

      {/* Create Modal */}
      <Modal
        open={showCreate}
        title="Add program"
        description="Create a program shell before adding cycles, phases, and documentary requirements."
        size="lg"
        onClose={() => setShowCreate(false)}
      >
            <InlineAlert type="error" className="mb-3" onDismiss={() => setFormError('')}>
              {formError}
            </InlineAlert>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <FormField id="program-name" label="Program name" required>
                  <input id="program-name" type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="input-field" placeholder="e.g. CMGP" />
                </FormField>
                <FormField id="program-code" label="Program code" required>
                  <input id="program-code" type="text" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} className="input-field" placeholder="e.g. CMGP" />
                </FormField>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <FormField id="program-type" label="Program type" required>
                  <select id="program-type" value={form.program_type} onChange={(e) => setForm({ ...form, program_type: e.target.value })} className="input-field">
                    <option value="infrastructure">Infrastructure</option>
                    <option value="non_infrastructure">Non-Infrastructure</option>
                    <option value="hybrid">Hybrid</option>
                  </select>
                </FormField>
                <FormField id="program-funding-agency" label="Funding agency">
                  <input id="program-funding-agency" type="text" value={form.funding_agency} onChange={(e) => setForm({ ...form, funding_agency: e.target.value })} className="input-field" placeholder="e.g. DILG" />
                </FormField>
              </div>
              <FormField id="program-description" label="Description">
                <textarea id="program-description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="input-field" rows={3} placeholder="Brief program description or issuance basis." />
              </FormField>
              <div className="flex gap-3 justify-end pt-2">
                <Button variant="outline" type="button" onClick={() => setShowCreate(false)}>Cancel</Button>
                <Button type="submit" loading={submitting} disabled={submitting}>Create Program</Button>
              </div>
            </form>
      </Modal>

      <BatchImportModal
        open={showImport}
        target="programs"
        title="Batch Import Programs"
        description="Create program records from a CSV or XLSX file. Duplicate program names or codes are skipped."
        onClose={() => setShowImport(false)}
        onImported={(result) => {
          setPageMessage(`Program import completed: ${result.summary.created || 0} created, ${result.summary.skipped || 0} skipped, ${result.summary.failed || 0} failed.`)
          fetchData()
        }}
      />
    </div>
  )
}
