import axios from 'axios'

const configuredApiUrl = String(import.meta.env.VITE_API_URL || '')
  .trim()
  .replace(/\/+$/, '')

if (!configuredApiUrl) {
  throw new Error('VITE_API_URL is required (example: http://localhost:8007)')
}

const apiOrigin = configuredApiUrl
const apiBaseUrl = apiOrigin.toLowerCase().endsWith('/api') ? apiOrigin : `${apiOrigin}/api`

const client = axios.create({
  baseURL: apiBaseUrl,
  headers: { 'Content-Type': 'application/json' },
})
const encodePathParam = (value) => encodeURIComponent(String(value ?? ''))
const AUTH_TOKEN_STORAGE_KEY = 'poultry_auth_token'
const AUTH_USER_STORAGE_KEY = 'poultry_auth_user'

const getStoredValue = (key) => {
  if (typeof window === 'undefined') return ''
  return String(window.localStorage.getItem(key) || '')
}

export const getAuthToken = () => getStoredValue(AUTH_TOKEN_STORAGE_KEY)
export const getAuthUser = () => {
  const raw = getStoredValue(AUTH_USER_STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export const setAuthSession = (token, user = null) => {
  if (typeof window === 'undefined') return
  const normalizedToken = String(token || '').trim()
  if (normalizedToken) {
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, normalizedToken)
  } else {
    window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
  }

  if (user && typeof user === 'object') {
    window.localStorage.setItem(AUTH_USER_STORAGE_KEY, JSON.stringify(user))
  } else {
    window.localStorage.removeItem(AUTH_USER_STORAGE_KEY)
  }
}

export const clearAuthSession = () => {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
  window.localStorage.removeItem(AUTH_USER_STORAGE_KEY)
}

let backendReachable = true
const backendStatusListeners = new Set()

const notifyBackendStatus = () => {
  backendStatusListeners.forEach((listener) => {
    try {
      listener(backendReachable)
    } catch {
      // Ignore listener errors so one bad subscriber does not break others.
    }
  })
}

const setBackendReachable = (isReachable) => {
  if (backendReachable === isReachable) return
  backendReachable = isReachable
  notifyBackendStatus()
}

const collectErrorText = (error) => {
  const parts = []
  const message = String(error?.message || '').trim()
  if (message) parts.push(message)

  const responseData = error?.response?.data
  if (typeof responseData === 'string' && responseData.trim()) {
    parts.push(responseData)
  } else if (responseData && typeof responseData === 'object') {
    const detail = responseData.detail || responseData.message || responseData.error
    if (typeof detail === 'string' && detail.trim()) {
      parts.push(detail)
    }
  }
  return parts.join(' ').toLowerCase()
}

const isBackendOfflineError = (error) => {
  if (!error?.response) return true

  const status = Number(error.response.status || 0)
  if (status >= 500) return true

  const code = String(error?.code || '').toLowerCase()
  if (code.includes('network') || code.includes('conn') || code.includes('abort')) {
    return true
  }

  const text = collectErrorText(error)
  if (
    text.includes('econnrefused') ||
    text.includes('connect econnrefused') ||
    text.includes('http proxy error') ||
    text.includes('proxy error')
  ) {
    return true
  }

  return false
}

client.interceptors.response.use(
  (response) => {
    setBackendReachable(true)
    return response
  },
  (error) => {
    setBackendReachable(!isBackendOfflineError(error))
    return Promise.reject(error)
  }
)// it is the response interceptor, it will return the response as is, and in case of error it will reject the promise with the error

client.interceptors.request.use((config) => {
  const token = getAuthToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export default client

export const backendStatus = {
  get: () => backendReachable,
  subscribe: (listener) => {
    if (typeof listener !== 'function') return () => {}
    backendStatusListeners.add(listener)
    listener(backendReachable)
    return () => {
      backendStatusListeners.delete(listener)
    }
  },
  ping: async () => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 4000)
    try {
      const response = await fetch(`${apiBaseUrl}/health`, {
        method: 'GET',
        cache: 'no-store',
        signal: controller.signal,
      })
      const isReachable = Number(response.status || 0) < 500
      setBackendReachable(isReachable)
      return isReachable
    } catch (error) {
      setBackendReachable(false)
      return false
    } finally {
      clearTimeout(timer)
    }
  },
}

export const auth = {
  login: (email, password) => client.post('/auth/login', { email, password }),
  vendorSignup: (data) => client.post('/auth/vendor-signup', data),
  vendorCreateCustomer: (data) => client.post('/auth/vendor/customer-signup', data),
  demoVendor: () => client.post('/auth/demo/vendor'),
  demoCustomer: () => client.post('/auth/demo/customer'),
  verifyPin: (pin, pinType = 'settings') => client.post('/auth/pin/verify', { pin, pin_type: pinType }),
  changePin: (currentPin, newPin, pinType = 'settings') =>
    client.post('/auth/pin/change', { current_pin: currentPin, new_pin: newPin, pin_type: pinType }),
}


export const plc = {
  latest: () => client.get('/plc/latest'),
  history: (minutes = 60, params = {}) => client.get('/plc/history', { params: { minutes, ...params } }),
  machineStatus: () => client.get('/plc/machine/status'),
}



export const rawMaterial = {
  listTypes: () => client.get('/raw-material/types'),
  addType: (name) => client.post('/raw-material/types', null, { params: { name } }),
  updateType: (id, name) => client.put(`/raw-material/types/${id}`, null, { params: { name } }),
  deleteType: (id) => client.delete(`/raw-material/types/${id}`),
  list: (params) => client.get('/raw-material', { params }),
  listByPeriod: (period, rmType = 'all', params = {}) =>
    client.get(
      `/raw-material/filtered/${encodePathParam(period)}/${encodePathParam(rmType)}`,
      { params }
    ),
  summaryByPeriod: (period, rmType = 'all', params = {}) =>
    client.get(
      `/raw-material/summary/${encodePathParam(period)}/${encodePathParam(rmType)}`,
      { params }
    ),
  create: (data) => client.post('/raw-material', data),
  update: (id, data) => client.put(`/raw-material/${id}`, data),
  downloadEntry: (id, format = 'pdf') => client.get(`/raw-material/${id}/download`, { params: { format }, responseType: 'blob' }),
  getLabReport: (entryId) => client.get(`/raw-material/lab-report/${entryId}`),
  submitLabReport: (data) => client.post('/raw-material/lab-report', data),
  download: (format, params = {}) =>
    client.get('/raw-material/download', {
      params: { format, ...params },
      responseType: 'blob'
    }),
}

export const dispatchApi = {
  list: (params) => client.get('/dispatch', { params }),
  listByPeriod: (period, productType = 'all', params = {}) =>
    client.get(
      `/dispatch/filtered/${encodePathParam(period)}/${encodePathParam(productType)}`,
      { params }
    ),
  summaryByPeriod: (period, productType = 'all', params = {}) =>
    client.get(
      `/dispatch/summary/${encodePathParam(period)}/${encodePathParam(productType)}`,
      { params }
    ),
  create: (data) => client.post('/dispatch', data),
  update: (id, data) => client.put(`/dispatch/${id}`, data),
  downloadEntry: (id, format = 'pdf') => client.get(`/dispatch/${id}/download`, { params: { format }, responseType: 'blob' }),
  download: (format, params = {}) =>
    client.get('/dispatch/download', {
      params: { format, ...params },
      responseType: 'blob',
    }),
  downloadInvoice: (id) => client.get(`/dispatch/${id}/invoice`, { responseType: 'blob' }),
}

export const productionApi = {
  listBatches: (params) => client.get('/production/batches', { params }),
  listBatchesByPeriod: (period, productName = 'all', params = {}) =>
    client.get(
      `/production/batches/filtered/${encodePathParam(period)}/${encodePathParam(productName)}`,
      { params }
    ),
  summaryByPeriod: (period, productName = 'all', params = {}) =>
    client.get(
      `/production/batches/summary/${encodePathParam(period)}/${encodePathParam(productName)}`,
      { params }
    ),
  getBatch: (id) => client.get(`/production/batches/${id}`),
  markBatchCompleteEligibility: (id) =>
    client.get(`/production/batches/${id}/mark-complete-eligibility`),
  createBatch: (data) => client.post('/production/batches', data),
  updateBatchDetails: (id, data) => client.put(`/production/batches/${id}/details`, data),
  markBatchComplete: (id) => client.post(`/production/batches/${id}/mark-complete`, {}),
  submitReport: (data) => client.post('/production/report', data),
  consumptionReport: (params) => client.get('/production/consumption', { params }),
  download: (format, params = {}) =>
    client.get('/production/download', {
      params: { format, ...params },
      responseType: 'blob'
    }),

  // ✅ ADD THIS (download single batch)
  downloadBatch: (id, format = "pdf") =>
    client.get(`/production/${id}/download`, {
      params: { format },
      responseType: 'blob'
    }),
  downloadBatchConsumption: (id, format = "pdf") =>
    client.get(`/production/${id}/consumption/download`, {
      params: { format },
      responseType: 'blob'
    }),
}

// export const stockApi = {
//   rm: (params) => client.get('/stock/rm', { params }),
//   feed: (params) => client.get('/stock/feed', { params }),
//   feedSummary: () => client.get('/stock/feed/summary'),
//   downloadRm: (format) => client.get('/stock/download/rm', { params: { format }, responseType: 'blob' }),
//   downloadFeed: (format) => client.get('/stock/download/feed', { params: { format }, responseType: 'blob' }),
//    downloadDispatch: (format = "pdf") =>
//     client.get('/stock/dispatch/report', {
//       params: { format },
//       responseType: 'blob'
//     }),

//   downloadProduction: (format = "pdf") =>
//     client.get('/stock/production/report', {
//       params: { format },
//       responseType: 'blob'
//     }),

//   downloadFeed: (format = "pdf") =>
//     client.get('/stock/download/feed', {
//       params: { format },
//       responseType: 'blob'
//     }),
// }
 export const stockApi = {
  rm: (params) => client.get('/stock/rm', { params }),
  rmByPeriod: (period, params = {}) =>
    client.get(`/stock/rm/filtered/${encodePathParam(period)}`, { params }),
  rmSummary: () => client.get('/stock/rm/summary'),
  feed: (params) => client.get('/stock/feed', { params }),
  feedByPeriod: (period, params = {}) =>
    client.get(`/stock/feed/filtered/${encodePathParam(period)}`, { params }),
  feedSummary: () => client.get('/stock/feed/summary'),

  // ✅ Raw Material Report
  downloadRM: (format = "pdf", params = {}) =>
    client.get('/stock/download/rm', {
      params: { format, ...params },
      responseType: 'blob'
    }),
  downloadRMIndividual: (format = "pdf") =>
    client.get('/stock/download/rm-summary', {
      params: { format },
      responseType: 'blob'
    }),
  downloadFeedIndividual: (format = "pdf") =>
    client.get('/stock/download/feed-summary', {
      params: { format },
      responseType: 'blob'
    }),

  // ✅ Dispatch Report
  downloadDispatch: (format = "pdf", params = {}) =>
    client.get('/dispatch/download', {
      params: { format, ...params },
      responseType: 'blob'
    }),

  // ✅ Production Report
  downloadProduction: (format = "pdf", params = {}) =>
    client.get('/production/download', {
      params: { format, ...params },
      responseType: 'blob'
    }),

  // ✅ Finished Feed Report
  downloadFeed: (format = "pdf", params = {}) =>
    client.get('/stock/download/feed', {
      params: { format, ...params },
      responseType: 'blob'
    }),

  // ✅ Overall Stock (RM + Feed in single file)
  downloadOverall: (format = "pdf") =>
    client.get('/stock/download/overall', {
      params: { format },
      responseType: 'blob'
    }),
};
export const configApi = {
  productTypes: () => client.get('/config/product-types'),
  productTypesManage: () => client.get('/config/product-types/manage'),
  addProductType: (name) =>
    client.post('/config/product-types', null, { params: { name } }),
  updateProductType: (id, name) =>
    client.put(`/config/product-types/${id}`, null, { params: { name } }),
  deleteProductType: (id) => client.delete(`/config/product-types/${id}`),
  recipes: () => client.get('/config/recipes'),
  addRecipe: (data) => client.post('/config/recipes', data),
  updateRecipe: (id, data) => client.put(`/config/recipes/${id}`, data),
  deleteRecipe: (id) => client.delete(`/config/recipes/${id}`),
}
