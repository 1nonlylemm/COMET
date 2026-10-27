export function GlassPanel({ children, className = '', noPadding = false }) {
  return (
    <section className={`glass-panel ${noPadding ? '' : 'p-6'} ${className}`}>
      {children}
    </section>
  )
}
