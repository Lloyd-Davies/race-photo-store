import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { CalendarDays, MapPin, ImageOff } from 'lucide-react'
import { fetchEvents, type Event } from '../api/events'
import { Skeleton } from '../components/Skeleton'

function EventCard({ event }: { event: Event }) {
  const date = new Date(event.date).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })

  return (
    <Link
      to={`/events/${event.id}`}
      className="group block bg-surface-900 border border-surface-700 rounded-xl overflow-hidden hover:border-sky-500/60 transition-colors"
    >
      {/* Colour band */}
      <div className="h-2 bg-sky-500 w-full" />

      <div className="p-5">
        <div className="flex items-start justify-between gap-2">
          <h2 className="font-semibold text-content group-hover:text-sky-500 transition-colors text-lg leading-tight">
            {event.name}
          </h2>
          {event.status === 'ARCHIVED' && (
            <span className="shrink-0 text-xs bg-surface-700 text-gray-400 rounded px-2 py-0.5">
              Archived
            </span>
          )}
        </div>

        <div className="mt-3 space-y-1 text-sm text-gray-400">
          <div className="flex items-center gap-1.5">
            <CalendarDays size={14} className="text-sky-500/70" />
            {date}
          </div>
          {event.location && (
            <div className="flex items-center gap-1.5">
              <MapPin size={14} className="text-sky-500/70" />
              {event.location}
            </div>
          )}
        </div>
      </div>
    </Link>
  )
}

export default function EventList() {
  const { data: events, isLoading, error } = useQuery({
    queryKey: ['events'],
    queryFn: fetchEvents,
  })

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-10">
      <h1 className="text-2xl font-bold text-content mb-8">Race Events</h1>

      {isLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-36 rounded-xl" />
          ))}
        </div>
      )}

      {error && (
        <div className="flex flex-col items-center gap-3 text-gray-500 py-20">
          <ImageOff size={40} />
          <p>Failed to load events. Please try again.</p>
        </div>
      )}

      {events && events.length === 0 && (
        <div className="flex flex-col items-center gap-3 text-gray-500 py-20">
          <ImageOff size={40} />
          <p>No events yet.</p>
        </div>
      )}

      {events && events.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {events.map((event) => (
            <EventCard key={event.id} event={event} />
          ))}
        </div>
      )}
    </div>
  )
}
