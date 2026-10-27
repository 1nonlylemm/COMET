import { ShieldCheck } from 'lucide-react'
import { formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import {
  complianceStatusClass,
  complianceStatusLabel,
  fileMeta,
  formatComplianceScore,
  formatDate,
} from './intakeFormatters.js'

export function StatusBadge({ row }) {
  const status = row?.status || 'pending'
  return (
    <span className={badgeClassForStatus(status)}>
      {formatStatus(status)}
    </span>
  )
}

export function FileSummary({ fileName, date, compact = false }) {
  const displayName = fileName || 'Document'
  const { Icon, label, className } = fileMeta(displayName)

  return (
    <div className="flex min-w-0 items-center gap-2">
      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md border ${className}`} title={label.toUpperCase()}>
        <Icon className="h-4 w-4" strokeWidth={1.7} />
      </div>
      <div className="min-w-0">
        <div className={`truncate font-medium text-brand-text ${compact ? 'max-w-[180px] text-sm' : 'text-sm'}`} title={displayName}>
          {displayName}
        </div>
        {date && (
          <div className="text-xs text-brand-text-muted">{formatDate(date)}</div>
        )}
      </div>
    </div>
  )
}

export function ComplianceSummary({ result, compact = false }) {
  if (!result) {
    return (
      <div className="flex items-center gap-2 text-xs text-brand-text-muted">
        <ShieldCheck className="h-3.5 w-3.5" strokeWidth={1.7} />
        <span>No compliance check yet</span>
      </div>
    )
  }
  return (
    <div className={compact ? 'mt-1 flex flex-wrap items-center gap-1.5' : 'flex flex-wrap items-center gap-2'}>
      <span className={complianceStatusClass(result)}>{complianceStatusLabel(result)}</span>
      <span className="inline-flex items-center rounded-full border border-brand-border bg-brand-surface px-2 py-0.5 text-xs font-semibold text-brand-text">
        {formatComplianceScore(result)}
      </span>
    </div>
  )
}
