import api from '../../../lib/api'


export function searchWorkspace(params = {}) {
  return api.get('/search', { params }).then((res) => res.data)
}
