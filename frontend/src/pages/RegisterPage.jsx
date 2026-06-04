import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Zap, ArrowRight } from 'lucide-react'
import { authAPI } from '../services/api'
import { useAuthStore } from '../store'
import toast from 'react-hot-toast'

export default function RegisterPage() {
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '' })
  const [loading, setLoading] = useState(false)
  const { setAuth } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (form.password !== form.confirm) {
      toast.error('Passwords do not match')
      return
    }
    setLoading(true)
    try {
      const { data } = await authAPI.register({
        name: form.name, email: form.email, password: form.password
      })
      setAuth(data.user, data.access_token, data.refresh_token)
      navigate('/dashboard')
      toast.success('Account created!')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  const fields = [
    { key: 'name', label: 'Full Name', type: 'text', placeholder: 'John Doe' },
    { key: 'email', label: 'Email', type: 'email', placeholder: 'you@example.com' },
    { key: 'password', label: 'Password', type: 'password', placeholder: '••••••••' },
    { key: 'confirm', label: 'Confirm Password', type: 'password', placeholder: '••••••••' },
  ]

  return (
    <div className="min-h-screen flex items-center justify-center hero-gradient">
      <div className="w-full max-w-sm mx-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl mb-4"
              style={{ background: 'var(--accent-primary)' }}>
              <Zap size={22} className="text-white" />
            </div>
            <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
              Create account
            </h1>
            <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
              Get started with Personal AI Studio
            </p>
          </div>

          <div className="card-elevated p-6 space-y-4">
            <form onSubmit={handleSubmit} className="space-y-4">
              {fields.map(({ key, label, type, placeholder }) => (
                <div key={key}>
                  <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>
                    {label}
                  </label>
                  <input
                    type={type}
                    className="input-base"
                    placeholder={placeholder}
                    value={form[key]}
                    onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                    required
                  />
                </div>
              ))}

              <button
                type="submit"
                disabled={loading}
                className="btn-primary w-full justify-center"
                style={{ opacity: loading ? 0.7 : 1 }}
              >
                {loading ? 'Creating...' : 'Create Account'}
                <ArrowRight size={14} />
              </button>
            </form>
          </div>

          <p className="text-center text-sm mt-4" style={{ color: 'var(--text-muted)' }}>
            Already have an account?{' '}
            <Link to="/login" style={{ color: 'var(--accent-primary)' }} className="font-semibold hover:underline">
              Sign in
            </Link>
          </p>
        </motion.div>
      </div>
    </div>
  )
}
