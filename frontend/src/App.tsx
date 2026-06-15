import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import EventList from './pages/EventList'
import EventGallery from './pages/EventGallery'
import Cart from './pages/Cart'
import OrderStatus from './pages/OrderStatus'
import AdminLayout from './pages/admin/AdminLayout'
import AdminDashboard from './pages/admin/AdminDashboard'
import AdminEvents from './pages/admin/AdminEvents'
import AdminIngest from './pages/admin/AdminIngest'
import AdminOrderDetail from './pages/admin/AdminOrderDetail'
import AdminOrders from './pages/admin/AdminOrders'
import AdminSettings from './pages/admin/AdminSettings'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {/* Public */}
        <Route index element={<EventList />} />
        <Route path="events/:eventRef" element={<EventGallery />} />
        <Route path="cart" element={<Cart />} />
        <Route path="orders/:orderId" element={<OrderStatus />} />

        {/* Admin */}
        <Route path="admin" element={<AdminLayout />}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<AdminDashboard />} />
          <Route path="events" element={<AdminEvents />} />
          <Route path="events/:eventId/ingest" element={<AdminIngest />} />
          <Route path="orders" element={<AdminOrders />} />
          <Route path="orders/:orderId" element={<AdminOrderDetail />} />
          <Route path="settings" element={<AdminSettings />} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
