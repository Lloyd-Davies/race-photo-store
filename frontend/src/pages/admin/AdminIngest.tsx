import { useState, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { ArrowLeft, Play, Upload, CheckCircle2, XCircle } from 'lucide-react'
import { fetchEvents, ingestPhotos, uploadBibTags, type IngestResult, type BibTagsResult } from '../../api/events'
import Button from '../../components/Button'

export default function AdminIngest() {
  const { eventId } = useParams<{ eventId: string }>()
  const id = Number(eventId)
  const bibFileRef = useRef<HTMLInputElement>(null)
  const [ingestResult, setIngestResult] = useState<IngestResult | null>(null)
  const [bibResult, setBibResult] = useState<BibTagsResult | null>(null)
  const [bibError, setBibError] = useState<string | null>(null)

  const { data: events } = useQuery({ queryKey: ['events'], queryFn: fetchEvents })
  const event = events?.find((e) => e.id === id)

  const ingestMut = useMutation({
    mutationFn: () => ingestPhotos(id),
    onSuccess: (data) => setIngestResult(data),
  })

  const bibMut = useMutation({
    mutationFn: async () => {
      setBibError(null)
      const file = bibFileRef.current?.files?.[0]
      if (!file) throw new Error('No file selected')

      // Parse JSON client-side to validate before upload
      let parsed: unknown
      try {
        parsed = JSON.parse(await file.text())
      } catch {
        throw new Error('File is not valid JSON')
      }

      if (!Array.isArray(parsed)) throw new Error('Expected a JSON array')

      return uploadBibTags(id, parsed as { photo_id: string; bib: string }[])
    },
    onSuccess: (data) => setBibResult(data),
    onError: (e: Error) => setBibError(e.message),
  })

  return (
    <div className="max-w-lg">
      <Link
        to="/admin/events"
        className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 mb-6 transition-colors"
      >
        <ArrowLeft size={16} />
        Events
      </Link>

      <h1 className="text-xl font-bold text-gray-100 mb-1">Ingest</h1>
      <p className="text-sm text-gray-400 mb-8">{event?.name ?? `Event ${id}`}</p>

      {/* --- Ingest photos --- */}
      <section className="bg-surface-900 border border-surface-700 rounded-xl p-6 mb-6">
        <h2 className="font-semibold text-gray-100 mb-1">Scan photos</h2>
        <p className="text-xs text-gray-400 mb-4">
          Index new photos from the server's photo directory for this event. Already-indexed
          photos are skipped.
        </p>

        {ingestMut.error && (
          <div className="flex items-center gap-2 text-sm text-red-400 mb-4">
            <XCircle size={16} />
            {(ingestMut.error as Error).message}
          </div>
        )}

        {ingestResult && (
          <div className="flex items-center gap-2 text-sm text-green-400 mb-4">
            <CheckCircle2 size={16} />
            Ingested {ingestResult.ingested}, skipped {ingestResult.skipped}
          </div>
        )}

        <Button
          size="sm"
          loading={ingestMut.isPending}
          onClick={() => { setIngestResult(null); ingestMut.mutate() }}
        >
          <Play size={14} className="mr-1" />
          Run ingest
        </Button>
      </section>

      {/* --- Bib tags --- */}
      <section className="bg-surface-900 border border-surface-700 rounded-xl p-6">
        <h2 className="font-semibold text-gray-100 mb-1">Upload bib tags</h2>
        <p className="text-xs text-gray-400 mb-4">
          Upload a JSON array of <code className="text-orange-400">{"[{photo_id, bib}, ...]"}</code>{' '}
          mappings to enable bib-number search.
        </p>

        <div className="flex items-center gap-3 mb-4">
          <label className="cursor-pointer">
            <span className="sr-only">Choose file</span>
            <input
              ref={bibFileRef}
              type="file"
              accept=".json,application/json"
              className="text-sm text-gray-300 file:mr-3 file:rounded file:border-0 file:bg-surface-700 file:text-gray-200 file:px-3 file:py-1 file:text-xs file:cursor-pointer hover:file:bg-surface-600"
            />
          </label>
        </div>

        {bibError && (
          <div className="flex items-center gap-2 text-sm text-red-400 mb-4">
            <XCircle size={16} />
            {bibError}
          </div>
        )}

        {bibResult && (
          <div className="flex items-center gap-2 text-sm text-green-400 mb-4">
            <CheckCircle2 size={16} />
            {bibResult.added} photo{bibResult.added !== 1 ? 's' : ''} tagged
          </div>
        )}

        <Button
          size="sm"
          variant="secondary"
          loading={bibMut.isPending}
          onClick={() => { setBibResult(null); bibMut.mutate() }}
        >
          <Upload size={14} className="mr-1" />
          Upload
        </Button>
      </section>
    </div>
  )
}
