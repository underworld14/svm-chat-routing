import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import AdminLayout from './pages/admin/AdminLayout'
import AdminEmptyState from './pages/admin/AdminEmptyState'
import AdminRoomPage from './pages/admin/AdminRoomPage'
import ArchivePage from './pages/ArchivePage'
import ChatWidget from './pages/ChatWidget'

function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/chat" element={<ChatWidget />} />
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<AdminEmptyState />} />
          <Route path="rooms/:roomId" element={<AdminRoomPage />} />
        </Route>
        <Route path="/admin/archive" element={<ArchivePage />} />
        <Route path="/" element={<Navigate to="/chat" replace />} />
      </Route>
    </Routes>
  )
}

export default App
