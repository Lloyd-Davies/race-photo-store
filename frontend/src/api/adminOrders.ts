import { apiBlob, apiGet, apiPost } from './client'
import type { OrderStatus } from './orders'

export type DeliveryZipStatus = 'NOT_REQUESTED' | 'BUILDING' | 'READY' | 'EXPIRED' | 'FAILED'

export interface AdminOrder {
  id: number
  status: OrderStatus
  email: string
  created_at: string
  paid_at?: string
  item_count: number
  subtotal_pence: number
  currency: string
  event_slug?: string
  download_count?: number
  max_downloads?: number
  expires_at?: string
  download_url?: string
  zip_status?: DeliveryZipStatus
  zip_expires_at?: string
  zip_error?: string
}

export interface AdminOrderItem {
  photo_id: string
  unit_price_pence: number
  discount_applied_pence: number
  line_total_pence: number
}

export interface AdminOrderDetail extends AdminOrder {
  items: AdminOrderItem[]
}

export interface AdminOrderList {
  orders: AdminOrder[]
  total: number
  page: number
  page_size: number
}

export type CommunicationKind = 'ORDER_CONFIRMED' | 'DOWNLOAD_READY' | 'DELIVERY_RESET'
export type CommunicationStatus =
  | 'QUEUED'
  | 'SENT'
  | 'FAILED'
  | 'DELIVERED'
  | 'BOUNCED'
  | 'BLOCKED'
  | 'DEFERRED'

export interface Communication {
  id: number
  kind: CommunicationKind
  status: CommunicationStatus
  recipient_email: string
  subject: string
  initiated_by?: string
  created_at: string
  sent_at?: string
  error_message?: string
}

export interface AdminOrderQuery {
  status?: OrderStatus | 'ALL'
  zip_status?: DeliveryZipStatus | 'ALL'
  event_id?: number | 'ALL'
  q?: string
  limit?: number
  page?: number
  page_size?: number
  sort?: 'id' | 'created_at' | 'paid_at' | 'status' | 'subtotal' | 'items'
  direction?: 'asc' | 'desc'
  created_from?: string
  created_to?: string
  paid_from?: string
  paid_to?: string
}

export interface AdminTimelineEntry {
  id: number
  source: 'activity' | 'communication' | 'stripe'
  action: string
  actor?: string
  message: string
  status?: string
  order_id?: number
  created_at: string
  metadata: Record<string, unknown>
}

export interface AdminOrderTimeline {
  entries: AdminTimelineEntry[]
}

export interface AdminStripeSyncResult {
  order_id?: number
  status: string
  message: string
  orders_checked: number
  orders_updated: number
}

const appendOrderQuery = (query: URLSearchParams, params?: AdminOrderQuery) => {
  if (!params) return
  if (params.status && params.status !== 'ALL') query.set('status', params.status)
  if (params.zip_status && params.zip_status !== 'ALL') query.set('zip_status', params.zip_status)
  if (params.event_id && params.event_id !== 'ALL') query.set('event_id', String(params.event_id))
  if (params.q) query.set('q', params.q)
  if (params.limit) query.set('limit', String(params.limit))
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.sort) query.set('sort', params.sort)
  if (params.direction) query.set('direction', params.direction)
  if (params.created_from) query.set('created_from', params.created_from)
  if (params.created_to) query.set('created_to', params.created_to)
  if (params.paid_from) query.set('paid_from', params.paid_from)
  if (params.paid_to) query.set('paid_to', params.paid_to)
}

export const fetchAdminOrders = (params?: AdminOrderQuery) => {
  const query = new URLSearchParams()
  appendOrderQuery(query, params)
  const qs = query.toString()
  return apiGet<AdminOrderList>(`/admin/orders${qs ? `?${qs}` : ''}`)
}

export const fetchAdminOrder = (orderId: number) =>
  apiGet<AdminOrderDetail>(`/admin/orders/${orderId}`)

export const resetAdminOrderDelivery = (
  orderId: number,
  body: { rotate_token: boolean; days_valid: number; max_downloads?: number }
) => apiPost<AdminOrder>(`/admin/orders/${orderId}/reset-delivery`, body)

export const rebuildAdminOrderZip = (orderId: number) =>
  apiPost<AdminOrder>(`/admin/orders/${orderId}/rebuild-zip`)

export const expireAdminOrderDelivery = (orderId: number) =>
  apiPost<AdminOrder>(`/admin/orders/${orderId}/expire-delivery`)

export const fetchOrderCommunications = (orderId: number) =>
  apiGet<Communication[]>(`/admin/orders/${orderId}/communications`)

export const sendAdminEmail = (orderId: number, kind: CommunicationKind) =>
  apiPost<Communication>(`/admin/orders/${orderId}/communications/send`, { kind })

export const fetchAdminOrderTimeline = (orderId: number) =>
  apiGet<AdminOrderTimeline>(`/admin/orders/${orderId}/timeline`)

export const syncAdminOrderWithStripe = (orderId: number) =>
  apiPost<AdminStripeSyncResult>(`/admin/orders/${orderId}/stripe-sync`)

export const reconcileAdminStripeOrders = (params?: { older_than_minutes?: number; limit?: number }) => {
  const query = new URLSearchParams()
  if (params?.older_than_minutes) query.set('older_than_minutes', String(params.older_than_minutes))
  if (params?.limit) query.set('limit', String(params.limit))
  const qs = query.toString()
  return apiPost<AdminStripeSyncResult>(`/admin/stripe/reconcile${qs ? `?${qs}` : ''}`)
}

export const exportAdminOrders = (params?: AdminOrderQuery) => {
  const query = new URLSearchParams()
  appendOrderQuery(query, params)
  const qs = query.toString()
  return apiBlob(`/admin/orders/export${qs ? `?${qs}` : ''}`)
}
