import api from '../../../lib/api'

export function getOperationsDashboard(params = {}) {
  return api.get('/dashboard/operations', { params }).then((res) => res.data)
}

