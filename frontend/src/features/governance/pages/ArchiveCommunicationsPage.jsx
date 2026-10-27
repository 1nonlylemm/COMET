import { useCallback, useEffect, useRef, useState } from 'react'
import { Archive, Download, FileClock, MessageSquareText, Search, Send, X } from 'lucide-react'
import { Button, Drawer, GlassPanel, InlineAlert, KpiCard, PageHeader } from '../../../components'
import { isInternalUser } from '../../../lib/auth'
import { fileTransferErrorMessage } from '../../../lib/fileTransfer'
import { useFiscalYear } from '../../../context/useFiscalYear'
import { formatDateTime, formatMachineLabel, formatStatus } from '../../../lib/formatters'
import { badgeClassForStatus } from '../../../lib/statusStyles'
import { CommunicationHistoryTable } from '../components/CommunicationHistoryTable'
import { DocumentArchiveTable } from '../components/DocumentArchiveTable'
import * as governanceApi from '../api/governanceApi'
import * as lguApi from '../../lgus/api/lguApi'
import * as programApi from '../../programs/api/programApi'
import * as projectApi from '../../projects/api/projectApi'

function formatBytes(value) {
  if (!value) return '—'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function pushBadge(status) {
  if (!status) return '—'
  return (
    <span className={badgeClassForStatus(status)}>
      {formatStatus(status)}
    </span>
  )
}

export default function ArchiveCommunicationsPage() {
  const { fiscalYearOptions, selectedFiscalYear } = useFiscalYear()
  const [archiveRecords, setArchiveRecords] = useState([])
  const [archivePage, setArchivePage] = useState(1)
  const [archiveMeta, setArchiveMeta] = useState({ page: 1, pages: 1, total: 0, per_page: 20 })
  const requestSequence = useRef(0)
  const [communications, setCommunications] = useState([])
  const [communicationPage, setCommunicationPage] = useState(1)
  const [communicationMeta, setCommunicationMeta] = useState({ page: 1, pages: 1, total: 0, per_page: 20 })
  const [selectedRecord, setSelectedRecord] = useState(null)
  const [recordDetail, setRecordDetail] = useState(null)
  const [activeTab, setActiveTab] = useState('submissions')
  const [lgus, setLgus] = useState([])
  const [programs, setPrograms] = useState([])
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')
  const [filters, setFilters] = useState({
    search: '',
    lgu_id: '',
    program_id: '',
    fiscal_year: '',
  })

  const loadPage = useCallback(async () => {
    const requestId = ++requestSequence.current
    setLoading(true)
    setError('')
    try {
      const params = {}
      if (filters.search) params.search = filters.search
      if (filters.lgu_id) params.lgu_id = Number(filters.lgu_id)
      if (filters.program_id) params.program_id = Number(filters.program_id)
      if (filters.fiscal_year) params.fiscal_year = Number(filters.fiscal_year)

      const [archiveRes, communicationRes, lguRes, programRes] = await Promise.all([
        governanceApi.listArchiveRecords({ ...params, page: archivePage, per_page: 20 }),
        governanceApi.listCommunications({
          page: communicationPage, per_page: 20,
          ...(filters.search ? { search: filters.search } : {}),
          ...(filters.lgu_id ? { lgu_id: Number(filters.lgu_id) } : {}),
        }),
        lguApi.listLgus({ per_page: 100 }),
        programApi.listPrograms({ per_page: 100 }),
      ])

      if (requestId !== requestSequence.current) return
      if (archiveRes.meta?.pages > 0 && archivePage > archiveRes.meta.pages) {
        setArchivePage(archiveRes.meta.pages)
        return
      }
      if (communicationRes.meta?.pages > 0 && communicationPage > communicationRes.meta.pages) {
        setCommunicationPage(communicationRes.meta.pages)
        return
      }
      const records = archiveRes.data || []
      setArchiveRecords(records)
      setArchiveMeta({ page: archivePage, pages: 1, total: records.length, per_page: 20, ...archiveRes.meta })
      setCommunications(communicationRes.data || [])
      setCommunicationMeta({ page: communicationPage, pages: 1, total: (communicationRes.data || []).length, per_page: 20, ...communicationRes.meta })
      setLgus(lguRes.data || [])
      setPrograms(programRes.data || [])
    } catch (requestError) {
      if (requestId !== requestSequence.current) return
      setError(requestError.response?.data?.message || 'Unable to load archive and communication records.')
    } finally {
      if (requestId === requestSequence.current) setLoading(false)
    }
  }, [filters, archivePage, communicationPage])

  useEffect(() => {
    loadPage()
  }, [loadPage])

  useEffect(() => {
    async function loadDetail() {
      if (!selectedRecord?.project_requirement_id) {
        setRecordDetail(null)
        return
      }
      setDetailLoading(true)
      try {
        const response = await governanceApi.getArchiveRecord(selectedRecord.project_requirement_id)
        setRecordDetail(response.data || null)
      } catch (requestError) {
        setError(requestError.response?.data?.message || 'Unable to load archive record details.')
      } finally {
        setDetailLoading(false)
      }
    }

    loadDetail()
  }, [selectedRecord])

  if (!isInternalUser()) {
    return (
      <GlassPanel>
        <h1 className="page-title mb-2">Archive & Communications</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Governance history is only available to internal users.
        </p>
      </GlassPanel>
    )
  }

  const handleDownloadFile = async (file) => {
    try {
      const response = await projectApi.downloadSubmissionFile(file.id)
      const blob = new Blob([response.data], { type: response.headers['content-type'] || file.mime_type || 'application/octet-stream' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = file.file_name
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (requestError) {
      setError(await fileTransferErrorMessage(requestError, 'Unable to download the archived file.'))
    }
  }

  const completedArchiveCount = archiveRecords.filter((record) => record.latest_push_status === 'completed').length
  const sentCommunicationCount = communications.filter((item) => item.delivery_status === 'sent').length

  return (
    <div>
      <PageHeader
        title="Archive & Communications"
        description="Browse documentary history by LGU, program, and fiscal year alongside consolidated communication logs."
        actions={<Button variant="outline" size="sm" onClick={loadPage}>Refresh</Button>}
      />

      <InlineAlert type="error" className="mb-4" onDismiss={() => setError('')}>
        {error}
      </InlineAlert>

      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-4">
        <KpiCard title="Archive Records" value={archiveMeta.total} icon={Archive} color="blue" />
        <KpiCard title="Handoff Completed (this page)" value={completedArchiveCount} icon={Send} color="emerald" />
        <KpiCard title="Communications" value={communicationMeta.total} icon={MessageSquareText} color="amber" />
        <KpiCard title="Sent Communications (this page)" value={sentCommunicationCount} icon={Send} color="cyan" />
      </div>

      <div className="mb-4 flex flex-wrap gap-3">
        <div className="relative min-w-[260px] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600 dark:text-slate-400" />
          <input
            id="archive-search"
            className="input-field pl-10"
            placeholder="Project, LGU, requirement, or subject"
            value={filters.search}
            onChange={(event) => { setArchivePage(1); setCommunicationPage(1); setFilters((current) => ({ ...current, search: event.target.value })) }}
            aria-label="Search archive and communications"
          />
        </div>
        <select
          id="archive-lgu"
          className="input-field w-auto min-w-[180px]"
          value={filters.lgu_id}
          onChange={(event) => { setArchivePage(1); setCommunicationPage(1); setFilters((current) => ({ ...current, lgu_id: event.target.value })) }}
          aria-label="Filter by LGU"
        >
          <option value="">All LGUs</option>
          {lgus.map((lgu) => (
            <option key={lgu.id} value={lgu.id}>{lgu.name}</option>
          ))}
        </select>
        <select
          id="archive-program"
          className="input-field w-auto min-w-[180px]"
          value={filters.program_id}
          onChange={(event) => { setArchivePage(1); setFilters((current) => ({ ...current, program_id: event.target.value })) }}
          aria-label="Filter by program"
        >
          <option value="">All Programs</option>
          {programs.map((program) => (
            <option key={program.id} value={program.id}>{program.name}</option>
          ))}
        </select>
        <select
          id="archive-fiscal-year"
          className="input-field w-auto min-w-[120px]"
          value={filters.fiscal_year}
          onChange={(event) => { setArchivePage(1); setFilters((current) => ({ ...current, fiscal_year: event.target.value })) }}
          aria-label="Filter by fiscal year"
        >
          <option value="">System FY{selectedFiscalYear ? ` ${selectedFiscalYear}` : ''}</option>
          {[...new Set([...fiscalYearOptions, selectedFiscalYear].filter(Boolean))].sort((a, b) => b - a).map((year) => (
            <option key={year} value={year}>FY {year}</option>
          ))}
        </select>
        <Button variant="outline" className="self-center" onClick={loadPage}>Apply Filters</Button>
      </div>

      <GlassPanel className="mb-6" noPadding>
        <div className="section-header">
          <h2 className="section-title">Document archive</h2>
        </div>
        <DocumentArchiveTable
          records={archiveRecords}
          programs={programs}
          loading={loading}
          pagination={archiveMeta}
          onPageChange={setArchivePage}
          onOpen={setSelectedRecord}
          selectedId={selectedRecord?.project_requirement_id}
        />
      </GlassPanel>

      <Drawer
        isOpen={!!selectedRecord}
        onClose={() => setSelectedRecord(null)}
        maxWidthClass="max-w-2xl"
      >
        <div className="flex h-full flex-col">
          <div className="flex items-start justify-between border-b border-brand-border px-5 py-4">
            <div>
              <div className="flex items-center gap-2">
                <FileClock className="h-5 w-5 text-blue-500" strokeWidth={1.5} />
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Document Version Record</h2>
              </div>
              {recordDetail && (
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                  {recordDetail.lgu_name} · FY {recordDetail.fiscal_year} · {recordDetail.requirement_name}
                </p>
              )}
            </div>
            <button
              aria-label="Close document version record"
              onClick={() => setSelectedRecord(null)}
              className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-300"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="flex flex-1 flex-col overflow-hidden">
            {detailLoading ? (
              <div className="py-8 text-center text-sm text-slate-600 dark:text-slate-400">Loading archive details...</div>
            ) : recordDetail ? (
              <>
                <div className="flex border-b border-brand-border px-5">
                  <button
                    className={`border-b-2 px-4 py-3 text-sm font-medium ${activeTab === 'submissions' ? 'border-brand-primary text-brand-primary' : 'border-transparent text-slate-600 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-100'}`}
                    onClick={() => setActiveTab('submissions')}
                  >
                    Submissions & Files
                  </button>
                  <button
                    className={`border-b-2 px-4 py-3 text-sm font-medium ${activeTab === 'handoffs' ? 'border-brand-primary text-brand-primary' : 'border-transparent text-slate-600 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-100'}`}
                    onClick={() => setActiveTab('handoffs')}
                  >
                    Regional Handoff
                  </button>
                  <button
                    className={`border-b-2 px-4 py-3 text-sm font-medium ${activeTab === 'communications' ? 'border-brand-primary text-brand-primary' : 'border-transparent text-slate-600 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-100'}`}
                    onClick={() => setActiveTab('communications')}
                  >
                    Communication Timeline
                  </button>
                  <button
                    className={`border-b-2 px-4 py-3 text-sm font-medium ${activeTab === 'audit' ? 'border-brand-primary text-brand-primary' : 'border-transparent text-slate-600 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-100'}`}
                    onClick={() => setActiveTab('audit')}
                  >
                    Audit Events
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto p-5">
                  {activeTab === 'submissions' && (
                    <div className="space-y-4">
                      {(recordDetail.submissions || []).map((submission) => (
                        <div key={submission.id} className="rounded-lg border border-brand-border bg-white/60 p-4 dark:bg-slate-900/40">
                          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                            <div>
                              <p className="text-sm font-semibold text-slate-900 dark:text-white">
                                Submission #{submission.id} · v{submission.current_version}
                              </p>
                              <p className="text-xs text-slate-600 dark:text-slate-400">
                                {formatMachineLabel(submission.source)} · {formatDateTime(submission.created_at)} · {submission.uploaded_by_name || 'Unassigned uploader'}
                              </p>
                            </div>
                          </div>
                          {submission.description && (
                            <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">{submission.description}</p>
                          )}
                          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                            <div className="min-w-0">
                              <p className="micro-text mb-2">Document Files</p>
                              <div className="space-y-2">
                                {(submission.document_files || []).map((file) => (
                                  <div key={file.id} className="flex items-center justify-between gap-3 rounded-md border border-brand-border px-3 py-2">
                                    <div className="min-w-0 flex-1">
                                      <p className="truncate text-sm font-medium text-slate-800 dark:text-slate-100" title={file.file_name}>{file.file_name}</p>
                                      <p className="text-xs text-slate-600 dark:text-slate-400">{formatBytes(file.file_size_bytes)} · {file.mime_type || 'file'}</p>
                                    </div>
                                    <Button size="sm" variant="outline" onClick={() => handleDownloadFile(file)}>
                                      <Download className="h-4 w-4" />
                                    </Button>
                                  </div>
                                ))}
                              </div>
                            </div>
                            <div className="min-w-0">
                              <p className="micro-text mb-2">Submission Versions</p>
                              <div className="space-y-2">
                                {(submission.versions || []).map((version) => (
                                  <div key={version.id} className="min-w-0 rounded-md border border-brand-border px-3 py-2 text-sm text-slate-700 dark:text-slate-300">
                                    <p className="truncate font-medium text-slate-800 dark:text-slate-100" title={`v${version.version_number} · ${version.original_filename}`}>
                                      v{version.version_number} · {version.original_filename}
                                    </p>
                                    <div className="text-xs text-slate-600 dark:text-slate-400">{formatDateTime(version.uploaded_at)}</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                      {!(recordDetail.submissions || []).length && (
                        <div className="rounded-lg border border-brand-border p-4 text-sm text-slate-600 dark:text-slate-400">
                          No submission versions are available for this archive record.
                        </div>
                      )}
                    </div>
                  )}

                  {activeTab === 'handoffs' && (
                    <div className="space-y-2">
                      {(recordDetail.handoffs || []).map((handoff) => (
                        <div key={handoff.id} className="min-w-0 rounded-md border border-brand-border px-3 py-2 text-sm">
                          <div className="mb-1 flex items-center justify-between gap-2">
                            {pushBadge(handoff.push_status)}
                            <span className="text-xs text-slate-600 dark:text-slate-400">{formatDateTime(handoff.pushed_at)}</span>
                          </div>
                          <p className="truncate text-slate-700 dark:text-slate-300" title={handoff.destination_path || 'Destination not recorded'}>
                            {handoff.destination_path || 'Destination not recorded'}
                          </p>
                        </div>
                      ))}
                      {!(recordDetail.handoffs || []).length && <p className="text-sm text-slate-600 dark:text-slate-400">No handoff attempts recorded.</p>}
                    </div>
                  )}

                  {activeTab === 'communications' && (
                    <div className="space-y-2">
                      {(recordDetail.communications || []).map((communication) => (
                        <div key={communication.id} className="min-w-0 rounded-md border border-brand-border px-3 py-2 text-sm">
                          <p className="truncate font-medium text-slate-800 dark:text-slate-100" title={communication.subject || formatMachineLabel(communication.communication_type)}>
                            {communication.subject || formatMachineLabel(communication.communication_type)}
                          </p>
                          <p className="text-xs text-slate-600 dark:text-slate-400">
                            {formatMachineLabel(communication.channel)} · {formatStatus(communication.delivery_status)} · {formatDateTime(communication.sent_at || communication.created_at)}
                          </p>
                        </div>
                      ))}
                      {!(recordDetail.communications || []).length && <p className="text-sm text-slate-600 dark:text-slate-400">No communications matched this project record.</p>}
                    </div>
                  )}

                  {activeTab === 'audit' && (
                    <div className="space-y-2">
                      {(recordDetail.audit_events || []).map((event) => (
                        <div key={event.id} className="min-w-0 rounded-md border border-brand-border px-3 py-2 text-xs text-slate-600 dark:text-slate-300">
                          <p className="truncate font-medium text-slate-800 dark:text-slate-100">
                            {formatMachineLabel(event.action)} · {formatMachineLabel(event.entity_type)} #{event.entity_id}
                          </p>
                          <div className="text-slate-600 dark:text-slate-400">{formatDateTime(event.created_at)} · {event.user_name || 'System'}</div>
                        </div>
                      ))}
                      {!(recordDetail.audit_events || []).length && <p className="text-sm text-slate-600 dark:text-slate-400">No audit events matched this archive record.</p>}
                    </div>
                  )}
                </div>
              </>
            ) : null}
          </div>
        </div>
      </Drawer>

      <GlassPanel noPadding>
        <div className="section-header">
          <div><h2 className="section-title">Communication history</h2><p className="mt-1 text-xs text-brand-text-muted">This history uses the search and LGU filters above.</p></div>
        </div>
        <CommunicationHistoryTable
          records={communications}
          loading={loading}
          pagination={communicationMeta}
          onPageChange={setCommunicationPage}
        />
      </GlassPanel>
    </div>
  )
}
