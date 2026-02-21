import { apiGet, apiPatch, apiPost } from './client'

export interface Event {
  id: number
  slug: string
  name: string
  date: string
  location?: string
  status: 'ACTIVE' | 'ARCHIVED'
  public_until?: string
  archive_after?: string
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

export const fetchEvents = () => apiGet<Event[]>('/events')

export const fetchPhotos = (
  eventId: number,
  page = 1,
  bib?: string,
  startTime?: string,
  endTime?: string,
) => {
  const params = new URLSearchParams({ page: String(page), page_size: '60' })
  if (bib) params.set('bib', bib)
  if (startTime) params.set('start_time', startTime)
  if (endTime) params.set('end_time', endTime)
  return apiGet<PhotoListResponse>(`/events/${eventId}/photos?${params}`)
}

export const createEvent = (body: { slug: string; name: string; date: string; location?: string }) =>
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
  }
) => apiPatch<EventCreatedOut>(`/admin/events/${eventId}`, body)

export const ingestPhotos = (eventId: number) =>
  apiPost<IngestResult>(`/admin/events/${eventId}/ingest`)

export const uploadBibTags = (eventId: number, tags: { photo_id: string; bib: string; confidence?: number }[]) =>
  apiPost<BibTagsResult>(`/admin/events/${eventId}/tags/bibs`, { tags })
