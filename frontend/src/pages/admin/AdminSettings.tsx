import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Mail, CheckCircle, XCircle, Loader2 } from 'lucide-react'
import Button from '../../components/Button'
import { fetchEmailConfig, sendTestEmail } from '../../api/adminSettings'

export default function AdminSettings() {
  const [testEmail, setTestEmail] = useState('')
  const [result, setResult] = useState<{ sent: boolean; message: string } | null>(null)

  const { data: config, isLoading } = useQuery({
    queryKey: ['admin-email-config'],
    queryFn: fetchEmailConfig,
  })

  const testMut = useMutation({
    mutationFn: () => sendTestEmail(testEmail.trim()),
    onSuccess: (data) => setResult({ sent: data.sent, message: data.message }),
    onError: (e: Error) => setResult({ sent: false, message: e.message }),
  })

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-lg font-bold text-content">Settings</h1>

      {/* Email config card */}
      <div className="bg-surface-900 border border-surface-700 rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2 mb-1">
          <Mail size={16} className="text-sky-500" />
          <h2 className="text-sm font-semibold text-content">Email configuration</h2>
        </div>

        {isLoading && (
          <div className="flex items-center gap-2 text-sm text-content-muted">
            <Loader2 size={14} className="animate-spin" />
            Loading…
          </div>
        )}

        {config && (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-content-muted">EMAIL_ENABLED</dt>
            <dd className="font-medium">
              {config.email_enabled ? (
                <span className="text-green-400">true</span>
              ) : (
                <span className="text-red-400">false</span>
              )}
            </dd>

            <dt className="text-content-muted">Provider</dt>
            <dd className="text-content">{config.provider}</dd>

            <dt className="text-content-muted">BREVO_API_KEY</dt>
            <dd className="font-medium">
              {config.brevo_key_set ? (
                <span className="text-green-400">set</span>
              ) : (
                <span className="text-red-400">not set</span>
              )}
            </dd>

            <dt className="text-content-muted">From address</dt>
            <dd className="text-content">{config.from_address || <em className="text-content-muted">not set</em>}</dd>

            <dt className="text-content-muted">From name</dt>
            <dd className="text-content">{config.from_name}</dd>

            <dt className="text-content-muted">Support email</dt>
            <dd className="text-content">{config.support_email || <em className="text-content-muted">not set</em>}</dd>

            <dt className="text-content-muted">Email required at checkout</dt>
            <dd className="text-content">{config.order_email_required ? 'yes' : 'no'}</dd>
          </dl>
        )}

        {/* Test email */}
        <div className="border-t border-surface-700 pt-4 space-y-3">
          <p className="text-xs text-content-muted">
            Send a test email directly from the API (synchronous, bypasses queue) to verify
            Brevo credentials and configuration.
          </p>
          <div className="flex gap-2">
            <input
              type="email"
              value={testEmail}
              onChange={(e) => { setTestEmail(e.target.value); setResult(null) }}
              placeholder="recipient@example.com"
              className="flex-1 bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-3 py-2 focus:outline-none focus:ring-1 focus:ring-sky-500 placeholder:text-content-muted"
            />
            <Button
              size="sm"
              loading={testMut.isPending}
              disabled={!testEmail.trim()}
              onClick={() => testMut.mutate()}
            >
              Send test
            </Button>
          </div>

          {result && (
            <div
              className={`flex items-start gap-2 rounded-lg px-3 py-2 text-sm border ${
                result.sent
                  ? 'bg-green-500/10 border-green-500/20 text-green-300'
                  : 'bg-red-500/10 border-red-500/20 text-red-300'
              }`}
            >
              {result.sent ? <CheckCircle size={16} className="shrink-0 mt-0.5" /> : <XCircle size={16} className="shrink-0 mt-0.5" />}
              {result.message}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
