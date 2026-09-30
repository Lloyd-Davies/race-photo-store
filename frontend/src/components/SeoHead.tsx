import { useEffect, useMemo } from 'react'
import type { SiteConfig } from '../api/siteConfig'

export interface SeoHeadProps {
  title: string
  description: string
  canonicalUrl: string
  robots: string
  siteName: string
  socialImage?: string
  structuredData?: object | object[] | null
}

function ensureMeta(attribute: 'name' | 'property', key: string, content: string) {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[${attribute}="${key}"]`)
  if (!element) {
    element = document.createElement('meta')
    element.setAttribute(attribute, key)
    document.head.appendChild(element)
  }
  element.content = content
}

function removeMeta(attribute: 'name' | 'property', key: string) {
  document.head.querySelector(`meta[${attribute}="${key}"]`)?.remove()
}

export function titleFromTemplate(page: string, config: SiteConfig) {
  return config.seo_title_template
    .replace('{page}', page)
    .replace('{site_name}', config.site_name)
}

export function absoluteSeoUrl(pathOrUrl: string, config: SiteConfig) {
  if (/^https:\/\//i.test(pathOrUrl)) return pathOrUrl
  const path = pathOrUrl.startsWith('/') ? pathOrUrl : `/${pathOrUrl}`
  return `${config.seo_site_url}${path}`
}

export function robotsForQuery(search: string, indexable = true) {
  if (!indexable) return 'noindex, nofollow, noarchive'
  const keys = Array.from(new URLSearchParams(search).keys()).map((key) => key.toLowerCase())
  if (keys.length === 0) return 'index, follow, max-image-preview:large'
  const onlyTracking = keys.every(
    (key) => key.startsWith('utm_') || ['gclid', 'dclid', 'fbclid', 'msclkid'].includes(key),
  )
  return onlyTracking ? 'index, follow, max-image-preview:large' : 'noindex, follow'
}

export default function SeoHead({
  title,
  description,
  canonicalUrl,
  robots,
  siteName,
  socialImage,
  structuredData,
}: SeoHeadProps) {
  const structuredJson = useMemo(
    () => structuredData ? JSON.stringify(structuredData) : null,
    [structuredData],
  )

  useEffect(() => {
    document.title = title
    ensureMeta('name', 'description', description)
    ensureMeta('name', 'robots', robots)
    ensureMeta('property', 'og:type', 'website')
    ensureMeta('property', 'og:site_name', siteName)
    ensureMeta('property', 'og:title', title)
    ensureMeta('property', 'og:description', description)
    ensureMeta('property', 'og:url', canonicalUrl)
    ensureMeta('name', 'twitter:card', 'summary_large_image')
    ensureMeta('name', 'twitter:title', title)
    ensureMeta('name', 'twitter:description', description)
    if (socialImage) {
      ensureMeta('property', 'og:image', socialImage)
      ensureMeta('property', 'og:image:alt', siteName)
      ensureMeta('name', 'twitter:image', socialImage)
    } else {
      removeMeta('property', 'og:image')
      removeMeta('property', 'og:image:alt')
      removeMeta('name', 'twitter:image')
    }

    let canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
    if (!canonical) {
      canonical = document.createElement('link')
      canonical.rel = 'canonical'
      document.head.appendChild(canonical)
    }
    canonical.href = canonicalUrl

    const existingSchema = document.getElementById('seo-structured-data')
    if (!structuredJson) {
      existingSchema?.remove()
      return
    }
    const schema = existingSchema instanceof HTMLScriptElement
      ? existingSchema
      : document.createElement('script')
    schema.id = 'seo-structured-data'
    schema.type = 'application/ld+json'
    schema.textContent = structuredJson
    if (!schema.isConnected) document.head.appendChild(schema)
  }, [canonicalUrl, description, robots, siteName, socialImage, structuredJson, title])

  return null
}
