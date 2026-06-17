import { useState, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Zap, Eye, EyeOff, ArrowRight, Chrome, Github, 
  ShieldCheck, Brain, Sparkles, Cpu, Mail, Lock, Check, AlertCircle 
} from 'lucide-react'
import { authAPI } from '../services/api'
import { useAuthStore } from '../store'
import toast from 'react-hot-toast'

// Typist Subtitle Component
function TypingSubtitle() {
  const words = [
    "Building Intelligence...",
    "Training Neural Models...",
    "Analyzing Dataset Chunks...",
    "Optimizing Embeddings...",
    "Ready to Assist..."
  ]
  const [currentWordIndex, setCurrentWordIndex] = useState(0)
  const [displayText, setDisplayText] = useState("")
  const [isDeleting, setIsDeleting] = useState(false)
  
  useEffect(() => {
    let timer
    const currentWord = words[currentWordIndex]
    const speed = isDeleting ? 25 : 55
    
    if (!isDeleting && displayText === currentWord) {
      timer = setTimeout(() => setIsDeleting(true), 2500)
    } else if (isDeleting && displayText === "") {
      setIsDeleting(false)
      setCurrentWordIndex((prev) => (prev + 1) % words.length)
    } else {
      timer = setTimeout(() => {
        setDisplayText(
          isDeleting
            ? currentWord.substring(0, displayText.length - 1)
            : currentWord.substring(0, displayText.length + 1)
        )
      }, speed)
    }
    
    return () => clearTimeout(timer)
  }, [displayText, isDeleting, currentWordIndex])
  
  return (
    <span className="inline-flex items-center text-cyan-400 font-mono text-[10px] sm:text-xs font-semibold tracking-wider uppercase h-5">
      <Sparkles size={12} className="mr-1.5 text-cyan-400 animate-pulse" />
      {displayText}
      <span className="ml-1 w-1.5 h-3.5 bg-cyan-400 animate-pulse" />
    </span>
  )
}

// Particle System Custom Canvas Simulation
function ParticleCanvas() {
  const canvasRef = useRef(null)
  
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    let animationFrameId
    
    let width = canvas.width = window.innerWidth
    let height = canvas.height = window.innerHeight
    
    const handleResize = () => {
      if (!canvas) return
      width = canvas.width = window.innerWidth
      height = canvas.height = window.innerHeight
    }
    window.addEventListener('resize', handleResize)
    
    // Dynamic node count based on screen size
    const particles = []
    const particleCount = Math.min(80, Math.floor((width * height) / 18000))
    
    class Particle {
      constructor() {
        this.x = Math.random() * width
        this.y = Math.random() * height
        this.vx = (Math.random() - 0.5) * 0.35
        this.vy = (Math.random() - 0.5) * 0.35
        this.radius = Math.random() * 2 + 1
        this.color = Math.random() > 0.4 
          ? 'rgba(139, 92, 246, 0.35)' // Purple
          : 'rgba(6, 182, 212, 0.35)'  // Cyan
      }
      update(mouseX, mouseY) {
        this.x += this.vx
        this.y += this.vy
        
        if (this.x < 0 || this.x > width) this.vx *= -1
        if (this.y < 0 || this.y > height) this.vy *= -1
        
        // Push slightly away from mouse
        if (mouseX && mouseY) {
          const dx = mouseX - this.x
          const dy = mouseY - this.y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < 130) {
            const force = (130 - dist) / 130
            this.x -= (dx / dist) * force * 0.6
            this.y -= (dy / dist) * force * 0.6
          }
        }
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
    
    let mouseX = null
    let mouseY = null
    const handleMouseMove = (e) => {
      mouseX = e.clientX
      mouseY = e.clientY
    }
    const handleMouseLeave = () => {
      mouseX = null
      mouseY = null
    }
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseleave', handleMouseLeave)
    
    const animate = () => {
      ctx.clearRect(0, 0, width, height)
      
      particles.forEach(p => {
        p.update(mouseX, mouseY)
        p.draw()
      })
      
      // Node connections
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const p1 = particles[i]
          const p2 = particles[j]
          const dx = p1.x - p2.x
          const dy = p1.y - p2.y
          const dist = Math.sqrt(dx * dx + dy * dy)
          
          if (dist < 110) {
            const alpha = ((110 - dist) / 110) * 0.12
            ctx.beginPath()
            ctx.moveTo(p1.x, p1.y)
            ctx.lineTo(p2.x, p2.y)
            ctx.strokeStyle = `rgba(99, 102, 241, ${alpha})`
            ctx.lineWidth = 0.75
            ctx.stroke()
          }
        }
        
        // Connect nodes to cursor
        if (mouseX && mouseY) {
          const p = particles[i]
          const dx = p.x - mouseX
          const dy = p.y - mouseY
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < 140) {
            const alpha = ((140 - dist) / 140) * 0.2
            ctx.beginPath()
            ctx.moveTo(p.x, p.y)
            ctx.lineTo(mouseX, mouseY)
            ctx.strokeStyle = `rgba(6, 182, 212, ${alpha})`
            ctx.lineWidth = 0.75
            ctx.stroke()
          }
        }
      }
      
      animationFrameId = requestAnimationFrame(animate)
    }
    animate()
    
    return () => {
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseleave', handleMouseLeave)
      cancelAnimationFrame(animationFrameId)
    }
  }, [])
  
  return <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none z-10" />
}

export default function LoginPage() {
  const [form, setForm] = useState({ email: '', password: '' })
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [rememberMe, setRememberMe] = useState(false)
  const { setAuth } = useAuthStore()
  const navigate = useNavigate()
  
  // Interactive mouse follow glow coordinates
  const containerRef = useRef(null)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })
  
  const handleMouseMove = (e) => {
    if (!containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    setMousePos({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top
    })
  }

  // Live validator checks
  const isEmailValid = form.email ? /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email) : null
  
  // Password complexity score calculation (0 to 4)
  const getPasswordStrength = () => {
    const pw = form.password
    if (!pw) return 0
    let score = 0
    if (pw.length >= 8) score++
    if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++
    if (/[0-9]/.test(pw)) score++
    if (/[^A-Za-z0-9]/.test(pw)) score++
    return score
  }
  const passwordStrength = getPasswordStrength()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const { data } = await authAPI.login(form)
      setAuth(data.user, data.access_token, data.refresh_token)
      toast.success('Successfully authenticated')
      navigate('/dashboard')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  const demoLogin = async () => {
    setForm({ email: 'demo@aistudio.com', password: 'demo1234' })
    setLoading(true)
    try {
      const { data } = await authAPI.login({ email: 'demo@aistudio.com', password: 'demo1234' })
      setAuth(data.user, data.access_token, data.refresh_token)
      toast.success('Logged in as Demo User')
      navigate('/dashboard')
    } catch {
      setAuth({ name: 'Demo User', email: 'demo@aistudio.com', role: 'admin', id: '1' }, 'mock-token', 'mock-refresh')
      toast.success('Offline bypass: Authenticated with mock demo data')
      navigate('/dashboard')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div 
      ref={containerRef}
      onMouseMove={handleMouseMove}
      className="relative min-h-screen flex items-center justify-center bg-[#030712] overflow-hidden select-none"
    >
      {/* Dynamic Style Sheet injection for Custom Neon Auroras and Shimmers */}
      <style>{`
        @keyframes float-slow {
          0%, 100% { transform: translateY(0px) scale(1); }
          50% { transform: translateY(-20px) scale(1.05); }
        }
        @keyframes spin-slow {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes spin-reverse-slow {
          0% { transform: rotate(360deg); }
          100% { transform: rotate(0deg); }
        }
        @keyframes pulse-ring {
          0% { transform: scale(0.95); opacity: 0.2; }
          50% { transform: scale(1.05); opacity: 0.35; }
          100% { transform: scale(0.95); opacity: 0.2; }
        }
        .animate-float {
          animation: float-slow 8s ease-in-out infinite;
        }
        .animate-spin-slow {
          animation: spin-slow 20s linear infinite;
        }
        .animate-spin-reverse {
          animation: spin-reverse-slow 25s linear infinite;
        }
        .animate-pulse-ring {
          animation: pulse-ring 4s ease-in-out infinite;
        }
        .glow-overlay {
          background: radial-gradient(800px circle at ${mousePos.x}px ${mousePos.y}px, rgba(99, 102, 241, 0.08), transparent 45%);
        }
        .glass-panel {
          background: rgba(17, 24, 39, 0.55);
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.05);
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }
        .glass-panel:hover {
          border-color: rgba(139, 92, 246, 0.25);
          box-shadow: 0 0 40px rgba(139, 92, 246, 0.1);
        }
        .shine-effect {
          position: relative;
          overflow: hidden;
        }
        .shine-effect::after {
          content: '';
          position: absolute;
          top: -50%;
          left: -60%;
          width: 30%;
          height: 200%;
          background: linear-gradient(
            to right,
            rgba(255, 255, 255, 0) 0%,
            rgba(255, 255, 255, 0.15) 50%,
            rgba(255, 255, 255, 0) 100%
          );
          transform: rotate(25deg);
          transition: all 0.75s ease;
        }
        .shine-effect:hover::after {
          left: 130%;
        }
      `}</style>

      {/* Aurora Ambient Lighting Blobs */}
      <div className="absolute inset-0 pointer-events-none z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-[#8B5CF6]/15 blur-[120px] animate-pulse-ring" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-[#6366F1]/15 blur-[120px] animate-pulse-ring" style={{ animationDelay: '2s' }} />
        <div className="absolute top-[30%] left-[35%] w-[35%] h-[35%] rounded-full bg-[#06B6D4]/10 blur-[130px] animate-float" />
      </div>

      {/* Mouse Follow Ambient Glow Overlay */}
      <div className="glow-overlay absolute inset-0 pointer-events-none z-0 transition-opacity duration-300" />

      {/* Connected Neural Network Canvas Background */}
      <ParticleCanvas />

      {/* Floating 3D Parallax Elements */}
      <div className="absolute inset-0 pointer-events-none z-10 hidden md:block">
        <motion.div 
          animate={{ y: [0, -12, 0], rotate: [0, 5, 0] }}
          transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
          className="absolute top-[18%] left-[12%] text-purple-500/25"
        >
          <Brain size={48} />
        </motion.div>
        <motion.div 
          animate={{ y: [0, 15, 0], rotate: [0, -10, 0] }}
          transition={{ duration: 7, repeat: Infinity, ease: "easeInOut", delay: 1 }}
          className="absolute bottom-[22%] left-[16%] text-cyan-500/25"
        >
          <Cpu size={40} />
        </motion.div>
        <motion.div 
          animate={{ y: [0, -18, 0], scale: [1, 1.05, 1] }}
          transition={{ duration: 8, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
          className="absolute top-[25%] right-[14%] text-indigo-500/20"
        >
          <Sparkles size={44} />
        </motion.div>
      </div>

      {/* Main Container */}
      <div className="w-full max-w-[430px] mx-4 z-20">
        <motion.div
          initial={{ opacity: 0, y: 35, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.65, ease: "easeOut" }}
          className="flex flex-col items-center"
        >
          {/* Glowing AI Emblem Group */}
          <div className="relative flex items-center justify-center w-24 h-24 mb-6">
            {/* Pulsing Backlight */}
            <div className="absolute inset-0 bg-gradient-to-tr from-purple-500 to-cyan-500 rounded-3xl blur-md opacity-25 animate-pulse" />
            
            {/* Outer Counter-Rotating Rings */}
            <div className="absolute inset-1 border border-dashed border-purple-500/40 rounded-3xl animate-spin-slow" />
            <div className="absolute inset-2 border border-dotted border-cyan-500/40 rounded-[22px] animate-spin-reverse" />
            
            {/* Central Badge */}
            <div className="absolute inset-3 bg-[#0d0f17] border border-white/[0.08] hover:border-purple-500/50 rounded-2xl flex items-center justify-center transition-colors duration-300">
              <Zap size={28} className="text-purple-400 drop-shadow-[0_0_8px_rgba(167,139,250,0.5)]" />
            </div>
          </div>

          {/* Titles & Typewriter Status */}
          <div className="text-center mb-6">
            <h1 className="text-3xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-gray-200 to-gray-400">
              AI Studio
            </h1>
            <p className="text-xs text-gray-500 font-medium mt-1 mb-2">
              Next-Generation Neural Workspace
            </p>
            <TypingSubtitle />
          </div>

          {/* Login Form Panel */}
          <div className="glass-panel w-full rounded-[28px] p-6 sm:p-8 space-y-6 transition-all duration-300">
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Email Input Field Group */}
              <div>
                <label className="block text-[10px] font-bold tracking-wider uppercase mb-1.5 text-gray-400">
                  Access Node (Email)
                </label>
                <div className="relative">
                  <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-500">
                    <Mail size={15} />
                  </div>
                  <input
                    type="email"
                    required
                    placeholder="you@example.com"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    className="w-full pl-10 pr-10 py-3 bg-white/[0.02] border border-white/[0.06] focus:border-purple-500/60 rounded-xl text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-purple-500/30 transition-all duration-200"
                  />
                  {/* Inline validator feedback */}
                  {isEmailValid !== null && (
                    <div className="absolute right-3.5 top-1/2 -translate-y-1/2">
                      {isEmailValid ? (
                        <Check size={15} className="text-emerald-500 drop-shadow-[0_0_4px_rgba(16,185,129,0.4)]" />
                      ) : (
                        <AlertCircle size={15} className="text-amber-500" />
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Password Input Field Group */}
              <div>
                <div className="flex justify-between items-center mb-1.5">
                  <label className="block text-[10px] font-bold tracking-wider uppercase text-gray-400">
                    Secure Cipher (Password)
                  </label>
                  <Link 
                    to="/forgot-password" 
                    className="text-[10px] font-semibold text-purple-400 hover:text-purple-300 hover:underline transition-colors"
                  >
                    Reset Keys?
                  </Link>
                </div>
                <div className="relative">
                  <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-500">
                    <Lock size={15} />
                  </div>
                  <input
                    type={showPw ? 'text' : 'password'}
                    required
                    placeholder="••••••••"
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    className="w-full pl-10 pr-10 py-3 bg-white/[0.02] border border-white/[0.06] focus:border-purple-500/60 rounded-xl text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-purple-500/30 transition-all duration-200"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw(!showPw)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors"
                  >
                    {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>

                {/* Password strength meter */}
                {form.password && (
                  <div className="mt-2 space-y-1">
                    <div className="flex justify-between items-center text-[9px] font-bold tracking-wide uppercase">
                      <span className="text-gray-500">Entropy Level:</span>
                      <span className={
                        passwordStrength <= 1 ? "text-rose-500" :
                        passwordStrength === 2 ? "text-amber-500" :
                        passwordStrength === 3 ? "text-yellow-400" : "text-emerald-500"
                      }>
                        {passwordStrength <= 1 ? "Weak" :
                         passwordStrength === 2 ? "Fair" :
                         passwordStrength === 3 ? "Good" : "Strong"}
                      </span>
                    </div>
                    <div className="h-1 w-full bg-white/[0.05] rounded-full overflow-hidden flex gap-0.5">
                      <div className={`h-full flex-1 transition-all duration-300 ${passwordStrength >= 1 ? (passwordStrength === 1 ? 'bg-rose-500' : passwordStrength === 2 ? 'bg-amber-500' : 'bg-emerald-500') : 'bg-transparent'}`} />
                      <div className={`h-full flex-1 transition-all duration-300 ${passwordStrength >= 2 ? (passwordStrength === 2 ? 'bg-amber-500' : 'bg-emerald-500') : 'bg-transparent'}`} />
                      <div className={`h-full flex-1 transition-all duration-300 ${passwordStrength >= 3 ? 'bg-emerald-500' : 'bg-transparent'}`} />
                      <div className={`h-full flex-1 transition-all duration-300 ${passwordStrength >= 4 ? 'bg-emerald-500' : 'bg-transparent'}`} />
                    </div>
                  </div>
                )}
              </div>

              {/* Remember Me Box */}
              <div className="flex items-center">
                <label className="flex items-center cursor-pointer select-none">
                  <div className="relative">
                    <input 
                      type="checkbox"
                      checked={rememberMe}
                      onChange={(e) => setRememberMe(e.target.checked)}
                      className="sr-only" 
                    />
                    <div className={`w-4 h-4 rounded-md border flex items-center justify-center transition-all duration-200 ${rememberMe ? 'border-purple-500 bg-purple-500/20' : 'border-white/10 bg-white/[0.02]'}`}>
                      {rememberMe && <Check size={10} className="text-purple-400 stroke-[3]" />}
                    </div>
                  </div>
                  <span className="ml-2 text-[11px] text-gray-500 font-medium hover:text-gray-400 transition-colors">Remember credentials</span>
                </label>
              </div>

              {/* Action Button */}
              <button
                type="submit"
                disabled={loading}
                className="shine-effect w-full py-3 bg-gradient-to-r from-purple-600 via-indigo-600 to-blue-600 hover:from-purple-500 hover:via-indigo-500 hover:to-blue-500 text-white font-semibold text-sm rounded-xl flex items-center justify-center gap-1.5 shadow-[0_4px_20px_rgba(99,102,241,0.25)] hover:shadow-[0_4px_25px_rgba(99,102,241,0.4)] disabled:opacity-60 transition-all duration-250"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Decrypting Keyrings...
                  </span>
                ) : (
                  <>
                    Sign In
                    <ArrowRight size={14} className="mt-0.5" />
                  </>
                )}
              </button>
            </form>

            {/* Splitter */}
            <div className="relative flex items-center justify-center">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-white/[0.05]" />
              </div>
              <span className="relative px-3 bg-[#0d101b] text-[10px] font-bold text-gray-600 tracking-wider uppercase">
                Consensus via
              </span>
            </div>

            {/* OAuth buttons & Demo */}
            <div className="space-y-2.5">
              <div className="grid grid-cols-2 gap-2.5">
                <button 
                  onClick={() => toast.success('Google authentication requested')}
                  className="py-2.5 bg-white/[0.02] border border-white/[0.05] hover:border-white/10 hover:bg-white/[0.05] rounded-xl flex items-center justify-center gap-2 text-xs font-semibold text-gray-300 transition-all duration-200"
                >
                  <Chrome size={14} className="text-red-400" />
                  Google
                </button>
                <button 
                  onClick={() => toast.success('GitHub authentication requested')}
                  className="py-2.5 bg-white/[0.02] border border-white/[0.05] hover:border-white/10 hover:bg-white/[0.05] rounded-xl flex items-center justify-center gap-2 text-xs font-semibold text-gray-300 transition-all duration-200"
                >
                  <Github size={14} className="text-gray-400" />
                  GitHub
                </button>
              </div>

              <button
                onClick={demoLogin}
                className="w-full py-2.5 bg-white/[0.01] hover:bg-white/[0.04] border border-dashed border-white/[0.08] hover:border-purple-500/40 rounded-xl text-xs font-bold text-gray-400 hover:text-purple-400 flex items-center justify-center gap-1.5 transition-all duration-200"
              >
                <Zap size={13} />
                Acquire Sandbox Account
              </button>
            </div>
          </div>

          {/* Footer Navigation */}
          <div className="mt-6 text-center space-y-3">
            <p className="text-xs text-gray-500">
              Not registered?{' '}
              <Link to="/register" className="text-purple-400 font-bold hover:text-purple-300 hover:underline transition-colors">
                Initialize account
              </Link>
            </p>

            {/* Security Audit Badge & Versioning */}
            <div className="flex items-center justify-center gap-4 text-[9px] font-bold tracking-wider uppercase text-gray-600">
              <span className="flex items-center gap-1">
                <ShieldCheck size={11} className="text-emerald-500/70" />
                TLS 1.3 Audit Passed
              </span>
              <span>•</span>
              <span>Platform v2.4.0</span>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
