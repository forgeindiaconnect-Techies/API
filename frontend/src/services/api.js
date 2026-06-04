import axios from 'axios'
import { useAuthStore } from '../store'

const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,
})

// Request interceptor
api.interceptors.request.use((config) => {
  const { token } = useAuthStore.getState()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Response interceptor
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true
      const { refreshToken, setAuth, logout } = useAuthStore.getState()
      if (refreshToken) {
        try {
          const { data } = await axios.post(`${BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken,
          })
          setAuth(data.user, data.access_token, data.refresh_token)
          original.headers.Authorization = `Bearer ${data.access_token}`
          return api(original)
        } catch {
          logout()
        }
      } else {
        logout()
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
    const { token } = useAuthStore.getState()
    return fetch(`${BASE_URL}/chat/conversations/${id}/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    }).then(async (res) => {
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) { onDone?.(); break }
        const chunk = decoder.decode(value)
        const lines = chunk.split('\n').filter(Boolean)
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') { onDone?.(); return }
            try { onChunk?.(JSON.parse(data)) } catch {}
          }
        }
      }
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
