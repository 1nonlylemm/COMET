function validBox(box) {
  return box && ['x', 'y', 'width', 'height'].every(key => Number.isFinite(box[key]))
    && box.x >= 0 && box.y >= 0 && box.width > 0 && box.height > 0
    && box.x + box.width <= 1 && box.y + box.height <= 1
}

/** TextContent interpolation is intentionally not a verification source. */
export function resolvePdfTextAnnotations(annotations = []) {
  return annotations.map(annotation => {
    const boxes = annotation.boxes?.length ? annotation.boxes : [annotation.bbox]
    const verified = annotation.resolution_state === 'verified_box'
      && annotation.geometry_source === 'pdfplumber'
      && annotation.bbox_type !== 'whole_page' && boxes.every(validBox)
    if (verified) return { ...annotation, boxes, renderable: true }
    const page = Number(annotation.page)
    return { ...annotation, bbox: null, boxes: [], renderable: false,
      resolution_state: Number.isInteger(page) && page > 0 ? 'page_marker' : 'none' }
  })
}

/** Scroll only the PDF's own scroller; never move the review form. */
export function focusPdfFinding(container, { findingId, annotationId } = {}) {
  if (!container || !findingId) return null
  const nodes = [...container.querySelectorAll('[data-finding-id], [data-finding-ids]')]
  const target = nodes.find(node => annotationId && node.dataset.annotationId === annotationId)
    || nodes.find(node => node.dataset.findingId === findingId
      || JSON.parse(node.dataset.findingIds || '[]').includes(findingId))
  if (!target) return null
  const box = target.getBoundingClientRect(), parent = container.getBoundingClientRect()
  container.scrollTo({ top: Math.max(0, container.scrollTop + box.top - parent.top - container.clientHeight / 2 + box.height / 2), behavior: 'smooth' })
  target.focus({ preventScroll: true })
  if (!target.dataset.pulsing) {
    target.dataset.pulsing = 'true'
    target.classList.add('animate-pulse', 'ring-4', 'ring-sky-400')
    setTimeout(() => {
      delete target.dataset.pulsing
      target.classList.remove('animate-pulse', 'ring-4', 'ring-sky-400')
    }, 1200)
  }
  return target
}
