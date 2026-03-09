import { apiGet, apiPost } from './client'
import type { OrderStatus } from './orders'

export interface AdminOrder {
  id: number
  status: OrderStatus
  email: string
  created_at: string
  paid_at?: string
  item_count: number
  event_slug?: string
  download_count?: number
  max_downloads?: number
  expires_at?: string
  download_url?: string
}

export interface AdminOrderList {
  orders: AdminOrder[]
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

export const fetchAdminOrders = (params?: { status?: OrderStatus | 'ALL'; q?: string; limit?: number }) => {
  const query = new URLSearchParams()
  if (params?.status && params.status !== 'ALL') query.set('status', params.status)
  if (params?.q) query.set('q', params.q)
  if (params?.limit) query.set('limit', String(params.limit))
  const qs = query.toString()
  return apiGet<AdminOrderList>(`/admin/orders${qs ? `?${qs}` : ''}`)
}

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