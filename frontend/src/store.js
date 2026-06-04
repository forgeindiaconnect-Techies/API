import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const useAuthStore = create(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      setAuth: (user, token, refreshToken) =>
        set({ user, token, refreshToken, isAuthenticated: true }),
      logout: () =>
        set({ user: null, token: null, refreshToken: null, isAuthenticated: false }),
      updateUser: (updates) =>
        set({ user: { ...get().user, ...updates } }),
    }),
    { name: 'auth-storage' }
  )
)

export const useUIStore = create((set) => ({
  sidebarOpen: true,
  theme: 'dark',
  activeSection: 'dashboard',
  notifications: [],
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setTheme: (theme) => {
    document.documentElement.classList.toggle('light', theme === 'light')
    set({ theme })
  },
  setActiveSection: (section) => set({ activeSection: section }),
  addNotification: (n) =>
    set((s) => ({ notifications: [{ id: Date.now(), ...n }, ...s.notifications.slice(0, 9)] })),
  removeNotification: (id) =>
    set((s) => ({ notifications: s.notifications.filter((n) => n.id !== id) })),
}))

export const useChatStore = create((set, get) => ({
  conversations: [],
  activeConversationId: null,
  messages: {},
  isStreaming: false,
  selectedModel: 'llama3',

  setActiveConversation: (id) => set({ activeConversationId: id }),
  setStreaming: (v) => set({ isStreaming: v }),
  setModel: (m) => set({ selectedModel: m }),

  addConversation: (conv) =>
    set((s) => ({ conversations: [conv, ...s.conversations] })),

  updateConversation: (id, updates) =>
    set((s) => ({
      conversations: s.conversations.map((c) =>
        c.id === id ? { ...c, ...updates } : c
      ),
    })),

  setMessages: (convId, messages) =>
    set((s) => ({ messages: { ...s.messages, [convId]: messages } })),

  addMessage: (convId, message) =>
    set((s) => ({
      messages: {
        ...s.messages,
        [convId]: [...(s.messages[convId] || []), message],
      },
    })),

  appendToLastMessage: (convId, text) =>
    set((s) => {
      const msgs = [...(s.messages[convId] || [])]
      if (msgs.length > 0) {
        msgs[msgs.length - 1] = {
          ...msgs[msgs.length - 1],
          content: (msgs[msgs.length - 1].content || '') + text,
        }
      }
      return { messages: { ...s.messages, [convId]: msgs } }
    }),
}))

export const useDatasetStore = create((set) => ({
  datasets: [],
  selectedDataset: null,
  uploadProgress: {},
  processingStatus: {},

  setDatasets: (datasets) => set({ datasets }),
  addDataset: (ds) => set((s) => ({ datasets: [ds, ...s.datasets] })),
  updateDataset: (id, updates) =>
    set((s) => ({
      datasets: s.datasets.map((d) => (d.id === id ? { ...d, ...updates } : d)),
    })),
  removeDataset: (id) =>
    set((s) => ({ datasets: s.datasets.filter((d) => d.id !== id) })),
  setSelectedDataset: (ds) => set({ selectedDataset: ds }),
  setUploadProgress: (id, progress) =>
    set((s) => ({ uploadProgress: { ...s.uploadProgress, [id]: progress } })),
  setProcessingStatus: (id, status) =>
    set((s) => ({ processingStatus: { ...s.processingStatus, [id]: status } })),
}))

export const useModelStore = create((set) => ({
  models: [],
  trainingJobs: [],
  selectedModel: null,

  setModels: (models) => set({ models }),
  addModel: (m) => set((s) => ({ models: [m, ...s.models] })),
  updateModel: (id, updates) =>
    set((s) => ({
      models: s.models.map((m) => (m.id === id ? { ...m, ...updates } : m)),
    })),
  setSelectedModel: (m) => set({ selectedModel: m }),

  addTrainingJob: (job) =>
    set((s) => ({ trainingJobs: [job, ...s.trainingJobs] })),
  updateTrainingJob: (id, updates) =>
    set((s) => ({
      trainingJobs: s.trainingJobs.map((j) =>
        j.id === id ? { ...j, ...updates } : j
      ),
    })),
}))

export const useApiKeyStore = create((set) => ({
  apiKeys: [],
  setApiKeys: (keys) => set({ apiKeys: keys }),
  addApiKey: (key) => set((s) => ({ apiKeys: [key, ...s.apiKeys] })),
  removeApiKey: (id) =>
    set((s) => ({ apiKeys: s.apiKeys.filter((k) => k.id !== id) })),
  updateApiKey: (id, updates) =>
    set((s) => ({
      apiKeys: s.apiKeys.map((k) => (k.id === id ? { ...k, ...updates } : k)),
    })),
}))
