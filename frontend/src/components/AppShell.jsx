import { NavLink, Outlet, useLocation } from 'react-router-dom'

function AppShell() {
  const { pathname } = useLocation()
  const onArchive = pathname.startsWith('/admin/archive')

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
            WhatsApp
          </NavLink>
          <NavLink
            to="/admin"
            className={({ isActive }) =>
              isActive && !onArchive ? 'shell__link is-active' : 'shell__link'
            }
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
