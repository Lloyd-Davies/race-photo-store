import { useState, useEffect } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, LogOut, ShieldAlert, ReceiptText } from 'lucide-react'
import Button from '../../components/Button'
import { fetchAdminStats } from '../../api/adminStats'
import { Skeleton } from '../../components/Skeleton'

const ADMIN_TOKEN_KEY = 'adminToken'

export default function AdminLayout() {
  const [authed, setAuthed] = useState(false)
  const [input, setInput] = useState('')
  const [error, setError] = useState(false)
  const navigate = useNavigate()

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['admin-stats'],
    queryFn: fetchAdminStats,
    enabled: authed,
    refetchInterval: 30000,
  })

  useEffect(() => {
    if (sessionStorage.getItem(ADMIN_TOKEN_KEY)) {
      setAuthed(true)
    }
  }, [])

  function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    if (input.trim()) {
      sessionStorage.setItem(ADMIN_TOKEN_KEY, input.trim())
      setAuthed(true)
      setError(false)
    } else {
      setError(true)
    }
  }

  function handleLogout() {
    sessionStorage.removeItem(ADMIN_TOKEN_KEY)
    setAuthed(false)
    navigate('/admin/events')
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
              placeholder="Admin token"
              className="w-full bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-3 py-2 focus:outline-none focus:ring-1 focus:ring-sky-500 placeholder:text-content-muted"
            />
            {error && (
              <p className="text-xs text-red-400">Please enter a token.</p>
            )}
            <Button type="submit" className="w-full">
              Sign in
            </Button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-[calc(100vh-64px)]">
      {/* Sidebar */}
      <aside className="w-48 shrink-0 bg-surface-900 border-r border-surface-700 p-4 space-y-1">
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
      <main className="flex-1 p-8 overflow-y-auto">
        <div className="mb-6 bg-surface-900 border border-surface-700 rounded-xl p-4">
          <p className="text-xs uppercase tracking-wide text-content-muted mb-3">Admin snapshot</p>
          {statsLoading && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {Array.from({ length: 5 }).map((_, idx) => (
                <Skeleton key={idx} className="h-14 rounded-lg" />
              ))}
            </div>
          )}

          {!statsLoading && stats && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div className="bg-surface-800 border border-surface-700 rounded-lg px-3 py-2">
                <p className="text-[11px] text-content-muted">Events</p>
                <p className="text-lg font-semibold text-content">{stats.total_events}</p>
              </div>
              <div className="bg-surface-800 border border-surface-700 rounded-lg px-3 py-2">
                <p className="text-[11px] text-content-muted">Photos</p>
                <p className="text-lg font-semibold text-content">{stats.total_photos}</p>
              </div>
              <div className="bg-surface-800 border border-surface-700 rounded-lg px-3 py-2">
                <p className="text-[11px] text-content-muted">Orders</p>
                <p className="text-lg font-semibold text-content">{stats.total_orders}</p>
              </div>
              <div className="bg-surface-800 border border-surface-700 rounded-lg px-3 py-2">
                <p className="text-[11px] text-content-muted">Pending</p>
                <p className="text-lg font-semibold text-content">{stats.pending_orders}</p>
              </div>
              <div className="bg-surface-800 border border-surface-700 rounded-lg px-3 py-2">
                <p className="text-[11px] text-content-muted">Failed</p>
                <p className="text-lg font-semibold text-content">{stats.failed_orders}</p>
              </div>
            </div>
          )}
        </div>
        <Outlet />
      </main>
    </div>
  )
}
