import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PhotoCard from './PhotoCard'

vi.mock('../hooks/useIntersection', () => ({
  useIntersection: () => [{ current: null }, true],
}))

describe('PhotoCard', () => {
  it('uses known event information for alt text and stored preview dimensions', () => {
    render(
      <PhotoCard
        photo={{
          photo_id: 'photo-001',
          proof_url: '/proofs/test-event/photo-001.jpg',
          preview_width: 1600,
          preview_height: 1067,
        }}
        eventId={1}
        eventSlug="test-event"
        eventName="Test Event 2026"
      />,
    )

    const image = screen.getByRole('img', { name: 'Photograph from Test Event 2026' })
    expect(image).toHaveAttribute('width', '1600')
    expect(image).toHaveAttribute('height', '1067')
    expect(image).toHaveAttribute('loading', 'lazy')
  })
})
