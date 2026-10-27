const SEGMENTS = [
  ['pending', 'Pending', '#f59e0b'],
  ['under_review', 'Under Review', '#3b82f6'],
  ['non_compliant', 'Non-Compliant', '#f43f5e'],
  ['compliant', 'Compliant', '#10b981'],
  ['waived', 'Waived', '#64748b'],
]

export default function DocumentaryStatusBreakdown({ summary = {} }) {
  const applicable = summary.applicable ?? SEGMENTS.reduce((total, [key]) => total + (summary[key] || 0), 0)
  const format = (value) => Number(value || 0).toLocaleString('en-PH')
  const description = SEGMENTS.map(([key, label]) => `${label}: ${format(summary[key])}`).join('; ')

  return (
    <div className="space-y-3">
      <p className="text-xs text-brand-text-muted">
        Status breakdown of {format(applicable)} applicable active requirements
      </p>
      <div
        role="img"
        aria-label={`Documentary status breakdown. ${description}. Not Applicable: ${format(summary.not_applicable)} (excluded).`}
        className="flex h-7 w-full overflow-hidden rounded-md bg-slate-200 dark:bg-slate-700"
      >
        {SEGMENTS.map(([key, label, color]) => {
          const count = summary[key] || 0
          return count > 0 && applicable > 0 ? (
            <span key={key} title={`${label}: ${format(count)}`} style={{ width: `${count / applicable * 100}%`, backgroundColor: color }} />
          ) : null
        })}
      </div>
      <dl className="flex flex-wrap gap-x-6 gap-y-2 text-xs">
        {SEGMENTS.map(([key, label, color]) => (
          <div key={key} className="flex items-center gap-2">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: color }} />
            <dt>{label}</dt><dd className="font-semibold tabular-nums">{format(summary[key])}</dd>
          </div>
        ))}
        <div className="flex items-center gap-2"><dt>Not Applicable</dt><dd className="font-semibold tabular-nums">{format(summary.not_applicable)}</dd></div>
      </dl>
      <p className="text-xs text-brand-text-muted">
        N/A is excluded. Waived requirements remain applicable and do not count as compliant.
        {applicable === 0 && ' No applicable requirements: Not rated.'}
      </p>
    </div>
  )
}
