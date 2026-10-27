import { Layers } from 'lucide-react'
import { badgeClassForTone } from '../../../lib/statusStyles'
import { REFERENCE_TYPE_META } from './referenceTypeMeta'

export default function ReferenceTypeChip({ referenceType, className = '' }) {
  if (!referenceType) return '—'

  const meta = REFERENCE_TYPE_META[referenceType] || {
    tone: 'neutral',
    icon: Layers,
    label: String(referenceType).replace(/_/g, ' '),
  }
  const Icon = meta.icon

  return (
    <span className={`${badgeClassForTone(meta.tone)} ${className}`}>
      {Icon && <Icon className="h-3.5 w-3.5" strokeWidth={1.7} aria-hidden="true" />}
      <span>{meta.label}</span>
    </span>
  )
}
