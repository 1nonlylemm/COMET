import {
  AlertTriangle,
  BookOpen,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  Clock,
  FileText,
  Landmark,
  Layers,
  MapPinned,
  MessageSquareText,
  Send,
  Timer,
  Upload,
  Workflow,
} from 'lucide-react'
import { formatMachineLabel } from '../lib/formatters'
import { badgeClassForTone } from '../lib/statusStyles'

const CATEGORY_META = {
  program_type: {
    infrastructure: { tone: 'info', icon: Building2, label: 'Infrastructure' },
    non_infrastructure: { tone: 'warning', icon: FileText, label: 'Non-Infrastructure' },
    hybrid: { tone: 'handoff', icon: Layers, label: 'Hybrid' },
  },
  requirement_type: {
    document: { tone: 'info', icon: FileText, label: 'Document' },
    certificate: { tone: 'success', icon: CheckCircle2, label: 'Certificate' },
    resolution: { tone: 'warning', icon: FileText, label: 'Resolution' },
    financial: { tone: 'handoff', icon: Landmark, label: 'Financial' },
    engineering: { tone: 'neutral', icon: Workflow, label: 'Engineering' },
    inspection: { tone: 'success', icon: ClipboardCheck, label: 'Inspection' },
    other: { tone: 'neutral', icon: Layers, label: 'Other' },
  },
  monitoring_type: {
    qaar: { tone: 'info', icon: ClipboardCheck, label: 'QAAR Monitoring' },
    aide_memoire: { tone: 'warning', icon: FileText, label: 'Aide Memoire Capture' },
    site_validation: { tone: 'success', icon: MapPinned, label: 'Site Validation' },
    follow_up: { tone: 'handoff', icon: Send, label: 'Follow-Up / Corrective Action' },
  },
  guideline_type: {
    memorandum: { tone: 'info', icon: FileText, label: 'Memorandum' },
    circular: { tone: 'handoff', icon: Send, label: 'Circular' },
    annex: { tone: 'warning', icon: BookOpen, label: 'Annex' },
    local_budget_circular: { tone: 'success', icon: Landmark, label: 'Local Budget Circular' },
    omnibus_guideline: { tone: 'neutral', icon: BookOpen, label: 'Omnibus Guideline' },
    other: { tone: 'neutral', icon: Layers, label: 'Other' },
  },
  deadline_type: {
    notice_of_eligibility_5day: { tone: 'danger', icon: AlertTriangle, label: 'Notice of Eligibility (5 Working Days)' },
    standard_15day: { tone: 'warning', icon: Timer, label: '15-Working-Day Notice Window' },
    custom_sla: { tone: 'info', icon: Clock, label: 'Internal Tracking Timer' },
    rectification_period: { tone: 'handoff', icon: ClipboardCheck, label: 'Rectification Period' },
  },
  communication_channel: {
    email: { tone: 'info', icon: Send, label: 'Email' },
    magic_link: { tone: 'handoff', icon: Upload, label: 'Magic Link' },
    sms: { tone: 'warning', icon: MessageSquareText, label: 'SMS' },
    manual_print: { tone: 'neutral', icon: FileText, label: 'Manual Print' },
  },
}

function normalize(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
}

export function CategoryBadge({ category, value, label, className = '' }) {
  if (!value) return '—'

  const normalized = normalize(value)
  const meta = CATEGORY_META[category]?.[normalized] || {
    tone: 'neutral',
    icon: Layers,
    label: label || formatMachineLabel(value),
  }
  const Icon = meta.icon

  return (
    <span className={`${badgeClassForTone(meta.tone)} ${className}`}>
      {Icon && <Icon className="h-3.5 w-3.5" strokeWidth={1.7} aria-hidden="true" />}
      <span>{label || meta.label || formatMachineLabel(value)}</span>
    </span>
  )
}
