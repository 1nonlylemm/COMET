import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Eye,
  KeyRound,
  Mail,
  MapPin,
  Network,
  Save,
  Search,
  ShieldCheck,
  ToggleLeft,
  ToggleRight,
  Upload,
  UserPlus,
  Users,
} from 'lucide-react'
import { Breadcrumb, Button, DataTable, FeedbackToast, FormField, GlassPanel, InlineAlert, KpiCard, PageHeader, ConfirmationModal } from '../../../components'
import { ROUTES } from '../../../config/routes'
import { isAdmin, isSystemAdmin } from '../../../lib/auth'
import { formatRole } from '../../../lib/formatters'
import { badgeClassForStatus, textClassForStatus } from '../../../lib/statusStyles'
import { BatchImportModal } from '../../imports/components/BatchImportModal'
import * as lguApi from '../../lgus/api/lguApi'
import * as userApi from '../api/userApi'

const TECHNICAL_ROLE = 'system_admin'
const OPERATIONAL_ROLE_OPTIONS = ['admin', 'staff', 'field_officer']
const SYSTEM_ADMIN_ROLE_OPTIONS = [TECHNICAL_ROLE, ...OPERATIONAL_ROLE_OPTIONS]
const CLUSTER_SCOPE_ROLES = new Set(['admin', 'staff'])
const ACCOUNT_STATUS_FILTER_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'true', label: 'Active' },
  { value: 'false', label: 'Inactive' },
]
const PASSWORD_FILTER_OPTIONS = [
  { value: '', label: 'All password states' },
  { value: 'true', label: 'Temporary password' },
  { value: 'false', label: 'Password updated' },
]

function roleLabel(role) {
  return formatRole(role)
}

function availableRoleOptions() {
  return isSystemAdmin() ? SYSTEM_ADMIN_ROLE_OPTIONS : OPERATIONAL_ROLE_OPTIONS
}

function defaultNewAccountRole() {
  return isSystemAdmin() ? TECHNICAL_ROLE : 'staff'
}

function isScopedRole(role) {
  return role === 'staff' || role === 'field_officer' || role === 'admin'
}

function usesClusterScope(role) {
  return CLUSTER_SCOPE_ROLES.has(role)
}

function usesLguScope(role) {
  return role === 'field_officer'
}

function getClusterIds(user) {
  return user?.assigned_clusters?.map((cluster) => cluster.cluster_id) || []
}

function getLguIds(user) {
  return user?.assigned_lgus?.map((lgu) => lgu.lgu_id) || []
}

function getScopeIds(user) {
  return getScopeIdsForRole(user, user?.role)
}

function getScopeIdsForRole(user, role) {
  if (!isScopedRole(role)) return []
  return usesLguScope(role) ? getLguIds(user) : getClusterIds(user)
}

function coverageSummary(user) {
  if (user?.role === TECHNICAL_ROLE) return 'Technical administration'
  if (user?.role === 'admin') return 'Province-wide'
  if (user?.role === 'field_officer') {
    if (!user?.assigned_lgus?.length) return 'No assigned LGU'
    return user.assigned_lgus.map((lgu) => lgu.lgu_name).join(', ')
  }
  if (!user?.assigned_clusters?.length) return 'No active cluster'
  return user.assigned_clusters.map((cluster) => cluster.cluster_name).join(', ')
}

function scopeCount(user) {
  if (user?.role === TECHNICAL_ROLE) return 'None'
  if (user?.role === 'admin') return 'All'
  if (user?.role === 'field_officer') return user.assigned_lgus?.length || 0
  return user.assigned_clusters?.length || 0
}

function sameIdSet(left, right) {
  if (left.length !== right.length) return false
  const rightSet = new Set(right)
  return left.every((id) => rightSet.has(id))
}

function getRoleEditorOptions(user) {
  const options = availableRoleOptions()
  return user?.role && !options.includes(user.role)
    ? [user.role, ...options]
    : options
}

function AccountStatusBadge({ user }) {
  const status = user.is_active ? 'active' : 'inactive'
  return (
    <span className={badgeClassForStatus(status)}>
      <span className={`status-dot ${user.is_active ? 'bg-emerald-600 dark:bg-emerald-300' : 'bg-slate-500 dark:bg-slate-300'}`} />
      {user.is_active ? 'Active' : 'Inactive'}
    </span>
  )
}

function PasswordStatusBadge({ user }) {
  return user.must_change_password ? (
    <span className={badgeClassForStatus('pending')}>Temporary</span>
  ) : (
    <span className={badgeClassForStatus('approved')}>Updated</span>
  )
}

function AdminOnlyNotice() {
  return (
    <GlassPanel className="p-6">
      <div className="flex items-start gap-4">
        <div className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-slate-100 dark:bg-slate-800">
          <ShieldCheck className="h-5 w-5 text-slate-600 dark:text-slate-400" />
        </div>
        <div>
          <h1 className="page-title mb-1">Internal User Accounts</h1>
          <p className="text-sm text-brand-text-muted">
            Only technical System Admins and operational Admins can create application accounts and assign internal roles.
          </p>
        </div>
      </div>
    </GlassPanel>
  )
}

function UserListView() {
  const navigate = useNavigate()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchDraft, setSearchDraft] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [passwordFilter, setPasswordFilter] = useState('')
  const [error, setError] = useState('')
  const [pageMessage, setPageMessage] = useState('')
  const [showImport, setShowImport] = useState(false)
  const roleOptions = availableRoleOptions()
  const canBatchImport = isAdmin()

  const loadUsers = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await userApi.listUsers({
        per_page: 100,
        search: appliedSearch || undefined,
        role: roleFilter || undefined,
        is_active: statusFilter || undefined,
        must_change_password: passwordFilter || undefined,
      })
      setUsers(response.data || [])
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to load internal accounts.')
    } finally {
      setLoading(false)
    }
  }, [appliedSearch, passwordFilter, roleFilter, statusFilter])

  useEffect(() => {
    loadUsers()
  }, [loadUsers])

  const handleSearchSubmit = (event) => {
    event.preventDefault()
    const nextSearch = searchDraft.trim()
    setAppliedSearch(nextSearch)
    if (nextSearch === appliedSearch) {
      loadUsers()
    }
  }

  const handleClearFilters = () => {
    setSearchDraft('')
    setAppliedSearch('')
    setRoleFilter('')
    setStatusFilter('')
    setPasswordFilter('')
  }

  const roleFilterOptions = [
    { value: '', label: 'All roles' },
    ...roleOptions.map((role) => ({ value: role, label: roleLabel(role) })),
  ]
  const hasActiveFilters = Boolean(searchDraft || appliedSearch || roleFilter || statusFilter || passwordFilter)

  const columns = [
    {
      key: 'full_name',
      label: 'Account',
      render: (row) => (
        <div className="min-w-0">
          <p className="break-words font-medium text-brand-text">{row.full_name}</p>
          <p className="mt-0.5 break-all text-xs text-brand-text-muted">{row.email}</p>
        </div>
      ),
    },
    {
      key: 'role',
      label: 'Role',
      render: (row) => (
        <span className="text-sm text-brand-text">{roleLabel(row.role)}</span>
      ),
    },
    {
      key: 'scope',
      label: 'Coverage',
      render: (row) => (
        <span className="text-sm text-brand-text-muted">{coverageSummary(row)}</span>
      ),
    },
    {
      key: 'is_active',
      label: 'Status',
      render: (row) => <AccountStatusBadge user={row} />,
    },
    {
      key: 'must_change_password',
      label: 'Password',
      render: (row) => <PasswordStatusBadge user={row} />,
    },
    {
      key: 'actions',
      label: '',
      render: (row) => (
        <Button
          size="sm"
          variant="outline"
          icon={Eye}
          onClick={(event) => {
            event.stopPropagation()
            navigate(ROUTES.userDetail(row.id))
          }}
        >
          View
        </Button>
      ),
    },
  ]

  return (
    <div className="space-y-5">
      <PageHeader
        title="Internal User Accounts"
        description="Manage internal DILG accounts, role assignment, activation state, and operational coverage."
        actions={(
          <>
            {canBatchImport && (
              <Button variant="outline" icon={Upload} onClick={() => { setError(''); setPageMessage(''); setShowImport(true) }}>
                Batch Import
              </Button>
            )}
            <Button icon={UserPlus} onClick={() => navigate(ROUTES.USER_CREATE)}>
              Create Account
            </Button>
          </>
        )}
      />

      {!isSystemAdmin() && (
        <InlineAlert type="info" title="Operational Account View">
          Technical System Admin accounts are managed separately and are hidden from operational Admin users.
        </InlineAlert>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <KpiCard title="Accounts" value={users.length} subtitle="total" icon={Users} color="blue" />
        <KpiCard title="Active" value={users.filter((u) => u.is_active).length} subtitle="enabled" icon={Mail} color="emerald" />
        <KpiCard title="Temp passwords" value={users.filter((u) => u.must_change_password).length} subtitle="must rotate" icon={KeyRound} color="amber" />
      </div>

      <div className="mb-4 flex flex-wrap gap-3">
        <form
          onSubmit={handleSearchSubmit}
          className="flex min-w-[280px] flex-1 flex-wrap gap-2 sm:flex-nowrap"
          role="search"
          aria-label="Search internal accounts"
        >
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-brand-text-muted" strokeWidth={1.5} />
            <input
              id="user-search"
              type="search"
              className="input-field pl-10"
              placeholder="Search by name or email..."
              value={searchDraft}
              onChange={(e) => setSearchDraft(e.target.value)}
              aria-label="Search internal accounts"
            />
          </div>
          <Button type="submit" variant="outline" className="self-center">Search</Button>
          {hasActiveFilters && (
            <Button type="button" variant="ghost" onClick={handleClearFilters} className="self-center">
              Clear
            </Button>
          )}
        </form>

        <select
          id="user-role-filter"
          className="input-field w-auto min-w-[150px]"
          value={roleFilter}
          onChange={(event) => setRoleFilter(event.target.value)}
          aria-label="Filter by role"
        >
          {roleFilterOptions.map((option) => (
            <option key={option.value || 'all'} value={option.value}>{option.label}</option>
          ))}
        </select>

        <select
          id="user-status-filter"
          className="input-field w-auto min-w-[150px]"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
          aria-label="Filter by status"
        >
          {ACCOUNT_STATUS_FILTER_OPTIONS.map((option) => (
            <option key={option.value || 'all'} value={option.value}>{option.label}</option>
          ))}
        </select>

        <select
          id="user-password-filter"
          className="input-field w-auto min-w-[180px]"
          value={passwordFilter}
          onChange={(event) => setPasswordFilter(event.target.value)}
          aria-label="Filter by password state"
        >
          {PASSWORD_FILTER_OPTIONS.map((option) => (
            <option key={option.value || 'all'} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>

      {/* Feedback */}
      <FeedbackToast type="success" message={pageMessage} onDismiss={() => setPageMessage('')} />
      <InlineAlert type="error" onDismiss={() => setError('')}>
        {error}
      </InlineAlert>

      {/* Table */}
      <DataTable
        columns={columns}
        data={users}
        keyField="id"
        isLoading={loading}
        emptyMessage="No internal accounts found."
        caption="Internal user accounts"
        onRowClick={(row) => navigate(ROUTES.userDetail(row.id))}
        density="compact"
      />

      {canBatchImport && (
        <BatchImportModal
          open={showImport}
          target="users"
          title="Batch Import Internal Users"
          description="Create internal DILG accounts from a CSV or XLSX file while preserving Admin, Staff, and Field Officer scope rules."
          onClose={() => setShowImport(false)}
          onImported={(result) => {
            setPageMessage(`Import complete: ${result.summary.created || 0} created, ${result.summary.skipped || 0} skipped, ${result.summary.failed || 0} failed.`)
            loadUsers()
          }}
        />
      )}
    </div>
  )
}

function UserCreateView() {
  const navigate = useNavigate()
  const [clusters, setClusters] = useState([])
  const [lgus, setLgus] = useState([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [deliveryResult, setDeliveryResult] = useState(null)
  const [createdUser, setCreatedUser] = useState(null)
  const roleOptions = availableRoleOptions()
  const initialRole = defaultNewAccountRole()
  const [form, setForm] = useState({
    email: '',
    first_name: '',
    last_name: '',
    role: initialRole,
    cluster_ids: [],
    lgu_ids: [],
  })

  useEffect(() => {
    let isMounted = true
    setLoading(true)
    Promise.all([
      lguApi.listClusters(),
      lguApi.listLgus({ is_active: true, per_page: 500 }),
    ])
      .then(([clusterResponse, lguResponse]) => {
        if (isMounted) {
          setClusters(clusterResponse.data || [])
          setLgus(lguResponse.data || [])
        }
      })
      .catch((err) => {
        if (isMounted) setError(err.response?.data?.message || 'Unable to load scope options.')
      })
      .finally(() => {
        if (isMounted) setLoading(false)
      })
    return () => { isMounted = false }
  }, [])

  const handleClusterToggle = (clusterId) => {
    setError('')
    const exists = form.cluster_ids.includes(clusterId)
    setForm({
      ...form,
      cluster_ids: exists
        ? form.cluster_ids.filter((id) => id !== clusterId)
        : [...form.cluster_ids, clusterId],
    })
  }

  const handleLguToggle = (lguId) => {
    setError('')
    const exists = form.lgu_ids.includes(lguId)
    setForm({
      ...form,
      lgu_ids: exists
        ? form.lgu_ids.filter((id) => id !== lguId)
        : [...form.lgu_ids, lguId],
    })
  }

  const handleCreateUser = async (event) => {
    event.preventDefault()
    setError('')
    setMessage('')
    setDeliveryResult(null)
    setCreatedUser(null)

    if (!form.email || !form.first_name || !form.last_name) {
      setError('Email, first name, and last name are required.')
      return
    }
    if (form.role === 'staff' && form.cluster_ids.length === 0) {
      setError('Staff accounts must be assigned to at least one cluster.')
      return
    }
    if (form.role === 'field_officer' && form.lgu_ids.length === 0) {
      setError('Field officer accounts must be assigned to at least one LGU.')
      return
    }

    setSubmitting(true)
    try {
      const payload = {
        ...form,
        cluster_ids: usesClusterScope(form.role) ? form.cluster_ids : [],
        lgu_ids: usesLguScope(form.role) ? form.lgu_ids : [],
      }
      const response = await userApi.createUser(payload)
      setMessage(response.data?.delivery?.message || 'Internal account created successfully.')
      setDeliveryResult(response.data?.delivery || null)
      setCreatedUser(response.data?.user || null)
      setForm({ email: '', first_name: '', last_name: '', role: initialRole, cluster_ids: [], lgu_ids: [] })
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to create the internal account.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-5">
      <Breadcrumb
        items={[
          { label: 'Internal User Accounts', to: ROUTES.USERS },
          { label: 'Create Account' },
        ]}
        className="mb-0"
      />

      <PageHeader
        title="Create Internal Account"
        description="Provision one DILG user account, assign a role, and set coverage only for scoped operational roles."
      />

      {/* Alerts */}
      <InlineAlert type="error" onDismiss={() => setError('')}>
        {error}
      </InlineAlert>

      {message && (
        <InlineAlert type="success" onDismiss={() => setMessage('')}>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>{message}</span>
            {createdUser && (
              <Button size="sm" variant="outline" icon={Eye} onClick={() => navigate(ROUTES.userDetail(createdUser.id))}>
                View Account
              </Button>
            )}
          </div>
        </InlineAlert>
      )}

      {deliveryResult?.temporary_password && (
        <InlineAlert type="warning">
          <p className="font-semibold">Manual credential handoff required</p>
          <p className="mt-1 text-sm">
            Email delivery did not complete. Share this temporary password through an approved secure channel and ask the user to change it on first sign-in.
          </p>
          <p className="mt-2 break-all font-mono text-sm tracking-wide">{deliveryResult.temporary_password}</p>
        </InlineAlert>
      )}

      {/* Form */}
      <GlassPanel className="p-5">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-12 text-sm text-brand-text-muted">
            <div className="mb-3 h-6 w-6 animate-spin rounded-full border-2 border-brand-primary border-t-transparent" />
            Loading cluster options...
          </div>
        ) : (
          <form onSubmit={handleCreateUser} className="space-y-6">
            {/* Identity fields */}
            <div>
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-brand-text-muted">Identity</p>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <FormField id="user-first-name" label="First name" required>
                  <input
                    id="user-first-name"
                    className="input-field"
                    value={form.first_name}
                    onChange={(event) => setForm({ ...form, first_name: event.target.value })}
                  />
                </FormField>
                <FormField id="user-last-name" label="Last name" required>
                  <input
                    id="user-last-name"
                    className="input-field"
                    value={form.last_name}
                    onChange={(event) => setForm({ ...form, last_name: event.target.value })}
                  />
                </FormField>
                <FormField id="user-email" label="Email address" required className="md:col-span-2">
                  <input
                    id="user-email"
                    type="email"
                    className="input-field"
                    placeholder="name@dilg.gov.ph"
                    value={form.email}
                    onChange={(event) => setForm({ ...form, email: event.target.value })}
                  />
                </FormField>
              </div>
            </div>

            {/* Divider */}
            <div className="border-t border-brand-border" />

            {/* Access fields */}
            <div>
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-brand-text-muted">Access</p>
              <FormField id="user-role" label="Role" required>
                <select
                  id="user-role"
                  className="input-field"
                  value={form.role}
                  onChange={(event) => setForm({
                    ...form,
                    role: event.target.value,
                    cluster_ids: usesClusterScope(event.target.value) ? form.cluster_ids : [],
                    lgu_ids: usesLguScope(event.target.value) ? form.lgu_ids : [],
                  })}
                >
                  {roleOptions.map((role) => (
                    <option key={role} value={role}>{roleLabel(role)}</option>
                  ))}
                </select>
              </FormField>
            </div>

            {/* Scope assignment */}
            {usesClusterScope(form.role) && (
              <div>
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-brand-text-muted">Assigned clusters</p>
                <p className="mb-3 text-xs text-brand-text-muted">
                  {form.role === 'admin'
                    ? 'Leave blank for province-wide admin access, or select clusters to limit this admin account.'
                    : 'Staff accounts require at least one active cluster before the account can be created.'}
                </p>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  {clusters.map((cluster) => (
                    <label
                      key={cluster.id}
                      className="flex min-h-10 cursor-pointer items-center gap-2.5 rounded-md border border-brand-border bg-brand-surface px-3 py-2 text-sm text-brand-text transition-colors hover:bg-brand-border/20"
                    >
                      <input
                        type="checkbox"
                        className="accent-brand-primary"
                        checked={form.cluster_ids.includes(cluster.id)}
                        onChange={() => handleClusterToggle(cluster.id)}
                      />
                      <span className="min-w-0 break-words">{cluster.name}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {usesLguScope(form.role) && (
              <div>
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-brand-text-muted">Assigned LGUs</p>
                <p className="mb-3 text-xs text-brand-text-muted">
                  Field officer accounts are scoped to specific LGUs, not whole clusters.
                </p>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  {lgus.map((lgu) => (
                    <label
                      key={lgu.id}
                      className="flex min-h-10 cursor-pointer items-center gap-2.5 rounded-md border border-brand-border bg-brand-surface px-3 py-2 text-sm text-brand-text transition-colors hover:bg-brand-border/20"
                    >
                      <input
                        type="checkbox"
                        className="accent-brand-primary"
                        checked={form.lgu_ids.includes(lgu.id)}
                        onChange={() => handleLguToggle(lgu.id)}
                      />
                      <span className="min-w-0 break-words">{lgu.name}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end border-t border-brand-border pt-4">
              <Button type="submit" loading={submitting} icon={UserPlus}>
                Create Account
              </Button>
            </div>
          </form>
        )}
      </GlassPanel>
    </div>
  )
}

function UserDetailView() {
  const { id } = useParams()
  const [user, setUser] = useState(null)
  const [clusters, setClusters] = useState([])
  const [lgus, setLgus] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [roleSaving, setRoleSaving] = useState(false)
  const [activeSaving, setActiveSaving] = useState(false)
  const [assignmentSaving, setAssignmentSaving] = useState(false)
  const [assignmentDraft, setAssignmentDraft] = useState([])
  const [roleDraft, setRoleDraft] = useState('')
  const [technicalDraft, setTechnicalDraft] = useState(false)
  const [managementDraft, setManagementDraft] = useState(false)
  const [confirmingActiveToggle, setConfirmingActiveToggle] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [userResponse, clusterResponse, lguResponse] = await Promise.all([
        userApi.getUser(id),
        lguApi.listClusters(),
        lguApi.listLgus({ is_active: true, per_page: 500 }),
      ])
      setUser(userResponse.data)
      setClusters(clusterResponse.data || [])
      setLgus(lguResponse.data || [])
      setRoleDraft(userResponse.data.role)
      setTechnicalDraft(userResponse.data.can_approve_technical_documents || false)
      setManagementDraft(userResponse.data.can_close_management_actions || false)
      setAssignmentDraft(getScopeIds(userResponse.data))
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to load this account.')
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleToggleActive = async () => {
    if (!user) return
    setError('')
    setMessage('')
    setActiveSaving(true)
    try {
      const response = await userApi.toggleUserActive(user.id, !user.is_active)
      setUser(response.data)
      setRoleDraft(response.data.role)
      setTechnicalDraft(response.data.can_approve_technical_documents || false)
      setManagementDraft(response.data.can_close_management_actions || false)
      setAssignmentDraft(getScopeIds(response.data))
      setMessage(`Account ${user.is_active ? 'deactivated' : 'activated'} successfully.`)
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to update the account status.')
    } finally {
      setActiveSaving(false)
      setConfirmingActiveToggle(false)
    }
  }

  const handleRoleDraftChange = (role) => {
    if (!user || role === roleDraft) return
    setError('')
    setMessage('')
    setRoleDraft(role)
    setAssignmentDraft(isScopedRole(role) ? getScopeIdsForRole(user, role) : [])
  }

  const handleAssignmentToggle = (scopeId) => {
    setError('')
    setAssignmentDraft((current) => (
      current.includes(scopeId)
        ? current.filter((draftId) => draftId !== scopeId)
        : [...current, scopeId]
    ))
  }

  const handleSaveAssignments = async () => {
    const targetRole = roleDraft || user?.role
    if (!user) return
    const roleChanged = targetRole !== user.role
    if (!isScopedRole(targetRole)) {
      if (!roleChanged) return
      setAssignmentSaving(true)
      setRoleSaving(true)
      setError('')
      setMessage('')

      try {
        const response = await userApi.changeUserRole(user.id, targetRole, {
          cluster_ids: [],
          lgu_ids: [],
          can_approve_technical_documents: technicalDraft,
          can_close_management_actions: managementDraft,
        })
        setUser(response.data)
        setRoleDraft(response.data.role)
        setAssignmentDraft(getScopeIds(response.data))
        setMessage('Role updated successfully.')
      } catch (err) {
        setError(err.response?.data?.message || 'Unable to update the account role.')
      } finally {
        setAssignmentSaving(false)
        setRoleSaving(false)
      }
      return
    }
    if (targetRole === 'staff' && assignmentDraft.length === 0) {
      setError('Staff accounts must keep at least one active cluster assignment.')
      return
    }
    if (targetRole === 'field_officer' && assignmentDraft.length === 0) {
      setError('Field officer accounts must keep at least one active LGU assignment.')
      return
    }
    setAssignmentSaving(true)
    setRoleSaving(roleChanged)
    setError('')
    setMessage('')

    try {
      if (roleChanged) {
        const usingTargetLguScope = usesLguScope(targetRole)
        const response = await userApi.changeUserRole(user.id, targetRole, {
          cluster_ids: usingTargetLguScope ? [] : assignmentDraft,
          lgu_ids: usingTargetLguScope ? assignmentDraft : [],
          can_approve_technical_documents: technicalDraft,
          can_close_management_actions: managementDraft,
        })
        setUser(response.data)
        setRoleDraft(response.data.role)
        setAssignmentDraft(getScopeIds(response.data))
        setMessage('Role and scope assignments updated successfully.')
        return
      }

      const usingLguScope = usesLguScope(targetRole)
      const currentAssignments = usingLguScope ? (user.assigned_lgus || []) : (user.assigned_clusters || [])
      const idKey = usingLguScope ? 'lgu_id' : 'cluster_id'
      const currentScopeIds = new Set(currentAssignments.map((a) => a[idKey]))
      const draftScopeIds = new Set(assignmentDraft)

      const additions = assignmentDraft.filter((scopeId) => !currentScopeIds.has(scopeId))
      const removals = currentAssignments.filter((a) => !draftScopeIds.has(a[idKey]))

      await Promise.all([
        ...additions.map((scopeId) => (
          usingLguScope
            ? lguApi.assignFieldOfficerToLgu({ user_id: user.id, lgu_id: scopeId })
            : lguApi.assignStaffToCluster({ user_id: user.id, cluster_id: scopeId })
        )),
        ...removals.map((a) => (
          usingLguScope
            ? lguApi.removeFieldAssignment(a.assignment_id)
            : lguApi.removeStaffAssignment(a.assignment_id)
        )),
      ])

      const response = await userApi.getUser(user.id)
      setUser(response.data)
      setRoleDraft(response.data.role)
      setTechnicalDraft(response.data.can_approve_technical_documents || false)
      setManagementDraft(response.data.can_close_management_actions || false)
      setAssignmentDraft(getScopeIds(response.data))
      setMessage('Scope assignments updated successfully.')
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to update scope assignments.')
    } finally {
      setAssignmentSaving(false)
      setRoleSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-brand-primary border-t-transparent" />
      </div>
    )
  }

  if (!user) {
    return (
      <div className="space-y-4">
        <Breadcrumb
          items={[
            { label: 'Internal User Accounts', to: ROUTES.USERS },
            { label: 'Account not available' },
          ]}
          className="mb-0"
        />
        <GlassPanel className="p-5">
          <h1 className="page-title mb-1">Account not available</h1>
          {error && <p className="text-sm text-brand-text-muted">{error}</p>}
        </GlassPanel>
      </div>
    )
  }

  const targetRole = roleDraft || user.role
  const currentScopeIds = getScopeIdsForRole(user, targetRole)
  const roleChanged = targetRole !== user.role
  const assignmentsChanged = !sameIdSet(currentScopeIds, assignmentDraft)
  const scopedAccount = isScopedRole(targetRole)
  const usingLguScope = usesLguScope(targetRole)
  const savedUsingLguScope = usesLguScope(user.role)
  const scopeOptions = usingLguScope ? lgus : clusters
  const nonScopedRole = !scopedAccount
  const scopeTitle = nonScopedRole
    ? 'No Coverage Scope'
    : usingLguScope ? 'LGU Assignment Workbench' : 'Cluster Assignment Workbench'
  const scopeDescription = nonScopedRole
    ? 'Technical System Admin accounts manage platform governance and do not receive operational LGU or cluster coverage.'
    : usingLguScope
      ? 'Toggle LGU coverage for this field officer. Save when ready.'
      : targetRole === 'admin'
        ? 'Leave all clusters unselected for province-wide access, or select clusters to limit this admin account.'
        : 'Toggle cluster coverage for this staff account. Save when ready.'
  const scopeKpiTitle = user.role === TECHNICAL_ROLE ? 'Scope' : savedUsingLguScope ? 'LGUs' : 'Clusters'
  const scopeKpiSubtitle = user.role === TECHNICAL_ROLE
    ? 'not applicable'
    : user.role === 'admin' && !user.assigned_clusters?.length ? 'province-wide' : 'in scope'
  const assignmentSaveDisabled = scopedAccount
    ? (!assignmentsChanged && !roleChanged) || (
      targetRole !== 'admin' && assignmentDraft.length === 0
    )
    : !roleChanged
  const assignmentSaveLabel = scopedAccount
    ? roleChanged ? 'Save Role and Assignments' : 'Save Assignments'
    : 'Save Role'

  return (
    <div className="space-y-5">
      <Breadcrumb
        items={[
          { label: 'Internal User Accounts', to: ROUTES.USERS },
          { label: user.full_name },
        ]}
        className="mb-0"
      />

      {/* Page header with status badges inline and toggle action */}
      <PageHeader
        title={user.full_name}
        description={user.email}
        meta={(
          <>
            <AccountStatusBadge user={user} />
            <PasswordStatusBadge user={user} />
          </>
        )}
        actions={(
          <Button
            variant={user.is_active ? 'danger' : 'primary'}
            icon={user.is_active ? ToggleRight : ToggleLeft}
            onClick={() => setConfirmingActiveToggle(true)}
          >
            {user.is_active ? 'Deactivate' : 'Activate'}
          </Button>
        )}
      />

      {/* Feedback */}
      <FeedbackToast type="success" message={message} onDismiss={() => setMessage('')} />
      <InlineAlert type="error" onDismiss={() => setError('')}>
        {error}
      </InlineAlert>

      {/* KPI strip */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <KpiCard title="Role" value={roleLabel(user.role)} subtitle="assigned" icon={ShieldCheck} color="blue" />
        <KpiCard
          title={scopeKpiTitle}
          value={scopeCount(user)}
          subtitle={scopeKpiSubtitle}
          icon={savedUsingLguScope ? MapPin : Network}
          color="emerald"
        />
        <KpiCard
          title="Password"
          value={user.must_change_password ? 'Temporary' : 'Updated'}
          subtitle={user.must_change_password ? 'must rotate' : 'current'}
          icon={KeyRound}
          color={user.must_change_password ? 'amber' : 'emerald'}
        />
      </div>

      {/* Two-column detail + role panels */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Account details */}
        <GlassPanel className="p-5">
          <h2 className="section-title mb-4">Account Details</h2>
          <dl className="divide-y divide-brand-border">
            <div className="flex items-start justify-between gap-4 py-2.5">
              <dt className="micro-text w-28 flex-shrink-0 pt-0.5">Full name</dt>
              <dd className="min-w-0 break-words text-right text-sm text-brand-text">{user.full_name}</dd>
            </div>
            <div className="flex items-start justify-between gap-4 py-2.5">
              <dt className="micro-text w-28 flex-shrink-0 pt-0.5">Email</dt>
              <dd className="min-w-0 text-right text-sm">
                <a href={`mailto:${user.email}`} className="action-link break-all">{user.email}</a>
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4 py-2.5">
              <dt className="micro-text w-28 flex-shrink-0 pt-0.5">Activation</dt>
              <dd><AccountStatusBadge user={user} /></dd>
            </div>
            <div className="flex items-start justify-between gap-4 py-2.5">
              <dt className="micro-text w-28 flex-shrink-0 pt-0.5">Password</dt>
              <dd><PasswordStatusBadge user={user} /></dd>
            </div>
            <div className="flex items-start justify-between gap-4 py-2.5">
              <dt className="micro-text w-28 flex-shrink-0 pt-0.5">Created</dt>
              <dd className="min-w-0 text-right text-sm text-brand-text">
                {user.created_at ? new Date(user.created_at).toLocaleString() : '-'}
              </dd>
            </div>
          </dl>
        </GlassPanel>

        {/* Role and scope */}
        <GlassPanel className="p-5">
          <h2 className="section-title mb-4">Role and Scope</h2>
          <div className="space-y-4">
            <FormField
              id="account-role"
              label="Role"
              hint={roleSaving ? 'Saving role update...' : 'Staff use clusters. Field Officers use assigned LGUs.'}
            >
              <select
                id="account-role"
                className="input-field"
                value={targetRole}
                disabled={roleSaving || assignmentSaving}
                onChange={(event) => handleRoleDraftChange(event.target.value)}
              >
                {getRoleEditorOptions(user).map((role) => (
                  <option key={role} value={role}>{roleLabel(role)}</option>
                ))}
              </select>
            </FormField>
            {roleChanged && (
              scopedAccount ? (
                <p className="rounded-md border border-brand-primary/25 bg-brand-primary/5 px-3 py-2 text-xs text-brand-text">
                  Select the required {usesLguScope(targetRole) ? 'LGUs' : 'clusters'} below, then save to apply this role change.
                </p>
              ) : (
                <p className="rounded-md border border-brand-primary/25 bg-brand-primary/5 px-3 py-2 text-xs text-brand-text">
                  Save to apply this technical role and clear operational coverage assignments.
                </p>
              )
            )}

            <div className="rounded-md border border-brand-border bg-brand-surface px-3 py-2.5">
              <p className="micro-text mb-0.5">Current coverage</p>
              <p className="break-words text-sm text-brand-text">{coverageSummary(user)}</p>
            </div>

            <p className={`text-xs leading-relaxed ${user.must_change_password ? textClassForStatus('pending') : 'text-brand-text-muted'}`}>
              {user.must_change_password
                ? 'This account is still using a temporary password and must rotate credentials on first sign-in.'
                : 'This account has completed the first-login password rotation.'}
            </p>
          </div>
        </GlassPanel>
      </div>

      {/* Scope assignment workbench */}
      <GlassPanel className="p-5">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="section-title">{scopeTitle}</h2>
            <p className="mt-1 text-sm text-brand-text-muted">
              {scopeDescription}
            </p>
          </div>
          {(scopedAccount || roleChanged) && (
            <Button
              icon={Save}
              onClick={handleSaveAssignments}
              loading={assignmentSaving}
              disabled={assignmentSaveDisabled}
            >
              {assignmentSaveLabel}
            </Button>
          )}
        </div>

        {scopedAccount ? (
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {scopeOptions.map((item) => {
              const checked = assignmentDraft.includes(item.id)
              return (
                <label
                  key={item.id}
                  className={`flex min-h-10 cursor-pointer items-center gap-2.5 rounded-md border px-3 py-2 text-sm transition-colors ${checked
                    ? 'border-brand-primary bg-brand-primary/5 text-brand-text'
                    : 'border-brand-border bg-brand-surface text-brand-text hover:bg-brand-border/20'
                    }`}
                >
                  <input
                    type="checkbox"
                    className="accent-brand-primary"
                    checked={checked}
                    onChange={() => handleAssignmentToggle(item.id)}
                  />
                  <span className="min-w-0 break-words">{item.name}</span>
                </label>
              )
            })}
          </div>
        ) : (
          <div className="rounded-md border border-brand-border bg-brand-surface px-4 py-3 text-sm text-brand-text-muted">
            This role does not use scoped workspace coverage.
          </div>
        )}
      </GlassPanel>

      <ConfirmationModal
        open={confirmingActiveToggle}
        title={`Confirm Account ${user?.is_active ? 'Deactivation' : 'Activation'}`}
        description={`Are you sure you want to ${user?.is_active ? 'deactivate' : 'activate'} this user account?`}
        confirmLabel={user?.is_active ? 'Deactivate' : 'Activate'}
        isDestructive={user?.is_active}
        onConfirm={handleToggleActive}
        onClose={() => setConfirmingActiveToggle(false)}
        loading={activeSaving}
      />
    </div>
  )
}

export default function UserManagementPage({ mode = 'list' }) {
  if (!isAdmin() && !isSystemAdmin()) {
    return <AdminOnlyNotice />
  }

  if (mode === 'create') {
    return <UserCreateView />
  }

  if (mode === 'detail') {
    return <UserDetailView />
  }

  return <UserListView />
}
