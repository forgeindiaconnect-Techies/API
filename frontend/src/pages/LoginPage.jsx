import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Zap, Eye, EyeOff, ArrowRight } from 'lucide-react'
import { authAPI } from '../services/api'
import { useAuthStore } from '../store'
import toast from 'react-hot-toast'

export default function LoginPage() {
  const [form, setForm] = useState({ email: '', password: '' })
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const { setAuth } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const { data } = await authAPI.login(form)
      setAuth(data.user, data.access_token, data.refresh_token)
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
      navigate('/dashboard')
    } catch {
      // Use mock data for demo
      setAuth({ name: 'Demo User', email: 'demo@aistudio.com', role: 'admin', id: '1' }, 'mock-token', 'mock-refresh')
      navigate('/dashboard')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center hero-gradient">
      <div className="w-full max-w-sm mx-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl mb-4"
              style={{ background: 'var(--accent-primary)' }}>
              <Zap size={22} className="text-white" />
            </div>
            <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
              Welcome back
            </h1>
            <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
              Sign in to your AI Studio
            </p>
          </div>

          {/* Card */}
          <div className="card-elevated p-6 space-y-4">
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                  Email
                </label>
                <input
                  type="email"
                  className="input-base"
                  placeholder="you@example.com"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                  Password
                </label>
                <div className="relative">
                  <input
                    type={showPw ? 'text' : 'password'}
                    className="input-base pr-10"
                    placeholder="••••••••"
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw(!showPw)}
                    className="absolute right-3 top-1/2 -translate-y-1/2"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="btn-primary w-full justify-center"
                style={{ opacity: loading ? 0.7 : 1 }}
              >
                {loading ? 'Signing in...' : 'Sign In'}
                <ArrowRight size={14} />
              </button>
            </form>

            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full" style={{ borderTop: '1px solid var(--border)' }} />
              </div>
              <div className="relative text-center">
                <span className="px-3 text-xs" style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}>
                  or
                </span>
              </div>
            </div>

            <button
              onClick={demoLogin}
              className="btn-ghost w-full justify-center"
            >
              Try Demo Account
            </button>
          </div>

          <p className="text-center text-sm mt-4" style={{ color: 'var(--text-muted)' }}>
            Don't have an account?{' '}
            <Link to="/register" style={{ color: 'var(--accent-primary)' }} className="font-semibold hover:underline">
              Sign up
            </Link>
          </p>
        </motion.div>
      </div>
    </div>
  )
}
