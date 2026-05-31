import { useEffect, useMemo, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Lock, Search, ShoppingCart, X } from 'lucide-react'
import { fetchEvent, fetchPhotos, unlockEvent } from '../api/events'
import { useCartStore } from '../store/cart'
import PhotoCard from '../components/PhotoCard'
import { PhotoSkeleton } from '../components/Skeleton'
import Button from '../components/Button'
import type { Photo } from '../api/events'
import { formatMoney } from '../utils/money'

export default function EventGallery() {
  const { eventRef } = useParams<{ eventRef: string }>()
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [bibInput, setBibInput] = useState('')
  const [startTimeInput, setStartTimeInput] = useState('')
  const [endTimeInput, setEndTimeInput] = useState('')
  const [bib, setBib] = useState<string | undefined>()
  const [startTime, setStartTime] = useState<string | undefined>()
  const [endTime, setEndTime] = useState<string | undefined>()
  const [activePhoto, setActivePhoto] = useState<Photo | null>(null)
  const [eventAccessToken, setEventAccessToken] = useState<string | null>(null)
  const [unlockSecret, setUnlockSecret] = useState('')
  const [unlockError, setUnlockError] = useState<string | null>(null)
  const [unlocking, setUnlocking] = useState(false)
  const cartCount = useCartStore((s) => s.items.length)

  const { data: event, isLoading: eventLoading, error: eventError } = useQuery({
    queryKey: ['event', eventRef],
    queryFn: () => fetchEvent(eventRef as string),
    enabled: !!eventRef,
  })

  const isEventLocked = !!event?.is_password_protected

  useEffect(() => {
    if (!event || !eventRef || eventRef === event.slug) return
    navigate(`/events/${event.slug}`, { replace: true })
  }, [event, eventRef, navigate])

  const eventAccessKey = useMemo(() => event ? `eventAccess:${event.id}` : null, [event?.id])

  useEffect(() => {
    if (!eventAccessKey) {
      setEventAccessToken(null)
      return
    }
    const token = sessionStorage.getItem(eventAccessKey)
    setEventAccessToken(token)
  }, [eventAccessKey])

  const { data, isLoading: photosLoading, error: photosError } = useQuery({
    queryKey: ['photos', event?.slug, page, bib, startTime, endTime, eventAccessToken],
    queryFn: () => fetchPhotos(event!.slug, page, bib, startTime, endTime, eventAccessToken ?? undefined),
    enabled: !!event && (!isEventLocked || !!eventAccessToken),
    placeholderData: (prev) => prev,
  })

  useEffect(() => {
    if (!isEventLocked || !photosError || !eventAccessKey) return
    const message = photosError instanceof Error ? photosError.message : ''
    if (!message.startsWith('401:')) return
    sessionStorage.removeItem(eventAccessKey)
    setEventAccessToken(null)
    setUnlockError('Access expired. Please enter the event secret again.')
  }, [photosError, eventAccessKey, isEventLocked])

  async function handleUnlock(e: React.FormEvent) {
    e.preventDefault()
    if (!event || !eventAccessKey) return
    if (!unlockSecret.trim()) {
      setUnlockError('Please enter the event secret.')
      return
    }

    setUnlocking(true)
    setUnlockError(null)
    try {
      const unlocked = await unlockEvent(event.slug, unlockSecret.trim())
      sessionStorage.setItem(eventAccessKey, unlocked.access_token)
      setEventAccessToken(unlocked.access_token)
      setUnlockSecret('')
    } catch {
      setUnlockError('Invalid event secret.')
    } finally {
      setUnlocking(false)
    }
  }

  function handleBibSearch(e: React.FormEvent) {
    e.preventDefault()
    setBib(bibInput.trim() || undefined)
    setStartTime(startTimeInput || undefined)
    setEndTime(endTimeInput || undefined)
    setPage(1)
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-4 mb-6">
        <Link
          to="/"
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 transition-colors"
        >
          <ArrowLeft size={16} />
          Events
        </Link>
        <span className="text-surface-600">/</span>
        <span className="text-sm text-gray-200 font-medium">
          {event?.name ?? 'Event'}
        </span>
      </div>

      {eventError && (
        <p className="text-red-400 text-sm text-center py-12">
          Event not found or no longer available.
        </p>
      )}

      {/* Title + controls */}
      {!eventError && (
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl font-bold text-content">{event?.name ?? 'Gallery'}</h1>
          {data && (
            <p className="text-sm text-gray-400 mt-0.5">
              {data.total} photos
              {event && (
                <span className="ml-2 text-content-muted">
                  {formatMoney(event.effective_photo_price_pence, event.currency)} each
                </span>
              )}
            </p>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Filters */}
          <form onSubmit={handleBibSearch} className="flex gap-2">
            <input
              type="text"
              value={bibInput}
              onChange={(e) => setBibInput(e.target.value)}
              placeholder="Bib number…"
              className="bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-3 py-1.5 w-32 focus:outline-none focus:ring-1 focus:ring-sky-500 placeholder:text-content-muted"
            />
            <input
              type="time"
              value={startTimeInput}
              onChange={(e) => setStartTimeInput(e.target.value)}
              title="Start time"
              className="bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
            <input
              type="time"
              value={endTimeInput}
              onChange={(e) => setEndTimeInput(e.target.value)}
              title="End time"
              className="bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
            <Button type="submit" size="sm" variant="secondary">
              <Search size={14} />
            </Button>
            {(bib || startTime || endTime) && (
              <Button
                size="sm"
                variant="ghost"
                type="button"
                onClick={() => {
                  setBib(undefined)
                  setStartTime(undefined)
                  setEndTime(undefined)
                  setBibInput('')
                  setStartTimeInput('')
                  setEndTimeInput('')
                  setPage(1)
                }}
              >
                Clear
              </Button>
            )}
          </form>

          {/* Cart shortcut */}
          {cartCount > 0 && (
            <Link to="/cart">
              <Button size="sm">
                <ShoppingCart size={14} className="mr-1" />
                {cartCount} selected
                {event && ` - ${formatMoney(cartCount * event.effective_photo_price_pence, event.currency)}`}
              </Button>
            </Link>
          )}
        </div>
      </div>
      )}

      {/* Gallery */}
      {!eventError && isEventLocked && !eventAccessToken && (
        <div className="max-w-md mx-auto bg-surface-900 border border-surface-700 rounded-xl p-6 mb-6">
          <div className="flex items-center gap-2 mb-2 text-content">
            <Lock size={16} className="text-sky-500" />
            <h2 className="font-semibold">This event is secret protected</h2>
          </div>
          {event?.access_hint && (
            <p className="text-sm text-content-muted mb-3">Hint: {event.access_hint}</p>
          )}
          <form onSubmit={handleUnlock} className="space-y-3">
            <input
              type="password"
              value={unlockSecret}
              onChange={(e) => setUnlockSecret(e.target.value)}
              placeholder="Event secret"
              className="w-full bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-3 py-2 focus:outline-none focus:ring-1 focus:ring-sky-500 placeholder:text-content-muted"
            />
            {unlockError && <p className="text-xs text-red-400">{unlockError}</p>}
            <Button type="submit" size="sm" loading={unlocking}>
              Unlock event
            </Button>
          </form>
        </div>
      )}

      {!eventError && (eventLoading || photosLoading) && <PhotoSkeleton />}
      {!eventError && photosError && (
        <p className="text-red-400 text-sm text-center py-12">Failed to load photos.</p>
      )}
      {!eventError && data && data.photos.length === 0 && (
        <p className="text-gray-500 text-sm text-center py-12">
          {bib || startTime || endTime ? 'No photos found for this filter set.' : 'No photos in this event yet.'}
        </p>
      )}
      {!eventError && data && data.photos.length > 0 && event && (
        <>
          <div className="masonry">
            {data.photos.map((photo) => (
              <PhotoCard
                key={photo.photo_id}
                photo={photo}
                eventId={event.id}
                eventSlug={event.slug}
                onFullscreen={setActivePhoto}
              />
            ))}
          </div>

          {/* Pagination */}
          {data.pages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-8">
              <Button
                variant="secondary"
                size="sm"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <span className="text-sm text-gray-400">
                Page {data.page} of {data.pages}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={page === data.pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}

      {activePhoto && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
          onClick={() => setActivePhoto(null)}
          role="dialog"
          aria-modal="true"
        >
          <button
            className="absolute top-4 right-4 text-white"
            onClick={() => setActivePhoto(null)}
            aria-label="Close fullscreen viewer"
          >
            <X size={28} />
          </button>
          <img
            src={activePhoto.proof_url}
            alt={`Photo ${activePhoto.photo_id}`}
            className="max-w-full max-h-full object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  )
}
