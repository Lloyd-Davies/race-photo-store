import { useState } from 'react'
import { AlertTriangle, Clipboard, Share2 } from 'lucide-react'
import Button from './Button'
import { canShareLink } from '../utils/embeddedBrowser'

interface EmbeddedBrowserWarningProps {
  mode: 'checkout' | 'download'
}

const copy = {
  checkout: {
    title: 'Open this page in Safari or Chrome before paying',
    body: 'In-app browsers can block ZIP downloads after checkout. You can continue here, but a normal browser is more reliable.',
  },
  download: {
    title: 'ZIP downloads may not save correctly in this browser',
    body: 'Use the individual photo downloads below, or open this page in Safari or Chrome for the ZIP file.',
  },
}

export default function EmbeddedBrowserWarning({ mode }: EmbeddedBrowserWarningProps) {
  const [copied, setCopied] = useState(false)
  const text = copy[mode]

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  async function shareLink() {
    try {
      await navigator.share({
        title: document.title || 'Race Photos',
        url: window.location.href,
      })
    } catch {
      // Sharing can be cancelled by the customer; no UI state needs changing.
    }
  }

  return (
    <div className="mb-6 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
      <div className="flex gap-3">
        <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-300" />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-amber-50">{text.title}</p>
          <p className="mt-1 text-amber-100/85">{text.body}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="secondary" onClick={copyLink}>
              <Clipboard size={14} className="mr-1.5" />
              {copied ? 'Copied' : 'Copy link'}
            </Button>
            {canShareLink() && (
              <Button type="button" size="sm" variant="secondary" onClick={shareLink}>
                <Share2 size={14} className="mr-1.5" />
                Share link
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
