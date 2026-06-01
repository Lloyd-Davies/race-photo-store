import { Link } from 'react-router-dom'
import { ShoppingBag, X } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { fetchEvents } from '../api/events'
import { useVisualViewport } from '../hooks/useVisualViewport'
import { useCartStore } from '../store/cart'
import { formatMoney } from '../utils/money'

export default function SelectedActionBar() {
  const items = useCartStore((s) => s.items)
  const eventId = useCartStore((s) => s.eventId)
  const clear = useCartStore((s) => s.clear)
  const viewport = useVisualViewport()
  const { data: events } = useQuery({ queryKey: ['events'], queryFn: fetchEvents })
  const event = events?.find((e) => e.id === eventId)
  const subtotal = event ? items.length * event.effective_photo_price_pence : null
  const rawBottomOffset = typeof window === 'undefined'
    ? 0
    : window.innerHeight - (viewport.offsetTop + viewport.height)
  const bottomOffset = Math.max(1, Math.ceil(rawBottomOffset))

  if (items.length === 0) return null

  return (
    <div
      className="fixed inset-x-0 z-40 border-t border-surface-700 bg-surface-950/95 px-4 py-3 shadow-2xl backdrop-blur md:hidden nav-safe-bottom"
      style={{ bottom: bottomOffset }}
    >
      <div className="mx-auto flex max-w-lg items-center gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded bg-surface-800 text-content">
            <ShoppingBag size={18} />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-content">
              {items.length} selected photo{items.length !== 1 ? 's' : ''}
            </p>
            {event && subtotal !== null && (
              <p className="text-xs text-content-muted">{formatMoney(subtotal, event.currency)}</p>
            )}
          </div>
        </div>

        <button
          type="button"
          onClick={clear}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded text-content-muted transition-colors hover:bg-surface-800 hover:text-content"
          aria-label="Clear selected photos"
        >
          <X size={17} />
        </button>
        <Link
          to="/cart"
          className="shrink-0 rounded bg-sky-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-sky-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
        >
          Review
        </Link>
      </div>
    </div>
  )
}
