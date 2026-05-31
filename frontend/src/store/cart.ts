import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface CartItem {
  photoId: string
  eventId: number
  eventSlug?: string
  proofUrl: string
}

interface CartStore {
  items: CartItem[]
  eventId: number | null      // all items must belong to the same event
  eventSlug: string | null
  add: (item: CartItem) => void
  remove: (photoId: string) => void
  clear: () => void
  has: (photoId: string) => boolean
}

export const useCartStore = create<CartStore>()(
  persist(
    (set, get) => ({
      items: [],
      eventId: null,
      eventSlug: null,

      add: (item) =>
        set((s) => {
          // Clear cart if switching to a different event
          if (s.eventId !== null && s.eventId !== item.eventId) {
            return { items: [item], eventId: item.eventId, eventSlug: item.eventSlug ?? null }
          }
          if (s.items.some((i) => i.photoId === item.photoId)) return s
          return {
            items: [...s.items, item],
            eventId: item.eventId,
            eventSlug: item.eventSlug ?? s.eventSlug,
          }
        }),

      remove: (photoId) =>
        set((s) => {
          const items = s.items.filter((i) => i.photoId !== photoId)
          return {
            items,
            eventId: items.length === 0 ? null : s.eventId,
            eventSlug: items.length === 0 ? null : (items[0]?.eventSlug ?? s.eventSlug),
          }
        }),

      clear: () => set({ items: [], eventId: null, eventSlug: null }),

      has: (photoId) => get().items.some((i) => i.photoId === photoId),
    }),
    { name: 'photostore-cart' },
  ),
)
