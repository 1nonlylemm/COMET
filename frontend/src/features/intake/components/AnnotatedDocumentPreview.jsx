import { useEffect, useRef, useState } from 'react'
import { AlertCircle, AlertTriangle, FileText, Info, Layers, Loader2 } from 'lucide-react'
import * as pdfjsLib from 'pdfjs-dist'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url'
import { annotationsForResult } from './documentAnnotations'
import { resolvePdfTextAnnotations, focusPdfFinding } from './pdfAnnotationResolver'
import { canPreviewInline, fileMeta } from '../lib/intakeFormatters.js'
import { formatMachineLabel } from '../../../lib/formatters'

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl

const SEVERITY_META = {
  blocker: {
    label: 'Blocker',
    Icon: AlertTriangle,
    border: 'border-red-500',
    fill: 'bg-red-500/20',
    ring: 'ring-red-500/30',
    text: 'text-red-700 dark:text-red-200',
  },
  warning: {
    label: 'Warning',
    Icon: AlertCircle,
    border: 'border-amber-500',
    fill: 'bg-amber-400/25',
    ring: 'ring-amber-500/30',
    text: 'text-amber-800 dark:text-amber-100',
  },
  minor_warning: {
    label: 'Warning',
    Icon: AlertCircle,
    border: 'border-amber-400',
    fill: 'bg-amber-300/20',
    ring: 'ring-amber-400/30',
    text: 'text-amber-800 dark:text-amber-100',
  },
  info: {
    label: 'Info',
    Icon: Info,
    border: 'border-blue-500',
    fill: 'bg-blue-400/20',
    ring: 'ring-blue-500/30',
    text: 'text-blue-700 dark:text-blue-200',
  },
}

const DEFAULT_META = SEVERITY_META.info

function isPdf(fileName, mimeType) {
  return String(mimeType || '').toLowerCase().includes('pdf') || String(fileName || '').toLowerCase().endsWith('.pdf')
}

function isImage(mimeType) {
  return String(mimeType || '').toLowerCase().startsWith('image/')
}

function annotationGroups(annotations) {
  const groups = new Map()
  for (const annotation of annotations) {
    const page = Number.parseInt(annotation.page, 10)
    if (!Number.isFinite(page) || page < 1) continue
    if (!groups.has(page)) groups.set(page, [])
    groups.get(page).push(annotation)
  }
  return groups
}

function percent(value) {
  return `${Math.round(Number(value) * 10000) / 100}%`
}

function isTextAnchorAnnotation(annotation) {
  return Boolean(
    String(annotation?.matched_text || '').trim()
    && ['detected_text', 'rendered_text'].includes(annotation?.bbox_type),
  )
}

function isPreviewAnnotation(annotation, allowTextAnchor = false) {
  if (annotation.resolution_state === 'none') return false
  if (annotation.resolution_state === 'page_marker') return true
  if (annotation?.renderable && annotation?.bbox) return true
  return allowTextAnchor && isTextAnchorAnnotation(annotation)
}

function PageMarkers({ annotations = [], pageNumber }) {
  const markers = annotations.filter(a => a.resolution_state === 'page_marker')
  if (!markers.length) return null
  return <button type="button" data-testid={`document-preview-page-marker-${pageNumber}`} data-finding-ids={JSON.stringify([...new Set(markers.map(a => a.finding_id))])} className="rounded border border-blue-300 bg-blue-50 px-2 py-1 text-xs text-blue-900">{markers.length} findings on this page</button>
}

function AnnotationOverlay({ annotations = [], pageNumber }) {
  const [activeAnnotationId, setActiveAnnotationId] = useState(null)
  const verified = annotations.filter(a => a.resolution_state === 'verified_box' && a.renderable)
  if (!verified.length) return null
  return <div className="pointer-events-none absolute inset-0" data-testid={`document-preview-annotation-layer-${pageNumber}`}>
    {verified.flatMap(annotation => (annotation.boxes || [annotation.bbox]).map((box, index) => {
      const active = activeAnnotationId === annotation.id
      const tooltipId = `document-preview-annotation-tooltip-${annotation.id}`
      return <button type="button" key={`${annotation.id}:${index}`} data-testid={`document-preview-annotation-${annotation.id}${index ? `-part-${index}` : ''}`} data-finding-id={annotation.finding_id} data-annotation-id={annotation.id} data-resolution-state="verified_box"
        className="pointer-events-auto absolute rounded-sm border-0 bg-amber-300/35 p-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500"
        style={{ left: percent(box.x), top: percent(box.y), width: percent(box.width), height: percent(box.height) }}
        title={annotation.message} aria-label={`Finding ${annotation.annotation_number}: ${annotation.matched_text || annotation.message}`} aria-describedby={active ? tooltipId : undefined}
        onMouseEnter={() => setActiveAnnotationId(annotation.id)} onMouseLeave={() => setActiveAnnotationId(null)} onFocus={() => setActiveAnnotationId(annotation.id)} onBlur={() => setActiveAnnotationId(null)}>
        {index === 0 && <span className="absolute bottom-full left-0 rounded bg-amber-800 px-1 text-[10px] font-bold text-white" data-testid="highlight-number">{annotation.annotation_number}</span>}
        {active && <span role="tooltip" id={tooltipId} data-testid={tooltipId} className="pointer-events-none absolute left-0 top-full z-30 mt-1 w-64 rounded border border-slate-300 bg-white p-2 text-left text-xs text-slate-900 shadow-xl dark:bg-slate-950 dark:text-slate-50">{annotation.message}{annotation.matched_text && <span className="block">Text: {annotation.matched_text}</span>}{annotation.reason && <span className="block">{annotation.reason}</span>}</span>}
      </button>
    }))}
  </div>
}
function HighlightSummary({ annotations }) {
  if (!annotations.length) {
    return (
      <div className="rounded-md border border-dashed border-brand-border bg-brand-surface px-3 py-2 text-xs text-brand-text-muted">
        No drawable highlights are available yet. Run the checker or add a template/profile with expected zones to generate document highlights.
      </div>
    )
  }

  return (
    <aside className="space-y-2 rounded-lg border border-brand-border bg-brand-surface-solid p-3">
      <div className="flex items-center justify-between gap-2 text-xs font-semibold text-brand-text">
        <span className="inline-flex items-center gap-1.5">
          <Layers className="h-3.5 w-3.5 text-brand-primary" strokeWidth={1.7} />
          Highlighted findings
        </span>
        <span className="text-brand-text-muted">{annotations.length}</span>
      </div>
      <ol className="max-h-56 space-y-1.5 overflow-auto pr-1">
        {annotations.map((annotation) => {
          const meta = SEVERITY_META[annotation.severity] || DEFAULT_META
          const Icon = meta.Icon
          return (
            <li key={annotation.id} className="rounded-md border border-brand-border bg-brand-surface px-2.5 py-2 text-xs">
              <div className="flex items-start gap-2">
                <Icon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${meta.text}`} strokeWidth={1.8} />
                <div className="min-w-0">
                  <div className="font-medium text-brand-text">{annotation.message}</div>
                  <div className="mt-0.5 text-[11px] text-brand-text-muted">
                    Page {annotation.page}{annotation.bbox_type ? ` · ${formatMachineLabel(annotation.bbox_type)}` : ''}
                  </div>
                  {annotation.detail && (
                    <div className="mt-0.5 text-brand-text-muted">{annotation.detail}</div>
                  )}
                </div>
              </div>
            </li>
          )
        })}
      </ol>
    </aside>
  )
}

function ImagePreview({ filePreview, annotationsByPage }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-brand-border bg-brand-surface p-3">
      <PageMarkers annotations={annotationsByPage.get(1) || []} pageNumber={1} />
      <div className="relative inline-block max-w-full overflow-hidden rounded-md bg-white shadow-sm">
        <img
          src={filePreview.url}
          alt={filePreview.fileName}
          className="block max-h-[65vh] max-w-full object-contain"
        />
        <AnnotationOverlay annotations={annotationsByPage.get(1) || []} pageNumber={1} />
      </div>
    </div>
  )
}

function PdfPage({ pdf, pageNumber, annotations }) {
  const canvasRef = useRef(null)
  const [pageSize, setPageSize] = useState(null)
  const [error, setError] = useState('')
  const [resolvedAnnotations, setResolvedAnnotations] = useState(annotations)

  useEffect(() => {
    let cancelled = false
    let renderTask = null

    async function renderPage() {
      try {
        const page = await pdf.getPage(pageNumber)
        if (cancelled) return
        const viewport = page.getViewport({ scale: 1.45 })
        const canvas = canvasRef.current
        if (!canvas) return
        const context = canvas.getContext('2d')
        canvas.width = Math.floor(viewport.width)
        canvas.height = Math.floor(viewport.height)
        setPageSize({ width: viewport.width, height: viewport.height })
        setResolvedAnnotations(annotations)
        renderTask = page.render({ canvasContext: context, viewport })
        await renderTask.promise
      } catch (renderError) {
        if (!cancelled && renderError?.name !== 'RenderingCancelledException') {
          setError('Unable to render this page preview.')
        }
      }
    }

    renderPage()

    return () => {
      cancelled = true
      if (renderTask) renderTask.cancel()
    }
  }, [annotations, pdf, pageNumber])

  return (
    <section className="mx-auto max-w-full" data-testid={`pdf-preview-page-${pageNumber}`}>
      <div className="mb-1.5 flex items-center justify-between text-xs font-medium text-brand-text-muted">Page {pageNumber}<PageMarkers annotations={resolvedAnnotations} pageNumber={pageNumber} /></div>
      <div
        className="relative overflow-hidden rounded-md border border-brand-border bg-white shadow-sm"
        style={pageSize ? { width: pageSize.width, maxWidth: '100%' } : undefined}
      >
        <canvas ref={canvasRef} className="block h-auto w-full" />
        <AnnotationOverlay annotations={resolvedAnnotations} pageNumber={pageNumber} />
      </div>
      {error && <div className="mt-1 text-xs text-red-600 dark:text-red-300">{error}</div>}
    </section>
  )
}

function PdfPreview({ filePreview, annotationsByPage, focusTarget }) {
  const pagesRef = useRef(null)
  const [state, setState] = useState({
    url: '',
    pdf: null,
    loading: true,
    error: '',
  })

  useEffect(() => {
    let cancelled = false
    const task = pdfjsLib.getDocument(filePreview.url)

    task.promise
      .then((loadedPdf) => {
        if (!cancelled) {
          setState({
            url: filePreview.url,
            pdf: loadedPdf,
            loading: false,
            error: '',
          })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({
            url: filePreview.url,
            pdf: null,
            loading: false,
            error: 'Unable to render this PDF preview with highlights.',
          })
        }
      })

    return () => {
      cancelled = true
      task.destroy()
    }
  }, [filePreview.url])

  const isCurrentUrl = state.url === filePreview.url
  const loading = !isCurrentUrl || state.loading
  const error = isCurrentUrl ? state.error : ''
  const pdf = isCurrentUrl ? state.pdf : null

  useEffect(() => {
    if (!focusTarget?.page || !pdf) return
    const revealPage = () => focusPdfFinding(pagesRef.current, focusTarget)
    revealPage()
    // PDF pages acquire their height asynchronously; keep the selected page in
    // view while the preceding pages finish rendering.
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(revealPage)
    pagesRef.current?.querySelectorAll('[data-testid^="pdf-preview-page-"]').forEach(element => observer.observe(element))
    return () => observer.disconnect()
  }, [focusTarget, pdf])

  if (loading) {
    return (
      <div className="flex min-h-[280px] items-center justify-center rounded-lg border border-brand-border bg-brand-surface text-sm text-brand-text-muted">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" strokeWidth={1.7} />
        Rendering document pages...
      </div>
    )
  }

  if (error || !pdf) {
    return (
      <div className="space-y-2"><p role="alert" className="rounded border border-amber-400 bg-amber-50 p-3 text-sm text-amber-950">Document highlights unavailable</p><iframe title={filePreview.fileName} src={filePreview.url} className="h-[65vh] w-full rounded-lg border border-brand-border bg-white" /></div>
    )
  }

  return (
    <div ref={pagesRef} className="max-h-[62vh] min-w-0 space-y-5 overflow-y-auto overflow-x-hidden rounded-lg border border-brand-border bg-brand-surface p-3">
      {Array.from({ length: pdf.numPages }, (_, index) => {
        const pageNumber = index + 1
        return (
          <PdfPage
            key={pageNumber}
            pdf={pdf}
            pageNumber={pageNumber}
            annotations={annotationsByPage.get(pageNumber) || []}
          />
        )
      })}
    </div>
  )
}

function UnsupportedPreview({ filePreview }) {
  const { Icon, label, className } = fileMeta(filePreview.fileName)
  return (
    <div className="flex min-h-[280px] flex-col items-center justify-center rounded-lg border border-brand-border bg-brand-surface p-8 text-center">
      <div className={`flex h-14 w-14 items-center justify-center rounded-lg border ${className}`}>
        <Icon className="h-6 w-6" strokeWidth={1.7} />
      </div>
      <div className="mt-4 text-sm font-semibold text-brand-text">{label.toUpperCase()} file ready</div>
      <p className="mt-2 max-w-md text-sm text-brand-text-muted">
        Browser preview with highlights is available for PDF and image files. Download this format to inspect it locally.
      </p>
    </div>
  )
}

export function AnnotatedDocumentPreview({ filePreview, compact = false, focusTarget = null }) {
  const mimeType = String(filePreview?.mimeType || '').toLowerCase()
  const pdfPreview = isPdf(filePreview?.fileName, mimeType)
  const annotations = resolvePdfTextAnnotations(annotationsForResult(filePreview?.complianceResult))
    .filter((annotation) => isPreviewAnnotation(annotation, pdfPreview))
  const annotationsByPage = annotationGroups(annotations)
  const inlinePreview = canPreviewInline(filePreview?.fileName, filePreview?.mimeType)

  if (!filePreview) return null

  return (
    <div className={compact ? 'min-w-0' : 'grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_18rem]'}>
      <div data-testid="annotated-document-preview" className="min-w-0">
        {isImage(mimeType) ? (
          <ImagePreview filePreview={filePreview} annotationsByPage={annotationsByPage} />
        ) : isPdf(filePreview.fileName, mimeType) ? (
          <PdfPreview filePreview={filePreview} annotationsByPage={annotationsByPage} focusTarget={focusTarget} />
        ) : inlinePreview ? (
          <iframe
            title={filePreview.fileName}
            src={filePreview.url}
            className="h-[65vh] w-full rounded-lg border border-brand-border bg-white"
          />
        ) : (
          <UnsupportedPreview filePreview={filePreview} />
        )}
      </div>
      {!compact && <div className="space-y-3">
        <div className="rounded-lg border border-brand-border bg-brand-surface-solid p-3 text-xs text-brand-text-muted">
          <div className="flex items-center gap-1.5 font-semibold text-brand-text">
            <FileText className="h-3.5 w-3.5 text-brand-primary" strokeWidth={1.7} />
            Checker overlay
          </div>
          <p className="mt-1">
            Highlights are drawn from the latest compliance result for this file. Scanned PDFs and photographed documents are rendered as pages first, then highlighted over the rendered image.
          </p>
        </div>
        <HighlightSummary annotations={annotations} />
      </div>}
    </div>
  )
}

export default AnnotatedDocumentPreview
