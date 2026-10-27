import api from '../../../lib/api'

// --- Projects ---

export function listProjects(params = {}) {
  return api.get('/projects', { params }).then(res => res.data)
}

export function searchProjectsAcrossFiscalYears(params = {}) {
  return api.get('/projects', {
    params,
    skipFiscalYear: true,
  }).then(res => res.data)
}

export function getProject(id) {
  return api.get(`/projects/${id}`).then(res => res.data)
}

export function getProjectActivity(id, params = {}) {
  return api.get(`/projects/${id}/activity`, { params }).then(res => res.data)
}

export function downloadProjectRevisionReport(id, options = {}) {
  const hasOptions = !!(options.template_id || Object.keys(options.placeholder_overrides || {}).length)
  const config = {
    responseType: 'blob',
  }
  const request = hasOptions
    ? api.post(`/projects/${id}/revision-report`, options, config)
    : api.get(`/projects/${id}/revision-report`, config)
  return request.then(res => ({
    data: res.data,
    headers: res.headers,
  }))
}

export function previewProjectRevisionReport(id, options = {}) {
  return api.post(`/projects/${id}/revision-report/preview`, options).then(res => res.data)
}

export function listProjectRevisionReportTemplates() {
  return api.get('/projects/revision-report/templates').then(res => res.data)
}

export function downloadRequirementCorrectionReport(requirementId, options = {}) {
  const config = {
    responseType: 'blob',
    params: {
      report_id: options.report_id || undefined,
      transition_id: options.transition_id || undefined,
    },
  }
  return api.get(`/projects/requirements/${requirementId}/correction-report`, config).then(res => ({
    data: res.data,
    headers: res.headers,
  }))
}

export function createProject(data) {
  return api.post('/projects', data).then(res => res.data)
}

export function updateProject(id, data) {
  return api.put(`/projects/${id}`, data).then(res => res.data)
}

// --- Phase Transitions ---

export function transitionProjectPhase(projectId, data) {
  return api.post(`/projects/${projectId}/transition`, data).then(res => res.data)
}

// --- Project Requirements ---

export function initializeProjectRequirements(projectId) {
  return api.post(`/projects/${projectId}/requirements/init`).then(res => res.data)
}

export function listProjectRequirements(projectId, params = {}) {
  return api.get(`/projects/${projectId}/requirements`, { params }).then(res => res.data)
}

export function getProjectRequirement(requirementId) {
  return api.get(`/projects/requirements/${requirementId}`).then(res => res.data)
}

export function updateProjectRequirement(requirementId, data) {
  return api.put(`/projects/requirements/${requirementId}`, data).then(res => res.data)
}

export function updateProjectRequirementApplicability(requirementId, data) {
  return api.put(`/projects/requirements/${requirementId}/applicability`, data).then(res => res.data)
}

export function returnProjectRequirementForRevision(requirementId, data) {
  return api.post(`/projects/requirements/${requirementId}/return-for-revision`, data).then(res => res.data)
}

export function createChangeStatusRequest(requirementId, data) {
  return api.post(`/projects/requirements/${requirementId}/change-requests`, data).then(res => res.data)
}

export function listChangeStatusRequests(params = {}) {
  return api.get('/projects/change-requests', { params }).then(res => res.data)
}

export function reviewChangeStatusRequest(requestId, data) {
  return api.post(`/projects/change-requests/${requestId}/review`, data).then(res => res.data)
}

// --- Intake / Documentary Evidence ---

export function listIntakeQueue(params = {}) {
  return api.get('/projects/intake/queue', { params }).then(res => res.data)
}

export function listRequirementSubmissions(requirementId) {
  return api.get(`/projects/requirements/${requirementId}/submissions`).then(res => res.data)
}

export function createRequirementSubmission(requirementId, payload) {
  return api.post(`/projects/requirements/${requirementId}/submissions`, payload, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  }).then(res => res.data)
}

function waitForScanPoll(delay, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('Aborted', 'AbortError'))
    const abort = () => {
      clearTimeout(timer)
      signal?.removeEventListener('abort', abort)
      reject(new DOMException('Aborted', 'AbortError'))
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', abort)
      resolve()
    }, delay)
    signal?.addEventListener('abort', abort, { once: true })
  })
}

export async function previewSubmissionScan(payload, { onProgress, signal } = {}) {
  const response = await api.post('/projects/submission-scan/jobs', payload, {
    signal,
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  let job = response.data.data
  const started = Date.now()
  let failures = 0
  while (job.status !== 'completed') {
    onProgress?.(job)
    if (job.status === 'failed') {
      throw new Error(job.error || 'Document processing failed. Please try again.')
    }
    if (Date.now() - started >= 25 * 60 * 1000) {
      throw new Error('Document processing is taking longer than expected. Please try again later.')
    }
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    const remaining = 25 * 60 * 1000 - (Date.now() - started)
    await waitForScanPoll(Math.min(1500 * 2 ** failures, 10000, remaining), signal)
    if (Date.now() - started >= 25 * 60 * 1000) {
      throw new Error('Document processing is taking longer than expected. Please try again later.')
    }
    try {
      const status = await api.get(`/projects/submission-scan/jobs/${job.job_id}`, {
        signal, timeout: Math.max(1, Math.min(10000, 25 * 60 * 1000 - (Date.now() - started))),
      })
      job = status.data.data
      failures = 0
    } catch (error) {
      if (signal?.aborted || error.code === 'ERR_CANCELED') throw error
      const code = error.response?.status
      const transient = !error.response || [408, 425, 429, 500, 502, 503, 504].includes(code)
      if (!transient || ++failures >= 5) {
        error.scanJobId = job.job_id
        throw error
      }
    }
  }
  onProgress?.(job)
  return { ...response.data, data: job.result }
}

export function scanSubmissionDocument(submissionId) {
  return api.post(`/projects/submissions/${submissionId}/scan`).then(res => res.data)
}

export function refreshSubmissionDestination(submissionId) {
  return api.post(`/projects/submissions/${submissionId}/refresh-destination`).then(res => res.data)
}

export function listSubmissionScanResults(submissionId) {
  return api.get(`/projects/submissions/${submissionId}/scan-results`).then(res => res.data)
}

export function runSubmissionComplianceCheck(submissionId, data = {}) {
  return api.post(`/projects/submissions/${submissionId}/compliance-check`, data).then(res => res.data)
}

export function listSubmissionComplianceResults(submissionId) {
  return api.get(`/projects/submissions/${submissionId}/compliance-results`).then(res => res.data)
}

export function reviewComplianceResult(resultId, data) {
  return api.post(`/projects/compliance-results/${resultId}/review`, data).then(res => res.data)
}

export function reviewSubmissionScan(scanId, data) {
  return api.post(`/projects/submission-scans/${scanId}/review`, data).then(res => res.data)
}

export function downloadSubmissionFile(fileId) {
  return api.get(`/projects/files/${fileId}/download`, {
    responseType: 'blob',
  }).then(res => ({
    data: res.data,
    headers: res.headers,
  }))
}

// --- Regional Handoff ---

export function listHandoffQueue(params = {}) {
  return api.get('/projects/handoff/queue', { params }).then(res => res.data)
}

export function pushRequirementHandoff(requirementId) {
  return api.post(`/projects/requirements/${requirementId}/handoff`).then(res => res.data)
}
