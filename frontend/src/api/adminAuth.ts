export interface AdminSession {
  access_token: string
  access_expires_at: string
  refresh_token: string
  refresh_expires_at: string
}

export async function adminLogin(adminToken: string): Promise<AdminSession> {
  const res = await fetch('/api/admin/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ admin_token: adminToken }),
  })

  if (!res.ok) {
    throw new Error('Invalid admin credentials')
  }

  return res.json() as Promise<AdminSession>
}

export async function refreshAdminSession(refreshToken: string): Promise<AdminSession> {
  const res = await fetch('/api/admin/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })

  if (!res.ok) {
    throw new Error('Admin session refresh failed')
  }

  return res.json() as Promise<AdminSession>
}

export async function verifyAdminSession(accessToken: string): Promise<void> {
  const res = await fetch('/api/admin/session', {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })

  if (!res.ok) {
    throw new Error('Invalid admin session')
  }
}
