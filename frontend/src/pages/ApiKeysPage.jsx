import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Key, Plus, Copy, Trash2, Eye, EyeOff, Shield, Activity, X, Check } from 'lucide-react'
import toast from 'react-hot-toast'

const mockKeys = [
  { id: '1', name: 'Production API', key: 'sk-prod-aX3kL9mN2pQ7rS4tU6vW8xY0zA1bC5dE', scopes: ['chat', 'predict', 'embed'], requests: 12450, limit: 50000, status: 'active', created_at: '2024-01-10', last_used: '2m ago' },
  { id: '2', name: 'Development', key: 'sk-dev-bC3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW', scopes: ['chat'], requests: 2340, limit: 10000, status: 'active', created_at: '2024-01-12', last_used: '1h ago' },
  { id: '3', name: 'Testing Key', key: 'sk-test-xY0zA1bC3dE5fG7hI9jK1lM3nO5pQ7r', scopes: ['chat', 'predict'], requests: 890, limit: 5000, status: 'inactive', created_at: '2024-01-05', last_used: '3d ago' },
]

export default function ApiKeysPage() {
  const [keys, setKeys] = useState(mockKeys)
  const [showCreate, setShowCreate] = useState(false)
  const [revealed, setRevealed] = useState({})
  const [copied, setCopied] = useState({})
  const [newKey, setNewKey] = useState({ name: '', scopes: ['chat'] })

  const SCOPES = ['chat', 'predict', 'embed', 'transcribe', 'generate-image']

  const copyKey = (id, key) => {
    navigator.clipboard.writeText(key)
    setCopied({ ...copied, [id]: true })
    toast.success('Copied to clipboard')
    setTimeout(() => setCopied(prev => ({ ...prev, [id]: false })), 2000)
  }

  const revokeKey = (id) => {
    setKeys(keys.filter(k => k.id !== id))
    toast.success('API key revoked')
  }

  const createKey = () => {
    if (!newKey.name.trim()) { toast.error('Name required'); return }
    const created = {
      id: Date.now().toString(),
      name: newKey.name,
      key: `sk-${Math.random().toString(36).slice(2, 6)}-${Math.random().toString(36).slice(2, 36)}`,
      scopes: newKey.scopes,
      requests: 0,
      limit: 10000,
      status: 'active',
      created_at: new Date().toISOString().split('T')[0],
      last_used: 'Never',
    }
    setKeys([created, ...keys])
    setShowCreate(false)
    setNewKey({ name: '', scopes: ['chat'] })
    toast.success('API key created!')
  }

  const maskKey = (key) => `${key.slice(0, 12)}${'•'.repeat(20)}${key.slice(-4)}`

  return (
    <div className="p-6 space-y-5 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>API Keys</h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Manage access keys for your inference endpoints
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

              <div>
                <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>Name</label>
                <input className="input-base" placeholder="e.g. Production API" value={newKey.name}
                  onChange={e => setNewKey({ ...newKey, name: e.target.value })} />
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

              <button onClick={createKey} className="btn-primary w-full justify-center">
                <Key size={14} /> Generate Key
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Keys List */}
      <div className="space-y-3">
        {keys.map((k, i) => (
          <motion.div key={k.id} className="card p-5"
            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg flex items-center justify-center"
                  style={{ background: k.status === 'active' ? 'rgba(16,185,129,0.1)' : 'var(--bg-tertiary)' }}>
                  <Key size={15} style={{ color: k.status === 'active' ? '#10b981' : 'var(--text-muted)' }} />
                </div>
                <div>
                  <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>{k.name}</p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                    Created {k.created_at} • Last used {k.last_used}
                  </p>
                </div>
              </div>
              <span className={`badge ${k.status === 'active' ? 'badge-green' : 'badge-red'}`}>{k.status}</span>
            </div>

            {/* Key Value */}
            <div className="flex items-center gap-2 p-3 rounded-lg mb-3"
              style={{ background: 'var(--bg-tertiary)', fontFamily: 'JetBrains Mono, monospace' }}>
              <code className="text-xs flex-1 truncate" style={{ color: 'var(--text-secondary)' }}>
                {revealed[k.id] ? k.key : maskKey(k.key)}
              </code>
              <button onClick={() => setRevealed({ ...revealed, [k.id]: !revealed[k.id] })}
                className="flex-shrink-0 p-1" style={{ color: 'var(--text-muted)' }}>
                {revealed[k.id] ? <EyeOff size={13} /> : <Eye size={13} />}
              </button>
              <button onClick={() => copyKey(k.id, k.key)}
                className="flex-shrink-0 p-1" style={{ color: copied[k.id] ? '#10b981' : 'var(--text-muted)' }}>
                {copied[k.id] ? <Check size={13} /> : <Copy size={13} />}
              </button>
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {/* Scopes */}
                <div className="flex gap-1 flex-wrap">
                  {k.scopes.map(s => <span key={s} className="badge badge-violet text-xs">{s}</span>)}
                </div>
              </div>

              <div className="flex items-center gap-4">
                <div className="text-right">
                  <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {k.requests.toLocaleString()} / {k.limit.toLocaleString()}
                  </p>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>requests</p>
                </div>
                <div className="w-20">
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${(k.requests / k.limit) * 100}%` }} />
                  </div>
                </div>
                <button onClick={() => revokeKey(k.id)}
                  className="p-1.5 rounded transition-colors"
                  style={{ color: 'var(--text-muted)' }}
                  onMouseEnter={(e) => e.currentTarget.style.color = '#ef4444'}
                  onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}>
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      {/* API Docs hint */}
      <div className="card p-4 flex items-center gap-3">
        <Shield size={16} style={{ color: 'var(--accent-primary)' }} />
        <div>
          <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            Using the API
          </p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Include your key as: <code className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'var(--bg-tertiary)', color: 'var(--accent-primary)' }}>
              Authorization: Bearer sk-...
            </code>
          </p>
        </div>
      </div>
    </div>
  )
}
