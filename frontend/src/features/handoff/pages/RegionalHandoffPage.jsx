import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  File,
  Folder,
  FolderPlus,
  Home,
  MoveRight,
  RefreshCw,
  Search,
  TriangleAlert,
  Upload,
  X,
} from 'lucide-react'
import {
  Button,
  DataTable,
  FormField,
  GlassPanel,
  InlineAlert,
  KpiCard,
  Modal,
  useToast,
  ConfirmationModal,
} from '../../../components'
import { isAdmin, isStaff } from '../../../lib/auth'
import { formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import * as projectApi from '../../projects/api/projectApi'
import * as driveApi from '../api/driveApi'

const WORKSPACE_TAB = 'workspace'
const QUEUE_TAB = 'queue'

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

function formatDateTime(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('en-PH', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return value
  }
}

function formatFileSize(value) {
  const size = Number(value || 0)
  if (!size) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let amount = size
  let index = 0
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024
    index += 1
  }
  return `${amount.toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

function pushStatusBadge(push) {
  const status = push?.push_status || 'not_started'
  return (
    <span className={badgeClassForStatus(status)}>
      {formatStatus(status)}
    </span>
  )
}

function DriveItemName({ item, onOpen }) {
  const Icon = item.is_folder ? Folder : File
  const content = (
    <span className="inline-flex min-w-0 items-center gap-2">
      <Icon className={`h-4 w-4 shrink-0 ${item.is_folder ? 'text-amber-600 dark:text-amber-300' : 'text-slate-600 dark:text-slate-400'}`} />
      <span className="truncate font-medium text-brand-text">{item.name || 'Untitled'}</span>
    </span>
  )

  if (!item.is_folder) {
    return content
  }

  return (
    <button
      type="button"
      onClick={() => onOpen(item)}
      className="inline-flex max-w-full items-center gap-2 text-left transition-colors hover:text-brand-primary"
    >
      {content}
    </button>
  )
}

export default function RegionalHandoffPage() {
  const [searchParams] = useSearchParams()
  const initialSearch = searchParams.get('search') || ''
  const toast = useToast()
  const [activeTab, setActiveTab] = useState(WORKSPACE_TAB)
  const [items, setItems] = useState([])
  const [meta, setMeta] = useState({ total: 0, page: 1, pages: 1 })
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState(initialSearch)
  const [actionError, setActionError] = useState('')
  const [handoffLoadingKey, setHandoffLoadingKey] = useState('')
  const [driveReadiness, setDriveReadiness] = useState(null)
  const [confirmingPush, setConfirmingPush] = useState(null)

  const [driveRoot, setDriveRoot] = useState(null)
  const [driveItems, setDriveItems] = useState([])
  const [driveLoading, setDriveLoading] = useState(false)
  const [drivePath, setDrivePath] = useState([])
  const [driveActionKey, setDriveActionKey] = useState('')
  const [folderModalOpen, setFolderModalOpen] = useState(false)
  const [folderName, setFolderName] = useState('')
  const [folderError, setFolderError] = useState('')
  const [pendingMove, setPendingMove] = useState(null)
  const [driveLoaded, setDriveLoaded] = useState(false)

  const driveReady = driveReadiness?.status === 'ready'
  const currentFolder = drivePath[drivePath.length - 1] || driveRoot
  const currentFolderId = currentFolder?.id || null

  const loadQueue = useCallback(async () => {
    setLoading(true)
    setActionError('')
    try {
      const response = await projectApi.listHandoffQueue({
        page,
        per_page: 20,
        search: search || undefined,
      })
      setItems(response.data || [])
      setMeta(response.meta || { total: 0, page: 1, pages: 1 })
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to load the regional Google Drive handoff queue.')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [page, search])

  const loadDriveWorkspace = useCallback(async (folderId, nextPath) => {
    if (!driveReady) return
    setDriveLoading(true)
    setActionError('')
    try {
      let root = driveRoot
      if (!root) {
        const rootResponse = await driveApi.getDriveRoot()
        root = rootResponse.data?.root || null
        setDriveRoot(root)
      }

      const parentId = folderId || root?.id || undefined
      const childrenResponse = await driveApi.listDriveChildren({ parent_id: parentId })
      setDriveItems(childrenResponse.data?.items || [])
      setDriveLoaded(true)
      if (nextPath) {
        setDrivePath(nextPath)
      } else if (!drivePath.length && root) {
        setDrivePath([root])
      }
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to load the regional Google Drive workspace.')
      setDriveItems([])
      setDriveLoaded(true)
    } finally {
      setDriveLoading(false)
    }
  }, [drivePath.length, driveReady, driveRoot])

  useEffect(() => {
    if (activeTab === QUEUE_TAB) {
      loadQueue()
    }
  }, [activeTab, loadQueue])

  useEffect(() => {
    let isMounted = true

    async function loadReadiness() {
      try {
        const response = await driveApi.getDriveReadiness()
        const googleDriveCheck = response.data || null
        if (isMounted) {
          setDriveReadiness(googleDriveCheck)
        }
      } catch {
        if (isMounted) {
          setDriveReadiness(null)
        }
      }
    }

    loadReadiness()
    return () => {
      isMounted = false
    }
  }, [])

  useEffect(() => {
    if (activeTab === WORKSPACE_TAB && driveReady && !driveLoaded && !driveLoading) {
      loadDriveWorkspace()
    }
  }, [activeTab, driveLoaded, driveLoading, driveReady, loadDriveWorkspace])

  async function handlePush(requirementId) {
    if (!requirementId) return
    if (!driveReadiness || driveReadiness.status !== 'ready') {
      setActionError('Google Drive handoff is implemented, but uploads are disabled until the Drive readiness check is ready.')
      setConfirmingPush(null)
      return
    }
    const key = `handoff-${requirementId}`
    setHandoffLoadingKey(key)
    setActionError('')
    try {
      await projectApi.pushRequirementHandoff(requirementId)
      await loadQueue()
      toast.success('Requirement uploaded to the regional Google Drive workspace.')
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to upload this requirement to the regional Google Drive.')
    } finally {
      setHandoffLoadingKey('')
      setConfirmingPush(null)
    }
  }

  async function handleCreateFolder(event) {
    event.preventDefault()
    const name = folderName.trim()
    if (!name) {
      setFolderError('Folder name is required.')
      return
    }

    setDriveActionKey('create-folder')
    setFolderError('')
    try {
      await driveApi.createDriveFolder({
        name,
        parent_id: currentFolderId,
      })
      toast.success('Folder created.')
      setFolderName('')
      setFolderModalOpen(false)
      await loadDriveWorkspace(currentFolderId, drivePath)
    } catch (error) {
      setFolderError(error.response?.data?.message || 'Unable to create this folder.')
    } finally {
      setDriveActionKey('')
    }
  }

  async function handleMoveHere() {
    if (!pendingMove || !currentFolderId) return
    if (pendingMove.id === currentFolderId) {
      setActionError('A folder cannot be moved into itself.')
      return
    }

    setDriveActionKey(`move-${pendingMove.id}`)
    setActionError('')
    try {
      await driveApi.moveDriveItem(pendingMove.id, { target_parent_id: currentFolderId })
      toast.success('Drive item moved.')
      setPendingMove(null)
      await loadDriveWorkspace(currentFolderId, drivePath)
    } catch (error) {
      setActionError(error.response?.data?.message || 'Unable to move this Drive item.')
    } finally {
      setDriveActionKey('')
    }
  }

  function openFolder(folder) {
    const nextPath = [...drivePath, folder]
    loadDriveWorkspace(folder.id, nextPath)
  }

  function openBreadcrumb(index) {
    const nextPath = drivePath.slice(0, index + 1)
    const target = nextPath[nextPath.length - 1]
    loadDriveWorkspace(target?.id, nextPath)
  }

  if (!isAdmin() && !isStaff()) {
    return (
      <GlassPanel>
        <h1 className="page-title">Regional Handoff</h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
          Regional Google Drive handoff is managed by PDMU staff after documentary approval.
        </p>
      </GlassPanel>
    )
  }

  const completedCount = items.filter((item) => item.latest_push?.push_status === 'completed').length
  const failedCount = items.filter((item) => item.latest_push?.push_status === 'failed').length
  const withHistoryCount = items.filter((item) => item.latest_push).length

  const queueColumns = [
    { key: 'project_name', label: 'Project' },
    { key: 'lgu_name', label: 'LGU' },
    { key: 'requirement_name', label: 'Requirement' },
    { key: 'annex_reference', label: 'Annex' },
    { key: 'reviewed_at', label: 'Approved On', render: (row) => formatDate(row.reviewed_at) },
    {
      key: 'latest_submission',
      label: 'Latest File',
      render: (row) => row.latest_submission?.primary_file_name || '—',
    },
    {
      key: 'latest_push',
      label: 'Drive Status',
      render: (row) => (
        <div className="space-y-2">
          {pushStatusBadge(row.latest_push)}
          {row.latest_push?.drive_folder_url && (
            <a
              href={row.latest_push.drive_folder_url}
              target="_blank"
              rel="noreferrer"
              className="action-link text-xs"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Open folder
            </a>
          )}
        </div>
      ),
    },
    {
      key: 'actions',
      label: '',
      render: (row) => (
        <Button
          size="sm"
          variant="outline"
          icon={Upload}
          disabled={!driveReady}
          loading={handoffLoadingKey === `handoff-${row.id}`}
          onClick={() => setConfirmingPush(row)}
          title={driveReady ? 'Upload to regional Google Drive' : 'Google Drive handoff is disabled until readiness is configured'}
        >
          {driveReady ? 'Upload' : 'Disabled'}
        </Button>
      ),
    },
  ]

  const driveColumns = [
    {
      key: 'name',
      label: 'Name',
      render: (row) => <DriveItemName item={row} onOpen={openFolder} />,
    },
    {
      key: 'type',
      label: 'Type',
      render: (row) => (row.is_folder ? 'Folder' : row.mime_type || 'File'),
    },
    {
      key: 'size',
      label: 'Size',
      render: (row) => (row.is_folder ? '—' : formatFileSize(row.size)),
    },
    {
      key: 'modified_time',
      label: 'Modified',
      render: (row) => formatDateTime(row.modified_time),
    },
    {
      key: 'actions',
      label: '',
      render: (row) => (
        <div className="flex flex-wrap justify-end gap-2">
          {row.web_view_link && (
            <a
              href={row.web_view_link}
              target="_blank"
              rel="noreferrer"
              className="btn-outline inline-flex min-h-10 items-center justify-center gap-2 px-3 py-1.5 text-sm"
            >
              <ExternalLink className="h-4 w-4" />
              Open
            </a>
          )}
          <Button
            size="sm"
            variant="outline"
            icon={MoveRight}
            onClick={() => setPendingMove(row)}
            disabled={driveActionKey === `move-${row.id}`}
          >
            Move
          </Button>
        </div>
      ),
    },
  ]

  const readinessWarning = driveReadiness && driveReadiness.status !== 'ready' ? (
    <InlineAlert type="warning" className="mb-4">
      <p className="font-medium">Google Drive system check: {formatStatus(driveReadiness.status)}</p>
      <p className="mt-1">{driveReadiness.message}</p>
      <p className="mt-1">
        The handoff workspace is available after Google Drive is enabled with service credentials and a root folder.
      </p>
    </InlineAlert>
  ) : null

  return (
    <div className="animate-fade-in">
      <div className="mb-6">
        <h1 className="page-title">Regional Handoff</h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Manage the regional Drive workspace and push approved requirements into Program / FY / LGU - Project / Requirement folders.
        </p>
      </div>

      <InlineAlert type="error" className="mb-4" onDismiss={() => setActionError('')}>
        {actionError}
      </InlineAlert>

      {readinessWarning}

      <div className="mb-5 flex flex-wrap gap-2 border-b border-brand-border">
        {[
          { key: WORKSPACE_TAB, label: 'Drive Workspace', icon: Folder },
          { key: QUEUE_TAB, label: 'Ready to Push', icon: Upload },
        ].map((tab) => {
          const Icon = tab.icon
          const isActive = activeTab === tab.key
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`inline-flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
                isActive
                  ? 'border-brand-primary text-brand-primary'
                  : 'border-transparent text-brand-text-muted hover:text-brand-text'
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {activeTab === WORKSPACE_TAB && (
        <div className="space-y-4">
          <GlassPanel>
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-sm font-semibold text-brand-text">Drive Folder Hierarchy</p>
                <p className="mt-1 text-sm text-brand-text-muted">
                  Program / FY / LGU - Project / Requirement / uploaded files
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  icon={RefreshCw}
                  disabled={!driveReady}
                  loading={driveLoading}
                  onClick={() => loadDriveWorkspace(currentFolderId, drivePath)}
                >
                  Refresh
                </Button>
                <Button
                  variant="primary"
                  icon={FolderPlus}
                  disabled={!driveReady || !currentFolderId}
                  onClick={() => {
                    setFolderError('')
                    setFolderName('')
                    setFolderModalOpen(true)
                  }}
                >
                  New Folder
                </Button>
              </div>
            </div>
          </GlassPanel>

          {pendingMove && (
            <InlineAlert type="info">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <span>
                  Moving <strong>{pendingMove.name}</strong>. Open the destination folder, then move it into <strong>{currentFolder?.name || 'this folder'}</strong>.
                </span>
                <span className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="primary"
                    icon={MoveRight}
                    loading={driveActionKey === `move-${pendingMove.id}`}
                    disabled={!currentFolderId}
                    onClick={handleMoveHere}
                  >
                    Move Here
                  </Button>
                  <Button size="sm" variant="ghost" icon={X} onClick={() => setPendingMove(null)}>
                    Cancel
                  </Button>
                </span>
              </div>
            </InlineAlert>
          )}

          <GlassPanel>
            <div className="mb-4 flex flex-wrap items-center gap-2 text-sm text-brand-text-muted">
              <Home className="h-4 w-4" />
              {drivePath.length ? (
                drivePath.map((item, index) => (
                  <span key={item.id} className="inline-flex items-center gap-2">
                    {index > 0 && <ChevronRight className="h-3.5 w-3.5" />}
                    <button
                      type="button"
                      onClick={() => openBreadcrumb(index)}
                      className="rounded px-1 py-0.5 font-medium text-brand-text transition-colors hover:bg-brand-surface hover:text-brand-primary"
                    >
                      {item.name}
                    </button>
                  </span>
                ))
              ) : (
                <span className="font-medium text-brand-text">Regional Handoff Root</span>
              )}
            </div>

            {!driveReady ? (
              <div className="rounded-md border border-dashed border-brand-border px-6 py-10 text-center">
                <Folder className="mx-auto h-10 w-10 text-brand-text-muted" />
                <p className="mt-3 text-sm font-semibold text-brand-text">Drive workspace is not ready</p>
                <p className="mx-auto mt-1 max-w-xl text-sm text-brand-text-muted">
                  Configure Google Drive credentials and a root folder before browsing or changing the regional handoff workspace.
                </p>
              </div>
            ) : (
              <>
                <DataTable
                  columns={driveColumns}
                  data={driveItems}
                  keyField="id"
                  isLoading={driveLoading}
                  emptyMessage="This Drive folder is empty."
                  hidePagination
                />
              </>
            )}
          </GlassPanel>
        </div>
      )}

      {activeTab === QUEUE_TAB && (
        <div>
          <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-4">
            <KpiCard title="Ready" value={meta.total || items.length} subtitle="for handoff" icon={Upload} color="blue" />
            <KpiCard title="Completed" value={completedCount} subtitle="uploads" icon={CheckCircle2} color="emerald" />
            <KpiCard title="Failed" value={failedCount} subtitle="uploads" icon={TriangleAlert} color="red" />
            <KpiCard title="With history" value={withHistoryCount} subtitle="prior handoffs" icon={RefreshCw} color="cyan" />
          </div>

          <div className="mb-4 flex flex-wrap gap-3">
            <form
              onSubmit={(event) => {
                event.preventDefault()
                setPage(1)
                loadQueue()
              }}
              className="flex min-w-[260px] flex-1 gap-2"
            >
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600 dark:text-slate-400" />
                <input
                  className="input-field pl-10"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search project, LGU, or requirement"
                />
              </div>
              <Button type="submit" variant="outline" className="self-center">Search</Button>
            </form>
            <Button variant="outline" onClick={loadQueue}>Refresh</Button>
          </div>

          <GlassPanel>
            <DataTable
              columns={queueColumns}
              data={items}
              keyField="id"
              isLoading={loading}
              emptyMessage="No compliant requirements are waiting for Google Drive handoff."
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
        </div>
      )}

      <Modal
        open={folderModalOpen}
        title="Create Drive Folder"
        description={`Add a folder inside ${currentFolder?.name || 'the current Drive folder'}.`}
        onClose={() => setFolderModalOpen(false)}
        footer={(
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setFolderModalOpen(false)}>Cancel</Button>
            <Button type="submit" form="create-drive-folder-form" loading={driveActionKey === 'create-folder'} icon={FolderPlus}>
              Create Folder
            </Button>
          </div>
        )}
      >
        <form id="create-drive-folder-form" onSubmit={handleCreateFolder}>
          <FormField id="drive-folder-name" label="Folder name" error={folderError} required>
            <input
              id="drive-folder-name"
              className="input-field"
              value={folderName}
              onChange={(event) => {
                setFolderName(event.target.value)
                setFolderError('')
              }}
              placeholder="Example: FY 2026"
              autoFocus
            />
          </FormField>
        </form>
      </Modal>

      <ConfirmationModal
        open={!!confirmingPush}
        title="Confirm Google Drive Upload"
        description={`This will push the latest approved files for "${confirmingPush?.requirement_name}" to Program / FY / LGU - Project / Requirement folders. Continue?`}
        confirmLabel="Upload"
        onConfirm={() => handlePush(confirmingPush?.id)}
        onClose={() => setConfirmingPush(null)}
        loading={!!handoffLoadingKey}
      />
    </div>
  )
}
