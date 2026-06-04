import { motion } from 'framer-motion'
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'
import { TrendingUp, Zap, Clock, Activity } from 'lucide-react'

const usageData = [
  { date: 'Jan 1', requests: 420, tokens: 15000, latency: 320 },
  { date: 'Jan 2', requests: 580, tokens: 22000, latency: 290 },
  { date: 'Jan 3', requests: 390, tokens: 14000, latency: 340 },
  { date: 'Jan 4', requests: 720, tokens: 28000, latency: 280 },
  { date: 'Jan 5', requests: 640, tokens: 24000, latency: 310 },
  { date: 'Jan 6', requests: 310, tokens: 11000, latency: 360 },
  { date: 'Jan 7', requests: 450, tokens: 17000, latency: 295 },
  { date: 'Jan 8', requests: 860, tokens: 33000, latency: 265 },
  { date: 'Jan 9', requests: 790, tokens: 30000, latency: 275 },
  { date: 'Jan 10', requests: 920, tokens: 36000, latency: 255 },
  { date: 'Jan 11', requests: 1050, tokens: 41000, latency: 240 },
  { date: 'Jan 12', requests: 980, tokens: 38000, latency: 248 },
  { date: 'Jan 13', requests: 740, tokens: 28500, latency: 270 },
  { date: 'Jan 14', requests: 1120, tokens: 44000, latency: 235 },
]

const endpointData = [
  { endpoint: '/chat', calls: 4820, errors: 12, p99: 480 },
  { endpoint: '/predict', calls: 2340, errors: 8, p99: 320 },
  { endpoint: '/embed', calls: 1890, errors: 3, p99: 180 },
  { endpoint: '/transcribe', calls: 560, errors: 5, p99: 1200 },
  { endpoint: '/generate', calls: 340, errors: 2, p99: 4800 },
]

const modelUsage = [
  { name: 'Jan 8', llama3: 420, mistral: 180, deepseek: 90, custom: 50 },
  { name: 'Jan 9', llama3: 380, mistral: 220, deepseek: 110, custom: 80 },
  { name: 'Jan 10', llama3: 510, mistral: 190, deepseek: 130, custom: 90 },
  { name: 'Jan 11', llama3: 620, mistral: 240, deepseek: 120, custom: 70 },
  { name: 'Jan 12', llama3: 580, mistral: 210, deepseek: 100, custom: 90 },
  { name: 'Jan 13', llama3: 440, mistral: 170, deepseek: 80, custom: 50 },
  { name: 'Jan 14', llama3: 700, mistral: 270, deepseek: 100, custom: 50 },
]

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload?.length) {
    return (
      <div className="card-elevated px-3 py-2 text-xs space-y-1">
        <p style={{ color: 'var(--text-muted)' }}>{label}</p>
        {payload.map(p => (
          <p key={p.name} style={{ color: p.color }}>
            {p.name}: {typeof p.value === 'number' ? p.value.toLocaleString() : p.value}
          </p>
        ))}
      </div>
    )
  }
  return null
}

export default function AnalyticsPage() {
  const totalRequests = usageData.reduce((a, b) => a + b.requests, 0)
  const totalTokens = usageData.reduce((a, b) => a + b.tokens, 0)
  const avgLatency = Math.round(usageData.reduce((a, b) => a + b.latency, 0) / usageData.length)

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>Analytics</h1>
        <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>Last 14 days</p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { icon: Zap, label: 'Total Requests', value: totalRequests.toLocaleString(), sub: '+18% vs prev', color: '#7c3aed' },
          { icon: Activity, label: 'Total Tokens', value: (totalTokens / 1000).toFixed(0) + 'K', sub: '+24% vs prev', color: '#06b6d4' },
          { icon: Clock, label: 'Avg Latency', value: avgLatency + 'ms', sub: '-8% improved', color: '#10b981' },
          { icon: TrendingUp, label: 'Error Rate', value: '0.31%', sub: '-0.1% vs prev', color: '#f59e0b' },
        ].map(({ icon: Icon, label, value, sub, color }, i) => (
          <motion.div key={label} className="stat-card"
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
            <div className="w-9 h-9 rounded-lg flex items-center justify-center"
              style={{ background: `${color}20` }}>
              <Icon size={16} style={{ color }} />
            </div>
            <div>
              <p className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>{value}</p>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</p>
              <p className="text-xs mt-0.5" style={{ color }}>{sub}</p>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Requests over time */}
      <motion.div className="card p-5"
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
        <p className="font-semibold text-sm mb-4" style={{ color: 'var(--text-primary)' }}>
          API Requests Over Time
        </p>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={usageData}>
            <defs>
              <linearGradient id="gReq" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#7c3aed" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#7c3aed" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gTok" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.2} />
                <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Area type="monotone" dataKey="requests" stroke="#7c3aed" strokeWidth={2} fill="url(#gReq)" name="Requests" />
          </AreaChart>
        </ResponsiveContainer>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Model usage stacked */}
        <motion.div className="card p-5"
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}>
          <p className="font-semibold text-sm mb-4" style={{ color: 'var(--text-primary)' }}>
            Requests by Model
          </p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={modelUsage}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="llama3" stackId="a" fill="#7c3aed" name="Llama 3" radius={[0, 0, 0, 0]} />
              <Bar dataKey="mistral" stackId="a" fill="#06b6d4" name="Mistral" />
              <Bar dataKey="deepseek" stackId="a" fill="#10b981" name="DeepSeek" />
              <Bar dataKey="custom" stackId="a" fill="#f59e0b" name="Custom" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </motion.div>

        {/* Latency trend */}
        <motion.div className="card p-5"
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
          <p className="font-semibold text-sm mb-4" style={{ color: 'var(--text-primary)' }}>
            Avg Latency (ms)
          </p>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={usageData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} domain={[200, 400]} />
              <Tooltip content={<CustomTooltip />} />
              <Line type="monotone" dataKey="latency" stroke="#10b981" strokeWidth={2} dot={false} name="Latency (ms)" />
            </LineChart>
          </ResponsiveContainer>
        </motion.div>
      </div>

      {/* Endpoint table */}
      <motion.div className="card overflow-hidden"
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}>
        <div className="px-5 py-4" style={{ borderBottom: '1px solid var(--border)' }}>
          <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Endpoint Breakdown</p>
        </div>
        <div className="flex items-center gap-4 px-5 py-2 text-xs font-semibold"
          style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
          <div className="flex-1">Endpoint</div>
          <div className="w-24 text-right">Calls</div>
          <div className="w-20 text-right">Errors</div>
          <div className="w-24 text-right">P99 Latency</div>
          <div className="w-24 text-right">Error Rate</div>
        </div>
        {endpointData.map((ep, i) => (
          <div key={i} className="flex items-center gap-4 px-5 py-3 text-sm"
            style={{ borderBottom: '1px solid var(--border-subtle)' }}
            onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-tertiary)'}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
            <div className="flex-1">
              <code className="text-xs" style={{ color: 'var(--accent-primary)', fontFamily: 'JetBrains Mono, monospace' }}>
                POST {ep.endpoint}
              </code>
            </div>
            <div className="w-24 text-right text-xs" style={{ color: 'var(--text-secondary)' }}>
              {ep.calls.toLocaleString()}
            </div>
            <div className="w-20 text-right">
              <span className="badge badge-red text-xs">{ep.errors}</span>
            </div>
            <div className="w-24 text-right text-xs" style={{ color: 'var(--text-secondary)' }}>
              {ep.p99}ms
            </div>
            <div className="w-24 text-right text-xs"
              style={{ color: (ep.errors / ep.calls) > 0.005 ? '#fca5a5' : '#6ee7b7' }}>
              {((ep.errors / ep.calls) * 100).toFixed(2)}%
            </div>
          </div>
        ))}
      </motion.div>
    </div>
  )
}
