import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import EventList from './pages/EventList'
import EventGallery from './pages/EventGallery'
import Cart from './pages/Cart'
import OrderStatus from './pages/OrderStatus'
import AdminLayout from './pages/admin/AdminLayout'
import AdminEvents from './pages/admin/AdminEvents'
import AdminIngest from './pages/admin/AdminIngest'
import AdminOrders from './pages/admin/AdminOrders'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {/* Public */}
        <Route index element={<EventList />} />
        <Route path="events/:eventId" element={<EventGallery />} />
        <Route path="cart" element={<Cart />} />
        <Route path="orders/:orderId" element={<OrderStatus />} />

        {/* Admin */}
        <Route path="admin" element={<AdminLayout />}>
          <Route index element={<Navigate to="events" replace />} />
          <Route path="events" element={<AdminEvents />} />
          <Route path="events/:eventId/ingest" element={<AdminIngest />} />
          <Route path="orders" element={<AdminOrders />} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
