import { Fragment, useMemo, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Building2,
  ChevronDown,
  ChevronUp,
  Eye,
  Layers,
  MapPin,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-PH')
}

function formatPercent(value) {
  if (value === 'Not rated') return 'Not rated'
  if (value === null || value === undefined) return 'Not reported'
  return `${Number(value || 0).toLocaleString('en-PH', { maximumFractionDigits: 1 })}%`
}

const DOCUMENT_SEGMENTS = [
  { key: 'compliant', label: 'Compliant', color: 'bg-emerald-500' },
  { key: 'under_review', label: 'Under Review', color: 'bg-blue-500' },
  { key: 'non_compliant', label: 'Non-Compliant', color: 'bg-rose-500' },
  { key: 'pending', label: 'Pending', color: 'bg-amber-500' },
  { key: 'waived', label: 'Waived', color: 'bg-slate-400' },
  { key: 'not_applicable', label: 'Not Applicable', color: 'bg-slate-500' },
]

export default function CompareAnalyticsCard({
  programData = [],
  clusterData = [],
  lguData = [],
  selectedProgram = null,
  selectedCluster = null,
  selectedLgu = null,
  selectedComplianceStatus = null,
  onProgramClick,
  onClusterClick,
  onLguClick,
  onSegmentClick,
}) {
  const [currentView, setCurrentView] = useState('lgu') // Default: 'lgu'
  const [sortField, setSortField] = useState('open_docs') // Default: 'open_docs'
  const [sortDirection, setSortDirection] = useState('desc') // Default: descending
  const [showAll, setShowAll] = useState(false)
  const [expandedRowId, setExpandedRowId] = useState(null)

  // Normalize row items depending on view
  const rawRows = useMemo(() => {
    if (currentView === 'cluster') {
      return clusterData.map((c) => {
        const compliant = c.compliant_document_count ?? c.compliant_count ?? c.compliant ?? 0
        const underReview = c.under_review_document_count ?? c.under_review_count ?? c.under_review ?? 0
        const nonCompliant = c.non_compliant_document_count ?? c.non_compliant_count ?? c.non_compliant ?? 0
        const pending = c.pending_document_count ?? c.pending_count ?? c.pending ?? 0
        const waived = c.waived_document_count ?? c.waived_count ?? c.waived ?? 0
        const notApplicable = c.not_applicable_document_count ?? c.not_applicable_count ?? c.not_applicable ?? 0
        const totalDocs = c.total_document_count ?? c.total_requirements ?? c.total ?? (compliant + underReview + nonCompliant + pending + waived + notApplicable)
        const applicableDocs = c.applicable_document_count ?? c.applicable_count ?? c.applicable ?? (totalDocs - notApplicable)
        const isNotRated = applicableDocs === 0
        const complianceRate = isNotRated
          ? 'Not rated'
          : (c.document_compliance_rate ?? c.compliance_rate ?? (applicableDocs > 0 ? (compliant / applicableDocs) * 100 : 'Not rated'))
        const openDocs = c.open_document_count ?? c.backlog_count ?? (underReview + nonCompliant + pending)

        return {
          ...c,
          id: c.cluster_id ?? c.cluster_name,
          name: c.cluster_name || 'Unclustered',
          subtext: null,
          average_progress: c.average_progress,
          compliant,
          under_review: underReview,
          non_compliant: nonCompliant,
          pending,
          waived,
          not_applicable: notApplicable,
          applicable_docs: applicableDocs,
          total_docs: totalDocs,
          compliance_rate: complianceRate,
          open_docs: openDocs,
          risk_count: c.risk_project_count ?? c.high_risk_project_count ?? c.risk_count ?? 0,
        }
      })
    }
    if (currentView === 'lgu') {
      return lguData.map((l) => {
        const compliant = l.compliant_document_count ?? l.compliant_count ?? l.compliant ?? 0
        const underReview = l.under_review_document_count ?? l.under_review_count ?? l.under_review ?? 0
        const nonCompliant = l.non_compliant_document_count ?? l.non_compliant_count ?? l.non_compliant ?? 0
        const pending = l.pending_document_count ?? l.pending_count ?? l.pending ?? 0
        const waived = l.waived_document_count ?? l.waived_count ?? l.waived ?? 0
        const notApplicable = l.not_applicable_document_count ?? l.not_applicable_count ?? l.not_applicable ?? 0
        const totalDocs = l.total_document_count ?? l.total_requirements ?? l.total ?? (compliant + underReview + nonCompliant + pending + waived + notApplicable)
        const applicableDocs = l.applicable_document_count ?? l.applicable_count ?? l.applicable ?? (totalDocs - notApplicable)
        const isNotRated = applicableDocs === 0
        const complianceRate = isNotRated
          ? 'Not rated'
          : (l.document_compliance_rate ?? l.compliance_rate ?? (applicableDocs > 0 ? (compliant / applicableDocs) * 100 : 'Not rated'))
        const openDocs = l.open_document_count ?? l.backlog_count ?? (underReview + nonCompliant + pending)

        return {
          ...l,
          id: l.lgu_id ?? l.lgu_name,
          name: l.lgu_name || 'Unassigned LGU',
          subtext: l.cluster_name || l.municipality || null,
          average_progress: l.average_progress,
          compliant,
          under_review: underReview,
          non_compliant: nonCompliant,
          pending,
          waived,
          not_applicable: notApplicable,
          applicable_docs: applicableDocs,
          total_docs: totalDocs,
          compliance_rate: complianceRate,
          open_docs: openDocs,
          risk_count: l.risk_project_count ?? l.high_risk_project_count ?? l.risk_count ?? 0,
        }
      })
    }
    // Default: program
    return programData.map((p) => {
      const compliant = p.compliant_document_count ?? p.compliant_count ?? p.compliant ?? 0
      const underReview = p.under_review_document_count ?? p.under_review_count ?? p.under_review ?? 0
      const nonCompliant = p.non_compliant_document_count ?? p.non_compliant_count ?? p.non_compliant ?? 0
      const pending = p.pending_document_count ?? p.pending_count ?? p.pending ?? 0
      const waived = p.waived_document_count ?? p.waived_count ?? p.waived ?? 0
      const notApplicable = p.not_applicable_document_count ?? p.not_applicable_count ?? p.not_applicable ?? 0
      const totalDocs = p.total_document_count ?? p.total_requirements ?? p.total ?? (compliant + underReview + nonCompliant + pending + waived + notApplicable)
      const applicableDocs = p.applicable_document_count ?? p.applicable_count ?? p.applicable ?? (totalDocs - notApplicable)
      const isNotRated = applicableDocs === 0
      const complianceRate = isNotRated
        ? 'Not rated'
        : (p.document_compliance_rate ?? p.compliance_rate ?? (applicableDocs > 0 ? (compliant / applicableDocs) * 100 : 'Not rated'))
      const openDocs = p.open_document_count ?? p.backlog_count ?? (underReview + nonCompliant + pending)

      return {
        ...p,
        id: p.program_id ?? p.program_name,
        name: p.program_name || 'Unassigned Program',
        subtext: p.fiscal_year ? `FY ${p.fiscal_year}${p.program_code ? ` · ${p.program_code}` : ''}` : p.program_code || null,
        average_progress: p.average_progress,
        compliant,
        under_review: underReview,
        non_compliant: nonCompliant,
        pending,
        waived,
        not_applicable: notApplicable,
        applicable_docs: applicableDocs,
        total_docs: totalDocs,
        compliance_rate: complianceRate,
        open_docs: openDocs,
        risk_count: p.risk_project_count ?? p.high_risk_project_count ?? p.risk_count ?? 0,
      }
    })
  }, [currentView, programData, clusterData, lguData])

  // Sorting
  const sortedRows = useMemo(() => {
    return [...rawRows].sort((a, b) => {
      let valA = a[sortField]
      let valB = b[sortField]

      if (sortField === 'name') {
        valA = (a.name || '').toLowerCase()
        valB = (b.name || '').toLowerCase()
        const cmp = valA.localeCompare(valB)
        return sortDirection === 'asc' ? cmp : -cmp
      }

      if (sortField === 'compliance_rate') {
        const rateA = a.compliance_rate === 'Not rated' ? -1 : Number(a.compliance_rate || 0)
        const rateB = b.compliance_rate === 'Not rated' ? -1 : Number(b.compliance_rate || 0)
        if (rateA !== rateB) {
          return sortDirection === 'asc' ? rateA - rateB : rateB - rateA
        }
      } else {
        valA = Number(valA || 0)
        valB = Number(valB || 0)

        if (valA !== valB) {
          return sortDirection === 'asc' ? valA - valB : valB - valA
        }
      }

      // Tie breaker: always break ties alphabetically by name
      const nameA = (a.name || '').toLowerCase()
      const nameB = (b.name || '').toLowerCase()
      return nameA.localeCompare(nameB)
    })
  }, [rawRows, sortField, sortDirection])

  const visibleRows = showAll ? sortedRows : sortedRows.slice(0, 10)

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      // Default to ascending for name, descending for counts and metrics
      setSortDirection(field === 'name' ? 'asc' : 'desc')
    }
  }

  const renderSortIcon = (field) => {
    if (sortField !== field) {
      return <ArrowUpDown className="h-3 w-3 opacity-40 ml-1 inline" />
    }
    return sortDirection === 'asc' ? (
      <ArrowUp className="h-3 w-3 text-brand-primary ml-1 inline" />
    ) : (
      <ArrowDown className="h-3 w-3 text-brand-primary ml-1 inline" />
    )
  }

  const handleRowClick = (row, event) => {
    if (currentView === 'program') {
      if (onProgramClick) {
        onProgramClick(row, event)
      }
    } else if (currentView === 'cluster') {
      if (onClusterClick) {
        onClusterClick(row, event)
      }
    } else if (currentView === 'lgu') {
      if (onLguClick) {
        onLguClick(row, event)
      }
    }
  }

  const handleSegmentClick = (e, row, statusKey) => {
    e.stopPropagation()
    if (onSegmentClick) {
      onSegmentClick(row, statusKey, currentView)
    } else if (currentView === 'program' && onProgramClick) {
      onProgramClick(row, statusKey)
    }
  }

  const isRowSelected = (row) => {
    if (currentView === 'program') {
      return (
        selectedProgram &&
        (selectedProgram.id === row.program_id || selectedProgram.name === row.program_name || selectedProgram.name === row.name)
      )
    }
    if (currentView === 'cluster') {
      return (
        selectedCluster &&
        (selectedCluster.id === row.cluster_id || selectedCluster.name === row.cluster_name || selectedCluster.name === row.name)
      )
    }
    if (currentView === 'lgu') {
      return (
        selectedLgu &&
        (selectedLgu.id === row.lgu_id || selectedLgu.name === row.lgu_name || selectedLgu.name === row.name)
      )
    }
    return false
  }

  return (
    <div className="space-y-4">
      {/* ── TOP CONTROLS & SEGMENTED SWITCH ── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-brand-border/60 pb-3">
        {/* Segmented Control */}
        <div
          role="tablist"
          aria-label="Compare dimensions"
          className="inline-flex rounded-lg bg-slate-100 p-1 dark:bg-slate-800/80 shadow-inner"
        >
          <button
            type="button"
            role="tab"
            aria-selected={currentView === 'lgu'}
            onClick={() => {
              setCurrentView('lgu')
              setShowAll(false)
            }}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
              currentView === 'lgu'
                ? 'bg-white text-brand-primary shadow-xs dark:bg-slate-700 dark:text-white'
                : 'text-brand-text-muted hover:text-brand-text'
            }`}
          >
            <MapPin className="h-3.5 w-3.5" />
            <span>LGU</span>
            <span className="rounded-full bg-slate-200/80 px-1.5 py-0.2 text-[10px] text-slate-700 dark:bg-slate-600 dark:text-slate-200">
              {lguData.length}
            </span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={currentView === 'program'}
            onClick={() => {
              setCurrentView('program')
              setShowAll(false)
            }}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
              currentView === 'program'
                ? 'bg-white text-brand-primary shadow-xs dark:bg-slate-700 dark:text-white'
                : 'text-brand-text-muted hover:text-brand-text'
            }`}
          >
            <Building2 className="h-3.5 w-3.5" />
            <span>Program</span>
            <span className="rounded-full bg-slate-200/80 px-1.5 py-0.2 text-[10px] text-slate-700 dark:bg-slate-600 dark:text-slate-200">
              {programData.length}
            </span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={currentView === 'cluster'}
            onClick={() => {
              setCurrentView('cluster')
              setShowAll(false)
            }}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
              currentView === 'cluster'
                ? 'bg-white text-brand-primary shadow-xs dark:bg-slate-700 dark:text-white'
                : 'text-brand-text-muted hover:text-brand-text'
            }`}
          >
            <Layers className="h-3.5 w-3.5" />
            <span>Cluster</span>
            <span className="rounded-full bg-slate-200/80 px-1.5 py-0.2 text-[10px] text-slate-700 dark:bg-slate-600 dark:text-slate-200">
              {clusterData.length}
            </span>
          </button>
        </div>

        {/* Legend / Status Context indicator */}
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-brand-text-muted">
          <span className="font-medium text-brand-text">
            Compliance Status by {currentView === 'lgu' ? 'LGU' : currentView === 'cluster' ? 'Cluster' : 'Program'}
          </span>
          <div className="flex items-center gap-2">
            {DOCUMENT_SEGMENTS.map((s) => (
              <span key={s.key} className="inline-flex items-center gap-1">
                <span className={`h-2 w-2 rounded-full ${s.color}`} />
                <span>{s.label}</span>
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* ── DATA TABLE ── */}
      {sortedRows.length === 0 ? (
        <div className="py-8 text-center text-sm text-brand-text-muted">
          No comparison data available for this dimension.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-brand-border/60 shadow-xs">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-brand-border/80 bg-slate-50/70 text-[11px] font-semibold uppercase tracking-wider text-brand-text-muted dark:bg-slate-900/50">
                <th className="py-2.5 px-3 cursor-pointer select-none hover:text-brand-text" onClick={() => handleSort('name')}>
                  <span className="inline-flex items-center">
                    {currentView === 'program' ? 'Program' : currentView === 'cluster' ? 'Cluster' : 'LGU'}
                    {renderSortIcon('name')}
                  </span>
                </th>
                <th className="py-2.5 px-3 text-right cursor-pointer select-none hover:text-brand-text" onClick={() => handleSort('project_count')}>
                  <span className="inline-flex items-center justify-end w-full">
                    Projects
                    {renderSortIcon('project_count')}
                  </span>
                </th>
                <th className="py-2.5 px-3 text-right cursor-pointer select-none hover:text-brand-text" onClick={() => handleSort('applicable_docs')}>
                  <span className="inline-flex items-center justify-end w-full">
                    Applicable
                    {renderSortIcon('applicable_docs')}
                  </span>
                </th>
                <th className="py-2.5 px-3 text-right cursor-pointer select-none hover:text-brand-text" onClick={() => handleSort('compliant')}>
                  <span className="inline-flex items-center justify-end w-full">
                    Compliant
                    {renderSortIcon('compliant')}
                  </span>
                </th>
                <th className="py-2.5 px-3 text-right cursor-pointer select-none hover:text-brand-text" onClick={() => handleSort('open_docs')}>
                  <span className="inline-flex items-center justify-end w-full">
                    Open
                    {renderSortIcon('open_docs')}
                  </span>
                </th>
                <th className="py-2.5 px-3 text-right cursor-pointer select-none hover:text-brand-text" onClick={() => handleSort('compliance_rate')}>
                  <span className="inline-flex items-center justify-end w-full">
                    Fulfillment Rate
                    {renderSortIcon('compliance_rate')}
                  </span>
                </th>
                <th className="py-2.5 px-2 w-8 text-center" aria-label="Details"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-border/40">
              {visibleRows.map((row, idx) => {
                const isSelected = isRowSelected(row)
                const totalDocs = row.total_docs || 0
                const isExpanded = expandedRowId === row.id

                return (
                  <Fragment key={row.id || `${currentView}-${idx}`}>
                    <tr
                      tabIndex={0}
                      onClick={(event) => handleRowClick(row, event)}
                      onKeyDown={(event) => {
                        if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) {
                          event.preventDefault()
                          handleRowClick(row, event)
                        }
                      }}
                      className={`cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-brand-primary/50 focus:bg-brand-primary/5 hover:bg-slate-50/80 dark:hover:bg-slate-800/50 ${
                        isSelected
                          ? 'bg-brand-primary/10 font-semibold ring-1 ring-brand-primary/40'
                          : idx % 2 === 1
                          ? 'bg-slate-50/30 dark:bg-slate-900/20'
                          : ''
                      }`}
                    >
                      {/* Name & Subtext */}
                      <td className="py-2.5 px-3">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            handleRowClick(row, e)
                          }}
                          className="text-left font-semibold text-brand-text hover:text-brand-primary focus:outline-none focus:underline truncate max-w-[220px] block"
                          title={`View ${row.name} contributing projects`}
                        >
                          {row.name}
                        </button>
                        {row.subtext && (
                          <div className="text-[10px] text-brand-text-muted truncate max-w-[220px]">
                            {row.subtext}
                          </div>
                        )}
                      </td>

                      {/* Project Count */}
                      <td className="py-2.5 px-3 text-right font-medium text-brand-text font-mono">
                        {formatNumber(row.project_count)}
                      </td>

                      {/* Applicable Docs */}
                      <td className="py-2.5 px-3 text-right font-medium text-brand-text font-mono">
                        {formatNumber(row.applicable_docs)}
                      </td>

                      {/* Compliant Docs */}
                      <td className="py-2.5 px-3 text-right font-medium font-mono text-emerald-700 dark:text-emerald-400">
                        {formatNumber(row.compliant)}
                      </td>

                      {/* Open Docs */}
                      <td className="py-2.5 px-3 text-right font-medium font-mono">
                        <span className={row.open_docs > 0 ? 'text-amber-700 dark:text-amber-400 font-semibold' : 'text-brand-text-muted'}>
                          {formatNumber(row.open_docs)}
                        </span>
                      </td>

                      {/* Fulfillment Rate */}
                      <td className="py-2.5 px-3 text-right font-medium font-mono">
                        {row.compliance_rate === 'Not rated' ? (
                          <span className="text-brand-text-muted font-normal">Not rated</span>
                        ) : (
                          <span
                            className={
                              row.compliance_rate >= 80
                                ? 'text-emerald-700 dark:text-emerald-400 font-semibold'
                                : row.compliance_rate >= 50
                                ? 'text-amber-700 dark:text-amber-400 font-semibold'
                                : 'text-rose-700 dark:text-rose-400 font-semibold'
                            }
                          >
                            {formatPercent(row.compliance_rate)}
                          </span>
                        )}
                      </td>

                      {/* Expand/Collapse Toggle */}
                      <td
                        className="py-2.5 px-2 text-center w-8"
                        onClick={(e) => {
                          e.stopPropagation()
                          setExpandedRowId(isExpanded ? null : row.id)
                        }}
                      >
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            setExpandedRowId(isExpanded ? null : row.id)
                          }}
                          className="p-1 text-brand-text-muted hover:text-brand-text rounded transition-colors"
                          title={isExpanded ? 'Collapse details' : 'Expand details'}
                          aria-label={isExpanded ? 'Collapse details' : 'Expand details'}
                        >
                          {isExpanded ? (
                            <ChevronUp className="h-3.5 w-3.5" />
                          ) : (
                            <ChevronDown className="h-3.5 w-3.5" />
                          )}
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="bg-slate-50/70 dark:bg-slate-900/40">
                        <td colSpan={7} className="py-2 px-4 border-b border-brand-border/40">
                          <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
                            <div className="flex items-center gap-4 text-brand-text-muted font-mono text-[11px]">
                              <span>Waived: <strong className="text-brand-text">{row.waived || 0}</strong></span>
                              <span>Not Applicable: <strong className="text-brand-text">{row.not_applicable || 0}</strong></span>
                              <span>Total Tracked: <strong className="text-brand-text">{totalDocs}</strong></span>
                            </div>
                            {totalDocs > 0 && (
                              <div className="w-56">
                                <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700 flex shadow-inner">
                                  {DOCUMENT_SEGMENTS.map((seg) => {
                                    const count = row[seg.key] || 0
                                    if (!count) return null
                                    const pct = (count / totalDocs) * 100
                                    const isSegmentActive = selectedComplianceStatus === seg.key
                                    return (
                                      <button
                                        key={seg.key}
                                        type="button"
                                        title={`Filter by ${row.name} + ${seg.label}`}
                                        aria-label={`Filter by ${row.name} + ${seg.label}`}
                                        onClick={(e) => handleSegmentClick(e, row, seg.key)}
                                        className={`${seg.color} h-full transition-all hover:brightness-110 ${
                                          isSegmentActive ? 'ring-2 ring-white dark:ring-slate-900 z-10' : ''
                                        }`}
                                        style={{ width: `${pct}%` }}
                                      />
                                    )
                                  })}
                                </div>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── FOOTER ACTIONS & TOGGLE ── */}
      {sortedRows.length > 10 && (
        <div className="flex items-center justify-between pt-1">
          <span className="text-xs text-brand-text-muted">
            Showing {visibleRows.length} of {sortedRows.length} {currentView === 'program' ? 'programs' : currentView === 'cluster' ? 'clusters' : 'LGUs'}
          </span>
          <button
            type="button"
            onClick={() => setShowAll((prev) => !prev)}
            className="inline-flex items-center gap-1 text-xs font-semibold text-brand-primary hover:underline"
          >
            {showAll ? (
              <>
                <span>Show top 10</span>
                <ChevronUp className="h-3.5 w-3.5" />
              </>
            ) : (
              <>
                <span>Show all ({sortedRows.length})</span>
                <ChevronDown className="h-3.5 w-3.5" />
              </>
            )}
          </button>
        </div>
      )}
    </div>
  )
}
