import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowUpRight, Loader2, Search, X } from 'lucide-react'
import { useFiscalYear } from '../../../context/useFiscalYear'
import { searchWorkspace } from '../api/searchApi'


const MIN_QUERY_LENGTH = 2


export function GlobalSearch() {
  const [query, setQuery] = useState('')
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)
  const requestIdRef = useRef(0)
  const navigate = useNavigate()
  const { selectedFiscalYear } = useFiscalYear()
  const trimmedQuery = query.trim()

  useEffect(() => {
    if (trimmedQuery.length < MIN_QUERY_LENGTH) {
      setPayload(null)
      setError('')
      setLoading(false)
      return undefined
    }

    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    setLoading(true)
    setError('')
    const timeoutId = window.setTimeout(async () => {
      try {
        const response = await searchWorkspace({
          q: trimmedQuery,
          per_type: 4,
          fiscal_year: selectedFiscalYear || undefined,
        })
        if (requestIdRef.current !== requestId) return
        setPayload(response.data || null)
        setOpen(true)
      } catch (err) {
        if (requestIdRef.current !== requestId) return
        setError(err.response?.data?.message || 'Search failed.')
        setPayload(null)
      } finally {
        if (requestIdRef.current === requestId) {
          setLoading(false)
        }
      }
    }, 280)

    return () => window.clearTimeout(timeoutId)
  }, [selectedFiscalYear, trimmedQuery])

  const groups = useMemo(
    () => (payload?.groups || []).filter((group) => (group.items || []).length > 0),
    [payload],
  )

  const clearSearch = () => {
    setQuery('')
    setPayload(null)
    setError('')
    setOpen(false)
  }

  const openResult = (url) => {
    if (!url) return
    clearSearch()
    navigate(url)
  }

  return (
    <div className="relative">
      <div className="flex items-center gap-2 rounded-lg border border-brand-border bg-brand-surface-solid px-3 py-2 shadow-sm">
        <Search strokeWidth={1.7} className="h-4 w-4 shrink-0 text-brand-text-muted" />
        <input
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          className="min-h-9 w-full bg-transparent text-sm text-brand-text outline-none placeholder:text-brand-text-muted"
          placeholder="Search projects, LGUs, status, requirements"
          aria-label="Global search"
        />
        {loading && <Loader2 strokeWidth={1.7} className="h-4 w-4 shrink-0 animate-spin text-brand-text-muted" />}
        {query && (
          <button
            type="button"
            onClick={clearSearch}
            className="icon-button min-h-8 min-w-8 border-0"
            aria-label="Clear search"
          >
            <X strokeWidth={1.7} className="h-4 w-4" />
          </button>
        )}
      </div>

      {open && trimmedQuery.length >= MIN_QUERY_LENGTH && (
        <div className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-40 overflow-hidden rounded-lg border border-brand-border bg-brand-surface-solid shadow-lg">
          {error ? (
            <div className="px-4 py-3 text-sm text-brand-danger">{error}</div>
          ) : groups.length ? (
            <div className="max-h-[26rem] overflow-y-auto py-2">
              {groups.map((group) => (
                <section key={group.type} className="py-1">
                  <div className="flex items-center justify-between px-4 py-2">
                    <span className="micro-text">{group.label}</span>
                    <span className="text-xs text-brand-text-muted">{group.total}</span>
                  </div>
                  <div>
                    {group.items.map((item) => (
                      <button
                        key={`${item.type}-${item.id}-${item.title}`}
                        type="button"
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => openResult(item.url)}
                        className="flex w-full items-center gap-3 px-4 py-2 text-left text-sm transition-colors hover:bg-brand-surface focus:bg-brand-surface focus:outline-none"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="truncate font-medium text-brand-text">{item.title}</div>
                          {item.subtitle && (
                            <div className="mt-0.5 truncate text-xs text-brand-text-muted">{item.subtitle}</div>
                          )}
                        </div>
                        <ArrowUpRight strokeWidth={1.7} className="h-4 w-4 shrink-0 text-brand-text-muted" />
                      </button>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          ) : loading ? (
            <div className="px-4 py-3 text-sm text-brand-text-muted">Searching...</div>
          ) : (
            <div className="px-4 py-3 text-sm text-brand-text-muted">No matching records found.</div>
          )}
        </div>
      )}
    </div>
  )
}
