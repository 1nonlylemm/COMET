import { Fragment } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

/**
 * Breadcrumb navigation.
 *
 * @param {{ items: Array<{ label: string, to?: string, onClick?: () => void, disabled?: boolean }> }} props
 *   Each item except the last should provide either `to` (router link) or
 *   `onClick` (callback). Items without navigation render as inert context.
 *   The final item is rendered as the current page.
 */
export function Breadcrumb({ items, className = '' }) {
  if (!items?.length) return null

  return (
    <nav aria-label="Breadcrumb" className={`mb-4 ${className}`}>
      <ol className="flex flex-wrap items-center gap-1.5 text-sm text-brand-text-muted">
        {items.map((item, index) => {
          const isLast = index === items.length - 1
          const key = `${item.label}-${index}`

          return (
            <Fragment key={key}>
              <li className="inline-flex items-center">
                {isLast ? (
                  <span className="font-medium text-brand-text" aria-current="page">
                    {item.label}
                  </span>
                ) : item.disabled || (!item.to && !item.onClick) ? (
                  <span className="px-1 py-0.5 text-brand-text-muted">
                    {item.label}
                  </span>
                ) : item.to ? (
                  <Link
                    to={item.to}
                    className="rounded px-1 py-0.5 transition-colors hover:text-brand-text focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/40"
                  >
                    {item.label}
                  </Link>
                ) : (
                  <button
                    type="button"
                    onClick={item.onClick}
                    className="rounded px-1 py-0.5 transition-colors hover:text-brand-text focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/40"
                  >
                    {item.label}
                  </button>
                )}
              </li>
              {!isLast && (
                <li aria-hidden="true" className="inline-flex items-center text-brand-text-muted/60">
                  <ChevronRight className="h-3.5 w-3.5" strokeWidth={2} />
                </li>
              )}
            </Fragment>
          )
        })}
      </ol>
    </nav>
  )
}
