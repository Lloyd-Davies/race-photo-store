import { useState, useEffect } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { BarChart3, CalendarDays, LogOut, ShieldAlert, ReceiptText, Settings } from 'lucide-react'
import Button from '../../components/Button'
import { adminLogin, refreshAdminSession, verifyAdminSession } from '../../api/adminAuth'

const ADMIN_ACCESS_TOKEN_KEY = 'adminAccessToken'
const ADMIN_REFRESH_TOKEN_KEY = 'adminRefreshToken'

export default function AdminLayout() {
  const [authed, setAuthed] = useState(false)
  const [input, setInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loadingLogin, setLoadingLogin] = useState(false)
  const [checkingStoredToken, setCheckingStoredToken] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    const accessToken = sessionStorage.getItem(ADMIN_ACCESS_TOKEN_KEY)
    const refreshToken = sessionStorage.getItem(ADMIN_REFRESH_TOKEN_KEY)

    if (!accessToken && !refreshToken) {
      setCheckingStoredToken(false)
      return
    }

    const verifyOrRefresh = async () => {
      try {
        if (accessToken) {
          await verifyAdminSession(accessToken)
          setAuthed(true)
          return
        }

        if (refreshToken) {
          const next = await refreshAdminSession(refreshToken)
          sessionStorage.setItem(ADMIN_ACCESS_TOKEN_KEY, next.access_token)
          sessionStorage.setItem(ADMIN_REFRESH_TOKEN_KEY, next.refresh_token)
          setAuthed(true)
          return
        }

        setAuthed(false)
      } catch {
        sessionStorage.removeItem(ADMIN_ACCESS_TOKEN_KEY)
        sessionStorage.removeItem(ADMIN_REFRESH_TOKEN_KEY)
        setAuthed(false)
        setError('Your admin session has expired. Please sign in again.')
      } finally {
        setCheckingStoredToken(false)
      }
    }

    void verifyOrRefresh()
  }, [])

  useEffect(() => {
    if (!authed) return

    const refresh = async () => {
      const refreshToken = sessionStorage.getItem(ADMIN_REFRESH_TOKEN_KEY)
      if (!refreshToken) {
        return
      }

      try {
        const next = await refreshAdminSession(refreshToken)
        sessionStorage.setItem(ADMIN_ACCESS_TOKEN_KEY, next.access_token)
        sessionStorage.setItem(ADMIN_REFRESH_TOKEN_KEY, next.refresh_token)
      } catch {
        sessionStorage.removeItem(ADMIN_ACCESS_TOKEN_KEY)
        sessionStorage.removeItem(ADMIN_REFRESH_TOKEN_KEY)
        setAuthed(false)
        setError('Your admin session is no longer valid. Please sign in again.')
      }
    }

    const id = window.setInterval(() => {
      void refresh()
    }, 5 * 60 * 1000)

    return () => window.clearInterval(id)
  }, [authed])

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    const token = input.trim()
    if (!token) {
      setError('Please enter a token.')
      return
    }

    setLoadingLogin(true)
    setError(null)
    try {
      const session = await adminLogin(token)
      sessionStorage.setItem(ADMIN_ACCESS_TOKEN_KEY, session.access_token)
      sessionStorage.setItem(ADMIN_REFRESH_TOKEN_KEY, session.refresh_token)
      setAuthed(true)
      setInput('')
    } catch {
      sessionStorage.removeItem(ADMIN_ACCESS_TOKEN_KEY)
      sessionStorage.removeItem(ADMIN_REFRESH_TOKEN_KEY)
      setAuthed(false)
      setError('Invalid admin credentials.')
    } finally {
      setLoadingLogin(false)
    }
  }

  function handleLogout() {
    sessionStorage.removeItem(ADMIN_ACCESS_TOKEN_KEY)
    sessionStorage.removeItem(ADMIN_REFRESH_TOKEN_KEY)
    setAuthed(false)
    setError(null)
    navigate('/admin/events')
  }

  if (checkingStoredToken) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center px-4">
        <div className="bg-surface-900 border border-surface-700 rounded-2xl p-8 w-full max-w-sm text-center">
          <p className="text-sm text-content-muted">Checking admin session…</p>
        </div>
      </div>
    )
  }

  if (!authed) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center px-4">
        <div className="bg-surface-900 border border-surface-700 rounded-2xl p-8 w-full max-w-sm">
          <div className="flex justify-center mb-6">
            <ShieldAlert size={40} className="text-sky-500" />
          </div>
          <h1 className="text-lg font-bold text-center text-content mb-6">Admin access</h1>
          <form onSubmit={handleLogin} className="space-y-4">
            <input
              type="password"
              autoFocus
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Admin credential"
              className="w-full bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-3 py-2 focus:outline-none focus:ring-1 focus:ring-sky-500 placeholder:text-content-muted"
            />
            {error && (
              <p className="text-xs text-red-400">{error}</p>
            )}
            <Button type="submit" className="w-full" loading={loadingLogin}>
              Sign in
            </Button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-[calc(100vh-64px)] min-w-0 overflow-x-hidden">
      {/* Sidebar — desktop only */}
      <aside className="hidden md:flex md:flex-col w-48 shrink-0 bg-surface-900 border-r border-surface-700 p-4 space-y-1">
        <NavLink
          to="/admin/dashboard"
          className={({ isActive }) =>
            `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              isActive
                ? 'bg-sky-500/20 text-sky-500'
                : 'text-content-muted hover:bg-surface-800 hover:text-content'
            }`
          }
        >
          <BarChart3 size={16} />
          Dashboard
        </NavLink>

        <NavLink
          to="/admin/events"
          end
          className={({ isActive }) =>
            `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              isActive
                ? 'bg-sky-500/20 text-sky-500'
                : 'text-content-muted hover:bg-surface-800 hover:text-content'
            }`
          }
        >
          <CalendarDays size={16} />
          Events
        </NavLink>

        <NavLink
          to="/admin/orders"
          className={({ isActive }) =>
            `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              isActive
                ? 'bg-sky-500/20 text-sky-500'
                : 'text-content-muted hover:bg-surface-800 hover:text-content'
            }`
          }
        >
          <ReceiptText size={16} />
          Orders
        </NavLink>

        <NavLink
          to="/admin/settings"
          className={({ isActive }) =>
            `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              isActive
                ? 'bg-sky-500/20 text-sky-500'
                : 'text-content-muted hover:bg-surface-800 hover:text-content'
            }`
          }
        >
          <Settings size={16} />
          Settings
        </NavLink>

        <div className="!mt-6">
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-500 hover:text-red-400 hover:bg-surface-800 transition-colors"
          >
            <LogOut size={16} />
            Sign out
          </button>
        </div>
      </aside>

      {/* Content */}
      <main className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto px-4 pt-4 pb-nav-safe md:px-8 md:pt-8 md:pb-8">
        <Outlet />
      </main>

      {/* Mobile bottom nav — visible below md */}
      <nav className="fixed bottom-0 left-0 right-0 z-40 flex md:hidden bg-surface-900 border-t border-surface-700 nav-safe-bottom">
        <NavLink
          to="/admin/dashboard"
          className={({ isActive }) =>
            `flex flex-1 flex-col items-center justify-center gap-0.5 py-3 text-[11px] font-medium transition-colors ${
              isActive ? 'text-sky-400' : 'text-content-muted'
            }`
          }
        >
          <BarChart3 size={20} />
          Metrics
        </NavLink>
        <NavLink
          to="/admin/events"
          end
          className={({ isActive }) =>
            `flex flex-1 flex-col items-center justify-center gap-0.5 py-3 text-[11px] font-medium transition-colors ${
              isActive ? 'text-sky-400' : 'text-content-muted'
            }`
          }
        >
          <CalendarDays size={20} />
          Events
        </NavLink>
        <NavLink
          to="/admin/orders"
          className={({ isActive }) =>
            `flex flex-1 flex-col items-center justify-center gap-0.5 py-3 text-[11px] font-medium transition-colors ${
              isActive ? 'text-sky-400' : 'text-content-muted'
            }`
          }
        >
          <ReceiptText size={20} />
          Orders
        </NavLink>
        <NavLink
          to="/admin/settings"
          className={({ isActive }) =>
            `flex flex-1 flex-col items-center justify-center gap-0.5 py-3 text-[11px] font-medium transition-colors ${
              isActive ? 'text-sky-400' : 'text-content-muted'
            }`
          }
        >
          <Settings size={20} />
          Settings
        </NavLink>
        <button
          type="button"
          onClick={handleLogout}
          className="flex flex-1 flex-col items-center justify-center gap-0.5 py-3 text-[11px] font-medium text-content-muted hover:text-red-400 transition-colors"
        >
          <LogOut size={20} />
          Sign out
        </button>
      </nav>
    </div>
  )
}
