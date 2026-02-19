import { Outlet, Link } from 'react-router-dom'
import { ShoppingCart, Camera } from 'lucide-react'
import { useCartStore } from '../store/cart'
import CartDrawer from './CartDrawer'
import { useState } from 'react'

export default function Layout() {
  const items = useCartStore((s) => s.items)
  const [drawerOpen, setDrawerOpen] = useState(false)

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top nav */}
      <header className="sticky top-0 z-40 bg-surface-950/90 backdrop-blur border-b border-surface-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <Link
            to="/"
            className="flex items-center gap-2 font-semibold text-gray-100 hover:text-orange-400 transition-colors"
          >
            <Camera size={20} className="text-orange-500" />
            <span>Race Photos</span>
          </Link>

          <nav className="flex items-center gap-4">
            <Link
              to="/admin/events"
              className="text-sm text-gray-400 hover:text-gray-200 transition-colors"
            >
              Admin
            </Link>

            <button
              onClick={() => setDrawerOpen(true)}
              className="relative flex items-center gap-1.5 text-sm text-gray-300 hover:text-orange-400 transition-colors"
              aria-label="Open cart"
            >
              <ShoppingCart size={20} />
              {items.length > 0 && (
                <span className="absolute -top-1.5 -right-1.5 bg-orange-500 text-white text-xs font-bold w-4 h-4 rounded-full flex items-center justify-center leading-none">
                  {items.length}
                </span>
              )}
            </button>
          </nav>
        </div>
      </header>

      {/* Page content */}
      <main className="flex-1">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="border-t border-surface-700 py-6 text-center text-sm text-gray-500">
        Race Photos &copy; {new Date().getFullYear()}
      </footer>

      {/* Cart drawer */}
      <CartDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  )
}
