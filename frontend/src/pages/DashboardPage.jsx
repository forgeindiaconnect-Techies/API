import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts'
import {
  MessageSquare, Database, Brain, Key, TrendingUp,
  Server, Clock, ArrowRight, Upload, Play, ShieldAlert, Activity
} from 'lucide-react'
import { useAuthStore } from '../store'
import { analyticsAPI } from '../services/api'
import { useNavigate } from 'react-router-dom'

const COLORS = ['#7c3aed', '#06b6d4', '#10b981', '#f59e0b']

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload?.length) {
    return (
      <div className="card-elevated px-3 py-2 text-xs">
        <p style={{ color: 'var(--text-muted)' }}>{label}</p>
        {payload.map((p) => (
          <p key={p.name} style={{ color: p.color }}>
            {p.name}: {p.value.toLocaleString()}
          </p>
        ))}
      </div>
    )
  }
  return null
}

export default function DashboardPage() {
  const { user } = useAuthStore()
  const navigate = useNavigate()
  
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState(null)
  const [gpuUsage] = useState(0)
  const [ramUsage] = useState(12)

  const fetchDashboardStats = async () => {
    setLoading(true)
    try {
      const { data: stats } = await analyticsAPI.getDashboard()
      setData(stats)
    } catch (err) {
      console.error('Failed to fetch dashboard stats:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDashboardStats()
  }, [])

  if (loading) {
    return (
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        <div className="space-y-2">
          <div className="h-6 w-48 bg-tertiary rounded animate-pulse" />
          <div className="h-4 w-64 bg-tertiary rounded animate-pulse" />
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(n => (
            <div key={n} className="stat-card animate-pulse space-y-3">
              <div className="w-9 h-9 rounded-lg bg-tertiary" />
              <div className="h-6 w-20 bg-tertiary rounded" />
              <div className="h-4 w-16 bg-tertiary rounded" />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="card p-5 lg:col-span-2 h-64 animate-pulse bg-tertiary/10" />
          <div className="card p-5 h-64 animate-pulse bg-tertiary/10" />
        </div>
      </div>
    )
  }

  const activeDatasets = data?.active_datasets || 0
  const activeModels = data?.active_models || 0
  const apiKeyCount = data?.api_key_count || 0
  const chatSessions = data?.chat_sessions || 0

  const hasNoData = activeDatasets === 0 && activeModels === 0

  const stats = [
    { icon: MessageSquare, label: 'Chat Sessions', value: chatSessions.toLocaleString(), color: '#7c3aed' },
    { icon: Database, label: 'Datasets', value: activeDatasets.toLocaleString(), color: '#06b6d4' },
    { icon: Brain, label: 'Models', value: activeModels.toLocaleString(), color: '#10b981' },
    { icon: Key, label: 'API Keys', value: apiKeyCount.toLocaleString(), color: '#f59e0b' },
  ]

  // If no data exists, show an attractive onboarding empty dashboard
  if (hasNoData) {
    return (
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        {/* Header */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
            Welcome to Personal AI Studio, {user?.name?.split(' ')[0] || 'User'} 👋
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
            Your full-stack workspace is configured and ready. Let's get started.
          </p>
        </motion.div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {stats.map(({ icon: Icon, label, value, color }, i) => (
            <motion.div
              key={label}
              className="stat-card animate-pulse-slow"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <div className="flex items-center justify-between">
                <div className="w-9 h-9 rounded-lg flex items-center justify-center"
                  style={{ background: `${color}15` }}>
                  <Icon size={16} style={{ color }} />
                </div>
              </div>
              <div>
                <p className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>{value}</p>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</p>
              </div>
            </motion.div>
          ))}
        </div>

        {/* Onboarding Cards */}
        <motion.div
          className="grid grid-cols-1 md:grid-cols-3 gap-5"
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <div className="card p-6 flex flex-col justify-between space-y-6 hover:border-violet-500/50 transition-all group">
            <div className="space-y-3">
              <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-cyan-500/10 text-cyan-500 group-hover:scale-105 transition-transform">
                <Upload size={22} />
              </div>
              <h3 className="font-bold text-base" style={{ color: 'var(--text-primary)' }}>1. Upload Dataset</h3>
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                Import CSV, Excel, PDF, or text files. The system automatically performs EDA and structures your data for fine-tuning or RAG indexation.
              </p>
            </div>
            <button
              onClick={() => navigate('/datasets')}
              className="btn-primary w-full justify-between items-center text-xs"
            >
              Go to Datasets <ArrowRight size={13} />
            </button>
          </div>

          <div className="card p-6 flex flex-col justify-between space-y-6 hover:border-violet-500/50 transition-all group">
            <div className="space-y-3">
              <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-violet-500/10 text-violet-500 group-hover:scale-105 transition-transform">
                <Brain size={22} />
              </div>
              <h3 className="font-bold text-base" style={{ color: 'var(--text-primary)' }}>2. Fine-tune Models</h3>
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                Fine-tune open-weights models like Llama 3 or Mistral. Monitor training loss plots and logs in real-time.
              </p>
            </div>
            <button
              onClick={() => navigate('/training')}
              className="btn-primary w-full justify-between items-center text-xs"
              style={{ opacity: activeDatasets === 0 ? 0.6 : 1 }}
            >
              Go to Model Training <ArrowRight size={13} />
            </button>
          </div>

          <div className="card p-6 flex flex-col justify-between space-y-6 hover:border-violet-500/50 transition-all group">
            <div className="space-y-3">
              <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-amber-500/10 text-amber-500 group-hover:scale-105 transition-transform">
                <Key size={22} />
              </div>
              <h3 className="font-bold text-base" style={{ color: 'var(--text-primary)' }}>3. Generate API Keys</h3>
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                Expose your models via secure, rate-limited public REST endpoints. Manage key lifecycles and scope control.
              </p>
            </div>
            <button
              onClick={() => navigate('/api-keys')}
              className="btn-primary w-full justify-between items-center text-xs"
            >
              Manage API Keys <ArrowRight size={13} />
            </button>
          </div>
        </motion.div>

        {/* Resources Indicator */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <Server size={14} style={{ color: 'var(--text-muted)' }} />
              <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>System Resources</p>
            </div>
            <div className="space-y-4">
              {[
                { label: 'GPU Usage', value: gpuUsage, color: '#7c3aed' },
                { label: 'RAM Usage', value: ramUsage, color: '#06b6d4' },
                { label: 'Available Storage', value: 88, color: '#10b981' },
              ].map(({ label, value, color }) => (
                <div key={label}>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
                    <span style={{ color }}>{value}%</span>
                  </div>
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${value}%`, background: color }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card p-5 flex flex-col justify-center items-center text-center space-y-2">
            <ShieldAlert size={28} className="text-cyan-500" />
            <h4 className="font-bold text-sm" style={{ color: 'var(--text-primary)' }}>Interactive Playground</h4>
            <p className="text-xs max-w-xs" style={{ color: 'var(--text-muted)' }}>
              Open the Chat Page to test streaming completions locally on Llama 3.
            </p>
            <button onClick={() => navigate('/chat')} className="btn-ghost text-xs mt-2">
              Open Chat Client
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Render full dashboard if user has models/datasets
  const mockUsageData = data?.daily_requests || [
    { date: 'Mon', requests: 0, tokens: 0 },
  ]
  const mockModelDist = data?.top_models || []

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
          Welcome back, {user?.name?.split(' ')[0] || 'User'} 👋
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          Here's what's happening with your AI Studio
        </p>
      </motion.div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map(({ icon: Icon, label, value, color }, i) => (
          <motion.div
            key={label}
            className="stat-card"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
          >
            <div className="flex items-center justify-between">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center"
                style={{ background: `${color}20` }}>
                <Icon size={16} style={{ color }} />
              </div>
            </div>
            <div>
              <p className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>{value}</p>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</p>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Usage Chart */}
        <motion.div
          className="card p-5 lg:col-span-2"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>API Usage</p>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Daily requests overview</p>
            </div>
            {data?.total_requests > 0 && (
              <span className="badge badge-violet">
                <TrendingUp size={10} className="mr-1 inline" /> Active
              </span>
            )}
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={mockUsageData}>
              <defs>
                <linearGradient id="gradRequests" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#7c3aed" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#7c3aed" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="requests" stroke="#7c3aed" strokeWidth={2}
                fill="url(#gradRequests)" name="Requests" />
            </AreaChart>
          </ResponsiveContainer>
        </motion.div>

        {/* Model Distribution */}
        <motion.div
          className="card p-5"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
        >
          <p className="font-semibold text-sm mb-1" style={{ color: 'var(--text-primary)' }}>Model Usage</p>
          <p className="text-xs mb-4" style={{ color: 'var(--text-muted)' }}>Distribution</p>
          <ResponsiveContainer width="100%" height={140}>
            <PieChart>
              <Pie data={mockModelDist} cx="50%" cy="50%" innerRadius={40} outerRadius={60}
                dataKey="requests" nameKey="model" strokeWidth={0}>
                {mockModelDist.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div className="space-y-1.5 mt-2">
            {mockModelDist.map(({ model, percent }, i) => (
              <div key={model} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                  <span style={{ color: 'var(--text-secondary)' }}>{model}</span>
                </div>
                <span style={{ color: 'var(--text-muted)' }}>{percent}%</span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Bottom Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* System Resources */}
        <motion.div
          className="card p-5"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <div className="flex items-center gap-2 mb-4">
            <Server size={14} style={{ color: 'var(--text-muted)' }} />
            <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>System Resources</p>
          </div>
          <div className="space-y-4">
            {[
              { label: 'GPU Usage', value: 38, color: '#7c3aed' },
              { label: 'RAM Usage', value: 54, color: '#06b6d4' },
              { label: 'Available Storage', value: 85, color: '#10b981' },
            ].map(({ label, value, color }) => (
              <div key={label}>
                <div className="flex justify-between text-xs mb-1.5">
                  <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
                  <span style={{ color }}>{value}%</span>
                </div>
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: `${value}%`, background: color }} />
                </div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Recent Activity */}
        <motion.div
          className="card p-5 lg:col-span-2"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
        >
          <div className="flex items-center gap-2 mb-4">
            <Activity size={14} style={{ color: 'var(--text-muted)' }} />
            <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Workspace Activity</p>
          </div>
          <div className="space-y-1">
            {[
              { icon: Database, text: `Active Datasets Loaded: ${activeDatasets}`, type: 'dataset' },
              { icon: Brain, text: `Trained Models Active: ${activeModels}`, type: 'model' },
              { icon: MessageSquare, text: `Active Chat Memory Sessions: ${chatSessions}`, type: 'chat' },
              { icon: Key, text: `Provisioned API key credentials: ${apiKeyCount}`, type: 'api' },
            ].map((act, i) => (
              <div key={i} className="table-row">
                <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                  style={{ background: 'var(--bg-tertiary)' }}>
                  <act.icon size={13} style={{ color: 'var(--text-muted)' }} />
                </div>
                <p className="flex-1 text-sm" style={{ color: 'var(--text-secondary)' }}>{act.text}</p>
                <div className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                  <Clock size={10} />
                  Active
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  )
}
