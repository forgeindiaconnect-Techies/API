import { useState, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Plus, Trash2, Bot, User, Copy, RefreshCw,
  ChevronDown, Paperclip, Mic, Square, X
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { useChatStore } from '../store'
import { chatAPI, ragAPI, datasetAPI } from '../services/api'
import toast from 'react-hot-toast'

const MODELS = [
  { id: 'llama3', label: 'Llama 3 8B' },
  { id: 'llama3:70b', label: 'Llama 3 70B' },
  { id: 'mistral', label: 'Mistral 7B' },
  { id: 'deepseek', label: 'DeepSeek' },
]

export default function ChatPage() {
  const { id: urlId } = useParams()
  const navigate = useNavigate()
  const {
    conversations, activeConversationId, messages, isStreaming,
    selectedModel, setActiveConversation, setConversations, addConversation,
    removeConversation, setMessages, addMessage, appendToLastMessage, setStreaming, setModel
  } = useChatStore()

  const [input, setInput] = useState('')
  const [modelMenuOpen, setModelMenuOpen] = useState(false)
  const [contextMenuOpen, setContextMenuOpen] = useState(false)
  const [indexes, setIndexes] = useState([])
  const [datasets, setDatasets] = useState([])
  const [selectedIndexId, setSelectedIndexId] = useState(null)
  const [selectedDatasetId, setSelectedDatasetId] = useState(null)
  const [datasetMode, setDatasetMode] = useState('dataset_llm')
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  const fetchConversations = async () => {
    try {
      const { data } = await chatAPI.getConversations()
      setConversations(data)
      if (data.length > 0 && !urlId) {
        setActiveConversation(data[0].id)
        navigate(`/chat/${data[0].id}`)
      }
    } catch (err) {
      toast.error('Failed to load chat history')
    }
  }

  useEffect(() => {
    fetchConversations()
    ragAPI.listIndexes().then(({ data }) => {
      setIndexes(data.filter(idx => idx.status === 'ready'))
    }).catch(() => {})
    datasetAPI.list().then(({ data }) => {
      setDatasets(data.filter(ds => ds.status === 'ready'))
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (urlId) {
      setActiveConversation(urlId)
      if (!messages[urlId]) {
        chatAPI.getMessages(urlId).then(({ data }) => {
          setMessages(urlId, data)
        }).catch(() => {
          toast.error('Failed to load messages')
        })
      }
    } else if (conversations.length > 0) {
      setActiveConversation(conversations[0]?.id)
      navigate(`/chat/${conversations[0]?.id}`)
    }
  }, [urlId, conversations.length])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, activeConversationId])

  const currentMessages = messages[activeConversationId] || []

  const sendMessage = async () => {
    if (!input.trim() || isStreaming) return
    const text = input.trim()
    setInput('')

    let activeId = activeConversationId
    if (!activeId) {
      // Create a conversation first
      try {
        const { data } = await chatAPI.createConversation({
          title: text.slice(0, 30) + (text.length > 30 ? '...' : ''),
          model: selectedModel,
        })
        addConversation(data)
        activeId = data.id
        setActiveConversation(activeId)
        navigate(`/chat/${activeId}`)
      } catch (err) {
        toast.error('Failed to start new chat')
        return
      }
    }

    const userMsg = { id: Date.now().toString(), role: 'user', content: text }
    addMessage(activeId, userMsg)

    const assistantMsgId = (Date.now() + 1).toString()
    const assistantMsg = { id: assistantMsgId, role: 'assistant', content: '' }
    addMessage(activeId, assistantMsg)
    setStreaming(true)

    try {
      await chatAPI.streamMessage(
        activeId,
        {
          content: text,
          model: selectedModel,
          temperature: 0.7,
          max_tokens: 2048,
          index_id: selectedIndexId || undefined,
          dataset_id: selectedDatasetId || undefined,
          mode: 'dataset_only'
        },
        (chunk) => {
          if (chunk.token) {
            appendToLastMessage(activeId, chunk.token)
          }
        },
        () => {
          setStreaming(false)
          chatAPI.getConversations().then(({ data }) => setConversations(data))
        }
      )
    } catch (err) {
      toast.error(err.message || 'Connection lost')
      setStreaming(false)
    }
  }

  const deleteChat = async (chatId) => {
    try {
      await chatAPI.deleteConversation(chatId)
      removeConversation(chatId)
      toast.success('Conversation deleted')
      if (activeConversationId === chatId) {
        setActiveConversation(null)
        navigate('/chat')
      }
    } catch (err) {
      toast.error('Failed to delete conversation')
    }
  }

  const newChat = async () => {
    try {
      const { data } = await chatAPI.createConversation({
        title: 'New conversation',
        model: selectedModel,
      })
      addConversation(data)
      setActiveConversation(data.id)
      navigate(`/chat/${data.id}`)
    } catch (err) {
      toast.error('Failed to create new conversation')
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="flex h-full w-full">
      {/* Conversations Sidebar */}
      <div className="w-60 flex-shrink-0 flex flex-col h-full"
        style={{ borderRight: '1px solid var(--border)', background: 'var(--bg-secondary)' }}>
        <div className="p-3">
          <button onClick={newChat} className="btn-primary w-full justify-center text-xs py-2">
            <Plus size={14} /> New Chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 space-y-0.5">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={`group w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-xs transition-colors ${activeConversationId === conv.id ? 'active-conv' : ''}`}
              style={{
                background: activeConversationId === conv.id ? 'var(--accent-muted)' : 'transparent',
              }}
            >
              <button
                onClick={() => { setActiveConversation(conv.id); navigate(`/chat/${conv.id}`) }}
                className="flex-1 text-left truncate font-medium mr-2"
                style={{
                  color: activeConversationId === conv.id ? 'var(--accent-primary)' : 'var(--text-secondary)',
                }}
              >
                {conv.title}
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); deleteChat(conv.id) }}
                className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-slate-700/50 text-slate-400 hover:text-red-400 transition-opacity"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="flex items-center gap-2">
            <Bot size={16} style={{ color: 'var(--accent-primary)' }} />
            <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              AI Assistant
            </span>
          </div>

          {/* Context & Model selector */}
          <div className="flex gap-2 relative">
            {/* Context Dropdown */}
            <div className="relative">
              <button
                onClick={() => {
                  setContextMenuOpen(!contextMenuOpen)
                  setModelMenuOpen(false)
                }}
                className="btn-ghost py-1.5 px-2.5 text-xs flex items-center gap-1.5"
                style={{
                  border: (selectedIndexId || selectedDatasetId) ? '1px solid var(--accent-primary)' : '1px solid transparent',
                  background: (selectedIndexId || selectedDatasetId) ? 'var(--accent-muted)' : 'transparent'
                }}
              >
                <Paperclip size={12} style={{ color: (selectedIndexId || selectedDatasetId) ? 'var(--accent-primary)' : 'var(--text-muted)' }} />
                <span className="max-w-[120px] truncate">
                  {selectedIndexId 
                    ? `Index: ${indexes.find(i => i.id === selectedIndexId)?.name || 'Selected'}`
                    : selectedDatasetId
                      ? `File: ${datasets.find(d => d.id === selectedDatasetId)?.name || 'Selected'}`
                      : 'Add Context'}
                </span>
                <ChevronDown size={12} />
              </button>
              <AnimatePresence>
                {contextMenuOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 4 }}
                    className="absolute right-0 top-full mt-1 w-64 rounded-lg overflow-hidden z-50 p-1"
                    style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
                  >
                    <div className="text-[10px] font-bold px-2 py-1 text-slate-400 uppercase tracking-wider">
                      Grounding Context
                    </div>
                    
                    <button
                      onClick={() => {
                        setSelectedIndexId(null)
                        setSelectedDatasetId(null)
                        setDatasetMode('dataset_llm')
                        setContextMenuOpen(false)
                      }}
                      className="w-full text-left px-3.5 py-1.5 text-xs rounded transition-colors flex items-center justify-between"
                      style={{
                        color: (!selectedIndexId && !selectedDatasetId) ? 'var(--accent-primary)' : 'var(--text-secondary)',
                        background: (!selectedIndexId && !selectedDatasetId) ? 'var(--accent-muted)' : 'transparent'
                      }}
                      onMouseEnter={(e) => { if (selectedIndexId || selectedDatasetId) e.currentTarget.style.background = 'var(--bg-tertiary)' }}
                      onMouseLeave={(e) => { if (selectedIndexId || selectedDatasetId) e.currentTarget.style.background = 'transparent' }}
                    >
                      No Context (Default Chat)
                    </button>

                    {indexes.length > 0 && (
                      <>
                        <div className="border-t border-slate-700/50 my-1"></div>
                        <div className="text-[10px] font-bold px-2 py-1 text-indigo-400 uppercase tracking-wider">
                          Vector Indexes (RAG)
                        </div>
                        {indexes.map((idx) => (
                          <button
                            key={idx.id}
                            onClick={() => {
                              setSelectedIndexId(idx.id)
                              setSelectedDatasetId(null)
                              setContextMenuOpen(false)
                            }}
                            className="w-full text-left px-3.5 py-1.5 text-xs rounded transition-colors truncate"
                            style={{
                              color: selectedIndexId === idx.id ? 'var(--accent-primary)' : 'var(--text-secondary)',
                              background: selectedIndexId === idx.id ? 'var(--accent-muted)' : 'transparent'
                            }}
                            onMouseEnter={(e) => { if (selectedIndexId !== idx.id) e.currentTarget.style.background = 'var(--bg-tertiary)' }}
                            onMouseLeave={(e) => { if (selectedIndexId !== idx.id) e.currentTarget.style.background = 'transparent' }}
                          >
                            KB: {idx.name} ({idx.chunk_count} chunks)
                          </button>
                        ))}
                      </>
                    )}

                    {datasets.length > 0 && (
                      <>
                        <div className="border-t border-slate-700/50 my-1"></div>
                        <div className="text-[10px] font-bold px-2 py-1 text-emerald-400 uppercase tracking-wider">
                          Uploaded Datasets (File)
                        </div>
                        {datasets.map((ds) => (
                          <button
                            key={ds.id}
                            onClick={() => {
                              setSelectedDatasetId(ds.id)
                              setSelectedIndexId(null)
                              setContextMenuOpen(false)
                            }}
                            className="w-full text-left px-3.5 py-1.5 text-xs rounded transition-colors truncate"
                            style={{
                              color: selectedDatasetId === ds.id ? 'var(--accent-primary)' : 'var(--text-secondary)',
                              background: selectedDatasetId === ds.id ? 'var(--accent-muted)' : 'transparent'
                            }}
                            onMouseEnter={(e) => { if (selectedDatasetId !== ds.id) e.currentTarget.style.background = 'var(--bg-tertiary)' }}
                            onMouseLeave={(e) => { if (selectedDatasetId !== ds.id) e.currentTarget.style.background = 'transparent' }}
                          >
                            File: {ds.name}
                          </button>
                        ))}
                      </>
                    )}
                    
                    {indexes.length === 0 && datasets.length === 0 && (
                      <div className="text-[11px] text-slate-500 italic px-3 py-2 text-center">
                        No datasets or vector indexes available.
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Dataset-Only RAG Mode Badge */}
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider shadow-sm"
              style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-primary)', color: 'var(--accent-primary)' }}>
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--accent-primary)' }} />
              Dataset-Only RAG
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {currentMessages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center gap-3">
              <div className="w-12 h-12 rounded-2xl flex items-center justify-center"
                style={{ background: 'var(--accent-muted)' }}>
                <Bot size={22} style={{ color: 'var(--accent-primary)' }} />
              </div>
              <p className="font-semibold" style={{ color: 'var(--text-primary)' }}>Dataset-Only RAG Search</p>
              <p className="text-sm max-w-xs" style={{ color: 'var(--text-muted)' }}>
                Please select a dataset file from the <strong>Add Context</strong> dropdown above to begin searching and chatting.
              </p>
            </div>
          ) : (
            currentMessages.map((msg) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
              >
                <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${msg.role === 'user' ? '' : ''}`}
                  style={{
                    background: msg.role === 'user' ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
                    border: '1px solid var(--border)'
                  }}>
                  {msg.role === 'user'
                    ? <User size={13} className="text-white" />
                    : <Bot size={13} style={{ color: 'var(--accent-primary)' }} />}
                </div>
                <div className={msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai'}>
                  {msg.role === 'assistant' ? (
                    <ReactMarkdown
                      className="text-sm prose-invert prose-sm max-w-none"
                      components={{
                        code({ children }) {
                          return <code className="code-block inline px-1 py-0.5 text-xs">{children}</code>
                        },
                        pre({ children }) {
                          return <pre className="code-block my-2 text-xs overflow-x-auto">{children}</pre>
                        },
                      }}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  ) : (
                    <p className="text-sm text-white">{msg.content}</p>
                  )}
                  {isStreaming && msg === currentMessages[currentMessages.length - 1] && msg.role === 'assistant' && (
                    <span className="inline-flex gap-1 mt-1">
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                    </span>
                  )}
                </div>
              </motion.div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Active Context Banner */}
        {(selectedIndexId || selectedDatasetId) && (
          <div className="px-4 py-2 flex items-center justify-between text-xs transition-all"
            style={{ background: 'var(--bg-secondary)', borderTop: '1px solid var(--border)' }}>
            <div className="flex items-center gap-1.5 text-slate-400">
              <span className="w-1.5 h-1.5 rounded-full animate-pulse"
                style={{ background: selectedIndexId ? '#6366f1' : '#10b981' }} />
              <span>
                Using grounding context from{' '}
                <strong style={{ color: 'var(--text-primary)' }}>
                  {selectedIndexId
                    ? `RAG Index: ${indexes.find(i => i.id === selectedIndexId)?.name}`
                    : `Dataset: ${datasets.find(d => d.id === selectedDatasetId)?.name}`}
                </strong>
              </span>
            </div>
            <button
              onClick={() => {
                setSelectedIndexId(null)
                setSelectedDatasetId(null)
                setDatasetMode('dataset_llm')
              }}
              className="text-slate-500 hover:text-slate-300 p-0.5 rounded-full hover:bg-slate-700/30 transition-colors"
            >
              <X size={12} />
            </button>
          </div>
        )}

        {/* Input */}
        <div className="p-4 flex-shrink-0" style={{ borderTop: '1px solid var(--border)' }}>
          <div className="flex gap-2 items-end">
            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Message AI Studio..."
                rows={1}
                className="input-base resize-none pr-10 min-h-[42px] max-h-32 overflow-y-auto"
                style={{ lineHeight: '1.5' }}
                onInput={(e) => {
                  e.target.style.height = 'auto'
                  e.target.style.height = Math.min(e.target.scrollHeight, 128) + 'px'
                }}
              />
            </div>
            <button
              onClick={isStreaming ? () => setStreaming(false) : sendMessage}
              disabled={!input.trim() && !isStreaming}
              className="btn-primary py-2.5 px-3 flex-shrink-0"
              style={{ opacity: (!input.trim() && !isStreaming) ? 0.5 : 1 }}
            >
              {isStreaming ? <Square size={14} /> : <Send size={14} />}
            </button>
          </div>
          <p className="text-center text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </div>
    </div>
  )
}
