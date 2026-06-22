import { useParams, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer
} from 'recharts'
import { Table, FileText, Brain, RefreshCw, Loader, AlertCircle, Sparkles, UploadCloud, Trash2 } from 'lucide-react'
import { datasetAPI, multimodalAPI, BASE_URL } from '../services/api'
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
      if (dsRes.data.stats) setEda(dsRes.data.stats)
      if (dsRes.data.preview) setPreview(dsRes.data.preview)

      if (dsRes.data.status === 'ready' || dsRes.data.status === 'completed' || dsRes.data.status === 'indexed') {
        const isImageDataset = dsRes.data.stats?.is_image_dataset || dsRes.data.metadata?.is_image_dataset || dsRes.data.preview?.is_image_dataset || dsRes.data.file_type === 'image_zip' || (dsRes.data.metadata?.type === 'image_dataset') || dsRes.data.name?.toLowerCase().endsWith('.zip');
        const supportEDA = ['csv', 'xlsx', 'xls', 'txt', 'md', 'pdf', 'docx'].includes(dsRes.data.file_type) || isImageDataset
        const supportPreview = ['csv', 'xlsx', 'xls', 'txt', 'md', 'pdf', 'docx', 'json'].includes(dsRes.data.file_type) || isImageDataset
        
        console.log(`[DatasetDetailPage] Fetching EDA and Preview. supportEDA: ${supportEDA}, supportPreview: ${supportPreview}`);
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
      
      // Check total timeout (limit to 30 minutes for larger datasets)
      secondsElapsed += currentInterval / 1000;
      if (secondsElapsed > 1800) {
        setPollingError("Processing is taking longer than expected. Please try refreshing the page later.");
        setReprocessing(false);
        return;
      }
      
      timeoutId = setTimeout(pollStatus, currentInterval);
    };

    const isProcessing = dataset && (['processing', 'uploaded', 'extracted', 'preprocessing', 'embedding', 'embedded'].includes(dataset.status) || reprocessing);
    if (isProcessing) {
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

  const handleDelete = async () => {
    if (!window.confirm(`Delete "${dataset?.name}"? This cannot be undone.`)) return
    try {
      await datasetAPI.delete(id)
      toast.success('Dataset deleted')
      navigate('/datasets')
    } catch (err) {
      toast.error(`Failed to delete: ${err.response?.data?.detail || err.message}`)
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

  const isProcessingState = ['processing', 'uploaded', 'extracted', 'preprocessing', 'embedding', 'embedded'].includes(dataset.status) || reprocessing;
  if (isProcessingState) {
    const steps = [
      { id: 'uploaded', label: 'Uploaded' },
      { id: 'extracted', label: 'Extracted' },
      { id: 'preprocessing', label: 'Preprocessing' },
      { id: 'embedding', label: 'Embedding' },
      { id: 'embedded', label: 'Embedded' },
      { id: 'ready', label: 'Ready' }
    ];
    const currentStepIdx = steps.findIndex(s => s.id === dataset.status);
    const isImageDataset = dataset.name?.toLowerCase().endsWith('.zip') || dataset.metadata?.is_image_dataset || dataset.metadata?.type === 'image_dataset';

    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-center p-6 space-y-6">
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
            <div className="relative flex items-center justify-center">
              <Loader size={56} className="animate-spin absolute" style={{ color: 'var(--accent-primary)', opacity: 0.15 }} />
              <div className="w-10 h-10 rounded-full flex items-center justify-center bg-violet-600/10 text-violet-500 animate-pulse font-bold text-sm">
                {currentStepIdx >= 0 ? `${Math.round(((currentStepIdx + 1) / steps.length) * 100)}%` : '...'}
              </div>
            </div>
            <div className="space-y-1">
              <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                {isImageDataset ? 'CNN Image Preprocessing Pipeline' : 'Dataset Processing in Progress'}
              </h3>
              <p className="text-sm max-w-md mx-auto" style={{ color: 'var(--text-muted)' }}>
                {isImageDataset 
                  ? 'Extracting archives, validating images, running CNN pipeline and generating search embeddings.'
                  : 'We are analyzing columns, counting rows, and running calculations. This will take a moment.'}
              </p>
            </div>
            
            {/* Visual Stepper for image datasets */}
            {isImageDataset && currentStepIdx >= 0 && (
              <div className="w-full max-w-lg mt-6 p-4 rounded-xl border border-slate-800 bg-slate-950/20 space-y-5">
                <div className="flex justify-between items-center relative px-2">
                  <div className="absolute top-1/2 left-0 right-0 h-0.5 bg-slate-800 -translate-y-1/2 z-0" />
                  <div 
                    className="absolute top-1/2 left-0 h-0.5 bg-violet-500 -translate-y-1/2 z-0 transition-all duration-500" 
                    style={{ width: `${(currentStepIdx / (steps.length - 1)) * 90 + 5}%` }}
                  />
                  
                  {steps.map((step, idx) => {
                    const isCompleted = idx < currentStepIdx;
                    const isActive = idx === currentStepIdx;
                    return (
                      <div key={step.id} className="flex flex-col items-center z-10 relative">
                        <div 
                          className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-xs border transition-all duration-300 ${
                            isCompleted 
                              ? 'bg-violet-600 border-violet-600 text-white' 
                              : isActive 
                                ? 'bg-slate-900 border-violet-500 text-violet-400 ring-4 ring-violet-500/10' 
                                : 'bg-slate-950 border-slate-800 text-gray-600'
                          }`}
                        >
                          {isCompleted ? '✓' : idx + 1}
                        </div>
                        <span className={`text-[10px] mt-1.5 font-medium transition-colors ${
                          isActive ? 'text-violet-400 font-semibold' : isCompleted ? 'text-gray-300' : 'text-gray-600'
                        }`}>
                          {step.label}
                        </span>
                      </div>
                    );
                  })}
                </div>
                <div className="text-[11px] text-gray-400 bg-slate-900/40 p-2.5 rounded-lg font-mono inline-block">
                  {dataset.status === 'uploaded' && '⚡ [UPLOADED] Extracting ZIP archive and validating contents...'}
                  {dataset.status === 'extracted' && '⚡ [EXTRACTED] De-duplicating files and running CNN split preprocessing...'}
                  {dataset.status === 'preprocessing' && '⚡ [PREPROCESSING] Resizing images, augmenting, and compressing...'}
                  {dataset.status === 'embedding' && `⚡ [EMBEDDING] Generating embeddings: Batch ${dataset.embedding_progress?.current_batch || 0}/${dataset.embedding_progress?.total_batches || 0}`}
                  {dataset.status === 'embedded' && '⚡ [EMBEDDED] Connecting to ChromaDB and compiling EDA stats...'}
                  {dataset.status === 'processing' && '⚡ Processing dataset index...'}
                </div>

                {/* Real-time embedding progress details */}
                {dataset.status === 'embedding' && dataset.embedding_progress && (
                  <div className="pt-3 border-t border-slate-850 space-y-3 text-left">
                    <div className="flex justify-between text-xs font-semibold">
                      <span className="text-gray-400">Embedding Progress</span>
                      <span className="text-violet-400">
                        {Math.round(((dataset.embedding_progress.processed_images || 0) / (dataset.embedding_progress.total_images || 1)) * 100)}%
                      </span>
                    </div>
                    <div className="w-full h-1.5 rounded-full bg-slate-900 border border-slate-850 overflow-hidden">
                      <div 
                        className="h-full bg-violet-500 transition-all duration-300"
                        style={{ width: `${((dataset.embedding_progress.processed_images || 0) / (dataset.embedding_progress.total_images || 1)) * 100}%` }}
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-y-1.5 text-[10px] font-mono text-gray-500">
                      <div>Processed Images: <span className="text-gray-300 font-semibold">{dataset.embedding_progress.processed_images || 0} / {dataset.embedding_progress.total_images || 0}</span></div>
                      <div className="text-right">Current Batch: <span className="text-gray-300 font-semibold">{dataset.embedding_progress.current_batch || 0} / {dataset.embedding_progress.total_batches || 0}</span></div>
                      <div className="col-span-2">Est. Time Remaining: <span className="text-violet-400 font-semibold">{dataset.embedding_progress.estimated_remaining_seconds ? `${Math.round(dataset.embedding_progress.estimated_remaining_seconds)}s` : 'calculating...'}</span></div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    );
  }

  if (dataset.status === 'error' || dataset.status === 'failed') {
    // Detect irrecoverable datasets: file is gone from disk AND no cloud backup was ever created.
    // Retrying will never work — the original file no longer exists anywhere.
    const isIrrecoverable = dataset.error_message &&
      (dataset.error_message.includes('All recovery methods') ||
       dataset.error_message.includes('Local File was MISSING') ||
       dataset.error_message.includes('File Recovery Failure') ||
       dataset.error_message.includes('File Access Failure'))

    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-center p-6 space-y-4">
        {isIrrecoverable ? (
          <UploadCloud size={48} style={{ color: '#f59e0b' }} />
        ) : (
          <AlertCircle size={48} style={{ color: '#ef4444' }} />
        )}
        <div className="space-y-2">
          <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
            {isIrrecoverable ? 'File No Longer Available' : 'Processing Failed'}
          </h3>
          {isIrrecoverable ? (
            <>
              <p className="text-sm max-w-sm" style={{ color: 'var(--text-muted)' }}>
                This dataset's file was lost during a server restart and was never backed up to cloud storage.
                It cannot be recovered automatically.
              </p>
              <p className="text-xs px-4 py-2 rounded-lg font-medium" style={{ color: '#f59e0b', background: 'rgba(245, 158, 11, 0.1)' }}>
                💡 Please delete this dataset and re-upload the original file.
              </p>
            </>
          ) : (
            <p className="text-xs max-w-md border border-dashed rounded-lg p-3 mt-2 bg-red-500/10 text-red-400 font-mono text-left break-all" style={{ borderColor: 'rgba(239, 68, 68, 0.2)' }}>
              {dataset.error_message || 'An error occurred while attempting to parse or process this file.'}
            </p>
          )}
        </div>
        <div className="flex gap-3">
          {isIrrecoverable ? (
            <button onClick={handleDelete} className="btn-primary" style={{ background: '#ef4444' }}>
              <Trash2 size={12} /> Delete & Re-upload
            </button>
          ) : (
            <button onClick={handleReprocess} disabled={reprocessing} className="btn-primary">
              <RefreshCw size={12} className={reprocessing ? 'animate-spin' : ''} /> Retry Reprocess
            </button>
          )}
          <button onClick={() => navigate('/datasets')} className="btn-ghost">
            Back to Datasets
          </button>
        </div>
      </div>
    )
  }

  const isImageDataset = dataset.stats?.is_image_dataset || dataset.metadata?.is_image_dataset || dataset.preview?.is_image_dataset || dataset.file_type === 'image_zip' || (dataset.metadata?.type === 'image_dataset');
  const isTabular = ['csv', 'xlsx', 'xls'].includes(dataset.file_type) && !isImageDataset
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
  if (isImageDataset) {
    stats = [
      { label: 'Total Images', value: dataset.stats?.valid_images?.toLocaleString() || dataset.rows?.toLocaleString() || '—', color: '#7c3aed' },
      { label: 'Classes / Categories', value: dataset.stats?.class_distribution ? Object.keys(dataset.stats.class_distribution).length.toLocaleString() : '—', color: '#06b6d4' },
      { label: 'Train / Val / Test', value: dataset.stats?.split_counts ? `${dataset.stats.split_counts.train} / ${dataset.stats.split_counts.val} / ${dataset.stats.split_counts.test}` : '—', color: '#f59e0b' },
      { label: 'File Size', value: formatSize(dataset.size_bytes), color: '#10b981' },
    ]
  } else if (isTxt) {
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
          {isImageDataset ? (
            <div className="card p-5 space-y-4">
              <div className="flex justify-between items-center">
                <div>
                  <h3 className="font-semibold text-sm text-white">Preprocessed CNN Dataset Preview</h3>
                  <p className="text-xs text-gray-500">Showing first {preview?.images?.length || 0} preprocessed images with class labels</p>
                </div>
                {(dataset.preprocessed_zip_path || dataset.gridfs_id) && (
                  <a
                    href={`${BASE_URL}/datasets/${id}/download`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-primary text-xs py-1.5 px-3 bg-violet-600 hover:bg-violet-700 text-white flex items-center gap-1.5 rounded-lg font-medium shadow-lg transition-all duration-300"
                    style={{ background: 'var(--accent-primary)' }}
                  >
                    <UploadCloud size={13} className="rotate-180" /> Download Preprocessed ZIP
                  </a>
                )}
              </div>
              {!preview?.images || preview.images.length === 0 ? (
                <p className="text-xs text-center py-8 text-gray-500">No previews available</p>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
                  {preview.images.map((img, i) => (
                    <div key={i} className="group relative rounded-xl border border-slate-800 bg-slate-950/40 p-2 hover:border-violet-500/40 transition-all duration-300">
                      <div className="aspect-square overflow-hidden rounded-lg bg-slate-900 flex items-center justify-center border border-slate-900">
                        <img 
                          src={`data:image/jpeg;base64,${img.thumbnail}`} 
                          alt={img.filename} 
                          className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" 
                        />
                      </div>
                      <div className="mt-2.5 px-0.5 space-y-0.5">
                        <p className="text-[10px] font-semibold text-gray-300 truncate" title={img.filename}>
                          {img.filename}
                        </p>
                        <div className="flex items-center justify-between">
                          <span className="badge badge-violet text-[8px] font-bold tracking-wide uppercase px-1.5 py-0.5 rounded">
                            {img.class_name}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : !preview || preview.rows?.length === 0 ? (
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
          {isImageDataset && eda ? (
            <div className="space-y-4">
              {/* Image EDA Metrics Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="card p-5 space-y-2">
                  <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Resolution Summary</p>
                  <p className="text-2xl font-bold text-violet-400">
                    {eda.resolution_stats?.mean_width ? `${Math.round(eda.resolution_stats.mean_width)} × ${Math.round(eda.resolution_stats.mean_height)}` : '—'}
                  </p>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Average dimensions (pixels)</p>
                </div>
                <div className="card p-5 space-y-2">
                  <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Dimension Limits</p>
                  <div className="text-sm font-semibold text-gray-300">
                    <p>Width: {eda.resolution_stats?.min_width || 0} to {eda.resolution_stats?.max_width || 0} px</p>
                    <p>Height: {eda.resolution_stats?.min_height || 0} to {eda.resolution_stats?.max_height || 0} px</p>
                  </div>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Min - Max range</p>
                </div>
                <div className="card p-5 space-y-2">
                  <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>File Integrity</p>
                  <p className="text-2xl font-bold text-emerald-400">
                    {eda.valid_images !== undefined && eda.total_images !== undefined
                      ? `${Math.round((eda.valid_images / eda.total_images) * 100)}%`
                      : '100%'}
                  </p>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    {eda.valid_images || 0} valid / {eda.total_images || 0} total images
                  </p>
                </div>
              </div>

              {/* Class Distribution Chart & Split Breakdown */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="card p-5">
                  <p className="font-semibold text-sm mb-4" style={{ color: 'var(--text-primary)' }}>
                    Class Distribution
                  </p>
                  {Object.keys(eda.class_distribution || {}).length > 0 ? (
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={Object.entries(eda.class_distribution).map(([name, count]) => ({ name, count }))}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} />
                        <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} />
                        <Tooltip />
                        <Bar dataKey="count" fill="var(--accent-primary)" radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-xs text-center py-8" style={{ color: 'var(--text-muted)' }}>No class distribution data available</p>
                  )}
                </div>

                <div className="card p-5 flex flex-col justify-between">
                  <div>
                    <h4 className="font-semibold text-sm mb-4" style={{ color: 'var(--text-primary)' }}>Stratified Split Breakdown</h4>
                    {eda.split_counts ? (
                      <div className="space-y-4">
                        {(() => {
                          const total = (eda.split_counts.train || 0) + (eda.split_counts.val || 0) + (eda.split_counts.test || 0) || 1;
                          const trainPct = Math.round((eda.split_counts.train / total) * 100);
                          const valPct = Math.round((eda.split_counts.val / total) * 100);
                          const testPct = Math.round((eda.split_counts.test / total) * 100);
                          return (
                            <>
                              <div className="h-4 rounded-full overflow-hidden flex bg-slate-900 border border-slate-800">
                                <div style={{ width: `${trainPct}%`, backgroundColor: 'var(--accent-primary)' }} title={`Train: ${trainPct}%`} className="h-full transition-all" />
                                <div style={{ width: `${valPct}%`, backgroundColor: '#06b6d4' }} title={`Val: ${valPct}%`} className="h-full transition-all" />
                                <div style={{ width: `${testPct}%`, backgroundColor: '#f59e0b' }} title={`Test: ${testPct}%`} className="h-full transition-all" />
                              </div>
                              <div className="grid grid-cols-3 gap-2 text-xs">
                                <div className="flex flex-col p-2.5 rounded-lg bg-slate-900/40 border border-slate-800">
                                  <div className="flex items-center gap-1.5 font-medium text-gray-300">
                                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: 'var(--accent-primary)' }} />
                                    Train (70%)
                                  </div>
                                  <p className="text-sm font-bold mt-1 text-white">{eda.split_counts.train} <span className="text-[9px] text-gray-500 font-normal">({trainPct}%)</span></p>
                                </div>
                                <div className="flex flex-col p-2.5 rounded-lg bg-slate-900/40 border border-slate-800">
                                  <div className="flex items-center gap-1.5 font-medium text-gray-300">
                                    <div className="w-2 h-2 rounded-full bg-cyan-500" />
                                    Val (15%)
                                  </div>
                                  <p className="text-sm font-bold mt-1 text-white">{eda.split_counts.val} <span className="text-[9px] text-gray-500 font-normal">({valPct}%)</span></p>
                                </div>
                                <div className="flex flex-col p-2.5 rounded-lg bg-slate-900/40 border border-slate-800">
                                  <div className="flex items-center gap-1.5 font-medium text-gray-300">
                                    <div className="w-2 h-2 rounded-full bg-amber-500" />
                                    Test (15%)
                                  </div>
                                  <p className="text-sm font-bold mt-1 text-white">{eda.split_counts.test} <span className="text-[9px] text-gray-500 font-normal">({testPct}%)</span></p>
                                </div>
                              </div>
                            </>
                          );
                        })()}
                      </div>
                    ) : (
                      <p className="text-xs text-center py-8" style={{ color: 'var(--text-muted)' }}>No split count information available</p>
                    )}
                  </div>
                </div>
              </div>

              {/* Integrity & Corruption Report */}
              {eda.missing_or_corrupt_report && eda.missing_or_corrupt_report.length > 0 ? (
                <div className="card p-4 border border-amber-950 bg-amber-950/10 space-y-2">
                  <div className="flex items-center gap-2 text-amber-400">
                    <AlertCircle size={16} />
                    <p className="text-sm font-semibold">Corrupted / Skipped Files Report ({eda.missing_or_corrupt_report.length})</p>
                  </div>
                  <p className="text-[11px] text-amber-500/80">These files were invalid, corrupted, or not recognized as valid images and were discarded from the training pipeline:</p>
                  <div className="max-h-36 overflow-y-auto font-mono text-[10px] text-gray-400 bg-slate-950/50 p-2.5 rounded-lg border border-slate-800 space-y-1">
                    {eda.missing_or_corrupt_report.map((item, idx) => (
                      <div key={idx} className="truncate border-b border-slate-900 pb-1 last:border-0 last:pb-0">{item}</div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="card p-4 flex items-center gap-3 border border-emerald-950 bg-emerald-950/10 text-emerald-400">
                  <AlertCircle size={18} className="text-emerald-500 shrink-0" />
                  <div className="text-xs">
                    <p className="font-semibold">All Files Validated Successfully</p>
                    <p className="text-emerald-500/80 mt-0.5">No corrupted images, unrecognized formats, or missing attributes were encountered.</p>
                  </div>
                </div>
              )}
            </div>
          ) : !isTabular && !['txt', 'md', 'pdf', 'docx'].includes(dataset.file_type) ? (
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
