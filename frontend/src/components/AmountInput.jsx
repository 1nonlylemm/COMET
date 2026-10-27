import { forwardRef, useRef, useImperativeHandle } from 'react'
import { formatAmountInput, parseAmount } from '../lib/formatters'

/**
 * AmountInput
 * Form input component that automatically formats numeric amounts with commas (thousands separators).
 *
 * Example:
 *   User inputs 10000000 -> displays "10,000,000"
 *   User inputs 10000000.5 -> displays "10,000,000.5"
 *
 * Supports cursor retention during typing, smart backspacing across commas,
 * and optional currency symbol prefix.
 */
export const AmountInput = forwardRef(function AmountInput(
  {
    id,
    name,
    value = '',
    onChange,
    onBlur,
    onKeyDown,
    placeholder = '0.00',
    disabled = false,
    readOnly = false,
    className = 'input-field',
    maxDecimals = 2,
    prefix,
    ...props
  },
  ref
) {
  const inputRef = useRef(null)
  useImperativeHandle(ref, () => inputRef.current)

  const displayValue = value === null || value === undefined ? '' : formatAmountInput(value, maxDecimals)

  const handleChange = (e) => {
    const rawValue = e.target.value
    const cursor = e.target.selectionStart ?? rawValue.length
    const beforeCursor = rawValue.slice(0, cursor)
    const digitsBeforeCursor = (beforeCursor.match(/[\d.]/g) || []).length

    const formatted = formatAmountInput(rawValue, maxDecimals)

    let newCursor = 0
    let seenDigits = 0
    for (let i = 0; i < formatted.length; i++) {
      if (/[\d.]/.test(formatted[i])) {
        seenDigits++
      }
      if (seenDigits === digitsBeforeCursor) {
        newCursor = i + 1
        break
      }
    }
    if (seenDigits < digitsBeforeCursor) {
      newCursor = formatted.length
    }

    if (onChange) {
      const customEvent = {
        ...e,
        target: {
          ...e.target,
          name: name || id,
          id,
          value: formatted,
          rawValue: formatted.replace(/,/g, ''),
          numericValue: parseAmount(formatted),
        },
      }
      onChange(customEvent)
    }

    requestAnimationFrame(() => {
      if (inputRef.current) {
        inputRef.current.setSelectionRange(newCursor, newCursor)
      }
    })
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Backspace') {
      const { selectionStart, selectionEnd, value: currentVal } = e.target
      if (selectionStart === selectionEnd && selectionStart > 0) {
        if (currentVal[selectionStart - 1] === ',') {
          e.preventDefault()
          const updated = currentVal.slice(0, selectionStart - 2) + currentVal.slice(selectionStart - 1)
          const formatted = formatAmountInput(updated, maxDecimals)

          const targetDigits = (currentVal.slice(0, selectionStart - 2).match(/[\d.]/g) || []).length
          let newCursor = 0
          let seenDigits = 0
          for (let i = 0; i < formatted.length; i++) {
            if (/[\d.]/.test(formatted[i])) {
              seenDigits++
            }
            if (seenDigits === targetDigits) {
              newCursor = i + 1
              break
            }
          }
          if (targetDigits === 0) newCursor = 0

          if (onChange) {
            onChange({
              ...e,
              target: {
                ...e.target,
                name: name || id,
                id,
                value: formatted,
                rawValue: formatted.replace(/,/g, ''),
                numericValue: parseAmount(formatted),
              },
            })
          }

          requestAnimationFrame(() => {
            if (inputRef.current) {
              inputRef.current.setSelectionRange(newCursor, newCursor)
            }
          })
          return
        }
      }
    }
    if (onKeyDown) {
      onKeyDown(e)
    }
  }

  const inputElement = (
    <input
      ref={inputRef}
      id={id}
      name={name}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      autoCorrect="off"
      spellCheck={false}
      value={displayValue}
      onChange={handleChange}
      onKeyDown={handleKeyDown}
      onBlur={onBlur}
      placeholder={placeholder}
      disabled={disabled}
      readOnly={readOnly}
      className={prefix ? `${className} pl-7` : className}
      {...props}
    />
  )

  if (prefix) {
    return (
      <div className="relative rounded-md w-full">
        <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-2.5 text-brand-text-muted text-sm font-medium">
          {prefix}
        </div>
        {inputElement}
      </div>
    )
  }

  return inputElement
})

export default AmountInput
