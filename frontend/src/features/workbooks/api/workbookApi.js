import api from '../../../lib/api'

export function listWorkspaces(params = {}) {
  return api.get('/workbook-workspaces', { params }).then(res => res.data)
}

export function listSheets(workspaceId) {
  return api.get(`/workbook-workspaces/${workspaceId}/sheets`).then(res => res.data)
}

export function getSheetGrid(workspaceId, sheetId, params = {}) {
  return api.get(`/workbook-workspaces/${workspaceId}/sheets/${sheetId}/grid`, { params }).then(res => res.data)
}

export function updateColumn(workspaceId, columnId, payload) {
  return api.patch(`/workbook-workspaces/${workspaceId}/columns/${columnId}`, payload).then(res => res.data)
}

export function updateCell(workspaceId, cellId, payload) {
  return api.patch(`/workbook-workspaces/${workspaceId}/cells/${cellId}`, payload).then(res => res.data)
}

export function listConflicts(workspaceId, params = {}) {
  return api.get(`/workbook-workspaces/${workspaceId}/conflicts`, { params }).then(res => res.data)
}

export function resolveConflict(workspaceId, conflictId, payload) {
  return api.post(`/workbook-workspaces/${workspaceId}/conflicts/${conflictId}/resolve`, payload).then(res => res.data)
}

export function listCellHistory(workspaceId, cellId, params = {}) {
  return api.get(`/workbook-workspaces/${workspaceId}/cells/${cellId}/history`, { params }).then(res => res.data)
}

function filenameFromDisposition(disposition, fallback) {
  const match = String(disposition || '').match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)["']?/i)
  return match ? decodeURIComponent(match[1]) : fallback
}

export function exportWorkbook(workspaceId) {
  return api.post(`/workbook-workspaces/${workspaceId}/export`, {}, { responseType: 'blob' }).then(res => ({
    blob: res.data,
    filename: filenameFromDisposition(res.headers['content-disposition'], `workbook-${workspaceId}.xlsx`),
  }))
}
