import api from '../../../lib/api'
import { getStoredFiscalYear } from '../../../lib/fiscalYear'

export function createConversation(data = {}) {
  return api.post('/ai/conversations', data).then((res) => res.data)
}

export function listConversations(params = {}) {
  return api.get('/ai/conversations', { params }).then((res) => res.data)
}

export function getConversation(id) {
  return api.get(`/ai/conversations/${id}`).then((res) => res.data)
}

export function updateConversation(id, data) {
  return api.patch(`/ai/conversations/${id}`, data).then((res) => res.data)
}

export function sendMessage(conversationId, message, attachmentStoredObjectId = null) {
  return api.post(`/ai/conversations/${conversationId}/messages`, {
    message,
    fiscal_year: getStoredFiscalYear(),
    ...(attachmentStoredObjectId ? { attachment_stored_object_id: attachmentStoredObjectId } : {}),
  }).then((res) => res.data)
}

export function uploadAttachment(conversationId, file) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post(`/ai/conversations/${conversationId}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then((res) => res.data)
}

export function listTools() {
  return api.get('/ai/tools').then((res) => res.data)
}

export function rewriteText(data) {
  return api.post('/ai/rewrite-text', data).then((res) => res.data)
}

export function confirmToolCall(toolCallId) {
  return api.post(`/ai/tool-calls/${toolCallId}/confirm`).then((res) => res.data)
}

export function cancelToolCall(toolCallId) {
  return api.post(`/ai/tool-calls/${toolCallId}/cancel`).then((res) => res.data)
}

export async function downloadToolFile(toolCallId, fileIndex) {
  try {
    const response = await api.get(`/ai/tool-calls/${toolCallId}/downloads/${fileIndex}`, {
      responseType: 'blob', skipFiscalYear: true,
    })
    const disposition = response.headers?.['content-disposition'] || ''
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)
    const plain = disposition.match(/filename="([^"]+)"|filename=([^;]+)/i)
    let filename = plain?.[1] || plain?.[2]?.trim() || 'report-download'
    if (encoded) {
      try { filename = decodeURIComponent(encoded[1]) } catch { /* use plain filename */ }
    }
    return { blob: response.data, filename: filename.split(/[\\/]/).pop() || 'report-download' }
  } catch (error) {
    let message = error.response?.data?.message
    if (!message && typeof error.response?.data?.text === 'function') {
      try { message = JSON.parse(await error.response.data.text()).message } catch { /* use fallback */ }
    }
    throw new Error(message || 'The download could not be completed. Please try again.')
  }
}
