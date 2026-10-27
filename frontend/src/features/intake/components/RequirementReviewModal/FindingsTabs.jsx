import { useId, useMemo, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { DEFICIENCY_CATEGORY_LABELS } from '../../../monitoring/components/workflowStatus'
import { FindingChip } from './FindingChip'
import { reviewFindingGroup, selectReviewFindings } from '../../lib/reviewFindings'

const TAB_ORDER = ['blocker', 'needs_verification', 'warning', 'advisory', 'info', 'all']

const TAB_LABELS = {
  blocker: 'Critical',
  needs_verification: 'Unverified',
  warning: 'Review Attention',
  info: 'Informational',
  all: 'All',
  advisory: 'Advisories',
}

function pickDefaultTab(counts) {
  if (counts.blocker > 0) return 'blocker'
  if (counts.needs_verification > 0) return 'needs_verification'
  if (counts.warning > 0) return 'warning'
  if (counts.advisory > 0) return 'advisory'
  if (counts.info > 0) return 'info'
  return 'all'
}

/**
 * FindingsTabs — segmented control + filtered findings list with inline citation selection.
 *
 * Supports both controlled and uncontrolled selection so existing tests and consumers continue working seamlessly.
 */
export function FindingsTabs({
  findings = [],
  selectedKeys: controlledSelectedKeys = null,
  onToggleSelect: controlledOnToggleSelect = null,
  onSelectAll: controlledOnSelectAll = null,
  onClearSelection: controlledOnClearSelection = null,
  customDeficiencies = [],
  onAddCustomDeficiency = null,
  onRemoveCustomDeficiency = null,
  onUpdateCustomDeficiency = null,
  disabled = false,
  compact = false,
  onViewFinding,
  findingReviews = {},
  onSaveFindingReview,
  savingReview = false,
}) {
  const fieldId = useId()
  const counts = useMemo(() => selectReviewFindings({ findings }).groups, [findings])
  const defaultTab = useMemo(() => pickDefaultTab(counts), [counts])
  const [activeTab, setActiveTab] = useState(defaultTab)
  const [uncontrolledKeys, setUncontrolledKeys] = useState(new Set())
  const [prevFindings, setPrevFindings] = useState(findings)

  // Use controlled state if provided, otherwise internal fallback
  const isControlled = controlledSelectedKeys !== null
  const effectiveSelectedKeys = isControlled ? controlledSelectedKeys : uncontrolledKeys

  // When the underlying findings change shape (e.g. after a checker run), re-pick default tab
  if (findings !== prevFindings) {
    setPrevFindings(findings)
    setActiveTab(defaultTab)
    if (!isControlled) {
      setUncontrolledKeys(new Set())
    }
  }

  const activeFindings = useMemo(() => {
    if (activeTab === 'all') return findings
    return (findings || []).filter((finding) => reviewFindingGroup(finding) === activeTab)
  }, [findings, activeTab])

  const handleToggle = (findingKey) => {
    if (controlledOnToggleSelect) {
      controlledOnToggleSelect(findingKey)
    } else {
      setUncontrolledKeys((prev) => {
        const next = new Set(prev)
        if (next.has(findingKey)) {
          next.delete(findingKey)
        } else {
          next.add(findingKey)
        }
        return next
      })
    }
  }

  const handleSelectAll = () => {
    const eligible = activeFindings.filter(finding => findingReviews[finding.id]?.status !== 'incorrect_flag')
    if (controlledOnSelectAll) {
      controlledOnSelectAll(eligible)
    } else {
      setUncontrolledKeys((prev) => {
        const next = new Set(prev)
        eligible.forEach((f) => {
          const key = f.id || f.message
          next.add(key)
        })
        return next
      })
    }
  }

  const handleClear = () => {
    if (controlledOnClearSelection) {
      controlledOnClearSelection()
    } else {
      setUncontrolledKeys(new Set())
    }
  }

  const allEmpty = counts.all === 0
  const totalSelectedCount = effectiveSelectedKeys.size + (customDeficiencies?.length || 0)

  return (
    <section data-testid="findings-tabs" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div
          role="tablist"
          aria-label="Findings by severity"
          onKeyDown={(event) => {
            const tabs = [...event.currentTarget.querySelectorAll('[role="tab"]:not(:disabled)')]
            const index = tabs.indexOf(document.activeElement)
            let next
            if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
            if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length
            if (event.key === 'Home') next = 0
            if (event.key === 'End') next = tabs.length - 1
            if (next !== undefined && tabs[next]) {
              event.preventDefault()
              tabs[next].focus()
              tabs[next].click()
            }
          }}
          className="inline-flex max-w-full flex-wrap gap-1 rounded-lg bg-brand-surface-solid p-1"
        >
          {TAB_ORDER.filter((tab) => !compact || counts[tab] > 0 || tab === 'all').map((tab) => {
            const isActive = activeTab === tab
            const count = counts[tab] || 0
            const tabDisabled = tab !== 'all' && count === 0
            return (
              <button
                key={tab}
                role="tab"
                aria-selected={isActive}
                aria-controls={`findings-tabpanel-${tab}`}
                id={`findings-tab-${tab}`}
                data-testid={`findings-tab-${tab}`}
                type="button"
                disabled={tabDisabled}
                tabIndex={isActive ? 0 : -1}
                onClick={() => setActiveTab(tab)}
                className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-brand-primary text-white shadow-sm dark:text-slate-950'
                    : tabDisabled
                      ? 'cursor-not-allowed text-brand-text-muted/50'
                      : 'text-brand-text-muted hover:bg-brand-surface hover:text-brand-text'
                }`}
                aria-label={`${compact && tab === 'needs_verification' ? 'Needs verification' : TAB_LABELS[tab]} (${count})`}
              >
                {compact && tab === 'needs_verification' ? 'Needs verification' : TAB_LABELS[tab]}
                <span className={`tabular-nums ${isActive ? 'text-white/80 dark:text-slate-950/80' : ''}`}>({count})</span>
              </button>
            )
          })}
        </div>

        {findings.length > 0 && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={disabled}
              onClick={handleSelectAll}
              className="text-[11px] font-medium text-brand-primary hover:underline disabled:opacity-50"
            >
              Select All in Tab
            </button>
            {effectiveSelectedKeys.size > 0 && (
              <>
                <span className="text-brand-text-muted">·</span>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={handleClear}
                  className="text-[11px] font-medium text-brand-text-muted hover:underline disabled:opacity-50"
                >
                  Clear Selection
                </button>
              </>
            )}
            {totalSelectedCount > 0 && (
              <span className="inline-flex items-center rounded-md border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                {totalSelectedCount} selected for return
              </span>
            )}
          </div>
        )}
      </div>

      <div
        id={`findings-tabpanel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`findings-tab-${activeTab}`}
        className="space-y-2"
      >
        {allEmpty ? (
          <div className="rounded-md border border-dashed border-brand-border bg-brand-surface-solid px-3 py-4 text-center text-xs text-brand-text-muted">
            {compact ? 'No automated findings listed. Inspect the document and evidence checks before deciding.' : 'No deterministic issues detected. A reviewer should still confirm before approval.'}
          </div>
        ) : (
          activeFindings.map((finding) => {
            const key = finding.id || finding.message
            return (
              <FindingChip
                key={key}
                finding={finding}
                findingNumber={findings.indexOf(finding) + 1}
                selectable={true}
                selected={effectiveSelectedKeys.has(key)}
                onToggleSelect={() => handleToggle(key)}
                disabled={disabled}
                compact={compact}
                onViewFinding={onViewFinding}
                review={findingReviews[key]}
                onSaveReview={onSaveFindingReview}
                savingReview={savingReview}
              />
            )
          })
        )}
      </div>

      {/* Inline Custom Deficiency Section */}
      {onAddCustomDeficiency && (
        <div className="pt-2">
          {customDeficiencies.length > 0 && (
            <div className="space-y-3 mb-3">
              <div className="text-xs font-semibold uppercase tracking-wider text-brand-text-muted">
                Custom Deficiency Citations ({customDeficiencies.length})
              </div>
              {customDeficiencies.map((item, idx) => (
                <div
                  key={idx}
                  className="rounded-lg border border-amber-300 bg-amber-50/40 p-3.5 space-y-2.5 dark:border-amber-800/40 dark:bg-amber-950/20"
                >
                  <div className="flex items-center justify-between border-b border-brand-border/60 pb-1.5">
                    <span className="text-xs font-semibold text-brand-text">
                      Custom Deficiency #{idx + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() => onRemoveCustomDeficiency(idx)}
                      className="flex items-center gap-1 text-xs text-rose-600 hover:text-rose-700 dark:text-rose-400"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      <span>Remove</span>
                    </button>
                  </div>

                  <div>
                    <label htmlFor={`${fieldId}-category-${idx}`} className="block text-xs font-medium text-brand-text-muted mb-1">
                      Deficiency Category *
                    </label>
                    <select
                      id={`${fieldId}-category-${idx}`}
                      className="input-field w-full text-xs"
                      value={item.category}
                      onChange={(e) => onUpdateCustomDeficiency(idx, 'category', e.target.value)}
                      disabled={disabled}
                    >
                      {Object.entries(DEFICIENCY_CATEGORY_LABELS).map(([catKey, label]) => (
                        <option key={catKey} value={catKey}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label htmlFor={`${fieldId}-observation-${idx}`} className="block text-xs font-medium text-brand-text-muted mb-1">
                      Finding / Observation *
                    </label>
                    <textarea
                      id={`${fieldId}-observation-${idx}`}
                      rows={2}
                      className="input-field w-full text-xs"
                      placeholder="Specify the discrete observed defect..."
                      value={item.finding_observation}
                      onChange={(e) => onUpdateCustomDeficiency(idx, 'finding_observation', e.target.value)}
                      disabled={disabled}
                    />
                  </div>

                  <div>
                    <label htmlFor={`${fieldId}-instruction-${idx}`} className="block text-xs font-medium text-brand-text-muted mb-1">
                      Corrective Action Required *
                    </label>
                    <textarea
                      id={`${fieldId}-instruction-${idx}`}
                      rows={2}
                      className="input-field w-full text-xs"
                      placeholder="Specify the exact corrective action required before resubmission..."
                      value={item.corrective_instruction}
                      onChange={(e) => onUpdateCustomDeficiency(idx, 'corrective_instruction', e.target.value)}
                      disabled={disabled}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}

          <button
            type="button"
            onClick={onAddCustomDeficiency}
            disabled={disabled}
            className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-brand-border bg-brand-surface px-3 py-1.5 text-xs font-medium text-brand-text-muted hover:border-brand-primary hover:text-brand-primary transition-colors disabled:opacity-50"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Add Custom Deficiency Item</span>
          </button>
        </div>
      )}
    </section>
  )
}

export default FindingsTabs
