import { Link } from 'react-router-dom'
import { ArrowRight, CalendarDays, Lock, MapPin, Tag } from 'lucide-react'
import type { Event } from '../api/events'
import { formatMoney } from '../utils/money'

interface EventTileProps {
  event: Event
}

function formatEventDate(date: string) {
  return new Date(date).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

export default function EventTile({ event }: EventTileProps) {
  return (
    <Link
      to={`/events/${event.slug}`}
      className="group grid min-h-52 overflow-hidden rounded-lg border border-surface-700 bg-surface-900 transition-colors hover:border-content/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 sm:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]"
    >
      <div className="relative min-h-32 overflow-hidden bg-surface-800">
        <div className="absolute inset-0 bg-[linear-gradient(135deg,rgb(var(--s-800))_0%,rgb(var(--s-900))_48%,rgb(var(--s-700))_100%)]" />
        <div className="absolute inset-x-5 top-5 h-px bg-content/10" />
        <div className="absolute bottom-5 left-5 right-5">
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-content-muted">
            Race gallery
          </p>
          <p className="mt-2 max-w-44 text-2xl font-semibold leading-none text-content/90">
            {new Date(event.date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}
          </p>
        </div>
      </div>

      <div className="flex min-w-0 flex-col justify-between p-5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {event.is_password_protected && (
              <span className="inline-flex items-center gap-1 rounded border border-surface-700 px-2 py-1 text-xs text-content-muted">
                <Lock size={12} />
                Protected
              </span>
            )}
            <span className="inline-flex items-center gap-1 rounded border border-surface-700 px-2 py-1 text-xs text-content-muted">
              <Tag size={12} />
              {formatMoney(event.effective_photo_price_pence, event.currency)} each
            </span>
          </div>

          <h2 className="mt-4 truncate text-xl font-semibold leading-tight text-content transition-colors group-hover:text-sky-500">
            {event.name}
          </h2>

          <div className="mt-3 space-y-2 text-sm text-content-muted">
            <p className="flex items-center gap-2">
              <CalendarDays size={15} className="shrink-0" />
              <span>{formatEventDate(event.date)}</span>
            </p>
            {event.location && (
              <p className="flex min-w-0 items-center gap-2">
                <MapPin size={15} className="shrink-0" />
                <span className="truncate">{event.location}</span>
              </p>
            )}
          </div>
        </div>

        <div className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-content">
          Open gallery
          <ArrowRight size={16} className="transition-transform group-hover:translate-x-0.5" />
        </div>
      </div>
    </Link>
  )
}
