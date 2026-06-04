import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useDropzone } from 'react-dropzone'
import {
  Upload, File, FileText, Table, Image, Mic, Archive,
  Trash2, Eye, Play, Search, Filter, X, CheckCircle,
  Clock, AlertCircle, MoreHorizontal
} from 'lucide-react'
import { useDatasetStore } from '../store'
import toast from 'react-hot-toast'

const fileTypeIcon = (type) => {
  if (['csv', 'xlsx'].includes(type)) return Table
  if (['pdf', 'txt', 'docx'].includes(type)) return FileText
  if (['jpg', 'png', 'jpeg'].includes(type)) return Image
  if (['mp3', 'wav'].includes(type)) return Mic
  if (type === 'zip') return Archive
  return File
}

const statusBadge = (status) => {
  switch (status) {
    case 'ready': return <span className="badge badge-green flex items-center gap-1"><CheckCircle size={9} /> Ready</span>
    case 'processing': return <span className="badge badge-yellow flex items-center gap-1"><Clock size={9} /> Processing</span>
    case 'error': return <span className="badge badge-red flex items-center gap-1"><AlertCircle size={9} /> Error</span>
    default: return <span className="badge badge-violet flex items-center gap-1"><Clock size={9} /> Pending</span>
  }
}

const mockDatasets = [
  { id: '1', name: 'customer_churn.csv', type: 'csv', size: 2400000, rows: 10000, cols: 24, status: 'ready', created_at: '2024-01-15' },
  { id: '2', name: 'product_reviews.xlsx', type: 'xlsx', size: 5600000, rows: 50000, cols: 8, status: 'ready', created_at: '2024-01-14' },
  { id: '3', name: 'knowledge_base.pdf', type: 'pdf', size: 1200000, rows: null, cols: null, status: 'ready', created_at: '2024-01-13' },
  { id: '4', name: 'training_images.zip', type: 'zip', size: 150000000, rows: 5000, cols: null, status: 'processing', created_at: '2024-01-12' },
  { id: '5', name: 'support_tickets.txt', type: 'txt', size: 800000, rows: 3200, cols: null, status: 'ready', created_at: '2024-01-11' },
]

const formatSize = (bytes) => {
  if (bytes > 1e9) return `${(bytes / 1e9).toFixed(1)} GB`
  if (bytes > 1e6) return `${(bytes / 1e6).toFixed(1)} MB`
  return `${(bytes / 1e3).toFixed(0)} KB`
}

export default function DatasetsPage() {
  const navigate = useNavigate()
  const { datasets, addDataset, removeDataset, uploadProgress } = useDatasetStore()
  const [uploading, setUploading] = useState(false)
  const [search, setSearch] = useState('')
  const [allDatasets] = useState(mockDatasets)
  const [showUpload, setShowUpload] = useState(false)

  const onDrop = useCallback(async (acceptedFiles) => {
    setUploading(true)
    for (const file of acceptedFiles) {
      const id = Date.now().toString()
      const ext = file.name.split('.').pop().toLowerCase()

      // Simulate upload
      const newDs = {
        id,
        name: file.name,
        type: ext,
        size: file.size,
        rows: null,
        cols: null,
        status: 'processing',
        created_at: new Date().toISOString().split('T')[0],
      }
      addDataset(newDs)
      toast.success(`Uploading ${file.name}...`)

      // Simulate processing
      setTimeout(() => {
        toast.success(`${file.name} processed successfully`)
      }, 3000)
    }
    setUploading(false)
    setShowUpload(false)
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/pdf': ['.pdf'],
      'text/plain': ['.txt'],
      'application/zip': ['.zip'],
      'image/*': ['.jpg', '.jpeg', '.png'],
      'audio/*': ['.mp3', '.wav'],
    },
  })

  const displayed = [...allDatasets, ...datasets].filter(d =>
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
                <Upload size={32} className="mx-auto mb-3" style={{ color: 'var(--accent-primary)' }} />
                <p className="font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
                  {isDragActive ? 'Drop files here' : 'Drag & drop files'}
                </p>
                <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                  or click to browse
                </p>
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

      {/* Datasets Table */}
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
          <div className="w-20">Actions</div>
        </div>

        {displayed.map((ds, i) => {
          const Icon = fileTypeIcon(ds.type)
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
                <span className="badge badge-violet text-xs uppercase">{ds.type}</span>
              </div>
              <div className="w-24 text-xs" style={{ color: 'var(--text-secondary)' }}>
                {formatSize(ds.size)}
              </div>
              <div className="w-20 text-xs" style={{ color: 'var(--text-secondary)' }}>
                {ds.rows?.toLocaleString() || '—'}
              </div>
              <div className="w-24">{statusBadge(ds.status)}</div>
              <div className="w-24 text-xs" style={{ color: 'var(--text-muted)' }}>
                {ds.created_at}
              </div>
              <div className="w-20 flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
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
                <button
                  onClick={() => toast.success('Processing started')}
                  className="p-1.5 rounded transition-colors"
                  style={{ color: 'var(--text-muted)' }}
                  onMouseEnter={(e) => e.currentTarget.style.color = '#10b981'}
                  onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
                  title="Process"
                >
                  <Play size={13} />
                </button>
              </div>
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}
