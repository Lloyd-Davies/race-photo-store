import { apiGet } from './client'

export interface AdminStats {
  total_events: number
  total_photos: number
  total_orders: number
  total_deliveries: number
  pending_orders: number
  failed_orders: number
  active_events: number
}

export const fetchAdminStats = () => apiGet<AdminStats>('/admin/stats')

export async function verifyAdminSession(token: string): Promise<void> {
  const res = await fetch('/api/admin/session', {
    method: 'GET',
    headers: {
      'X-Admin-Token': token,
    },
  })

  if (!res.ok) {
    throw new Error('Invalid admin token')
  }
}
