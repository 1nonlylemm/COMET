import api from '../../../lib/api'

export function listInspections(params = {}) {
  return api.get('/monitoring/inspections', { params }).then((res) => res.data)
}

export function getMonitoringWorkbench() {
  return api.get('/monitoring/workbench').then((res) => res.data)
}

export function getQaarCatalog() {
  return api.get('/monitoring/qaar/catalog').then((res) => res.data)
}

export function listQaarItemCatalog(params = {}) {
  return api.get('/monitoring/qaar/item-catalog', { params }).then((res) => res.data)
}

export function listQaarFindingCatalog(params = {}) {
  return api.get('/monitoring/qaar/finding-catalog', { params }).then((res) => res.data)
}

export function updateProjectMonitoringProfile(projectId, data) {
  return api.put(`/monitoring/projects/${projectId}/profile`, data).then((res) => res.data)
}

export function listSubaybayanVerifications(params = {}) {
  return api.get('/monitoring/subaybayan-verifications', { params }).then((res) => res.data)
}

export function upsertSubaybayanVerification(data) {
  return api.post('/monitoring/subaybayan-verifications', data).then((res) => res.data)
}

export function listManagementActions(params = {}) {
  return api.get('/monitoring/management-actions', { params }).then((res) => res.data)
}

export function upsertManagementAction(data) {
  return api.post('/monitoring/management-actions', data).then((res) => res.data)
}

export function createInspection(data) {
  return api.post('/monitoring/inspections', data).then((res) => res.data)
}

export function updateInspection(id, data) {
  return api.put(`/monitoring/inspections/${id}`, data).then((res) => res.data)
}

export function generateInspectionOutputs(id, data) {
  return api.post(`/monitoring/inspections/${id}/outputs`, data).then((res) => res.data)
}

export function downloadGeneratedOutput(id) {
  return api.get(`/monitoring/outputs/${id}/download`, {
    responseType: 'blob',
  }).then((res) => ({
    data: res.data,
    headers: res.headers,
  }))
}

// ---------------------------------------------------------------------------
// Phase 2A: Monthly Progress Report
// ---------------------------------------------------------------------------

export function listMonthlyProgressReports(params = {}) {
  return api.get('/monitoring/monthly-progress-reports', { params }).then((res) => res.data)
}

export function createMonthlyProgressReport(data) {
  const isFormData = typeof FormData !== 'undefined' && data instanceof FormData
  return api.post('/monitoring/monthly-progress-reports', data, isFormData ? {
    headers: { 'Content-Type': 'multipart/form-data' },
  } : undefined).then((res) => res.data)
}

export function updateMonthlyProgressReport(id, data) {
  return api.put(`/monitoring/monthly-progress-reports/${id}`, data).then((res) => res.data)
}

// ---------------------------------------------------------------------------
// Phase 2A: Form 3 - Justification for Project Delay
// ---------------------------------------------------------------------------

export function listForm3Requests(params = {}) {
  return api.get('/monitoring/form3-requests', { params }).then((res) => res.data)
}

export function createForm3Request(data) {
  const isFormData = typeof FormData !== 'undefined' && data instanceof FormData
  return api.post('/monitoring/form3-requests', data, isFormData ? {
    headers: { 'Content-Type': 'multipart/form-data' },
  } : undefined).then((res) => res.data)
}

export function updateForm3Request(id, data) {
  return api.put(`/monitoring/form3-requests/${id}`, data).then((res) => res.data)
}

// ---------------------------------------------------------------------------
// Phase 2A: Project Exception Report
// ---------------------------------------------------------------------------

export function listExceptionReports(params = {}) {
  return api.get('/monitoring/exception-reports', { params }).then((res) => res.data)
}

export function createExceptionReport(data) {
  const isFormData = typeof FormData !== 'undefined' && data instanceof FormData
  return api.post('/monitoring/exception-reports', data, isFormData ? {
    headers: { 'Content-Type': 'multipart/form-data' },
  } : undefined).then((res) => res.data)
}

export function updateExceptionReport(id, data) {
  return api.put(`/monitoring/exception-reports/${id}`, data).then((res) => res.data)
}

// ---------------------------------------------------------------------------
// Phase 2A: shared document workflow transitions (reused for Monthly
// Progress Report, Form 3, and Project Exception Report via their backing
// project_requirement_id)
// ---------------------------------------------------------------------------

export function getRequirementWorkflow(requirementId) {
  return api.get(`/projects/requirements/${requirementId}/workflow`).then((res) => res.data)
}

export function submitRequirementWorkflow(requirementId, data = {}) {
  return api.post(`/projects/requirements/${requirementId}/workflow/submit`, data).then((res) => res.data)
}

export function verifyRequirementWorkflow(requirementId, data = {}) {
  return api.post(`/projects/requirements/${requirementId}/workflow/verify`, data).then((res) => res.data)
}

export function staffApproveRequirementWorkflow(requirementId, data = {}) {
  return api.post(`/projects/requirements/${requirementId}/workflow/staff-approve`, data).then((res) => res.data)
}

export function provincialApproveRequirementWorkflow(requirementId, data = {}) {
  return api.post(`/projects/requirements/${requirementId}/workflow/provincial-approve`, data).then((res) => res.data)
}

export function returnRequirementWorkflow(requirementId, data = {}) {
  return api.post(`/projects/requirements/${requirementId}/workflow/return`, data).then((res) => res.data)
}

export function listRequirementDeficiencies(requirementId, params = {}) {
  return api.get(`/projects/requirements/${requirementId}/deficiencies`, { params }).then((res) => res.data)
}

export function resolveRequirementDeficiency(requirementId, deficiencyId, data = {}) {
  return api.patch(`/projects/requirements/${requirementId}/deficiencies/${deficiencyId}/resolve`, data).then((res) => res.data)
}

// ---------------------------------------------------------------------------
// Phase 2A: V&V Queue
// ---------------------------------------------------------------------------

export function listWorkflowQueue(params = {}) {
  return api.get('/monitoring/workflow-queue', { params }).then((res) => res.data)
}

export function getWorkflowQueueCounts() {
  return api.get('/monitoring/workflow-queue/counts').then((res) => res.data)
}

// ---------------------------------------------------------------------------
// Phase 2A: Management Action Report lifecycle
// ---------------------------------------------------------------------------

export function submitManagementAction(id, data = {}) {
  return api.post(`/monitoring/management-actions/${id}/submit`, data).then((res) => res.data)
}

export function acknowledgeManagementAction(id, data = {}) {
  return api.post(`/monitoring/management-actions/${id}/acknowledge`, data).then((res) => res.data)
}

export function closeManagementAction(id, data = {}) {
  return api.post(`/monitoring/management-actions/${id}/close`, data).then((res) => res.data)
}

export function listManagementActionsForCycle(cycleMonth) {
  return api.get(`/monitoring/management-actions/cycle/${cycleMonth}`).then((res) => res.data)
}

// ---------------------------------------------------------------------------
// Phase 2A: configurable risk thresholds
// ---------------------------------------------------------------------------

export function getRiskThresholds() {
  return api.get('/monitoring/risk-thresholds').then((res) => res.data)
}

export function updateRiskThresholds(data) {
  return api.put('/monitoring/risk-thresholds', data).then((res) => res.data)
}

// ---------------------------------------------------------------------------
// Phase 2A: submission evidence upload (reuses the existing project
// requirement submission endpoint for Evidence Intake, no new upload path)
// ---------------------------------------------------------------------------

export function uploadRequirementEvidence(requirementId, formData) {
  return api.post(`/projects/requirements/${requirementId}/submissions`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then((res) => res.data)
}

// ---------------------------------------------------------------------------
// Phase 2B: Non-Infra Monitoring / APM Template
// ---------------------------------------------------------------------------

export function listNonInfraMonitoringRecords(params = {}) {
  return api.get('/monitoring/non-infra-monitoring-records', { params }).then((res) => res.data)
}

export function createNonInfraMonitoringRecord(data) {
  const isFormData = typeof FormData !== 'undefined' && data instanceof FormData
  return api.post('/monitoring/non-infra-monitoring-records', data, isFormData ? {
    headers: { 'Content-Type': 'multipart/form-data' },
  } : undefined).then((res) => res.data)
}

export function updateNonInfraMonitoringRecord(id, data) {
  return api.put(`/monitoring/non-infra-monitoring-records/${id}`, data).then((res) => res.data)
}

// ---------------------------------------------------------------------------
// Phase 2B: Beneficiary evidence (Signed Distribution List, Acknowledgement
// Receipt, Beneficiary Tracking Record, Turnover Photos, Delivery Invoice)
// ---------------------------------------------------------------------------

export function listBeneficiaryEvidenceRecords(params = {}) {
  return api.get('/monitoring/beneficiary-evidence-records', { params }).then((res) => res.data)
}

export function createBeneficiaryEvidenceRecord(data) {
  const isFormData = typeof FormData !== 'undefined' && data instanceof FormData
  return api.post('/monitoring/beneficiary-evidence-records', data, isFormData ? {
    headers: { 'Content-Type': 'multipart/form-data' },
  } : undefined).then((res) => res.data)
}

export function updateBeneficiaryEvidenceRecord(id, data) {
  return api.put(`/monitoring/beneficiary-evidence-records/${id}`, data).then((res) => res.data)
}

// ---------------------------------------------------------------------------
// Phase 2C / Fix C: Appendix Monitoring Templates (Appendices 1-19)
// ---------------------------------------------------------------------------

export function listAppendixTemplates(params = {}) {
  return api.get('/monitoring/templates/appendices', { params }).then((res) => res.data)
}

export function downloadAppendixTemplate(appendixNumber) {
  return api.get(`/monitoring/templates/appendices/${appendixNumber}/download`, {
    responseType: 'blob',
  }).then((res) => ({
    data: res.data,
    headers: res.headers,
  }))
}
