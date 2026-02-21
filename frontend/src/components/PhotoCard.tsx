import { useState } from 'react'
import { CheckCircle2, Maximize2, PlusCircle } from 'lucide-react'
import { useCartStore } from '../store/cart'
import { useIntersection } from '../hooks/useIntersection'
import type { Photo } from '../api/events'

interface PhotoCardProps {
  photo: Photo
  eventId: number
  onFullscreen?: (photo: Photo) => void
}

export default function PhotoCard({ photo, eventId, onFullscreen }: PhotoCardProps) {
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
      add({ photoId: photo.photo_id, eventId, proofUrl: photo.proof_url })
    }
  }

  function openFullscreen(e: React.MouseEvent) {
    e.stopPropagation()
    onFullscreen?.(photo)
  }

  return (
    <div
      ref={ref}
      className={`masonry-item group relative cursor-pointer rounded overflow-hidden bg-surface-900 transition-transform hover:scale-[1.01] ${
        inCart ? 'ring-2 ring-sky-500' : ''
      }`}
      onClick={toggle}
      role="button"
      tabIndex={0}
      aria-pressed={inCart}
      onKeyDown={(e) => e.key === 'Enter' && toggle(e as unknown as React.MouseEvent)}
    >
      {/* Lazy-load placeholder */}
      {!loaded && (
        <div className="w-full bg-surface-800 animate-pulse" style={{ minHeight: 160 }} />
      )}

      {/* Actual image — only mounted when in viewport */}
      {isVisible && (
        <img
          src={photo.proof_url}
          alt={`Photo ${photo.photo_id}`}
          loading="lazy"
          decoding="async"
          className={`w-full h-auto object-cover transition-opacity duration-300 ${
            loaded ? 'opacity-100' : 'opacity-0 absolute top-0 left-0'
          }`}
          onLoad={() => setLoaded(true)}
        />
      )}

      {/* Selection overlay */}
      <div
        className={`absolute inset-0 transition-all duration-200 ${
          inCart
            ? 'bg-sky-500/20'
            : 'bg-black/0 group-hover:bg-black/20'
        }`}
      />

      {/* Selection icon */}
      <button
        className="absolute top-2 right-2 transition-opacity duration-200 opacity-0 group-hover:opacity-100 focus:opacity-100"
        aria-hidden={!inCart}
        tabIndex={-1}
      >
        {inCart ? (
          <CheckCircle2 size={22} className="text-sky-400 drop-shadow" />
        ) : (
          <PlusCircle size={22} className="text-white drop-shadow" />
        )}
      </button>

      {/* Fullscreen action */}
      {onFullscreen && (
        <button
          onClick={openFullscreen}
          className="absolute top-2 left-2 transition-opacity duration-200 opacity-0 group-hover:opacity-100 focus:opacity-100 text-white"
          aria-label="Open fullscreen viewer"
        >
          <Maximize2 size={20} className="drop-shadow" />
        </button>
      )}
    </div>
  )
}
