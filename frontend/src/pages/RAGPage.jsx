import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, Database, Plus, Zap, FileText, ChevronRight, Loader } from 'lucide-react'
import toast from 'react-hot-toast'

const mockIndexes = [
  { id: '1', name: 'Customer KB', dataset: 'knowledge_base.pdf', chunks: 342, model: 'all-MiniLM-L6-v2', created_at: '2024-01-14' },
  { id: '2', name: 'Support Docs', dataset: 'support_tickets.txt', chunks: 1240, model: 'text-embedding-ada-002', created_at: '2024-01-12' },
]

const mockResults = [
  {
    id: 1, score: 0.94,
    content: 'Customer churn is primarily driven by contract type, service quality, and monthly charges. Customers on month-to-month contracts have 3x higher churn rates compared to annual contracts.',
    source: 'knowledge_base.pdf', page: 12
  },
  {
    id: 2, score: 0.87,
    content: 'To reduce churn, focus on: (1) offering loyalty discounts after 12 months, (2) proactive outreach for customers with declining usage, (3) improving tech support response times.',
    source: 'knowledge_base.pdf', page: 24
  },
  {
    id: 3, score: 0.81,
    content: 'Customer satisfaction scores are strongly correlated with churn probability. A 1-point drop in CSAT score increases churn likelihood by 18%.',
    source: 'knowledge_base.pdf', page: 8
  },
]

export default function RAGPage() {
  const [selectedIndex, setSelectedIndex] = useState('1')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [aiAnswer, setAiAnswer] = useState('')
  const [loading, setLoading] = useState(false)
  const [showCreateIndex, setShowCreateIndex] = useState(false)

  const search = async () => {
    if (!query.trim()) return
    setLoading(true)
    setResults([])
    setAiAnswer('')
    await new Promise(r => setTimeout(r, 1200))
    setResults(mockResults)

    // Simulate streaming answer
    const answer = `Based on the retrieved documents, **customer churn** in your dataset is primarily influenced by:

1. **Contract Type** — Month-to-month customers churn at 3x the rate of annual contracts
2. **Tenure** — Customers in their first 6 months are most at risk
3. **Monthly Charges** — Higher charges correlate with increased churn probability

**Recommended Actions:**
- Implement early retention programs for new customers
- Offer loyalty incentives at the 12-month mark
- Proactively reach out to high-value customers showing declining engagement`

    setLoading(false)
    let i = 0
    const interval = setInterval(() => {
      if (i < answer.length) {
        setAiAnswer(prev => prev + answer[i])
        i++
      } else {
        clearInterval(interval)
      }
    }, 10)
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
        <button onClick={() => setShowCreateIndex(true)} className="btn-primary">
          <Plus size={14} /> Create Index
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
        {/* Indexes Sidebar */}
        <div className="space-y-3">
          <p className="section-title">Vector Indexes</p>
          {mockIndexes.map((idx) => (
            <button
              key={idx.id}
              onClick={() => setSelectedIndex(idx.id)}
              className="w-full text-left p-3 rounded-xl transition-all"
              style={{
                background: selectedIndex === idx.id ? 'var(--accent-muted)' : 'var(--bg-secondary)',
                border: `1px solid ${selectedIndex === idx.id ? 'var(--accent-primary)' : 'var(--border)'}`,
              }}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <Database size={13} style={{ color: selectedIndex === idx.id ? 'var(--accent-primary)' : 'var(--text-muted)' }} />
                <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {idx.name}
                </span>
              </div>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{idx.chunks} chunks</p>
              <p className="text-xs mt-0.5 truncate" style={{ color: 'var(--text-muted)' }}>{idx.dataset}</p>
            </button>
          ))}
        </div>

        {/* Search Area */}
        <div className="lg:col-span-3 space-y-4">
          {/* Search Input */}
          <div className="card p-4">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
                <input
                  className="input-base pl-9"
                  placeholder="Ask a question about your data..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && search()}
                />
              </div>
              <button onClick={search} disabled={loading || !query.trim()} className="btn-primary px-4">
                {loading ? <Loader size={14} className="animate-spin" /> : <Zap size={14} />}
                Search
              </button>
            </div>
            <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
              Using index: <strong style={{ color: 'var(--accent-primary)' }}>
                {mockIndexes.find(i => i.id === selectedIndex)?.name}
              </strong> • Model: all-MiniLM-L6-v2
            </p>
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
                  key={r.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.1 }}
                  className="card p-4"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <FileText size={12} style={{ color: 'var(--text-muted)' }} />
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                        {r.source} • Page {r.page}
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

          {!results.length && !loading && !aiAnswer && (
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
    </div>
  )
}
