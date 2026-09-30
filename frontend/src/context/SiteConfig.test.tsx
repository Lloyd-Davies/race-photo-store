import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchSiteConfig, type SiteConfig } from '../api/siteConfig'
import { SiteConfigProvider, useSiteConfig } from './SiteConfig'

vi.mock('../api/siteConfig', () => ({ fetchSiteConfig: vi.fn() }))
afterEach(cleanup)

function Probe() {
  const config = useSiteConfig()
  return <div data-testid="site-config">{JSON.stringify(config)}</div>
}

describe('runtime site configuration', () => {
  it('uses deployment branding and origin returned by the API', async () => {
    vi.mocked(fetchSiteConfig).mockResolvedValue({
      site_name: 'Synthetic Store', site_tagline: '', allow_stripe_promotion_codes: false,
      seo_site_url: 'https://events.example.org', seo_default_title: 'Synthetic Store',
      seo_title_template: '{page} | {site_name}', seo_default_description: 'Synthetic photos',
      seo_logo_url: 'https://events.example.org/favicon.svg',
    })
    render(<SiteConfigProvider><Probe /></SiteConfigProvider>)
    await waitFor(() => expect(screen.getByTestId('site-config')).toHaveTextContent('https://events.example.org'))
    expect(screen.getByTestId('site-config')).toHaveTextContent('Synthetic Store')
  })

  it('keeps same-origin fallbacks when an older API returns only branding', async () => {
    vi.mocked(fetchSiteConfig).mockResolvedValue({
      site_name: 'Legacy Store', site_tagline: '', allow_stripe_promotion_codes: false,
    } as SiteConfig)
    render(<SiteConfigProvider><Probe /></SiteConfigProvider>)
    await waitFor(() => expect(screen.getByTestId('site-config')).toHaveTextContent('Legacy Store'))
    expect(screen.getByTestId('site-config')).toHaveTextContent(window.location.origin)
    expect(screen.getByTestId('site-config')).toHaveTextContent('seo_default_title')
  })
})
