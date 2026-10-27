import {
  BookOpen,
  FileSpreadsheet,
  FileText,
  Landmark,
  Layers,
  Send,
} from 'lucide-react'

// Single source of truth for the seven Reference_Type values defined in
// the Library glossary. Keep aligned with library_service.VALID_REFERENCE_TYPES
// on the backend.
export const REFERENCE_TYPE_META = {
  memorandum: { tone: 'info', icon: FileText, label: 'Memorandum' },
  circular: { tone: 'handoff', icon: Send, label: 'Circular' },
  annex: { tone: 'warning', icon: BookOpen, label: 'Annex' },
  local_budget_circular: { tone: 'success', icon: Landmark, label: 'Local Budget Circular' },
  omnibus_guideline: { tone: 'neutral', icon: BookOpen, label: 'Omnibus Guideline' },
  other: { tone: 'neutral', icon: Layers, label: 'Other' },
  template: { tone: 'info', icon: FileSpreadsheet, label: 'Template' },
}

export const REFERENCE_TYPE_LABELS = Object.fromEntries(
  Object.entries(REFERENCE_TYPE_META).map(([key, meta]) => [key, meta.label]),
)
