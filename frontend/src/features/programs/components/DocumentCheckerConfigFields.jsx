import { useState } from 'react'
import { Plus, X, ShieldCheck, FileCheck, Calendar, Award, PenTool } from 'lucide-react'
import { Button } from '../../../components'
import { STANDARD_SIGNATORY_ROLES, defaultCheckerConfig } from './checkerConfigDefaults'

export function DocumentCheckerConfigFields({ value, onChange }) {
  const config = { ...defaultCheckerConfig(), ...(value || {}) }

  const [newCustomRole, setNewCustomRole] = useState('')
  const [newCertPhrase, setNewCertPhrase] = useState('')
  const [newRequiredPhrase, setNewRequiredPhrase] = useState('')

  const updateConfig = (updates) => {
    onChange?.({ ...config, ...updates })
  }

  const handleRoleToggle = (roleKey) => {
    const currentRoles = new Set(config.signatory_roles || [])
    if (currentRoles.has(roleKey)) {
      currentRoles.delete(roleKey)
    } else {
      currentRoles.add(roleKey)
    }
    updateConfig({ signatory_roles: Array.from(currentRoles) })
  }

  const handleAddCustomRole = (e) => {
    e?.preventDefault?.()
    const trimmed = newCustomRole.trim()
    if (!trimmed) return
    const currentCustom = config.custom_signatory_roles || []
    if (!currentCustom.includes(trimmed)) {
      updateConfig({ custom_signatory_roles: [...currentCustom, trimmed] })
    }
    setNewCustomRole('')
  }

  const handleRemoveCustomRole = (roleToRemove) => {
    const updated = (config.custom_signatory_roles || []).filter((r) => r !== roleToRemove)
    updateConfig({ custom_signatory_roles: updated })
  }

  const handleAddCertPhrase = (e) => {
    e?.preventDefault?.()
    const trimmed = newCertPhrase.trim()
    if (!trimmed) return
    const current = config.certification_phrases || []
    if (!current.includes(trimmed)) {
      updateConfig({ certification_phrases: [...current, trimmed] })
    }
    setNewCertPhrase('')
  }

  const handleRemoveCertPhrase = (phraseToRemove) => {
    const updated = (config.certification_phrases || []).filter((p) => p !== phraseToRemove)
    updateConfig({ certification_phrases: updated })
  }

  const handleAddRequiredPhrase = (e) => {
    e?.preventDefault?.()
    const trimmed = newRequiredPhrase.trim()
    if (!trimmed) return
    const current = config.required_phrases || []
    if (!current.includes(trimmed)) {
      updateConfig({ required_phrases: [...current, trimmed] })
    }
    setNewRequiredPhrase('')
  }

  const handleRemoveRequiredPhrase = (phraseToRemove) => {
    const updated = (config.required_phrases || []).filter((p) => p !== phraseToRemove)
    updateConfig({ required_phrases: updated })
  }

  return (
    <div
      data-testid="document-checker-config"
      className="space-y-4 rounded-xl border border-brand-border/80 bg-slate-50/60 p-4 dark:border-slate-800 dark:bg-slate-900/40"
    >
      <div className="flex items-center gap-2 border-b border-brand-border/60 pb-2">
        <ShieldCheck className="h-4 w-4 text-brand-primary" />
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-brand-text">
            Document Checker Evidence Requirements
          </h4>
          <p className="text-[11px] text-brand-text-muted">
            Configure automated evidence verification expectations. Unchecked categories are not required.
          </p>
        </div>
      </div>

      {/* 1. Signatories */}
      <div className="space-y-3 rounded-lg border border-brand-border/50 bg-white p-3 dark:border-slate-800 dark:bg-slate-900/80">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            data-testid="toggle-requires-signatories"
            checked={Boolean(config.requires_signatories)}
            onChange={(e) => updateConfig({ requires_signatories: e.target.checked })}
            className="rounded border-slate-300 bg-white text-brand-primary focus:ring-brand-primary dark:border-slate-600 dark:bg-slate-800"
          />
          <PenTool className="h-3.5 w-3.5 text-brand-primary" />
          <span className="text-xs font-medium text-brand-text">Signatories required</span>
        </label>

        {config.requires_signatories && (
          <div className="ml-6 space-y-3 pt-1" data-testid="signatories-suboptions">
            <div className="text-[11px] font-medium text-brand-text-muted">Standard signatory roles:</div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {STANDARD_SIGNATORY_ROLES.map((role) => {
                const isChecked = (config.signatory_roles || []).includes(role.key)
                return (
                  <label
                    key={role.key}
                    data-testid={`checkbox-role-${role.key}`}
                    className="flex items-center gap-2 text-xs text-brand-text cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => handleRoleToggle(role.key)}
                      className="rounded border-slate-300 text-brand-primary focus:ring-brand-primary dark:border-slate-600 dark:bg-slate-800"
                    />
                    <span>{role.label}</span>
                  </label>
                )
              })}
            </div>

            {/* Custom Signatory Roles */}
            <div className="pt-2">
              <div className="text-[11px] font-medium text-brand-text-muted">Custom signatory roles:</div>
              <div className="mt-1 flex gap-2">
                <input
                  type="text"
                  data-testid="input-custom-signatory"
                  value={newCustomRole}
                  onChange={(e) => setNewCustomRole(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      handleAddCustomRole()
                    }
                  }}
                  placeholder="e.g. Project Engineer, City Accountant"
                  className="input-field text-xs h-8 flex-1"
                />
                <Button
                  type="button"
                  size="xs"
                  variant="outline"
                  icon={Plus}
                  data-testid="btn-add-custom-signatory"
                  onClick={handleAddCustomRole}
                >
                  Add Role
                </Button>
              </div>

              {(config.custom_signatory_roles || []).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5" data-testid="custom-signatories-chips">
                  {config.custom_signatory_roles.map((customRole) => (
                    <span
                      key={customRole}
                      className="inline-flex items-center gap-1 rounded-md bg-brand-surface-solid px-2 py-0.5 text-xs text-brand-text border border-brand-border/60"
                    >
                      {customRole}
                      <button
                        type="button"
                        aria-label={`Remove ${customRole}`}
                        onClick={() => handleRemoveCustomRole(customRole)}
                        className="text-brand-text-muted hover:text-rose-500"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* 2. Certification */}
      <div className="space-y-3 rounded-lg border border-brand-border/50 bg-white p-3 dark:border-slate-800 dark:bg-slate-900/80">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            data-testid="toggle-requires-certification"
            checked={Boolean(config.requires_certification)}
            onChange={(e) => updateConfig({ requires_certification: e.target.checked })}
            className="rounded border-slate-300 bg-white text-brand-primary focus:ring-brand-primary dark:border-slate-600 dark:bg-slate-800"
          />
          <Award className="h-3.5 w-3.5 text-brand-primary" />
          <span className="text-xs font-medium text-brand-text">Certified True Copy / certification required</span>
        </label>

        {config.requires_certification && (
          <div className="ml-6 space-y-2 pt-1" data-testid="certification-suboptions">
            <p className="text-[11px] text-brand-text-muted">
              Automatically checks for standard marks (e.g. "Certified True Copy", "Certified Correct").
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                data-testid="input-custom-cert-phrase"
                value={newCertPhrase}
                onChange={(e) => setNewCertPhrase(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleAddCertPhrase()
                  }
                }}
                placeholder="Optional custom phrase (e.g. Katunayan)"
                className="input-field text-xs h-8 flex-1"
              />
              <Button
                type="button"
                size="xs"
                variant="outline"
                icon={Plus}
                data-testid="btn-add-cert-phrase"
                onClick={handleAddCertPhrase}
              >
                Add Phrase
              </Button>
            </div>

            {(config.certification_phrases || []).length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {config.certification_phrases.map((phrase) => (
                  <span
                    key={phrase}
                    className="inline-flex items-center gap-1 rounded-md bg-brand-surface-solid px-2 py-0.5 text-xs text-brand-text border border-brand-border/60"
                  >
                    {phrase}
                    <button
                      type="button"
                      aria-label={`Remove phrase ${phrase}`}
                      onClick={() => handleRemoveCertPhrase(phrase)}
                      className="text-brand-text-muted hover:text-rose-500"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 3. Notarization */}
      <div className="space-y-1 rounded-lg border border-brand-border/50 bg-white p-3 dark:border-slate-800 dark:bg-slate-900/80">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            data-testid="toggle-requires-notarization"
            checked={Boolean(config.requires_notarization)}
            onChange={(e) => updateConfig({ requires_notarization: e.target.checked })}
            className="rounded border-slate-300 bg-white text-brand-primary focus:ring-brand-primary dark:border-slate-600 dark:bg-slate-800"
          />
          <FileCheck className="h-3.5 w-3.5 text-brand-primary" />
          <span className="text-xs font-medium text-brand-text">Notarization required</span>
        </label>
        <p className="ml-6 text-[11px] text-brand-text-muted">
          Automatically verifies legal jurat and Notary Public block (Doc No., Page No., Book No., Series) without manual typing.
        </p>
      </div>

      {/* 4. Date */}
      <div className="space-y-1 rounded-lg border border-brand-border/50 bg-white p-3 dark:border-slate-800 dark:bg-slate-900/80">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            data-testid="toggle-requires-date"
            checked={Boolean(config.requires_date)}
            onChange={(e) => updateConfig({ requires_date: e.target.checked })}
            className="rounded border-slate-300 bg-white text-brand-primary focus:ring-brand-primary dark:border-slate-600 dark:bg-slate-800"
          />
          <Calendar className="h-3.5 w-3.5 text-brand-primary" />
          <span className="text-xs font-medium text-brand-text">Date required</span>
        </label>
        <p className="ml-6 text-[11px] text-brand-text-muted">
          Verifies that the document contains an identifiable date (e.g. Month Day, Year).
        </p>
      </div>

      {/* 5. Required Phrases */}
      <div className="space-y-2 rounded-lg border border-brand-border/50 bg-white p-3 dark:border-slate-800 dark:bg-slate-900/80">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-brand-text">Required phrases</span>
        </div>
        <p className="text-[11px] text-brand-text-muted">
          Specify exact textual phrases or references that must be present in the document.
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            data-testid="input-required-phrase"
            value={newRequiredPhrase}
            onChange={(e) => setNewRequiredPhrase(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                handleAddRequiredPhrase()
              }
            }}
            placeholder="e.g. Sangguniang Bayan, Resolution No."
            className="input-field text-xs h-8 flex-1"
          />
          <Button
            type="button"
            size="xs"
            variant="outline"
            icon={Plus}
            data-testid="btn-add-required-phrase"
            onClick={handleAddRequiredPhrase}
          >
            Add Phrase
          </Button>
        </div>

        {(config.required_phrases || []).length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1" data-testid="required-phrases-chips">
            {config.required_phrases.map((phrase) => (
              <span
                key={phrase}
                className="inline-flex items-center gap-1 rounded-md bg-brand-surface-solid px-2 py-0.5 text-xs text-brand-text border border-brand-border/60"
              >
                {phrase}
                <button
                  type="button"
                  aria-label={`Remove phrase ${phrase}`}
                  onClick={() => handleRemoveRequiredPhrase(phrase)}
                  className="text-brand-text-muted hover:text-rose-500"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
