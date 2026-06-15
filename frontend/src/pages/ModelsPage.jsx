import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Brain, Play, Trash2, Download, BarChart3, Plus, AlertCircle, RefreshCw } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useModelStore } from '../store'
import { modelAPI } from '../services/api'
import toast from 'react-hot-toast'

const formatSize = (bytes) => {
  if (!bytes) return '—'
  if (bytes > 1e9) return `${(bytes / 1e9).toFixed(1)} GB`
  if (bytes > 1e6) return `${(bytes / 1e6).toFixed(1)} MB`
  return `${(bytes / 1e3).toFixed(0)} KB`
}

const formatDate = (dateStr) => {
  if (!dateStr) return '—'
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
  } catch {
    return dateStr
  }
}

const statusBadge = (status, progress) => {
  if (status === 'ready') return <span className="badge badge-green">Ready</span>
  if (status === 'training') return <span className="badge badge-yellow">Training {progress || 0}%</span>
  if (status === 'stopped') return <span className="badge badge-gray">Stopped</span>
  return <span className="badge badge-red">Error</span>
}

export default function ModelsPage() {
  const navigate = useNavigate()
  const { models, setModels } = useModelStore()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [visibleCount, setVisibleCount] = useState(6)
  const pollIntervalRef = useRef(null)

  const fetchModels = async (showLoading = true) => {
    if (showLoading) setLoading(true)
    try {
      const { data } = await modelAPI.list()
      setModels(data)
      setError(null)
    } catch (err) {
      console.error('Failed to fetch models:', err)
      setError('Failed to load models. Please ensure the backend is running and try again.')
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  // Load models on mount
  useEffect(() => {
    fetchModels(true)
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    }
  }, [])

  // Start polling if any models are in 'training' status
  useEffect(() => {
    const hasTrainingModel = models.some(m => m.status === 'training')
    
    if (hasTrainingModel) {
      if (!pollIntervalRef.current) {
        pollIntervalRef.current = setInterval(async () => {
          try {
            const { data } = await modelAPI.getTrainingProgress()
            let shouldRefreshAll = false
            
            const updatedModels = models.map(m => {
              const update = data[m.id]
              if (update) {
                if (m.status === 'training' && update.status !== 'training') {
                  shouldRefreshAll = true
                }
                return { ...m, status: update.status, progress: update.progress }
              } else if (m.status === 'training') {
                shouldRefreshAll = true
              }
              return m
            })
            
            if (shouldRefreshAll) {
              fetchModels(false)
            } else {
              setModels(updatedModels)
            }
          } catch (err) {
            console.error('Failed to poll progress:', err)
          }
        }, 3000)
      }
    } else {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
    }
  }, [models])

  const handleDeleteModel = async (id, e) => {
    e.stopPropagation()
    if (!confirm('Are you sure you want to delete this model?')) return

    try {
      await modelAPI.delete(id)
      toast.success('Model deleted successfully')
      setModels(models.filter(m => m.id !== id))
    } catch (err) {
      console.error('Failed to delete model:', err)
      toast.error('Failed to delete model')
    }
  }

  if (loading && models.length === 0) {
    return (
      <div className="p-6 space-y-5 max-w-7xl mx-auto">
        <div className="flex justify-between items-center">
          <div>
            <div className="h-6 w-32 bg-tertiary rounded animate-pulse" />
            <div className="h-4 w-48 bg-tertiary rounded mt-2 animate-pulse" />
          </div>
          <div className="h-10 w-36 bg-tertiary rounded animate-pulse" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map(n => (
            <div key={n} className="card p-5 space-y-4 animate-pulse">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-tertiary" />
                  <div className="space-y-2">
                    <div className="h-4 w-28 bg-tertiary rounded" />
                    <div className="h-3 w-40 bg-tertiary rounded" />
                  </div>
                </div>
                <div className="h-5 w-16 bg-tertiary rounded" />
              </div>
              <div className="h-10 bg-tertiary rounded" />
              <div className="h-4 bg-tertiary rounded w-2/3" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6 max-w-7xl mx-auto text-center flex flex-col items-center justify-center space-y-4 min-h-[50vh]">
        <div className="w-12 h-12 rounded-full flex items-center justify-center bg-red-500/10">
          <AlertCircle size={24} className="text-red-500" />
        </div>
        <div>
          <h3 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>Connection Error</h3>
          <p className="text-sm mt-1 max-w-md" style={{ color: 'var(--text-muted)' }}>
            {error}
          </p>
        </div>
        <button onClick={() => fetchModels(true)} className="btn-primary flex items-center gap-2">
          <RefreshCw size={14} /> Retry Connection
        </button>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-5 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>Models</h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
            {models.length} model{models.length !== 1 ? 's' : ''} trained
          </p>
        </div>
        <button onClick={() => navigate('/training')} className="btn-primary flex items-center gap-1.5">
          <Plus size={14} /> Train New Model
        </button>
      </div>

      {models.length === 0 ? (
        <div className="card p-8 text-center flex flex-col items-center justify-center space-y-4 max-w-lg mx-auto mt-12 border-dashed border-2">
          <div className="w-16 h-16 rounded-full flex items-center justify-center" style={{ background: 'var(--accent-muted)' }}>
            <Brain size={32} style={{ color: 'var(--accent-primary)' }} />
          </div>
          <div>
            <h3 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>No Models Available</h3>
            <p className="text-sm mt-1 max-w-sm" style={{ color: 'var(--text-muted)' }}>
              You haven't trained any custom models yet. Start fine-tuning a base LLM with your dataset.
            </p>
          </div>
          <button onClick={() => navigate('/training')} className="btn-primary flex items-center gap-2">
            <Plus size={16} /> Train New Model
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <AnimatePresence mode="popLayout">
              {models.slice(0, visibleCount).map((model, i) => (
                <motion.div
                  key={model.id}
                  layout
                  className="card p-5 space-y-4 cursor-pointer hover:border-opacity-60 transition-all"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.2, delay: i * 0.05 }}
                  style={{ borderColor: model.status === 'training' ? 'rgba(245,158,11,0.3)' : undefined }}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                        style={{ background: 'var(--accent-muted)' }}>
                        <Brain size={18} style={{ color: 'var(--accent-primary)' }} />
                      </div>
                      <div>
                        <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                          {model.name}
                        </p>
                        <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                          {model.base_model} • {model.parameters || '—'}
                        </p>
                      </div>
                    </div>
                    {statusBadge(model.status, model.progress)}
                  </div>

                  {model.status === 'training' && (
                    <div>
                      <div className="progress-bar">
                        <div className="progress-fill" style={{ width: `${model.progress || 0}%` }} />
                      </div>
                    </div>
                  )}

                  {model.status === 'ready' && (
                    <div className="grid grid-cols-3 gap-3">
                      {[
                        { label: 'Accuracy', value: model.accuracy ? `${(model.accuracy * 100).toFixed(1)}%` : '—', color: '#10b981' },
                        { label: 'F1 Score', value: model.f1_score ? model.f1_score.toFixed(3) : '—', color: '#06b6d4' },
                        { label: 'Type', value: model.task?.split('-')?.[1]?.toUpperCase() || model.task || 'CLASS', color: '#7c3aed' },
                      ].map(({ label, value, color }) => (
                        <div key={label} className="text-center p-2 rounded-lg"
                          style={{ background: 'var(--bg-tertiary)' }}>
                          <p className="text-sm font-bold" style={{ color }}>{value}</p>
                          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</p>
                        </div>
                      ))}
                    </div>
                  )}

                  {model.status === 'stopped' && (
                    <div className="text-center p-3 rounded-lg text-xs" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-muted)' }}>
                      Training stopped. No evaluation metrics available.
                    </div>
                  )}

                  {model.status === 'error' && (
                    <div className="text-center p-3 rounded-lg text-xs text-red-400 bg-red-500/5">
                      Model training failed. Please check logs.
                    </div>
                  )}

                  <div className="flex items-center justify-between pt-1"
                    style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                      {formatSize(model.size_bytes)} • {formatDate(model.created_at)}
                    </span>
                    <div className="flex gap-1">
                      {model.status === 'ready' && (
                        <>
                          <button className="p-1.5 rounded transition-colors"
                            style={{ color: 'var(--text-muted)' }}
                            onMouseEnter={(e) => e.currentTarget.style.color = '#7c3aed'}
                            onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
                            onClick={() => navigate(`/analytics`)}
                            title="View analytics">
                            <BarChart3 size={14} />
                          </button>
                          <button className="p-1.5 rounded transition-colors"
                            style={{ color: 'var(--text-muted)' }}
                            onMouseEnter={(e) => e.currentTarget.style.color = '#06b6d4'}
                            onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
                            onClick={() => toast.success('Downloading model configuration...')}
                            title="Download">
                            <Download size={14} />
                          </button>
                        </>
                      )}
                      <button className="p-1.5 rounded transition-colors"
                        style={{ color: 'var(--text-muted)' }}
                        onMouseEnter={(e) => e.currentTarget.style.color = '#ef4444'}
                        onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
                        onClick={(e) => handleDeleteModel(model.id, e)}
                        title="Delete model">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>

          {models.length > visibleCount && (
            <div className="flex justify-center pt-4">
              <button 
                onClick={() => setVisibleCount(prev => prev + 6)} 
                className="px-5 py-2.5 rounded-xl text-sm font-semibold transition-all hover:scale-105 active:scale-95"
                style={{
                  background: 'var(--accent-primary, #7c3aed)',
                  color: 'white',
                  boxShadow: '0 4px 12px rgba(124, 58, 237, 0.2)'
                }}
              >
                Load More Models ({models.length - visibleCount} remaining)
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
