import { useState, useMemo } from 'react'
import { Modal, Button } from '../../../components'
import {
  AlertOctagon,
  AlertTriangle,
  Calendar,
  Clock,
  ExternalLink,
  Filter,
  Info,
  MapPin,
  ShieldAlert,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { ROUTES } from '../../../config/routes'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatDate(dateStr) {
  if (!dateStr) return '—'
  try {
    return new Date(dateStr).toLocaleDateString('en-PH', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return dateStr
  }
}

const SEVERITY_CONFIG = {
  severe: {
    label: 'Severe Defect',
    tone: 'danger',
    badge: 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300 ring-1 ring-rose-200 dark:ring-rose-800',
    icon: AlertOctagon,
  },
  major: {
    label: 'Major Defect',
    tone: 'warning',
    badge: 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300 ring-1 ring-amber-200 dark:ring-amber-800',
    icon: AlertTriangle,
  },
  minor: {
    label: 'Minor Defect',
    tone: 'neutral',
    badge: 'bg-yellow-50 text-yellow-800 dark:bg-yellow-950/50 dark:text-yellow-300 ring-1 ring-yellow-200 dark:ring-yellow-800',
    icon: Info,
  },
  unclassified: {
    label: 'Unclassified',
    tone: 'neutral',
    badge: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    icon: Info,
  },
}

export default function QaarFindingDetailModal({
  findings = [],
  initialSeverity = null,
  open,
  onClose,
}) {
  const [severityFilter, setSeverityFilter] = useState(initialSeverity || 'all')
  const [prevSeverity, setPrevSeverity] = useState(initialSeverity)

  if (initialSeverity !== prevSeverity) {
    setPrevSeverity(initialSeverity)
    setSeverityFilter(initialSeverity || 'all')
  }

  const counts = useMemo(() => {
    const c = { all: findings.length, severe: 0, major: 0, minor: 0 }
    for (const f of findings) {
      const r = (f.risk_level || '').toLowerCase()
      if (r in c) {
        c[r] += 1
      }
    }
    return c
  }, [findings])

  const filteredFindings = useMemo(() => {
    if (severityFilter === 'all') return findings
    return findings.filter((f) => (f.risk_level || '').toLowerCase() === severityFilter)
  }, [findings, severityFilter])

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="QAAR Inspection Findings"
      description={`Detailed record of civil works quality assurance inspection findings (${formatNumber(findings.length)} total)`}
      size="xl"
      footer={(
        <div className="flex justify-end">
          <Button variant="outline" onClick={onClose}>Close</Button>
        </div>
      )}
    >
      <div className="space-y-4">
        {/* Severity Filter Pills */}
        <div className="flex flex-wrap items-center gap-2 border-b border-brand-border pb-3">
          <button
            type="button"
            onClick={() => setSeverityFilter('all')}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1 text-xs font-semibold transition-colors ${
              severityFilter === 'all'
                ? 'bg-brand-primary text-white shadow-xs dark:text-slate-950'
                : 'bg-slate-100 dark:bg-slate-800 text-brand-text hover:bg-slate-200 dark:hover:bg-slate-700'
            }`}
          >
            All Findings ({counts.all})
          </button>

          <button
            type="button"
            onClick={() => setSeverityFilter('severe')}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1 text-xs font-semibold transition-colors ${
              severityFilter === 'severe'
                ? 'bg-rose-600 text-white shadow-xs'
                : 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300 hover:bg-rose-100'
            }`}
          >
            <AlertOctagon className="h-3 w-3" />
            Severe ({counts.severe})
          </button>

          <button
            type="button"
            onClick={() => setSeverityFilter('major')}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1 text-xs font-semibold transition-colors ${
              severityFilter === 'major'
                ? 'bg-amber-600 text-white shadow-xs'
                : 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 hover:bg-amber-100'
            }`}
          >
            <AlertTriangle className="h-3 w-3" />
            Major ({counts.major})
          </button>

          <button
            type="button"
            onClick={() => setSeverityFilter('minor')}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1 text-xs font-semibold transition-colors ${
              severityFilter === 'minor'
                ? 'bg-yellow-600 text-white shadow-xs'
                : 'bg-yellow-50 text-yellow-800 dark:bg-yellow-950/40 dark:text-yellow-300 hover:bg-yellow-100'
            }`}
          >
            <Info className="h-3 w-3" />
            Minor ({counts.minor})
          </button>
        </div>

        {/* Findings List */}
        {filteredFindings.length === 0 ? (
          <div className="py-8 text-center text-sm text-brand-text-muted">
            No QAAR inspection findings match the selected severity filter.
          </div>
        ) : (
          <div className="max-h-[60vh] space-y-3 overflow-y-auto pr-1">
            {filteredFindings.map((finding) => {
              const rLevel = (finding.risk_level || 'unclassified').toLowerCase()
              const cfg = SEVERITY_CONFIG[rLevel] || SEVERITY_CONFIG.unclassified

              return (
                <div
                  key={finding.id}
                  className="rounded-xl border border-brand-border bg-brand-surface p-4 shadow-xs space-y-3"
                >
                  {/* Finding Header */}
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Link
                          to={ROUTES.projectDetail(finding.project_id)}
                          className="font-semibold text-brand-primary hover:underline flex items-center gap-1 text-sm"
                        >
                          {finding.project_name}
                          <ExternalLink className="h-3 w-3 inline" />
                        </Link>
                        <span className="text-xs text-brand-text-muted">·</span>
                        <span className="text-xs font-medium text-brand-text-muted flex items-center gap-1">
                          <MapPin className="h-3 w-3 inline opacity-70" />
                          {finding.lgu_name}
                        </span>
                      </div>
                      <div className="mt-0.5 flex items-center gap-2 text-xs text-brand-text-muted">
                        <span>Inspection: <strong>{formatDate(finding.inspection_date)}</strong></span>
                        <span>•</span>
                        <span>Status: <strong className="capitalize">{finding.inspection_status || 'Reviewed'}</strong></span>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold ${cfg.badge}`}>
                        {cfg.label}
                      </span>
                      {finding.defect_code && (
                        <span className="rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs font-mono text-brand-text">
                          {finding.defect_code}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Defect Description & Quality Issue */}
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 text-xs bg-slate-50/60 dark:bg-slate-900/40 rounded-lg p-3">
                    <div>
                      <span className="font-semibold text-brand-text block mb-0.5">Defect Description:</span>
                      <p className="text-brand-text-muted">{finding.defect_description || 'No description recorded.'}</p>
                    </div>
                    <div>
                      <span className="font-semibold text-brand-text block mb-0.5">Quality Issue:</span>
                      <p className="text-brand-text-muted">{finding.quality_issue || 'General workmanship deviation.'}</p>
                    </div>
                  </div>

                  {/* Recommendations & Action Plan */}
                  <div className="flex flex-wrap items-start justify-between gap-3 text-xs border-t border-brand-border/40 pt-2.5">
                    <div className="min-w-0 flex-1">
                      <span className="font-semibold text-brand-text">Recommendation: </span>
                      <span className="text-brand-text-muted">{finding.recommendation || 'Remediate per standard engineering specification.'}</span>
                    </div>
                    {finding.timeline && (
                      <div className="flex items-center gap-1 text-amber-700 dark:text-amber-300 font-medium shrink-0">
                        <Clock className="h-3 w-3" />
                        <span>Timeline: {finding.timeline}</span>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </Modal>
  )
}
