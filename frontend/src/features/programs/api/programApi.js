import api from '../../../lib/api'

// --- Programs ---

export function listPrograms(params = {}) {
  return api.get('/programs', { params }).then(res => res.data)
}

export function listFiscalYears() {
  return api.get('/programs/fiscal-years').then(res => res.data)
}

export function getProgram(id) {
  return api.get(`/programs/${id}`).then(res => res.data)
}

export function createProgram(data) {
  return api.post('/programs', data).then(res => res.data)
}

export function updateProgram(id, data) {
  return api.put(`/programs/${id}`, data).then(res => res.data)
}

export function toggleProgramActive(id) {
  return api.post(`/programs/${id}/toggle-active`).then(res => res.data)
}

export function getProgramMatrix(id, params = {}) {
  return api.get(`/programs/${id}/matrix`, { params }).then(res => res.data)
}

// --- Program Cycles ---

export function listProgramCycles(programId, params = {}) {
  return api.get(`/programs/${programId}/cycles`, { params }).then(res => res.data)
}

export function createProgramCycle(programId, data) {
  return api.post(`/programs/${programId}/cycles`, data).then(res => res.data)
}

export function updateProgramCycle(cycleId, data) {
  return api.put(`/programs/cycles/${cycleId}`, data).then(res => res.data)
}

export function cloneProgramCycle(cycleId, data) {
  return api.post(`/programs/cycles/${cycleId}/clone`, data).then(res => res.data)
}

// --- Phases ---

export function listPhases(programId) {
  return api.get(`/programs/${programId}/phases`).then(res => res.data)
}

export function createPhase(programId, data) {
  return api.post(`/programs/${programId}/phases`, data).then(res => res.data)
}

export function updatePhase(phaseId, data) {
  return api.put(`/programs/phases/${phaseId}`, data).then(res => res.data)
}

export function deletePhase(phaseId) {
  return api.delete(`/programs/phases/${phaseId}`).then(res => res.data)
}

// --- Requirements ---

export function listRequirements(programId) {
  return api.get(`/programs/${programId}/requirements`).then(res => res.data)
}

export function createRequirement(phaseId, data) {
  return api.post(`/programs/phases/${phaseId}/requirements`, data).then(res => res.data)
}

export function getRequirement(reqId) {
  return api.get(`/programs/requirements/${reqId}`).then(res => res.data)
}

export function updateRequirement(reqId, data) {
  return api.put(`/programs/requirements/${reqId}`, data).then(res => res.data)
}

export function deleteRequirement(reqId) {
  return api.delete(`/programs/requirements/${reqId}`).then(res => res.data)
}
