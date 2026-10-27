import api from '../../../lib/api'

export function listCheckerDatasets(params) {
  return api.get('/document-checker/evaluation/datasets', { params }).then((res) => res.data)
}

export function createCheckerDataset(data) {
  return api.post('/document-checker/evaluation/datasets', data).then((res) => res.data)
}

export function getCheckerDataset(id) {
  return api.get(`/document-checker/evaluation/datasets/${id}`).then((res) => res.data)
}

export function importCheckerDatasetManifest(data) {
  return api.post('/document-checker/evaluation/datasets/import-manifest', data).then((res) => res.data)
}

export function exportCheckerGoldLabelTemplate(data) {
  return api.post('/document-checker/evaluation/gold-label-template', data).then((res) => res.data)
}

export function exportCheckerCompletedGoldLabelSample() {
  return api.get('/document-checker/evaluation/gold-label-template/sample').then((res) => res.data)
}

export function exportCheckerGoldLabelReviewerGuide() {
  return api.get('/document-checker/evaluation/gold-label-template/reviewer-guide').then((res) => res.data)
}

export function listCheckerGoldLabelSourceResults(params) {
  return api.get('/document-checker/evaluation/gold-label-template/source-results', { params }).then((res) => res.data)
}

export function updateCheckerDatasetStatus(id, data) {
  return api.patch(`/document-checker/evaluation/datasets/${id}/status`, data).then((res) => res.data)
}

export function listCheckerRuns(params) {
  return api.get('/document-checker/evaluation/runs', { params }).then((res) => res.data)
}

export function createCheckerRun(data) {
  return api.post('/document-checker/evaluation/runs', data).then((res) => res.data)
}

export function startCheckerRun(id) {
  return api.post(`/document-checker/evaluation/runs/${id}/start`).then((res) => res.data)
}

export function releaseCheckerRunReport(id, data = {}) {
  return api.post(`/document-checker/evaluation/runs/${id}/release`, data).then((res) => res.data)
}

export function revokeCheckerRunReport(id, data = {}) {
  return api.post(`/document-checker/evaluation/runs/${id}/release/revoke`, data).then((res) => res.data)
}

export function getCheckerRun(id) {
  return api.get(`/document-checker/evaluation/runs/${id}`).then((res) => res.data)
}

export function listCheckerRunResults(id, params) {
  return api.get(`/document-checker/evaluation/runs/${id}/results`, { params }).then((res) => res.data)
}

export function getCheckerRunReport(id) {
  return api.get(`/document-checker/evaluation/runs/${id}/report`).then((res) => res.data)
}

export function listCheckerReleasedReports(params) {
  return api.get('/document-checker/evaluation/released-reports', { params }).then((res) => res.data)
}

export function getCheckerEvaluationResult(id) {
  return api.get(`/document-checker/evaluation/results/${id}`).then((res) => res.data)
}

export function getCheckerEvaluationSummary(params) {
  return api.get('/document-checker/evaluation/summary', { params }).then((res) => res.data)
}

export function getCheckerEvaluationTrends(params) {
  return api.get('/document-checker/evaluation/trends', { params }).then((res) => res.data)
}

export function getCheckerEvaluationFailures(params) {
  return api.get('/document-checker/evaluation/failures', { params }).then((res) => res.data)
}

export function getCheckerReviewerFeedback(params) {
  return api.get('/document-checker/evaluation/reviewer-feedback', { params }).then((res) => res.data)
}
