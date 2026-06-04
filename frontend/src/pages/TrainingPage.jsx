import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { Brain, Play, Square, AlertTriangle, RefreshCw, Cpu, Database } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { datasetAPI, modelAPI } from '../services/api'
import toast from 'react-hot-toast'

const BASE_MODELS = [
  { id: 'llama3', label: 'Llama 3 8B', type: 'text' },
  { id: 'llama3:70b', label: 'Llama 3 70B', type: 'text' },
  { id: 'mistral', label: 'Mistral 7B', type: 'text' },
  { id: 'deepseek', label: 'DeepSeek 7B', type: 'text' },
  { id: 'vit', label: 'ViT-B/16', type: 'vision' },
  { id: 'whisper', label: 'Whisper Large', type: 'audio' },
]

const TECHNIQUES = ['LoRA', 'QLoRA', 'Full Fine-tuning', 'Adapter', 'Prompt Tuning']
const TASKS = ['Text Classification', 'Question Answering', 'Summarization', 'Named Entity Recognition', 'Sentiment Analysis']

export default function TrainingPage() {
  const navigate = useNavigate()
  const [datasets, setDatasets] = useState([])
  const [datasetsLoading, setDatasetsLoading] = useState(true)
  const [config, setConfig] = useState({
    name: '',
    model: 'llama3',
    dataset: '',
    technique: 'LoRA',
    task: 'Text Classification',
    epochs: 3,
    batchSize: 8,
    lr: 0.0002,
    loraR: 16,
    loraAlpha: 32,
  })

  const [training, setTraining] = useState(false)
  const [activeJobId, setActiveJobId] = useState(null)
  const [progress, setProgress] = useState(0)
  const [logs, setLogs] = useState([])
  const [lossData, setLossData] = useState([])
  const [step, setStep] = useState(0)

  const pollIntervalRef = useRef(null)

  // Fetch datasets
  const fetchDatasets = async () => {
    setDatasetsLoading(true)
    try {
      const { data } = await datasetAPI.list()
      // Only show datasets that are successfully processed and ready
      const readyDatasets = data.filter(d => d.status === 'ready')
      setDatasets(readyDatasets)
      if (readyDatasets.length > 0) {
        setConfig(prev => ({ ...prev, dataset: readyDatasets[0].id }))
      }
    } catch (err) {
      console.error('Failed to fetch datasets:', err)
      toast.error('Failed to load datasets')
    } finally {
      setDatasetsLoading(false)
    }
  }

  useEffect(() => {
    fetchDatasets()
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    }
  }, [])

  // Poll training progress and logs
  const pollTrainingStatus = async (jobId) => {
    try {
      // 1. Get status & metrics
      const { data: job } = await modelAPI.getTrainingStatus(jobId)
      setProgress(job.progress || 0)
      setStep(job.current_step || 0)

      if (job.train_loss !== undefined && job.train_loss !== null) {
        setLossData(prev => {
          // Avoid duplicate steps in charts
          if (prev.some(d => d.step === job.current_step)) return prev
          return [...prev, {
            step: job.current_step,
            train_loss: job.train_loss,
            val_loss: job.val_loss || job.train_loss + 0.05
          }].slice(-40) // Keep last 40 data points
        })
      }

      // Check termination states
      if (job.status === 'ready') {
        setTraining(false)
        setProgress(100)
        toast.success('Training completed successfully!')
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current)
          pollIntervalRef.current = null
        }
      } else if (job.status === 'error') {
        setTraining(false)
        toast.error('Training job failed!')
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current)
          pollIntervalRef.current = null
        }
      } else if (job.status === 'stopped') {
        setTraining(false)
        toast.error('Training was stopped.')
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current)
          pollIntervalRef.current = null
        }
      }

      // 2. Get logs
      const { data: logList } = await modelAPI.getTrainingLogs(jobId)
      setLogs(logList.map(l => ({
        t: new Date(l.timestamp).toLocaleTimeString(),
        msg: l.message
      })))
    } catch (err) {
      console.error('Error polling training status:', err)
    }
  }

  const startTraining = async () => {
    // Validation
    if (!config.name.trim()) {
      toast.error('Please specify a model name')
      return
    }
    if (!config.dataset) {
      toast.error('Please upload and select a dataset')
      return
    }

    try {
      // Format task slug as expected by backend
      const taskSlug = config.task.toLowerCase().replace(' ', '-')
      const requestPayload = {
        name: config.name,
        dataset_id: config.dataset,
        base_model: config.model,
        technique: config.technique,
        task: taskSlug,
        epochs: config.epochs,
        batch_size: config.batchSize,
        learning_rate: config.lr,
        lora_r: config.loraR,
        lora_alpha: config.loraAlpha
      }

      setTraining(true)
      setProgress(0)
      setStep(0)
      setLossData([])
      setLogs([{ t: new Date().toLocaleTimeString(), msg: 'Initializing training configuration...' }])
      
      const { data } = await modelAPI.startTraining(requestPayload)
      setActiveJobId(data.job_id)
      
      toast.success('Training job scheduled!')

      // Start interval
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = setInterval(() => {
        pollTrainingStatus(data.job_id)
      }, 1500)

    } catch (err) {
      console.error('Failed to start training:', err)
      setTraining(false)
      toast.error(err.response?.data?.detail || 'Failed to start training job')
    }
  }

  const stopTraining = async () => {
    if (!activeJobId) return
    try {
      await modelAPI.stopTraining(activeJobId)
      toast.success('Stopping training job...')
    } catch (err) {
      console.error('Failed to stop training:', err)
      toast.error('Failed to stop training')
    }
  }

  return (
    <div className="p-6 space-y-5 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>Model Training</h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Fine-tune LLMs with LoRA/QLoRA
          </p>
        </div>
      </div>

      {datasetsLoading ? (
        <div className="card p-8 flex flex-col items-center justify-center space-y-3 min-h-[30vh]">
          <RefreshCw size={24} className="animate-spin text-violet-500" />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading configuration datasets...</p>
        </div>
      ) : datasets.length === 0 ? (
        <div className="card p-8 text-center flex flex-col items-center justify-center space-y-4 max-w-2xl mx-auto mt-6 border-dashed border-2">
          <div className="w-16 h-16 rounded-full flex items-center justify-center bg-amber-500/10">
            <AlertTriangle size={32} className="text-amber-500" />
          </div>
          <div>
            <h3 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>Datasets Required</h3>
            <p className="text-sm mt-1 max-w-md mx-auto" style={{ color: 'var(--text-muted)' }}>
              No processed datasets were found in your library. You must upload and successfully process a dataset (e.g. CSV or TXT) before fine-tuning a model.
            </p>
          </div>
          <button onClick={() => navigate('/datasets')} className="btn-primary flex items-center gap-2">
            <Database size={16} /> Upload a Dataset
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Config Panel */}
          <div className="card p-5 space-y-4">
            <div className="flex items-center gap-2 mb-1">
              <Brain size={14} style={{ color: 'var(--accent-primary)' }} />
              <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Configuration</p>
            </div>

            <div>
              <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>
                Model Name
              </label>
              <input
                type="text"
                placeholder="e.g. classifier-v1"
                value={config.name}
                onChange={(e) => setConfig({ ...config, name: e.target.value })}
                disabled={training}
                className="input-base text-sm"
              />
            </div>

            {[
              { label: 'Base Model', key: 'model', options: BASE_MODELS.map(m => ({ value: m.id, label: m.label })) },
              { label: 'Dataset', key: 'dataset', options: datasets.map(d => ({ value: d.id, label: d.name })) },
              { label: 'Technique', key: 'technique', options: TECHNIQUES.map(t => ({ value: t, label: t })) },
              { label: 'Task', key: 'task', options: TASKS.map(t => ({ value: t, label: t })) },
            ].map(({ label, key, options }) => (
              <div key={key}>
                <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>
                  {label}
                </label>
                <select
                  value={config[key]}
                  onChange={(e) => setConfig({ ...config, [key]: e.target.value })}
                  disabled={training}
                  className="input-base text-sm"
                  style={{ background: 'var(--bg-tertiary)' }}
                >
                  {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            ))}

            <div className="grid grid-cols-2 gap-3">
              {[
                { label: 'Epochs', key: 'epochs', min: 1, max: 20 },
                { label: 'Batch Size', key: 'batchSize', min: 1, max: 64 },
              ].map(({ label, key, min, max }) => (
                <div key={key}>
                  <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>
                    {label}
                  </label>
                  <input
                    type="number" min={min} max={max}
                    value={config[key]}
                    onChange={(e) => setConfig({ ...config, [key]: +e.target.value })}
                    disabled={training}
                    className="input-base text-sm"
                  />
                </div>
              ))}
            </div>

            <div>
              <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>
                Learning Rate: {config.lr}
              </label>
              <input
                type="range" min={0.00001} max={0.001} step={0.00001}
                value={config.lr}
                onChange={(e) => setConfig({ ...config, lr: +e.target.value })}
                disabled={training}
                className="w-full cursor-pointer accent-violet-600"
              />
            </div>

            {config.technique.includes('LoRA') && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>
                    LoRA r
                  </label>
                  <input type="number" value={config.loraR}
                    onChange={(e) => setConfig({ ...config, loraR: +e.target.value })}
                    disabled={training}
                    className="input-base text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>
                    LoRA α
                  </label>
                  <input type="number" value={config.loraAlpha}
                    onChange={(e) => setConfig({ ...config, loraAlpha: +e.target.value })}
                    disabled={training}
                    className="input-base text-sm" />
                </div>
              </div>
            )}

            <button
              onClick={training ? stopTraining : startTraining}
              className={training ? 'btn-ghost w-full justify-center text-red-400 hover:text-red-300' : 'btn-primary w-full justify-center'}
            >
              {training ? <><Square size={14} /> Stop Training</> : <><Play size={14} /> Start Training</>}
            </button>
          </div>

          {/* Training Monitor */}
          <div className="lg:col-span-2 space-y-4">
            {/* Progress */}
            <div className="card p-5">
              <div className="flex items-center justify-between mb-3">
                <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                  Training Progress
                </p>
                <div className="flex items-center gap-2">
                  {training && (
                    <span className="w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse" />
                  )}
                  <span className="text-sm font-bold" style={{ color: 'var(--accent-primary)' }}>
                    {progress}%
                  </span>
                </div>
              </div>
              <div className="progress-bar" style={{ height: 8 }}>
                <motion.div
                  className="progress-fill"
                  style={{ height: '100%', borderRadius: 4 }}
                  animate={{ width: `${progress}%` }}
                  transition={{ duration: 0.2 }}
                />
              </div>
              <div className="flex justify-between text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                <span>Step {step}</span>
                <span>{config.epochs} epochs</span>
              </div>
            </div>

            {/* Loss Chart */}
            {lossData.length > 0 && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card p-5">
                <p className="font-semibold text-sm mb-4" style={{ color: 'var(--text-primary)' }}>
                  Training Loss
                </p>
                <ResponsiveContainer width="100%" height={160}>
                  <LineChart data={lossData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="step" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} />
                    <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} domain={['auto', 'auto']} />
                    <Tooltip />
                    <Line type="monotone" dataKey="train_loss" stroke="#7c3aed" strokeWidth={1.5} dot={false} name="Train Loss" />
                    <Line type="monotone" dataKey="val_loss" stroke="#06b6d4" strokeWidth={1.5} dot={false} name="Val Loss" />
                  </LineChart>
                </ResponsiveContainer>
              </motion.div>
            )}

            {/* Logs */}
            <div className="card p-4">
              <p className="font-semibold text-sm mb-3" style={{ color: 'var(--text-primary)' }}>
                Training Logs
              </p>
              <div className="code-block h-40 overflow-y-auto space-y-1 text-xs font-mono p-3 rounded" style={{ background: 'var(--bg-tertiary)' }}>
                {logs.length === 0 ? (
                  <p style={{ color: 'var(--text-muted)' }}>Logs will appear here when training starts...</p>
                ) : (
                  logs.map((l, i) => (
                    <div key={i} className="flex gap-2">
                      <span style={{ color: 'var(--text-muted)' }}>[{l.t}]</span>
                      <span style={{ color: '#a78bfa' }}>{l.msg}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
