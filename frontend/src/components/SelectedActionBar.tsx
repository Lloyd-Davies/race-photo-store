import { Link } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import { ShoppingBag, X } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { fetchEvents } from '../api/events'
import { useVisualViewport } from '../hooks/useVisualViewport'
import { useCartStore } from '../store/cart'
import { formatMoney } from '../utils/money'

const MOBILE_BAR_EDGE_GAP = 12

export default function SelectedActionBar() {
  const barRef = useRef<HTMLDivElement | null>(null)
  const [barHeight, setBarHeight] = useState(72)
  const items = useCartStore((s) => s.items)
  const eventId = useCartStore((s) => s.eventId)
  const clear = useCartStore((s) => s.clear)
  const viewport = useVisualViewport()
  const { data: events } = useQuery({ queryKey: ['events'], queryFn: fetchEvents })
  const event = events?.find((e) => e.id === eventId)
  const subtotal = event ? items.length * event.effective_photo_price_pence : null
  const visibleTop = Math.max(0, Math.floor(viewport.offsetTop + viewport.height - barHeight - MOBILE_BAR_EDGE_GAP))
  const visibleLeft = Math.max(0, Math.floor(viewport.offsetLeft + MOBILE_BAR_EDGE_GAP))
  const visibleWidth = Math.max(0, Math.floor(viewport.width - MOBILE_BAR_EDGE_GAP * 2))

  useEffect(() => {
    const bar = barRef.current
    if (!bar) return undefined

    function updateHeight() {
      const currentBar = barRef.current
      if (!currentBar) return
      const nextHeight = Math.ceil(currentBar.getBoundingClientRect().height)
      if (nextHeight > 0) setBarHeight(nextHeight)
    }

    updateHeight()
    const resizeObserver = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(updateHeight)
      : null
    resizeObserver?.observe(bar)
    window.addEventListener('resize', updateHeight)

    return () => {
      resizeObserver?.disconnect()
      window.removeEventListener('resize', updateHeight)
    }
  }, [event?.currency, items.length, subtotal])

  if (items.length === 0) return null

  return (
    <div
      ref={barRef}
      className="fixed z-40 rounded-lg border border-surface-700 bg-surface-950/95 px-3 py-3 shadow-2xl backdrop-blur md:hidden"
      style={{
        top: visibleTop,
        left: visibleLeft,
        width: visibleWidth,
        paddingBottom: 'calc(0.75rem + env(safe-area-inset-bottom, 0px))',
      }}
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
