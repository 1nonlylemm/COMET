export const PROJECT_STATUS_OPTIONS = [
  { value: 'not_yet_started', label: 'Not Yet Started' },
  { value: 'ongoing', label: 'Ongoing' },
  { value: 'completed', label: 'Completed' },
  { value: 'cancelled', label: 'Cancelled' },
]

export const PROJECT_STATUS_BADGE = Object.fromEntries(
  PROJECT_STATUS_OPTIONS.map((item) => [item.value, { label: item.label }]),
)

export const PROJECT_STATUS_FILTERS = [
  { value: '', label: 'All Statuses' },
  ...PROJECT_STATUS_OPTIONS,
]

