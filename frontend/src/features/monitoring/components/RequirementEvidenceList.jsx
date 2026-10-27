import { useCallback, useEffect, useState } from 'react'
import { Download, Eye } from 'lucide-react'
import { Button, Modal } from '../../../components'
import { AnnotatedDocumentPreview } from '../../intake/components/AnnotatedDocumentPreview'
import { fileMeta } from '../../intake/lib/intakeFormatters.js'
import * as projectApi from '../../projects/api/projectApi'

/**
 * Shared "already uploaded evidence" list for the Phase 2A/2B monitoring
 * panels (Monthly Progress Report, Form 3, Project Exception Report,
 * Non-Infra Monitoring, Beneficiary Evidence). Every one of those panels
 * only exposed a fresh, empty file picker with no way to see files a
 * Field Officer already uploaded -- this reuses the existing DMS Intake
 * submission listing (`projectApi.listRequirementSubmissions`) and file
 * preview/download pipeline (`projectApi.downloadSubmissionFile`,
 * `AnnotatedDocumentPreview`) instead of building a second file viewer.
 *
 * `refreshKey` lets the parent force a re-fetch after a new upload
 * without needing its own submissions state.
 */
export function RequirementEvidenceList({ requirementId, refreshKey, onFileCountChange }) {
  const [submissions, setSubmissions] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState(null)
  const [previewLoadingId, setPreviewLoadingId] = useState('')

  const load = useCallback(async () => {
    if (!requirementId) return
    setLoading(true)
    setError('')
    try {
      const response = await projectApi.listRequirementSubmissions(requirementId)
      const loadedSubmissions = response.data || []
      setSubmissions(loadedSubmissions)
      const fileCount = loadedSubmissions.reduce((total, submission) => total + (submission.document_files?.length || 0), 0)
      onFileCountChange?.(fileCount)
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to load uploaded evidence.')
    } finally {
      setLoading(false)
    }
  }, [requirementId, onFileCountChange])

  useEffect(() => {
    load()
  }, [load, refreshKey])

  useEffect(() => {
    return () => {
      if (preview?.url) {
        window.URL.revokeObjectURL(preview.url)
      }
    }
  }, [preview?.url])

  const files = submissions.flatMap((submission) => submission.document_files || [])

  const handlePreview = async (file) => {
    setPreviewLoadingId(file.id)
    setError('')
    try {
      const response = await projectApi.downloadSubmissionFile(file.id)
      const mimeType = response.headers?.['content-type'] || file.mime_type || 'application/octet-stream'
      const blob = new Blob([response.data], { type: mimeType })
      const url = window.URL.createObjectURL(blob)
      setPreview((current) => {
        if (current?.url) window.URL.revokeObjectURL(current.url)
        return { url, fileName: file.file_name, mimeType }
      })
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to preview this file.')
    } finally {
      setPreviewLoadingId('')
    }
  }

  const handleDownload = async (file) => {
    setError('')
    try {
      const response = await projectApi.downloadSubmissionFile(file.id)
      const mimeType = response.headers?.['content-type'] || file.mime_type || 'application/octet-stream'
      const blob = new Blob([response.data], { type: mimeType })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = file.file_name || `evidence-${file.id}`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      setTimeout(() => window.URL.revokeObjectURL(url), 1500)
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Unable to download this file.')
    }
  }

  if (!requirementId) return null

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wider text-brand-text-muted">
        Uploaded evidence {files.length > 0 && `(${files.length})`}
      </p>
      {error && <p className="text-xs text-red-600 dark:text-red-300">{error}</p>}
      {loading ? (
        <p className="text-xs text-brand-text-muted">Loading uploaded files...</p>
      ) : files.length === 0 ? (
        <p className="text-xs text-brand-text-muted">No evidence uploaded yet.</p>
      ) : (
        <ul className="divide-y divide-brand-border rounded-md border border-brand-border bg-brand-surface">
          {files.map((file) => {
            const meta = fileMeta(file.file_name)
            const Icon = meta.Icon
            return (
              <li key={file.id} className="flex items-center justify-between gap-3 px-3 py-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md border ${meta.className}`}>
                    <Icon className="h-4 w-4" strokeWidth={1.7} aria-hidden="true" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-brand-text" title={file.file_name}>
                      {file.file_name}
                    </p>
                    {file.created_at && (
                      <p className="text-xs text-brand-text-muted">
                        {new Date(file.created_at).toLocaleDateString('en-PH', { year: 'numeric', month: 'short', day: 'numeric' })}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1.5">
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={Eye}
                    loading={previewLoadingId === file.id}
                    onClick={() => handlePreview(file)}
                  >
                    Preview
                  </Button>
                  <Button size="sm" variant="ghost" icon={Download} onClick={() => handleDownload(file)}>
                    Download
                  </Button>
                </div>
              </li>
            )
          })}
        </ul>
      )}

      <Modal
        open={Boolean(preview)}
        title="Document Preview"
        description={preview?.fileName}
        onClose={() => setPreview(null)}
        size="xl"
        footer={preview && (
          <div className="flex justify-end">
            <a
              href={preview.url}
              download={preview.fileName}
              className="btn-outline inline-flex min-h-10 items-center justify-center gap-2 px-4 py-2 text-sm"
            >
              <Download className="h-4 w-4" strokeWidth={1.5} aria-hidden="true" />
              Download
            </a>
          </div>
        )}
      >
        {preview && <AnnotatedDocumentPreview filePreview={preview} />}
      </Modal>
    </div>
  )
}
