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

/** A grid of skeleton photo cards matching the gallery */
export function PhotoSkeleton() {
  return (
    <div className="masonry">
      {Array.from({ length: 12 }).map((_, i) => (
        <div key={i} className="masonry-item">
          <Skeleton className="absolute inset-0" />
        </div>
      ))}
    </div>
  )
}
