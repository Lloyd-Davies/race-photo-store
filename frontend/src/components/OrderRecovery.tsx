import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../api/client'

interface Recovery {
  excluded_reason?: string
  steps: string[]
  jobs: { kind: string; status: string; attempts: number; last_attempt_at?: string; next_attempt_at?: string; error?: string }[]
}

export function OrderRecovery({ orderId }: { orderId: number }) {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['order-recovery', orderId], queryFn: () => apiGet<Recovery>(`/admin/orders/${orderId}/recovery`), refetchInterval: 15000 })
  const retry = useMutation({ mutationFn: () => apiPost(`/admin/orders/${orderId}/recovery`), onSuccess: () => { client.invalidateQueries({ queryKey: ['order-recovery', orderId] }) } })
  return <section className="my-4 rounded border border-surface-700 p-4">
    <h2 className="font-semibold">Automatic recovery</h2>
    {query.isError && <p role="alert">Unable to load recovery status.</p>}
    {query.data?.excluded_reason && <p>{query.data.excluded_reason}</p>}
    {query.data?.jobs.map(j => <div key={j.kind} className="my-2 text-sm">
      <p>{j.kind}: {j.status} · {j.attempts} attempts</p>
      {j.last_attempt_at && <p>Last attempt: {new Date(j.last_attempt_at).toLocaleString()}</p>}
      {j.status === 'PENDING' && j.next_attempt_at && <p>Next attempt: {new Date(j.next_attempt_at).toLocaleString()}</p>}
      {j.error && <p>{j.error}</p>}
    </div>)}
    {query.data?.steps.map(s => <p key={s} className="text-sm">{s}</p>)}
    {!!query.data?.steps.length && !query.data.excluded_reason && <button className="mt-3 rounded bg-surface-700 px-3 py-2" disabled={retry.isPending} onClick={() => retry.mutate()}>Retry listed steps safely</button>}
    {retry.isError && <p role="alert">{(retry.error as Error).message}</p>}
    {retry.isSuccess && <p>Selected for recovery. Access limits are unchanged.</p>}
  </section>
}

export function HistoricalRecoveryPreview() {
  const [enabled, setEnabled] = useState(false)
  const [afterId, setAfterId] = useState(0)
  const query = useQuery({ queryKey: ['historical-recovery', afterId], enabled, queryFn: () => apiGet<{ candidates: { order_id: number; excluded_reason?: string; steps: string[] }[]; next_after_id?: number }>(`/admin/recovery/preview?after_id=${afterId}`) })
  return <section className="my-4 rounded border border-surface-700 p-4">
    <button onClick={() => setEnabled(!enabled)}>Preview older orders needing recovery</button>
    {enabled && <p className="text-sm">Preview only. Open an order to select its recovery steps.</p>}
    {enabled && query.isError && <p role="alert">Unable to load historical preview.</p>}
    {enabled && query.data?.candidates.map(c => <p key={c.order_id} className="my-2 text-sm"><Link to={`/admin/orders/${c.order_id}`}>Order #{c.order_id}</Link>: {c.excluded_reason || c.steps.join('; ')}</p>)}
    {enabled && query.data?.next_after_id && <button onClick={() => setAfterId(query.data!.next_after_id!)}>Next page</button>}
  </section>
}
