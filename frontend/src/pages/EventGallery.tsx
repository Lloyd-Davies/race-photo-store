import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock3,
  ImageOff,
  Lock,
  MapPin,
  Search,
  ShoppingBag,
  SlidersHorizontal,
  Tag,
  X,
} from 'lucide-react'
import { fetchEvent, fetchPhotos, unlockEvent, PHOTO_PAGE_SIZE } from '../api/events'
import type { Photo } from '../api/events'
import Button from '../components/Button'
import FocusViewer from '../components/FocusViewer'
import type { FocusViewerDirection, FocusViewerItem } from '../components/FocusViewer'
import PhotoCard from '../components/PhotoCard'
import PublicPageShell from '../components/PublicPageShell'
import { PhotoSkeleton } from '../components/Skeleton'
import { useCartStore } from '../store/cart'
import { formatMoney } from '../utils/money'

function formatEventDate(date?: string) {
  if (!date) return 'Date to be confirmed'
  return new Date(date).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

interface MetadataPillProps {
  icon: ReactNode
  label: string
}

function MetadataPill({ icon, label }: MetadataPillProps) {
  return (
    <span className="inline-flex min-h-9 max-w-full items-center gap-2 rounded border border-surface-700 bg-surface-900 px-3 py-1.5 text-sm text-content-muted">
      <span className="shrink-0 text-content-muted">{icon}</span>
      <span className="truncate">{label}</span>
    </span>
  )
}

interface FilterPillProps {
  label: string
  onClear: () => void
}

function FilterPill({ label, onClear }: FilterPillProps) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded border border-surface-700 bg-surface-900 px-2.5 py-1 text-xs text-content">
      {label}
      <button
        type="button"
        onClick={onClear}
        className="rounded text-content-muted transition-colors hover:text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
        aria-label={`Clear ${label} filter`}
      >
        <X size={13} />
      </button>
    </span>
  )
}

function toViewerItems(photos: Photo[], page: number): FocusViewerItem[] {
  return photos.map((photo, indexOnPage) => ({
    photo,
    page,
    indexOnPage,
    position: (page - 1) * PHOTO_PAGE_SIZE + indexOnPage + 1,
  }))
}

function mergeViewerItems(currentItems: FocusViewerItem[], nextItems: FocusViewerItem[]) {
  const byId = new Map<string, FocusViewerItem>()
  currentItems.forEach((item) => byId.set(item.photo.photo_id, item))
  nextItems.forEach((item) => byId.set(item.photo.photo_id, item))

  return Array.from(byId.values()).sort((a, b) => {
    if (a.page !== b.page) return a.page - b.page
    return a.indexOnPage - b.indexOnPage
  })
}

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
  const [activePhotoId, setActivePhotoId] = useState<string | null>(null)
  const [viewerItems, setViewerItems] = useState<FocusViewerItem[]>([])
  const [viewerLoadedPages, setViewerLoadedPages] = useState<Set<number>>(() => new Set())
  const [viewerLoadingDirection, setViewerLoadingDirection] = useState<FocusViewerDirection | null>(null)
  const [viewerLoadError, setViewerLoadError] = useState<string | null>(null)
  const viewerOriginRef = useRef<HTMLElement | null>(null)
  const [eventAccessToken, setEventAccessToken] = useState<string | null>(null)
  const [unlockSecret, setUnlockSecret] = useState('')
  const [unlockError, setUnlockError] = useState<string | null>(null)
  const [unlocking, setUnlocking] = useState(false)
  const selectedItems = useCartStore((s) => s.items)
  const selectedEventId = useCartStore((s) => s.eventId)

  const { data: event, isLoading: eventLoading, error: eventError } = useQuery({
    queryKey: ['event', eventRef],
    queryFn: () => fetchEvent(eventRef as string),
    enabled: !!eventRef,
  })

  const isEventLocked = !!event?.is_password_protected
  const selectedCount = event && selectedEventId === event.id ? selectedItems.length : 0
  const selectedTotal = event ? selectedCount * event.effective_photo_price_pence : 0
  const hasActiveFilters = !!(bib || startTime || endTime)

  useEffect(() => {
    if (!event || !eventRef || eventRef === event.slug) return
    navigate(`/events/${event.slug}`, { replace: true })
  }, [event, eventRef, navigate])

  const eventAccessKey = useMemo(() => event ? `eventAccess:${event.id}` : null, [event])

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

  async function handleUnlock(e: FormEvent) {
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

  function handleFilterSubmit(e: FormEvent) {
    e.preventDefault()
    setBib(bibInput.trim() || undefined)
    setStartTime(startTimeInput || undefined)
    setEndTime(endTimeInput || undefined)
    setPage(1)
  }

  function clearFilters() {
    setBib(undefined)
    setStartTime(undefined)
    setEndTime(undefined)
    setBibInput('')
    setStartTimeInput('')
    setEndTimeInput('')
    setPage(1)
  }

  const activeViewerIndex = viewerItems.findIndex((item) => item.photo.photo_id === activePhotoId)
  const activeViewerItem = activeViewerIndex >= 0 ? viewerItems[activeViewerIndex] : null
  const viewerPageNumbers = useMemo(() => Array.from(viewerLoadedPages), [viewerLoadedPages])
  const minViewerPage = viewerPageNumbers.length ? Math.min(...viewerPageNumbers) : page
  const maxViewerPage = viewerPageNumbers.length ? Math.max(...viewerPageNumbers) : page
  const totalViewerPages = data?.pages ?? 0
  const hasPreviousViewer = activeViewerIndex > 0 || minViewerPage > 1
  const hasNextViewer = activeViewerIndex >= 0 && (activeViewerIndex < viewerItems.length - 1 || maxViewerPage < totalViewerPages)

  const loadViewerPage = useCallback(
    async (targetPage: number, direction: FocusViewerDirection) => {
      if (!event?.slug || !data || targetPage < 1 || targetPage > data.pages) return []

      if (viewerLoadedPages.has(targetPage)) {
        return viewerItems.filter((item) => item.page === targetPage)
      }

      setViewerLoadingDirection(direction)
      setViewerLoadError(null)
      try {
        const response = await fetchPhotos(
          event.slug,
          targetPage,
          bib,
          startTime,
          endTime,
          eventAccessToken ?? undefined,
        )
        const nextItems = toViewerItems(response.photos, targetPage)
        setViewerItems((currentItems) => mergeViewerItems(currentItems, nextItems))
        setViewerLoadedPages((currentPages) => {
          const nextPages = new Set(currentPages)
          nextPages.add(targetPage)
          return nextPages
        })
        return nextItems
      } catch {
        setViewerLoadError('Could not load more photos.')
        return []
      } finally {
        setViewerLoadingDirection(null)
      }
    },
    [bib, data, endTime, event?.slug, eventAccessToken, startTime, viewerItems, viewerLoadedPages],
  )

  function handleOpenViewer(photo: Photo) {
    if (!data) return
    viewerOriginRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setViewerItems(toViewerItems(data.photos, data.page))
    setViewerLoadedPages(new Set([data.page]))
    setViewerLoadError(null)
    setActivePhotoId(photo.photo_id)
  }

  function handleCloseViewer() {
    setActivePhotoId(null)
    setViewerItems([])
    setViewerLoadedPages(new Set())
    setViewerLoadingDirection(null)
    setViewerLoadError(null)
    requestAnimationFrame(() => viewerOriginRef.current?.focus())
  }

  async function handleViewerPrevious() {
    if (viewerLoadingDirection) return
    if (activeViewerIndex > 0) {
      setActivePhotoId(viewerItems[activeViewerIndex - 1].photo.photo_id)
      return
    }
    if (minViewerPage <= 1) return

    const previousItems = await loadViewerPage(minViewerPage - 1, 'previous')
    if (previousItems.length > 0) {
      setActivePhotoId(previousItems[previousItems.length - 1].photo.photo_id)
    }
  }

  async function handleViewerNext() {
    if (viewerLoadingDirection) return
    if (activeViewerIndex >= 0 && activeViewerIndex < viewerItems.length - 1) {
      setActivePhotoId(viewerItems[activeViewerIndex + 1].photo.photo_id)
      return
    }
    if (!totalViewerPages || maxViewerPage >= totalViewerPages) return

    const nextItems = await loadViewerPage(maxViewerPage + 1, 'next')
    if (nextItems.length > 0) {
      setActivePhotoId(nextItems[0].photo.photo_id)
    }
  }

  return (
    <PublicPageShell className="space-y-8">
      <nav className="flex min-w-0 items-center gap-3 text-sm" aria-label="Breadcrumb">
        <Link
          to="/"
          className="inline-flex shrink-0 items-center gap-1.5 rounded py-1 text-content-muted transition-colors hover:text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
        >
          <ArrowLeft size={16} />
          Events
        </Link>
        <span className="text-surface-600">/</span>
        <span className="min-w-0 truncate font-medium text-content">
          {event?.name ?? 'Gallery'}
        </span>
      </nav>

      {eventError && (
        <div className="flex min-h-80 flex-col items-center justify-center gap-3 rounded-lg border border-surface-700 bg-surface-900 px-4 text-center text-content-muted">
          <ImageOff size={38} />
          <p className="font-medium text-content">Event not found</p>
          <p className="max-w-sm text-sm">
            This gallery may have been archived or the link may no longer be available.
          </p>
          <Link to="/" className="mt-2 text-sm font-medium text-sky-500 hover:text-sky-400">
            Back to events
          </Link>
        </div>
      )}

      {!eventError && (
        <section className="space-y-5 rounded-lg border border-surface-700 bg-surface-900 p-5 sm:p-6">
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
            <div className="min-w-0">
              <p className="text-sm font-medium uppercase tracking-[0.16em] text-content-muted">
                Event gallery
              </p>
              <h1 className="mt-3 text-3xl font-semibold leading-tight text-content sm:text-4xl">
                {event?.name ?? 'Loading gallery'}
              </h1>
              <div className="mt-4 flex flex-wrap gap-2">
                <MetadataPill icon={<CalendarDays size={15} />} label={formatEventDate(event?.date)} />
                {event?.location && (
                  <MetadataPill icon={<MapPin size={15} />} label={event.location} />
                )}
                <MetadataPill
                  icon={<Tag size={15} />}
                  label={event ? `${formatMoney(event.effective_photo_price_pence, event.currency)} each` : 'Price loading'}
                />
                <MetadataPill
                  icon={<Lock size={15} />}
                  label={event?.is_password_protected ? 'Protected event' : 'Open gallery'}
                />
              </div>
            </div>

            <div className="grid min-w-0 grid-cols-2 gap-3 sm:grid-cols-3 lg:w-full lg:max-w-sm">
              <div className="rounded border border-surface-700 bg-surface-950 p-3">
                <p className="text-2xl font-semibold text-content">{data?.total ?? event?.photo_count ?? '-'}</p>
                <p className="mt-1 text-xs text-content-muted">Photos</p>
              </div>
              <div className="rounded border border-surface-700 bg-surface-950 p-3">
                <p className="text-2xl font-semibold text-content">{selectedCount}</p>
                <p className="mt-1 text-xs text-content-muted">Selected</p>
              </div>
              <div className="col-span-2 rounded border border-surface-700 bg-surface-950 p-3 sm:col-span-1">
                <p className="truncate text-2xl font-semibold text-content">
                  {event ? formatMoney(selectedTotal, event.currency) : '-'}
                </p>
                <p className="mt-1 text-xs text-content-muted">Total</p>
              </div>
            </div>
          </div>

          {selectedCount > 0 && (
            <div className="flex flex-col gap-3 rounded border border-sky-500/30 bg-sky-500/10 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded bg-sky-500 text-white">
                  <ShoppingBag size={18} />
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-content">
                    {selectedCount} selected photo{selectedCount === 1 ? '' : 's'}
                  </p>
                  <p className="text-sm text-content-muted">
                    {event && formatMoney(selectedTotal, event.currency)}
                  </p>
                </div>
              </div>
              <Link
                to="/cart"
                className="inline-flex min-h-10 items-center justify-center rounded bg-sky-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-sky-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
              >
                Review selected
              </Link>
            </div>
          )}
        </section>
      )}

      {!eventError && isEventLocked && !eventAccessToken && (
        <section className="mx-auto max-w-lg rounded-lg border border-surface-700 bg-surface-900 p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded bg-surface-800 text-content">
              <Lock size={18} />
            </span>
            <div>
              <h2 className="font-semibold text-content">This event is protected</h2>
              <p className="mt-1 text-sm leading-6 text-content-muted">
                Enter the event secret to view and select photos.
              </p>
              {event?.access_hint && (
                <p className="mt-2 text-sm text-content-muted">Hint: {event.access_hint}</p>
              )}
            </div>
          </div>

          <form onSubmit={handleUnlock} className="mt-5 space-y-3">
            <label className="block text-sm font-medium text-content" htmlFor="event-secret">
              Event secret
            </label>
            <input
              id="event-secret"
              type="password"
              value={unlockSecret}
              onChange={(e) => setUnlockSecret(e.target.value)}
              placeholder="Enter event secret"
              className="min-h-11 w-full rounded border border-surface-600 bg-surface-800 px-3 py-2 text-sm text-content placeholder:text-content-muted focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
            {unlockError && <p className="text-sm text-red-400">{unlockError}</p>}
            <Button type="submit" loading={unlocking} className="min-h-11 w-full sm:w-auto">
              Unlock event
            </Button>
          </form>
        </section>
      )}

      {!eventError && (!isEventLocked || !!eventAccessToken) && (
        <section className="space-y-5">
          <div className="rounded-lg border border-surface-700 bg-surface-900 p-4">
            <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-content">
              <SlidersHorizontal size={17} />
              Find photos
            </div>
            <form onSubmit={handleFilterSubmit} className="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,11rem)_minmax(0,11rem)_auto_auto] lg:items-end">
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.12em] text-content-muted">
                  Bib number
                </span>
                <div className="relative">
                  <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-content-muted" />
                  <input
                    type="text"
                    value={bibInput}
                    onChange={(e) => setBibInput(e.target.value)}
                    placeholder="Search bib"
                    className="min-h-11 w-full rounded border border-surface-600 bg-surface-800 px-9 py-2 text-sm text-content placeholder:text-content-muted focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.12em] text-content-muted">
                  Start time
                </span>
                <div className="relative">
                  <Clock3 size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-content-muted" />
                  <input
                    type="time"
                    value={startTimeInput}
                    onChange={(e) => setStartTimeInput(e.target.value)}
                    className="min-h-11 w-full rounded border border-surface-600 bg-surface-800 px-9 py-2 text-sm text-content focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.12em] text-content-muted">
                  End time
                </span>
                <div className="relative">
                  <Clock3 size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-content-muted" />
                  <input
                    type="time"
                    value={endTimeInput}
                    onChange={(e) => setEndTimeInput(e.target.value)}
                    className="min-h-11 w-full rounded border border-surface-600 bg-surface-800 px-9 py-2 text-sm text-content focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
              </label>

              <Button type="submit" className="min-h-11 w-full lg:w-auto">
                Apply
              </Button>
              <Button
                type="button"
                variant="secondary"
                className="min-h-11 w-full lg:w-auto"
                onClick={clearFilters}
                disabled={!hasActiveFilters && !bibInput && !startTimeInput && !endTimeInput}
              >
                Clear
              </Button>
            </form>

            {hasActiveFilters && (
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium uppercase tracking-[0.12em] text-content-muted">
                  Active
                </span>
                {bib && (
                  <FilterPill
                    label={`Bib ${bib}`}
                    onClear={() => {
                      setBib(undefined)
                      setBibInput('')
                      setPage(1)
                    }}
                  />
                )}
                {startTime && (
                  <FilterPill
                    label={`From ${startTime}`}
                    onClear={() => {
                      setStartTime(undefined)
                      setStartTimeInput('')
                      setPage(1)
                    }}
                  />
                )}
                {endTime && (
                  <FilterPill
                    label={`Until ${endTime}`}
                    onClear={() => {
                      setEndTime(undefined)
                      setEndTimeInput('')
                      setPage(1)
                    }}
                  />
                )}
              </div>
            )}
          </div>

          {(eventLoading || photosLoading) && <PhotoSkeleton />}

          {photosError && !photosLoading && (
            <div className="flex min-h-72 flex-col items-center justify-center gap-3 rounded-lg border border-surface-700 bg-surface-900 px-4 text-center text-content-muted">
              <ImageOff size={36} />
              <p className="font-medium text-content">Photos could not be loaded</p>
              <p className="max-w-sm text-sm">Refresh the page or adjust your filters.</p>
            </div>
          )}

          {data && data.photos.length === 0 && !photosLoading && (
            <div className="flex min-h-72 flex-col items-center justify-center gap-3 rounded-lg border border-surface-700 bg-surface-900 px-4 text-center text-content-muted">
              <ImageOff size={36} />
              <p className="font-medium text-content">
                {hasActiveFilters ? 'No photos match these filters' : 'No photos yet'}
              </p>
              <p className="max-w-sm text-sm">
                {hasActiveFilters
                  ? 'Clear the filters or widen the time range to keep searching.'
                  : 'Photos will appear here once this event has been processed.'}
              </p>
              {hasActiveFilters && (
                <Button type="button" variant="secondary" onClick={clearFilters}>
                  Clear filters
                </Button>
              )}
            </div>
          )}

          {data && data.photos.length > 0 && event && (
            <>
              <div className="masonry">
                {data.photos.map((photo) => (
                  <PhotoCard
                    key={photo.photo_id}
                    photo={photo}
                    eventId={event.id}
                    eventSlug={event.slug}
                    onFullscreen={handleOpenViewer}
                  />
                ))}
              </div>

              {data.pages > 1 && (
                <div className="flex flex-col gap-3 rounded-lg border border-surface-700 bg-surface-900 p-3 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-center text-sm text-content-muted sm:text-left">
                    Page <span className="font-medium text-content">{data.page}</span> of{' '}
                    <span className="font-medium text-content">{data.pages}</span>
                    <span className="hidden sm:inline"> - {data.total} photos</span>
                  </p>
                  <div className="grid grid-cols-2 gap-2 sm:flex">
                    <Button
                      variant="secondary"
                      disabled={page === 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      className="min-h-10"
                    >
                      <ChevronLeft size={16} />
                      Previous
                    </Button>
                    <Button
                      variant="secondary"
                      disabled={page === data.pages}
                      onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                      className="min-h-10"
                    >
                      Next
                      <ChevronRight size={16} />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      )}

      {activePhotoId && activeViewerItem && event && data && (
        <FocusViewer
          items={viewerItems}
          activePhotoId={activePhotoId}
          total={data.total}
          eventId={event.id}
          eventSlug={event.slug}
          photoPricePence={event.effective_photo_price_pence}
          currency={event.currency}
          hasPrevious={hasPreviousViewer}
          hasNext={hasNextViewer}
          loadingDirection={viewerLoadingDirection}
          loadError={viewerLoadError}
          onPrevious={handleViewerPrevious}
          onNext={handleViewerNext}
          onSelectPhoto={setActivePhotoId}
          onClose={handleCloseViewer}
        />
      )}
    </PublicPageShell>
  )
}
