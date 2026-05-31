import { useQuery } from '@tanstack/react-query'
import { ArrowRight, ImageOff, Loader2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { fetchEvents } from '../api/events'
import EventTile from '../components/EventTile'
import PublicPageShell from '../components/PublicPageShell'
import { Skeleton } from '../components/Skeleton'
import { useSiteConfig } from '../context/SiteConfig'

export default function EventList() {
  const { site_name, site_tagline } = useSiteConfig()
  const { data: events, isLoading, error } = useQuery({
    queryKey: ['events'],
    queryFn: fetchEvents,
  })

  const eventCount = events?.length ?? 0

  return (
    <PublicPageShell className="space-y-10">
      <section className="grid gap-8 lg:grid-cols-[minmax(0,0.82fr)_minmax(320px,0.48fr)] lg:items-end">
        <div className="max-w-3xl">
          <p className="text-sm font-medium uppercase tracking-[0.18em] text-content-muted">
            Event photo galleries
          </p>
          <h1 className="mt-4 text-4xl font-semibold leading-tight text-content sm:text-5xl">
            {site_name}
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-content-muted sm:text-lg">
            {site_tagline}
          </p>
          <p className="mt-5 max-w-2xl text-sm leading-6 text-content-muted">
            Find your race, browse proofs quickly, select the photos you want, and check out securely.
          </p>
        </div>

        <div className="rounded-lg border border-surface-700 bg-surface-900 p-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-3xl font-semibold text-content">{eventCount}</p>
              <p className="text-sm text-content-muted">
                active event{eventCount === 1 ? '' : 's'}
              </p>
            </div>
            {isLoading ? (
              <Loader2 size={22} className="animate-spin text-content-muted" />
            ) : (
              <ArrowRight size={22} className="text-content-muted" />
            )}
          </div>
          <p className="mt-4 text-sm leading-6 text-content-muted">
            Galleries are arranged by event date. Protected events require the event secret before photos load.
          </p>
        </div>
      </section>

      <section aria-labelledby="events-heading" className="space-y-5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 id="events-heading" className="text-2xl font-semibold text-content">
              Events
            </h2>
            <p className="mt-1 text-sm text-content-muted">
              Choose your gallery to start browsing.
            </p>
          </div>
          {events && events.length > 0 && (
            <Link
              to={`/events/${events[0].slug}`}
              className="inline-flex items-center gap-2 text-sm font-medium text-content hover:text-sky-500"
            >
              Latest gallery
              <ArrowRight size={16} />
            </Link>
          )}
        </div>

        {isLoading && (
          <div className="grid gap-4 lg:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-52 rounded-lg" />
            ))}
          </div>
        )}

        {error && (
          <div className="flex min-h-64 flex-col items-center justify-center gap-3 rounded-lg border border-surface-700 bg-surface-900 px-4 text-center text-content-muted">
            <ImageOff size={36} />
            <p className="font-medium text-content">Events could not be loaded</p>
            <p className="max-w-sm text-sm">Refresh the page or try again shortly.</p>
          </div>
        )}

        {events && events.length === 0 && (
          <div className="flex min-h-64 flex-col items-center justify-center gap-3 rounded-lg border border-surface-700 bg-surface-900 px-4 text-center text-content-muted">
            <ImageOff size={36} />
            <p className="font-medium text-content">No events are public yet</p>
            <p className="max-w-sm text-sm">Published event galleries will appear here.</p>
          </div>
        )}

        {events && events.length > 0 && (
          <div className="grid gap-4 lg:grid-cols-2">
            {events.map((event) => (
              <EventTile key={event.id} event={event} />
            ))}
          </div>
        )}
      </section>
    </PublicPageShell>
  )
}
