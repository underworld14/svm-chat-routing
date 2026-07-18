import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import AdminDashboard from './pages/AdminDashboard'
import ArchivePage from './pages/ArchivePage'
import ChatWidget from './pages/ChatWidget'

function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/chat" element={<ChatWidget />} />
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/admin/archive" element={<ArchivePage />} />
        <Route path="/" element={<Navigate to="/chat" replace />} />
      </Route>
    </Routes>
  )
}

export default App
