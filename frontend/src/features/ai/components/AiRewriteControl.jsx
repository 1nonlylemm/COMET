import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { Button } from '../../../components'
import { rewriteText } from '../api/aiApi'

const MODES = [
  { value: 'polish', label: 'Polish' },
  { value: 'formal', label: 'Formal' },
  { value: 'concise', label: 'Concise' },
  { value: 'expand', label: 'Longer' },
  { value: 'paraphrase', label: 'Paraphrase' },
]

export function AiRewriteControl({
  value,
  onTextChange,
  contextLabel = 'workspace note',
  disabled = false,
  className = '',
  label = 'AI Note',
  placeholder = '',
  rows = 3,
  autoFocus = false,
  children
}) {
  const [mode, setMode] = useState('polish')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleRewrite() {
    const text = String(value || '').trim()
    if (!text) {
      setError('Add text before using AI rewrite.')
      return
    }

    setLoading(true)
    setError('')
    try {
      const response = await rewriteText({
        text,
        mode,
        context_label: contextLabel,
      })
      const rewritten = response.data?.rewritten_text
      if (rewritten) {
        onTextChange(rewritten)
      } else {
        setError('AI rewrite did not return text.')
      }
    } catch (err) {
      setError(err.response?.data?.message || 'AI rewrite is unavailable right now.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={`rounded-xl border border-brand-border bg-brand-surface overflow-hidden transition-all focus-within:ring-2 focus-within:ring-brand-primary focus-within:border-brand-primary ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-50/50 dark:bg-slate-800/50 border-b border-brand-border p-3">
        <label className="text-xs font-bold tracking-wider uppercase text-slate-600 dark:text-slate-400">
          {label}
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="input-field min-h-9 h-9 !py-0 w-auto min-w-[120px] text-sm !border-slate-300 dark:!border-slate-600 focus:!ring-brand-primary"
            value={mode}
            onChange={(event) => setMode(event.target.value)}
            disabled={disabled || loading}
            aria-label="AI rewrite style"
            title="AI rewrite style"
          >
            {MODES.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
          <Button
            size="sm"
            variant="outline"
            className="h-9 font-medium"
            icon={Sparkles}
            loading={loading}
            disabled={disabled || loading || !String(value || '').trim()}
            onClick={handleRewrite}
            title="Rewrite with AI"
          >
            AI Rewrite
          </Button>
        </div>
      </div>

      <div className="relative">
        <textarea
          value={value || ''}
          onChange={(e) => onTextChange(e.target.value)}
          disabled={disabled || loading}
          placeholder={placeholder}
          rows={rows}
          autoFocus={autoFocus}
          className="w-full resize-y border-0 bg-transparent p-4 text-sm text-brand-text placeholder:text-slate-600 dark:placeholder:text-slate-400 focus:outline-none focus:ring-0 disabled:opacity-50 min-h-[96px]"
        />
        {error && (
          <div className="border-t border-red-200 bg-red-50 px-4 py-2 text-xs font-medium text-red-700 dark:border-red-900/60 dark:bg-red-900/30 dark:text-red-200">
            {error}
          </div>
        )}
      </div>

      {children && (
        <div className="flex items-center justify-end gap-3 p-3">
          {children}
        </div>
      )}
    </div>
  )
}
