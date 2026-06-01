import { useEffect, useState } from 'react'

export interface VisualViewportSnapshot {
  width: number
  height: number
  offsetTop: number
  offsetLeft: number
  pageTop: number
  pageLeft: number
}

function readViewport(): VisualViewportSnapshot {
  if (typeof window === 'undefined') {
    return { width: 0, height: 0, offsetTop: 0, offsetLeft: 0, pageTop: 0, pageLeft: 0 }
  }

  const visualViewport = window.visualViewport
  return {
    width: visualViewport?.width ?? window.innerWidth,
    height: visualViewport?.height ?? window.innerHeight,
    offsetTop: visualViewport?.offsetTop ?? 0,
    offsetLeft: visualViewport?.offsetLeft ?? 0,
    pageTop: visualViewport?.pageTop ?? window.scrollY,
    pageLeft: visualViewport?.pageLeft ?? window.scrollX,
  }
}

export function useVisualViewport() {
  const [viewport, setViewport] = useState<VisualViewportSnapshot>(() => readViewport())

  useEffect(() => {
    const visualViewport = window.visualViewport
    let frame = 0

    function update() {
      window.cancelAnimationFrame(frame)
      frame = window.requestAnimationFrame(() => setViewport(readViewport()))
    }

    window.addEventListener('resize', update)
    window.addEventListener('orientationchange', update)
    visualViewport?.addEventListener('resize', update)
    visualViewport?.addEventListener('scroll', update)
    update()

    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener('resize', update)
      window.removeEventListener('orientationchange', update)
      visualViewport?.removeEventListener('resize', update)
      visualViewport?.removeEventListener('scroll', update)
    }
  }, [])

  return viewport
}

export function getVisualViewportSnapshot() {
  return readViewport()
}
