import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuthStore, useUIStore } from '../../store'
import {
  LayoutDashboard, MessageSquare, Database, Brain, Cpu,
  Search, Key, BarChart3, Settings, Layers,
  ChevronLeft, ChevronRight, Bell, Sun, Moon, LogOut, User,
  Zap, Menu, X, ShieldAlert, Sparkles, ChevronDown
} from 'lucide-react'
import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'

const navItems = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/dashboard' },
  { icon: MessageSquare, label: 'AI Chat', path: '/chat' },
  { icon: Database, label: 'Datasets', path: '/datasets' },
  { icon: Brain, label: 'Models', path: '/models' },
  { icon: Cpu, label: 'Training', path: '/training' },
  { icon: Search, label: 'RAG Search', path: '/rag' },
  { icon: Key, label: 'API Keys', path: '/api-keys' },
  { icon: BarChart3, label: 'Analytics', path: '/analytics' },
  { icon: Settings, label: 'Settings', path: '/settings' },
]

export default function DashboardLayout() {
  const { user, logout } = useAuthStore()
  const { sidebarOpen, theme, toggleSidebar, setTheme } = useUIStore()
  const navigate = useNavigate()
  const location = useLocation()
  
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [notiOpen, setNotiOpen] = useState(false)
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const [selectedWorkspace, setSelectedWorkspace] = useState('Personal Dev Node')
  const [searchQuery, setSearchQuery] = useState('')

  const handleLogout = () => {
    logout()
    toast.success('Logged out successfully')
    navigate('/login')
  }

  // Force dark mode styles on initialization
  useEffect(() => {
    setTheme('dark')
    document.documentElement.classList.add('dark')
  }, [setTheme])

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#030712] font-sans antialiased text-gray-200">
      
      {/* Dynamic Style Injection for Sidebars & Glowing Borders */}
      <style>{`
        .active-nav-item {
          background: linear-gradient(to right, rgba(139, 92, 246, 0.1), rgba(99, 102, 241, 0.04));
          border-left: 2px solid #8b5cf6;
          color: #a78bfa !important;
          box-shadow: inset 4px 0 12px rgba(139, 92, 246, 0.06);
        }
        .nav-item-glow:hover {
          background: rgba(255, 255, 255, 0.02);
          color: #f3f4f6;
        }
        .nav-item-glow:hover svg {
          color: #a78bfa;
          transform: scale(1.05);
        }
        /* Custom scrollbar for sidebar */
        .sidebar-scroll::-webkit-scrollbar {
          width: 4px;
        }
        .sidebar-scroll::-webkit-scrollbar-track {
          background: transparent;
        }
        .sidebar-scroll::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.05);
          border-radius: 2px;
        }
        .glass-header {
          background: rgba(13, 16, 27, 0.45);
          backdrop-filter: blur(16px);
          -webkit-backdrop-filter: blur(16px);
          border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        }
        .sidebar-panel {
          background: rgba(9, 11, 20, 0.7);
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
          border-right: 1px solid rgba(255, 255, 255, 0.04);
        }
      `}</style>

      {/* Sidebar - Collapsible Width */}
      <motion.aside
        animate={{ width: sidebarOpen ? 260 : 76 }}
        transition={{ duration: 0.3, ease: [0.25, 0.8, 0.25, 1] }}
        className="sidebar-panel flex-shrink-0 flex flex-col h-full overflow-hidden z-30"
      >
        {/* Top Branding Section */}
        <div className="flex items-center justify-between px-4 py-4 flex-shrink-0">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-purple-600 to-indigo-600 flex items-center justify-center flex-shrink-0 shadow-[0_0_15px_rgba(139,92,246,0.35)]">
              <Zap size={18} className="text-white fill-white/10" />
            </div>
            {sidebarOpen && (
              <motion.div 
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                className="flex flex-col"
              >
                <span className="font-extrabold text-sm tracking-wide text-transparent bg-clip-text bg-gradient-to-r from-white via-gray-100 to-gray-400">
                  AI Studio
                </span>
                <span className="text-[9px] font-bold tracking-widest text-cyan-400 uppercase">
                  Enterprise
                </span>
              </motion.div>
            )}
          </div>
          
          {/* Collapse Button inside header on expanded mode */}
          {sidebarOpen && (
            <button 
              onClick={toggleSidebar}
              className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-white/[0.03] transition-colors"
            >
              <ChevronLeft size={16} />
            </button>
          )}
        </div>

        {/* Workspace Switcher */}
        <div className="px-3 mb-2 flex-shrink-0">
          {sidebarOpen ? (
            <div className="relative">
              <button 
                onClick={() => setWorkspaceOpen(!workspaceOpen)}
                className="flex items-center justify-between w-full px-3 py-2 bg-white/[0.02] hover:bg-white/[0.04] border border-white/[0.05] rounded-xl text-left transition-all"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-4 h-4 rounded-full bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center flex-shrink-0">
                    <div className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                  </div>
                  <span className="text-xs font-semibold truncate text-gray-300">
                    {selectedWorkspace}
                  </span>
                </div>
                <ChevronDown size={14} className="text-gray-500 flex-shrink-0" />
              </button>
              
              <AnimatePresence>
                {workspaceOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 5 }}
                    className="absolute top-full left-0 right-0 mt-1.5 bg-[#090b14] border border-white/[0.08] rounded-xl overflow-hidden shadow-2xl z-50 p-1"
                  >
                    {[
                      { name: 'Personal Dev Node', type: 'dev' },
                      { name: 'Team R&D Cluster', type: 'team' },
                      { name: 'Production Agent-X', type: 'prod' }
                    ].map((ws) => (
                      <button
                        key={ws.name}
                        onClick={() => {
                          setSelectedWorkspace(ws.name)
                          setWorkspaceOpen(false)
                          toast.success(`Switched to workspace: ${ws.name}`)
                        }}
                        className="flex items-center justify-between w-full px-3 py-2 text-xs text-left rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.03] transition-all"
                      >
                        <span>{ws.name}</span>
                        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-white/[0.05] text-gray-500 uppercase">
                          {ws.type}
                        </span>
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ) : (
            <div className="flex justify-center py-1">
              <button 
                onClick={toggleSidebar}
                className="w-8 h-8 rounded-lg bg-white/[0.02] border border-white/[0.05] hover:border-purple-500/30 flex items-center justify-center transition-colors"
              >
                <div className="w-2 h-2 rounded-full bg-cyan-400" />
              </button>
            </div>
          )}
        </div>

        {/* Sidebar Navigation */}
        <nav className="flex-1 px-3 space-y-0.5 overflow-y-auto sidebar-scroll">
          {sidebarOpen && (
            <p className="text-[9px] font-bold tracking-widest text-gray-600 uppercase px-3 py-2.5">
              Platform Core
            </p>
          )}
          {navItems.map(({ icon: Icon, label, path }) => {
            const isActive = location.pathname === path
            return (
              <NavLink
                key={path}
                to={path}
                className={`flex items-center gap-3.5 px-3.5 py-3 rounded-xl text-xs font-semibold text-gray-400 hover:text-white transition-all duration-200 nav-item-glow ${
                  isActive ? 'active-nav-item' : ''
                }`}
              >
                <Icon size={16} className="flex-shrink-0 transition-transform" />
                {sidebarOpen && (
                  <motion.span 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="truncate"
                  >
                    {label}
                  </motion.span>
                )}
              </NavLink>
            )
          })}
        </nav>

        {/* Sidebar Footer User Profile */}
        <div className="p-3 border-t border-white/[0.04] flex-shrink-0">
          <div className="relative">
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex items-center gap-3 w-full p-2.5 hover:bg-white/[0.03] border border-transparent hover:border-white/[0.05] rounded-xl transition-all"
            >
              <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-purple-500 to-indigo-500 text-white flex items-center justify-center text-xs font-extrabold flex-shrink-0 shadow-[0_0_10px_rgba(139,92,246,0.2)]">
                {user?.name?.[0]?.toUpperCase() || 'D'}
              </div>
              
              {sidebarOpen && (
                <motion.div 
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex-1 text-left min-w-0"
                >
                  <p className="text-xs font-semibold text-gray-200 truncate">
                    {user?.name || 'Demo User'}
                  </p>
                  <p className="text-[10px] text-gray-500 truncate mt-0.5">
                    {user?.email || 'demo@aistudio.com'}
                  </p>
                </motion.div>
              )}
            </button>

            {/* User Dropdown */}
            <AnimatePresence>
              {userMenuOpen && (
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 6 }}
                  className="absolute bottom-full left-0 right-0 mb-2 bg-[#090b14] border border-white/[0.08] rounded-xl overflow-hidden shadow-2xl z-50 p-1"
                >
                  <button
                    onClick={() => { navigate('/settings'); setUserMenuOpen(false) }}
                    className="flex items-center gap-2.5 w-full px-3.5 py-2.5 text-xs text-gray-400 hover:text-white hover:bg-white/[0.03] rounded-lg transition-colors"
                  >
                    <User size={13} /> Edit Profile
                  </button>
                  <button
                    onClick={handleLogout}
                    className="flex items-center gap-2.5 w-full px-3.5 py-2.5 text-xs text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors"
                  >
                    <LogOut size={13} /> Terminate Session
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </motion.aside>

      {/* Main Container */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        
        {/* Top Navbar */}
        <header className="glass-header flex items-center justify-between px-6 py-4 flex-shrink-0 z-20">
          
          {/* Left: Hamburger & Search */}
          <div className="flex items-center gap-4 flex-1">
            {!sidebarOpen && (
              <button
                onClick={toggleSidebar}
                className="p-2 text-gray-500 hover:text-gray-300 hover:bg-white/[0.03] border border-white/[0.05] rounded-xl transition-colors"
              >
                <Menu size={16} />
              </button>
            )}

            {/* Global Search Bar */}
            <div className="relative max-w-sm w-full hidden sm:block">
              <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                type="text"
                placeholder="Global search index..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-12 py-1.5 bg-white/[0.01] hover:bg-white/[0.03] border border-white/[0.05] focus:border-purple-500/50 rounded-xl text-xs text-gray-300 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-purple-500/20 transition-all"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[9px] font-bold text-gray-600 bg-white/[0.04] border border-white/[0.05] px-1.5 py-0.5 rounded uppercase">
                ⌘K
              </span>
            </div>
          </div>

          {/* Right Menu Controls */}
          <div className="flex items-center gap-3">
            
            {/* Live System Status Indicator */}
            <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500/5 border border-emerald-500/15 rounded-xl">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400">
                API Live: 99.9%
              </span>
            </div>

            {/* Theme Toggle (Static Dark Theme for Premium Aesthetics) */}
            <button
              onClick={() => toast.success('Workspace locked to Premium Dark Node')}
              className="p-2 text-gray-500 hover:text-gray-300 hover:bg-white/[0.03] border border-white/[0.05] rounded-xl transition-colors"
            >
              <Moon size={15} />
            </button>

            {/* Notification Dropdown */}
            <div className="relative">
              <button
                onClick={() => setNotiOpen(!notiOpen)}
                className="p-2 text-gray-500 hover:text-gray-300 hover:bg-white/[0.03] border border-white/[0.05] rounded-xl relative transition-colors"
              >
                <Bell size={15} />
                <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-purple-500 animate-pulse" />
              </button>

              <AnimatePresence>
                {notiOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 5 }}
                    className="absolute right-0 mt-2 w-72 bg-[#090b14] border border-white/[0.08] rounded-xl shadow-2xl overflow-hidden z-50 p-2 space-y-1"
                  >
                    <div className="flex justify-between items-center px-2 py-1.5 border-b border-white/[0.04]">
                      <span className="text-[10px] font-bold tracking-wider text-gray-400 uppercase">Alert Logs</span>
                      <button onClick={() => setNotiOpen(false)} className="text-[9px] text-purple-400 hover:underline">Clear</button>
                    </div>
                    {[
                      { text: 'ChromaDB collection successfully backfilled', time: '5m ago' },
                      { text: 'Llama-3 indexing complete', time: '1h ago' }
                    ].map((not, idx) => (
                      <div key={idx} className="p-2 hover:bg-white/[0.02] rounded-lg text-left transition-colors">
                        <p className="text-[11px] text-gray-300 leading-normal">{not.text}</p>
                        <span className="text-[9px] text-gray-500 font-medium mt-1 block">{not.time}</span>
                      </div>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </header>

        {/* Content Outlet */}
        <main className="flex-1 overflow-auto bg-[#030712] relative z-10">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
