import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { X, ShoppingCart, Trash2 } from 'lucide-react'
import { useCartStore } from '../store/cart'
import Button from './Button'

interface CartDrawerProps {
  open: boolean
  onClose: () => void
}

export default function CartDrawer({ open, onClose }: CartDrawerProps) {
  const items = useCartStore((s) => s.items)
  const remove = useCartStore((s) => s.remove)
  const clear = useCartStore((s) => s.clear)
  const navigate = useNavigate()

  // Trap scroll when open
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [open])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity duration-300 ${
          open ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
        aria-hidden
      />

      {/* Drawer panel */}
      <aside
        className={`fixed right-0 top-0 z-50 h-full w-80 max-w-[90vw] bg-surface-900 border-l border-surface-700 shadow-2xl flex flex-col transition-transform duration-300 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
        aria-label="Cart"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 h-14 border-b border-surface-700 shrink-0">
          <div className="flex items-center gap-2 font-semibold text-content">
            <ShoppingCart size={18} className="text-sky-500" />
            <span>Cart ({items.length})</span>
          </div>
          <button
            onClick={onClose}
            className="text-content-muted hover:text-content transition-colors"
            aria-label="Close cart"
          >
            <X size={20} />
          </button>
        </div>

        {/* Items */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {items.length === 0 ? (
            <p className="text-sm text-gray-500 text-center mt-8">Your cart is empty.</p>
          ) : (
            items.map((item) => (
              <div
                key={item.photoId}
                className="flex items-center gap-3 bg-surface-800 rounded-lg p-2"
              >
                <img
                  src={item.proofUrl}
                  alt={item.photoId}
                  className="w-14 h-14 object-cover rounded"
                />
                <span className="flex-1 text-xs text-gray-400 truncate">{item.photoId}</span>
                <button
                  onClick={() => remove(item.photoId)}
                  className="text-gray-500 hover:text-red-400 transition-colors shrink-0"
                  aria-label="Remove"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))
          )}
        </div>

        {/* Footer actions */}
        {items.length > 0 && (
          <div className="p-4 border-t border-surface-700 space-y-2 shrink-0">
            <Button
              className="w-full"
              onClick={() => { onClose(); navigate('/cart') }}
            >
              Checkout ({items.length} photo{items.length !== 1 ? 's' : ''})
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="w-full text-gray-400"
              onClick={clear}
            >
              Clear cart
            </Button>
          </div>
        )}
      </aside>
    </>
  )
}
