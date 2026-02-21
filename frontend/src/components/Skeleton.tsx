import type { HTMLAttributes } from 'react'

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  className?: string
}

export function Skeleton({ className = '', ...props }: SkeletonProps) {
  return (
    <div
      {...props}
      className={`bg-surface-800 rounded animate-pulse ${className}`}
      aria-hidden
    />
  )
}

/** A grid of skeleton photo cards matching the masonry gallery */
export function PhotoSkeleton() {
  // Vary heights to mimic a real masonry layout during loading
  const heights = [180, 240, 200, 160, 220, 200, 180, 240, 160, 200, 220, 200]
  return (
    <div className="masonry">
      {heights.map((h, i) => (
        <div key={i} className="masonry-item">
          <Skeleton style={{ height: h }} />
        </div>
      ))}
    </div>
  )
}
