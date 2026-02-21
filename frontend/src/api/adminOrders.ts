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