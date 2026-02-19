import { useState, useEffect } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { CalendarDays, LogOut, ShieldAlert } from 'lucide-react'
import Button from '../../components/Button'

const ADMIN_TOKEN_KEY = 'adminToken'

export default function AdminLayout() {
  const [authed, setAuthed] = useState(false)
  const [input, setInput] = useState('')
  const [error, setError] = useState(false)
  const navigate = useNavigate()

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
        <Outlet />
      </main>
    </div>
  )
}
