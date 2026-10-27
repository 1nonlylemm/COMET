import { useMemo } from 'react'
import { Ban, CheckCircle2, RotateCcw, SlidersHorizontal } from 'lucide-react'
import { Button, InlineAlert } from '../../../components'

const FORMAT_PROFILE_KEYS = [
  'format_profile',
  'format_profile_version',
  'format_profile_source',
  'format_profile_source_hash',
  'format_profile_extraction',
]

function parseMetadataText(metadataText) {
  const text = metadataText?.trim() || '{}'
  try {
    const metadata = JSON.parse(text)
    if (!metadata || Array.isArray(metadata) || typeof metadata !== 'object') {
      return { error: 'Checker metadata must be a JSON object.' }
    }
    return { metadata }
  } catch {
    return { error: 'Checker metadata must be valid JSON before the format helper can read it.' }
  }
}

function countItems(value) {
  return Array.isArray(value) ? value.length : 0
}

function countVisualZones(profile) {
  return (
    countItems(profile?.signature_zones) +
    countItems(profile?.stamp_zones) +
    countItems(profile?.seal_zones) +
    countItems(profile?.logo_zones) +
    countItems(profile?.letterhead_zones)
  )
}

function countLabel(count, singular, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`
}

function formatMetadata(metadata) {
  return JSON.stringify(metadata, null, 2)
}

function removeFormatProfile(metadata) {
  return Object.fromEntries(
    Object.entries(metadata).filter(([key]) => !FORMAT_PROFILE_KEYS.includes(key)),
  )
}

function extractionSummary(extraction) {
  if (!extraction?.status) return 'Extraction: not recorded'
  const details = [`Extraction: ${extraction.status}`]
  if (extraction.page_count) details.push(`${extraction.page_count} pages`)
  if (extraction.readable_text_chars) details.push(`${extraction.readable_text_chars} chars`)
  return details.join(' | ')
}

export default function FormatProfileHelperPanel({ metadataText, onMetadataTextChange }) {
  const parsed = useMemo(() => parseMetadataText(metadataText), [metadataText])

  if (parsed.error) {
    return (
      <InlineAlert type="warning">
        {parsed.error}
      </InlineAlert>
    )
  }

  const metadata = parsed.metadata
  const profile = metadata.format_profile
  const autoExtractionDisabled = Boolean(metadata.disable_auto_format_profile)

  const updateMetadata = (nextMetadata) => {
    onMetadataTextChange(formatMetadata(nextMetadata))
  }

  const handleToggleAutoExtraction = () => {
    if (autoExtractionDisabled) {
      const nextMetadata = { ...metadata }
      delete nextMetadata.disable_auto_format_profile
      updateMetadata(nextMetadata)
      return
    }
    updateMetadata({ ...metadata, disable_auto_format_profile: true })
  }

  const handleClearFormatProfile = () => {
    updateMetadata(removeFormatProfile(metadata))
  }

  const profileStats = profile
    ? [
        countLabel(countItems(profile.required_headings), 'heading'),
        countLabel(countItems(profile.section_order), 'ordered section'),
        countLabel(countItems(profile.tables), 'table'),
        countLabel(countVisualZones(profile), 'visual zone'),
      ]
    : []

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-200">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="mt-0.5 rounded-md bg-white p-2 text-slate-600 shadow-sm dark:bg-slate-900 dark:text-slate-300">
            <SlidersHorizontal className="h-4 w-4" strokeWidth={1.5} aria-hidden="true" />
          </div>
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-semibold text-slate-900 dark:text-slate-100">Format profile</p>
              {profile ? (
                <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200">
                  Active
                </span>
              ) : (
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-200">
                  Not configured
                </span>
              )}
              {autoExtractionDisabled && (
                <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                  Profile locked
                </span>
              )}
            </div>
            {profile ? (
              <>
                <div className="flex flex-wrap gap-2 text-xs text-slate-600 dark:text-slate-300">
                  <span>{metadata.format_profile_version || 'No version'}</span>
                  <span>{metadata.format_profile_source || 'manual'}</span>
                  <span>{profile.strictness || 'standard'}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {profileStats.map((label) => (
                    <span
                      key={label}
                      className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                    >
                      {label}
                    </span>
                  ))}
                </div>
                <p className="text-xs text-slate-600 dark:text-slate-400">
                  {extractionSummary(metadata.format_profile_extraction)}
                </p>
              </>
            ) : (
              <p className="max-w-2xl text-xs text-slate-600 dark:text-slate-400">
                If this checker reference has a downloadable file, the system will try to build a local
                format profile when the profile is saved.
              </p>
            )}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {profile && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              icon={RotateCcw}
              onClick={handleClearFormatProfile}
            >
              Clear Format Profile
            </Button>
          )}
          <Button
            type="button"
            variant={autoExtractionDisabled ? 'success' : 'outline'}
            size="sm"
            icon={autoExtractionDisabled ? CheckCircle2 : Ban}
            onClick={handleToggleAutoExtraction}
          >
            {autoExtractionDisabled
              ? 'Unlock profile — allow file re-scans'
              : "Lock this profile — don't auto-update from file re-scans"}
          </Button>
        </div>
      </div>
    </div>
  )
}
