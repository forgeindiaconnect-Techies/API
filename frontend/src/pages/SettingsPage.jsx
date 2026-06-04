import { useState } from 'react'
import { motion } from 'framer-motion'
import { User, Bell, Shield, Cpu, Palette, Save, Eye, EyeOff } from 'lucide-react'
import { useAuthStore, useUIStore } from '../store'
import toast from 'react-hot-toast'

const TABS = [
  { id: 'profile', label: 'Profile', icon: User },
  { id: 'appearance', label: 'Appearance', icon: Palette },
  { id: 'models', label: 'AI Models', icon: Cpu },
  { id: 'security', label: 'Security', icon: Shield },
  { id: 'notifications', label: 'Notifications', icon: Bell },
]

export default function SettingsPage() {
  const { user, updateUser } = useAuthStore()
  const { theme, setTheme } = useUIStore()
  const [tab, setTab] = useState('profile')
  const [profile, setProfile] = useState({ name: user?.name || '', email: user?.email || '', bio: '' })
  const [showPw, setShowPw] = useState(false)
  const [pw, setPw] = useState({ current: '', new: '', confirm: '' })
  const [notifs, setNotifs] = useState({
    training_complete: true,
    api_errors: true,
    weekly_report: false,
    new_features: true,
  })
  const [modelSettings, setModelSettings] = useState({
    default_model: 'llama3',
    temperature: 0.7,
    max_tokens: 2048,
    ollama_url: 'http://localhost:11434',
    openai_key: '',
  })

  const save = () => toast.success('Settings saved!')

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-bold mb-5" style={{ color: 'var(--text-primary)' }}>Settings</h1>

      <div className="flex gap-5">
        {/* Sidebar */}
        <div className="w-44 flex-shrink-0 space-y-0.5">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setTab(id)}
              className={`sidebar-item w-full ${tab === id ? 'active' : ''}`}>
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 space-y-4">
          {tab === 'profile' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card p-6 space-y-4">
              <h2 className="font-bold text-sm" style={{ color: 'var(--text-primary)' }}>Profile Information</h2>

              {/* Avatar */}
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-2xl flex items-center justify-center text-2xl font-bold"
                  style={{ background: 'var(--accent-primary)', color: 'white' }}>
                  {profile.name[0]?.toUpperCase() || 'U'}
                </div>
                <button className="btn-ghost text-xs py-1.5">Change Photo</button>
              </div>

              {[
                { label: 'Full Name', key: 'name', type: 'text' },
                { label: 'Email', key: 'email', type: 'email' },
              ].map(({ label, key, type }) => (
                <div key={key}>
                  <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                    {label}
                  </label>
                  <input type={type} className="input-base"
                    value={profile[key]}
                    onChange={e => setProfile({ ...profile, [key]: e.target.value })} />
                </div>
              ))}

              <div>
                <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>Bio</label>
                <textarea rows={3} className="input-base resize-none" placeholder="Tell us about yourself..."
                  value={profile.bio}
                  onChange={e => setProfile({ ...profile, bio: e.target.value })} />
              </div>

              <button onClick={save} className="btn-primary">
                <Save size={13} /> Save Changes
              </button>
            </motion.div>
          )}

          {tab === 'appearance' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card p-6 space-y-5">
              <h2 className="font-bold text-sm" style={{ color: 'var(--text-primary)' }}>Appearance</h2>
              <div>
                <label className="block text-xs font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>Theme</label>
                <div className="grid grid-cols-3 gap-3">
                  {['dark', 'light', 'system'].map(t => (
                    <button key={t} onClick={() => setTheme(t === 'system' ? 'dark' : t)}
                      className="p-3 rounded-xl text-sm font-medium capitalize transition-all"
                      style={{
                        background: theme === t ? 'var(--accent-muted)' : 'var(--bg-tertiary)',
                        border: `1px solid ${theme === t ? 'var(--accent-primary)' : 'var(--border)'}`,
                        color: theme === t ? 'var(--accent-primary)' : 'var(--text-secondary)',
                      }}>
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>Accent Color</label>
                <div className="flex gap-2">
                  {['#7c3aed', '#2563eb', '#059669', '#dc2626', '#d97706', '#db2777'].map(c => (
                    <button key={c} className="w-8 h-8 rounded-full border-2 transition-all"
                      style={{ background: c, borderColor: c === '#7c3aed' ? 'white' : 'transparent' }} />
                  ))}
                </div>
              </div>
            </motion.div>
          )}

          {tab === 'models' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card p-6 space-y-4">
              <h2 className="font-bold text-sm" style={{ color: 'var(--text-primary)' }}>AI Model Configuration</h2>

              <div>
                <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                  Default Model
                </label>
                <select className="input-base" value={modelSettings.default_model}
                  onChange={e => setModelSettings({ ...modelSettings, default_model: e.target.value })}>
                  {['llama3', 'llama3:70b', 'mistral', 'deepseek'].map(m =>
                    <option key={m} value={m}>{m}</option>
                  )}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                  Temperature: {modelSettings.temperature}
                </label>
                <input type="range" min={0} max={2} step={0.1}
                  value={modelSettings.temperature}
                  onChange={e => setModelSettings({ ...modelSettings, temperature: +e.target.value })}
                  className="w-full" />
              </div>

              <div>
                <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                  Ollama URL
                </label>
                <input type="text" className="input-base font-mono text-sm"
                  value={modelSettings.ollama_url}
                  onChange={e => setModelSettings({ ...modelSettings, ollama_url: e.target.value })} />
              </div>

              <div>
                <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                  OpenAI API Key (optional)
                </label>
                <div className="relative">
                  <input type={showPw ? 'text' : 'password'} className="input-base pr-10"
                    placeholder="sk-..."
                    value={modelSettings.openai_key}
                    onChange={e => setModelSettings({ ...modelSettings, openai_key: e.target.value })} />
                  <button className="absolute right-3 top-1/2 -translate-y-1/2"
                    onClick={() => setShowPw(!showPw)} style={{ color: 'var(--text-muted)' }}>
                    {showPw ? <EyeOff size={13} /> : <Eye size={13} />}
                  </button>
                </div>
              </div>

              <button onClick={save} className="btn-primary">
                <Save size={13} /> Save Configuration
              </button>
            </motion.div>
          )}

          {tab === 'security' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card p-6 space-y-4">
              <h2 className="font-bold text-sm" style={{ color: 'var(--text-primary)' }}>Security</h2>
              {[
                { label: 'Current Password', key: 'current', placeholder: '••••••••' },
                { label: 'New Password', key: 'new', placeholder: '••••••••' },
                { label: 'Confirm Password', key: 'confirm', placeholder: '••••••••' },
              ].map(({ label, key, placeholder }) => (
                <div key={key}>
                  <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                    {label}
                  </label>
                  <input type="password" className="input-base" placeholder={placeholder}
                    value={pw[key]} onChange={e => setPw({ ...pw, [key]: e.target.value })} />
                </div>
              ))}
              <button onClick={save} className="btn-primary">
                <Shield size={13} /> Update Password
              </button>
            </motion.div>
          )}

          {tab === 'notifications' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card p-6 space-y-4">
              <h2 className="font-bold text-sm" style={{ color: 'var(--text-primary)' }}>Notifications</h2>
              {[
                { key: 'training_complete', label: 'Training Complete', desc: 'When a model finishes training' },
                { key: 'api_errors', label: 'API Errors', desc: 'When error rate exceeds threshold' },
                { key: 'weekly_report', label: 'Weekly Report', desc: 'Summary of usage each week' },
                { key: 'new_features', label: 'New Features', desc: 'Product updates and announcements' },
              ].map(({ key, label, desc }) => (
                <div key={key} className="flex items-center justify-between py-2"
                  style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <div>
                    <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{label}</p>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{desc}</p>
                  </div>
                  <button onClick={() => setNotifs({ ...notifs, [key]: !notifs[key] })}
                    className="w-10 h-5 rounded-full transition-colors relative"
                    style={{ background: notifs[key] ? 'var(--accent-primary)' : 'var(--bg-tertiary)' }}>
                    <span className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all"
                      style={{ left: notifs[key] ? '22px' : '2px' }} />
                  </button>
                </div>
              ))}
              <button onClick={save} className="btn-primary">
                <Save size={13} /> Save Preferences
              </button>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  )
}
