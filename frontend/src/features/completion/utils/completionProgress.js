export function getCompletionProgressLabel(project) {
  if (project?.progress_metric) {
    switch (project.progress_metric) {
      case 'delivery':
        return 'Delivery Completion %'
      case 'disbursement':
        return 'Disbursement %'
      case 'physical':
        return 'Physical Completion %'
      default:
        break
    }
  }

  switch (project?.project_kind) {
    case 'goods':
      return 'Delivery Completion %'
    case 'vehicle':
      return 'Delivery / Acceptance %'
    case 'financial_assistance':
      return 'Disbursement %'
    case 'infrastructure':
    default:
      return 'Physical Completion %'
  }
}

export function isInfrastructureProject(project) {
  if (!project) return true
  if (project.project_kind) {
    return project.project_kind === 'infrastructure'
  }
  if (project.progress_metric) {
    return project.progress_metric === 'physical'
  }
  return true
}
