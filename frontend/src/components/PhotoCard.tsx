import { useState } from 'react'
import { Check, Maximize2, Plus } from 'lucide-react'
import { useCartStore } from '../store/cart'
import { useIntersection } from '../hooks/useIntersection'
import type { Photo } from '../api/events'

interface PhotoCardProps {
  photo: Photo
  eventId: number
  eventSlug: string
  onFullscreen?: (photo: Photo) => void
}

export default function PhotoCard({ photo, eventId, eventSlug, onFullscreen }: PhotoCardProps) {
  const [ref, isVisible] = useIntersection({ rootMargin: '200px' })
  const [loaded, setLoaded] = useState(false)
  const inCart = useCartStore((s) => s.has(photo.photo_id))
  const add = useCartStore((s) => s.add)
  const remove = useCartStore((s) => s.remove)

  function toggle(e: React.MouseEvent) {
    e.stopPropagation()
    if (inCart) {
      remove(photo.photo_id)
    } else {
      add({ photoId: photo.photo_id, eventId, eventSlug, proofUrl: photo.proof_url })
    }
  }

  function openFullscreen(e: React.MouseEvent) {
    e.stopPropagation()
    onFullscreen?.(photo)
  }

  return (
    <div
      ref={ref}
      className={`masonry-item group relative cursor-pointer overflow-hidden rounded-lg bg-surface-900 transition-transform hover:scale-[1.01] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 ${
        inCart ? 'ring-2 ring-sky-500 ring-offset-2 ring-offset-surface-950' : ''
      }`}
      onClick={toggle}
      role="button"
      tabIndex={0}
      aria-pressed={inCart}
      onKeyDown={(e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return
        e.preventDefault()
        toggle(e as unknown as React.MouseEvent)
      }}
    >
      {!loaded && (
        <div className="w-full animate-pulse bg-surface-800" style={{ paddingBottom: '66.67%' }} />
      )}

      {isVisible && (
        <img
          src={photo.proof_url}
          alt={`Photo ${photo.photo_id}`}
          loading="lazy"
          decoding="async"
          className={`block h-auto w-full transition-opacity duration-300 ${
            loaded ? 'opacity-100' : 'absolute left-0 top-0 opacity-0'
          }`}
          onLoad={() => setLoaded(true)}
        />
      )}

      <div
        className={`absolute inset-0 transition-all duration-200 ${
          inCart ? 'bg-sky-500/15' : 'bg-black/0 group-hover:bg-black/15'
        }`}
      />

      <span
        className={`absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full border text-white shadow transition-opacity duration-200 ${
          inCart
            ? 'border-sky-400 bg-sky-500 opacity-100'
            : 'border-white/50 bg-black/45 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100'
        }`}
        aria-hidden
      >
        {inCart ? <Check size={17} /> : <Plus size={17} />}
      </span>

      {onFullscreen && (
        <button
          onClick={openFullscreen}
          className="absolute left-2 top-2 flex h-8 w-8 items-center justify-center rounded-full border border-white/50 bg-black/45 text-white opacity-0 shadow transition-opacity duration-200 hover:bg-black/65 focus:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white group-hover:opacity-100"
          aria-label="Open fullscreen viewer"
        >
          <Maximize2 size={16} />
        </button>
      )}

      <div className="pointer-events-none absolute bottom-2 left-1/2 -translate-x-1/2">
        <span className="select-none rounded bg-black/65 px-2 py-0.5 font-mono text-xs text-white">
          {photo.photo_id.split('-').slice(-1)[0]}
        </span>
      </div>
    </div>
  )
}
