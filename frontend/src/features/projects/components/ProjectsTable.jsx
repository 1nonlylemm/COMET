import { Fragment, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../../../components/EmptyState'
import { ROUTES } from '../../../config/routes'
import { formatMachineLabel, formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'

export function ProjectsTable({ projects, programs, lgus, isLoading, emptyMessage }) {
  const [expandedProjectId, setExpandedProjectId] = useState(null)
  if (isLoading) {
    return <div className="data-table-panel p-10 text-center text-sm text-brand-text-muted" role="status">Loading projects…</div>
  }
  if (!projects.length) {
    return <div className="data-table-panel"><EmptyState title={emptyMessage} /></div>
  }

  return (
    <div className="data-table-panel">
      <div className="overflow-x-auto focus-visible:outline-2 focus-visible:outline-brand-primary focus-visible:-outline-offset-2" role="region" aria-label="Projects table, scroll horizontally on smaller screens" tabIndex={0}>
        <table className="w-full min-w-[920px] table-fixed text-left">
          <caption className="sr-only">Projects</caption>
          <colgroup>
            <col className="w-[33%]" /><col className="w-[17%]" /><col className="w-[16%]" />
            <col className="w-[15%]" /><col className="w-[10%]" /><col className="w-[9%]" />
          </colgroup>
          <thead className="data-table-header">
            <tr>
              {['Project', 'LGU', 'Program / FY', 'Status / phase', 'Physical progress', 'Actions'].map(label => (
                <th key={label} scope="col" className="border-b border-brand-border px-4 py-3 text-xs font-semibold text-brand-text-muted">{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {projects.map(project => {
              const program = programs.find(item => Number(item.id) === Number(project.program_id))
              const programName = project.program_name || program?.name
              const programCode = project.program_code || program?.code
              const lguName = project.lgu_name || lgus.find(item => Number(item.id) === Number(project.lgu_id))?.name
              const rawProgress = project.physical_completion_pct
              const progress = rawProgress === null || rawProgress === undefined || rawProgress === '' ? null : Number(rawProgress)
              const hasProgress = progress !== null && Number.isFinite(progress) && progress >= 0 && progress <= 100
              const expanded = expandedProjectId === project.id
              return (
                <Fragment key={project.id}>
                <tr className="data-table-row">
                  <td className="data-table-cell px-4 py-4">
                    <Link to={ROUTES.projectDetail(project.id)} className="block break-words font-semibold leading-5 text-brand-text hover:text-brand-primary hover:underline focus-visible:rounded focus-visible:outline-2 focus-visible:outline-brand-primary">
                      {project.project_name}
                    </Link>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-brand-text-muted">
                      <span>#{project.id}</span>
                      {project.source_project_code && <span className="break-all border-l border-brand-border pl-2 font-mono text-[11px]">{project.source_project_code}</span>}
                    </div>
                  </td>
                  <td className="data-table-cell break-words px-4 py-4 leading-5">{lguName || 'Not recorded'}</td>
                  <td className="data-table-cell px-4 py-4">
                      <button type="button" aria-label={`Program and cycle details for ${project.project_name}`} aria-expanded={expanded} aria-controls={`project-context-${project.id}`} onClick={() => setExpandedProjectId(expanded ? null : project.id)} className="flex min-h-6 items-start gap-1.5 rounded text-left font-medium focus-visible:outline-2 focus-visible:outline-brand-primary">
                        <span className="break-words">{programCode || programName || 'Not recorded'}</span>
                        <ChevronDown className={`mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-text-muted transition-transform ${expanded ? 'rotate-180' : ''}`} aria-hidden="true" />
                      </button>
                    <p className="mt-1 text-xs text-brand-text-muted">{project.fiscal_year ? `FY ${project.fiscal_year}` : 'FY not recorded'}</p>
                  </td>
                  <td className="data-table-cell px-4 py-4">
                    <span className={badgeClassForStatus(project.overall_status, 'neutral')}>{project.overall_status ? formatStatus(project.overall_status) : 'Not recorded'}</span>
                    <p className="mt-1.5 text-xs leading-4 text-brand-text-muted">{project.current_phase ? formatMachineLabel(project.current_phase) : 'Phase not recorded'}</p>
                  </td>
                  <td className="data-table-cell px-4 py-4">
                    {hasProgress ? (
                      <div>
                        <span className="text-sm font-semibold tabular-nums">{progress}%</span>
                        <div role="progressbar" aria-label={`Physical progress for ${project.project_name}`} aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100} className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                          <div className="h-full rounded-full bg-brand-primary" style={{ width: `${progress}%` }} />
                        </div>
                      </div>
                    ) : <span className="text-xs text-brand-text-muted">Not recorded</span>}
                  </td>
                  <td className="data-table-cell px-4 py-4">
                    <Link to={ROUTES.projectDetail(project.id)} aria-label={`Open project: ${project.project_name}`} className="inline-flex min-h-9 items-center gap-1 rounded text-sm font-medium text-brand-primary hover:underline focus-visible:outline-2 focus-visible:outline-brand-primary">
                      Open <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                    </Link>
                  </td>
                </tr>
                {expanded && (
                  <tr id={`project-context-${project.id}`} className="border-b border-brand-border bg-slate-50 dark:bg-slate-800/50">
                    <td colSpan={6} className="px-4 py-4">
                      <dl className="grid gap-4 text-sm sm:grid-cols-2">
                        <div><dt className="mb-1 text-xs font-medium text-brand-text-muted">Full program name</dt><dd className="break-words text-brand-text">{programName || programCode || 'Not recorded'}</dd></div>
                        <div><dt className="mb-1 text-xs font-medium text-brand-text-muted">Program cycle</dt><dd className="break-words text-brand-text">{project.program_cycle_name || 'Not assigned'}</dd></div>
                      </dl>
                    </td>
                  </tr>
                )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
