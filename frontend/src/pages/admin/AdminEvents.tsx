import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, UploadCloud, CalendarDays, MapPin, Pencil, Trash2 } from 'lucide-react'
import { fetchEvents, createEvent, updateEvent, deleteEvent, type Event } from '../../api/events'
import Button from '../../components/Button'
import { Skeleton } from '../../components/Skeleton'

interface CreateForm {
  slug: string
  name: string
  date: string
  location: string
}

const EMPTY_FORM: CreateForm = { slug: '', name: '', date: '', location: '' }

interface EditForm {
  name: string
  date: string
  location: string
  status: Event['status']
}

function slugify(v: string) {
  return v
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

export default function AdminEvents() {
  const qc = useQueryClient()
  const [form, setForm] = useState<CreateForm>(EMPTY_FORM)
  const [errors, setErrors] = useState<Partial<CreateForm>>({})
  const [showForm, setShowForm] = useState(false)
  const [editingEventId, setEditingEventId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<EditForm | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Event | null>(null)
  const [deleteFiles, setDeleteFiles] = useState(false)
  const [forceInfo, setForceInfo] = useState<{ ordersAffected: number } | null>(null)
  const [forceConfirmed, setForceConfirmed] = useState(false)

  const { data: events, isLoading } = useQuery({
    queryKey: ['events'],
    queryFn: fetchEvents,
  })

  const createMut = useMutation({
    mutationFn: () =>
      createEvent({
        slug: form.slug,
        name: form.name,
        date: form.date,
        location: form.location || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['events'] })
      setForm(EMPTY_FORM)
      setShowForm(false)
    },
  })

  const updateMut = useMutation({
    mutationFn: ({ eventId, body }: { eventId: number; body: EditForm }) =>
      updateEvent(eventId, {
        name: body.name,
        date: body.date,
        location: body.location || undefined,
        status: body.status,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['events'] })
      setEditingEventId(null)
      setEditForm(null)
    },
  })

  const deleteMut = useMutation({
    mutationFn: ({ eventId, opts }: { eventId: number; opts: { deleteFiles: boolean; force: boolean } }) =>
      deleteEvent(eventId, opts),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['events'] })
      closeDeleteModal()
    },
    onError: (err: Error) => {
      let ordersAffected: number | null = null
      const match = err.message.match(/^409: (.+)$/)
      if (match) {
        try {
          const body = JSON.parse(match[1])
          const n = body?.detail?.orders_affected ?? body?.orders_affected
          if (typeof n === 'number' && Number.isFinite(n)) {
            ordersAffected = n
          }
        } catch {
          // non-JSON 409 — leave ordersAffected null
        }
      }
      if (ordersAffected !== null) {
        setForceInfo({ ordersAffected })
      }
    },
  })

  function openDeleteModal(event: Event) {
    setDeleteTarget(event)
    setDeleteFiles(false)
    setForceInfo(null)
    setForceConfirmed(false)
    deleteMut.reset()
  }

  function closeDeleteModal() {
    setDeleteTarget(null)
    setDeleteFiles(false)
    setForceInfo(null)
    setForceConfirmed(false)
    deleteMut.reset()
  }

  function handleDelete() {
    if (!deleteTarget) return
    deleteMut.mutate({ eventId: deleteTarget.id, opts: { deleteFiles, force: forceConfirmed } })
  }

  function handleField(field: keyof CreateForm, value: string) {
    setForm((prev) => {
      const next = { ...prev, [field]: value }
      // Auto-fill slug from name
      if (field === 'name' && !prev.slug) {
        next.slug = slugify(value)
      }
      return next
    })
    setErrors((prev) => ({ ...prev, [field]: undefined }))
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const errs: Partial<CreateForm> = {}
    if (!form.slug) errs.slug = 'Required'
    if (!form.name) errs.name = 'Required'
    if (!form.date) errs.date = 'Required'
    if (Object.keys(errs).length) { setErrors(errs); return }
    createMut.mutate()
  }

  function startEdit(event: Event) {
    setEditingEventId(event.id)
    setEditForm({
      name: event.name,
      date: event.date.slice(0, 10),
      location: event.location ?? '',
      status: event.status,
    })
  }

  function saveEdit(eventId: number) {
    if (!editForm || !editForm.name || !editForm.date) return
    updateMut.mutate({ eventId, body: editForm })
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-content">Events</h1>
        <Button size="sm" onClick={() => setShowForm((v) => !v)}>
          <Plus size={14} className="mr-1" />
          New event
        </Button>
      </div>

      {/* Create form */}
      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="bg-surface-800 border border-surface-600 rounded-xl p-6 mb-8 space-y-4"
        >
          <h2 className="font-semibold text-content text-sm mb-2">Create event</h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {(
              [
                { key: 'name', label: 'Event name', type: 'text', placeholder: 'Spring 10k 2025' },
                { key: 'slug', label: 'Slug', type: 'text', placeholder: 'spring-10k-2025' },
                { key: 'date', label: 'Date', type: 'date', placeholder: '' },
                { key: 'location', label: 'Location (optional)', type: 'text', placeholder: 'London, UK' },
              ] as const
            ).map(({ key, label, type, placeholder }) => (
              <div key={key}>
                <label className="block text-xs text-gray-400 mb-1">{label}</label>
                <input
                  type={type}
                  value={form[key]}
                  onChange={(e) => handleField(key, e.target.value)}
                  placeholder={placeholder}
                  className="w-full bg-surface-900 border border-surface-600 rounded-md text-sm text-content px-3 py-2 focus:outline-none focus:ring-1 focus:ring-sky-500 placeholder:text-content-muted"
                />
                {errors[key] && (
                  <p className="text-xs text-red-400 mt-1">{errors[key]}</p>
                )}
              </div>
            ))}
          </div>

          {createMut.error && (
            <p className="text-xs text-red-400">
              {(createMut.error as Error).message ?? 'Failed to create event.'}
            </p>
          )}

          <div className="flex gap-3 pt-2">
            <Button type="submit" size="sm" loading={createMut.isPending}>
              Create
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => { setShowForm(false); setForm(EMPTY_FORM); setErrors({}) }}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}

      {/* Event list */}
      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 rounded-xl" />
          ))}
        </div>
      )}

      {events && events.length === 0 && (
        <p className="text-sm text-gray-500 text-center py-12">
          No events yet. Create one above.
        </p>
      )}

      {events && events.length > 0 && (
        <div className="space-y-3">
          {events.map((event: Event) => (
            <div
              key={event.id}
              className="bg-surface-900 border border-surface-700 rounded-xl p-4 flex items-center gap-4"
            >
              <div className="flex-1 min-w-0">
                {editingEventId === event.id && editForm ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <input
                      value={editForm.name}
                      onChange={(e) => setEditForm((prev) => (prev ? { ...prev, name: e.target.value } : prev))}
                      className="bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-3 py-2"
                    />
                    <input
                      type="date"
                      value={editForm.date}
                      onChange={(e) => setEditForm((prev) => (prev ? { ...prev, date: e.target.value } : prev))}
                      className="bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-3 py-2"
                    />
                    <input
                      value={editForm.location}
                      onChange={(e) => setEditForm((prev) => (prev ? { ...prev, location: e.target.value } : prev))}
                      placeholder="Location"
                      className="bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-3 py-2"
                    />
                    <select
                      value={editForm.status}
                      onChange={(e) => setEditForm((prev) => (prev ? { ...prev, status: e.target.value as Event['status'] } : prev))}
                      className="bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-3 py-2"
                    >
                      <option value="ACTIVE">ACTIVE</option>
                      <option value="ARCHIVED">ARCHIVED</option>
                    </select>
                  </div>
                ) : (
                  <>
                    <p className="font-medium text-gray-100 truncate">{event.name}</p>
                    <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                      <span className="flex items-center gap-1">
                        <CalendarDays size={11} />
                        {new Date(event.date).toLocaleDateString('en-GB')}
                      </span>
                      {event.location && (
                        <span className="flex items-center gap-1">
                          <MapPin size={11} />
                          {event.location}
                        </span>
                      )}
                      <code className="text-surface-500">{event.slug}</code>
                    </div>
                  </>
                )}
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <span
                  className={`text-xs rounded px-2 py-0.5 ${
                    event.status === 'ACTIVE'
                      ? 'bg-green-500/10 text-green-400 border border-green-500/20'
                      : 'bg-surface-700 text-gray-400'
                  }`}
                >
                  {event.status}
                </span>
                {editingEventId === event.id ? (
                  <>
                    <Button
                      size="sm"
                      onClick={() => saveEdit(event.id)}
                      loading={updateMut.isPending}
                    >
                      Save
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setEditingEventId(null)
                        setEditForm(null)
                      }}
                    >
                      Cancel
                    </Button>
                  </>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => startEdit(event)}
                  >
                    <Pencil size={14} className="mr-1" />
                    Edit
                  </Button>
                )}
                <Link to={`/admin/events/${event.id}/ingest`}>
                  <Button variant="secondary" size="sm">
                    <UploadCloud size={14} className="mr-1" />
                    Ingest
                  </Button>
                </Link>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-red-400 hover:text-red-300"
                  onClick={() => openDeleteModal(event)}
                  aria-label="Delete event"
                >
                  <Trash2 size={14} />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
      {/* Delete confirmation modal */}
      {deleteTarget && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-modal-title"
          onKeyDown={(e) => { if (e.key === 'Escape') closeDeleteModal() }}
        >
          <div className="bg-surface-800 border border-surface-600 rounded-xl p-6 max-w-md w-full space-y-4">
            <h2 id="delete-modal-title" className="font-semibold text-content">Delete event</h2>
            <p className="text-sm text-gray-300">
              Delete{' '}
              <span className="font-medium text-white">{deleteTarget.name}</span>? All photos and
              tag data will be permanently removed.
            </p>

            <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={deleteFiles}
                onChange={(e) => setDeleteFiles(e.target.checked)}
              />
              Delete files from disk
            </label>

            {forceInfo && (
              <div className="bg-red-950/50 border border-red-700/40 rounded-lg p-3 space-y-2">
                <p className="text-xs text-red-300">
                  ⚠ {forceInfo.ordersAffected} paid order
                  {forceInfo.ordersAffected !== 1 ? 's' : ''} reference this event.
                </p>
                <label className="flex items-center gap-2 text-xs text-red-300 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={forceConfirmed}
                    onChange={(e) => setForceConfirmed(e.target.checked)}
                  />
                  I understand — force delete anyway
                </label>
              </div>
            )}

            {deleteMut.error && (() => {
              const is409 = (deleteMut.error as Error).message?.startsWith('409:')
              // Suppress 409 errors when forceInfo is showing the confirmation UI;
              // always show non-409 errors (e.g. network failures after a force attempt)
              if (forceInfo && is409) return null
              return (
                <p className="text-xs text-red-400">
                  {(deleteMut.error as Error).message}
                </p>
              )
            })()}

            <div className="flex gap-3 pt-2">
              <Button
                variant="danger"
                size="sm"
                onClick={handleDelete}
                loading={deleteMut.isPending}
                disabled={!!forceInfo && !forceConfirmed}
              >
                Delete
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={closeDeleteModal}
                disabled={deleteMut.isPending}
              >
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
