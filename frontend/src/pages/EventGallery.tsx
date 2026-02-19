import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Search, ShoppingCart } from 'lucide-react'
import { fetchPhotos, fetchEvents } from '../api/events'
import { useCartStore } from '../store/cart'
import PhotoCard from '../components/PhotoCard'
import { PhotoSkeleton } from '../components/Skeleton'
import Button from '../components/Button'

export default function EventGallery() {
  const { eventId } = useParams<{ eventId: string }>()
  const id = Number(eventId)
  const [page, setPage] = useState(1)
  const [bibInput, setBibInput] = useState('')
  const [bib, setBib] = useState<string | undefined>()
  const cartCount = useCartStore((s) => s.items.length)

  const { data: events } = useQuery({
    queryKey: ['events'],
    queryFn: fetchEvents,
  })

  const event = events?.find((e) => e.id === id)

  const { data, isLoading, error } = useQuery({
    queryKey: ['photos', id, page, bib],
    queryFn: () => fetchPhotos(id, page, bib),
    enabled: !isNaN(id),
    placeholderData: (prev) => prev,
  })

  function handleBibSearch(e: React.FormEvent) {
    e.preventDefault()
    setBib(bibInput.trim() || undefined)
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
          {event?.name ?? `Event ${id}`}
        </span>
      </div>

      {/* Title + controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl font-bold text-content">{event?.name ?? 'Gallery'}</h1>
          {data && (
            <p className="text-sm text-gray-400 mt-0.5">{data.total} photos</p>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Bib search */}
          <form onSubmit={handleBibSearch} className="flex gap-2">
            <input
              type="text"
              value={bibInput}
              onChange={(e) => setBibInput(e.target.value)}
              placeholder="Bib number…"
              className="bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-3 py-1.5 w-32 focus:outline-none focus:ring-1 focus:ring-sky-500 placeholder:text-content-muted"
            />
            <Button type="submit" size="sm" variant="secondary">
              <Search size={14} />
            </Button>
            {bib && (
              <Button
                size="sm"
                variant="ghost"
                type="button"
                onClick={() => { setBib(undefined); setBibInput('') }}
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
              </Button>
            </Link>
          )}
        </div>
      </div>

      {/* Gallery */}
      {isLoading && <PhotoSkeleton />}
      {error && (
        <p className="text-red-400 text-sm text-center py-12">Failed to load photos.</p>
      )}
      {data && data.photos.length === 0 && (
        <p className="text-gray-500 text-sm text-center py-12">
          {bib ? `No photos found for bib #${bib}.` : 'No photos in this event yet.'}
        </p>
      )}
      {data && data.photos.length > 0 && (
        <>
          <div className="masonry">
            {data.photos.map((photo) => (
              <PhotoCard key={photo.photo_id} photo={photo} eventId={id} />
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
    </div>
  )
}
