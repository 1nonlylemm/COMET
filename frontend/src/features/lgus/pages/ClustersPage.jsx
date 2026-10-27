import { useCallback, useEffect, useState } from 'react'
import { Search, Plus, Edit2, Trash2, Upload, Network, Building2, CircleOff, Link2 } from 'lucide-react'
import { Button, DataTable, FeedbackToast, FormField, InlineAlert, KpiCard, Modal, PageHeader } from '../../../components'
import { isAdmin } from '../../../lib/auth'
import { apiErrorMessage } from '../../../lib/formErrors'
import { BatchImportModal } from '../../imports/components/BatchImportModal'
import * as lguApi from '../api/lguApi'

const EMPTY_CLUSTER_FORM = { name: '', description: '', lgu_ids: [] }

export default function ClustersPage() {
  const [clusters, setClusters] = useState([])
  const [lgus, setLgus] = useState([])
  const [search, setSearch] = useState('')
  const [coverageFilter, setCoverageFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [pendingDelete, setPendingDelete] = useState(null)
  const [editingCluster, setEditingCluster] = useState(null)
  const [form, setForm] = useState(EMPTY_CLUSTER_FORM)
  const [formError, setFormError] = useState('')
  const [pageMessage, setPageMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const fetchClusters = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await lguApi.listClusters(search)
      setClusters(res.data || [])
    } catch (err) {
      setError(apiErrorMessage(err, 'Unable to load clusters. Please try again.'))
    } finally {
      setLoading(false)
    }
  }, [search])

  const fetchLgus = useCallback(async () => {
    try {
      const res = await lguApi.listLgus({ per_page: 500 })
      setLgus(res.data || [])
    } catch {
      setLgus([])
    }
  }, [])

  useEffect(() => { fetchClusters() }, [fetchClusters])
  useEffect(() => { fetchLgus() }, [fetchLgus])

  const handleSearch = (e) => {
    e.preventDefault()
    fetchClusters()
  }

  const openCreate = () => {
    setEditingCluster(null)
    setForm(EMPTY_CLUSTER_FORM)
    setFormError('')
    setPageMessage('')
    setShowModal(true)
  }

  const openEdit = (cluster) => {
    setEditingCluster(cluster)
    setForm({
      name: cluster.name,
      description: cluster.description || '',
      lgu_ids: lgus
        .filter((lgu) => Number(lgu.cluster_id) === Number(cluster.id))
        .map((lgu) => lgu.id),
    })
    setFormError('')
    setPageMessage('')
    setShowModal(true)
  }

  const handleLguToggle = (lguId) => {
    const exists = form.lgu_ids.includes(lguId)
    setForm({
      ...form,
      lgu_ids: exists
        ? form.lgu_ids.filter((id) => id !== lguId)
        : [...form.lgu_ids, lguId],
    })
  }

  const saveClusterLguAssignments = async (clusterId, selectedLguIds) => {
    const selectedIds = new Set(selectedLguIds.map((lguId) => Number(lguId)))
    const currentClusterId = Number(clusterId)

    const assignmentUpdates = lgus
      .filter((lgu) => {
        const lguId = Number(lgu.id)
        const lguClusterId = lgu.cluster_id ? Number(lgu.cluster_id) : null
        const shouldBelongHere = selectedIds.has(lguId)
        const currentlyBelongsHere = lguClusterId === currentClusterId
        return (shouldBelongHere && !currentlyBelongsHere) || (!shouldBelongHere && currentlyBelongsHere)
      })
      .map((lgu) => {
        const nextClusterId = selectedIds.has(Number(lgu.id)) ? currentClusterId : null
        return lguApi.updateLgu(lgu.id, { cluster_id: nextClusterId })
      })

    await Promise.all(assignmentUpdates)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) {
      setFormError('Cluster name is required.')
      return
    }
    setSubmitting(true)
    try {
      const clusterPayload = {
        name: form.name,
        description: form.description,
      }
      if (editingCluster) {
        await lguApi.updateCluster(editingCluster.id, clusterPayload)
        await saveClusterLguAssignments(editingCluster.id, form.lgu_ids)
      } else {
        const response = await lguApi.createCluster(clusterPayload)
        if (form.lgu_ids.length && response.data?.id) {
          await saveClusterLguAssignments(response.data.id, form.lgu_ids)
        }
      }
      setShowModal(false)
      setPageMessage(editingCluster ? 'Cluster updated successfully.' : 'Cluster created successfully.')
      await Promise.all([fetchClusters(), fetchLgus()])
    } catch (err) {
      setFormError(err.response?.data?.message || 'Unable to save the cluster.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (cluster) => {
    setPendingDelete(cluster)
  }

  const confirmDelete = async () => {
    if (!pendingDelete) return
    setFormError('')
    setPageMessage('')
    try {
      await lguApi.deleteCluster(pendingDelete.id)
      setPendingDelete(null)
      setPageMessage('Cluster deleted successfully.')
      await Promise.all([fetchClusters(), fetchLgus()])
    } catch (err) {
      setFormError(err.response?.data?.message || 'Unable to delete the cluster.')
    }
  }

  const clusterNameFor = (clusterId) => {
    const cluster = clusters.find((item) => Number(item.id) === Number(clusterId))
    return cluster?.name || 'Unassigned'
  }

  const hasErrorNoData = Boolean(error && clusters.length === 0)
  const assignedLguCount = lgus.filter((lgu) => Boolean(lgu.cluster_id)).length
  const unassignedLguCount = lgus.length - assignedLguCount
  const emptyClusterCount = clusters.filter((cluster) => Number(cluster.lgus_count || 0) === 0).length
  const filteredClusters = clusters.filter((cluster) => {
    const lguCount = Number(cluster.lgus_count || 0)
    if (coverageFilter === 'with_lgus') return lguCount > 0
    if (coverageFilter === 'empty') return lguCount === 0
    return true
  })
  const clusterEmptyMessage = error
    ? 'Unable to load clusters. Please retry.'
    : coverageFilter === 'empty'
      ? 'No empty clusters found. Every visible cluster already has LGU coverage.'
      : coverageFilter === 'with_lgus'
        ? 'No clusters with assigned LGUs found. Assign LGUs from the cluster edit modal.'
        : 'No clusters found. Add a cluster before assigning staff or cluster-scoped admins.'

  const columns = [
    { key: 'id', label: '#' },
    { key: 'name', label: 'Cluster Name' },
    { key: 'description', label: 'Description', render: (row) => row.description || '—' },
    { key: 'lgus_count', label: 'LGUs', render: (row) => row.lgus_count ?? '—' },
    {
      key: 'actions', label: '', render: (row) => isAdmin() ? (
        <div className="flex gap-2">
          <button
            onClick={() => openEdit(row)}
            className="text-brand-text-muted transition-colors hover:text-brand-primary"
            aria-label={`Edit cluster ${row.name}`}
            title="Edit cluster"
          >
            <Edit2 className="h-4 w-4" />
          </button>
          <button
            onClick={() => handleDelete(row)}
            className="text-brand-text-muted transition-colors hover:text-red-700 dark:hover:text-red-200"
            aria-label={`Delete cluster ${row.name}`}
            title="Delete cluster"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      ) : '—'
    },
  ]

  return (
    <div>
      <PageHeader
        title="LGU Clusters"
        description="Maintain cluster groupings used for field-side and PDMU assignment coverage."
        actions={isAdmin() && (
          <>
            <Button variant="outline" icon={Upload} onClick={() => { setFormError(''); setPageMessage(''); setShowImport(true) }}>Batch Import</Button>
            <Button icon={Plus} onClick={openCreate}>New Cluster</Button>
          </>
        )}
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4 mb-6">
        <KpiCard title="Clusters" value={hasErrorNoData ? '—' : clusters.length} subtitle="groupings" icon={Network} color="blue" />
        <KpiCard title="Assigned LGUs" value={hasErrorNoData ? '—' : assignedLguCount} subtitle={`of ${lgus.length} LGUs`} icon={Link2} color="emerald" />
        <KpiCard title="Unassigned LGUs" value={hasErrorNoData ? '—' : unassignedLguCount} subtitle="need coverage" icon={Building2} color="amber" />
        <KpiCard title="Empty Clusters" value={hasErrorNoData ? '—' : emptyClusterCount} subtitle="no LGU members" icon={CircleOff} color="slate" />
      </div>

      <FeedbackToast type="success" message={pageMessage} onDismiss={() => setPageMessage('')} />
      {error && (
        <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>
          <div className="flex items-center justify-between gap-3">
            <span>{error}</span>
            <Button size="sm" variant="outline" onClick={() => { fetchClusters(); fetchLgus() }}>
              Retry
            </Button>
          </div>
        </InlineAlert>
      )}
      {!showModal && (
        <InlineAlert type="error" className="mb-4" onDismiss={() => setFormError('')}>
          {formError}
        </InlineAlert>
      )}

      <div className="mb-4 flex flex-wrap gap-3">
        <form onSubmit={handleSearch} className="flex min-w-[260px] flex-1 gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-600 dark:text-slate-400" />
            <input
              id="cluster-search"
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search clusters..."
              className="input-field pl-10"
              aria-label="Search clusters"
            />
          </div>
          <Button variant="outline" type="submit" className="self-center">Search</Button>
        </form>
        <select
          id="cluster-coverage-filter"
          value={coverageFilter}
          onChange={(e) => setCoverageFilter(e.target.value)}
          className="input-field w-auto min-w-[180px]"
          aria-label="Filter by coverage"
        >
          <option value="">All Clusters</option>
          <option value="with_lgus">With LGUs</option>
          <option value="empty">Empty Clusters</option>
        </select>
      </div>

      <DataTable
        columns={columns}
        data={filteredClusters}
        keyField="id"
        isLoading={loading}
        emptyMessage={clusterEmptyMessage}
        caption="LGU clusters"
        density="compact"
      />

      <Modal
        open={showModal && isAdmin()}
        title={editingCluster ? 'Edit cluster' : 'Create cluster'}
        description="Manage the cluster record and the LGUs assigned to it."
        size="xl"
        onClose={() => setShowModal(false)}
      >
            <InlineAlert type="error" className="mb-3" onDismiss={() => setFormError('')}>
              {formError}
            </InlineAlert>
            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
                <div className="space-y-4">
                  <FormField id="cluster-name" label="Name" required>
                    <input
                      id="cluster-name"
                      type="text"
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                      className="input-field"
                      placeholder="e.g. Cluster 1 - First District"
                      autoFocus
                    />
                  </FormField>
                  <FormField id="cluster-description" label="Description">
                    <textarea
                      id="cluster-description"
                      value={form.description}
                      onChange={(e) => setForm({ ...form, description: e.target.value })}
                      className="input-field min-h-[128px]"
                      placeholder="Optional description..."
                    />
                  </FormField>
                </div>

                <div>
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <div>
                      <p className="label-text mb-0">Assigned LGUs</p>
                      <p className="text-xs text-brand-text-muted">
                        Selecting an LGU here moves it into this cluster. Deselecting an existing member leaves it unassigned.
                      </p>
                    </div>
                    <span className="text-xs font-medium text-brand-text-muted">
                      {form.lgu_ids.length} selected
                    </span>
                  </div>
                  <div className="max-h-80 overflow-y-auto rounded-lg border border-brand-border bg-brand-surface-solid">
                    {lgus.length ? (
                      lgus.map((lgu) => {
                        const checked = form.lgu_ids.includes(lgu.id)
                        const currentCluster = lgu.cluster_id ? clusterNameFor(lgu.cluster_id) : 'Unassigned'
                        return (
                          <label
                            key={lgu.id}
                            className="flex min-h-12 items-start gap-3 border-b border-brand-border px-3 py-2 text-sm last:border-b-0 hover:bg-brand-surface"
                          >
                            <input
                              type="checkbox"
                              className="mt-1"
                              checked={checked}
                              onChange={() => handleLguToggle(lgu.id)}
                            />
                            <span className="min-w-0">
                              <span className="block font-medium text-brand-text">{lgu.name}</span>
                              <span className="block text-xs text-brand-text-muted">
                                {lgu.municipality}, {lgu.province} · Current: {currentCluster}
                              </span>
                            </span>
                          </label>
                        )
                      })
                    ) : (
                      <p className="px-3 py-4 text-sm text-brand-text-muted">
                        No LGUs are available yet. Create LGU profiles before assigning them to clusters.
                      </p>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex gap-3 justify-end">
                <Button variant="outline" type="button" onClick={() => setShowModal(false)}>Cancel</Button>
                <Button type="submit" loading={submitting}>
                  {editingCluster ? 'Update Cluster' : 'Create Cluster'}
                </Button>
              </div>
            </form>
      </Modal>

      <Modal
        open={Boolean(pendingDelete)}
        title="Delete cluster"
        description={pendingDelete ? `Delete "${pendingDelete.name}"? This cannot be undone.` : ''}
        onClose={() => setPendingDelete(null)}
        footer={
          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setPendingDelete(null)}>Cancel</Button>
            <Button variant="danger" onClick={confirmDelete}>Delete Cluster</Button>
          </div>
        }
      >
        <p className="text-sm text-brand-text-muted">
          Delete only when this cluster is no longer referenced by active LGU assignments or staff coverage.
        </p>
      </Modal>

      <BatchImportModal
        open={showImport}
        target="clusters"
        title="Batch Import LGU Clusters"
        description="Create cluster records from a CSV or XLSX file. Existing cluster names are skipped."
        onClose={() => setShowImport(false)}
        onImported={(result) => {
          setPageMessage(`Cluster import completed: ${result.summary.created || 0} created, ${result.summary.skipped || 0} skipped, ${result.summary.failed || 0} failed.`)
          fetchClusters()
          fetchLgus()
        }}
      />
    </div>
  )
}
