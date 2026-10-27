import { ChevronRight } from 'lucide-react'

/**
 * DetailsAccordion — progressive-disclosure container.
 *
 * Renders each section as a native <details>/<summary> so keyboard navigation
 * is built in. Sections are collapsed by default each time the parent mounts.
 *
 * Each section in the `sections` prop is:
 *   { id, label, content, count?, icon?, defaultOpen? }
 */
export function DetailsAccordion({ sections = [] }) {
  if (!sections.length) return null
  return (
    <div data-testid="details-accordion" className="overflow-hidden rounded-xl border border-brand-border bg-brand-surface">
      {sections.map((section, index) => {
        const Icon = section.icon
        return (
          <details
            key={section.id}
            data-testid={`details-section-${section.id}`}
            open={Boolean(section.defaultOpen)}
            className={`group ${index !== 0 ? 'border-t border-brand-border' : ''}`}
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-medium text-brand-text hover:bg-brand-surface-solid focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/35">
              <span className="flex items-center gap-2 text-left">
                {Icon && <Icon className="h-4 w-4 text-brand-text-muted" strokeWidth={1.7} />}
                <span>{section.label}</span>
                {Number.isFinite(Number(section.count)) && Number(section.count) > 0 && (
                  <span className="inline-flex items-center rounded-full border border-brand-border bg-brand-surface-solid px-1.5 py-0.5 text-[10px] font-medium text-brand-text-muted">
                    {section.count}
                  </span>
                )}
              </span>
              <ChevronRight className="h-4 w-4 shrink-0 text-brand-text-muted transition-transform duration-200 group-open:rotate-90" strokeWidth={1.7} />
            </summary>
            <div className="border-t border-brand-border bg-brand-surface-solid px-4 py-4">
              {section.content}
            </div>
          </details>
        )
      })}
    </div>
  )
}

export default DetailsAccordion
