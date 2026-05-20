import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Mail, CheckCircle, XCircle, Loader2, CreditCard, Settings2, Globe2 } from 'lucide-react'
import Button from '../../components/Button'
import { fetchAdminSettings, sendTestEmail, updateCheckoutSettings } from '../../api/adminSettings'
import { formatMoney } from '../../utils/money'

export default function AdminSettings() {
  const qc = useQueryClient()
  const [testEmail, setTestEmail] = useState('')
  const [result, setResult] = useState<{ sent: boolean; message: string } | null>(null)
  const [pricePounds, setPricePounds] = useState('')
  const [currency, setCurrency] = useState('GBP')
  const [allowPromos, setAllowPromos] = useState(false)

  const { data: settings, isLoading } = useQuery({
    queryKey: ['admin-settings'],
    queryFn: fetchAdminSettings,
  })

  useEffect(() => {
    if (!settings) return
    setPricePounds((settings.checkout.default_photo_price_pence / 100).toFixed(2))
    setCurrency(settings.checkout.currency)
    setAllowPromos(settings.checkout.allow_stripe_promotion_codes)
  }, [settings])

  const testMut = useMutation({
    mutationFn: () => sendTestEmail(testEmail.trim()),
    onSuccess: (data) => setResult({ sent: data.sent, message: data.message }),
    onError: (e: Error) => setResult({ sent: false, message: e.message }),
  })

  const checkoutMut = useMutation({
    mutationFn: () => {
      const amount = Math.round(Number(pricePounds) * 100)
      if (!Number.isFinite(amount) || amount <= 0) {
        throw new Error('Default photo price must be greater than 0.')
      }
      return updateCheckoutSettings({
        default_photo_price_pence: amount,
        currency: currency.trim().toUpperCase(),
        allow_stripe_promotion_codes: allowPromos,
      })
    },
    onSuccess: (data) => {
      qc.setQueryData(['admin-settings'], data)
      qc.invalidateQueries({ queryKey: ['events'] })
      qc.invalidateQueries({ queryKey: ['admin-events'] })
      setPricePounds((data.checkout.default_photo_price_pence / 100).toFixed(2))
      setCurrency(data.checkout.currency)
      setAllowPromos(data.checkout.allow_stripe_promotion_codes)
    },
  })

  const config = settings?.email

  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-lg font-bold text-content">Settings</h1>

      <div className="bg-surface-900 border border-surface-700 rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2 mb-1">
          <CreditCard size={16} className="text-sky-500" />
          <h2 className="text-sm font-semibold text-content">Checkout defaults</h2>
        </div>

        {isLoading && (
          <div className="flex items-center gap-2 text-sm text-content-muted">
            <Loader2 size={14} className="animate-spin" />
            Loading...
          </div>
        )}

        {settings && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-[1fr_120px] gap-3">
              <div>
                <label className="block text-xs text-content-muted mb-1">Default photo price</label>
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={pricePounds}
                  onChange={(e) => setPricePounds(e.target.value)}
                  className="w-full bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-3 py-2 focus:outline-none focus:ring-1 focus:ring-sky-500"
                />
                <p className="text-xs text-content-muted mt-1">
                  Events inherit this unless they define their own price.
                </p>
              </div>
              <div>
                <label className="block text-xs text-content-muted mb-1">Currency</label>
                <input
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                  maxLength={3}
                  className="w-full bg-surface-800 border border-surface-600 rounded-md text-sm text-content px-3 py-2 uppercase focus:outline-none focus:ring-1 focus:ring-sky-500"
                />
              </div>
            </div>

            <label className="flex items-center gap-2 text-sm text-content cursor-pointer select-none">
              <input
                type="checkbox"
                checked={allowPromos}
                onChange={(e) => setAllowPromos(e.target.checked)}
              />
              Allow Stripe promotion codes at checkout
            </label>

            <div className="flex items-center gap-3">
              <Button size="sm" loading={checkoutMut.isPending} onClick={() => checkoutMut.mutate()}>
                Save checkout settings
              </Button>
              <span className="text-xs text-content-muted">
                Current default: {formatMoney(settings.checkout.default_photo_price_pence, settings.checkout.currency)}
              </span>
            </div>
            {checkoutMut.error && (
              <p className="text-xs text-red-400">{(checkoutMut.error as Error).message}</p>
            )}
          </>
        )}
      </div>

      <div className="bg-surface-900 border border-surface-700 rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2 mb-1">
          <Settings2 size={16} className="text-sky-500" />
          <h2 className="text-sm font-semibold text-content">Configuration health</h2>
        </div>
        {settings && (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-content-muted">STRIPE_SECRET_KEY</dt>
            <dd>{settings.stripe_secret_key_set ? <span className="text-green-400">set</span> : <span className="text-red-400">not set</span>}</dd>
            <dt className="text-content-muted">STRIPE_WEBHOOK_SECRET</dt>
            <dd>{settings.stripe_webhook_secret_set ? <span className="text-green-400">set</span> : <span className="text-red-400">not set</span>}</dd>
            <dt className="text-content-muted">PUBLIC_BASE_URL</dt>
            <dd className="text-content">{settings.public_base_url || <em className="text-content-muted">not set</em>}</dd>
            <dt className="text-content-muted">Price source</dt>
            <dd className="text-content">Database inline pricing</dd>
          </dl>
        )}
      </div>

      <div className="bg-surface-900 border border-surface-700 rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2 mb-1">
          <Globe2 size={16} className="text-sky-500" />
          <h2 className="text-sm font-semibold text-content">Public site</h2>
        </div>
        {settings && (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-content-muted">Site name</dt>
            <dd className="text-content">{settings.site_name}</dd>
            <dt className="text-content-muted">Tagline</dt>
            <dd className="text-content">{settings.site_tagline}</dd>
          </dl>
        )}
      </div>

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
