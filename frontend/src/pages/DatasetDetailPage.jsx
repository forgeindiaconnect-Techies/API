import { useParams, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer
} from 'recharts'
import { Table, FileText, Brain, RefreshCw, Loader, AlertCircle, Sparkles } from 'lucide-react'
import { datasetAPI, multimodalAPI } from '../services/api'
import toast from 'react-hot-toast'

const formatSize = (bytes) => {
  if (!bytes) return '0 KB'
  if (bytes > 1e9) return `${(bytes / 1e9).toFixed(1)} GB`
  if (bytes > 1e6) return `${(bytes / 1e6).toFixed(1)} MB`
  return `${(bytes / 1e3).toFixed(0)} KB`
}

const TABS = ['Overview', 'Preview', 'EDA', 'AI Summary']

export default function DatasetDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [tab, setTab] = useState('Overview')
  const [dataset, setDataset] = useState(null)
  const [eda, setEda] = useState(null)
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [reprocessing, setReprocessing] = useState(false)
  const [error, setError] = useState(null)
  const [pollingError, setPollingError] = useState(null)
  
  // AI summary state
  const [aiSummary, setAiSummary] = useState('')
  const [generatingSummary, setGeneratingSummary] = useState(false)

  const loadData = async () => {
    console.log(`[DatasetDetailPage] loadData called for ID: ${id}`);
    
    // Client-side dataset ID validation: 24-character hexadecimal regex
    const isObjectId = /^[0-9a-fA-F]{24}$/.test(id);
    if (!isObjectId) {
      console.warn(`[DatasetDetailPage] Client-side ID validation failed: "${id}" is not a valid 24-character hex ObjectId`);
      setError(`Invalid dataset ID format ("${id}"). A dataset ID must be a 24-character hexadecimal string.`);
      setLoading(false);
      return;
    }

    try {
      setLoading(true)
      setError(null)
      const dsRes = await datasetAPI.get(id)
      console.log(`[DatasetDetailPage] Dataset details successfully loaded:`, dsRes.data);
      setDataset(dsRes.data)

      if (dsRes.data.status === 'ready' || dsRes.data.status === 'completed' || dsRes.data.status === 'indexed') {
        const supportEDA = ['csv', 'xlsx', 'xls', 'txt', 'md', 'pdf', 'docx'].includes(dsRes.data.file_type)
        const supportPreview = ['csv', 'xlsx', 'xls', 'txt', 'md', 'pdf', 'docx', 'json'].includes(dsRes.data.file_type)
        
        console.log(`[DatasetDetailPage] Fetching EDA and Preview for format: ${dsRes.data.file_type}`);
        try {
          const promises = []
          if (supportEDA) {
            promises.push(
              datasetAPI.getEDA(id)
                .then(res => {
                  console.log(`[DatasetDetailPage] EDA loaded successfully`);
                  setEda(res.data);
                })
                .catch(err => console.error(`[DatasetDetailPage] Failed to load EDA:`, err))
            );
          }
          if (supportPreview) {
            promises.push(
              datasetAPI.getPreview(id)
                .then(res => {
                  console.log(`[DatasetDetailPage] Preview loaded successfully`);
                  setPreview(res.data);
                })
                .catch(err => console.error(`[DatasetDetailPage] Failed to load Preview:`, err))
            );
          }
          await Promise.all(promises)
        } catch (err) {
          console.error('[DatasetDetailPage] Failed to load EDA or Preview data concurrently:', err)
        }
      }
    } catch (err) {
      console.error(`[DatasetDetailPage] Failed to load dataset details:`, err);
      const errMsg = err.response?.data?.detail || err.message || 'Failed to load dataset details';
      setError(errMsg);
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [id])

  useEffect(() => {
    let timeoutId;
    let active = true;
    let secondsElapsed = 0;
    let consecutiveErrors = 0;
    let currentInterval = 2000; // start with 2s

    const pollStatus = async () => {
      if (!active) return;
      
      try {
        const res = await datasetAPI.getStatus(id);
        if (!active) return;
        
        // Reset error states on successful response
        consecutiveErrors = 0;
        currentInterval = 2000;
        setPollingError(null);
        
        const currentStatus = res.data.status;
        
        if (currentStatus === 'completed' || currentStatus === 'ready' || currentStatus === 'indexed') {
          setReprocessing(false);
          loadData();
          return;
        } else if (currentStatus === 'failed' || currentStatus === 'error') {
          setReprocessing(false);
          setDataset(prev => prev ? { ...prev, status: 'failed', error_message: res.data.error_message || 'Processing failed' } : null);
          return;
        }
      } catch (err) {
        if (!active) return;
        consecutiveErrors += 1;
        console.error(`Error polling status (failures: ${consecutiveErrors}):`, err);
        
        // Exponential backoff: double the interval up to 10 seconds
        currentInterval = Math.min(currentInterval * 2, 10000);
        
        const errMsg = err.response?.data?.detail || err.message || "Connection error";
        
        if (consecutiveErrors >= 3) {
          setPollingError(`Backend server is currently unreachable (${errMsg}). Polling stopped.`);
          setReprocessing(false);
          return;
        }
      }
      
      // Check total timeout (limit to 3 minutes for larger datasets)
      secondsElapsed += currentInterval / 1000;
      if (secondsElapsed > 180) {
        setPollingError("Processing is taking longer than expected. Please try refreshing the page later.");
        setReprocessing(false);
        return;
      }
      
      timeoutId = setTimeout(pollStatus, currentInterval);
    };

    if (dataset && (dataset.status === 'processing' || reprocessing)) {
      setPollingError(null);
      timeoutId = setTimeout(pollStatus, currentInterval);
    }

    return () => {
      active = false;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [dataset?.status, reprocessing, id]);

  const handleReprocess = async () => {
    try {
      setReprocessing(true)
      setPollingError(null)
      await datasetAPI.process(id, {})
      toast.success('Reprocessing started')
    } catch (err) {
      toast.error('Failed to reprocess')
      setReprocessing(false)
    }
  }

  const handleGenerateAISummary = async () => {
    if (!dataset) return
    setGeneratingSummary(true)
    try {
      let summaryPrompt = ""
      if (['csv', 'xlsx', 'xls'].includes(dataset.file_type)) {
        summaryPrompt = `Analyze the tabular dataset named "${dataset.name}".
File type: ${dataset.file_type}
Size: ${formatSize(dataset.size_bytes)}
Rows: ${dataset.rows || 'Unknown'}
Columns: ${dataset.columns?.join(', ') || 'None'}
Status: ${dataset.status}
${eda ? `EDA summary: missing values: ${eda.missing_values}, duplicates: ${eda.duplicates}` : ''}

Generate a structured response with these EXACT headings:
### Dataset Summary
[Provide a clear overview of what the dataset contains, its purpose, and format]

### Key Topics
[Analyze the columns/data to identify the main themes or topics present]

### Main Entities
[Identify key entities, classes, or main categorical concepts]

### Sentiment Overview
[Provide a sentiment overview of the data columns or text targets]`
      } else if (['txt', 'md', 'pdf', 'docx'].includes(dataset.file_type)) {
        summaryPrompt = `Analyze the document dataset named "${dataset.name}".
File type: ${dataset.file_type}
Size: ${formatSize(dataset.size_bytes)}
Lines/Paragraphs: ${dataset.metadata?.lines || dataset.metadata?.paragraphs || dataset.rows || 'Unknown'}
Words: ${dataset.metadata?.words || 'Unknown'}
Characters: ${dataset.metadata?.chars || 'Unknown'}
Language: ${dataset.metadata?.language || 'English'}
Average Sentence Length: ${dataset.metadata?.avg_sentence_len || 'Unknown'} words
${eda?.top_keywords ? `Keywords: ${eda.top_keywords.join(', ')}` : ''}

Generate a structured response with these EXACT headings:
### Dataset Summary
[Provide a clear overview of the document's content, purpose, and key takeaways]

### Key Topics
[Identify the main themes, chapters, or topics discussed in the document]

### Main Entities
[Identify the main entities (people, organizations, places, products) mentioned in the document]

### Sentiment Overview
[Analyze and describe the general tone, mood, or sentiment of the document]`
      } else {
        summaryPrompt = `Analyze the dataset named "${dataset.name}".
File type: ${dataset.file_type}
Size: ${formatSize(dataset.size_bytes)}
Status: ${dataset.status}

Generate a structured response with these EXACT headings:
### Dataset Summary
[Provide a clear overview of the file]

### Key Topics
[Identify main topics]

### Main Entities
[Identify main entities]

### Sentiment Overview
[Provide a general tone/sentiment assessment]`
      }
      
      const res = await multimodalAPI.summarize({ text: summaryPrompt, max_length: 500, style: "concise" })
      setAiSummary(res.data.summary)
    } catch (err) {
      toast.error('Failed to generate AI Summary')
    } finally {
      setGeneratingSummary(false)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-2">
        <Loader size={32} className="animate-spin" style={{ color: 'var(--accent-primary)' }} />
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading dataset details...</p>
      </div>
    )
  }

  if (error || !dataset) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-center p-6 space-y-4">
        <AlertCircle size={48} style={{ color: '#ef4444' }} />
        <div className="space-y-1">
          <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>Failed to Load Dataset</h3>
          <p className="text-sm max-w-sm" style={{ color: 'var(--text-muted)' }}>{error || 'Dataset not found.'}</p>
        </div>
        <button onClick={loadData} className="btn-primary">Retry</button>
      </div>
    )
  }

  if (dataset.status === 'processing' || reprocessing) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-center p-6 space-y-4">
        {pollingError ? (
          <>
            <AlertCircle size={48} style={{ color: '#ef4444' }} />
            <div className="space-y-1">
              <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>Processing Timeout</h3>
              <p className="text-sm max-w-sm" style={{ color: 'var(--text-muted)' }}>{pollingError}</p>
            </div>
            <div className="flex gap-3">
              <button onClick={loadData} className="btn-primary">Refresh</button>
              <button onClick={handleReprocess} className="btn-ghost">Force Reprocess</button>
            </div>
          </>
        ) : (
          <>
            <Loader size={48} className="animate-spin" style={{ color: 'var(--accent-primary)' }} />
            <div className="space-y-1">
              <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>Dataset Processing in Progress</h3>
              <p className="text-sm max-w-sm" style={{ color: 'var(--text-muted)' }}>
                We are analyzing columns, counting rows, and running calculations. This will take a moment.
              </p>
            </div>
          </>
        )}
      </div>
    )
  }

  if (dataset.status === 'error' || dataset.status === 'failed') {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-center p-6 space-y-4">
        <AlertCircle size={48} style={{ color: '#ef4444' }} />
        <div className="space-y-1">
          <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>Processing Failed</h3>
          <p className="text-xs max-w-md border border-dashed rounded-lg p-3 mt-2 bg-red-500/10 text-red-400 font-mono text-left break-all" style={{ borderColor: 'rgba(239, 68, 68, 0.2)' }}>
            {dataset.error_message || 'An error occurred while attempting to parse or process this file.'}
          </p>
        </div>
        <button onClick={handleReprocess} className="btn-primary">
          <RefreshCw size={12} /> Retry Reprocess
        </button>
      </div>
    )
  }

  const isTabular = ['csv', 'xlsx', 'xls'].includes(dataset.file_type)
  const isTxt = ['txt', 'md'].includes(dataset.file_type)
  const isDoc = ['docx', 'pdf'].includes(dataset.file_type)
  const isImg = ['jpg', 'jpeg', 'png', 'webp'].includes(dataset.file_type)

  const missingByColData = eda?.missing_by_column
    ? Object.entries(eda.missing_by_column).map(([name, missing]) => ({ name, missing }))
    : []

  const wordFreqData = eda?.word_frequency
    ? Object.entries(eda.word_frequency).map(([name, count]) => ({ name, count }))
    : []
  const sentLenData = eda?.sentence_length_distribution
    ? Object.entries(eda.sentence_length_distribution).map(([name, count]) => ({ name, count }))
    : []
  const topKeywords = eda?.top_keywords || []

  let stats = []
  if (isTxt) {
    stats = [
      { label: 'Total Lines', value: dataset.metadata?.lines?.toLocaleString() || dataset.rows?.toLocaleString() || '—', color: '#7c3aed' },
      { label: 'Total Words', value: dataset.metadata?.words?.toLocaleString() || '—', color: '#06b6d4' },
      { label: 'Total Characters', value: dataset.metadata?.chars?.toLocaleString() || '—', color: '#f59e0b' },
      { label: 'File Size', value: formatSize(dataset.size_bytes), color: '#10b981' },
    ]
  } else if (isDoc) {
    stats = [
      { label: 'Pages / Paragraphs', value: dataset.metadata?.pages?.toLocaleString() || dataset.metadata?.paragraphs?.toLocaleString() || dataset.rows?.toLocaleString() || '—', color: '#7c3aed' },
      { label: 'Total Words', value: dataset.metadata?.words?.toLocaleString() || '—', color: '#06b6d4' },
      { label: 'Total Characters', value: dataset.metadata?.chars?.toLocaleString() || '—', color: '#f59e0b' },
      { label: 'File Size', value: formatSize(dataset.size_bytes), color: '#10b981' },
    ]
  } else if (isImg) {
    stats = [
      { label: 'Width', value: dataset.metadata?.width ? `${dataset.metadata.width} px` : '—', color: '#7c3aed' },
      { label: 'Height', value: dataset.metadata?.height ? `${dataset.metadata.height} px` : '—', color: '#06b6d4' },
      { label: 'Format / Mode', value: dataset.metadata?.format ? `${dataset.metadata.format} (${dataset.metadata.mode || ''})` : '—', color: '#f59e0b' },
      { label: 'File Size', value: formatSize(dataset.size_bytes), color: '#10b981' },
    ]
  } else {
    stats = [
      { label: 'Total Rows', value: dataset.rows?.toLocaleString() || '—', color: '#7c3aed' },
      { label: 'Columns', value: dataset.cols || '—', color: '#06b6d4' },
      { label: 'Missing Values', value: eda?.missing_values?.toLocaleString() || '0', color: '#f59e0b' },
      { label: 'Duplicates', value: eda?.duplicates?.toLocaleString() || '0', color: '#10b981' },
    ]
  }

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
            <h1 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>{dataset.name}</h1>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {isTxt
                ? `${dataset.metadata?.lines?.toLocaleString() || dataset.rows?.toLocaleString() || '—'} lines × ${dataset.metadata?.words?.toLocaleString() || '—'} words (${formatSize(dataset.size_bytes)})`
                : isDoc
                  ? `${dataset.metadata?.pages || dataset.metadata?.paragraphs || dataset.rows || '—'} pages/paragraphs × ${dataset.metadata?.words?.toLocaleString() || '—'} words (${formatSize(dataset.size_bytes)})`
                  : isImg
                    ? `${dataset.metadata?.width || '—'} × ${dataset.metadata?.height || '—'} pixels (${formatSize(dataset.size_bytes)})`
                    : `${dataset.rows ? `${dataset.rows.toLocaleString()} rows` : '—'} × ${dataset.cols || '—'} columns (${formatSize(dataset.size_bytes)})`
              }
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={handleReprocess} disabled={reprocessing} className="btn-ghost text-xs py-2">
            <RefreshCw size={12} className={reprocessing ? 'animate-spin' : ''} /> Reprocess
          </button>
          {isTabular && (
            <button onClick={() => navigate('/training')} className="btn-primary text-xs py-2">
              <Brain size={12} /> Train Model
            </button>
          )}
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

      {/* Tab Contents */}
      {tab === 'Overview' && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {stats.map(({ label, value, color }) => (
              <div key={label} className="stat-card">
                <p className="text-2xl font-bold" style={{ color }}>{value}</p>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</p>
              </div>
            ))}
          </div>

          {isImg && dataset.cloudinary_url && (
            <div className="card p-5 flex flex-col items-center justify-center space-y-3">
              <h3 className="font-semibold text-sm self-start" style={{ color: 'var(--text-primary)' }}>Image Preview</h3>
              <img src={dataset.cloudinary_url} alt={dataset.name} className="max-w-md max-h-96 rounded-lg shadow-md border" style={{ borderColor: 'var(--border)' }} />
            </div>
          )}

          {!isTabular && !isImg ? (
            <div className="card p-5 space-y-4">
              <div className="flex items-center gap-2">
                <FileText size={18} style={{ color: 'var(--accent-primary)' }} />
                <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Document Metadata Breakdown</h3>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                <div className="p-3 bg-slate-800/10 border border-slate-700/20 rounded-lg">
                  <p className="text-slate-400 font-medium">Language</p>
                  <p className="text-sm font-semibold text-white mt-1">{dataset.metadata?.language || 'English'}</p>
                </div>
                <div className="p-3 bg-slate-800/10 border border-slate-700/20 rounded-lg">
                  <p className="text-slate-400 font-medium">Avg Sentence Length</p>
                  <p className="text-sm font-semibold text-white mt-1">
                    {dataset.metadata?.avg_sentence_len ? `${dataset.metadata.avg_sentence_len} words` : '—'}
                  </p>
                </div>
                <div className="p-3 bg-slate-800/10 border border-slate-700/20 rounded-lg">
                  <p className="text-slate-400 font-medium">Total Words</p>
                  <p className="text-sm font-semibold text-white mt-1">{dataset.metadata?.words?.toLocaleString() || '—'}</p>
                </div>
                <div className="p-3 bg-slate-800/10 border border-slate-700/20 rounded-lg">
                  <p className="text-slate-400 font-medium">Total Characters</p>
                  <p className="text-sm font-semibold text-white mt-1">{dataset.metadata?.chars?.toLocaleString() || '—'}</p>
                </div>
              </div>
            </div>
          ) : isTabular && eda ? (
            <div className="card p-5 space-y-3">
              <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Columns & Statistical Summary</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)', background: 'var(--bg-tertiary)' }}>
                      <th className="text-left px-4 py-3 font-semibold" style={{ color: 'var(--text-muted)' }}>Column</th>
                      <th className="text-left px-4 py-3 font-semibold" style={{ color: 'var(--text-muted)' }}>Type</th>
                      <th className="text-left px-4 py-3 font-semibold" style={{ color: 'var(--text-muted)' }}>Nulls</th>
                      <th className="text-left px-4 py-3 font-semibold" style={{ color: 'var(--text-muted)' }}>Unique / Mean</th>
                      <th className="text-left px-4 py-3 font-semibold" style={{ color: 'var(--text-muted)' }}>Range (Min - Max)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(eda.column_stats || {}).map(([colName, stats]) => {
                      const isNumeric = stats.mean !== undefined
                      return (
                        <tr key={colName} style={{ borderBottom: '1px solid var(--border-subtle)' }}
                          onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-tertiary)'}
                          onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
                          <td className="px-4 py-2.5 font-medium" style={{ color: 'var(--text-primary)' }}>{colName}</td>
                          <td className="px-4 py-2.5" style={{ color: 'var(--text-secondary)' }}>
                            <span className={`badge ${isNumeric ? 'badge-green' : 'badge-violet'} text-[10px]`}>
                              {isNumeric ? 'Numeric' : 'Categorical'}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-xs" style={{ color: 'var(--text-secondary)' }}>{stats.nulls}</td>
                          <td className="px-4 py-2.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
                            {isNumeric ? stats.mean : `${stats.unique_values} values`}
                          </td>
                          <td className="px-4 py-2.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
                            {isNumeric ? `${stats.min} to ${stats.max}` : '—'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            isTabular && (
              <div className="card p-5 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
                No column statistical information available.
              </div>
            )
          )}
        </motion.div>
      )}

      {tab === 'Preview' && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          {!preview || preview.rows?.length === 0 ? (
            <div className="card p-5 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
              Preview is not available for this file type or is empty.
            </div>
          ) : (
            <div className="card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)', background: 'var(--bg-tertiary)' }}>
                      {preview.columns?.map(k => (
                        <th key={k} className="text-left px-4 py-3 font-semibold"
                          style={{ color: 'var(--text-muted)' }}>{k}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows?.map((row, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid var(--border-subtle)' }}
                        onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-tertiary)'}
                        onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
                        {preview.columns?.map((col) => (
                          <td key={col} className="px-4 py-2.5" style={{ color: 'var(--text-secondary)' }}>
                            {String(row[col])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </motion.div>
      )}

      {tab === 'EDA' && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
          {!isTabular && !['txt', 'md', 'pdf', 'docx'].includes(dataset.file_type) ? (
            <div className="card p-5 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
              EDA charts are only supported for document datasets (TXT, PDF, DOCX) and tabular CSV/Excel files.
            </div>
          ) : ['txt', 'md', 'pdf', 'docx'].includes(dataset.file_type) ? (
            <div className="space-y-4">
              {/* Word Frequency & Sentence Length charts */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="card p-5">
                  <p className="font-semibold text-sm mb-4" style={{ color: 'var(--text-primary)' }}>
                    Word Frequency Chart
                  </p>
                  {wordFreqData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={wordFreqData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} />
                        <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} />
                        <Tooltip />
                        <Bar dataKey="count" fill="var(--accent-primary)" radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-xs text-center py-8" style={{ color: 'var(--text-muted)' }}>No word frequency data available</p>
                  )}
                </div>

                <div className="card p-5">
                  <p className="font-semibold text-sm mb-4" style={{ color: 'var(--text-primary)' }}>
                    Sentence Length Distribution
                  </p>
                  {sentLenData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={sentLenData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} />
                        <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} />
                        <Tooltip />
                        <Bar dataKey="count" fill="#10b981" radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-xs text-center py-8" style={{ color: 'var(--text-muted)' }}>No sentence length distribution data available</p>
                  )}
                </div>
              </div>

              {/* Top Keywords */}
              <div className="card p-5 space-y-3">
                <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Top Keywords</p>
                <div className="flex flex-wrap gap-2">
                  {topKeywords.map((kw) => (
                    <span key={kw} className="badge badge-violet py-1 px-3 text-xs font-semibold">
                      {kw}
                    </span>
                  ))}
                  {topKeywords.length === 0 && (
                    <p className="text-xs" style={{ color: 'var(--text-muted)' }}>No keywords extracted.</p>
                  )}
                </div>
              </div>

              {/* Document Statistics Summary */}
              <div className="card p-5 grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  { label: 'Language', value: eda?.metadata?.language || 'English', color: '#7c3aed' },
                  { label: 'Avg Sentence Length', value: eda?.metadata?.avg_sentence_len ? `${eda.metadata.avg_sentence_len} words` : '—', color: '#06b6d4' },
                  { label: 'Total Words', value: eda?.metadata?.words?.toLocaleString() || '—', color: '#f59e0b' },
                  { label: 'Total Characters', value: eda?.metadata?.chars?.toLocaleString() || '—', color: '#10b981' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="stat-card border-none bg-slate-800/10">
                    <p className="text-xl font-bold" style={{ color }}>{value}</p>
                    <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : missingByColData.length === 0 ? (
            <div className="card p-5 text-center text-xs space-y-1">
              <p className="font-semibold" style={{ color: 'var(--text-primary)' }}>Perfect Data Quality!</p>
              <p style={{ color: 'var(--text-muted)' }}>No missing values found across any columns in this dataset.</p>
            </div>
          ) : (
            <div className="card p-5">
              <p className="font-semibold text-sm mb-4" style={{ color: 'var(--text-primary)' }}>
                Missing Values by Column
              </p>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={missingByColData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} />
                  <Tooltip />
                  <Bar dataKey="missing" fill="#f59e0b" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {isTabular && eda && (
            <div className="grid grid-cols-2 gap-4">
              <div className="card p-4">
                <p className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>Column Types</p>
                <div className="space-y-3">
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span style={{ color: 'var(--text-secondary)' }}>Numeric</span>
                      <span style={{ color: '#06b6d4' }}>{eda.numeric_columns?.length || 0} cols</span>
                    </div>
                    <div className="progress-bar">
                      <div className="progress-fill" style={{ width: `${((eda.numeric_columns?.length || 0) / (dataset.cols || 1)) * 100}%`, background: '#06b6d4' }} />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span style={{ color: 'var(--text-secondary)' }}>Categorical</span>
                      <span style={{ color: '#7c3aed' }}>{eda.categorical_columns?.length || 0} cols</span>
                    </div>
                    <div className="progress-bar">
                      <div className="progress-fill" style={{ width: `${((eda.categorical_columns?.length || 0) / (dataset.cols || 1)) * 100}%` }} />
                    </div>
                  </div>
                </div>
              </div>
              <div className="card p-4">
                <p className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>Data Cleanliness</p>
                <div className="space-y-2 text-xs">
                  {[
                    { label: 'Missing Values Count', value: eda.missing_values || 0, color: eda.missing_values > 0 ? '#f59e0b' : '#10b981' },
                    { label: 'Duplicate Rows Count', value: eda.duplicates || 0, color: eda.duplicates > 0 ? '#f59e0b' : '#10b981' },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="flex justify-between">
                      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
                      <span className="font-semibold" style={{ color }}>{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </motion.div>
      )}

      {tab === 'AI Summary' && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <div className="card p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Brain size={16} style={{ color: 'var(--accent-primary)' }} />
                <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                  AI-Generated Dataset Summary
                </p>
              </div>
              <button
                onClick={handleGenerateAISummary}
                disabled={generatingSummary}
                className="btn-primary text-xs py-1.5 px-3 flex items-center gap-1"
              >
                {generatingSummary ? (
                  <>
                    <Loader size={12} className="animate-spin" /> Analyzing...
                  </>
                ) : (
                  <>
                    <Sparkles size={12} /> {aiSummary ? 'Regenerate Summary' : 'Generate Summary'}
                  </>
                )}
              </button>
            </div>
            
            {aiSummary ? (
              <div className="text-sm leading-relaxed whitespace-pre-line border-l-2 pl-4 py-1"
                style={{ color: 'var(--text-secondary)', borderColor: 'var(--accent-primary)' }}>
                {aiSummary}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-center space-y-2">
                <Sparkles size={24} style={{ color: 'var(--text-muted)' }} />
                <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                  Click "Generate Summary" to have the AI analyze the schema, rows, and data profile.
                </p>
              </div>
            )}
          </div>
        </motion.div>
      )}
    </div>
  )
}
