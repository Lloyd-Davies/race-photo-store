import { apiDelete, apiGet, apiPatch, apiPost } from './client'

export interface Event {
  id: number
  slug: string
  name: string
  date: string
  location?: string
  status: 'ACTIVE' | 'ARCHIVED'
  is_password_protected: boolean
  access_hint?: string
  public_until?: string
  archive_after?: string
  photo_price_pence?: number | null
  effective_photo_price_pence: number
  currency: string
  photo_count?: number
  order_count?: number
}

export interface Photo {
  photo_id: string
  proof_url: string
  captured_at?: string
}

export interface PhotoListResponse {
  photos: Photo[]
  total: number
  page: number
  pages: number
}

export interface EventUnlockResponse {
  access_token: string
  expires_at: string
}

export interface EventCreatedOut {
  id: number
  slug: string
}

export interface IngestResult {
  ingested: number
  skipped: number
}

export interface BibTagsResult {
  added: number
}

export interface DeleteEventResult {
  slug: string
  photos_deleted: number
  tags_deleted: number
  orders_affected: number
  files_deleted: boolean
}

export const fetchEvents = () => apiGet<Event[]>('/events')

export const fetchEvent = (eventRef: string) =>
  apiGet<Event>(`/events/${encodeURIComponent(eventRef)}`)

export const fetchAdminEvents = () => apiGet<Event[]>('/admin/events')

export const fetchPhotos = (
  eventRef: string,
  page = 1,
  bib?: string,
  startTime?: string,
  endTime?: string,
  eventAccessToken?: string,
) => {
  const params = new URLSearchParams({ page: String(page), page_size: '60' })
  if (bib) params.set('bib', bib)
  if (startTime) params.set('start_time', startTime)
  if (endTime) params.set('end_time', endTime)
  const headers: HeadersInit | undefined = eventAccessToken
    ? { 'X-Event-Access': eventAccessToken }
    : undefined
  return apiGet<PhotoListResponse>(`/events/${encodeURIComponent(eventRef)}/photos?${params}`, headers)
}

export const unlockEvent = (eventRef: string, secret: string) =>
  apiPost<EventUnlockResponse>(`/events/${encodeURIComponent(eventRef)}/unlock`, { secret })

export const createEvent = (body: {
  slug: string
  name: string
  date: string
  location?: string
  is_password_protected?: boolean
  access_secret?: string
  access_hint?: string
  photo_price_pence?: number
}) =>
  apiPost<EventCreatedOut>('/admin/events', body)

export const updateEvent = (
  eventId: number,
  body: {
    name?: string
    date?: string
    location?: string | null
    status?: 'ACTIVE' | 'ARCHIVED'
    public_until?: string | null
    archive_after?: string | null
    is_password_protected?: boolean
    access_secret?: string
    clear_access_secret?: boolean
    access_hint?: string | null
    photo_price_pence?: number | null
    clear_photo_price?: boolean
  }
) => apiPatch<EventCreatedOut>(`/admin/events/${eventId}`, body)

export const ingestPhotos = (eventId: number) =>
  apiPost<IngestResult>(`/admin/events/${eventId}/ingest`)

export const uploadBibTags = (eventId: number, tags: { photo_id: string; bib: string; confidence?: number }[]) =>
  apiPost<BibTagsResult>(`/admin/events/${eventId}/tags/bibs`, { tags })

export const listAdminEvents = () => apiGet<Event[]>('/admin/events')

export const deleteEvent = (
  eventId: number,
  opts: { deleteFiles?: boolean; force?: boolean } = {},
) => {
  const params = new URLSearchParams()
  if (opts.deleteFiles) params.set('delete_files', 'true')
  if (opts.force) params.set('force', 'true')
  const qs = params.toString()
  return apiDelete<DeleteEventResult>(`/admin/events/${eventId}${qs ? `?${qs}` : ''}`)
}
