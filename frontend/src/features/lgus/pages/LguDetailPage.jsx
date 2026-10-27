import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Edit2,
  ToggleLeft,
  ToggleRight,
  MapPin,
  Phone,
  Mail,
  User,
  Building2,
  Landmark,
  Layers,
  FolderKanban,
  CheckCircle2,
  Archive,
  AlertTriangle,
  X,
  Crown,
  Headphones,
  ArrowRight,
} from 'lucide-react'
import { Breadcrumb, DataTable, FeedbackToast, GlassPanel, Button, FormField, InlineAlert, KpiCard, PageHeader } from '../../../components'
import { isAdmin } from '../../../lib/auth'
import { ROUTES } from '../../../config/routes'
import { formatMachineLabel, formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import { apiErrorMessage } from '../../../lib/formErrors'
import * as lguApi from '../api/lguApi'
import * as projectApi from '../../projects/api/projectApi'

export default function LguDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [lgu, setLgu] = useState(null)
  const [projects, setProjects] = useState([])
  const [clusters, setClusters] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({})
  const [formError, setFormError] = useState('')
  const [pageMessage, setPageMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const fetchLgu = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [res, clustersRes, projectRes] = await Promise.all([
        lguApi.getLgu(id),
        lguApi.listClusters(),
        projectApi.listProjects({ lgu_id: id, per_page: 100 }),
      ])
      setLgu(res.data)
      setClusters(clustersRes.data || [])
      setForm({
        name: res.data.name || '',
        municipality: res.data.municipality || '',
        province: res.data.province || 'Laguna',
        cluster_id: res.data.cluster_id || '',
        mayor_name: res.data.mayor_name || '',
        mayor_email: res.data.mayor_email || '',
        contact_person: res.data.contact_person || '',
        contact_email: res.data.contact_email || '',
        contact_phone: res.data.contact_phone || '',
      })
      setProjects(projectRes.data || [])
    } catch (err) {
      if (err?.response?.status === 404) {
        navigate(ROUTES.LGUS)
        return
      }
      setError(apiErrorMessage(err, 'Unable to load LGU profile. Please try again.'))
    } finally {
      setLoading(false)
    }
  }, [id, navigate])

  useEffect(() => { fetchLgu() }, [fetchLgu])

  const handleToggle = async () => {
    setFormError('')
    setPageMessage('')
    try {
      await lguApi.toggleLguActive(lgu.id, !lgu.is_active)
      setPageMessage(`LGU profile ${lgu.is_active ? 'deactivated' : 'activated'} successfully.`)
      fetchLgu()
    } catch (err) {
      setFormError(err.response?.data?.message || 'Unable to update the LGU status.')
    }
  }

  const handleUpdate = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      const payload = {
        ...form,
        cluster_id: form.cluster_id ? Number(form.cluster_id) : null,
      }
      await lguApi.updateLgu(lgu.id, payload)
      setEditing(false)
      setFormError('')
      setPageMessage('LGU profile updated successfully.')
      fetchLgu()
    } catch (err) {
      setFormError(err.response?.data?.message || 'Unable to update the LGU profile.')
    } finally {
      setSubmitting(false)
    }
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

  if (error && !lgu) {
    return (
      <div className="animate-fade-in">
        <Breadcrumb
          items={[
            { label: 'LGUs', to: ROUTES.LGUS },
            { label: 'LGU Profile' },
          ]}
        />
        <div className="mt-4">
          <InlineAlert type="error">
            <div className="flex items-center justify-between gap-4">
              <span>{error}</span>
              <Button size="sm" variant="outline" onClick={fetchLgu}>Retry</Button>
            </div>
          </InlineAlert>
        </div>
      </div>
    )
  }

  if (!lgu) return null

  const ongoingCount = projects.filter((p) => p.overall_status === 'ongoing').length
  const completedCount = projects.filter((p) => p.overall_status === 'completed').length
  const attentionCount = projects.filter((p) => ['not_yet_started', 'cancelled', 'at_risk', 'delayed'].includes(p.overall_status)).length

  const initials = (lgu.name || '')
    .replace(/municipality of/i, '')
    .replace(/city of/i, '')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase() || 'LG'

  return (
    <div className="animate-fade-in">
      <Breadcrumb
        items={[
          { label: 'LGUs', to: ROUTES.LGUS },
          { label: lgu.name },
        ]}
      />

      {error && (
        <InlineAlert type="error" className="mt-4">
          <div className="flex items-center justify-between gap-4">
            <span>{error}</span>
            <Button size="sm" variant="outline" onClick={fetchLgu}>Retry</Button>
          </div>
        </InlineAlert>
      )}

      <PageHeader
        eyebrow="LGU Profile"
        title={
          <span className="inline-flex items-center gap-3">
            <span
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-brand-primary/10 text-brand-primary font-semibold"
              aria-hidden="true"
            >
              {initials}
            </span>
            <span>{lgu.name}</span>
          </span>
        }
        description={
          <span className="inline-flex items-center gap-1.5">
            <MapPin className="h-4 w-4 shrink-0" aria-hidden="true" />
            {lgu.municipality}, {lgu.province}
          </span>
        }
        meta={
          <>
            <span className={badgeClassForStatus(lgu.is_active ? 'active' : 'inactive')}>
              <span className={`status-dot ${lgu.is_active ? 'bg-emerald-600 dark:bg-emerald-300' : 'bg-slate-500 dark:bg-slate-300'}`} />
              {lgu.is_active ? 'Active' : 'Inactive'}
            </span>
            {lgu.cluster_name && (
              <span className="status-badge status-badge-info">
                <Layers className="h-3 w-3" aria-hidden="true" />
                {lgu.cluster_name}
              </span>
            )}
            <span className="status-badge status-badge-neutral">
              <FolderKanban className="h-3 w-3" aria-hidden="true" />
              {projects.length} {projects.length === 1 ? 'project' : 'projects'}
            </span>
          </>
        }
        actions={
          isAdmin() && (
            <>
              <Button
                variant="outline"
                icon={editing ? X : Edit2}
                onClick={() => { setEditing(!editing); setFormError('') }}
              >
                {editing ? 'Cancel' : 'Edit profile'}
              </Button>
              {!editing && (
                <Button
                  variant={lgu.is_active ? 'danger' : 'primary'}
                  icon={lgu.is_active ? ToggleRight : ToggleLeft}
                  onClick={handleToggle}
                >
                  {lgu.is_active ? 'Deactivate' : 'Activate'}
                </Button>
              )}
            </>
          )
        }
      />

      <FeedbackToast type="success" message={pageMessage} onDismiss={() => setPageMessage('')} />
      {!editing && (
        <InlineAlert type="error" className="mb-4" onDismiss={() => setFormError('')}>
          {formError}
        </InlineAlert>
      )}

      {editing ? (
        <GlassPanel>
          <header className="mb-4 flex items-start gap-3 border-b border-brand-border pb-4">
            <div className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-brand-primary/10 text-brand-primary">
              <Edit2 className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Edit LGU details</h2>
              <p className="text-sm text-brand-text-muted">Update basic profile and official contact information.</p>
            </div>
          </header>
          <InlineAlert type="error" className="mb-3" onDismiss={() => setFormError('')}>
            {formError}
          </InlineAlert>
          <form onSubmit={handleUpdate} className="space-y-6">
            <section className="space-y-4">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-brand-text-muted">Basic information</h3>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <FormField id="lgu-name" label="Name" required>
                  <input id="lgu-name" type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="input-field" />
                </FormField>
                <FormField id="lgu-municipality" label="Municipality" required>
                  <input id="lgu-municipality" type="text" value={form.municipality} onChange={(e) => setForm({ ...form, municipality: e.target.value })} className="input-field" />
                </FormField>
                <FormField id="lgu-province" label="Province">
                  <input id="lgu-province" type="text" value={form.province} onChange={(e) => setForm({ ...form, province: e.target.value })} className="input-field" />
                </FormField>
                <FormField id="lgu-cluster" label="Cluster">
                  <select id="lgu-cluster" value={form.cluster_id} onChange={(e) => setForm({ ...form, cluster_id: e.target.value })} className="input-field">
                    <option value="">Unassigned</option>
                    {clusters.map((cluster) => (
                      <option key={cluster.id} value={cluster.id}>{cluster.name}</option>
                    ))}
                  </select>
                </FormField>
              </div>
            </section>

            <section className="space-y-4">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-brand-text-muted">Official contact information</h3>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <FormField id="lgu-mayor-name" label="Mayor name">
                  <input id="lgu-mayor-name" type="text" value={form.mayor_name} onChange={(e) => setForm({ ...form, mayor_name: e.target.value })} className="input-field" />
                </FormField>
                <FormField id="lgu-mayor-email" label="Mayor email">
                  <input id="lgu-mayor-email" type="email" value={form.mayor_email} onChange={(e) => setForm({ ...form, mayor_email: e.target.value })} className="input-field" />
                </FormField>
                <FormField id="lgu-contact-person" label="Contact person">
                  <input id="lgu-contact-person" type="text" value={form.contact_person} onChange={(e) => setForm({ ...form, contact_person: e.target.value })} className="input-field" />
                </FormField>
                <FormField id="lgu-contact-email" label="Contact email">
                  <input id="lgu-contact-email" type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} className="input-field" />
                </FormField>
                <FormField id="lgu-contact-phone" label="Contact phone">
                  <input id="lgu-contact-phone" type="text" value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} className="input-field" />
                </FormField>
              </div>
            </section>

            <div className="flex items-center justify-end gap-3 border-t border-brand-border pt-4">
              <Button type="button" variant="outline" onClick={() => { setEditing(false); setFormError('') }}>Cancel</Button>
              <Button type="submit" loading={submitting}>Save changes</Button>
            </div>
          </form>
        </GlassPanel>
      ) : (
        <>
          {/* KPI strip */}
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <KpiCard title="Project records" value={projects.length} subtitle="total" icon={FolderKanban} color="blue" />
            <KpiCard title="Ongoing" value={ongoingCount} subtitle="in progress" icon={CheckCircle2} color="emerald" />
            <KpiCard title="Completed" value={completedCount} subtitle="delivered" icon={Archive} color="cyan" />
            <KpiCard title="Needs attention" value={attentionCount} subtitle="not started / at risk" icon={AlertTriangle} color="amber" />
          </div>

          {/* Info cards */}
          <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-5">
            {/* Basic Info */}
            <GlassPanel className="lg:col-span-2">
              <header className="mb-4 flex items-center gap-2 border-b border-brand-border pb-3">
                <Building2 className="h-4 w-4 status-text-info" aria-hidden="true" />
                <h3 className="font-semibold text-slate-900 dark:text-white">Basic information</h3>
              </header>
              <dl className="space-y-3.5">
                <InfoRow icon={Landmark} label="Name" value={lgu.name} />
                <InfoRow icon={Building2} label="Municipality" value={lgu.municipality} />
                <InfoRow icon={MapPin} label="Province" value={lgu.province} />
                <InfoRow
                  icon={Layers}
                  label="Cluster"
                  value={lgu.cluster_name || <span className="italic text-brand-text-muted">Unassigned</span>}
                />
              </dl>
            </GlassPanel>

            {/* Contact Info */}
            <GlassPanel className="lg:col-span-3">
              <header className="mb-4 flex items-center gap-2 border-b border-brand-border pb-3">
                <User className="h-4 w-4 status-text-info" aria-hidden="true" />
                <h3 className="font-semibold text-slate-900 dark:text-white">Official contact information</h3>
              </header>

              <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
                {/* Mayor block */}
                <section>
                  <div className="mb-3 flex items-center gap-2">
                    <Crown className="h-3.5 w-3.5 text-amber-600 dark:text-amber-300" aria-hidden="true" />
                    <span className="text-xs font-semibold uppercase tracking-wide text-brand-text-muted">Mayor's office</span>
                  </div>
                  <dl className="space-y-3">
                    <InfoRow icon={User} label="Mayor" value={lgu.mayor_name || '—'} />
                    <InfoRow
                      icon={Mail}
                      label="Email"
                      value={lgu.mayor_email
                        ? <a href={`mailto:${lgu.mayor_email}`} className="action-link break-all">{lgu.mayor_email}</a>
                        : '—'}
                    />
                  </dl>
                </section>

                {/* Compliance desk block */}
                <section>
                  <div className="mb-3 flex items-center gap-2">
                    <Headphones className="h-3.5 w-3.5 text-blue-600 dark:text-blue-300" aria-hidden="true" />
                    <span className="text-xs font-semibold uppercase tracking-wide text-brand-text-muted">Compliance desk</span>
                  </div>
                  <dl className="space-y-3">
                    <InfoRow icon={User} label="Contact person" value={lgu.contact_person || '—'} />
                    <InfoRow
                      icon={Mail}
                      label="Email"
                      value={lgu.contact_email
                        ? <a href={`mailto:${lgu.contact_email}`} className="action-link break-all">{lgu.contact_email}</a>
                        : '—'}
                    />
                    <InfoRow
                      icon={Phone}
                      label="Phone"
                      value={lgu.contact_phone
                        ? <a href={`tel:${lgu.contact_phone}`} className="action-link">{lgu.contact_phone}</a>
                        : '—'}
                    />
                  </dl>
                </section>
              </div>
            </GlassPanel>
          </div>

          {/* Project records */}
          <GlassPanel>
            <header className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-brand-border pb-3">
              <div className="flex items-center gap-2">
                <FolderKanban className="h-4 w-4 status-text-info" aria-hidden="true" />
                <h3 className="font-semibold text-slate-900 dark:text-white">Project records</h3>
                <span className="status-badge status-badge-neutral">{projects.length}</span>
              </div>
              {projects.length > 0 && (
                <span className="text-xs text-brand-text-muted">Click a row to open the project detail.</span>
              )}
            </header>
            <DataTable
              columns={[
                {
                  key: 'project_name',
                  label: 'Project',
                  render: (row) => (
                    <span className="font-medium text-brand-text">{row.project_name}</span>
                  ),
                },
                { key: 'fiscal_year', label: 'FY' },
                {
                  key: 'current_phase',
                  label: 'Phase',
                  render: (row) => (
                    <span className={badgeClassForStatus(row.current_phase, 'neutral')}>
                      {formatMachineLabel(row.current_phase)}
                    </span>
                  ),
                },
                {
                  key: 'overall_status',
                  label: 'Status',
                  render: (row) => (
                    <span className={badgeClassForStatus(row.overall_status, 'neutral')}>
                      {formatStatus(row.overall_status)}
                    </span>
                  ),
                },
                {
                  key: 'actions',
                  label: '',
                  render: () => (
                    <ArrowRight className="h-4 w-4 text-brand-text-muted" aria-hidden="true" />
                  ),
                },
              ]}
              data={projects}
              keyField="id"
              onRowClick={(row) => navigate(ROUTES.projectDetail(row.id))}
              emptyMessage="No project records have been created or imported for this LGU yet."
            />
          </GlassPanel>
        </>
      )}
    </div>
  )
}

function InfoRow({ icon: Icon, label, value }) {
  return (
    <div className="flex items-start gap-3">
      {Icon && (
        <span className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-brand-surface text-brand-text-muted">
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <dt className="micro-text">{label}</dt>
        <dd className="text-sm text-brand-text">{value}</dd>
      </div>
    </div>
  )
}
