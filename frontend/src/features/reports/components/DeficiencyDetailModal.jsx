import { Modal, Button } from '../../../components'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import { AlertCircle, CheckCircle2, Clock } from 'lucide-react'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatDate(isoStr) {
  if (!isoStr) return '-'
  try {
    return new Date(isoStr).toLocaleDateString('en-PH', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return isoStr
  }
}

export default function DeficiencyDetailModal({
  categoryData,
  open,
  onClose,
}) {
  if (!categoryData) return null

  const items = categoryData.items || []

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={categoryData.label || categoryData.category}
      description={`Showing ${formatNumber(items.length)} documented deficiency items for this category`}
      size="xl"
      footer={(
        <div className="flex justify-end">
          <Button variant="outline" onClick={onClose}>Close</Button>
        </div>
      )}
    >
      <div className="space-y-4">
        {/* Category stats pills */}
        <div className="flex flex-wrap items-center gap-3 border-b border-brand-border pb-3 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="text-brand-text-muted">Total:</span>
            <span className="font-bold text-brand-text tabular-nums">{formatNumber(categoryData.total)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-rose-500" />
            <span className="text-brand-text-muted">Open:</span>
            <span className="font-semibold text-rose-700 dark:text-rose-400 tabular-nums">{formatNumber(categoryData.open)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            <span className="text-brand-text-muted">Resolved:</span>
            <span className="font-semibold text-emerald-700 dark:text-emerald-400 tabular-nums">{formatNumber(categoryData.resolved)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-slate-400" />
            <span className="text-brand-text-muted">Waived:</span>
            <span className="font-semibold text-slate-600 dark:text-slate-400 tabular-nums">{formatNumber(categoryData.waived)}</span>
          </div>
        </div>

        {/* Item List */}
        {items.length === 0 ? (
          <div className="py-8 text-center text-sm text-brand-text-muted">
            No specific deficiency records recorded for this category yet.
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((item) => (
              <div
                key={item.id}
                className="rounded-lg border border-brand-border bg-brand-surface p-3.5 space-y-2"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div>
                    <h4 className="text-xs font-bold text-brand-text">
                      {item.project_name}
                    </h4>
                    <p className="text-[11px] text-brand-text-muted">
                      {item.lgu_name} · Requirement: <span className="font-medium text-brand-text">{item.requirement_name}</span>
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={badgeClassForStatus(item.resolution_state)}>
                      {item.resolution_state?.toUpperCase()}
                    </span>
                    <span className="text-[10px] text-brand-text-muted tabular-nums">
                      {formatDate(item.created_at)}
                    </span>
                  </div>
                </div>

                <div className="rounded bg-brand-surface-solid p-2.5 text-xs space-y-1.5 border border-brand-border/60">
                  <div>
                    <span className="font-semibold text-rose-700 dark:text-rose-400">Finding: </span>
                    <span className="text-brand-text">{item.finding_observation}</span>
                  </div>
                  <div>
                    <span className="font-semibold text-blue-700 dark:text-blue-400">Corrective Action: </span>
                    <span className="text-brand-text">{item.corrective_instruction}</span>
                  </div>
                  {item.resolution_notes && (
                    <div>
                      <span className="font-semibold text-emerald-700 dark:text-emerald-400">Resolution: </span>
                      <span className="text-brand-text-muted">{item.resolution_notes}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}
