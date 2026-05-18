export function isEmbeddedInAppBrowser(userAgent?: string): boolean {
  const ua = (
    userAgent ?? (typeof navigator !== 'undefined' ? navigator.userAgent : '')
  ).toLowerCase()

  return [
    'instagram',
    'fbav',
    'fban',
    'fb_iab',
    'messenger',
    'tiktok',
    'musical_ly',
    'twitter',
    'line/',
    'snapchat',
    'linkedinapp',
    'pinterest',
    'webview',
    '; wv',
  ].some((needle) => ua.includes(needle))
}

export function canShareLink(): boolean {
  return typeof navigator !== 'undefined' && typeof navigator.share === 'function'
}
