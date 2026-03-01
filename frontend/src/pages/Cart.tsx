import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Trash2, ArrowLeft, Mail } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import { useCartStore } from '../store/cart'
import { createCart } from '../api/cart'
import { createCheckout } from '../api/cart'
import Button from '../components/Button'

export default function Cart() {
  const items = useCartStore((s) => s.items)
  const eventId = useCartStore((s) => s.eventId)
  const remove = useCartStore((s) => s.remove)
  const clear = useCartStore((s) => s.clear)
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)

  const checkoutMut = useMutation({
    mutationFn: async () => {
      if (!eventId) throw new Error('No event selected')
      setError(null)

      // Create cart server-side
      const cart = await createCart({
        event_id: eventId,
        photo_ids: items.map((i) => i.photoId),
        email: email || undefined,
      })

      // Create Stripe checkout session
      const checkout = await createCheckout(cart.cart_id)

      // Store order ID so we can return to it if the user navigates back
      localStorage.setItem('lastOrderId', String(checkout.order_id))
      localStorage.setItem(`orderAccessToken:${checkout.order_id}`, checkout.order_access_token)

      // Hand off to Stripe — browser navigates away
      window.location.href = checkout.stripe_checkout_url
    },
    onError: (e: Error) => setError(e.message),
  })

  if (items.length === 0) {
    return (
      <div className="max-w-xl mx-auto px-4 py-20 text-center">
        <p className="text-gray-400 mb-6">Your cart is empty.</p>
        <Link to="/">
          <Button variant="secondary">Browse events</Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="max-w-xl mx-auto px-4 sm:px-6 py-10">
      <Link
        to={eventId ? `/events/${eventId}` : '/'}
        className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 mb-6 transition-colors"
      >
        <ArrowLeft size={16} />
        Back to gallery
      </Link>

      <h1 className="text-xl font-bold text-content mb-6">
        Your cart — {items.length} photo{items.length !== 1 ? 's' : ''}
      </h1>

      {/* Photo list */}
      <div className="space-y-3 mb-8">
        {items.map((item) => (
          <div
            key={item.photoId}
            className="flex items-center gap-3 bg-surface-900 border border-surface-700 rounded-lg p-3"
          >
            <img
              src={item.proofUrl}
              alt={item.photoId}
              className="w-16 h-16 object-cover rounded"
            />
            <span className="flex-1 text-sm text-gray-300 truncate">{item.photoId}</span>
            <button
              onClick={() => remove(item.photoId)}
              className="text-gray-500 hover:text-red-400 transition-colors"
              aria-label="Remove"
            >
              <Trash2 size={16} />
            </button>
          </div>
        ))}
      </div>

      {/* Email */}
      <div className="mb-6">
        <label className="block text-sm text-gray-300 mb-2 font-medium">
          <Mail size={14} className="inline mr-1.5 text-sky-500" />
          Email (optional — for order confirmation)
        </label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className="w-full bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-3 py-2 focus:outline-none focus:ring-1 focus:ring-sky-500 placeholder:text-content-muted"
        />
      </div>

      {error && (
        <p className="text-sm text-red-400 mb-4 bg-red-500/10 border border-red-500/20 rounded px-3 py-2">
          {error}
        </p>
      )}

      <div className="flex gap-3">
        <Button
          className="flex-1"
          loading={checkoutMut.isPending}
          onClick={() => checkoutMut.mutate()}
        >
          Pay with Stripe
        </Button>
        <Button variant="ghost" size="md" onClick={clear}>
          Clear
        </Button>
      </div>

      <p className="mt-4 text-xs text-gray-500 text-center">
        You'll be redirected to Stripe's secure checkout. Photos are delivered as a
        ZIP download after payment.
      </p>
    </div>
  )
}
