export function deadlinePosition(row, { daysRemaining, isOverdue }, now = new Date()) {
  if (row.is_resolved) return 'Closed'
  if (daysRemaining == null) return 'Timing unavailable'
  if (isOverdue) return daysRemaining < 0 ? `${Math.abs(daysRemaining)} working ${Math.abs(daysRemaining) === 1 ? 'day' : 'days'} overdue` : 'Overdue · under 1 working day'
  if (daysRemaining === 0 && new Date(row.deadline_date).toISOString().slice(0, 10) === now.toISOString().slice(0, 10)) return 'Due today'
  return `${daysRemaining} working ${daysRemaining === 1 ? 'day' : 'days'} remaining`
}

