import { useState, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Plus, Trash2, Bot, User, Copy, RefreshCw,
  ChevronDown, Paperclip, Mic, Square
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { useChatStore } from '../store'
import { chatAPI } from '../services/api'
import toast from 'react-hot-toast'

const MODELS = [
  { id: 'llama3', label: 'Llama 3 8B' },
  { id: 'llama3:70b', label: 'Llama 3 70B' },
  { id: 'mistral', label: 'Mistral 7B' },
  { id: 'deepseek', label: 'DeepSeek' },
]

const mockConversations = [
  { id: '1', title: 'Data analysis helper', created_at: new Date() },
  { id: '2', title: 'Python code review', created_at: new Date() },
  { id: '3', title: 'ML model questions', created_at: new Date() },
]

const mockMessages = {
  '1': [
    { id: 'm1', role: 'user', content: 'Can you help me analyze my sales dataset?' },
    { id: 'm2', role: 'assistant', content: 'Of course! I can help you analyze your sales dataset. Could you share the dataset or describe its structure? I can help with:\n\n- **Exploratory Data Analysis (EDA)** — distributions, trends, outliers\n- **Statistical summaries** — mean, median, variance\n- **Visualizations** — charts and graphs\n- **Predictive modeling** — forecasting future sales\n\nWhat would you like to focus on?' },
  ],
}

export default function ChatPage() {
  const { id: urlId } = useParams()
  const navigate = useNavigate()
  const {
    conversations, activeConversationId, messages, isStreaming,
    selectedModel, setActiveConversation, addConversation,
    setMessages, addMessage, appendToLastMessage, setStreaming, setModel
  } = useChatStore()

  const [input, setInput] = useState('')
  const [modelMenuOpen, setModelMenuOpen] = useState(false)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  // Initialize with mock data
  useEffect(() => {
    if (conversations.length === 0) {
      mockConversations.forEach(c => addConversation(c))
      Object.entries(mockMessages).forEach(([id, msgs]) => setMessages(id, msgs))
      setActiveConversation('1')
    }
  }, [])

  useEffect(() => {
    if (urlId) setActiveConversation(urlId)
    else if (conversations.length > 0) setActiveConversation(conversations[0]?.id)
  }, [urlId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, activeConversationId])

  const currentMessages = messages[activeConversationId] || []

  const sendMessage = async () => {
    if (!input.trim() || isStreaming) return
    const text = input.trim()
    setInput('')

    const userMsg = { id: Date.now().toString(), role: 'user', content: text }
    addMessage(activeConversationId, userMsg)

    const aiMsg = { id: (Date.now() + 1).toString(), role: 'assistant', content: '' }
    addMessage(activeConversationId, aiMsg)
    setStreaming(true)

    // Simulate streaming response
    const response = simulateAIResponse(text)
    let i = 0
    const interval = setInterval(() => {
      if (i < response.length) {
        appendToLastMessage(activeConversationId, response[i])
        i++
      } else {
        clearInterval(interval)
        setStreaming(false)
      }
    }, 15)
  }

  const simulateAIResponse = (prompt) => {
    const responses = [
      `That's a great question! Let me think through this carefully.\n\n**Here's my analysis:**\n\nBased on your input, I can provide several insights:\n\n1. **Key consideration**: The context you've provided gives me a good foundation\n2. **Approach**: I'll break this down systematically\n3. **Recommendation**: Start with the fundamentals\n\nWould you like me to go deeper on any particular aspect?`,
      `I understand what you're looking for. Here's a comprehensive breakdown:\n\n\`\`\`python\n# Example code\ndef analyze_data(df):\n    summary = df.describe()\n    return summary\n\`\`\`\n\nThis approach handles the most common cases and scales well.`,
      `Excellent point! Let me elaborate on that...\n\nThe key factors to consider are:\n- **Performance**: Optimized for speed and accuracy\n- **Scalability**: Handles large datasets efficiently  \n- **Interpretability**: Results are easy to understand\n\nI hope this helps clarify things!`,
    ]
    return responses[Math.floor(Math.random() * responses.length)]
  }

  const newChat = () => {
    const id = Date.now().toString()
    addConversation({ id, title: 'New conversation', created_at: new Date() })
    setActiveConversation(id)
    navigate(`/chat/${id}`)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="flex h-full">
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
            <button
              key={conv.id}
              onClick={() => { setActiveConversation(conv.id); navigate(`/chat/${conv.id}`) }}
              className={`w-full text-left px-3 py-2.5 rounded-lg text-xs transition-colors truncate ${activeConversationId === conv.id ? 'active-conv' : ''}`}
              style={{
                background: activeConversationId === conv.id ? 'var(--accent-muted)' : 'transparent',
                color: activeConversationId === conv.id ? 'var(--accent-primary)' : 'var(--text-secondary)',
              }}
            >
              {conv.title}
            </button>
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

          {/* Model selector */}
          <div className="relative">
            <button
              onClick={() => setModelMenuOpen(!modelMenuOpen)}
              className="btn-ghost py-1.5 text-xs"
            >
              {MODELS.find(m => m.id === selectedModel)?.label || 'Llama 3'}
              <ChevronDown size={12} />
            </button>
            <AnimatePresence>
              {modelMenuOpen && (
                <motion.div
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 4 }}
                  className="absolute right-0 top-full mt-1 w-40 rounded-lg overflow-hidden z-50"
                  style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
                >
                  {MODELS.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => { setModel(m.id); setModelMenuOpen(false) }}
                      className="w-full text-left px-3 py-2 text-xs transition-colors"
                      style={{
                        color: selectedModel === m.id ? 'var(--accent-primary)' : 'var(--text-secondary)',
                        background: selectedModel === m.id ? 'var(--accent-muted)' : 'transparent'
                      }}
                      onMouseEnter={(e) => { if (selectedModel !== m.id) e.currentTarget.style.background = 'var(--bg-tertiary)' }}
                      onMouseLeave={(e) => { if (selectedModel !== m.id) e.currentTarget.style.background = 'transparent' }}
                    >
                      {m.label}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
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
              <p className="font-semibold" style={{ color: 'var(--text-primary)' }}>Start a conversation</p>
              <p className="text-sm max-w-xs" style={{ color: 'var(--text-muted)' }}>
                Ask anything — I can help with data analysis, code, questions, and more.
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
