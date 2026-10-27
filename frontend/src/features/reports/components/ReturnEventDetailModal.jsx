import { Modal, Button } from '../../../components'
import { AlertCircle, Calendar, CornerUpLeft, ExternalLink, FileText, Layers, User } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ROUTES } from '../../../config/routes'
import { formatStatus } from '../../../lib/formatters'

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
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return isoStr
  }
}

function formatLabel(value) {
  return String(value || 'N/A')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

export default function ReturnEventDetailModal({
  requirementData,
  open,
  onClose,
}) {
  if (!requirementData) return null

  const events = requirementData.events || []

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={requirementData.requirement_name}
      description={`Documented Revision Return Events (${formatNumber(events.length)} total events recorded)`}
      size="xl"
      footer={(
        <div className="flex justify-end">
          <Button variant="outline" onClick={onClose}>Close</Button>
        </div>
      )}
    >
      <div className="space-y-4">
        {/* Requirement stats pills */}
        <div className="flex flex-wrap items-center gap-3 border-b border-brand-border pb-3 text-xs">
          <div className="flex items-center gap-1.5 rounded-md bg-rose-50 dark:bg-rose-950/40 px-2.5 py-1 text-rose-700 dark:text-rose-300 font-semibold">
            <CornerUpLeft className="h-3.5 w-3.5" />
            <span>{formatNumber(requirementData.return_count)} Return Events</span>
          </div>
          <div className="flex items-center gap-1.5 text-brand-text-muted">
            <FileText className="h-3.5 w-3.5 opacity-70" />
            <span>Unique Requirements:</span>
            <span className="font-bold text-brand-text tabular-nums">{formatNumber(requirementData.unique_requirements_count)}</span>
          </div>
          <div className="flex items-center gap-1.5 text-brand-text-muted">
            <Layers className="h-3.5 w-3.5 opacity-70" />
            <span>Projects Affected:</span>
            <span className="font-bold text-brand-text tabular-nums">{formatNumber(requirementData.affected_projects_count)}</span>
          </div>
        </div>

        {/* Return Events List */}
        {events.length === 0 ? (
          <div className="py-8 text-center text-sm text-brand-text-muted">
            No detailed return event records found for this requirement.
          </div>
        ) : (
          <div className="max-h-[60vh] space-y-3 overflow-y-auto pr-1">
            {events.map((event, idx) => (
              <div
                key={event.transition_id || idx}
                className="rounded-lg border border-brand-border bg-brand-surface p-4 shadow-sm"
              >
                {/* Event header */}
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Link
                        to={ROUTES.projectDetail(event.project_id)}
                        className="font-semibold text-brand-primary hover:underline flex items-center gap-1"
                      >
                        {event.project_name}
                        <ExternalLink className="h-3 w-3 inline" />
                      </Link>
                      <span className="text-xs text-brand-text-muted">·</span>
                      <span className="text-xs font-medium text-brand-text-muted">{event.lgu_name}</span>
                    </div>
                    {event.program_name && (
                      <p className="mt-0.5 text-xs text-brand-text-muted">{event.program_name}</p>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2 shrink-0">
                    <span className="text-xs text-brand-text-muted flex items-center gap-1">
                      <Calendar className="h-3.5 w-3.5" />
                      {formatDate(event.created_at)}
                    </span>
                    <span className="rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-brand-text">
                      Status: {formatLabel(event.current_compliance_status || event.current_status)}
                    </span>
                  </div>
                </div>

                {/* Return Reason */}
                <div className="mt-3 rounded-md bg-rose-50/70 dark:bg-rose-950/30 p-3 text-xs border border-rose-100 dark:border-rose-900/50">
                  <div className="font-semibold text-rose-800 dark:text-rose-300 flex items-center gap-1.5 mb-1">
                    <AlertCircle className="h-3.5 w-3.5" />
                    Reviewer Return Reason
                  </div>
                  <p className="text-rose-900 dark:text-rose-200 whitespace-pre-wrap leading-relaxed">
                    {event.remarks || event.reason || 'No specific text reason recorded.'}
                  </p>
                </div>

                {/* Actor & Custody */}
                <div className="mt-2.5 flex items-center justify-between text-[11px] text-brand-text-muted">
                  <span className="flex items-center gap-1">
                    <User className="h-3 w-3" />
                    Reviewer: <span className="font-medium text-brand-text">{event.actor_name}</span>
                  </span>
                  <span>
                    Workflow: <span className="font-medium text-brand-text">{formatStatus(event.current_workflow_status)}</span>
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}
