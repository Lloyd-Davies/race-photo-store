import { useState, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { ArrowLeft, Play, Upload, CheckCircle2, XCircle, CloudUpload } from 'lucide-react'
import {
  fetchAdminEvents,
  fetchEventStorageMigrations,
  ingestPhotos,
  startEventStorageMigration,
  uploadBibTags,
  type AssetMigrationType,
  type BibTagsResult,
  type EventAssetMigration,
  type IngestResult,
} from '../../api/events'
import Button from '../../components/Button'

type BibTagUploadRow = { photo_id: string; bib: string; confidence?: number }

function parseBibCsv(text: string): BibTagUploadRow[] {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)

  if (lines.length === 0) {
    throw new Error('CSV file is empty')
  }

  const parseLine = (line: string) => line.split(',').map((part) => part.trim().replace(/^"|"$/g, ''))
  const header = parseLine(lines[0]).map((column) => column.toLowerCase())

  const photoIdIdx = header.indexOf('photo_id')
  const bibIdx = header.indexOf('bib')
  const confidenceIdx = header.indexOf('confidence')

  if (photoIdIdx === -1 || bibIdx === -1) {
    throw new Error("CSV must include headers 'photo_id' and 'bib'")
  }

  const rows: BibTagUploadRow[] = []
  for (let i = 1; i < lines.length; i += 1) {
    const cols = parseLine(lines[i])
    const photoId = (cols[photoIdIdx] ?? '').trim()
    const bib = (cols[bibIdx] ?? '').trim()

    if (!photoId || !bib) {
      continue
    }

    let confidence: number | undefined
    if (confidenceIdx >= 0) {
      const raw = (cols[confidenceIdx] ?? '').trim()
      if (raw) {
        const parsed = Number(raw)
        if (Number.isNaN(parsed)) {
          throw new Error(`Invalid confidence value on CSV row ${i + 1}`)
        }
        confidence = parsed
      }
    }

    rows.push({ photo_id: photoId, bib, confidence })
  }

  if (rows.length === 0) {
    throw new Error('CSV contains no valid photo_id/bib rows')
  }

  return rows
}

function parseBibJson(text: string): BibTagUploadRow[] {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new Error('File is not valid JSON')
  }

  if (!Array.isArray(parsed)) {
    throw new Error('Expected a JSON array')
  }

  const rows: BibTagUploadRow[] = []
  for (const row of parsed) {
    if (!row || typeof row !== 'object') {
      continue
    }
    const rec = row as Record<string, unknown>
    const photoId = typeof rec.photo_id === 'string' ? rec.photo_id.trim() : ''
    const bib = typeof rec.bib === 'string' ? rec.bib.trim() : ''
    if (!photoId || !bib) {
      continue
    }
    const confidence = typeof rec.confidence === 'number' ? rec.confidence : undefined
    rows.push({ photo_id: photoId, bib, confidence })
  }

  if (rows.length === 0) {
    throw new Error('JSON contains no valid photo_id/bib rows')
  }

  return rows
}

async function parseBibUploadFile(file: File): Promise<BibTagUploadRow[]> {
  const text = await file.text()
  const isCsv = file.name.toLowerCase().endsWith('.csv')
  if (isCsv) {
    return parseBibCsv(text)
  }
  return parseBibJson(text)
}

export default function AdminIngest() {
  const { eventId } = useParams<{ eventId: string }>()
  const id = Number(eventId)
  const bibFileRef = useRef<HTMLInputElement>(null)
  const [ingestResult, setIngestResult] = useState<IngestResult | null>(null)
  const [bibResult, setBibResult] = useState<BibTagsResult | null>(null)
  const [bibError, setBibError] = useState<string | null>(null)

  const { data: events } = useQuery({ queryKey: ['admin-events'], queryFn: fetchAdminEvents })
  const event = events?.find((e) => e.id === id)
  const migrationsQuery = useQuery({
    queryKey: ['event-storage-migrations', id],
    queryFn: () => fetchEventStorageMigrations(id),
    enabled: Number.isFinite(id),
    refetchInterval: 3000,
  })

  const ingestMut = useMutation({
    mutationFn: () => ingestPhotos(id),
    onSuccess: (data) => setIngestResult(data),
  })

  const bibMut = useMutation({
    mutationFn: async () => {
      setBibError(null)
      const file = bibFileRef.current?.files?.[0]
      if (!file) throw new Error('No file selected')

      const parsed = await parseBibUploadFile(file)
      return uploadBibTags(id, parsed)
    },
    onSuccess: (data) => setBibResult(data),
    onError: (e: Error) => setBibError(e.message),
  })

  const migrationMut = useMutation({
    mutationFn: (type: 'proofs' | 'originals') => startEventStorageMigration(id, type),
    onSuccess: () => migrationsQuery.refetch(),
  })

  const migrationFor = (type: AssetMigrationType): EventAssetMigration | undefined =>
    migrationsQuery.data?.migrations.find((migration) => migration.asset_type === type)
  const proofMigration = migrationFor('PROOFS')
  const originalMigration = migrationFor('ORIGINALS')
  const migrationActive = migrationMut.isPending

  const renderMigration = (
    label: string,
    migration: EventAssetMigration | undefined,
    type: 'proofs' | 'originals',
    disabled = false,
  ) => {
    const status = migration?.status ?? 'NOT_STARTED'
    const active = status === 'QUEUED' || status === 'RUNNING'
    const processed = (migration?.migrated_count ?? 0) + (migration?.skipped_count ?? 0) + (migration?.failed_count ?? 0)
    const total = migration?.total_count ?? 0
    const progress = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0
    const action = status === 'FAILED' ? 'Retry' : status === 'READY' ? 'Run again' : 'Migrate'

    return (
      <div className="py-4 border-t border-surface-700 first:border-t-0 first:pt-0 last:pb-0">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-gray-100">{label}</span>
              <span className="text-xs text-gray-400">{status.replace('_', ' ')}</span>
            </div>
            {(active || status === 'READY' || status === 'FAILED') && (
              <p className="text-xs text-gray-400 mt-1">
                {processed} of {total} checked
                {(migration?.failed_count ?? 0) > 0 ? `, ${migration?.failed_count} failed` : ''}
              </p>
            )}
            {active && (
              <div className="h-1.5 bg-surface-700 rounded mt-2 overflow-hidden" aria-label={`${label} migration progress`}>
                <div className="h-full bg-sky-500 transition-all" style={{ width: `${progress}%` }} />
              </div>
            )}
            {migration?.error && <p className="text-xs text-red-400 mt-2 break-words">{migration.error}</p>}
          </div>
          <Button
            size="sm"
            variant="secondary"
            disabled={disabled || active || migrationActive}
            loading={migrationMut.isPending && migrationMut.variables === type}
            onClick={() => migrationMut.mutate(type)}
          >
            <CloudUpload size={14} className="mr-1" />
            {action}
          </Button>
        </div>
      </div>
    )
  }

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

      <section className="bg-surface-900 border border-surface-700 rounded-xl p-6 mb-6">
        <h2 className="font-semibold text-gray-100 mb-1">Object storage migration</h2>
        <p className="text-xs text-gray-400 mb-4">
          Copy event assets to private object storage. Local files are retained.
        </p>

        {migrationsQuery.error && (
          <div className="flex items-center gap-2 text-sm text-red-400 mb-4">
            <XCircle size={16} />
            {(migrationsQuery.error as Error).message}
          </div>
        )}
        {migrationMut.error && (
          <div className="flex items-center gap-2 text-sm text-red-400 mb-4">
            <XCircle size={16} />
            {(migrationMut.error as Error).message}
          </div>
        )}

        {renderMigration('Proofs', proofMigration, 'proofs')}
        {renderMigration(
          'Originals',
          originalMigration,
          'originals',
          proofMigration?.status !== 'READY' || event?.status === 'ARCHIVED',
        )}
      </section>

      {/* --- Bib tags --- */}
      <section className="bg-surface-900 border border-surface-700 rounded-xl p-6">
        <h2 className="font-semibold text-gray-100 mb-1">Upload bib tags</h2>
        <p className="text-xs text-gray-400 mb-4">
          Upload a generated CSV (<code className="text-sky-400">photo_id,bib,confidence</code>) or
          JSON array (<code className="text-sky-400">{"[{photo_id, bib}, ...]"}</code>) to enable bib-number search.
        </p>

        <div className="flex items-center gap-3 mb-4">
          <label className="cursor-pointer">
            <span className="sr-only">Choose file</span>
            <input
              ref={bibFileRef}
              type="file"
              accept=".csv,text/csv,.json,application/json"
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
