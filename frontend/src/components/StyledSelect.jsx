import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, Search, X } from 'lucide-react'

/**
 * StyledSelect - A custom, accessible dropdown component that replaces
 * native browser select elements with a consistent COMET design-system dropdown.
 */
export function StyledSelect({
  id,
  value,
  onChange,
  options = [],
  placeholder = 'Select option...',
  disabled = false,
  searchable = false,
  clearable = false,
  className = '',
  size = 'md',
  error = false,
  'aria-label': ariaLabel,
  'aria-describedby': ariaDescribedby,
  ...restProps
}) {
  const generatedId = useId()
  const selectId = id || generatedId
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [activeIndex, setActiveIndex] = useState(-1)
  const containerRef = useRef(null)
  const searchInputRef = useRef(null)
  const listRef = useRef(null)

  // Normalize string/number value comparison
  const selectedOption = useMemo(() => {
    if (value === undefined || value === null) return null
    return options.find((opt) => String(opt.value) === String(value)) || null
  }, [options, value])

  const filteredOptions = useMemo(() => {
    if (!search.trim()) return options
    const query = search.toLowerCase()
    return options.filter(
      (opt) =>
        opt.label?.toLowerCase().includes(query) ||
        String(opt.value).toLowerCase().includes(query),
    )
  }, [options, search])

  // Close on click outside or escape
  useEffect(() => {
    if (!open) return undefined

    const handlePointerDown = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false)
      }
    }

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setOpen(false)
      }
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  // Auto-focus search input when opening
  useEffect(() => {
    if (open && searchable && searchInputRef.current) {
      searchInputRef.current.focus()
    }
  }, [open, searchable])

  const handleSelect = (optionValue) => {
    // Dispatch standard synthetic event-compatible shape
    const syntheticEvent = {
      target: { id: selectId, name: selectId, value: optionValue },
      currentTarget: { id: selectId, name: selectId, value: optionValue },
    }
    onChange?.(syntheticEvent)
    setOpen(false)
    setSearch('')
  }

  const handleClear = (event) => {
    event.stopPropagation()
    handleSelect('')
  }

  const handleKeyDown = (event) => {
    if (disabled) return

    if (!open) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) {
        event.preventDefault()
        setOpen(true)
      }
      return
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((prev) =>
        prev < filteredOptions.length - 1 ? prev + 1 : 0,
      )
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((prev) =>
        prev > 0 ? prev - 1 : filteredOptions.length - 1,
      )
    } else if (event.key === 'Enter') {
      event.preventDefault()
      if (activeIndex >= 0 && activeIndex < filteredOptions.length) {
        handleSelect(filteredOptions[activeIndex].value)
      }
    }
  }

  const sizeStyles =
    size === 'sm'
      ? 'min-h-[34px] px-2.5 py-1.5 text-xs'
      : 'min-h-[40px] px-3 py-2 text-sm'

  return (
    <div
      ref={containerRef}
      className={`relative inline-block w-full text-left ${className}`}
      onKeyDown={handleKeyDown}
      {...restProps}
    >
      <button
        id={selectId}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        aria-describedby={ariaDescribedby}
        onClick={() => setOpen((prev) => !prev)}
        className={`flex w-full items-center justify-between gap-2 rounded-md border bg-white text-left font-normal transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/20 dark:bg-slate-900 ${sizeStyles} ${
          error
            ? 'border-red-600 focus-visible:border-red-600 dark:border-red-400'
            : 'border-brand-border hover:border-slate-400 focus-visible:border-brand-primary'
        } ${disabled ? 'cursor-not-allowed opacity-60 bg-slate-100 dark:bg-slate-800' : 'cursor-pointer'}`}
      >
        <span
          className={`block truncate ${
            selectedOption ? 'text-brand-text' : 'text-brand-text-muted'
          }`}
        >
          {selectedOption ? selectedOption.label : placeholder}
        </span>

        <div className="flex shrink-0 items-center gap-1">
          {clearable && selectedOption && !disabled && (
            <span
              role="button"
              tabIndex={0}
              onClick={handleClear}
              className="rounded p-0.5 text-brand-text-muted hover:bg-slate-100 hover:text-brand-text dark:hover:bg-slate-800"
              aria-label="Clear selection"
            >
              <X className="h-3.5 w-3.5" />
            </span>
          )}
          <ChevronDown
            className={`h-4 w-4 text-brand-text-muted transition-transform duration-200 ${
              open ? 'rotate-180 text-brand-primary dark:text-blue-400' : ''
            }`}
            strokeWidth={1.7}
          />
        </div>
      </button>

      {open && (
        <div
          role="listbox"
          id={`${selectId}-listbox`}
          ref={listRef}
          className="absolute z-50 mt-1 max-h-60 w-full min-w-[180px] overflow-auto rounded-md border border-brand-border bg-white py-1 shadow-lg ring-1 ring-black/5 focus:outline-none dark:bg-slate-900 dark:ring-white/10"
        >
          {searchable && (
            <div className="sticky top-0 z-10 border-b border-brand-border bg-white p-2 dark:bg-slate-900">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-brand-text-muted" />
                <input
                  ref={searchInputRef}
                  type="text"
                  className="w-full rounded border border-brand-border bg-brand-surface py-1 pl-8 pr-2 text-xs text-brand-text placeholder-brand-text-muted focus:border-brand-primary focus:outline-none"
                  placeholder="Search options..."
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value)
                    setActiveIndex(-1)
                  }}
                  onClick={(event) => event.stopPropagation()}
                />
              </div>
            </div>
          )}

          {filteredOptions.length === 0 ? (
            <div className="px-3 py-2 text-center text-xs text-brand-text-muted">
              No matching options
            </div>
          ) : (
            filteredOptions.map((opt, index) => {
              const isSelected =
                selectedOption && String(selectedOption.value) === String(opt.value)
              const isFocused = index === activeIndex

              return (
                <div
                  key={String(opt.value)}
                  role="option"
                  aria-selected={isSelected}
                  className={`flex cursor-pointer items-center justify-between px-3 py-2 text-xs transition-colors ${
                    isSelected
                      ? 'bg-brand-surface font-medium text-brand-primary dark:text-blue-400'
                      : isFocused
                        ? 'bg-slate-100 dark:bg-slate-800 text-brand-text'
                        : 'text-brand-text hover:bg-slate-50 dark:hover:bg-slate-800/60'
                  }`}
                  onClick={() => handleSelect(opt.value)}
                >
                  <span className="block truncate">{opt.label}</span>
                  {isSelected && (
                    <Check
                      className="ml-2 h-3.5 w-3.5 shrink-0 text-brand-primary dark:text-blue-400"
                      strokeWidth={2}
                    />
                  )}
                </div>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
export default StyledSelect
