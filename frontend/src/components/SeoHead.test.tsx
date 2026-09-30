import { cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import SeoHead, { robotsForQuery } from './SeoHead'

afterEach(() => cleanup())

describe('SeoHead', () => {
  it('updates title, canonical, social metadata, and structured data', async () => {
    const view = render(
      <SeoHead
        title="Test Race Photos | Race Photos"
        description="Photographs from Test Race."
        canonicalUrl="https://photos.example.com/events/test-race"
        robots="index, follow, max-image-preview:large"
        siteName="Race Photos"
        socialImage="https://photos.example.com/covers/test-race.jpg"
        structuredData={{ '@context': 'https://schema.org', '@type': 'ImageGallery' }}
      />,
    )

    await waitFor(() => expect(document.title).toBe('Test Race Photos | Race Photos'))
    expect(document.querySelector('link[rel="canonical"]')).toHaveAttribute(
      'href',
      'https://photos.example.com/events/test-race',
    )
    expect(document.querySelector('meta[name="description"]')).toHaveAttribute(
      'content',
      'Photographs from Test Race.',
    )
    expect(document.getElementById('seo-structured-data')?.textContent).toContain('ImageGallery')

    view.rerender(
      <SeoHead
        title="Homepage"
        description="Homepage description"
        canonicalUrl="https://photos.example.com/"
        robots="index, follow"
        siteName="Race Photos"
      />,
    )
    await waitFor(() => expect(document.querySelector('meta[property="og:image"]')).toBeNull())
  })

  it('noindexes stateful query variants but not tracking parameters', () => {
    expect(robotsForQuery('?bib=123')).toBe('noindex, follow')
    expect(robotsForQuery('?utm_source=newsletter')).toBe('index, follow, max-image-preview:large')
  })
})
