import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  Archive,
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock,
  Download,
  FileText,
  ListChecks,
  Loader2,
  Maximize2,
  MessageCircle,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Paperclip,
  RotateCcw,
  Search,
  Send,
  Settings,
  ShieldAlert,
  Wrench,
  X,
} from 'lucide-react'
import { Button, Drawer, InlineAlert } from '../../../components'
import { ROUTES } from '../../../config/routes'
import { formatMachineLabel, formatTableCell } from '../../../lib/formatters'
import { useBranding } from '../../../hooks/useBranding'
import * as aiApi from '../api/aiApi'
import AssistantMarkdownContent from './AssistantMarkdownContent'

const DOCUMENT_UPLOAD_ACCEPT = '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.csv'
const MAX_UPLOAD_BYTES = 25 * 1024 * 1024 // 25 MB
const ALLOWED_UPLOAD_EXTENSIONS = new Set(['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'jpg', 'jpeg', 'png', 'csv'])

const LAST_CONVERSATION_KEY = 'brand_ai_active_conversation_id'
const HISTORY_PANEL_VISIBLE_KEY = 'brand_ai_history_panel_visible'
const TOOLS_PANEL_VISIBLE_KEY = 'brand_ai_tools_panel_visible'
const INTERNAL_IMPORT_FIELDS = new Set([
  'preview_token', 'preview_fingerprint', 'mapping_fingerprint',
  'template_fingerprint', 'file_hash', 'preview_expires_in_seconds',
  'expected_revision',
])

const DETAIL_BADGE_CLASSES = {
  emerald: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800',
  amber: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:ring-amber-800',
  red: 'bg-red-50 text-red-700 ring-1 ring-red-200 dark:bg-red-900/30 dark:text-red-300 dark:ring-red-800',
  blue: 'bg-blue-50 text-blue-700 ring-1 ring-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:ring-blue-800',
  slate: 'bg-slate-100 text-slate-600 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700',
}

const DETAIL_STATUS_KEYS = /(status|state|decision|level|risk|ready|resolved|overdue|triggered|enabled|valid|configured)$/i
const DETAIL_DATE_KEYS = /(date|_at|generated|sent|acknowledged|resolved|trigger)$/i

const THINKING_VERBS = [
  'Reading the current thread',
  'Checking workspace records',
  'Checking available actions',
  'Reviewing project context',
  'Drafting a response',
]

function makeTemporaryId(prefix) {
  if (typeof window !== 'undefined' && window.crypto?.randomUUID) {
    return `${prefix}-${window.crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function readBooleanPreference(key, fallback) {
  if (typeof window === 'undefined') return fallback
  try {
    const value = window.localStorage.getItem(key)
    return value === null ? fallback : value === 'true'
  } catch {
    return fallback
  }
}

function writeBooleanPreference(key, value) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, String(value))
  } catch {
    // Preference persistence should never block the workspace UI.
  }
}

function formatCell(value, key = '') {
  return formatTableCell(value, key, '-')
}

function isLinkValue(value) {
  return typeof value === 'string' && /^(https?:\/\/|\/[^\s]*)/.test(value.trim())
}

function LinkValue({ value, className = '' }) {
  const href = String(value).trim()
  const isExternal = /^https?:\/\//i.test(href)
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className={`break-all font-medium text-blue-600 hover:underline dark:text-blue-400 ${className}`.trim()}
    >
      {isExternal ? href : href}
    </a>
  )
}

function formatDateTime(value) {
  if (!value) return ''
  try {
    return new Intl.DateTimeFormat([], {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }).format(new Date(value))
  } catch {
    return ''
  }
}

function stripLeadingResponseColon(content) {
  if (typeof content !== 'string') return ''
  return content.replace(/^\s*:\s*/, '')
}

function normalizeMessage(message) {
  if (!message || message.role !== 'assistant') return message
  const content = stripLeadingResponseColon(message.content)
  return content === message.content ? message : { ...message, content }
}

function normalizeMessages(messages = []) {
  return messages.map(normalizeMessage)
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isEmptyDetailValue(value) {
  if (value === null || value === undefined || value === '') return true
  if (Array.isArray(value)) return value.length === 0
  if (isPlainObject(value)) return Object.keys(value).length === 0
  return false
}

function formatBytes(value) {
  const bytes = Number(value)
  if (!Number.isFinite(bytes)) return formatCell(value)
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDetailDate(value, key = '') {
  if (!value || !DETAIL_DATE_KEYS.test(key)) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const hasTime = /T|\d{1,2}:\d{2}/.test(String(value))
  return new Intl.DateTimeFormat([], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    ...(hasTime ? { hour: 'numeric', minute: '2-digit' } : {}),
  }).format(date)
}

function formatDetailValue(value, key = '') {
  if (isEmptyDetailValue(value)) return '-'
  if (String(key).toLowerCase().includes('size_bytes')) return formatBytes(value)
  const formattedDate = formatDetailDate(value, key)
  if (formattedDate) return formattedDate
  return formatCell(value, key)
}

function toneForValue(value) {
  const normalized = String(value ?? '').toLowerCase()
  if (['ready', 'resolved', 'completed', 'compliant', 'success', 'valid', 'yes', 'true', 'sent', 'acknowledged'].includes(normalized)) {
    return 'emerald'
  }
  if (['warning', 'pending', 'pending_confirmation', 'in_progress', 'open', 'draft', 'not_required'].includes(normalized)) {
    return 'amber'
  }
  if (['failed', 'blocked', 'overdue', 'non_compliant', 'error', 'no', 'false'].includes(normalized)) {
    return 'red'
  }
  if (['disabled', 'waived', 'cancelled', 'canceled'].includes(normalized)) {
    return 'slate'
  }
  return 'blue'
}

function DetailBadge({ value, tone }) {
  return (
    <span className={`inline-flex max-w-full items-center rounded-md px-2 py-0.5 text-[11px] font-semibold ${DETAIL_BADGE_CLASSES[tone || toneForValue(value)]}`}>
      <span className="truncate">{formatDetailValue(value)}</span>
    </span>
  )
}

function DetailValue({ value, itemKey = '' }) {
  if (isEmptyDetailValue(value)) {
    return <span className="text-brand-text-muted">-</span>
  }

  if (isLinkValue(value)) {
    return <LinkValue value={value} />
  }

  if (typeof value === 'boolean' || (typeof value === 'string' && DETAIL_STATUS_KEYS.test(itemKey))) {
    return <DetailBadge value={typeof value === 'boolean' ? (value ? 'yes' : 'no') : value} />
  }

  return <span className="break-words text-brand-text">{formatDetailValue(value, itemKey)}</span>
}

function MetricValue({ value }) {
  if (isPlainObject(value)) {
    const entries = Object.entries(value).filter(([, entryValue]) => !isEmptyDetailValue(entryValue))
    if (entries.length === 0) {
      return <div className="mt-1 text-base font-semibold text-brand-text">-</div>
    }

    return (
      <dl className="mt-2 space-y-1.5">
        {entries.map(([key, entryValue]) => (
          <div key={key} className="flex items-baseline justify-between gap-3 text-xs">
            <dt className="min-w-0 truncate text-brand-text-muted">{formatMachineLabel(key)}</dt>
            <dd className="shrink-0 font-semibold text-brand-text">{formatDetailValue(entryValue, key)}</dd>
          </div>
        ))}
      </dl>
    )
  }

  return <div className="mt-1 text-base font-semibold text-brand-text">{formatCell(value)}</div>
}

function DetailGrid({ entries, columns = 'md:grid-cols-2', flat = false }) {
  const visibleEntries = entries.filter((entry) => !isEmptyDetailValue(entry.value) || entry.content)
  if (visibleEntries.length === 0) return null

  if (flat) {
    return (
      <dl className={`grid grid-cols-1 gap-x-5 gap-y-2.5 ${columns}`}>
        {visibleEntries.map((entry) => (
          <div key={entry.key || entry.label} className={entry.wide ? 'md:col-span-2' : ''}>
            <dt className="text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">
              {entry.label}
            </dt>
            <dd className="mt-0.5 text-sm">
              {entry.content || <DetailValue value={entry.value} itemKey={entry.key} />}
            </dd>
          </div>
        ))}
      </dl>
    )
  }

  return (
    <div className={`grid grid-cols-1 gap-1.5 ${columns}`}>
      {visibleEntries.map((entry) => (
        <div
          key={entry.key || entry.label}
          className={`${entry.wide ? 'md:col-span-2' : ''} rounded-md border border-brand-border bg-brand-surface p-2`}
        >
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">
            {entry.label}
          </div>
          <div className="text-sm">
            {entry.content || <DetailValue value={entry.value} itemKey={entry.key} />}
          </div>
        </div>
      ))}
    </div>
  )
}

function DetailSection({ title, icon: Icon, children }) {
  if (!children) return null
  return (
    <section className="mt-3 rounded-md border border-brand-border bg-white p-3 dark:bg-slate-900">
      <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">
        {Icon && <Icon className="h-3.5 w-3.5" />}
        <span>{title}</span>
      </div>
      {children}
    </section>
  )
}

function DetailTextBlock({ title, children }) {
  if (!children) return null
  return (
    <div className="rounded-md border border-brand-border bg-brand-surface p-3">
      {title && (
        <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">
          {title}
        </div>
      )}
      <div className="max-h-48 overflow-auto whitespace-pre-wrap text-sm leading-6 text-brand-text">
        {children}
      </div>
    </div>
  )
}

function ObjectSummary({ value, flat = false }) {
  if (!isPlainObject(value)) return <DetailValue value={value} />
  const scalarEntries = Object.entries(value)
    .filter(([, entryValue]) => !isPlainObject(entryValue) && !Array.isArray(entryValue) && !isEmptyDetailValue(entryValue))
    .slice(0, 8)
    .map(([key, entryValue]) => ({ key, label: formatMachineLabel(key), value: entryValue }))

  return <DetailGrid entries={scalarEntries} flat={flat} />
}

const NAME_KEY_REGEX = /(^name$|_name$|title$|label$)/i
const ID_KEY_REGEX = /(^id$|_id$)/i

function ObjectListRow({ value }) {
  const entries = Object.entries(value).filter(
    ([, v]) => !isPlainObject(v) && !Array.isArray(v) && !isEmptyDetailValue(v),
  )
  if (entries.length === 0) return <span className="text-brand-text-muted">-</span>

  const primary = entries.find(([k]) => NAME_KEY_REGEX.test(k)) || entries[0]
  const status = entries.find(([k]) => DETAIL_STATUS_KEYS.test(k))
  const identifier = entries.find(([k]) => ID_KEY_REGEX.test(k))
  const usedKeys = new Set([primary?.[0], status?.[0], identifier?.[0]].filter(Boolean))
  const others = entries.filter(([k]) => !usedKeys.has(k)).slice(0, 3)

  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          {identifier && (
            <span className="font-mono text-[11px] text-brand-text-muted">#{formatDetailValue(identifier[1], identifier[0])}</span>
          )}
          <span className="font-medium text-brand-text">
            {primary ? formatDetailValue(primary[1], primary[0]) : '-'}
          </span>
        </div>
        {others.length > 0 && (
          <dl className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-brand-text-muted">
            {others.map(([k, v]) => (
              <div key={k} className="flex items-baseline gap-1">
                <dt className="font-medium">{formatMachineLabel(k)}:</dt>
                <dd>{formatDetailValue(v, k)}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
      {status && <DetailBadge value={status[1]} />}
    </div>
  )
}

function DetailList({ title, items, tone = 'blue' }) {
  const visibleItems = (items || []).filter((item) => !isEmptyDetailValue(item)).slice(0, 8)
  if (visibleItems.length === 0) return null

  return (
    <div className="overflow-hidden rounded-md border border-brand-border bg-white dark:bg-slate-900">
      <div className="flex items-center justify-between gap-2 border-b border-brand-border bg-brand-surface px-3 py-2">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">
          {title}
        </div>
        <DetailBadge value={visibleItems.length} tone={tone} />
      </div>
      <ul className="divide-y divide-brand-border">
        {visibleItems.map((item, index) => (
          <li key={`${title}-${index}`} className="px-3 py-2 text-sm leading-5 text-brand-text">
            {isPlainObject(item) ? <ObjectListRow value={item} /> : formatDetailValue(item)}
          </li>
        ))}
      </ul>
    </div>
  )
}

function ComplianceSummaryDetail({ detail }) {
  return (
    <div className="mt-3 space-y-3">
      <DetailTextBlock title="Executive Summary">{detail.executive_summary}</DetailTextBlock>
      <DetailGrid
        entries={Object.entries(detail.source_metrics || {}).map(([key, value]) => ({
          key,
          label: formatMachineLabel(key),
          value,
        }))}
        columns="sm:grid-cols-2 lg:grid-cols-4"
      />
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <DetailList title="Bottlenecks" items={detail.bottlenecks} tone="amber" />
        <DetailList title="Recommended Actions" items={detail.recommended_actions} tone="emerald" />
        <DetailList title="Risk Flags" items={detail.risk_flags} tone="red" />
      </div>
      <DetailGrid
        entries={[
          { key: 'generated_at', label: 'Generated', value: detail.generated_at },
          { key: 'ai_provider_used', label: 'Provider', value: detail.ai_provider_used },
          { key: 'ai_model_used', label: 'Model', value: detail.ai_model_used },
        ]}
      />
    </div>
  )
}

function SettingsReadinessDetail({ detail }) {
  const summary = detail.summary || {}
  const checks = Array.isArray(detail.checks) ? detail.checks : []

  return (
    <div className="mt-3 space-y-3">
      <DetailGrid
        entries={[
          { key: 'ready', label: 'Ready', value: summary.ready },
          { key: 'warning', label: 'Warnings', value: summary.warning },
          { key: 'disabled', label: 'Disabled', value: summary.disabled },
          { key: 'total', label: 'Total Checks', value: summary.total },
        ]}
        columns="grid-cols-2 lg:grid-cols-4"
      />
      <div className="grid grid-cols-1 gap-1.5 md:grid-cols-2">
        {checks.map((check) => (
          <div key={check.key} className="rounded-md border border-brand-border bg-brand-surface p-3">
            <div className="mb-1 flex items-start justify-between gap-2">
              <div className="text-xs font-semibold text-brand-text">
                {formatMachineLabel(check.key)}
              </div>
              <DetailBadge value={check.status} />
            </div>
            <p className="text-xs leading-5 text-brand-text-muted">{check.message}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function DeadlineDetail({ detail }) {
  return (
    <div className="mt-3 space-y-3">
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-3">
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-2.5 dark:border-emerald-900/60 dark:bg-emerald-950/30">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">Resolution</div>
          <DetailBadge value={detail.is_resolved ? 'resolved' : 'open'} />
        </div>
        <div className="rounded-md border border-brand-border bg-brand-surface p-2.5">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">Deadline State</div>
          <DetailBadge value={detail.is_overdue ? 'overdue' : 'on_track'} />
        </div>
        <div className="rounded-md border border-brand-border bg-brand-surface p-2.5">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">Escalation</div>
          <DetailBadge value={detail.escalation_triggered ? 'triggered' : 'not_triggered'} />
        </div>
      </div>
      <DetailGrid
        entries={[
          { key: 'id', label: 'Deadline ID', value: detail.id },
          { key: 'deadline_type', label: 'Timer Type', value: detail.deadline_type },
          { key: 'project_name', label: 'Project', value: detail.project_name, wide: true },
          { key: 'requirement_name', label: 'Requirement', value: detail.requirement_name, wide: true },
          { key: 'deadline_date', label: 'Deadline Date', value: detail.deadline_date },
          { key: 'trigger_date', label: 'Trigger Date', value: detail.trigger_date },
          { key: 'sla_working_days', label: 'Working-Day Target', value: detail.sla_working_days },
          { key: 'days_remaining', label: 'Working Days Remaining', value: detail.days_remaining },
          { key: 'resolved_at', label: 'Resolved At', value: detail.resolved_at },
          { key: 'notes', label: 'Notes', value: detail.notes, wide: true },
        ]}
      />
    </div>
  )
}

function SectionHeading({ icon: Icon, title, trailing }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">
        {Icon && <Icon className="h-3.5 w-3.5" />}
        <span>{title}</span>
      </div>
      {trailing}
    </div>
  )
}

function ProjectOverviewDetail({ detail }) {
  const requirementSummary = detail.requirement_summary || {}
  const phaseGate = detail.phase_gate
  const lgu = detail.lgu || {}
  const program = detail.program || {}

  const summaryChips = Object.entries(requirementSummary)
    .filter(([, v]) => !isEmptyDetailValue(v))
    .map(([key, value]) => ({ key, label: formatMachineLabel(key), value }))

  return (
    <div className="mt-3 space-y-4">
      <DetailGrid
        flat
        entries={[
          { key: 'project_name', label: 'Project', value: detail.project_name, wide: true },
          { key: 'lgu_name', label: 'LGU', value: lgu.name || detail.lgu_name },
          { key: 'program_name', label: 'Program', value: program.name || detail.program_name },
          { key: 'fiscal_year', label: 'Fiscal Year', value: detail.fiscal_year },
          { key: 'current_phase', label: 'Current Phase', value: detail.current_phase },
          { key: 'overall_status', label: 'Overall Status', value: detail.overall_status },
          { key: 'source_project_code', label: 'Source Code', value: detail.source_project_code },
          { key: 'pending_change_requests', label: 'Pending Change Requests', value: detail.pending_change_requests },
        ]}
      />

      {summaryChips.length > 0 && (
        <div className="space-y-2 border-t border-brand-border pt-3">
          <SectionHeading icon={ListChecks} title="Requirement Summary" />
          <div className="flex flex-wrap gap-1.5">
            {summaryChips.map((chip) => (
              <span
                key={chip.key}
                className="inline-flex items-center gap-1.5 rounded-md border border-brand-border bg-brand-surface px-2 py-1 text-[11px]"
              >
                <span className="font-semibold text-brand-text">{formatDetailValue(chip.value, chip.key)}</span>
                <span className="text-brand-text-muted">{chip.label}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {phaseGate && (
        <div className="space-y-2 border-t border-brand-border pt-3">
          <SectionHeading
            icon={Clock}
            title={`Phase Gate — ${phaseGate.current_phase_label || ''}`.trim()}
            trailing={<DetailBadge value={phaseGate.can_advance ? 'ready' : 'blocked'} />}
          />
          <DetailList title="Blocking Requirements" items={phaseGate.blocking_requirements} tone="amber" />
        </div>
      )}

      {(detail.revision_requirements || []).length > 0 && (
        <div className="space-y-2 border-t border-brand-border pt-3">
          <DetailList title="Returned Requirements" items={detail.revision_requirements} tone="amber" />
        </div>
      )}
    </div>
  )
}

function HandoffDetail({ detail }) {
  return (
    <div className="mt-3 space-y-3">
      <DetailGrid
        entries={[
          { key: 'push_status', label: 'Push Status', value: detail.push_status },
          { key: 'already_handed_off', label: 'Already Handed Off', value: detail.already_handed_off },
          { key: 'project_requirement_id', label: 'Requirement ID', value: detail.project_requirement_id },
          { key: 'submission_id', label: 'Submission ID', value: detail.submission_id },
          { key: 'files_count', label: 'Files', value: detail.files_count },
          { key: 'total_size_bytes', label: 'Total Size', value: detail.total_size_bytes },
          { key: 'destination_path', label: 'Destination Path', value: detail.destination_path, wide: true },
          { key: 'drive_folder_url', label: 'Drive Folder', value: detail.drive_folder_url, wide: true },
          { key: 'pushed_at', label: 'Pushed At', value: detail.pushed_at },
          { key: 'error_message', label: 'Error Message', value: detail.error_message, wide: true },
        ]}
      />
    </div>
  )
}

function NoticeDetail({ detail }) {
  const noticeText = detail.final_text || detail.ai_generated_text || detail.body_text
  return (
    <div className="mt-3 space-y-3">
      <DetailGrid
        entries={[
          { key: 'title', label: 'Title', value: detail.title, wide: true },
          { key: 'notice_type', label: 'Notice Type', value: detail.notice_type },
          { key: 'status', label: 'Status', value: detail.status },
          { key: 'notice_number', label: 'Notice Number', value: detail.notice_number },
          { key: 'project_name', label: 'Project', value: detail.project_name, wide: true },
          { key: 'lgu_name', label: 'LGU', value: detail.lgu_name },
          { key: 'requirement_name', label: 'Requirement', value: detail.requirement_name },
          { key: 'generated_at', label: 'Generated At', value: detail.generated_at },
          { key: 'generator_name', label: 'Prepared By', value: detail.generator_name },
          { key: 'recipient_count', label: 'Recipients', value: detail.recipient_count },
        ]}
      />
      <DetailTextBlock title="Prepared Notice Text">{noticeText}</DetailTextBlock>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <DetailList title="Recipients" items={detail.recipients} tone="blue" />
        <DetailList title="Communications" items={detail.communications} tone="emerald" />
      </div>
      <DetailList title="Legal Findings" items={detail.legal_findings} tone="amber" />
    </div>
  )
}

function GenericDetailResult({ detail }) {
  const entries = Object.entries(detail || {}).filter(([key]) => !INTERNAL_IMPORT_FIELDS.has(key))
  const scalarEntries = entries
    .filter(([, value]) => !Array.isArray(value) && !isPlainObject(value))
    .map(([key, value]) => ({ key, label: formatMachineLabel(key), value }))
  const listEntries = entries.filter(([, value]) => Array.isArray(value) && value.length > 0)
  const objectEntries = entries.filter(([, value]) => isPlainObject(value) && Object.keys(value).length > 0)

  return (
    <div className="mt-3 space-y-3">
      <DetailGrid entries={scalarEntries} />
      {listEntries.map(([key, value]) => (
        <DetailList key={key} title={formatMachineLabel(key)} items={value} />
      ))}
      {objectEntries.map(([key, value]) => (
        <DetailSection key={key} title={formatMachineLabel(key)} icon={FileText}>
          <ObjectSummary value={value} />
        </DetailSection>
      ))}
    </div>
  )
}

function DetailResult({ toolName, detail }) {
  if (toolName === 'generate_compliance_summary' || detail.executive_summary) {
    return <ComplianceSummaryDetail detail={detail} />
  }
  if (toolName === 'settings_readiness' || Array.isArray(detail.checks)) {
    return <SettingsReadinessDetail detail={detail} />
  }
  if (toolName === 'resolve_sla_deadline') {
    return <DeadlineDetail detail={detail} />
  }
  if (toolName === 'get_project_overview') {
    return <ProjectOverviewDetail detail={detail} />
  }
  if (toolName === 'push_requirement_handoff') {
    return <HandoffDetail detail={detail} />
  }
  if (toolName === 'generate_notice_for_sla') {
    return <NoticeDetail detail={detail} />
  }
  return <GenericDetailResult detail={detail} />
}

function buildConfirmationFields(outputArguments = {}) {
  if (!isPlainObject(outputArguments)) return { fields: [], notice: null }

  const displayObj = isPlainObject(outputArguments.confirmation_display)
    ? outputArguments.confirmation_display
    : {}

  // Extract notice if present
  const notice = displayObj.notice || outputArguments.notice || null

  const fields = []
  const seenKeys = new Set(['notice', 'confirmation_display', 'confirmation_phrase', ...INTERNAL_IMPORT_FIELDS])

  // 1. High-priority semantic labels
  const priorityKeys = [
    ['file_name', 'File Name'],
    ['file_type', 'File Type'],
    ['project_name', 'Project'],
    ['requirement_name', 'Requirement'],
    ['document_structure', 'Document Structure'],
    ['readability', 'Readability'],
    ['advisory_observations', 'Advisory Observations'],
    ['stage', 'SLA Stage'],
    ['deadline_date', 'Deadline Date'],
    ['comment_type', 'Comment Type'],
    ['visibility', 'Visibility'],
    ['comment', 'Comment'],
    ['body', 'Comment Text'],
    ['backup_id', 'Backup ID'],
    ['target_db', 'Target Database'],
    ['fiscal_year', 'Fiscal Year'],
    ['requirement_id', 'Requirement ID'],
    ['attachment_id', 'Attachment ID'],
    ['sla_id', 'SLA ID'],
  ]

  for (const [k, label] of priorityKeys) {
    const val = displayObj[k] ?? outputArguments[k]
    if (val !== undefined && val !== null && val !== '') {
      fields.push({ key: k, label, value: val })
      seenKeys.add(k)
    }
  }

  // 2. Add remaining confirmation_display keys
  for (const [k, val] of Object.entries(displayObj)) {
    if (!seenKeys.has(k) && val !== undefined && val !== null && val !== '') {
      fields.push({ key: k, label: formatMachineLabel(k), value: val })
      seenKeys.add(k)
    }
  }

  // 3. Add any remaining top-level arguments (skipping raw dicts)
  for (const [k, val] of Object.entries(outputArguments)) {
    if (!seenKeys.has(k) && val !== undefined && val !== null && val !== '') {
      if (isPlainObject(val)) continue
      fields.push({ key: k, label: formatMachineLabel(k), value: val })
      seenKeys.add(k)
    }
  }

  return { fields, notice }
}

function ReportDownloads({ toolCall }) {
  const [busyIndex, setBusyIndex] = useState(null)
  const [error, setError] = useState(null)

  async function download(index) {
    setBusyIndex(index)
    setError(null)
    try {
      const { blob, filename } = await aiApi.downloadToolFile(toolCall.id, index)
      const url = window.URL.createObjectURL(blob)
      try {
        const link = document.createElement('a')
        link.href = url
        link.download = filename
        document.body.appendChild(link)
        link.click()
        link.remove()
      } finally {
        window.URL.revokeObjectURL(url)
      }
    } catch (failure) {
      setError(failure.message || 'The download could not be completed.')
    } finally {
      setBusyIndex(null)
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {(toolCall.output_data?.downloads || []).map((file, index) => (
          <Button key={index} size="sm" variant="outline" disabled={busyIndex !== null} onClick={() => download(index)}>
            {busyIndex === index ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
            {file.label || 'Download file'}
          </Button>
        ))}
      </div>
      {error && <p role="alert" className="text-red-700 dark:text-red-300">{error}</p>}
    </div>
  )
}

function ToolResult({ toolCall, onConfirm, onCancel, isBusy }) {
  const output = toolCall.output_data || {}
  const rows = output.rows || []
  const columns = output.columns || []
  const metrics = output.metrics || []
  const detail = output.detail || {}
  const isPending = toolCall.status === 'pending_confirmation'
  const isFailed = toolCall.status === 'failed'
  const statusTone = isPending ? 'amber' : isFailed ? 'red' : toneForValue(toolCall.status)

  return (
    <div className="mt-2 rounded-lg border border-brand-border bg-white text-xs dark:bg-slate-900">
      {/* Tool result header */}
      <div className="flex items-start justify-between gap-3 border-b border-brand-border px-3 py-2.5">
        <div className="min-w-0">
          <p className="font-semibold text-brand-text">{output.title || toolCall.tool_name}</p>
          <p className="mt-0.5 text-brand-text-muted">
            {isFailed ? toolCall.error_message : output.summary || toolCall.reason || 'Action result'}
          </p>
        </div>
        <span className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ${DETAIL_BADGE_CLASSES[statusTone]}`}>
          {formatMachineLabel(toolCall.status)}
        </span>
      </div>

      <div className="p-3 space-y-3">
        {toolCall.status === 'completed' && output.downloads?.length > 0 && <ReportDownloads toolCall={toolCall} />}
        {isPending && (() => {
          const { fields, notice } = buildConfirmationFields(output.arguments)
          return (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-100">
              <div className="flex items-center justify-between gap-2">
                <p className="font-semibold text-amber-950 dark:text-amber-50">Confirmation required</p>
                <span className="rounded bg-amber-200/70 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-900 dark:bg-amber-900/60 dark:text-amber-200">
                  Risk: {formatMachineLabel(toolCall.risk_level)}
                </span>
              </div>

              {notice && (
                <div className="mt-2 rounded border border-amber-300/80 bg-amber-100/70 p-2 text-xs font-medium text-amber-950 dark:border-amber-800/80 dark:bg-amber-900/40 dark:text-amber-100">
                  {notice}
                </div>
              )}

              {fields.length > 0 && (
                <dl className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {fields.map(({ key, label, value }) => {
                    const isLong = typeof value === 'string' && value.length > 45
                    return (
                      <div key={key} className={isLong ? 'sm:col-span-2' : ''}>
                        <dt className="text-[10px] font-bold uppercase tracking-wider text-amber-800/80 dark:text-amber-300/80">
                          {label}
                        </dt>
                        <dd className="mt-0.5 text-xs font-semibold text-amber-950 dark:text-amber-50 break-words">
                          {formatDetailValue(value, key)}
                        </dd>
                      </div>
                    )
                  })}
                </dl>
              )}

              <div className="mt-3 flex gap-2">
                <Button size="sm" onClick={() => onConfirm(toolCall.id)} disabled={isBusy}>
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  {output.arguments?.confirmation_display?.action_label || 'Confirm'}
                </Button>
                <Button size="sm" variant="outline" onClick={() => onCancel(toolCall.id)} disabled={isBusy}>
                  Cancel
                </Button>
              </div>
            </div>
          )
        })()}

        {metrics.length > 0 && (
          <div className="grid grid-cols-2 gap-1.5">
            {metrics.map((metric) => (
              <div
                key={metric.label}
                className={`rounded-md border border-brand-border bg-brand-surface p-2 ${
                  isPlainObject(metric.value) ? 'col-span-2' : ''
                }`}
              >
                <div className="text-brand-text-muted">{metric.label}</div>
                <MetricValue value={metric.value} />
              </div>
            ))}
          </div>
        )}

        {rows.length > 0 && columns.length > 0 && (
          <div className="max-h-60 overflow-auto rounded-md border border-brand-border">
            <table className="min-w-full divide-y divide-brand-border">
              <thead className="bg-brand-surface">
                <tr>
                  {columns.slice(0, 6).map((column) => (
                    <th key={column.key} className="px-2.5 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-brand-text-muted">
                      {column.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border bg-white dark:bg-slate-900">
                {rows.slice(0, 8).map((row, index) => (
                  <tr key={row.id || row.project_id || row.requirement_id || index} className="hover:bg-brand-surface">
                    {columns.slice(0, 6).map((column) => {
                      const rawValue = row[column.key]
                      return (
                        <td key={column.key} className="px-2.5 py-2 text-brand-text">
                          {isLinkValue(rawValue)
                            ? <LinkValue value={rawValue} />
                            : formatCell(rawValue, column.key)}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {output.display_type === 'detail' && Object.keys(detail).length > 0 && (
          <DetailResult toolName={toolCall.tool_name} detail={detail} />
        )}
      </div>
    </div>
  )
}

function MessageBubble({ message, onConfirm, onCancel, busyToolId, isExpanded }) {
  const isUser = message.role === 'user'
  const toolCalls = message.display_payload?.tool_calls || []
  const guardrail = message.display_payload?.guardrail
  const content = isUser ? message.content : stripLeadingResponseColon(message.content)

  if (message.isGenerating) {
    return <ThinkingStatus />
  }

  return (
    <div className={`flex gap-2.5 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {/* Avatar dot */}
      {!isUser && (
        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-primary/10 text-brand-primary dark:bg-blue-900/40 dark:text-blue-300">
          <Bot className="h-4 w-4" />
        </div>
      )}

      <div className={`${isExpanded ? 'max-w-[72%]' : 'max-w-[86%]'} flex flex-col gap-1`}>
        {/* Guardrail label */}
        {guardrail && !isUser && (
          <div className="flex items-center gap-1.5 px-1 text-[11px] font-semibold text-brand-text-muted">
            <ShieldAlert className="h-3.5 w-3.5" />
            <span>{guardrail.decision === 'blocked' ? 'Request blocked' : 'Scope check'}</span>
          </div>
        )}

        {/* Bubble */}
        <div className={`rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? 'rounded-tr-sm bg-brand-primary text-white dark:text-slate-950'
            : guardrail?.decision === 'blocked'
              ? 'rounded-tl-sm border border-red-200 bg-red-50 text-red-900 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-100'
              : guardrail
                ? 'rounded-tl-sm border border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100'
                : 'rounded-tl-sm border border-brand-border bg-white text-brand-text dark:bg-slate-900 dark:text-slate-100'
        }`}>
          {(message.attachment_filename || message.attachment_stored_object_id) && (
            <div className={`mb-2 inline-flex max-w-full items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium ${
              isUser
                ? 'bg-white/15 text-white border border-white/20 dark:border-slate-950/20 dark:bg-slate-950/10 dark:text-slate-950'
                : 'bg-brand-surface text-brand-text border border-brand-border'
            }`}>
              <FileText className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{message.attachment_filename || `Attachment #${message.attachment_stored_object_id}`}</span>
            </div>
          )}
          {isUser ? (
            <div className="whitespace-pre-wrap">{content}</div>
          ) : (
            <AssistantMarkdownContent content={content} />
          )}
          {Array.isArray(message.display_payload?.ctas) && message.display_payload.ctas.length > 0 && !isUser && (
            <div className="mt-3 flex flex-wrap gap-2 pt-2 border-t border-brand-border/40" data-testid="assistant-ctas">
              {message.display_payload.ctas.map((cta, idx) => (
                <a
                  key={`${cta.url}-${idx}`}
                  href={cta.url}
                  data-testid={`assistant-cta-link-${idx}`}
                  className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition shadow-xs ${
                    cta.type === 'primary'
                      ? 'bg-brand-primary text-white hover:bg-brand-primary/90 dark:text-slate-950'
                      : 'bg-brand-surface text-brand-text hover:bg-brand-border/60 border border-brand-border'
                  }`}
                >
                  <span>{cta.label}</span>
                  <ArrowRight className="h-3 w-3 shrink-0" />
                </a>
              ))}
            </div>
          )}
          {message.deliveryStatus === 'failed' && (
            <p className="mt-2 text-xs font-medium text-red-200 dark:text-red-950">
              Message was not sent. It has been restored to the composer.
            </p>
          )}
        </div>

        {/* Tool call results stay below the bubble, outside the message text. */}
        {toolCalls.length > 0 && (
          <div className="space-y-1.5">
            {toolCalls.map((toolCall) => (
              <ToolResult
                key={toolCall.id}
                toolCall={toolCall}
                onConfirm={onConfirm}
                onCancel={onCancel}
                isBusy={busyToolId === toolCall.id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ThinkingStatus() {
  const [step, setStep] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setStep((current) => (current + 1) % THINKING_VERBS.length)
    }, 1400)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <div className="flex items-start gap-2.5" role="status" aria-live="polite">
      <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-primary/10 text-brand-primary dark:bg-blue-900/40 dark:text-blue-300">
        <Bot className="h-4 w-4" />
      </div>
      <div className="flex items-center gap-2 rounded-xl rounded-tl-sm border border-brand-border bg-white px-4 py-2.5 text-xs font-medium text-brand-text-muted dark:bg-slate-900">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-brand-primary dark:text-blue-400" />
        <span>{THINKING_VERBS[step]}</span>
        <span className="flex gap-0.5" aria-hidden="true">
          <span className="h-1 w-1 animate-pulse rounded-full bg-current" />
          <span className="h-1 w-1 animate-pulse rounded-full bg-current [animation-delay:150ms]" />
          <span className="h-1 w-1 animate-pulse rounded-full bg-current [animation-delay:300ms]" />
        </span>
      </div>
    </div>
  )
}

function ConversationList({
  conversations,
  activeConversationId,
  isLoading,
  search,
  onSearch,
  includeArchived,
  onToggleArchived,
  onSelect,
  onNew,
  onSetStatus,
  onClose,
}) {
  const { branding } = useBranding()
  const filteredConversations = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return conversations
    return conversations.filter((conversation) => (
      (conversation.title || '').toLowerCase().includes(query)
      || (conversation.last_message_preview || '').toLowerCase().includes(query)
    ))
  }, [conversations, search])

  return (
    <aside className="flex max-h-48 w-full shrink-0 flex-col overflow-auto border-b border-brand-border bg-brand-surface dark:bg-slate-950 lg:h-full lg:max-h-none lg:w-72 lg:min-w-48 lg:max-w-[45%] lg:resize-x lg:border-r lg:border-b-0">
      {/* Header */}
      <div className="border-b border-brand-border p-4">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-brand-text">Conversation History</p>
            <p className="mt-0.5 truncate text-[11px] text-brand-text-muted">{branding.assistant_name}</p>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onNew}
              className="rounded-lg bg-brand-primary p-1.5 text-white hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-brand-primary/40 dark:text-slate-950"
              aria-label="Start new conversation"
              title="New conversation"
            >
              <MessageSquarePlus className="h-4 w-4" />
            </button>
            {onClose && (
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg p-1.5 text-brand-text-muted hover:bg-brand-border hover:text-brand-text focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                aria-label="Hide history"
                title="Hide history"
              >
                <PanelLeftClose className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>

        {/* Search */}
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-brand-border bg-white px-2.5 py-1.5 dark:bg-slate-900">
          <Search className="h-3.5 w-3.5 shrink-0 text-brand-text-muted" />
          <input
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            className="w-full bg-transparent text-xs text-brand-text outline-none placeholder:text-brand-text-muted"
            placeholder="Search conversations"
          />
        </div>

        {/* Archive toggle */}
        <button
          type="button"
          onClick={onToggleArchived}
          className="mt-2 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium text-brand-text-muted hover:bg-brand-border hover:text-brand-text"
        >
          {includeArchived ? <RotateCcw className="h-3 w-3" /> : <Archive className="h-3 w-3" />}
          {includeArchived ? 'Show active only' : 'Include archived'}
        </button>
      </div>

      {/* List */}
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-8 text-xs text-brand-text-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Loading history...
          </div>
        ) : filteredConversations.length === 0 ? (
          <div className="rounded-lg border border-dashed border-brand-border p-4 text-xs text-brand-text-muted">
            No conversations found.
          </div>
        ) : (
          <div className="space-y-0.5">
            {filteredConversations.map((conversation) => {
              const isActive = String(activeConversationId || '') === String(conversation.id)
              const isArchived = conversation.status === 'archived'
              const preview = stripLeadingResponseColon(conversation.last_message_preview)
              const title = conversation.title || 'Untitled conversation'
              return (
                <div
                  key={conversation.id}
                  className={`group flex items-start gap-1 rounded-lg border ${
                    isActive
                      ? 'border-brand-primary/20 bg-brand-primary/5 dark:border-blue-900/60 dark:bg-blue-950/30'
                      : 'border-transparent hover:bg-white dark:hover:bg-slate-900'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(conversation.id)}
                    className="min-w-0 flex-1 rounded-md px-2 py-2 text-left"
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="truncate text-xs font-semibold text-brand-text">
                        {title}
                      </span>
                      {conversation.pending_tool_call_count > 0 && (
                        <span className="shrink-0 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-700 dark:bg-amber-900/40 dark:text-amber-200">
                          {conversation.pending_tool_call_count}
                        </span>
                      )}
                      {isArchived && (
                        <span className="shrink-0 rounded-md bg-brand-surface px-1.5 py-0.5 text-[10px] font-medium text-brand-text-muted ring-1 ring-brand-border">
                          Archived
                        </span>
                      )}
                    </div>
                    <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-brand-text-muted">
                      {preview || 'No messages yet'}
                    </p>
                    <div className="mt-1.5 text-[10px] text-brand-text-muted">
                      {formatDateTime(conversation.updated_at)}
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => onSetStatus(conversation.id, isArchived ? 'active' : 'archived')}
                    className="mt-2 rounded-md p-1.5 text-brand-text-muted opacity-100 hover:bg-brand-border hover:text-brand-text lg:opacity-0 lg:group-hover:opacity-100"
                    title={isArchived ? 'Restore' : 'Archive'}
                    aria-label={isArchived ? 'Restore conversation' : 'Archive conversation'}
                  >
                    {isArchived ? <RotateCcw className="h-3.5 w-3.5" /> : <Archive className="h-3.5 w-3.5" />}
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </aside>
  )
}

export function ToolCatalog({ tools, capabilities, isLoading, onClose }) {
  const { branding } = useBranding()
  const [query, setQuery] = useState('')
  const confirmationCount = tools.filter((tool) => tool.requires_confirmation).length
  const groupedTools = useMemo(() => {
    const search = query.trim().toLocaleLowerCase()
    const matching = tools.filter((tool) => !search || [tool.label, tool.category, tool.summary, tool.description,
      ...(tool.notes || []), ...(tool.required_inputs || []).map((input) => input.label),
      ...(tool.supported_inputs || []).map((input) => input.label),
    ].filter(Boolean).join(' ').toLocaleLowerCase().includes(search))
    const grouped = matching.reduce((groups, tool) => {
      const group = tool.category || 'Other actions'
      return {
        ...groups,
        [group]: [...(groups[group] || []), tool],
      }
    }, {})
    return Object.entries(grouped)
  }, [tools, query])
  const matchingCount = groupedTools.reduce((total, [, entries]) => total + entries.length, 0)

  return (
    <aside className="hidden h-full w-72 min-w-72 flex-col border-l border-brand-border bg-brand-surface dark:bg-slate-950 xl:flex">
      <div className="border-b border-brand-border p-4">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-1.5">
              <Wrench className="h-3.5 w-3.5 text-brand-primary dark:text-blue-400" />
              <p className="text-xs font-semibold text-brand-text">Available Actions</p>
            </div>
            <p className="mt-0.5 text-[11px] text-brand-text-muted">
              {branding.app_name} actions for your account
            </p>
            {capabilities?.role_label && <p className="mt-1 text-[11px] font-medium text-brand-text">{capabilities.role_label}</p>}
          </div>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-brand-text-muted hover:bg-brand-border hover:text-brand-text focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
              aria-label="Hide actions"
              title="Hide actions"
            >
              <PanelRightClose className="h-4 w-4" />
            </button>
          )}
        </div>
        {!isLoading && <p className="mt-2 text-[11px] text-brand-text-muted">{tools.length} actions · {confirmationCount} require confirmation</p>}
        <label className="mt-3 block text-[11px] font-medium text-brand-text" htmlFor="assistant-action-search">Find an action</label>
        <input id="assistant-action-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)}
          className="mt-1 w-full rounded-md border border-brand-border bg-white px-2 py-1.5 text-xs text-brand-text dark:bg-slate-900"
          placeholder="Search actions or supported details" />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <div className="flex items-center gap-2 text-xs text-brand-text-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Loading actions...
          </div>
        ) : (
          <div className="space-y-5">
            <div className="space-y-2 text-[11px] leading-4 text-brand-text-muted">
              <p>{capabilities?.scope_note || 'Access to individual records is checked when an action runs.'}</p>
              <p>{capabilities?.confirmation_note || 'Actions marked Confirmation required wait for your approval. Other actions run when requested.'}</p>
              {capabilities?.limits?.length > 0 && <details>
                <summary className="cursor-pointer font-semibold text-brand-text">Limits and actions handled in other pages</summary>
                <ul className="mt-2 list-disc space-y-1 pl-4">{capabilities.limits.map((limit) => <li key={limit}>{limit}</li>)}</ul>
              </details>}
            </div>
            {query.trim() && <p className="text-[11px] text-brand-text-muted">{matchingCount} of {tools.length} actions</p>}
            {matchingCount === 0 && <p className="text-xs text-brand-text-muted">{query.trim() ? 'No actions match your search.' : 'No actions available for this account.'}</p>}
            {groupedTools.map(([group, groupTools]) => (
              <section key={group}>
                <div className="mb-2 flex items-center gap-1.5">
                  {group === 'Settings' && <Settings className="h-3 w-3 text-brand-text-muted" />}
                  {group === 'Compliance' && <ShieldAlert className="h-3 w-3 text-brand-text-muted" />}
                  {group === 'Compliance deadlines' && <Clock className="h-3 w-3 text-brand-text-muted" />}
                  <h3 className="text-[10px] font-bold uppercase tracking-wider text-brand-text-muted">
                    {group}
                  </h3>
                </div>
                <div className="space-y-1.5">
                  {groupTools.map((tool) => (
                    <div
                      key={tool.name}
                      className="rounded-lg border border-brand-border bg-white p-2.5 dark:bg-slate-900"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xs font-semibold text-brand-text">
                          {tool.label || formatMachineLabel(tool.name)}
                        </p>
                        <div className="flex shrink-0 flex-col items-end gap-1">
                          <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${tool.requires_confirmation
                            ? 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                            : 'bg-brand-surface text-brand-text-muted'}`}>
                            {tool.requires_confirmation ? 'Confirmation required' : 'Runs on request'}
                          </span>
                        </div>
                      </div>
                      <p className="mt-1 text-[11px] leading-4 text-brand-text-muted">
                        {tool.summary || tool.description}
                      </p>
                      {(tool.notes || []).map((note) => <p key={note} className="mt-1 text-[11px] leading-4 text-brand-text-muted">{note}</p>)}
                      {(tool.required_inputs || tool.required_args?.map((key) => ({ key, label: formatMachineLabel(key) })))?.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {(tool.required_inputs || tool.required_args?.map((key) => ({ key, label: formatMachineLabel(key) })))
                            ?.filter((input) => !INTERNAL_IMPORT_FIELDS.has(input.key)).map((input) => (
                            <span key={input.key} className="rounded-md bg-brand-surface px-1.5 py-0.5 text-[10px] font-medium text-brand-text-muted ring-1 ring-brand-border">
                              Required: {input.label}
                            </span>
                          ))}
                        </div>
                      )}
                      {tool.supported_inputs?.length > 0 && <details className="mt-2 text-[11px] text-brand-text-muted">
                        <summary className="cursor-pointer font-medium">Supported details</summary>
                        <p className="mt-1">{tool.supported_inputs.filter((input) => !INTERNAL_IMPORT_FIELDS.has(input.key)).map((input) => input.label).join(', ')}</p>
                      </details>}
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}

function EmptyThread({ mode }) {
  const { branding } = useBranding()
  return (
    <div className="mx-auto flex h-full max-w-lg flex-col items-center justify-center px-5 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-brand-border bg-brand-surface text-brand-primary dark:bg-slate-900 dark:text-blue-400">
        <Bot className="h-6 w-6" />
      </div>
      <h2 className="mt-4 text-base font-semibold text-brand-text">
        Ask about {branding.app_name} operations
      </h2>
      <p className="mt-2 text-sm leading-6 text-brand-text-muted">
        Ask "what can you do?" to see the actions available to your account.
        Actions marked Confirmation required wait for your approval.
      </p>
      {mode === 'drawer' && (
        <p className="mt-3 text-xs text-brand-text-muted">
          Expand for conversation history and the full action panel.
        </p>
      )}
    </div>
  )
}

function ChatPanel({
  mode,
  activeConversation,
  messages,
  isThreadLoading,
  draft,
  onDraftChange,
  onSend,
  isSending,
  attachment,
  isUploadingAttachment,
  onFileSelect,
  onRemoveAttachment,
  error,
  onErrorDismiss,
  onConfirm,
  onCancel,
  busyToolId,
  onNew,
  onClose,
  onExpand,
  onRestore,
  isHistoryPanelVisible = true,
  isToolsPanelVisible = true,
  onToggleHistoryPanel,
  onToggleToolsPanel,
}) {
  const navigate = useNavigate()
  const { branding } = useBranding()
  const isExpanded = mode === 'page'
  const isArchived = activeConversation?.status === 'archived'
  const canToggleWorkspacePanels = isExpanded && onToggleHistoryPanel && onToggleToolsPanel
  const [isDraggingOver, setIsDraggingOver] = useState(false)
  const dragCounterRef = useRef(0)
  const fileInputRef = useRef(null)
  const threadRef = useRef(null)
  const responseStartRef = useRef(null)
  const scrollStateRef = useRef(null)
  const readerScrolledRef = useRef(false)
  const lastScrollTopRef = useRef(0)
  const latestAssistant = messages.slice().reverse().find(message => message.role === 'assistant')

  useLayoutEffect(() => {
    if (isThreadLoading) {
      scrollStateRef.current = null
      return
    }
    const viewport = threadRef.current
    const start = responseStartRef.current
    if (!viewport || !start || !latestAssistant) return
    const previous = scrollStateRef.current
    const conversationChanged = previous?.conversationId !== activeConversation?.id
    const newMessage = previous?.messageId !== latestAssistant.id
    if (!conversationChanged && !newMessage) return
    if (conversationChanged || latestAssistant.isGenerating) readerScrolledRef.current = false
    scrollStateRef.current = { conversationId: activeConversation?.id, messageId: latestAssistant.id }
    if (readerScrolledRef.current) return
    // Scroll only this pane, and align the start of a reply rather than its end.
    viewport.scrollTop += start.getBoundingClientRect().top - viewport.getBoundingClientRect().top - 12
    lastScrollTopRef.current = viewport.scrollTop
  }, [activeConversation?.id, isThreadLoading, latestAssistant])

  const handleThreadScroll = () => {
    const top = threadRef.current?.scrollTop || 0
    if (Math.abs(top - lastScrollTopRef.current) > 1) readerScrolledRef.current = true
    lastScrollTopRef.current = top
  }

  const handleThreadClick = useCallback((event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return
    }
    const anchor = event.target.closest('a')
    if (!anchor) return
    if (anchor.target && anchor.target !== '_self') return
    const href = anchor.getAttribute('href')
    if (!href) return

    if (href.startsWith('/') && !href.startsWith('//')) {
      event.preventDefault()
      navigate(href)
    }
  }, [navigate])

  const handleDragEnter = (e) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current += 1
    if (!e.dataTransfer || (e.dataTransfer.items && e.dataTransfer.items.length > 0) || (e.dataTransfer.types && e.dataTransfer.types.length > 0)) {
      setIsDraggingOver(true)
    }
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current -= 1
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0
      setIsDraggingOver(false)
    }
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.stopPropagation()
    e.dataTransfer.dropEffect = 'copy'
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current = 0
    setIsDraggingOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file && onFileSelect) {
      onFileSelect(file)
    }
  }

  return (
    <section
      className="relative flex h-full min-h-0 min-w-0 flex-1 flex-col bg-white dark:bg-slate-950"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* Drag and Drop Overlay */}
      {isDraggingOver && (
        <div className="absolute inset-0 z-50 flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-brand-primary bg-brand-primary/10 backdrop-blur-[2px] pointer-events-none m-2">
          <div className="rounded-full bg-white p-3 shadow-md text-brand-primary dark:bg-slate-900">
            <Paperclip className="h-6 w-6" />
          </div>
          <p className="text-sm font-semibold text-brand-primary">
            Drop file to attach to conversation
          </p>
          <p className="text-xs text-brand-text-muted">
            PDF, Word, Excel, PowerPoint, images up to 25MB
          </p>
        </div>
      )}

      {/* Header */}
      <header className="flex shrink-0 items-center justify-between border-b border-brand-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          {/* Panel toggles shown to the left of the title in page mode */}
          {canToggleWorkspacePanels && !isHistoryPanelVisible && (
            <button
              type="button"
              onClick={onToggleHistoryPanel}
              className="rounded-md p-1.5 text-brand-text-muted hover:bg-brand-surface hover:text-brand-text focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
              aria-label="Show history"
              title="Show history"
            >
              <PanelLeftOpen className="h-4 w-4" />
            </button>
          )}
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-brand-text">
              {activeConversation?.title || branding.assistant_name}
            </p>
            <p className="truncate text-[11px] text-brand-text-muted">
              {isSending ? 'Preparing a response...' : 'Actions marked for confirmation wait for your approval'}
            </p>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-0.5">
          {canToggleWorkspacePanels && isHistoryPanelVisible && (
            <button
              type="button"
              onClick={onToggleHistoryPanel}
              className="rounded-md p-1.5 text-brand-text-muted hover:bg-brand-surface hover:text-brand-text focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
              aria-label="Hide history"
              title="Hide history"
              aria-pressed={isHistoryPanelVisible}
            >
              <PanelLeftClose className="h-4 w-4" />
            </button>
          )}
          {canToggleWorkspacePanels && (
            <button
              type="button"
              onClick={onToggleToolsPanel}
              className="rounded-md p-1.5 text-brand-text-muted hover:bg-brand-surface hover:text-brand-text focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
              aria-label={isToolsPanelVisible ? 'Hide actions' : 'Show actions'}
              title={isToolsPanelVisible ? 'Hide actions' : 'Show actions'}
              aria-pressed={isToolsPanelVisible}
            >
              {isToolsPanelVisible ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
            </button>
          )}
          <button
            type="button"
            onClick={onNew}
            className="rounded-md p-1.5 text-brand-text-muted hover:bg-brand-surface hover:text-brand-text"
            aria-label="New conversation"
            title="New conversation"
          >
            <MessageSquarePlus className="h-4 w-4" />
          </button>
          {mode === 'drawer' && (
            <button
              type="button"
              onClick={onExpand}
              className="rounded-md p-1.5 text-brand-text-muted hover:bg-brand-surface hover:text-brand-text"
              aria-label="Expand workspace"
              title="Expand"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          )}
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1.5 text-brand-text-muted hover:bg-brand-surface hover:text-brand-text"
              aria-label={`Close ${branding.assistant_name}`}
              title="Close"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </header>

      {/* Thread */}
      <div ref={threadRef} role="region" aria-label="Assistant conversation" className="min-h-0 flex-1 overflow-y-auto px-4 py-5" style={{ overflowAnchor: 'none' }} onClick={handleThreadClick} onScroll={handleThreadScroll}>
        {isThreadLoading ? (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-brand-text-muted">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading conversation...
          </div>
        ) : messages.length === 0 ? (
          <EmptyThread mode={mode} />
        ) : (
          <div className={`mx-auto space-y-4 ${isExpanded ? 'max-w-4xl' : ''}`}>
            {messages.map((message) => (
              <div key={message.id} ref={message.id === latestAssistant?.id ? responseStartRef : undefined} data-message-id={message.id}>
                <MessageBubble
                  message={message}
                  onConfirm={onConfirm}
                  onCancel={onCancel}
                  busyToolId={busyToolId}
                  isExpanded={isExpanded}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Archived banner */}
      {isArchived && (
        <div className="mx-4 mb-3 flex items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
          <span className="text-xs font-medium">This conversation is archived.</span>
          <button
            type="button"
            onClick={onRestore}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold hover:bg-amber-100 dark:hover:bg-amber-900/40"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Restore
          </button>
        </div>
      )}

      {error && (
        <InlineAlert type="error" className="mx-4 mb-3" onDismiss={onErrorDismiss}>
          {error}
        </InlineAlert>
      )}

      {/* Composer */}
      <form
        onSubmit={onSend}
        className="shrink-0 border-t border-brand-border bg-white px-4 py-3 dark:bg-slate-950"
      >
        {/* Staged attachment / uploading preview */}
        {isUploadingAttachment && (
          <div className="mx-auto mb-2 flex max-w-4xl items-center gap-2 rounded-lg border border-brand-border bg-brand-surface px-3 py-1.5 text-xs text-brand-text-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-brand-primary" />
            <span>Uploading attachment...</span>
          </div>
        )}
        {attachment && !isUploadingAttachment && (
          <div className="mx-auto mb-2 flex max-w-4xl items-center justify-between gap-2 rounded-lg border border-brand-border bg-brand-surface px-3 py-1.5 text-xs">
            <div className="flex min-w-0 items-center gap-2 text-brand-text">
              <FileText className="h-4 w-4 shrink-0 text-brand-primary" />
              <span className="truncate font-medium">{attachment.filename}</span>
              <span className="text-[11px] text-brand-text-muted">({formatBytes(attachment.sizeBytes)})</span>
            </div>
            <button
              type="button"
              onClick={onRemoveAttachment}
              className="rounded p-1 text-brand-text-muted hover:bg-brand-border/50 hover:text-brand-text"
              title="Remove attachment"
              aria-label="Remove attachment"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        <div className="mx-auto flex max-w-4xl items-center gap-2">
          {/* File picker input */}
          <input
            ref={fileInputRef}
            type="file"
            accept={DOCUMENT_UPLOAD_ACCEPT}
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) {
                onFileSelect?.(file)
              }
              event.target.value = ''
            }}
          />

          {/* Attach button */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isArchived || isSending || isUploadingAttachment}
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-brand-border bg-brand-surface text-brand-text-muted hover:bg-brand-surface/80 hover:text-brand-text focus:outline-none focus:ring-2 focus:ring-brand-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
            title="Attach documentary evidence"
            aria-label="Attach file"
          >
            {isUploadingAttachment ? (
              <Loader2 className="h-4 w-4 animate-spin text-brand-primary" />
            ) : (
              <Paperclip className="h-4 w-4" />
            )}
          </button>

          <textarea
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            rows={1}
            disabled={isArchived || isSending}
            className="min-h-10 max-h-32 flex-1 resize-none rounded-lg border border-brand-border bg-brand-surface px-3 py-2.5 text-sm text-brand-text outline-none transition-colors placeholder:text-brand-text-muted focus:border-brand-primary focus:bg-white focus:ring-2 focus:ring-brand-primary/10 disabled:cursor-not-allowed disabled:opacity-50 dark:focus:bg-slate-900"
            placeholder={isArchived ? 'Restore this conversation to continue.' : 'Ask about projects, deadlines, handoff, notices, or attach evidence...'}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                onSend(event)
              }
            }}
          />
          <Button 
            type="submit" 
            disabled={isSending || isArchived || isUploadingAttachment || (!draft.trim() && !attachment)}
            className="h-10 min-h-10 px-4 py-2"
          >
            {isSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {isSending ? 'Working' : 'Send'}
          </Button>
        </div>
        <p className="mx-auto mt-1.5 max-w-4xl text-[10px] text-brand-text-muted">
          Enter to send; Shift+Enter for new line; drag and drop or click paperclip to attach files
        </p>
      </form>
    </section>
  )
}

export function AiAssistantWorkspace({
  mode = 'drawer',
  initialConversationId = null,
  onClose,
  onExpand,
  onActiveConversationChange,
}) {
  const { branding } = useBranding()
  const [conversations, setConversations] = useState([])
  const [tools, setTools] = useState([])
  const [capabilities, setCapabilities] = useState(null)
  const [activeConversation, setActiveConversation] = useState(null)
  const [activeConversationId, setActiveConversationId] = useState(initialConversationId)
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [attachment, setAttachment] = useState(null)
  const [isUploadingAttachment, setIsUploadingAttachment] = useState(false)
  const [search, setSearch] = useState('')
  const [isHistoryPanelVisible, setIsHistoryPanelVisible] = useState(() => (
    readBooleanPreference(HISTORY_PANEL_VISIBLE_KEY, true)
  ))
  const [isToolsPanelVisible, setIsToolsPanelVisible] = useState(() => (
    readBooleanPreference(TOOLS_PANEL_VISIBLE_KEY, true)
  ))
  const [includeArchived, setIncludeArchived] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [toolsLoading, setToolsLoading] = useState(false)
  const [threadLoading, setThreadLoading] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [busyToolId, setBusyToolId] = useState(null)
  const [error, setError] = useState('')
  const activeIdRef = useRef(initialConversationId)
  const selectionVersionRef = useRef(0)

  const updateHistoryPanelVisibility = useCallback((nextValue) => {
    setIsHistoryPanelVisible(nextValue)
    writeBooleanPreference(HISTORY_PANEL_VISIBLE_KEY, nextValue)
  }, [])

  const updateToolsPanelVisibility = useCallback((nextValue) => {
    setIsToolsPanelVisible(nextValue)
    writeBooleanPreference(TOOLS_PANEL_VISIBLE_KEY, nextValue)
  }, [])

  const selectConversation = useCallback(async (conversationId) => {
    if (!conversationId) return
    const selectionVersion = ++selectionVersionRef.current
    const previousId = activeIdRef.current
    activeIdRef.current = conversationId
    setThreadLoading(true)
    setError('')
    setAttachment(null)
    setDraft('')
    try {
      const response = await aiApi.getConversation(conversationId)
      if (selectionVersion !== selectionVersionRef.current) return
      const conversation = response.data
      setActiveConversation(conversation)
      setActiveConversationId(conversation.id)
      activeIdRef.current = conversation.id
      setMessages(normalizeMessages(conversation.messages || []))
      try {
        localStorage.setItem(LAST_CONVERSATION_KEY, String(conversation.id))
      } catch {
        // Ignore storage errors in restricted test environments
      }
      onActiveConversationChange?.(conversation.id)
    } catch (err) {
      if (selectionVersion !== selectionVersionRef.current) return
      activeIdRef.current = previousId
      setError(err.response?.data?.message || 'Unable to load the assistant conversation.')
    } finally {
      if (selectionVersion === selectionVersionRef.current) setThreadLoading(false)
    }
  }, [onActiveConversationChange])

  const clearActiveConversation = useCallback(() => {
    ++selectionVersionRef.current
    setActiveConversation(null)
    setActiveConversationId(null)
    activeIdRef.current = null
    setMessages([])
    setAttachment(null)
    setDraft('')
    try {
      localStorage.removeItem(LAST_CONVERSATION_KEY)
    } catch {
      // Ignore storage errors
    }
    onActiveConversationChange?.(null)
  }, [onActiveConversationChange])

  const refreshConversations = useCallback(async () => {
    const response = await aiApi.listConversations({ include_archived: includeArchived })
    setConversations(response.data || [])
    return response.data || []
  }, [includeArchived])

  useEffect(() => {
    let ignore = false

    async function loadInitialState() {
      setHistoryLoading(true)
      setError('')
      try {
        const [conversationResponse, toolResponse] = await Promise.all([
          aiApi.listConversations({ include_archived: includeArchived }),
          aiApi.listTools(),
        ])
        if (ignore) return

        const items = conversationResponse.data || []
        setConversations(items)
        setTools(toolResponse.data || [])
        setCapabilities(toolResponse.meta?.capabilities || null)

        const requestedId = initialConversationId
          || activeIdRef.current
          || localStorage.getItem(LAST_CONVERSATION_KEY)
        const selected = requestedId
          ? items.find((item) => String(item.id) === String(requestedId))
          : items[0]

        if (selected) {
          await selectConversation(selected.id)
        } else {
          clearActiveConversation()
        }
      } catch (err) {
        if (!ignore) {
          setError(err.response?.data?.message || 'Unable to load the assistant workspace.')
        }
      } finally {
        if (!ignore) {
          setHistoryLoading(false)
          setToolsLoading(false)
        }
      }
    }

    setToolsLoading(true)
    loadInitialState()

    return () => { ignore = true }
  }, [clearActiveConversation, includeArchived, initialConversationId, selectConversation])

  const createAndSelectConversation = async ({ preserveMessages = false } = {}) => {
    const selectionVersion = ++selectionVersionRef.current
    setError('')
    setAttachment(null)
    const response = await aiApi.createConversation({ title: `${branding.assistant_name} Conversation` })
    const conversation = response.data
    setConversations((current) => [conversation, ...current.filter((item) => item.id !== conversation.id)])
    if (selectionVersion !== selectionVersionRef.current) return conversation.id
    setActiveConversation(conversation)
    setActiveConversationId(conversation.id)
    activeIdRef.current = conversation.id
    if (!preserveMessages) {
      setMessages(normalizeMessages(conversation.messages || []))
    }
    try { localStorage.setItem(LAST_CONVERSATION_KEY, String(conversation.id)) } catch { /* Storage is optional. */ }
    onActiveConversationChange?.(conversation.id)
    return conversation.id
  }

  const handleFileSelect = async (file) => {
    if (!file) return
    const ext = (file.name || '').split('.').pop()?.toLowerCase()
    if (!ext || !ALLOWED_UPLOAD_EXTENSIONS.has(ext)) {
      setError(`Unsupported file type for documentary intake. Allowed extensions: ${Array.from(ALLOWED_UPLOAD_EXTENSIONS).join(', ')}.`)
      return
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setError(`Documentary intake files must be ${MAX_UPLOAD_BYTES / (1024 * 1024)} MB or smaller.`)
      return
    }

    setError('')
    setIsUploadingAttachment(true)
    let conversationId = activeConversationId
    try {
      conversationId = conversationId || await createAndSelectConversation({ preserveMessages: true })
      const response = await aiApi.uploadAttachment(conversationId, file)
      if (String(activeIdRef.current) !== String(conversationId)) return
      setAttachment({
        file,
        storedObjectId: response.data.attachment_stored_object_id,
        filename: response.data.attachment_filename || file.name,
        sizeBytes: file.size,
      })
    } catch (err) {
      if (String(activeIdRef.current) !== String(conversationId)) return
      setError(err.response?.data?.message || 'Failed to upload documentary evidence file.')
      setAttachment(null)
    } finally {
      setIsUploadingAttachment(false)
    }
  }

  const handleRemoveAttachment = () => {
    setAttachment(null)
  }

  const handleSend = async (event) => {
    event?.preventDefault()
    const content = draft.trim()
    if ((!content && !attachment) || isSending || isUploadingAttachment || threadLoading) return

    const effectiveContent = content || `Uploaded attachment: ${attachment.filename}`
    const now = new Date().toISOString()
    const optimisticUserId = makeTemporaryId('user')
    const thinkingId = makeTemporaryId('assistant')
    const optimisticUserMessage = {
      id: optimisticUserId,
      role: 'user',
      content: effectiveContent,
      created_at: now,
      display_payload: {},
      attachment_filename: attachment?.filename || null,
      attachment_stored_object_id: attachment?.storedObjectId || null,
    }
    const thinkingMessage = {
      id: thinkingId,
      role: 'assistant',
      content: '',
      created_at: now,
      display_payload: {},
      isGenerating: true,
    }

    const attachmentIdToSend = attachment?.storedObjectId || null
    const stagedAttachment = attachment

    setError('')
    setIsSending(true)
    setDraft('')
    setAttachment(null)
    setMessages((current) => [...current, optimisticUserMessage, thinkingMessage])
    let conversationId = activeConversationId
    try {
      conversationId = conversationId || await createAndSelectConversation({ preserveMessages: true })
      const response = await aiApi.sendMessage(conversationId, effectiveContent, attachmentIdToSend)
      if (String(activeIdRef.current) !== String(conversationId)) {
        await refreshConversations().catch(() => {})
        return
      }
      setMessages((current) => {
        const withoutOptimistic = current.filter((message) => (
          message.id !== optimisticUserId && message.id !== thinkingId
        ))
        return [
          ...withoutOptimistic,
          response.data.user_message,
          normalizeMessage(response.data.assistant_message),
        ].filter(Boolean)
      })
      setActiveConversation(response.data.conversation)
      setActiveConversationId(response.data.conversation.id)
      activeIdRef.current = response.data.conversation.id
      await refreshConversations().catch(() => {})
      const hadPendingAction = messages.some((message) => (
        message.display_payload?.tool_calls || message.tool_calls || []
      ).some((call) => call.status === 'pending_confirmation'))
      if (hadPendingAction) {
        // A correction or conversational cancellation can supersede an older
        // card. Merge authoritative saved messages without replacing new local
        // messages or updating a different conversation after navigation.
        const refreshed = await aiApi.getConversation(conversationId).catch(() => null)
        if (String(activeIdRef.current) === String(conversationId)
          && Array.isArray(refreshed?.data?.messages)) {
          const saved = new Map(refreshed.data.messages.map((message) => [message.id, message]))
          setMessages((current) => current.map((message) => (
            saved.has(message.id) ? normalizeMessage(saved.get(message.id)) : message
          )))
        }
      }
    } catch (err) {
      if (String(activeIdRef.current) !== String(conversationId)) return
      setError(err.response?.data?.message || `${branding.assistant_name} could not process the message.`)
      setDraft(content)
      setAttachment(stagedAttachment)
      setMessages((current) => current
        .filter((message) => message.id !== thinkingId)
        .map((message) => (
          message.id === optimisticUserId
            ? { ...message, deliveryStatus: 'failed' }
            : message
        )))
    } finally {
      setIsSending(false)
    }
  }

  const updateToolCall = (toolCall) => {
    setMessages((current) => current.map((message) => {
      const toolCalls = message.display_payload?.tool_calls
      if (!toolCalls?.some((item) => item.id === toolCall.id)) return message
      return {
        ...message,
        display_payload: {
          ...(message.display_payload || {}),
          tool_calls: toolCalls.map((item) => (item.id === toolCall.id ? toolCall : item)),
        },
      }
    }))
  }

  const handleConfirm = async (toolCallId) => {
    const conversationId = activeIdRef.current
    setBusyToolId(toolCallId)
    setError('')
    try {
      const response = await aiApi.confirmToolCall(toolCallId)
      if (activeIdRef.current === conversationId) updateToolCall(response.data)
      await refreshConversations().catch(() => {})
    } catch (err) {
      if (activeIdRef.current === conversationId) setError(err.response?.data?.message || 'Unable to confirm the assistant action.')
    } finally {
      setBusyToolId(null)
    }
  }

  const handleCancel = async (toolCallId) => {
    const conversationId = activeIdRef.current
    setBusyToolId(toolCallId)
    setError('')
    try {
      const response = await aiApi.cancelToolCall(toolCallId)
      if (activeIdRef.current === conversationId) updateToolCall(response.data)
      await refreshConversations().catch(() => {})
    } catch (err) {
      if (activeIdRef.current === conversationId) setError(err.response?.data?.message || 'Unable to cancel the assistant action.')
    } finally {
      setBusyToolId(null)
    }
  }

  const handleSetConversationStatus = async (conversationId, status) => {
    setError('')
    try {
      const response = await aiApi.updateConversation(conversationId, { status })
      const updatedConversation = response.data
      const items = await refreshConversations()
      if (String(activeConversationId || '') === String(conversationId)) {
        if (status === 'archived' && !includeArchived) {
          const nextConversation = items.find((item) => item.id !== conversationId)
          if (nextConversation) {
            await selectConversation(nextConversation.id)
          } else {
            clearActiveConversation()
          }
        } else {
          setActiveConversation(updatedConversation)
          setMessages(normalizeMessages(updatedConversation.messages || messages))
        }
      }
    } catch (err) {
      setError(err.response?.data?.message || 'Unable to update the assistant conversation.')
    }
  }

  const handleRestoreActive = () => {
    if (activeConversationId) {
      handleSetConversationStatus(activeConversationId, 'active')
    }
  }

  if (mode === 'page') {
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-brand-border bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950 lg:flex-row">
        {isHistoryPanelVisible && (
          <ConversationList
            conversations={conversations}
            activeConversationId={activeConversationId}
            isLoading={historyLoading}
            search={search}
            onSearch={setSearch}
            includeArchived={includeArchived}
            onToggleArchived={() => setIncludeArchived((current) => !current)}
            onSelect={selectConversation}
            onNew={createAndSelectConversation}
            onSetStatus={handleSetConversationStatus}
            onClose={() => updateHistoryPanelVisibility(false)}
          />
        )}
        <ChatPanel
          mode="page"
          activeConversation={activeConversation}
          messages={messages}
          isThreadLoading={threadLoading}
          draft={draft}
          onDraftChange={setDraft}
          onSend={handleSend}
          isSending={isSending}
          attachment={attachment}
          isUploadingAttachment={isUploadingAttachment}
          onFileSelect={handleFileSelect}
          onRemoveAttachment={handleRemoveAttachment}
          error={error}
          onErrorDismiss={() => setError('')}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
          busyToolId={busyToolId}
          onNew={createAndSelectConversation}
          onRestore={handleRestoreActive}
          isHistoryPanelVisible={isHistoryPanelVisible}
          isToolsPanelVisible={isToolsPanelVisible}
          onToggleHistoryPanel={() => updateHistoryPanelVisibility(!isHistoryPanelVisible)}
          onToggleToolsPanel={() => updateToolsPanelVisibility(!isToolsPanelVisible)}
        />
        {isToolsPanelVisible && (
          <ToolCatalog
            tools={tools}
            capabilities={capabilities}
            isLoading={toolsLoading}
            onClose={() => updateToolsPanelVisibility(false)}
          />
        )}
      </div>
    )
  }

  return (
    <ChatPanel
      mode="drawer"
      activeConversation={activeConversation}
      messages={messages}
      isThreadLoading={threadLoading || historyLoading}
      draft={draft}
      onDraftChange={setDraft}
      onSend={handleSend}
      isSending={isSending}
      attachment={attachment}
      isUploadingAttachment={isUploadingAttachment}
      onFileSelect={handleFileSelect}
      onRemoveAttachment={handleRemoveAttachment}
      error={error}
      onErrorDismiss={() => setError('')}
      onConfirm={handleConfirm}
      onCancel={handleCancel}
      busyToolId={busyToolId}
      onNew={createAndSelectConversation}
      onClose={onClose}
      onExpand={() => onExpand?.(activeConversationId)}
      onRestore={handleRestoreActive}
    />
  )
}

export function AiAssistantDrawer() {
  const navigate = useNavigate()
  const { branding } = useBranding()
  const [isOpen, setIsOpen] = useState(false)
  const [activeConversationId, setActiveConversationId] = useState(null)

  const handleExpand = (conversationId) => {
    setIsOpen(false)
    const targetId = conversationId || activeConversationId
    navigate(targetId ? `${ROUTES.AI_ASSIST}?conversation=${targetId}` : ROUTES.AI_ASSIST)
  }

  return (
    <>
      {/* FAB */}
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="fixed bottom-5 right-5 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-brand-primary text-white shadow-lg transition hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-brand-primary/40 dark:text-slate-950"
        aria-label={`Open ${branding.assistant_name}`}
      >
        <MessageCircle className="h-5 w-5" />
      </button>

      {/* Drawer overlay */}
      <Drawer isOpen={isOpen} onClose={() => setIsOpen(false)}>
        <AiAssistantWorkspace
          mode="drawer"
          onClose={() => setIsOpen(false)}
          onExpand={handleExpand}
          onActiveConversationChange={setActiveConversationId}
        />
      </Drawer>
    </>
  )
}
