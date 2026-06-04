import { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useDropzone } from 'react-dropzone'
import { Image, Mic, FileText, Wand2, Upload, Loader, Copy, Download, X } from 'lucide-react'
import toast from 'react-hot-toast'

const MODES = [
  { id: 'ocr', label: 'OCR Extraction', icon: FileText, desc: 'Extract text from images', accept: { 'image/*': [] } },
  { id: 'caption', label: 'Image Caption', icon: Image, desc: 'Auto-describe images', accept: { 'image/*': [] } },
  { id: 'transcribe', label: 'Audio Transcribe', icon: Mic, desc: 'Speech to text', accept: { 'audio/*': [] } },
  { id: 'generate', label: 'Image Generate', icon: Wand2, desc: 'Text to image', accept: null },
]

const mockResults = {
  ocr: `Invoice #INV-2024-001
Date: January 15, 2024
Client: Acme Corporation

Item                    Qty    Price     Total
---------------------------------------------------
AI Development Services   1   $5,000   $5,000.00
Data Analysis             3     $800   $2,400.00
Model Training            1   $1,200   $1,200.00
---------------------------------------------------
                               Subtotal: $8,600.00
                                    Tax: $860.00
                                  TOTAL: $9,460.00`,

  caption: `A professional office workspace featuring a modern dual-monitor setup with a MacBook Pro laptop. The desk is organized with a notebook, coffee mug, and small plant. Natural lighting streams in from a window on the left side. The overall aesthetic is minimalist and productive.

Detected objects: laptop, monitor (×2), keyboard, mouse, notebook, coffee mug, plant, desk lamp
Scene: Office/Workspace
Style: Modern, Minimalist`,

  transcribe: `[00:00:00] Hello and welcome to today's presentation on machine learning fundamentals.

[00:00:06] Today we'll be covering three main topics: supervised learning, unsupervised learning, and reinforcement learning.

[00:00:15] Let's start with supervised learning, which is the most common type used in industry today.

[00:00:22] In supervised learning, we train a model on labeled data, where each input has a corresponding output that we're trying to predict.

[00:00:31] Common examples include spam detection, image classification, and sentiment analysis.

Speaker confidence: 94.2%
Language: English (US)
Word count: 82`,
}

export default function MultimodalPage() {
  const [mode, setMode] = useState('ocr')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [result, setResult] = useState('')
  const [loading, setLoading] = useState(false)
  const [prompt, setPrompt] = useState('')

  const currentMode = MODES.find(m => m.id === mode)

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: currentMode?.accept || {},
    maxFiles: 1,
    onDrop: (files) => {
      if (!files[0]) return
      setFile(files[0])
      setResult('')
      if (files[0].type.startsWith('image/')) {
        const url = URL.createObjectURL(files[0])
        setPreview(url)
      } else {
        setPreview(null)
      }
    },
  })

  const process = async () => {
    if (mode !== 'generate' && !file) { toast.error('Please upload a file first'); return }
    if (mode === 'generate' && !prompt.trim()) { toast.error('Enter a prompt first'); return }

    setLoading(true)
    setResult('')

    await new Promise(r => setTimeout(r, 1800))

    if (mode === 'generate') {
      setResult('https://picsum.photos/seed/aistudio/512/512')
    } else {
      const text = mockResults[mode] || 'Processing complete.'
      setLoading(false)
      let i = 0
      const interval = setInterval(() => {
        if (i < text.length) {
          setResult(prev => prev + text[i++])
        } else {
          clearInterval(interval)
        }
      }, 8)
      return
    }
    setLoading(false)
  }

  const copyResult = () => {
    navigator.clipboard.writeText(result)
    toast.success('Copied!')
  }

  return (
    <div className="p-6 space-y-5 max-w-6xl mx-auto">
      <div>
        <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>Multimodal AI</h1>
        <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
          Process images, audio, and generate content with AI
        </p>
      </div>

      {/* Mode Selector */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {MODES.map(({ id, label, icon: Icon, desc }) => (
          <button key={id} onClick={() => { setMode(id); setFile(null); setPreview(null); setResult('') }}
            className="p-4 rounded-xl text-left transition-all"
            style={{
              background: mode === id ? 'var(--accent-muted)' : 'var(--bg-secondary)',
              border: `1px solid ${mode === id ? 'var(--accent-primary)' : 'var(--border)'}`,
            }}>
            <Icon size={18} className="mb-2"
              style={{ color: mode === id ? 'var(--accent-primary)' : 'var(--text-muted)' }} />
            <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{label}</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{desc}</p>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Input */}
        <div className="space-y-3">
          <p className="section-title">Input</p>

          {mode === 'generate' ? (
            <div className="card p-5 space-y-3">
              <label className="block text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Image Prompt
              </label>
              <textarea
                rows={4}
                className="input-base resize-none"
                placeholder="A futuristic city at sunset with neon lights and flying cars..."
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
              />
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Style', options: ['Photorealistic', 'Anime', 'Oil Painting', 'Digital Art'] },
                  { label: 'Size', options: ['512×512', '768×768', '1024×1024'] },
                ].map(({ label, options }) => (
                  <div key={label}>
                    <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>
                      {label}
                    </label>
                    <select className="input-base text-sm" style={{ background: 'var(--bg-tertiary)' }}>
                      {options.map(o => <option key={o}>{o}</option>)}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div {...getRootProps()}
              className={`upload-zone p-8 text-center cursor-pointer ${isDragActive ? 'drag-active' : ''}`}>
              <input {...getInputProps()} />
              {file ? (
                <div className="space-y-2">
                  {preview && (
                    <img src={preview} alt="preview" className="mx-auto max-h-40 rounded-lg object-cover" />
                  )}
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{file.name}</p>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    {(file.size / 1024).toFixed(1)} KB
                  </p>
                  <button onClick={e => { e.stopPropagation(); setFile(null); setPreview(null) }}
                    className="text-xs" style={{ color: '#ef4444' }}>
                    Remove
                  </button>
                </div>
              ) : (
                <>
                  <Upload size={28} className="mx-auto mb-3" style={{ color: 'var(--accent-primary)' }} />
                  <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                    {isDragActive ? 'Drop here' : 'Upload file'}
                  </p>
                  <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                    {mode === 'transcribe' ? 'MP3, WAV, M4A' : 'JPG, PNG, WEBP'}
                  </p>
                </>
              )}
            </div>
          )}

          <button onClick={process} disabled={loading}
            className="btn-primary w-full justify-center"
            style={{ opacity: loading ? 0.7 : 1 }}>
            {loading
              ? <><Loader size={14} className="animate-spin" /> Processing...</>
              : <><Wand2 size={14} /> {currentMode?.label}</>
            }
          </button>
        </div>

        {/* Output */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="section-title">Output</p>
            {result && mode !== 'generate' && (
              <button onClick={copyResult} className="btn-ghost py-1 text-xs">
                <Copy size={12} /> Copy
              </button>
            )}
          </div>

          <div className="card p-4 min-h-64">
            {!result && !loading ? (
              <div className="flex flex-col items-center justify-center h-48 text-center">
                <Wand2 size={24} className="mb-2" style={{ color: 'var(--text-muted)' }} />
                <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                  Results will appear here
                </p>
              </div>
            ) : loading ? (
              <div className="flex flex-col items-center justify-center h-48 gap-3">
                <div className="flex gap-1">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </div>
                <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Processing with AI...</p>
              </div>
            ) : mode === 'generate' && result ? (
              <div className="space-y-3">
                <img src={result} alt="generated" className="w-full rounded-lg" />
                <button className="btn-ghost w-full justify-center text-xs">
                  <Download size={12} /> Download
                </button>
              </div>
            ) : (
              <pre className="text-xs leading-relaxed whitespace-pre-wrap font-mono overflow-auto"
                style={{ color: 'var(--text-secondary)', fontFamily: 'JetBrains Mono, monospace' }}>
                {result}
              </pre>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
