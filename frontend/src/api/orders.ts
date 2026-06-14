import { apiGet, apiPost } from './client'

export type OrderStatus = 'PENDING' | 'PAID' | 'BUILDING' | 'READY' | 'FAILED' | 'EXPIRED'
export type ZipStatus = 'NOT_REQUESTED' | 'BUILDING' | 'READY' | 'EXPIRED' | 'FAILED'

export interface OrderDownloadItem {
  photo_id: string
  proof_url?: string
  view_url?: string
  download_url: string
}

export interface OrderZip {
  status: ZipStatus
  download_url?: string
  expires_at?: string
  error?: string
}

export interface Order {
  id: number
  status: OrderStatus
  download_url?: string
  zip: OrderZip
  items: OrderDownloadItem[]
  download_items: OrderDownloadItem[]
}

export const fetchOrder = (orderId: number, accessToken?: string) =>
  apiGet<Order>(
    `/orders/${orderId}`,
    accessToken ? { 'X-Order-Access': accessToken } : undefined,
  )

export const prepareOrderZip = (orderId: number, accessToken?: string) =>
  apiPost<OrderZip>(
    `/orders/${orderId}/zip`,
    undefined,
    accessToken ? { 'X-Order-Access': accessToken } : undefined,
  )
