import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, Database, Plus, Zap, FileText, Loader, Trash2, X, AlertCircle } from 'lucide-react'
import { ragAPI, datasetAPI } from '../services/api'
import toast from 'react-hot-toast'

export default function RAGPage() {
  const [indexes, setIndexes] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedIndex, setSelectedIndex] = useState(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [aiAnswer, setAiAnswer] = useState('')
  const [searching, setSearching] = useState(false)
  
  // Create index modal state
  const [showCreateIndex, setShowCreateIndex] = useState(false)
  const [datasets, setDatasets] = useState([])
  const [loadingDatasets, setLoadingDatasets] = useState(false)
  const [indexForm, setIndexForm] = useState({
    name: '',
    dataset_id: '',
    embedding_model: 'all-MiniLM-L6-v2',
    chunk_size: 512,
    chunk_overlap: 50,
  })

  const fetchIndexes = async () => {
    try {
      setLoading(true)
      const { data } = await ragAPI.listIndexes()
      setIndexes(data)
      if (data.length > 0 && !selectedIndex) {
        const readyIdx = data.find(idx => idx.status === 'ready')
        if (readyIdx) {
          setSelectedIndex(readyIdx.id)
        }
      }
    } catch (err) {
      toast.error('Failed to load vector indexes')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchIndexes()
  }, [])

  // Poll indexes if any are building
  useEffect(() => {
    const buildingIndex = indexes.some(idx => idx.status === 'building')
    if (!buildingIndex) return

    const interval = setInterval(async () => {
      try {
        const { data } = await ragAPI.listIndexes()
        setIndexes(data)
        setSelectedIndex(prev => {
          if (!prev) {
            const readyIdx = data.find(idx => idx.status === 'ready')
            return readyIdx ? readyIdx.id : null
          }
          const selected = data.find(idx => idx.id === prev)
          if (selected && selected.status === 'ready') {
            return prev
          }
          const readyIdx = data.find(idx => idx.status === 'ready')
          return readyIdx ? readyIdx.id : null
        })
      } catch (err) {
        console.error('Failed to poll index status', err)
      }
    }, 5000)

    return () => clearInterval(interval)
  }, [indexes])

  const loadDatasets = async () => {
    try {
      setLoadingDatasets(true)
      const { data } = await datasetAPI.list()
      // Only keep ready tabular/text files for indexing
      setDatasets(data.filter(d => d.status === 'ready' || d.status === 'completed'))
    } catch (err) {
      toast.error('Failed to load datasets')
    } finally {
      setLoadingDatasets(false)
    }
  }

  const openCreateModal = () => {
    setShowCreateIndex(true)
    loadDatasets()
  }

  const handleCreateIndex = async () => {
    if (!indexForm.name.trim()) { toast.error('Index name required'); return }
    if (!indexForm.dataset_id) { toast.error('Please select a dataset'); return }

    try {
      const { data } = await ragAPI.createIndex(indexForm.dataset_id, {
        name: indexForm.name,
        embedding_model: indexForm.embedding_model,
        chunk_size: indexForm.chunk_size,
        chunk_overlap: indexForm.chunk_overlap,
      })
      toast.success('Vector index build started!')
      setIndexes(prev => [...prev, data])
      setSelectedIndex(data.id)
      setShowCreateIndex(false)
      setIndexForm({
        name: '',
        dataset_id: '',
        embedding_model: 'all-MiniLM-L6-v2',
        chunk_size: 512,
        chunk_overlap: 50,
      })
    } catch (err) {
      toast.error('Failed to initiate index build')
    }
  }

  const handleDeleteIndex = async (id, name, e) => {
    e.stopPropagation()
    try {
      await ragAPI.deleteIndex(id)
      setIndexes(prev => prev.filter(x => x.id !== id))
      toast.success(`Index "${name}" deleted`)
      if (selectedIndex === id) {
        setSelectedIndex(null)
      }
    } catch (err) {
      toast.error('Failed to delete vector index')
    }
  }

  const handleSearch = async () => {
    if (!query.trim() || !selectedIndex) return
    setSearching(true)
    setResults([])
    setAiAnswer('')
    try {
      const res = await ragAPI.chat(selectedIndex, query)
      setAiAnswer(res.data.answer)
      setResults(res.data.sources || [])
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to search vector index')
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="p-6 space-y-5 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>RAG Search</h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Retrieval-Augmented Generation over your datasets
          </p>
        </div>
        <button onClick={openCreateModal} className="btn-primary">
          <Plus size={14} /> Create Index
        </button>
      </div>

      {/* Create Modal */}
      <AnimatePresence>
        {showCreateIndex && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
            onClick={() => setShowCreateIndex(false)}>
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="card-elevated w-full max-w-md p-6 space-y-4"
              onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between">
                <h3 className="font-bold" style={{ color: 'var(--text-primary)' }}>Create Vector Index</h3>
                <button onClick={() => setShowCreateIndex(false)} style={{ color: 'var(--text-muted)' }}><X size={18} /></button>
              </div>

              <div className="space-y-3 text-xs">
                <div>
                  <label className="block font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>Index Name</label>
                  <input className="input-base text-xs" placeholder="e.g. customer-kb" value={indexForm.name}
                    onChange={e => setIndexForm({ ...indexForm, name: e.target.value })} />
                </div>

                <div>
                  <label className="block font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>Select Dataset</label>
                  {loadingDatasets ? (
                    <div className="flex items-center gap-1.5 py-2">
                      <Loader size={12} className="animate-spin" /> Loading datasets...
                    </div>
                  ) : datasets.length === 0 ? (
                    <div className="text-red-400 py-1 flex items-center gap-1">
                      <AlertCircle size={12} /> No ready datasets available. Please upload a dataset first.
                    </div>
                  ) : (
                    <select className="input-base text-xs" style={{ background: 'var(--bg-tertiary)' }}
                      value={indexForm.dataset_id}
                      onChange={e => setIndexForm({ ...indexForm, dataset_id: e.target.value })}>
                      <option value="">-- Choose Dataset --</option>
                      {datasets.map(d => (
                        <option key={d.id} value={d.id}>{d.name} ({d.file_type})</option>
                      ))}
                    </select>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>Chunk Size</label>
                    <input type="number" className="input-base text-xs" value={indexForm.chunk_size}
                      onChange={e => setIndexForm({ ...indexForm, chunk_size: parseInt(e.target.value) || 512 })} />
                  </div>
                  <div>
                    <label className="block font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>Chunk Overlap</label>
                    <input type="number" className="input-base text-xs" value={indexForm.chunk_overlap}
                      onChange={e => setIndexForm({ ...indexForm, chunk_overlap: parseInt(e.target.value) || 50 })} />
                  </div>
                </div>
              </div>

              <button onClick={handleCreateIndex} disabled={datasets.length === 0} className="btn-primary w-full justify-center mt-2">
                <Database size={14} /> Start Building Index
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {loading ? (
        <div className="flex flex-col items-center justify-center min-h-[300px]">
          <Loader size={32} className="animate-spin" style={{ color: 'var(--accent-primary)' }} />
          <p className="text-sm mt-2" style={{ color: 'var(--text-muted)' }}>Loading vector indexes...</p>
        </div>
      ) : indexes.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col items-center justify-center p-12 text-center card min-h-[300px] space-y-4"
        >
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center" style={{ background: 'var(--accent-muted)' }}>
            <Database size={28} style={{ color: 'var(--accent-primary)' }} />
          </div>
          <div className="space-y-1">
            <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>No Vector Indexes Created</h3>
            <p className="text-sm max-w-sm" style={{ color: 'var(--text-muted)' }}>
              Create a vector index to enable Retrieval-Augmented Generation (RAG) over your uploaded files.
            </p>
          </div>
          <button onClick={openCreateModal} className="btn-primary mt-2">
            <Plus size={14} /> Create First Vector Index
          </button>
        </motion.div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
          {/* Indexes Sidebar */}
          <div className="space-y-3">
            <p className="section-title">Vector Indexes</p>
            {indexes.map((idx) => {
              const isActive = selectedIndex === idx.id
              const isReady = idx.status === 'ready'
              const isBuilding = idx.status === 'building'
              return (
                <div
                  key={idx.id}
                  onClick={() => isReady && setSelectedIndex(idx.id)}
                  className={`w-full group flex items-start justify-between p-3 rounded-xl transition-all ${isReady ? 'cursor-pointer' : 'cursor-not-allowed opacity-75'} ${isActive ? 'bg-[var(--accent-muted)] border-[var(--accent-primary)]' : 'bg-[var(--bg-secondary)] border-[var(--border)]'}`}
                  style={{ border: '1px solid' }}
                >
                  <div className="min-w-0 mr-2">
                    <div className="flex items-center gap-2 mb-1">
                      <Database size={13} style={{ color: isActive ? 'var(--accent-primary)' : 'var(--text-muted)' }} />
                      <span className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
                        {idx.name}
                      </span>
                    </div>
                    {isBuilding ? (
                      <span className="text-[10px] text-yellow-400 flex items-center gap-1 font-medium">
                        <Loader size={10} className="animate-spin" /> Building ({Math.round(idx.progress || 10)}%)...
                      </span>
                    ) : idx.status === 'failed' ? (
                      <span className="text-[10px] text-red-400 flex items-center gap-1 font-medium" title={idx.error || 'Indexing failed'}>
                        <AlertCircle size={10} /> Failed: {idx.error || 'Indexing failed'}
                      </span>
                    ) : (
                      <>
                        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{idx.chunk_count} chunks</p>
                        <p className="text-[10px] mt-0.5 truncate" style={{ color: 'var(--text-muted)' }}>ID: {idx.id}</p>
                      </>
                    )}
                  </div>
                  <button onClick={(e) => handleDeleteIndex(idx.id, idx.name, e)}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-slate-700/50 text-slate-400 hover:text-red-400 transition-opacity">
                    <Trash2 size={12} />
                  </button>
                </div>
              )
            })}
          </div>

          {/* Search Area */}
          <div className="lg:col-span-3 space-y-4">
            {/* Search Input */}
            <div className="card p-4">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
                  <input
                    className="input-base pl-9 text-sm"
                    placeholder="Ask a question about your indexed data..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                    disabled={searching}
                  />
                </div>
                <button onClick={handleSearch} disabled={searching || !query.trim() || !selectedIndex} className="btn-primary px-4">
                  {searching ? <Loader size={14} className="animate-spin" /> : <Zap size={14} />}
                  Search
                </button>
              </div>
              {selectedIndex && (
                <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                  Active Index: <strong style={{ color: 'var(--accent-primary)' }}>
                    {indexes.find(i => i.id === selectedIndex)?.name}
                  </strong>
                </p>
              )}
            </div>

            {/* AI Answer */}
            <AnimatePresence>
              {aiAnswer && (
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card p-5 gradient-border">
                  <div className="flex items-center gap-2 mb-3">
                    <Zap size={14} style={{ color: 'var(--accent-primary)' }} />
                    <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>AI Answer</p>
                  </div>
                  <p className="text-sm whitespace-pre-line leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                    {aiAnswer}
                  </p>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Retrieved Chunks */}
            {results.length > 0 && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-3">
                <p className="section-title">Retrieved Chunks ({results.length})</p>
                {results.map((r, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.1 }}
                    className="card p-4"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <FileText size={12} style={{ color: 'var(--text-muted)' }} />
                        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                          {r.source}
                        </span>
                      </div>
                      <span className="badge badge-green text-xs">
                        {(r.score * 100).toFixed(0)}% match
                      </span>
                    </div>
                    <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                      {r.content}
                    </p>
                  </motion.div>
                ))}
              </motion.div>
            )}

            {!results.length && !searching && !aiAnswer && (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <Search size={32} className="mb-3" style={{ color: 'var(--text-muted)' }} />
                <p className="font-semibold" style={{ color: 'var(--text-secondary)' }}>
                  Ask a question
                </p>
                <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
                  Enter a question to search your indexed documents
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
