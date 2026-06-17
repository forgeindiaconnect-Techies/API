import { useEffect, useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, BarChart, Bar
} from 'recharts'
import {
  MessageSquare, Database, Brain, Key, TrendingUp, TrendingDown,
  Server, Clock, ArrowRight, Upload, Play, ShieldAlert, Activity,
  Sparkles, ShieldCheck, Cpu, HardDrive, Users, Zap
} from 'lucide-react'
import { useAuthStore } from '../store'
import { analyticsAPI } from '../services/api'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'

const COLORS = ['#8B5CF6', '#6366F1', '#06B6D4', '#10B981']

// Connected Node Canvas Background Animation
function LocalParticleCanvas() {
  const canvasRef = useRef(null)
  
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    let animationFrameId
    
    let width = canvas.width = canvas.parentElement.offsetWidth
    let height = canvas.height = canvas.parentElement.offsetHeight
    
    const handleResize = () => {
      if (!canvas) return
      width = canvas.width = canvas.parentElement.offsetWidth
      height = canvas.height = canvas.parentElement.offsetHeight
    }
    window.addEventListener('resize', handleResize)
    
    const particles = []
    const particleCount = 45
    
    class Particle {
      constructor() {
        this.x = Math.random() * width
        this.y = Math.random() * height
        this.vx = (Math.random() - 0.5) * 0.2
        this.vy = (Math.random() - 0.5) * 0.2
        this.radius = Math.random() * 1.5 + 1
        this.color = Math.random() > 0.5 ? 'rgba(139, 92, 246, 0.2)' : 'rgba(6, 182, 212, 0.2)'
      }
      update() {
        this.x += this.vx
        this.y += this.vy
        if (this.x < 0 || this.x > width) this.vx *= -1
        if (this.y < 0 || this.y > height) this.vy *= -1
      }
      draw() {
        ctx.beginPath()
        ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2)
        ctx.fillStyle = this.color
        ctx.fill()
      }
    }
    
    for (let i = 0; i < particleCount; i++) {
      particles.push(new Particle())
    }
    
    const animate = () => {
      ctx.clearRect(0, 0, width, height)
      
      particles.forEach(p => {
        p.update()
        p.draw()
      })
      
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const p1 = particles[i]
          const p2 = particles[j]
          const dx = p1.x - p2.x
          const dy = p1.y - p2.y
          const dist = Math.sqrt(dx * dx + dy * dy)
          
          if (dist < 100) {
            const alpha = ((100 - dist) / 100) * 0.08
            ctx.beginPath()
            ctx.moveTo(p1.x, p1.y)
            ctx.lineTo(p2.x, p2.y)
            ctx.strokeStyle = `rgba(99, 102, 241, ${alpha})`
            ctx.lineWidth = 0.6
            ctx.stroke()
          }
        }
      }
      
      animationFrameId = requestAnimationFrame(animate)
    }
    animate()
    
    return () => {
      window.removeEventListener('resize', handleResize)
      cancelAnimationFrame(animationFrameId)
    }
  }, [])
  
  return <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none z-0" />
}

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload?.length) {
    return (
      <div className="bg-[#090b14]/90 border border-white/[0.08] backdrop-blur-md px-3 py-2 text-xs rounded-xl shadow-2xl">
        <p className="text-gray-500 font-bold mb-1">{label}</p>
        {payload.map((p) => (
          <p key={p.name} style={{ color: p.color }} className="font-semibold">
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
  
  // Real-time clock states
  const [timeStr, setTimeStr] = useState(new Date().toLocaleTimeString())
  const [dateStr] = useState(new Date().toLocaleDateString(undefined, { 
    weekday: 'long', 
    year: 'numeric', 
    month: 'long', 
    day: 'numeric' 
  }))

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
    const timer = setInterval(() => {
      setTimeStr(new Date().toLocaleTimeString())
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  if (loading) {
    return (
      <div className="p-6 sm:p-8 space-y-6 max-w-7xl mx-auto bg-[#030712] min-h-screen">
        <div className="space-y-3">
          <div className="h-7 w-52 bg-white/[0.02] border border-white/[0.05] rounded-xl animate-pulse" />
          <div className="h-4 w-72 bg-white/[0.02] border border-white/[0.05] rounded-xl animate-pulse" />
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(n => (
            <div key={n} className="bg-white/[0.02] border border-white/[0.05] p-5 rounded-2xl animate-pulse space-y-3">
              <div className="w-10 h-10 rounded-xl bg-white/[0.04]" />
              <div className="h-7 w-20 bg-white/[0.04] rounded-lg" />
              <div className="h-4 w-16 bg-white/[0.04] rounded-lg" />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="bg-white/[0.02] border border-white/[0.05] rounded-2xl p-5 lg:col-span-2 h-72 animate-pulse" />
          <div className="bg-white/[0.02] border border-white/[0.05] rounded-2xl p-5 h-72 animate-pulse" />
        </div>
      </div>
    )
  }

  const activeDatasets = data?.active_datasets || 0
  const activeModels = data?.active_models || 0
  const apiKeyCount = data?.api_key_count || 0
  const chatSessions = data?.chat_sessions || 0

  // 8 Premium Stat Metrics
  const statsList = [
    { icon: MessageSquare, label: 'Chat Sessions', value: chatSessions.toLocaleString(), trend: '+14.2%', isUp: true, color: '#8B5CF6' },
    { icon: Database, label: 'Datasets Active', value: activeDatasets.toLocaleString(), trend: '+12.5%', isUp: true, color: '#06B6D4' },
    { icon: Brain, label: 'Trained Models', value: activeModels.toLocaleString(), trend: '+8.3%', isUp: true, color: '#10B981' },
    { icon: Key, label: 'API Keys Issued', value: apiKeyCount.toLocaleString(), trend: '+20.0%', isUp: true, color: '#F59E0B' },
    { icon: Activity, label: 'Daily Requests', value: (data?.total_requests || 1840).toLocaleString(), trend: '+18.1%', isUp: true, color: '#6366F1' },
    { icon: Sparkles, label: 'Token Volume', value: '4.8M', trend: '+9.4%', isUp: true, color: '#EC4899' },
    { icon: Users, label: 'Active Sessions', value: '3', trend: 'Stable', isUp: true, color: '#3B82F6' },
    { icon: HardDrive, label: 'Storage Usage', value: '1.2 GB', trend: '12% of 10G', isUp: true, color: '#10B981' }
  ]

  const mockUsageData = data?.daily_requests || [
    { date: 'Mon', requests: 120, tokens: 4000 },
    { date: 'Tue', requests: 250, tokens: 6800 },
    { date: 'Wed', requests: 180, tokens: 5500 },
    { date: 'Thu', requests: 310, tokens: 9000 },
    { date: 'Fri', requests: 480, tokens: 12400 },
    { date: 'Sat', requests: 620, tokens: 17500 },
    { date: 'Sun', requests: 590, tokens: 16800 }
  ]

  const mockModelDist = data?.top_models || [
    { model: 'Llama 3 Instruct', requests: 65, percent: 65 },
    { model: 'Mistral 7B', requests: 25, percent: 25 },
    { model: 'paraphrase-MiniLM', requests: 10, percent: 10 }
  ]

  const mockTokenData = [
    { name: 'Mon', volume: 400 },
    { name: 'Tue', volume: 680 },
    { name: 'Wed', volume: 550 },
    { name: 'Thu', volume: 900 },
    { name: 'Fri', volume: 1240 },
    { name: 'Sat', volume: 1750 },
    { name: 'Sun', volume: 1680 }
  ]

  return (
    <div className="relative p-6 sm:p-8 space-y-8 max-w-7xl mx-auto overflow-hidden">
      
      {/* Dynamic Style Sheet Injection for Dashboard Elements */}
      <style>{`
        .glass-card {
          background: rgba(17, 24, 39, 0.45);
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.04);
          transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        }
        .glass-card:hover {
          border-color: rgba(139, 92, 246, 0.2);
          transform: translateY(-3px);
          box-shadow: 0 15px 35px -5px rgba(0, 0, 0, 0.4), 0 0 20px rgba(139, 92, 246, 0.05);
        }
        .progress-bar-cyan {
          background: rgba(6, 182, 212, 0.1);
        }
        .glow-green {
          box-shadow: 0 0 12px rgba(16, 185, 129, 0.3);
        }
      `}</style>

      {/* Connected Neural Grid Background */}
      <LocalParticleCanvas />

      {/* Hero Header Section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/[0.04] pb-6 z-10 relative">
        <motion.div 
          initial={{ opacity: 0, x: -15 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5 }}
          className="space-y-1.5"
        >
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-extrabold tracking-widest text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded-full uppercase">
              Control Panel
            </span>
            <span className="text-[10px] font-bold text-gray-500">•</span>
            <span className="text-[10px] font-semibold text-gray-400">{timeStr}</span>
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-gray-100 to-gray-400">
            Welcome back, {user?.name?.split(' ')[0] || 'Demo'} 👋
          </h1>
          <p className="text-sm text-gray-500">
            Workspace telemetry: All neural models and vector storage pipelines online.
          </p>
        </motion.div>

        {/* Date Display Card */}
        <motion.div
          initial={{ opacity: 0, x: 15 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex items-center gap-3 px-4 py-2 bg-white/[0.01] border border-white/[0.04] rounded-2xl flex-shrink-0"
        >
          <div className="w-8 h-8 rounded-xl bg-cyan-500/10 flex items-center justify-center text-cyan-400">
            <Clock size={16} />
          </div>
          <div className="text-left">
            <p className="text-[10px] font-bold text-gray-600 uppercase tracking-wide">Workspace Clock</p>
            <p className="text-xs font-bold text-gray-300">{dateStr}</p>
          </div>
        </motion.div>
      </div>

      {/* Interactive Quick Actions Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 z-10 relative">
        {[
          { label: 'Start AI Chat', desc: 'Interact with models', icon: MessageSquare, path: '/chat', border: 'hover:border-purple-500/30' },
          { label: 'Upload Dataset', desc: 'CSV, TXT, PDF formats', icon: Upload, path: '/datasets', border: 'hover:border-cyan-500/30' },
          { label: 'Train New Model', desc: 'Start model fine-tune', icon: Brain, path: '/training', border: 'hover:border-emerald-500/30' },
          { label: 'Generate API Key', desc: 'Expose REST endpoints', icon: Key, path: '/api-keys', border: 'hover:border-amber-500/30' }
        ].map((act, idx) => (
          <button
            key={idx}
            onClick={() => navigate(act.path)}
            className={`glass-card text-left p-4 rounded-2xl flex flex-col justify-between h-28 ${act.border}`}
          >
            <div className="w-9 h-9 rounded-xl bg-white/[0.03] border border-white/[0.05] flex items-center justify-center text-gray-400">
              <act.icon size={16} />
            </div>
            <div className="mt-2 min-w-0">
              <p className="text-xs font-bold text-gray-200 truncate flex items-center gap-1">
                {act.label}
                <ArrowRight size={10} className="text-gray-500 transition-transform group-hover:translate-x-1" />
              </p>
              <p className="text-[9px] text-gray-500 truncate mt-0.5">{act.desc}</p>
            </div>
          </button>
        ))}
      </div>

      {/* 8 Statistics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 z-10 relative">
        {statsList.map(({ icon: Icon, label, value, trend, isUp, color }, i) => (
          <motion.div
            key={label}
            className="glass-card p-5 rounded-2xl flex flex-col justify-between"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }}
          >
            <div className="flex items-center justify-between">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center"
                style={{ background: `${color}12`, border: `1px solid ${color}20` }}>
                <Icon size={16} style={{ color }} />
              </div>
              <div className="flex items-center gap-1">
                {isUp ? (
                  <TrendingUp size={11} className="text-emerald-400" />
                ) : (
                  <TrendingDown size={11} className="text-rose-400" />
                )}
                <span className={`text-[10px] font-bold ${isUp ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {trend}
                </span>
              </div>
            </div>
            <div className="mt-4">
              <p className="text-2xl font-black text-white tracking-tight">{value}</p>
              <p className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mt-1">{label}</p>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Charts section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 z-10 relative">
        {/* Daily Requests (Area) */}
        <motion.div
          className="glass-card p-5 rounded-2xl lg:col-span-2"
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
        >
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="font-bold text-sm text-gray-200">API Gateway Requests</p>
              <p className="text-[10px] text-gray-500 uppercase font-bold tracking-wide mt-0.5">Daily volume metrics</p>
            </div>
            <span className="text-[9px] font-bold uppercase tracking-widest text-purple-400 bg-purple-500/10 border border-purple-500/20 px-2 py-0.5 rounded-full flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" /> Active Telemetry
            </span>
          </div>
          <ResponsiveContainer width="100%" height={190}>
            <AreaChart data={mockUsageData}>
              <defs>
                <linearGradient id="requestsGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#8B5CF6" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280', fontWeight: 'semibold' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280', fontWeight: 'semibold' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="requests" stroke="#8B5CF6" strokeWidth={2}
                fill="url(#requestsGrad)" name="Requests" />
            </AreaChart>
          </ResponsiveContainer>
        </motion.div>

        {/* Model Distribution (Donut) */}
        <motion.div
          className="glass-card p-5 rounded-2xl"
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <p className="font-bold text-sm text-gray-200">Model Inference Share</p>
          <p className="text-[10px] text-gray-500 uppercase font-bold tracking-wide mt-0.5 mb-4">Request distribution</p>
          
          <div className="relative flex justify-center items-center h-[130px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={mockModelDist} cx="50%" cy="50%" innerRadius={42} outerRadius={56}
                  dataKey="requests" nameKey="model" strokeWidth={0} paddingAngle={2}>
                  {mockModelDist.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            {/* Centered label */}
            <div className="absolute flex flex-col justify-center items-center">
              <span className="text-lg font-black text-white">Llama 3</span>
              <span className="text-[9px] font-bold text-gray-500 uppercase">Primary</span>
            </div>
          </div>

          <div className="space-y-2 mt-4">
            {mockModelDist.map(({ model, percent }, i) => (
              <div key={model} className="flex items-center justify-between text-[11px] font-semibold">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-2.5 h-2.5 rounded-md flex-shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
                  <span className="text-gray-400 truncate">{model}</span>
                </div>
                <span className="text-gray-200 font-bold ml-2">{percent}%</span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* AI Insights & Token Bar Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 z-10 relative">
        {/* Token Volume (BarChart) */}
        <motion.div
          className="glass-card p-5 rounded-2xl"
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
        >
          <div>
            <p className="font-bold text-sm text-gray-200">Token Volume Index</p>
            <p className="text-[10px] text-gray-500 uppercase font-bold tracking-wide mt-0.5 mb-4">Token usage in thousands</p>
          </div>
          <ResponsiveContainer width="100%" height={150}>
            <BarChart data={mockTokenData}>
              <defs>
                <linearGradient id="tokenGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#06B6D4" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#6366F1" stopOpacity={0.3} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 9, fill: '#6b7280' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 9, fill: '#6b7280' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="volume" fill="url(#tokenGrad)" radius={[4, 4, 0, 0]} name="Tokens" />
            </BarChart>
          </ResponsiveContainer>
        </motion.div>

        {/* AI Insights Widget */}
        <motion.div
          className="glass-card p-5 rounded-2xl lg:col-span-2 flex flex-col justify-between"
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <div>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-7 h-7 rounded-xl bg-purple-500/10 flex items-center justify-center text-purple-400">
                <Sparkles size={14} className="animate-pulse" />
              </div>
              <p className="font-bold text-sm text-gray-200">AI Platform Insights</p>
            </div>
            <p className="text-xs text-gray-500 leading-normal mb-4">
              Real-time platform resource analyzer recommendations.
            </p>
            
            <div className="space-y-3">
              {[
                { title: 'Model Optimization Advice', text: 'Prompt cache is active. Recommend fine-tuning Llama-3 with your recent CSV dataset to decrease latency.', color: 'text-purple-400' },
                { title: 'Database Index Health', text: 'Vector store holds 3 chunks in ChromaDB. Embedding space and index structures match optimally.', color: 'text-cyan-400' },
                { title: 'GPU Capacity Check', text: 'Available GPU storage stands at 38% capacity. Excellent headroom for batch training.', color: 'text-emerald-400' }
              ].map((ins, i) => (
                <div key={i} className="p-3 bg-white/[0.01] border border-white/[0.04] rounded-xl flex items-start gap-2.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-purple-500 mt-1.5 flex-shrink-0" />
                  <div className="min-w-0">
                    <p className={`text-[10px] font-bold uppercase tracking-wider ${ins.color}`}>{ins.title}</p>
                    <p className="text-[11px] text-gray-400 leading-normal mt-0.5">{ins.text}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </div>

      {/* Datasets table section */}
      <div className="grid grid-cols-1 gap-6 z-10 relative">
        <motion.div
          className="glass-card p-5 rounded-2xl"
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
        >
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Database size={15} className="text-cyan-400" />
              <p className="font-bold text-sm text-gray-200">Recent Datasets</p>
            </div>
            <button 
              onClick={() => navigate('/datasets')}
              className="text-xs font-semibold text-purple-400 hover:text-purple-300 flex items-center gap-1 hover:underline transition-colors"
            >
              See All Registry <ArrowRight size={12} />
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-white/[0.04] text-gray-500 font-bold uppercase tracking-wider">
                  <th className="py-3 px-4">Dataset Name</th>
                  <th className="py-3 px-4">Format</th>
                  <th className="py-3 px-4">Storage Backup</th>
                  <th className="py-3 px-4 text-center">Status</th>
                  <th className="py-3 px-4 text-right">Integrity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.02]">
                {[
                  { name: 'WineQT.csv', type: 'csv', storage: 'GridFS + Cloudinary', status: 'indexed', integrity: '100% Valid' },
                  { name: 'test_both_original.txt', type: 'txt', storage: 'GridFS + Cloudinary', status: 'indexed', integrity: '100% Valid' },
                  { name: 'article_level_data.csv', type: 'csv', storage: 'GridFS + Cloudinary', status: 'indexed', integrity: '100% Valid' }
                ].map((row, i) => (
                  <tr key={i} className="hover:bg-white/[0.01] transition-colors">
                    <td className="py-3.5 px-4 font-bold text-gray-200">{row.name}</td>
                    <td className="py-3.5 px-4">
                      <span className="px-2 py-0.5 rounded bg-white/[0.04] text-gray-400 font-mono text-[10px] uppercase font-bold">
                        {row.type}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-gray-400 font-medium">{row.storage}</td>
                    <td className="py-3.5 px-4 text-center">
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        <span className="w-1 h-1 rounded-full bg-emerald-400 animate-pulse" /> {row.status}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-right font-bold text-gray-400">{row.integrity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      </div>

    </div>
  )
}
