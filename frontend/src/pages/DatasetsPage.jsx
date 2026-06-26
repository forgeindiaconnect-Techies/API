import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useDropzone } from 'react-dropzone'
import {
  Upload, File, FileText, Table, Image, Mic, Archive,
  Trash2, Eye, Play, Search, X, CheckCircle,
  Clock, AlertCircle, Loader, AlertTriangle
} from 'lucide-react'
import { useDatasetStore } from '../store'
import { datasetAPI } from '../services/api'
import toast from 'react-hot-toast'

const fileTypeIcon = (type) => {
  if (['csv', 'xlsx', 'xls'].includes(type)) return Table
  if (['pdf', 'txt', 'docx', 'md', 'json'].includes(type)) return FileText
  if (['jpg', 'png', 'jpeg', 'webp', 'gif'].includes(type)) return Image
  if (['mp3', 'wav', 'm4a'].includes(type)) return Mic
  if (type === 'zip') return Archive
  return File
}

const isIrrecoverableDataset = (ds) => {
  return ds.status === 'failed' &&
    ds.error_message &&
    (ds.error_message.includes('All recovery methods') ||
     ds.error_message.includes('Local File was MISSING') ||
     ds.error_message.includes('File Recovery Failure') ||
     ds.error_message.includes('File Access Failure'))
}

const statusBadge = (ds) => {
  if (isIrrecoverableDataset(ds)) {
    return <span className="badge badge-yellow flex items-center gap-1"><AlertTriangle size={9} /> Re-upload</span>
  }
  switch (ds.status) {
    case 'ready':
    case 'completed':
    case 'indexed':
      return <span className="badge badge-green flex items-center gap-1"><CheckCircle size={9} /> Ready</span>
    case 'processing':
      return <span className="badge badge-yellow flex items-center gap-1"><Clock size={9} /> Processing</span>
    case 'error':
    case 'failed':
      return <span className="badge badge-red flex items-center gap-1"><AlertCircle size={9} /> Error</span>
    default:
      return <span className="badge badge-violet flex items-center gap-1"><Clock size={9} /> Pending</span>
  }
}

const formatSize = (bytes) => {
  if (!bytes) return '0 KB'
  if (bytes > 1e9) return `${(bytes / 1e9).toFixed(1)} GB`
  if (bytes > 1e6) return `${(bytes / 1e6).toFixed(1)} MB`
  return `${(bytes / 1e3).toFixed(0)} KB`
}

export default function DatasetsPage() {
  const navigate = useNavigate()
  const { datasets, setDatasets, addDataset, removeDataset, updateDataset } = useDatasetStore()
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [search, setSearch] = useState('')
  const [showUpload, setShowUpload] = useState(false)

  const fetchDatasets = async () => {
    try {
      setLoading(true)
      const { data } = await datasetAPI.list()
      setDatasets(data)
    } catch (err) {
      toast.error('Failed to load datasets')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDatasets()
  }, [])

  // Poll status of processing/pending datasets to update UI reactively
  useEffect(() => {
    const processing = datasets.filter(d => {
      const s = (d.status || '').toLowerCase()
      return ['processing', 'pending', 'uploaded', 'saved', 'reading_file', 'preprocessing', 'chunking', 'embedding', 'embedded', 'extracted'].includes(s)
    })
    if (processing.length === 0) return

    const interval = setInterval(async () => {
      for (const ds of processing) {
        try {
          const { data } = await datasetAPI.getStatus(ds.id)
          const currentStatus = (data.status || '').toLowerCase()
          if (['indexed', 'ready', 'completed'].includes(currentStatus)) {
            const detailRes = await datasetAPI.get(ds.id)
            updateDataset(ds.id, {
              ...detailRes.data,
              status: 'ready'
            })
            toast.success(`Dataset "${ds.name}" is processed and ready!`)
          } else if (currentStatus === 'failed' || currentStatus === 'error') {
            updateDataset(ds.id, {
              status: 'error',
              error_message: data.error || data.error_message || 'Indexing task failed.'
            })
            toast.error(`Dataset "${ds.name}" processing failed: ${data.error || data.error_message || 'Indexing task failed.'}`)
          }
        } catch (err) {
          console.error(`Error polling status for dataset ${ds.id}:`, err)
        }
      }
    }, 3000)

    return () => clearInterval(interval)
  }, [datasets, updateDataset])

  const uploadWithRetry = async (file, maxRetries = 3, baseDelayMs = 1500) => {
    let attempt = 0
    while (attempt < maxRetries) {
      try {
        const formData = new FormData()
        formData.append('file', file)
        const onProgress = (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          setUploadProgress(percentCompleted)
        }
        const { data } = await datasetAPI.upload(formData, onProgress)
        return data
      } catch (err) {
        attempt++
        if (attempt >= maxRetries) {
          throw err
        }
        const currentDelay = baseDelayMs * Math.pow(2, attempt - 1)
        toast.error(`Upload failed for ${file.name}. Retrying attempt ${attempt}/${maxRetries} in ${currentDelay / 1000}s...`)
        await new Promise((resolve) => setTimeout(resolve, currentDelay))
      }
    }
  }

  const onDrop = useCallback(async (acceptedFiles) => {
    const allowedExtensions = ['csv', 'xlsx', 'xls', 'pdf', 'txt', 'docx', 'jpg', 'jpeg', 'png', 'webp', 'mp3', 'wav', 'm4a', 'zip']
    const maxSizeBytes = 500 * 1024 * 1024 // 500MB

    const validFiles = []
    for (const file of acceptedFiles) {
      const ext = file.name.split('.').pop().toLowerCase()
      if (!allowedExtensions.includes(ext)) {
        toast.error(`File type .${ext} is not supported.`)
        continue
      }
      if (file.size > maxSizeBytes) {
        toast.error(`File ${file.name} exceeds the 500MB limit.`)
        continue
      }
      validFiles.push(file)
    }

    if (validFiles.length === 0) return

    setUploading(true)
    setUploadProgress(0)

    for (const file of validFiles) {
      try {
        const data = await uploadWithRetry(file)
        addDataset(data)
        toast.success(`${file.name} uploaded successfully and started processing!`)
      } catch (err) {
        let errMsg = 'Network Error'
        if (err.response) {
          const data = err.response.data
          if (data) {
            if (typeof data === 'string') errMsg = data
            else if (data.detail) {
              errMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
            } else if (data.message) errMsg = data.message
            else if (data.error) errMsg = data.error
          } else {
            errMsg = `Server Error (${err.response.status})`
          }
        } else if (err.request) {
          if (err.code === 'ECONNABORTED') {
            errMsg = 'Upload timed out (120 seconds limit exceeded)'
          } else {
            errMsg = 'Connection failed (CORS block, protocol error, or server crashed)'
          }
        } else {
          errMsg = err.message || 'Unexpected setup error'
        }
        toast.error(`Upload failed for ${file.name} after 3 attempts: ${errMsg}`)
      }
    }

    setUploading(false)
    setUploadProgress(0)
    setShowUpload(false)
  }, [addDataset])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
      'application/pdf': ['.pdf'],
      'text/plain': ['.txt'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/zip': ['.zip'],
      'application/x-zip-compressed': ['.zip'],
      'image/jpeg': ['.jpeg', '.jpg'],
      'image/png': ['.png'],
      'image/webp': ['.webp'],
      'audio/mpeg': ['.mp3'],
      'audio/mp3': ['.mp3'],
      'audio/wav': ['.wav'],
      'audio/x-m4a': ['.m4a'],
    },
  })

  const handleDelete = async (id, name, e) => {
    e.stopPropagation()
    try {
      await datasetAPI.delete(id)
      removeDataset(id)
      toast.success(`${name} deleted`)
    } catch (err) {
      toast.error(`Failed to delete: ${err.response?.data?.detail || err.message}`)
    }
  }

  const handleReprocess = async (id, e) => {
    e.stopPropagation()
    try {
      await datasetAPI.process(id, {})
      toast.success('Reprocessing scheduled')
      fetchDatasets()
    } catch (err) {
      toast.error(`Failed to reprocess: ${err.response?.data?.detail || err.message}`)
    }
  }

  const displayed = datasets.filter(d =>
    d.name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="p-6 space-y-5 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>Datasets</h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
            {displayed.length} datasets uploaded
          </p>
        </div>
        <button onClick={() => setShowUpload(true)} className="btn-primary">
          <Upload size={14} /> Upload Dataset
        </button>
      </div>

      {/* Upload Modal */}
      <AnimatePresence>
        {showUpload && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
            onClick={() => setShowUpload(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="card-elevated w-full max-w-lg p-6"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-bold" style={{ color: 'var(--text-primary)' }}>Upload Dataset</h3>
                <button onClick={() => setShowUpload(false)} style={{ color: 'var(--text-muted)' }}>
                  <X size={18} />
                </button>
              </div>

              <div
                {...getRootProps()}
                className={`upload-zone p-8 text-center cursor-pointer ${isDragActive ? 'drag-active' : ''}`}
              >
                <input {...getInputProps()} />
                {uploading ? (
                  <div className="space-y-4">
                    <Loader size={32} className="mx-auto animate-spin" style={{ color: 'var(--accent-primary)' }} />
                    <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Uploading to server...</p>
                    
                    {/* Progress Bar */}
                    <div className="w-full bg-slate-700/60 rounded-full h-2 mt-2 overflow-hidden max-w-xs mx-auto">
                      <div
                        className="bg-violet-600 h-2 rounded-full transition-all duration-300 ease-out"
                        style={{ width: `${uploadProgress}%` }}
                      />
                    </div>
                    <p className="text-xs font-medium text-slate-400">
                      {uploadProgress}% completed
                    </p>
                  </div>
                ) : (
                  <>
                    <Upload size={32} className="mx-auto mb-3" style={{ color: 'var(--accent-primary)' }} />
                    <p className="font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
                      {isDragActive ? 'Drop files here' : 'Drag & drop files'}
                    </p>
                    <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                      or click to browse
                    </p>
                  </>
                )}
                <div className="flex flex-wrap justify-center gap-1.5 mt-4">
                  {['CSV', 'XLSX', 'PDF', 'TXT', 'DOCX', 'JPG', 'MP3', 'ZIP'].map(t => (
                    <span key={t} className="badge badge-violet text-xs">{t}</span>
                  ))}
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Search */}
      {datasets.length > 0 && (
        <div className="flex gap-3">
          <div className="relative flex-1 max-w-sm">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
            <input
              className="input-base pl-9"
              placeholder="Search datasets..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
      )}

      {/* Datasets Content */}
      {loading ? (
        <div className="grid grid-cols-1 gap-3">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-16 w-full rounded-xl animate-pulse card flex items-center justify-between px-4">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-slate-700/50" />
                <div className="space-y-1.5">
                  <div className="h-3 w-40 rounded bg-slate-700/50" />
                  <div className="h-2.5 w-20 rounded bg-slate-700/50" />
                </div>
              </div>
              <div className="h-4 w-24 rounded bg-slate-700/50" />
            </div>
          ))}
        </div>
      ) : datasets.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col items-center justify-center p-12 text-center card min-h-[300px] space-y-4"
        >
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center" style={{ background: 'var(--accent-muted)' }}>
            <Upload size={28} style={{ color: 'var(--accent-primary)' }} />
          </div>
          <div className="space-y-1">
            <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>No Datasets Uploaded</h3>
            <p className="text-sm max-w-sm" style={{ color: 'var(--text-muted)' }}>
              Upload your CSV, Excel, PDF, or text files to begin. The system will perform automatic EDA and structure your data.
            </p>
          </div>
          <button onClick={() => setShowUpload(true)} className="btn-primary mt-2">
            <Upload size={14} /> Upload First Dataset
          </button>
        </motion.div>
      ) : (
        <div className="card overflow-hidden">
          {/* Table header */}
          <div className="flex items-center gap-4 px-4 py-3 text-xs font-semibold"
            style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-muted)' }}>
            <div className="flex-1">Name</div>
            <div className="w-20">Type</div>
            <div className="w-24">Size</div>
            <div className="w-20">Rows</div>
            <div className="w-24">Status</div>
            <div className="w-24">Date</div>
            <div className="w-20 text-right">Actions</div>
          </div>

          {displayed.map((ds, i) => {
            const Icon = fileTypeIcon(ds.file_type)
            return (
              <motion.div
                key={ds.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: i * 0.04 }}
                className="flex items-center gap-4 px-4 py-3 cursor-pointer"
                style={{ borderBottom: '1px solid var(--border-subtle)' }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-tertiary)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                onClick={() => navigate(`/datasets/${ds.id}`)}
              >
                <div className="flex-1 flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: 'var(--bg-tertiary)' }}>
                    <Icon size={14} style={{ color: 'var(--accent-primary)' }} />
                  </div>
                  <span className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                    {ds.name}
                  </span>
                </div>
                <div className="w-20">
                  <span className="badge badge-violet text-xs uppercase">{ds.file_type}</span>
                </div>
                <div className="w-24 text-xs" style={{ color: 'var(--text-secondary)' }}>
                  {formatSize(ds.size_bytes)}
                </div>
                <div className="w-20 text-xs" style={{ color: 'var(--text-secondary)' }}>
                  {ds.rows?.toLocaleString() || '—'}
                </div>
                <div className="w-24">{statusBadge(ds)}</div>
                <div className="w-24 text-xs" style={{ color: 'var(--text-muted)' }}>
                  {ds.created_at ? new Date(ds.created_at).toLocaleDateString() : '—'}
                </div>
                <div className="w-20 flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => navigate(`/datasets/${ds.id}`)}
                    className="p-1.5 rounded transition-colors"
                    style={{ color: 'var(--text-muted)' }}
                    onMouseEnter={(e) => e.currentTarget.style.color = 'var(--accent-primary)'}
                    onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
                    title="View"
                  >
                    <Eye size={13} />
                  </button>
                  {isIrrecoverableDataset(ds) ? (
                    <button
                      onClick={(e) => { e.stopPropagation(); navigate(`/datasets/${ds.id}`) }}
                      className="p-1.5 rounded transition-colors"
                      style={{ color: '#f59e0b' }}
                      title="File lost — click to view and delete"
                    >
                      <AlertTriangle size={13} />
                    </button>
                  ) : (
                    <button
                      onClick={(e) => handleReprocess(ds.id, e)}
                      className="p-1.5 rounded transition-colors"
                      style={{ color: 'var(--text-muted)' }}
                      onMouseEnter={(e) => e.currentTarget.style.color = '#10b981'}
                      onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
                      title="Process"
                    >
                      <Play size={13} />
                    </button>
                  )}
                  <button
                    onClick={(e) => handleDelete(ds.id, ds.name, e)}
                    className="p-1.5 rounded transition-colors"
                    style={{ color: 'var(--text-muted)' }}
                    onMouseEnter={(e) => e.currentTarget.style.color = '#ef4444'}
                    onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
                    title="Delete"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </motion.div>
            )
          })}
        </div>
      )}
    </div>
  )
}
