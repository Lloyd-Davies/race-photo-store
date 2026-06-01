import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Trash2, ArrowLeft, Mail } from 'lucide-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useCartStore } from '../store/cart'
import { createCart } from '../api/cart'
import { createCheckout } from '../api/cart'
import Button from '../components/Button'
import { fetchEvents } from '../api/events'
import { formatMoney } from '../utils/money'
import { useSiteConfig } from '../context/SiteConfig'
import EmbeddedBrowserWarning from '../components/EmbeddedBrowserWarning'
import { isEmbeddedInAppBrowser } from '../utils/embeddedBrowser'

export default function Cart() {
  const items = useCartStore((s) => s.items)
  const eventId = useCartStore((s) => s.eventId)
  const eventSlug = useCartStore((s) => s.eventSlug)
  const remove = useCartStore((s) => s.remove)
  const clear = useCartStore((s) => s.clear)
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const siteConfig = useSiteConfig()
  const { data: events } = useQuery({ queryKey: ['events'], queryFn: fetchEvents })
  const event = events?.find((e) => e.id === eventId)
  const galleryPath = event?.slug ? `/events/${event.slug}` : eventSlug ? `/events/${eventSlug}` : '/'
  const unitPrice = event?.effective_photo_price_pence
  const subtotal = unitPrice ? items.length * unitPrice : 0
  const isInAppBrowser = isEmbeddedInAppBrowser()

  const checkoutMut = useMutation({
    mutationFn: async () => {
      if (!eventId) throw new Error('No event selected')
      if (!email.trim()) throw new Error('Email address is required')
      setError(null)

      // Create cart server-side
      const cart = await createCart({
        event_id: eventId,
        photo_ids: items.map((i) => i.photoId),
        email: email || undefined,
      })

      // Create Stripe checkout session
      const checkout = await createCheckout(cart.cart_id, email || undefined)

      // Store order ID so we can return to it if the user navigates back
      localStorage.setItem('lastOrderId', String(checkout.order_id))
      localStorage.setItem(`orderAccessToken:${checkout.order_id}`, checkout.order_access_token)

      if (checkout.stripe_checkout_url) {
        // Hand off to Stripe — browser navigates away
        window.location.href = checkout.stripe_checkout_url
        return
      }

      navigate(`/orders/${checkout.order_id}?access_token=${checkout.order_access_token}`)
    },
    onError: (e: Error) => setError(e.message),
  })

  if (items.length === 0) {
    return (
      <div className="mx-auto max-w-xl min-w-0 px-4 py-20 text-center">
        <p className="text-gray-400 mb-6">Your cart is empty.</p>
        <Link to="/">
          <Button variant="secondary">Browse events</Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-xl min-w-0 px-4 py-10 sm:px-6">
      <Link
        to={galleryPath}
        className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 mb-6 transition-colors"
      >
        <ArrowLeft size={16} />
        Back to gallery
      </Link>

      <h1 className="text-xl font-bold text-content mb-6">
        Your cart — {items.length} photo{items.length !== 1 ? 's' : ''}
      </h1>

      {isInAppBrowser && <EmbeddedBrowserWarning mode="checkout" />}

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
            {event && (
              <span className="text-xs text-content-muted">
                {formatMoney(event.effective_photo_price_pence, event.currency)}
              </span>
            )}
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

      {event && (
        <div className="bg-surface-900 border border-surface-700 rounded-lg px-4 py-3 mb-6 space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-content-muted">Unit price</span>
            <span className="text-content">{formatMoney(event.effective_photo_price_pence, event.currency)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-content-muted">Photos</span>
            <span className="text-content">{items.length}</span>
          </div>
          <div className="flex justify-between font-semibold">
            <span className="text-content">Subtotal</span>
            <span className="text-content">{formatMoney(subtotal, event.currency)}</span>
          </div>
          {siteConfig.allow_stripe_promotion_codes && (
            <p className="text-xs text-content-muted">
              Promotion codes can be applied on Stripe's secure checkout page.
            </p>
          )}
        </div>
      )}

      {/* Email */}
      <div className="mb-6">
        <label className="block text-sm text-gray-300 mb-2 font-medium">
          <Mail size={14} className="inline mr-1.5 text-sky-500" />
          Email <span className="text-red-400">*</span>
          <span className="block font-normal text-gray-500 sm:ml-1 sm:inline">- order confirmation &amp; download link</span>
        </label>
        <input
          type="email"
          required
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

      <div className="grid gap-3 sm:flex">
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
        You'll be redirected to Stripe's secure checkout. Photos are delivered by
        ZIP and individual image links after payment.
      </p>
    </div>
  )
}
