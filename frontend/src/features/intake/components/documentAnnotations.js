export const DEFAULT_BBOX_TYPE = 'detected_text'

export function annotationsForResult(result) {
  const direct = Array.isArray(result?.annotations) ? result.annotations : []
  const findings = Array.isArray(result?.findings) ? result.findings : []
  const directAnnotations = direct
    .map((annotation, index) => normalizeAnnotation({ ...annotation,
      finding_number: findings.findIndex(f => f.id === annotation.finding_id) + 1 || annotation.finding_number,
    }, index))
    .filter(shouldUseDefaultAnnotation)
  const derivedAnnotations = findings.flatMap((finding, index) => annotationsFromFinding(finding, index + 1))
  if (direct.length) {
    return dedupeAnnotations([...directAnnotations, ...derivedAnnotations])
  }
  return dedupeAnnotations(derivedAnnotations)
}

function annotationsFromFinding(finding, findingNumber) {
  let locations = Array.isArray(finding?.locations) ? finding.locations : []
  if (!locations.length && positiveInt(finding?.page)) {
    locations = [{
      page: finding.page,
      bbox: finding.bbox || null,
      bbox_type: finding.bbox ? DEFAULT_BBOX_TYPE : 'whole_page',
      matched_text: finding.evidence_text || '',
    }]
  }
  return locations
    .map((location, index) => {
      const page = positiveInt(location?.page)
      if (!page && !location?.resolution_state) return null
      const bbox = normalizeBBox(location)
      const annotation = {
        ...location,
        id: `${finding?.id || 'finding'}:${index}`,
        finding_id: finding?.id,
        finding_number: findingNumber,
        annotation_number: location.issue_index != null ? `${findingNumber}.${location.issue_index + 1}` : String(findingNumber),
        page,
        severity: finding?.severity || 'info',
        category: finding?.category,
        message: finding?.message,
        detail: finding?.detail,
        bbox,
        bbox_type: location?.bbox_type || location?.type || DEFAULT_BBOX_TYPE,
        reason: location?.reason,
        source_bbox: bbox ? undefined : location?.bbox,
        renderable: Boolean(bbox),
      }
      for (const key of ['matched_text', 'field', 'label']) {
        if (location?.[key] !== undefined && location?.[key] !== null) {
          annotation[key] = location[key]
        }
      }
      return shouldUseDefaultAnnotation(annotation) ? annotation : null
    })
    .filter(Boolean)
}

function normalizeAnnotation(annotation, index) {
  const bbox = annotation?.bbox ? normalizeBBox(annotation) : null
  return {
    ...annotation,
    id: annotation?.id || `${annotation?.finding_id || 'annotation'}:${index}`,
    page: positiveInt(annotation?.page),
    annotation_number: annotation.issue_index != null ? `${annotation.finding_number}.${annotation.issue_index + 1}` : String(annotation.finding_number || ''),
    severity: annotation?.severity || 'info',
    bbox,
    bbox_type: annotation?.bbox_type || DEFAULT_BBOX_TYPE,
    renderable: annotation?.renderable !== false && Boolean(bbox),
  }
}

function shouldUseDefaultAnnotation(annotation) {
  const matchedText = String(annotation?.matched_text || '').trim()
  if (matchedText) return true

  const findingId = String(annotation?.finding_id || '')
  const id = String(annotation?.id || '')
  const message = String(annotation?.message || '').toLowerCase()
  const identity = `${findingId} ${id}`.toLowerCase()
  if (identity.includes('field_missing:')) return false
  if (identity.includes('format_profile_missing')) return false
  if (annotation?.bbox_type === 'expected_zone' && (identity.includes('missing') || message.includes('not found'))) {
    return false
  }
  return true
}

function dedupeAnnotations(annotations) {
  const seen = new Set()
  const output = []
  for (const annotation of annotations) {
    const key = annotation?.id || [
      annotation?.finding_id,
      annotation?.page,
      annotation?.bbox_type,
      annotation?.matched_text,
    ].join('|')
    if (seen.has(key)) continue
    seen.add(key)
    output.push(annotation)
  }
  return output
}

function normalizeBBox(source) {
  const raw = source?.bbox
  const values = bboxValues(raw)
  if (!values) return null
  const [x, y, width, height] = values
  const pageWidth = positiveNumber(source?.page_width || source?.width)
  const pageHeight = positiveNumber(source?.page_height || source?.height)

  if (isNormalized(values)) return clampBBox(x, y, width, height)
  if (isPercentage(values)) return clampBBox(x / 100, y / 100, width / 100, height / 100)
  if (pageWidth && pageHeight) {
    return clampBBox(x / pageWidth, y / pageHeight, width / pageWidth, height / pageHeight)
  }
  return null
}

function bboxValues(raw) {
  if (Array.isArray(raw) && raw.length === 4) {
    return numericValues(raw)
  }
  if (raw && typeof raw === 'object') {
    return numericValues([raw.x, raw.y, raw.width ?? raw.w, raw.height ?? raw.h])
  }
  return null
}

function numericValues(values) {
  const output = []
  for (const value of values) {
    const numeric = Number(value)
    if (!Number.isFinite(numeric) || numeric < 0) return null
    output.push(numeric)
  }
  return output
}

function isNormalized(values) {
  const [x, y, width, height] = values
  return Math.max(...values) <= 1 && x + width <= 1.05 && y + height <= 1.05
}

function isPercentage(values) {
  const [x, y, width, height] = values
  return Math.max(...values) <= 100 && x + width <= 100.5 && y + height <= 100.5
}

function clampBBox(x, y, width, height) {
  const clampedX = clamp(x)
  const clampedY = clamp(y)
  return {
    x: round4(clampedX),
    y: round4(clampedY),
    width: round4(Math.max(0, Math.min(1 - clampedX, width))),
    height: round4(Math.max(0, Math.min(1 - clampedY, height))),
  }
}

function clamp(value) {
  return Math.max(0, Math.min(1, Number(value)))
}

function round4(value) {
  return Math.round(Number(value) * 10000) / 10000
}

function positiveInt(value) {
  const numeric = Number.parseInt(value, 10)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null
}

function positiveNumber(value) {
  const numeric = Number(value)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null
}
