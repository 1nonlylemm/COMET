export function PageHeader({
  eyebrow,
  title,
  titleExtra,
  description,
  actions,
  meta,
  className = '',
}) {
  return (
    <header className={`mb-6 flex flex-col gap-4 border-b border-brand-border pb-5 lg:flex-row lg:items-end lg:justify-between ${className}`}>
      <div className="min-w-0">
        {eyebrow && <p className="micro-text mb-2">{eyebrow}</p>}
        <div className="flex items-center gap-2">
          <h1 className="page-title">{title}</h1>
          {titleExtra}
        </div>
        {description && <p className="mt-2 max-w-3xl text-sm leading-6 text-brand-text-muted">{description}</p>}
        {meta && <div className="mt-3 flex flex-wrap items-center gap-2">{meta}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 lg:justify-end">{actions}</div>}
    </header>
  )
}
