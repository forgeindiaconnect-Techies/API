import { useParams } from 'react-router-dom'
import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, ScatterChart, Scatter
} from 'recharts'
import { Table, FileText, Brain, Search, Download, RefreshCw } from 'lucide-react'

const COLORS = ['#7c3aed', '#06b6d4', '#10b981', '#f59e0b', '#ef4444']

const mockEDA = {
  name: 'customer_churn.csv',
  rows: 10000,
  cols: 24,
  missing: 234,
  duplicates: 12,
  numericCols: 16,
  categoricalCols: 8,
  targetDistribution: [
    { label: 'Churned', value: 2867 },
    { label: 'Retained', value: 7133 },
  ],
  featureImportance: [
    { name: 'tenure', importance: 0.24 },
    { name: 'contract_type', importance: 0.19 },
    { name: 'monthly_charges', importance: 0.16 },
    { name: 'total_charges', importance: 0.14 },
    { name: 'tech_support', importance: 0.11 },
    { name: 'internet_service', importance: 0.09 },
    { name: 'online_backup', importance: 0.07 },
  ],
  missingByCol: [
    { name: 'total_charges', missing: 11 },
    { name: 'monthly_charges', missing: 8 },
    { name: 'tenure', missing: 5 },
  ],
  preview: [
    { customer_id: 'CUST001', tenure: 24, monthly_charges: 65.5, total_charges: 1572, churn: 'No' },
    { customer_id: 'CUST002', tenure: 3, monthly_charges: 89.2, total_charges: 267.6, churn: 'Yes' },
    { customer_id: 'CUST003', tenure: 48, monthly_charges: 45.0, total_charges: 2160, churn: 'No' },
    { customer_id: 'CUST004', tenure: 12, monthly_charges: 110.5, total_charges: 1326, churn: 'Yes' },
    { customer_id: 'CUST005', tenure: 36, monthly_charges: 72.0, total_charges: 2592, churn: 'No' },
  ],
  aiSummary: `This dataset contains **10,000 customer records** with **24 features** related to customer behavior and service usage. 
  
Key findings:
- **28.7% churn rate** — higher than industry average
- **Tenure** is the strongest predictor of churn (customers with <6 months tenure churn 4x more)  
- **Month-to-month contracts** have 3x higher churn vs 2-year contracts
- Missing values are minimal (2.3%) and can be imputed with median values
- No significant class imbalance issues that would require SMOTE or oversampling`
}

const TABS = ['Overview', 'Preview', 'EDA', 'AI Summary']

export default function DatasetDetailPage() {
  const { id } = useParams()
  const [tab, setTab] = useState('Overview')

  return (
    <div className="p-6 space-y-5 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: 'var(--accent-muted)' }}>
            <Table size={18} style={{ color: 'var(--accent-primary)' }} />
          </div>
          <div>
            <h1 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>{mockEDA.name}</h1>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {mockEDA.rows.toLocaleString()} rows × {mockEDA.cols} columns
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost text-xs py-2">
            <RefreshCw size={12} /> Reprocess
          </button>
          <button className="btn-primary text-xs py-2">
            <Brain size={12} /> Train Model
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-lg w-fit" style={{ background: 'var(--bg-secondary)' }}>
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className="px-4 py-1.5 rounded-md text-sm font-medium transition-all"
            style={{
              background: tab === t ? 'var(--bg-elevated)' : 'transparent',
              color: tab === t ? 'var(--text-primary)' : 'var(--text-muted)',
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {tab === 'Overview' && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: 'Total Rows', value: mockEDA.rows.toLocaleString(), color: '#7c3aed' },
              { label: 'Columns', value: mockEDA.cols, color: '#06b6d4' },
              { label: 'Missing Values', value: mockEDA.missing, color: '#f59e0b' },
              { label: 'Duplicates', value: mockEDA.duplicates, color: '#10b981' },
            ].map(({ label, value, color }) => (
              <div key={label} className="stat-card">
                <p className="text-2xl font-bold" style={{ color }}>{value}</p>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Target Distribution */}
            <div className="card p-5">
              <p className="font-semibold text-sm mb-4" style={{ color: 'var(--text-primary)' }}>
                Target Distribution
              </p>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={mockEDA.targetDistribution} cx="50%" cy="50%"
                    outerRadius={70} dataKey="value" label={({ label, percent }) =>
                      `${label} ${(percent * 100).toFixed(0)}%`}>
                    {mockEDA.targetDistribution.map((_, i) => (
                      <Cell key={i} fill={COLORS[i]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* Feature Importance */}
            <div className="card p-5">
              <p className="font-semibold text-sm mb-4" style={{ color: 'var(--text-primary)' }}>
                Feature Importance
              </p>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={mockEDA.featureImportance} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-secondary)' }} axisLine={false} width={90} />
                  <Tooltip formatter={(v) => v.toFixed(3)} />
                  <Bar dataKey="importance" fill="#7c3aed" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </motion.div>
      )}

      {/* Preview Tab */}
      {tab === 'Preview' && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)', background: 'var(--bg-tertiary)' }}>
                    {Object.keys(mockEDA.preview[0]).map(k => (
                      <th key={k} className="text-left px-4 py-3 font-semibold"
                        style={{ color: 'var(--text-muted)' }}>{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {mockEDA.preview.map((row, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--border-subtle)' }}
                      onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-tertiary)'}
                      onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
                      {Object.values(row).map((v, j) => (
                        <td key={j} className="px-4 py-2.5" style={{ color: 'var(--text-secondary)' }}>
                          {String(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </motion.div>
      )}

      {/* EDA Tab */}
      {tab === 'EDA' && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
          <div className="card p-5">
            <p className="font-semibold text-sm mb-4" style={{ color: 'var(--text-primary)' }}>
              Missing Values by Column
            </p>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={mockEDA.missingByCol}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} />
                <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} />
                <Tooltip />
                <Bar dataKey="missing" fill="#f59e0b" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="card p-4">
              <p className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>Column Types</p>
              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span style={{ color: 'var(--text-secondary)' }}>Numeric</span>
                    <span style={{ color: '#06b6d4' }}>{mockEDA.numericCols} cols</span>
                  </div>
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${(mockEDA.numericCols/mockEDA.cols)*100}%`, background: '#06b6d4' }} />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span style={{ color: 'var(--text-secondary)' }}>Categorical</span>
                    <span style={{ color: '#7c3aed' }}>{mockEDA.categoricalCols} cols</span>
                  </div>
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${(mockEDA.categoricalCols/mockEDA.cols)*100}%` }} />
                  </div>
                </div>
              </div>
            </div>
            <div className="card p-4">
              <p className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>Data Quality</p>
              <div className="space-y-2 text-xs">
                {[
                  { label: 'Completeness', value: '97.7%', color: '#10b981' },
                  { label: 'Uniqueness', value: '99.9%', color: '#10b981' },
                  { label: 'Consistency', value: '94.2%', color: '#f59e0b' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="flex justify-between">
                    <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
                    <span style={{ color }}>{value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      )}

      {/* AI Summary Tab */}
      {tab === 'AI Summary' && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <Brain size={16} style={{ color: 'var(--accent-primary)' }} />
              <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                AI-Generated Dataset Summary
              </p>
            </div>
            <div className="text-sm leading-relaxed whitespace-pre-line"
              style={{ color: 'var(--text-secondary)' }}>
              {mockEDA.aiSummary}
            </div>
          </div>
        </motion.div>
      )}
    </div>
  )
}
