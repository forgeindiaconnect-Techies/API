import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Key, Plus, Copy, Trash2, Shield, X, Check, Loader, AlertCircle, Edit2 } from 'lucide-react'
import { apiKeyAPI } from '../services/api'
import { useApiKeyStore } from '../store'
import toast from 'react-hot-toast'

export default function ApiKeysPage() {
  const { apiKeys, setApiKeys } = useApiKeyStore()
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  
  // Newly created key modal details (one-time display)
  const [createdKeyData, setCreatedKeyData] = useState(null)
  
  const [copied, setCopied] = useState({})
  const [newKey, setNewKey] = useState({ name: '', scopes: ['chat'], rate_limit: 10000 })

  // Inline renaming states
  const [editingId, setEditingId] = useState(null)
  const [editingName, setEditingName] = useState("")

  const SCOPES = ['chat', 'predict', 'embed', 'transcribe', 'generate-image']

  const fetchKeys = async () => {
    try {
      setLoading(true)
      const { data } = await apiKeyAPI.list()
      setApiKeys(data)
    } catch (err) {
      toast.error('Failed to load API keys')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchKeys()
  }, [])

  const copyKey = (id, key) => {
    if (!key) return
    navigator.clipboard.writeText(key)
    setCopied({ ...copied, [id]: true })
    toast.success('Copied to clipboard')
    setTimeout(() => setCopied(prev => ({ ...prev, [id]: false })), 2000)
  }

  const revokeKey = async (id, name) => {
    const confirmed = window.confirm(`Are you sure you want to revoke the API key "${name}"? This action cannot be undone and external services using it will stop working immediately.`)
    if (!confirmed) return

    try {
      await apiKeyAPI.revoke(id)
      toast.success('API key revoked')
      fetchKeys()
    } catch (err) {
      toast.error('Failed to revoke API key')
    }
  }

  const renameKey = async (id) => {
    if (!editingName.trim()) {
      toast.error('Name cannot be empty')
      return
    }
    try {
      await apiKeyAPI.rename(id, editingName.trim())
      toast.success('API key renamed')
      setEditingId(null)
      setEditingName("")
      fetchKeys()
    } catch (err) {
      toast.error('Failed to rename API key')
    }
  }

  const startRename = (id, name) => {
    setEditingId(id)
    setEditingName(name)
  }

  const cancelRename = () => {
    setEditingId(null)
    setEditingName("")
  }

  const createKey = async () => {
    if (!newKey.name.trim()) { toast.error('Name required'); return }
    try {
      const { data } = await apiKeyAPI.create({
        name: newKey.name,
        scopes: newKey.scopes,
        rate_limit: newKey.rate_limit,
      })
      setCreatedKeyData(data) // Triggers the warning display modal
      setShowCreate(false)
      setNewKey({ name: '', scopes: ['chat'], rate_limit: 10000 })
      toast.success('API key created successfully!')
      fetchKeys()
    } catch (err) {
      toast.error('Failed to generate API key')
    }
  }

  const maskKey = (prefix) => `${prefix || 'sk-••••'}••••••••`

  const formatLastUsed = (dateVal) => {
    if (!dateVal) return 'Never used'
    return new Date(dateVal).toLocaleString()
  }

  return (
    <div className="p-6 space-y-5 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>API Keys</h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Manage access credentials for your models and inference endpoints
          </p>
        </div>
        <button onClick={() => setShowCreate(true)} className="btn-primary">
          <Plus size={14} /> New Key
        </button>
      </div>

      {/* Create Modal */}
      <AnimatePresence>
        {showCreate && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
            onClick={() => setShowCreate(false)}>
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="card-elevated w-full max-w-md p-6 space-y-4"
              onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between">
                <h3 className="font-bold" style={{ color: 'var(--text-primary)' }}>Create API Key</h3>
                <button onClick={() => setShowCreate(false)} style={{ color: 'var(--text-muted)' }}><X size={18} /></button>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>Name</label>
                  <input className="input-base" placeholder="e.g. Production Client" value={newKey.name}
                    onChange={e => setNewKey({ ...newKey, name: e.target.value })} />
                </div>

                <div>
                  <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>Rate Limit (monthly requests)</label>
                  <input type="number" className="input-base" placeholder="10000" value={newKey.rate_limit}
                    onChange={e => setNewKey({ ...newKey, rate_limit: parseInt(e.target.value) || 1000 })} />
                </div>

                <div>
                  <label className="block text-xs font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>
                    Scopes
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {SCOPES.map(s => (
                      <button key={s}
                        onClick={() => {
                          const scopes = newKey.scopes.includes(s)
                            ? newKey.scopes.filter(x => x !== s)
                            : [...newKey.scopes, s]
                          setNewKey({ ...newKey, scopes })
                        }}
                        className={`badge text-xs cursor-pointer transition-all ${newKey.scopes.includes(s) ? 'badge-violet' : ''}`}
                        style={!newKey.scopes.includes(s) ? { background: 'var(--bg-tertiary)', color: 'var(--text-muted)' } : {}}>
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <button onClick={createKey} className="btn-primary w-full justify-center">
                <Key size={14} /> Generate Key
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* One-Time Display Modal for newly created key */}
      <AnimatePresence>
        {createdKeyData && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(5px)' }}
            onClick={() => setCreatedKeyData(null)}>
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="card-elevated w-full max-w-lg p-6 space-y-4"
              onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-lg text-yellow-500" style={{ color: 'var(--text-primary)' }}>Copy your API Key</h3>
                <button onClick={() => setCreatedKeyData(null)} style={{ color: 'var(--text-muted)' }}><X size={18} /></button>
              </div>

              <div className="p-4 rounded-lg bg-yellow-950/20 border border-yellow-700/30 flex items-start gap-3">
                <AlertCircle className="flex-shrink-0 mt-0.5" size={18} style={{ color: '#f59e0b' }} />
                <div className="text-xs space-y-1">
                  <p className="font-semibold text-yellow-500">Copy this key now — it will never be shown again</p>
                  <p style={{ color: 'var(--text-muted)' }}>
                    For security reasons, this key can only be displayed this one time. Save it in a password manager or secure vault. If you close this window, the key cannot be recovered.
                  </p>
                </div>
              </div>

              <div className="space-y-1">
                <label className="block text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>API Key Name</label>
                <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{createdKeyData.name}</p>
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>API Key Value</label>
                <div className="flex items-center gap-2 p-3 rounded-lg"
                  style={{ background: 'var(--bg-tertiary)', fontFamily: 'JetBrains Mono, monospace' }}>
                  <code className="text-xs flex-1 select-all truncate" style={{ color: 'var(--accent-primary)' }}>
                    {createdKeyData.key}
                  </code>
                  <button onClick={() => copyKey('new_key_display', createdKeyData.key)}
                    className="flex-shrink-0 p-1" style={{ color: copied['new_key_display'] ? '#10b981' : 'var(--text-muted)' }}>
                    {copied['new_key_display'] ? <Check size={14} /> : <Copy size={14} />}
                  </button>
                </div>
              </div>

              <button onClick={() => setCreatedKeyData(null)} className="btn-primary w-full justify-center">
                I Have Copied and Saved It
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Keys List */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2].map(n => (
            <div key={n} className="h-28 w-full rounded-xl animate-pulse card" />
          ))}
        </div>
      ) : apiKeys.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col items-center justify-center p-12 text-center card min-h-[260px] space-y-4"
        >
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center" style={{ background: 'var(--accent-muted)' }}>
            <Key size={28} style={{ color: 'var(--accent-primary)' }} />
          </div>
          <div className="space-y-1">
            <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>No API Keys Generated</h3>
            <p className="text-sm max-w-sm" style={{ color: 'var(--text-muted)' }}>
              Generate API keys to grant external client applications secure access to your trained AI model inference endpoints.
            </p>
          </div>
          <button onClick={() => setShowCreate(true)} className="btn-primary mt-2">
            <Plus size={14} /> Generate First API Key
          </button>
        </motion.div>
      ) : (
        <div className="space-y-3">
          {apiKeys.map((k, i) => (
            <motion.div key={k.id} className="card p-5"
              initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: k.is_active ? 'rgba(16,185,129,0.1)' : 'var(--bg-tertiary)' }}>
                    <Key size={15} style={{ color: k.is_active ? '#10b981' : 'var(--text-muted)' }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    {editingId === k.id ? (
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <input
                          className="input-base text-sm py-1 px-2.5 max-w-[240px]"
                          value={editingName}
                          onChange={e => setEditingName(e.target.value)}
                          autoFocus
                          onKeyDown={e => {
                            if (e.key === 'Enter') renameKey(k.id)
                            if (e.key === 'Escape') cancelRename()
                          }}
                        />
                        <button onClick={() => renameKey(k.id)} className="p-1 rounded bg-green-500/10 text-green-400 hover:bg-green-500/20" title="Save">
                          <Check size={14} />
                        </button>
                        <button onClick={cancelRename} className="p-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20" title="Cancel">
                          <X size={14} />
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <p className="font-semibold text-sm truncate" style={{ color: 'var(--text-primary)' }}>{k.name}</p>
                        {k.is_active && (
                          <button onClick={() => startRename(k.id, k.name)} className="p-0.5 text-slate-500 hover:text-slate-300 transition-colors" title="Rename Key">
                            <Edit2 size={12} />
                          </button>
                        )}
                      </div>
                    )}
                    <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                      Created {new Date(k.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                <span className={`badge ${k.is_active ? 'badge-green' : 'badge-red'}`}>
                  {k.is_active ? 'Active' : 'Revoked'}
                </span>
              </div>

              {/* Key Value */}
              <div className="flex items-center justify-between gap-2 p-3 rounded-lg mb-3"
                style={{ background: 'var(--bg-tertiary)', fontFamily: 'JetBrains Mono, monospace' }}>
                <code className="text-xs flex-1 truncate" style={{ color: 'var(--text-secondary)' }}>
                  {maskKey(k.key_prefix)}
                </code>
                {k.is_active && (
                  <button onClick={() => copyKey(k.id, maskKey(k.key_prefix))}
                    className="flex-shrink-0 p-1 text-slate-500 hover:text-slate-300 transition-colors"
                    title="Copy Prefix">
                    <Copy size={13} />
                  </button>
                )}
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex gap-1 flex-wrap">
                    {k.scopes.map(s => <span key={s} className="badge badge-violet text-xs">{s}</span>)}
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {k.requests_count.toLocaleString()} / {k.rate_limit.toLocaleString()}
                    </p>
                    <p className="text-xs" style={{ color: 'var(--text-muted)' }}>requests</p>
                  </div>
                  <div className="w-20">
                    <div className="progress-bar">
                      <div className="progress-fill" style={{ width: `${Math.min(100, (k.requests_count / k.rate_limit) * 100)}%` }} />
                    </div>
                  </div>
                  <div className="text-right min-w-[120px]">
                    <p className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: 'var(--text-muted)' }}>Last Used</p>
                    <p className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{formatLastUsed(k.last_used)}</p>
                  </div>
                  {k.is_active && (
                    <button onClick={() => revokeKey(k.id, k.name)}
                      className="p-1.5 rounded transition-colors"
                      style={{ color: 'var(--text-muted)' }}
                      onMouseEnter={(e) => e.currentTarget.style.color = '#ef4444'}
                      onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
                      title="Revoke Key">
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* API Docs hint */}
      <div className="card p-4 flex items-center gap-3">
        <Shield size={16} style={{ color: 'var(--accent-primary)' }} />
        <div>
          <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            Using the API
          </p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Include your key as: <code className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'var(--bg-tertiary)', color: 'var(--accent-primary)' }}>
              Authorization: Bearer your-full-api-key
            </code>
          </p>
        </div>
      </div>
    </div>
  )
}
