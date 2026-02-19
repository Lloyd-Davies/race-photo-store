import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface CartItem {
  photoId: string
  eventId: number
  proofUrl: string
}

interface CartStore {
  items: CartItem[]
  eventId: number | null      // all items must belong to the same event
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

      add: (item) =>
        set((s) => {
          // Clear cart if switching to a different event
          if (s.eventId !== null && s.eventId !== item.eventId) {
            return { items: [item], eventId: item.eventId }
          }
          if (s.items.some((i) => i.photoId === item.photoId)) return s
          return { items: [...s.items, item], eventId: item.eventId }
        }),

      remove: (photoId) =>
        set((s) => {
          const items = s.items.filter((i) => i.photoId !== photoId)
          return { items, eventId: items.length === 0 ? null : s.eventId }
        }),

      clear: () => set({ items: [], eventId: null }),

      has: (photoId) => get().items.some((i) => i.photoId === photoId),
    }),
    { name: 'photostore-cart' },
  ),
)
