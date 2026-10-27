import { useEffect, useRef, useState } from 'react'
import { renderAsync } from 'docx-preview'

function base64ToArrayBuffer(base64) {
  const binaryString = window.atob(base64)
  const len = binaryString.length
  const bytes = new Uint8Array(len)
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i)
  }
  return bytes.buffer
}

function paragraphClass(block) {
  const align = {
    center: 'text-center',
    right: 'text-right',
    justify: 'text-justify',
  }[block.align] || 'text-left'
  const style = String(block.style || '').toLowerCase()
  const weight = style.includes('heading') || style.includes('title') ? 'font-semibold' : 'font-normal'
  return `${align} ${weight}`
}

function renderParagraphText(text) {
  return String(text || '').split('\n').map((line, index) => (
    <span key={`${line}-${index}`}>
      {line}
      {index < String(text || '').split('\n').length - 1 && <br />}
    </span>
  ))
}

function renderBlock(block, index) {
  if (block.type === 'table') {
    return (
      <div key={`table-${index}`} className="my-4 overflow-x-auto">
        <table className="w-full border-collapse text-[11px] leading-5">
          <tbody>
            {(block.rows || []).map((row, rowIndex) => (
              <tr key={`row-${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td key={`cell-${cellIndex}`} className="border border-slate-300 px-2 py-1 align-top dark:border-slate-600">
                    {renderParagraphText(cell.text)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <p key={`paragraph-${index}`} className={`mb-3 whitespace-pre-wrap ${paragraphClass(block)}`}>
      {renderParagraphText(block.text)}
    </p>
  )
}

function fallbackBlocks(text) {
  return String(text || '')
    .split(/\n{2,}/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((text) => ({ type: 'paragraph', text, align: 'left', style: '' }))
}

export function DocumentPreview({
  document,
  docxBase64,
  fallbackText,
  title = 'Document preview',
  emptyMessage = 'Generate a preview to review the document layout.',
  loading = false,
}) {
  const docxData = docxBase64 || document?.docx_base64
  const containerRef = useRef(null)
  const [renderedDocx, setRenderedDocx] = useState(null)
  const [renderError, setRenderError] = useState(null)

  useEffect(() => {
    if (!docxData || !containerRef.current) return
    let isMounted = true
    const container = containerRef.current
    container.innerHTML = ''

    Promise.resolve()
      .then(() => {
        const buffer = typeof docxData === 'string' ? base64ToArrayBuffer(docxData) : docxData
        return renderAsync(buffer, container, null, {
          className: 'comet-docx-preview',
          inWrapper: true,
          ignoreWidth: false,
          ignoreHeight: false,
          breakPages: true,
          renderHeaders: true,
          renderFooters: true,
        })
      })
      .then(() => {
        if (isMounted) {
          setRenderedDocx(docxData)
        }
      })
      .catch((err) => {
        if (isMounted) {
          setRenderError({ docx: docxData, message: err?.message || 'Failed to render DOCX preview.' })
          setRenderedDocx(docxData)
        }
      })

    return () => {
      isMounted = false
    }
  }, [docxData])

  const blocks = document?.blocks?.length
    ? document.blocks
    : document?.preview_document?.blocks?.length
      ? document.preview_document.blocks
      : fallbackBlocks(fallbackText || document?.preview_text)

  const currentError = renderError && renderError.docx === docxData ? renderError.message : null
  const renderingDocx = Boolean(docxData) && renderedDocx !== docxData && !currentError
  const hasDocx = Boolean(docxData) && !currentError

  return (
    <div className="rounded-lg border border-brand-border bg-slate-100 p-3 dark:bg-slate-900/60">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-brand-text-muted">{title}</div>
        <div className="flex items-center gap-2">
          {hasDocx && (
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
              DOCX High-Fidelity
            </span>
          )}
          {document?.truncated && (
            <span className="rounded-full border border-brand-border px-2 py-0.5 text-[11px] font-medium text-brand-text-muted">
              Preview truncated
            </span>
          )}
        </div>
      </div>

      {hasDocx ? (
        <div className="relative max-h-[38rem] overflow-y-auto rounded bg-slate-200/50 p-2 dark:bg-slate-950/40">
          {(loading || renderingDocx) && (
            <div className="flex min-h-[20rem] items-center justify-center rounded-md border border-brand-border bg-brand-surface py-12 text-sm text-brand-text-muted">
              Rendering document preview...
            </div>
          )}
          <div
            ref={containerRef}
            className={`docx-preview-container flex flex-col items-center text-slate-950 ${loading || renderingDocx ? 'hidden' : ''}`}
          />
        </div>
      ) : loading ? (
        <div className="flex min-h-[20rem] items-center justify-center rounded-md border border-brand-border bg-brand-surface py-12 text-sm text-brand-text-muted">
          Rendering document preview...
        </div>
      ) : blocks.length > 0 ? (
        <div className="max-h-[30rem] overflow-y-auto">
          <div className="mx-auto min-h-[36rem] max-w-[46rem] rounded-sm bg-white px-8 py-10 font-serif text-[12px] leading-6 text-slate-950 shadow-sm ring-1 ring-slate-200 dark:bg-slate-950 dark:text-slate-100 dark:ring-slate-700 sm:px-10">
            {blocks.map(renderBlock)}
          </div>
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-brand-border bg-brand-surface px-3 py-6 text-center text-sm text-brand-text-muted">
          {emptyMessage}
        </div>
      )}
    </div>
  )
}
