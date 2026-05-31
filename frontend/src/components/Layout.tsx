import { Outlet, Link } from 'react-router-dom'
import { Camera, ShoppingBag } from 'lucide-react'
import { useCartStore } from '../store/cart'
import CartDrawer from './CartDrawer'
import SelectedActionBar from './SelectedActionBar'
import ThemeToggle from './ThemeToggle'
import { useState } from 'react'
import { useSiteConfig } from '../context/SiteConfig'
import { clsx } from '../utils/clsx'

export default function Layout() {
  const items = useCartStore((s) => s.items)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const { site_name } = useSiteConfig()

  return (
    <div className="min-h-screen flex flex-col bg-surface-950">
      {/* Top nav */}
      <header className="sticky top-0 z-40 bg-surface-950/90 backdrop-blur border-b border-surface-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <Link
            to="/"
            className="flex items-center gap-2 font-semibold text-content hover:text-sky-500 transition-colors"
          >
            <Camera size={20} className="text-sky-500" />
            <span>{site_name}</span>
          </Link>

          <nav className="flex items-center gap-4">
            <button
              onClick={() => setDrawerOpen(true)}
              className="relative flex items-center gap-2 rounded px-2 py-1.5 text-sm text-content-muted transition-colors hover:bg-surface-900 hover:text-content"
              aria-label="Open selected photos"
            >
              <ShoppingBag size={19} />
              <span className="hidden sm:inline">Selected</span>
              {items.length > 0 && (
                <span className="absolute -top-1.5 -right-1.5 bg-sky-500 text-white text-xs font-bold w-4 h-4 rounded-full flex items-center justify-center leading-none">
                  {items.length}
                </span>
              )}
            </button>

            <ThemeToggle />
          </nav>
        </div>
      </header>

      {/* Page content */}
      <main className={clsx('flex-1', items.length > 0 && 'pb-24 md:pb-0')}>
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="border-t border-surface-700 py-6 text-center text-sm text-content-muted">
        <div className="flex items-center justify-center gap-3">
          <span>{site_name} &copy; {new Date().getFullYear()}</span>
          <span className="text-surface-600">•</span>
          <Link to="/admin/events" className="hover:text-content transition-colors">
            Login
          </Link>
        </div>
      </footer>

      {/* Cart drawer */}
      <CartDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
      <SelectedActionBar />
    </div>
  )
}
