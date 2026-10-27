import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Search, Plus, Building2, ToggleLeft, ToggleRight, Upload } from 'lucide-react'
import { Button, DataTable, FeedbackToast, FormField, InlineAlert, KpiCard, Modal, PageHeader } from '../../../components'
import { isAdmin } from '../../../lib/auth'
import { ROUTES } from '../../../config/routes'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import { BatchImportModal } from '../../imports/components/BatchImportModal'
import { apiErrorMessage } from '../../../lib/formErrors'
import * as lguApi from '../api/lguApi'

export default function LgusPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const initialCluster = searchParams.get('cluster_id') || ''
  const initialSearch = searchParams.get('search') || ''
  const initialActive = searchParams.get('is_active') || ''
  const [lgus, setLgus] = useState([])
  const [clusters, setClusters] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState(initialSearch)
  const [filterCluster, setFilterCluster] = useState(initialCluster)
  const [filterActive, setFilterActive] = useState(initialActive)
  const [page, setPage] = useState(1)
  const [meta, setMeta] = useState({ total: 0, pages: 1 })
  const [showCreate, setShowCreate] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [form, setForm] = useState({
    name: '', municipality: '', province: 'Laguna', cluster_id: '',
    mayor_name: '', mayor_email: '', contact_person: '', contact_email: '', contact_phone: ''
  })
  const [formError, setFormError] = useState('')
  const [pageMessage, setPageMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = { page, per_page: 20 }
      if (search) params.search = search
      if (filterCluster) params.cluster_id = filterCluster
      if (filterActive !== '') params.is_active = filterActive
      const res = await lguApi.listLgus(params)
      setLgus(res.data || [])
      if (res.meta) setMeta(res.meta)
    } catch (err) {
      setError(apiErrorMessage(err, 'Unable to load LGUs. Please try again.'))
    } finally {
      setLoading(false)
    }
  }, [page, search, filterCluster, filterActive])

  const fetchClusters = async () => {
    try {
      const res = await lguApi.listClusters()
      setClusters(res.data || [])
    } catch { setClusters([]) }
  }

  useEffect(() => { fetchClusters() }, [])
  useEffect(() => { fetchData() }, [fetchData])

  useEffect(() => {
    const c = searchParams.get('cluster_id') || ''
    const s = searchParams.get('search') || ''
    const a = searchParams.get('is_active') || ''
    if (c) setFilterCluster(c)
    if (s) setSearch(s)
    if (a) setFilterActive(a)
  }, [searchParams])

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!form.name.trim() || !form.municipality.trim()) {
      setFormError('LGU name and municipality are required.')
      return
    }
    setFormError('')
    setSubmitting(true)
    try {
      const payload = { ...form }
      if (payload.cluster_id) {
        payload.cluster_id = Number(payload.cluster_id)
      } else {
        delete payload.cluster_id
      }
      if (!payload.mayor_name) delete payload.mayor_name
      if (!payload.mayor_email) delete payload.mayor_email
      if (!payload.contact_person) delete payload.contact_person
      if (!payload.contact_email) delete payload.contact_email
      if (!payload.contact_phone) delete payload.contact_phone
      await lguApi.createLgu(payload)
      setFormError('')
      setShowCreate(false)
      setForm({ name: '', municipality: '', province: 'Laguna', cluster_id: '', mayor_name: '', mayor_email: '', contact_person: '', contact_email: '', contact_phone: '' })
      fetchData()
    } catch (err) {
      setFormError(err.response?.data?.message || 'Unable to add the LGU profile.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggle = async (lgu) => {
    setFormError('')
    setPageMessage('')
    try {
      await lguApi.toggleLguActive(lgu.id, !lgu.is_active)
      setPageMessage(`LGU profile ${lgu.is_active ? 'deactivated' : 'activated'} successfully.`)
      fetchData()
    } catch (err) {
      setFormError(err.response?.data?.message || 'Unable to update the LGU status.')
    }
  }

  const hasErrorNoData = Boolean(error && lgus.length === 0)
  const displayTotal = hasErrorNoData ? '—' : (meta.total || lgus.length)
  const activeCount = hasErrorNoData ? '—' : lgus.filter(l => l.is_active).length
  const inactiveCount = hasErrorNoData ? '—' : (typeof activeCount === 'number' ? lgus.length - activeCount : '—')
  const clusterCount = hasErrorNoData ? '—' : new Set(lgus.map(l => l.cluster_id).filter(Boolean)).size

  const columns = [
    { key: 'id', label: '#' },
    { key: 'name', label: 'LGU Name' },
    { key: 'municipality', label: 'Municipality' },
    { key: 'province', label: 'Province' },
    {
      key: 'cluster_name', label: 'Cluster', render: (row) => {
        const c = clusters.find(cl => cl.id === row.cluster_id)
        return c ? c.name : '—'
      }
    },
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
          <button onClick={() => navigate(ROUTES.lguDetail(row.id))} className="action-link text-sm">
            View
          </button>
          {isAdmin() && (
            <button onClick={() => handleToggle(row)} className="text-slate-400 hover:text-amber-400 transition-colors" title={row.is_active ? 'Deactivate' : 'Activate'}>
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
        title="LGUs & Assignments"
        description="Maintain LGU profiles, cluster assignment, and official contact details for Laguna Province."
        actions={(isAdmin()) && (
          <>
            <Button variant="outline" icon={Upload} onClick={() => { setFormError(''); setPageMessage(''); setShowImport(true) }}>Batch Import</Button>
            <Button icon={Plus} onClick={() => { setFormError(''); setPageMessage(''); setShowCreate(true) }}>Add LGU</Button>
          </>
        )}
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <KpiCard title="LGUs" value={displayTotal} subtitle="registered" icon={Building2} color="blue" />
        <KpiCard title="Active" value={activeCount} subtitle="registered" color="emerald" />
        <KpiCard title="Inactive" value={inactiveCount} subtitle="paused" color="red" />
        <KpiCard title="Clusters" value={clusterCount} subtitle="groupings" color="cyan" />
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
              id="lgu-search"
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search LGUs..."
              className="input-field pl-10"
              aria-label="Search LGUs"
            />
          </div>
          <Button variant="outline" type="submit" className="self-center">Search</Button>
        </form>
        <select
          id="lgu-cluster-filter"
          value={filterCluster}
          onChange={(e) => { setFilterCluster(e.target.value); setPage(1) }}
          className="input-field w-auto min-w-[180px]"
          aria-label="Filter by cluster"
        >
          <option value="">All Clusters</option>
          {clusters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select
          id="lgu-status-filter"
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
        data={lgus}
        keyField="id"
        isLoading={loading}
        emptyMessage={error ? 'Unable to load LGUs. Please retry.' : 'No LGUs found. Add an LGU profile before creating or importing projects.'}
        caption="LGUs"
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
        title="Add LGU profile"
        description="Create the LGU record used for assignments, projects, and contacts."
        size="lg"
        onClose={() => { setFormError(''); setShowCreate(false) }}
      >
            <InlineAlert type="error" className="mb-3" onDismiss={() => setFormError('')}>
              {formError}
            </InlineAlert>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <FormField id="lgu-name" label="LGU name" required>
                  <input id="lgu-name" type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="input-field" placeholder="LGU name" />
                </FormField>
                <FormField id="lgu-municipality" label="Municipality" required>
                  <input id="lgu-municipality" type="text" value={form.municipality} onChange={(e) => setForm({ ...form, municipality: e.target.value })} className="input-field" placeholder="Municipality" />
                </FormField>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <FormField id="lgu-province" label="Province">
                  <input id="lgu-province" type="text" value={form.province} onChange={(e) => setForm({ ...form, province: e.target.value })} className="input-field" />
                </FormField>
                <FormField id="lgu-cluster" label="Cluster">
                  <select id="lgu-cluster" value={form.cluster_id} onChange={(e) => setForm({ ...form, cluster_id: e.target.value })} className="input-field">
                    <option value="">— None —</option>
                    {clusters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </FormField>
              </div>
              <hr className="border-brand-border" />
              <p className="text-sm text-brand-text-muted">Official Contact Information (Optional)</p>
              <div className="grid grid-cols-2 gap-4">
                <FormField id="lgu-mayor-name" label="Mayor name">
                  <input id="lgu-mayor-name" type="text" value={form.mayor_name} onChange={(e) => setForm({ ...form, mayor_name: e.target.value })} className="input-field" />
                </FormField>
                <FormField id="lgu-mayor-email" label="Mayor email">
                  <input id="lgu-mayor-email" type="email" value={form.mayor_email} onChange={(e) => setForm({ ...form, mayor_email: e.target.value })} className="input-field" />
                </FormField>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <FormField id="lgu-contact-person" label="Contact person">
                  <input id="lgu-contact-person" type="text" value={form.contact_person} onChange={(e) => setForm({ ...form, contact_person: e.target.value })} className="input-field" />
                </FormField>
                <FormField id="lgu-contact-email" label="Contact email">
                  <input id="lgu-contact-email" type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} className="input-field" />
                </FormField>
              </div>
              <FormField id="lgu-contact-phone" label="Contact phone">
                <input id="lgu-contact-phone" type="text" value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} className="input-field" />
              </FormField>
              <div className="flex gap-3 justify-end pt-2">
                <Button variant="outline" type="button" onClick={() => setShowCreate(false)}>Cancel</Button>
                <Button type="submit" loading={submitting}>Save LGU Profile</Button>
              </div>
            </form>
      </Modal>

      <BatchImportModal
        open={showImport}
        target="lgus"
        title="Batch Import LGUs"
        description="Create LGU profiles from a CSV or XLSX file. Duplicate LGUs are skipped without blocking other rows."
        onClose={() => setShowImport(false)}
        onImported={(result) => {
          setPageMessage(`LGU import completed: ${result.summary.created || 0} created, ${result.summary.skipped || 0} skipped, ${result.summary.failed || 0} failed.`)
          fetchData()
          fetchClusters()
        }}
      />
    </div>
  )
}
