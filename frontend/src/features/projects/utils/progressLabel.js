export function getProgressLabel(project) {
  if (project?.project_kind) {
    switch (project.project_kind) {
      case 'goods':
        return 'Delivery Completion'
      case 'vehicle':
        return 'Delivery / Acceptance'
      case 'financial_assistance':
        return 'Disbursement'
      case 'infrastructure':
        return 'Physical Completion'
      default:
        break
    }
  }

  if (project?.progress_metric) {
    switch (project.progress_metric) {
      case 'delivery':
        return 'Delivery Completion'
      case 'disbursement':
        return 'Disbursement'
      case 'physical':
        return 'Physical Completion'
      default:
        break
    }
  }

  return 'Physical Completion'
}
