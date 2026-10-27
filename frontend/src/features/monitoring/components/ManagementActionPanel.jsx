import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Send, XCircle } from 'lucide-react'
import { Button, DataTable, FeedbackToast, FormField, GlassPanel, InlineAlert, PageHeader } from '../../../components'
import { badgeClassForTone } from '../../../lib/statusStyles'
import { formatStatus } from '../../../lib/formatters'
import { isAdmin, isPlainStaff, isSystemAdmin } from '../../../lib/auth'
import * as monitoringApi from '../api/monitoringApi'
import { riskLevelLabel, riskLevelTone } from './workflowStatus'

function statusTone(status) {
  switch (status) {
    case 'closed': return 'success'
    case 'acted': return 'info'
    case 'submitted': return 'warning'
    case 'for_review': return 'warning'
    default: return 'neutral'
  }
}

/**
 * Management Action Report queue. Reuses the existing MAR list endpoint
 * and adds the Phase 2A lifecycle actions (submit / acknowledge / close).
 * Auto-generated MARs (trigger_source = monthly_monitoring) are labeled
 * distinctly from manually created ones, per the plan's requirement that
 * automatic escalation and manual creation stay traceable.
 */
export function ManagementActionPanel() {
  const restricted = isSystemAdmin()
  const staff = isPlainStaff()
  const admin = isAdmin()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [cycleMonth, setCycleMonth] = useState('')
  const [busyId, setBusyId] = useState(null)

  const load = useCallback(async () => {
    if (restricted) return
    setLoading(true)
    setError('')
    try {
      const response = cycleMonth
        ? await monitoringApi.listManagementActionsForCycle(cycleMonth)
        : await monitoringApi.listManagementActions()
      setItems(response.data || [])
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to load Management Action Reports.')
    } finally {
      setLoading(false)
    }
  }, [cycleMonth, restricted])

  useEffect(() => {
    load()
  }, [load])

  const runAction = async (id, action) => {
    setBusyId(id)
    setError('')
    setMessage('')
    try {
      if (action === 'submit') await monitoringApi.submitManagementAction(id)
      if (action === 'acknowledge') await monitoringApi.acknowledgeManagementAction(id)
      if (action === 'close') await monitoringApi.closeManagementAction(id)
      setMessage('Management Action Report updated successfully.')
      await load()
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to update the Management Action Report.')
    } finally {
      setBusyId(null)
    }
  }

  const columns = [
    { key: 'project_name', label: 'Project', render: (row) => row.project_name || '—' },
    { key: 'cycle_month', label: 'Cycle' },
    { key: 'risk_level', label: 'Risk', render: (row) => <span className={badgeClassForTone(riskLevelTone(row.risk_level))}>{riskLevelLabel(row.risk_level)}</span> },
    {
      key: 'trigger_source',
      label: 'Trigger',
      render: (row) => (
        row.trigger_source === 'monthly_monitoring'
          ? <span className={badgeClassForTone('warning')}>Auto-Generated</span>
          : <span className="text-brand-text-muted">{formatStatus(row.trigger_source)}</span>
      ),
    },
    { key: 'status', label: 'Status', render: (row) => <span className={badgeClassForTone(statusTone(row.status))}>{formatStatus(row.status)}</span> },
    {
      key: 'actions',
      label: '',
      render: (row) => {
        const busy = busyId === row.id
        if (staff && ['draft', 'for_review'].includes(row.status)) {
          return (
            <Button size="sm" variant="outline" icon={Send} loading={busy} onClick={() => runAction(row.id, 'submit')}>
              Submit
            </Button>
          )
        }
        if (admin && row.status === 'submitted') {
          return (
            <Button size="sm" icon={CheckCircle2} loading={busy} onClick={() => runAction(row.id, 'acknowledge')}>
              Acknowledge
            </Button>
          )
        }
        if (admin && row.status === 'acted') {
          return (
            <Button size="sm" variant="outline" icon={XCircle} loading={busy} onClick={() => runAction(row.id, 'close')}>
              Close
            </Button>
          )
        }
        return null
      },
    },
  ]

  if (restricted) {
    return (
      <div>
        <PageHeader
          title="Management Action Report"
          description="Track risk escalations generated automatically from Monthly Progress Report slippage, plus manually recorded actions. Staff submit for Provincial Admin action; Provincial Admin acknowledges and closes."
        />
        <InlineAlert type="info">
          System Administrators do not have operational access to Management Action Reports. This workspace is limited to Staff and Provincial Admin roles.
        </InlineAlert>
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title="Management Action Report"
        description="Track risk escalations generated automatically from Monthly Progress Report slippage, plus manually recorded actions. Staff submit for Provincial Admin action; Provincial Admin acknowledges and closes."
        actions={(
          <div className="flex flex-wrap items-end gap-2">
            <FormField id="mar-cycle-filter" label="Cycle month" className="mb-0">
              <input
                id="mar-cycle-filter"
                type="month"
                className="input-field w-auto min-w-[190px]"
                value={cycleMonth}
                onChange={(event) => setCycleMonth(event.target.value)}
              />
            </FormField>
            <Button variant="outline" size="sm" onClick={load}>Refresh</Button>
          </div>
        )}
      />

      <FeedbackToast type="success" message={message} onDismiss={() => setMessage('')} />
      <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>{error}</InlineAlert>

      <GlassPanel noPadding>
        <DataTable
          columns={columns}
          data={items}
          keyField="id"
          isLoading={loading}
          emptyMessage="No Management Action Reports have been recorded yet."
          caption="Management Action Reports"
          density="compact"
        />
      </GlassPanel>
    </div>
  )
}
