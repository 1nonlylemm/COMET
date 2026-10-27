import api from '../../../lib/api'

export function getMonitoringUpdatesReport(params = {}) {
  return api.get('/reports/monitoring-updates', { params }).then((res) => res.data)
}

export function getDeepDiveAnalytics(params = {}) {
  return api.get('/reports/analytics/deep-dive', { params }).then((res) => res.data)
}

export function exportMonitoringUpdatesPdf(config = {}) {
  return api.post('/reports/monitoring-updates/export-pdf', config, {
    responseType: 'blob',
  })
}

export function getCheckerEvaluationSummary(params = {}) {
  return api.get('/document-checker/evaluation/summary', { params }).then((res) => res.data)
}

export function getCheckerEvaluationTrends(params = {}) {
  return api.get('/document-checker/evaluation/trends', { params }).then((res) => res.data)
}

export function getCheckerReviewerFeedback(params = {}) {
  return api.get('/document-checker/evaluation/reviewer-feedback', { params }).then((res) => res.data)
}

export function listCheckerReleasedReports(params = {}) {
  return api.get('/document-checker/evaluation/released-reports', { params }).then((res) => res.data)
}

export function listCheckerEvaluationRuns(params = {}) {
  return api.get('/document-checker/evaluation/runs', { params }).then((res) => res.data)
}

export function getCheckerRunReport(id) {
  return api.get(`/document-checker/evaluation/runs/${id}/report`).then((res) => res.data)
}
