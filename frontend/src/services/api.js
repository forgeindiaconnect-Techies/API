import axios from 'axios'
import { useAuthStore } from '../store'

const BASE_URL = import.meta.env.VITE_API_URL || 
  (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? '/api/v1'
    : 'https://d-ai-7k8h.onrender.com/api/v1')

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,
  withCredentials: true,
})

function getjwtExpiry(token) {
  if (!token) return 0
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return 0
    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')))
    return payload.exp ? payload.exp * 1000 : 0
  } catch (e) {
    return 0
  }
}

let refreshPromise = null

async function getOrRefreshAccessToken() {
  let token = localStorage.getItem("access_token") || useAuthStore.getState().token
  const refreshToken = localStorage.getItem("refresh_token") || useAuthStore.getState().refreshToken

  if (token) {
    const expiry = getjwtExpiry(token)
    const now = Date.now()
    const isExpiredOrExpiringSoon = expiry && (expiry - now < 30000) // 30s buffer

    if (isExpiredOrExpiringSoon && refreshToken) {
      if (!refreshPromise) {
        const { setAuth, logout } = useAuthStore.getState()
        refreshPromise = axios.post(`${BASE_URL}/auth/refresh`, {
          refresh_token: refreshToken,
        }).then(res => {
          const data = res.data
          setAuth(data.user, data.access_token, data.refresh_token)
          refreshPromise = null
          return data.access_token
        }).catch(err => {
          refreshPromise = null
          logout()
          window.location.href = '/login'
          return Promise.reject(err)
        })
      }
      return refreshPromise
    }
  }
  return token
}

// Request interceptor
api.interceptors.request.use(async (config) => {
  console.log(`[API Request] ${config.method?.toUpperCase()} ${config.url}`, config.params || '');
  if (config.url.includes('/auth/refresh') || config.url.includes('/auth/login') || config.url.includes('/auth/register')) {
    return config
  }
  try {
    const token = await getOrRefreshAccessToken()
    if (token) {
      if (config.headers.set) {
        config.headers.set('Authorization', `Bearer ${token}`)
      } else {
        config.headers['Authorization'] = `Bearer ${token}`
      }
      console.log(`[API Request Auth] Token attached for: ${config.url}`);
    } else {
      console.warn(`[API Request Auth] No token available for: ${config.url}`);
    }
  } catch (e) {
    console.error(`[API Request Auth Error] Failed to set auth header:`, e);
    return Promise.reject(e)
  }
  return config
})

// Response interceptor
api.interceptors.response.use(
  (res) => {
    console.log(`[API Response Success] ${res.config.method?.toUpperCase()} ${res.config.url} Status: ${res.status}`);
    return res;
  },
  async (err) => {
    const original = err.config
    console.error(`[API Response Error] ${original?.method?.toUpperCase()} ${original?.url} Status: ${err.response?.status}`, err.response?.data || err.message);
    if (
      err.response?.status === 401 &&
      !original._retry &&
      !original.url.includes('/auth/refresh') &&
      !original.url.includes('/auth/login') &&
      !original.url.includes('/auth/register')
    ) {
      original._retry = true
      const refreshToken = localStorage.getItem("refresh_token") || useAuthStore.getState().refreshToken
      const { setAuth, logout } = useAuthStore.getState()
      if (refreshToken) {
        if (!refreshPromise) {
          console.log('[API Auth] Access token rejected (401). Attempting refresh...');
          refreshPromise = axios.post(`${BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken,
          }).then(res => {
            const data = res.data
            console.log('[API Auth] Token refresh successful.');
            setAuth(data.user, data.access_token, data.refresh_token)
            refreshPromise = null
            return data.access_token
          }).catch(refreshErr => {
            console.error('[API Auth] Token refresh failed. Logging out.', refreshErr.response?.data || refreshErr.message);
            refreshPromise = null
            logout()
            // Use replace to prevent back-button loops to broken auth state
            if (window.location.pathname !== '/login') {
              window.location.replace('/login')
            }
            return Promise.reject(refreshErr)
          })
        }
        try {
          const newToken = await refreshPromise
          if (original.headers.set) {
            original.headers.set('Authorization', `Bearer ${newToken}`)
          } else {
            original.headers['Authorization'] = `Bearer ${newToken}`
          }
          return api(original)
        } catch (refreshErr) {
          return Promise.reject(refreshErr)
        }
      } else {
        console.warn('[API Auth] No refresh token available. Logging out.');
        logout()
        if (window.location.pathname !== '/login') {
          window.location.replace('/login')
        }
        return Promise.reject(err)
      }
    }
    return Promise.reject(err)
  }
)

// Auth
export const authAPI = {
  login: (data) => api.post('/auth/login', data),
  register: (data) => api.post('/auth/register', data),
  refresh: (token) => api.post('/auth/refresh', { refresh_token: token }),
  me: () => api.get('/auth/me'),
  updateProfile: (data) => api.put('/auth/profile', data),
  changePassword: (data) => api.put('/auth/password', data),
}

// Chat
export const chatAPI = {
  getConversations: () => api.get('/chat/conversations'),
  createConversation: (data) => api.post('/chat/conversations', data),
  deleteConversation: (id) => api.delete(`/chat/conversations/${id}`),
  getMessages: (id) => api.get(`/chat/conversations/${id}/messages`),
  sendMessage: (id, data) => api.post(`/chat/conversations/${id}/messages`, data),
  streamMessage: (id, data, onChunk, onDone) => {
    const refreshToken = localStorage.getItem("refresh_token") || useAuthStore.getState().refreshToken
    const { setAuth, logout } = useAuthStore.getState()
    
    const cleanId = id ? id.toString().replace(/\/+$/, '') : ''
    const executeFetch = (accessToken) => {
      return fetch(`${BASE_URL}/chat/conversations/${cleanId}/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify(data),
      })
    }

    const handleStream = async (res) => {
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      
      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          if (buffer.trim()) {
            const trimmed = buffer.trim()
            if (trimmed.startsWith('data: ')) {
              const data = trimmed.slice(6).trim()
              if (data !== '[DONE]') {
                try { onChunk?.(JSON.parse(data)) } catch {}
              }
            }
          }
          onDone?.()
          break
        }
        
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // Keep the last incomplete line in the buffer
        
        for (const line of lines) {
          const trimmed = line.trim()
          if (trimmed.startsWith('data: ')) {
            const data = trimmed.slice(6).trim()
            if (data === '[DONE]') { onDone?.(); return }
            try { onChunk?.(JSON.parse(data)) } catch {}
          }
        }
      }
    }

    return getOrRefreshAccessToken().then((accessToken) => {
      return executeFetch(accessToken).then(async (res) => {
        if (res.status === 401 && refreshToken) {
          try {
            if (!refreshPromise) {
              refreshPromise = axios.post(`${BASE_URL}/auth/refresh`, {
                refresh_token: refreshToken,
              }).then(refreshRes => {
                const newData = refreshRes.data
                setAuth(newData.user, newData.access_token, newData.refresh_token)
                refreshPromise = null
                return newData.access_token
              }).catch(refreshErr => {
                refreshPromise = null
                logout()
                throw new Error('Authentication expired. Please log in again.')
              })
            }
            const newAccessToken = await refreshPromise
            const retriedRes = await executeFetch(newAccessToken)
            if (!retriedRes.ok) {
              throw new Error(`Streaming failed: HTTP ${retriedRes.status}`)
            }
            return handleStream(retriedRes)
          } catch (refreshErr) {
            logout()
            throw new Error('Authentication expired. Please log in again.')
          }
        }

        if (!res.ok) {
          const errText = await res.text().catch(() => '')
          let errMsg = errText
          try {
            const parsed = JSON.parse(errText)
            if (parsed && parsed.detail) {
              errMsg = parsed.detail
            }
          } catch {}
          throw new Error(errMsg || `Request failed with status ${res.status}`)
        }

        return handleStream(res)
      })
    })
  },
}

// Datasets
export const datasetAPI = {
  list: () => api.get('/datasets'),
  upload: (formData, onProgress) =>
    api.post('/datasets/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    }),
  get: (id) => api.get(`/datasets/${id}`),
  delete: (id) => api.delete(`/datasets/${id}`),
  process: (id, options) => api.post(`/datasets/${id}/process`, options),
  getEDA: (id) => api.get(`/datasets/${id}/eda`),
  getPreview: (id) => api.get(`/datasets/${id}/preview`),
  getStatus: (id) => api.get(`/datasets/${id}/status`),
  getStats: (id) => api.get(`/datasets/${id}/stats`),
}

// Models
export const modelAPI = {
  list: () => api.get('/models'),
  get: (id) => api.get(`/models/${id}`),
  delete: (id) => api.delete(`/models/${id}`),
  startTraining: (data) => api.post('/models/train', data),
  getTrainingStatus: (id) => api.get(`/models/training/${id}`),
  stopTraining: (id) => api.post(`/models/training/${id}/stop`),
  getTrainingLogs: (id) => api.get(`/models/training/${id}/logs`),
  getTrainingProgress: () => api.get('/models/training/progress'),
  evaluate: (id, data) => api.post(`/models/${id}/evaluate`, data),
  predict: (id, data) => api.post(`/models/${id}/predict`, data),
}

// RAG
export const ragAPI = {
  createIndex: (datasetId, options) =>
    api.post('/rag/index', { dataset_id: datasetId, ...options }),
  listIndexes: () => api.get('/rag/indexes'),
  deleteIndex: (id) => api.delete(`/rag/indexes/${id}`),
  search: (indexId, query, topK = 5) =>
    api.post('/rag/search', { index_id: indexId, query, top_k: topK }),
  chat: (indexId, question) =>
    api.post('/rag/chat', { index_id: indexId, question }),
}

// API Keys
export const apiKeyAPI = {
  list: () => api.get('/api-keys'),
  create: (data) => api.post('/api-keys', data),
  revoke: (id) => api.delete(`/api-keys/${id}`),
  rename: (id, name) => api.patch(`/api-keys/${id}`, { name }),
  rotate: (id) => api.post(`/api-keys/${id}/rotate`),
  getUsage: (id) => api.get(`/api-keys/${id}/usage`),
}

// Analytics
export const analyticsAPI = {
  getDashboard: () => api.get('/analytics/dashboard'),
  getUsage: (params) => api.get('/analytics/usage', { params }),
  getModelPerformance: (modelId) => api.get(`/analytics/models/${modelId}`),
  getApiStats: () => api.get('/analytics/api'),
}

// Multimodal
export const multimodalAPI = {
  transcribeAudio: (formData) =>
    api.post('/ai/transcribe', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  captionImage: (formData) =>
    api.post('/ai/caption', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  generateImage: (data) => api.post('/ai/generate-image', data),
  extractOCR: (formData) =>
    api.post('/ai/ocr', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  summarize: (data) => api.post('/ai/summarize', data),
}

export default api
