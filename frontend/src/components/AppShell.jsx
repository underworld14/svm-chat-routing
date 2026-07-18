import { NavLink, Outlet } from 'react-router-dom'

function AppShell() {
  return (
    <div className="shell">
      <header className="shell__top">
        <div className="shell__brand">
          <p className="shell__product">Chat Routing</p>
        </div>
        <nav className="shell__nav" aria-label="Primary">
          <NavLink
            to="/chat"
            className={({ isActive }) => (isActive ? 'shell__link is-active' : 'shell__link')}
          >
            Chat
          </NavLink>
          <NavLink
            to="/admin"
            end
            className={({ isActive }) => (isActive ? 'shell__link is-active' : 'shell__link')}
          >
            Admin
          </NavLink>
          <NavLink
            to="/admin/archive"
            className={({ isActive }) => (isActive ? 'shell__link is-active' : 'shell__link')}
          >
            Archive
          </NavLink>
        </nav>
      </header>
      <main className="shell__main">
        <Outlet />
      </main>
    </div>
  )
}

export default AppShell
