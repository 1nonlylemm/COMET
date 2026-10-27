import { useEffect, useState } from 'react'
import { AlertCircle, AlertTriangle, FileText, Info, Loader2, MapPin } from 'lucide-react'
import * as projectApi from '../../projects/api/projectApi'
import { AnnotatedDocumentPreview } from './AnnotatedDocumentPreview'
import { DEFAULT_BBOX_TYPE, annotationsForResult } from './documentAnnotations'
import { resolvePdfTextAnnotations } from './pdfAnnotationResolver'

const SEVERITY_META = {
  blocker: {
    label: 'Blocker',
    Icon: AlertTriangle,
    border: 'border-red-500',
    fill: 'bg-red-500/20',
    text: 'text-red-700 dark:text-red-200',
  },
  warning: {
    label: 'Warning',
    Icon: AlertCircle,
    border: 'border-amber-500',
    fill: 'bg-amber-400/25',
    text: 'text-amber-800 dark:text-amber-100',
  },
  info: {
    label: 'Info',
    Icon: Info,
    border: 'border-blue-500',
    fill: 'bg-blue-400/20',
    text: 'text-blue-700 dark:text-blue-200',
  },
}

const DEFAULT_META = SEVERITY_META.info

function round4(value) {
  return Math.round(Number(value) * 10000) / 10000
}

function positiveInt(value) {
  const numeric = Number.parseInt(value, 10)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null
}

function percent(value) {
  return `${round4(Number(value) * 100)}%`
}

function labelForType(type) {
  return String(type || DEFAULT_BBOX_TYPE)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function groupedByPage(annotations) {
  const groups = new Map()
  for (const annotation of annotations) {
    const page = positiveInt(annotation.page)
    if (!page) continue
    if (!groups.has(page)) groups.set(page, [])
    groups.get(page).push(annotation)
  }
  return [...groups.entries()].sort(([left], [right]) => left - right)
}

export function DocumentAnnotationViewer({ result, file = null, workspace = false, focusTarget = null }) {
  const annotations = resolvePdfTextAnnotations(annotationsForResult(result))
  const groups = groupedByPage(annotations)
  const previewKey = file?.id ? `${file.id}:${result?.id || 'latest'}` : ''
  const [previewState, setPreviewState] = useState({
    previewKey: '',
    error: '',
    filePreview: null,
  })

  useEffect(() => {
    let cancelled = false
    let objectUrl = ''

    if (!file?.id) {
      return undefined
    }

    const downloadPromise = projectApi.downloadSubmissionFile?.(file.id)
    if (!downloadPromise?.then) {
      return undefined
    }

    downloadPromise
      .then((response) => {
        const mimeType = response.headers?.['content-type'] || file.mime_type || 'application/octet-stream'
        const blob = new Blob([response.data], { type: mimeType })
        objectUrl = window.URL.createObjectURL(blob)
        if (cancelled) {
          window.URL.revokeObjectURL(objectUrl)
          return
        }
        setPreviewState({
          previewKey,
          error: '',
          filePreview: {
            url: objectUrl,
            fileName: file.file_name || `submission-${file.id}`,
            mimeType,
            sizeBytes: file.file_size_bytes,
            complianceResult: result,
          },
        })
      })
      .catch(() => {
        if (!cancelled) {
          setPreviewState({
            previewKey,
            error: 'Unable to render the attached document with highlights.',
            filePreview: null,
          })
        }
      })

    return () => {
      cancelled = true
      if (objectUrl) {
        window.URL.revokeObjectURL(objectUrl)
      }
    }
  }, [file?.id, file?.file_name, file?.file_size_bytes, file?.mime_type, previewKey, result])

  if (!groups.length && !workspace) {
    return (
      <section
        data-testid="document-annotation-viewer"
        className="rounded-md border border-dashed border-brand-border bg-brand-surface px-3 py-4 text-center text-xs text-brand-text-muted"
      >
        No page highlights are available for this checker result yet. Findings without page locations still appear in the findings list.
      </section>
    )
  }

  if (file?.id) {
    if (previewState.previewKey !== previewKey) {
      return (
        <section
          data-testid="document-annotation-viewer"
          className="flex min-h-[240px] items-center justify-center rounded-lg border border-brand-border bg-brand-surface text-sm text-brand-text-muted"
        >
          <Loader2 className="mr-2 h-4 w-4 animate-spin" strokeWidth={1.7} />
          Rendering attached document with highlights...
        </section>
      )
    }

    if (previewState.filePreview) {
      return (
        <section data-testid="document-annotation-viewer" className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm font-medium text-brand-text">
              <MapPin className="h-4 w-4 text-brand-primary" strokeWidth={1.7} />
              {workspace ? 'Document preview' : 'Document Highlights'}
            </div>
            <span className="text-xs text-brand-text-muted">
              {annotations.length} location{annotations.length === 1 ? '' : 's'}
            </span>
          </div>
          <AnnotatedDocumentPreview filePreview={previewState.filePreview} compact={workspace} focusTarget={focusTarget} />
        </section>
      )
    }
  }

  if (workspace) {
    return (
      <section data-testid="document-annotation-viewer" className="flex min-h-72 flex-col items-center justify-center gap-2 p-5 text-center text-sm text-brand-text-muted">
        <FileText className="h-6 w-6" />
        <p>{previewState.error || 'No attached file is available for preview.'}</p>
        <p className="text-xs">Recorded evidence and submission details remain available under Files.</p>
      </section>
    )
  }

  return (
    <section data-testid="document-annotation-viewer" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium text-brand-text">
          <MapPin className="h-4 w-4 text-brand-primary" strokeWidth={1.7} />
          Document Highlights
        </div>
        <span className="text-xs text-brand-text-muted">
          {annotations.length} location{annotations.length === 1 ? '' : 's'}
        </span>
      </div>

      {previewState.error && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-300/40 dark:bg-amber-300/10 dark:text-amber-100">
          {previewState.error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="space-y-3">
          {groups.map(([page, pageAnnotations]) => (
            <div key={page} className="rounded-md border border-brand-border bg-brand-surface p-3">
              <div className="mb-2 text-xs font-semibold text-brand-text">Page {page}</div>
              {pageAnnotations.some(a => a.resolution_state === 'page_marker') && <p className="mb-2 rounded border border-blue-300 bg-blue-50 p-2 text-xs text-blue-900">{pageAnnotations.filter(a => a.resolution_state === 'page_marker').length} findings on this page</p>}
              <div
                className="relative mx-auto max-w-[18rem] overflow-hidden rounded-sm border border-brand-border bg-white shadow-sm dark:bg-slate-950"
                style={{ aspectRatio: '1 / 1.414' }}
              >
                <div className="absolute inset-x-6 top-8 h-2 rounded bg-slate-200 dark:bg-slate-700" />
                <div className="absolute inset-x-6 top-14 h-1.5 rounded bg-slate-100 dark:bg-slate-800" />
                <div className="absolute inset-x-6 top-20 h-1.5 rounded bg-slate-100 dark:bg-slate-800" />
                <div className="absolute inset-x-10 bottom-10 h-10 rounded border border-dashed border-slate-200 dark:border-slate-700" />
                {pageAnnotations
                  .filter((annotation) => annotation.renderable && annotation.bbox)
                  .map((annotation) => {
                    const meta = SEVERITY_META[annotation.severity] || DEFAULT_META
                    const box = annotation.bbox
                    return (
                      <button
                        key={annotation.id}
                        type="button"
                        data-testid={`document-annotation-${annotation.id}`}
                        className={`absolute rounded-sm border-2 ${meta.border} ${meta.fill} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/50`}
                        style={{
                          left: percent(box.x),
                          top: percent(box.y),
                          width: percent(box.width),
                          height: percent(box.height),
                        }}
                        aria-label={`${meta.label} highlight on page ${annotation.page}: ${annotation.message}`}
                        title={`${meta.label}: ${annotation.message}`}
                      />
                    )
                  })}
              </div>
            </div>
          ))}
        </div>

        <ol className="space-y-2">
          {annotations.map((annotation) => {
            const meta = SEVERITY_META[annotation.severity] || DEFAULT_META
            const Icon = meta.Icon
            return (
              <li
                key={annotation.id}
                className="rounded-md border border-brand-border bg-brand-surface px-3 py-2.5 text-xs"
              >
                <div className="flex items-start gap-2">
                  <Icon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${meta.text}`} strokeWidth={1.8} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-brand-text-muted">
                      <span>Page {annotation.page}</span>
                      <span>·</span>
                      <span>{labelForType(annotation.bbox_type)}</span>
                    </div>
                    <div className="mt-1 font-medium text-brand-text">{annotation.message}</div>
                    {annotation.detail && (
                      <div className="mt-0.5 text-brand-text-muted">{annotation.detail}</div>
                    )}
                    {annotation.reason && (
                      <div className="mt-0.5 text-brand-text-muted">{annotation.reason}</div>
                    )}
                    {!annotation.renderable && (
                      <div className="mt-1 text-brand-text-muted">
                        No drawable region is available for this location.
                      </div>
                    )}
                  </div>
                </div>
              </li>
            )
          })}
        </ol>
      </div>
    </section>
  )
}

export default DocumentAnnotationViewer
