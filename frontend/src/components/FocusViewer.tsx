import { useEffect, useRef, type PointerEvent } from 'react'
import { Link } from 'react-router-dom'
import { Check, ChevronLeft, ChevronRight, Loader2, Plus, ShoppingBag, X } from 'lucide-react'
import type { Photo } from '../api/events'
import { useCartStore } from '../store/cart'
import { clsx } from '../utils/clsx'
import { formatMoney } from '../utils/money'

export interface FocusViewerItem {
  photo: Photo
  page: number
  indexOnPage: number
  position: number
}

export type FocusViewerDirection = 'previous' | 'next'

interface FocusViewerProps {
  items: FocusViewerItem[]
  activePhotoId: string
  total: number
  eventId: number
  eventSlug: string
  photoPricePence: number
  currency: string
  hasPrevious: boolean
  hasNext: boolean
  loadingDirection: FocusViewerDirection | null
  loadError: string | null
  onPrevious: () => void
  onNext: () => void
  onSelectPhoto: (photoId: string) => void
  onClose: () => void
}

export default function FocusViewer({
  items,
  activePhotoId,
  total,
  eventId,
  eventSlug,
  photoPricePence,
  currency,
  hasPrevious,
  hasNext,
  loadingDirection,
  loadError,
  onPrevious,
  onNext,
  onSelectPhoto,
  onClose,
}: FocusViewerProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const activeThumbRef = useRef<HTMLButtonElement | null>(null)
  const pointerStartRef = useRef<{ x: number; y: number } | null>(null)
  const selectedItems = useCartStore((s) => s.items)
  const selectedEventId = useCartStore((s) => s.eventId)
  const isSelected = useCartStore((s) => s.has(activePhotoId))
  const add = useCartStore((s) => s.add)
  const remove = useCartStore((s) => s.remove)

  const activeIndex = items.findIndex((item) => item.photo.photo_id === activePhotoId)
  const activeItem = activeIndex >= 0 ? items[activeIndex] : null
  const selectedCount = selectedEventId === eventId ? selectedItems.length : 0
  const selectedTotal = selectedCount * photoPricePence

  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    requestAnimationFrame(() => dialogRef.current?.focus())

    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [])

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return
      }

      if (e.key === 'ArrowLeft' && hasPrevious) {
        e.preventDefault()
        onPrevious()
        return
      }

      if (e.key === 'ArrowRight' && hasNext) {
        e.preventDefault()
        onNext()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [hasNext, hasPrevious, onClose, onNext, onPrevious])

  useEffect(() => {
    const adjacentItems = [items[activeIndex - 1], items[activeIndex + 1]].filter(Boolean)
    adjacentItems.forEach((item) => {
      const preload = new Image()
      preload.src = item.photo.proof_url
    })
  }, [activeIndex, items])

  useEffect(() => {
    activeThumbRef.current?.scrollIntoView({ block: 'nearest', inline: 'center' })
  }, [activePhotoId])

  if (!activeItem) return null

  function toggleSelected() {
    if (!activeItem) return
    if (isSelected) {
      remove(activeItem.photo.photo_id)
      return
    }
    add({
      photoId: activeItem.photo.photo_id,
      eventId,
      eventSlug,
      proofUrl: activeItem.photo.proof_url,
    })
  }

  function handlePointerDown(e: PointerEvent<HTMLDivElement>) {
    if (e.pointerType === 'mouse' && e.button !== 0) return
    pointerStartRef.current = { x: e.clientX, y: e.clientY }
  }

  function handlePointerUp(e: PointerEvent<HTMLDivElement>) {
    const start = pointerStartRef.current
    pointerStartRef.current = null
    if (!start) return

    const deltaX = e.clientX - start.x
    const deltaY = e.clientY - start.y
    if (Math.abs(deltaX) < 48 || Math.abs(deltaX) < Math.abs(deltaY) * 1.35) return

    if (deltaX < 0 && hasNext) onNext()
    if (deltaX > 0 && hasPrevious) onPrevious()
  }

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="focus-viewer-title"
      tabIndex={-1}
      className="fixed inset-0 z-50 flex flex-col bg-black text-white focus:outline-none"
    >
      <h2 id="focus-viewer-title" className="sr-only">
        Photo {activeItem.position} of {total}
      </h2>

      <main className="mx-auto grid min-h-0 w-full max-w-7xl flex-1 grid-cols-[minmax(0,1fr)] gap-3 px-0 py-0 sm:grid-cols-[3rem_minmax(0,1fr)_3rem] sm:px-4 sm:py-3">
        <button
          type="button"
          onClick={onPrevious}
          disabled={!hasPrevious || loadingDirection === 'previous'}
          className="hidden h-full min-h-24 items-center justify-center rounded border border-white/10 bg-white/5 text-white transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white disabled:pointer-events-none disabled:opacity-35 sm:flex"
          aria-label="Previous photo"
        >
          {loadingDirection === 'previous' ? <Loader2 size={22} className="animate-spin" /> : <ChevronLeft size={27} />}
        </button>

        <div
          className="relative flex min-h-0 items-center justify-center overflow-hidden bg-white/[0.04] touch-pan-y sm:rounded"
          onPointerDown={handlePointerDown}
          onPointerUp={handlePointerUp}
        >
          <img
            src={activeItem.photo.proof_url}
            alt={`Photo ${activeItem.photo.photo_id}`}
            className="max-h-full max-w-full select-none object-contain"
            draggable={false}
          />

          <div
            className="absolute inset-x-3 top-3 z-10 flex items-start justify-between gap-3"
            style={{ top: 'calc(0.75rem + env(safe-area-inset-top, 0px))' }}
          >
            <div className="min-w-0 rounded bg-black/55 px-3 py-2 text-white shadow-lg backdrop-blur">
              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-white/55">
                Focus
              </p>
              <p className="mt-0.5 truncate text-sm font-semibold">
                Photo {activeItem.position} of {total}
              </p>
            </div>
            <button
              type="button"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={onClose}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded border border-white/20 bg-black/55 text-white shadow-lg backdrop-blur transition-colors hover:bg-black/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
              aria-label="Close focus viewer"
            >
              <X size={21} />
            </button>
          </div>

          <div className="absolute inset-x-3 top-1/2 z-10 flex -translate-y-1/2 items-center justify-between sm:hidden">
            <button
              type="button"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={onPrevious}
              disabled={!hasPrevious || loadingDirection === 'previous'}
              className="flex h-10 w-10 items-center justify-center rounded border border-white/20 bg-black/45 text-white backdrop-blur transition-colors hover:bg-black/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white disabled:pointer-events-none disabled:opacity-35"
              aria-label="Previous photo"
            >
              {loadingDirection === 'previous' ? <Loader2 size={18} className="animate-spin" /> : <ChevronLeft size={23} />}
            </button>
            <button
              type="button"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={onNext}
              disabled={!hasNext || loadingDirection === 'next'}
              className="flex h-10 w-10 items-center justify-center rounded border border-white/20 bg-black/45 text-white backdrop-blur transition-colors hover:bg-black/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white disabled:pointer-events-none disabled:opacity-35"
              aria-label="Next photo"
            >
              {loadingDirection === 'next' ? <Loader2 size={18} className="animate-spin" /> : <ChevronRight size={23} />}
            </button>
          </div>
        </div>

        <button
          type="button"
          onClick={onNext}
          disabled={!hasNext || loadingDirection === 'next'}
          className="hidden h-full min-h-24 items-center justify-center rounded border border-white/10 bg-white/5 text-white transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white disabled:pointer-events-none disabled:opacity-35 sm:flex"
          aria-label="Next photo"
        >
          {loadingDirection === 'next' ? <Loader2 size={22} className="animate-spin" /> : <ChevronRight size={27} />}
        </button>
      </main>

      <footer
        className="shrink-0 border-t border-white/10 bg-black/95 px-4 py-3"
        style={{ paddingBottom: 'calc(0.75rem + env(safe-area-inset-bottom, 0px))' }}
      >
        <div className="mx-auto max-w-7xl space-y-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <p className="truncate font-mono text-sm text-white">{activeItem.photo.photo_id}</p>
              <p className="mt-1 text-sm text-white/60">
                {items.length} loaded in Focus
                {loadError ? <span className="text-red-300"> - {loadError}</span> : null}
              </p>
            </div>

            <div className="grid min-w-0 gap-2 sm:grid-cols-2 lg:flex lg:items-center">
              <button
                type="button"
                onClick={toggleSelected}
                className={clsx(
                  'inline-flex min-h-11 items-center justify-center gap-2 rounded px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white',
                  isSelected
                    ? 'border border-sky-400 bg-sky-500 text-white hover:bg-sky-600'
                    : 'border border-white/15 bg-white/10 text-white hover:bg-white/20',
                )}
                aria-label={isSelected ? 'Remove photo from selected photos' : 'Select photo'}
              >
                {isSelected ? <Check size={17} /> : <Plus size={17} />}
                {isSelected ? 'Selected' : 'Select photo'}
              </button>

              {selectedCount > 0 ? (
                <Link
                  to="/cart"
                  className="inline-flex min-h-11 items-center justify-center gap-2 rounded bg-white px-4 py-2 text-sm font-semibold text-black transition-colors hover:bg-white/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                >
                  <ShoppingBag size={17} />
                  <span className="truncate">
                    {selectedCount} selected - {formatMoney(selectedTotal, currency)}
                  </span>
                </Link>
              ) : (
                <span className="inline-flex min-h-11 items-center justify-center gap-2 rounded border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-white/40">
                  <ShoppingBag size={17} />
                  No selected photos
                </span>
              )}
            </div>
          </div>

          <div className="flex gap-2 overflow-x-auto pb-1" aria-label="Loaded photo filmstrip">
            {items.map((item) => {
              const active = item.photo.photo_id === activePhotoId
              return (
                <button
                  key={item.photo.photo_id}
                  type="button"
                  ref={active ? activeThumbRef : undefined}
                  onClick={() => onSelectPhoto(item.photo.photo_id)}
                  className={clsx(
                    'relative h-16 w-16 shrink-0 overflow-hidden rounded border bg-white/5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white',
                    active ? 'border-sky-400' : 'border-white/15 hover:border-white/45',
                  )}
                  aria-label={`Open photo ${item.position}`}
                  aria-current={active ? 'true' : undefined}
                >
                  <img
                    src={item.photo.proof_url}
                    alt=""
                    className="h-full w-full object-cover"
                    loading="lazy"
                    decoding="async"
                  />
                  <span className="absolute bottom-1 left-1 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-white">
                    {item.position}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      </footer>
    </div>
  )
}
