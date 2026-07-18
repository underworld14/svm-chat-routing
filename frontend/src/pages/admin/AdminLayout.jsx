import { useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useMatch } from 'react-router-dom'
import { AdminLiveProvider, useAdminLive } from '../../admin/AdminLiveContext'
import { ROLES } from '../../admin/adminUtils'

function RoleBoard({ role, intents, sessions, activeRoomId, defaultOpen }) {
  const [boardOpen, setBoardOpen] = useState(defaultOpen)
  const [intentsOpen, setIntentsOpen] = useState(false)
  const isUnassigned = role.key === 'unassigned'
  const intentCount = intents.length

  useEffect(() => {
    if (defaultOpen) setBoardOpen(true)
  }, [defaultOpen])

  return (
    <section className={`board ${boardOpen ? 'is-open' : ''}`}>
      <header className="board__head">
        <button
          type="button"
          className="board__toggle"
          aria-expanded={boardOpen}
          onClick={() => setBoardOpen((open) => !open)}
        >
          <span className="board__title">{role.label}</span>
          <span className="board__count">{sessions.length}</span>
          <span className="board__chevron" aria-hidden="true">
            {boardOpen ? '▾' : '▸'}
          </span>
        </button>
      </header>

      {boardOpen && (
        <div className="board__body">
          {(isUnassigned || intentCount > 0) && (
            <div className="queue__intents">
              <button
                type="button"
                className="queue__intents-toggle"
                aria-expanded={intentsOpen}
                onClick={() => setIntentsOpen((open) => !open)}
              >
                <span>
                  {isUnassigned
                    ? 'No matching agent'
                    : `${intentCount} intent${intentCount === 1 ? '' : 's'}`}
                </span>
                <span className="queue__intents-chevron" aria-hidden="true">
                  {intentsOpen ? '▾' : '▸'}
                </span>
              </button>
              {intentsOpen && (
                <div className="queue__intent-tags">
                  {isUnassigned ? (
                    <span className="chip chip--quiet">unclassified / no agent online</span>
                  ) : (
                    intents.map((name) => (
                      <span key={name} className="chip chip--intent">
                        {name}
                      </span>
                    ))
                  )}
                </div>
              )}
            </div>
          )}

          <div className="board__rooms">
            {sessions.length === 0 ? (
              <p className="empty empty--sm">No rooms</p>
            ) : (
              <ul>
                {sessions.map((session) => (
                  <li key={session.id}>
                    <NavLink
                      to={`/admin/rooms/${session.id}`}
                      className={({ isActive }) =>
                        isActive || activeRoomId === String(session.id)
                          ? 'room-link is-active'
                          : 'room-link'
                      }
                    >
                      <strong className="room-link__name">
                        {session.user?.name?.trim() ||
                          session.user?.phone ||
                          session.client_id ||
                          `Room #${session.id}`}
                      </strong>
                      <span className="room-link__intent">
                        {session.intent?.name ?? 'unclassified'}
                      </span>
                      <span className="room-link__meta">
                        <span>{session.assigned_agent?.name ?? 'Unassigned'}</span>
                        <span className="room-link__id">#{session.id}</span>
                      </span>
                    </NavLink>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

function AdminShell() {
  const roomMatch = useMatch('/admin/rooms/:roomId')
  const roomId = roomMatch?.params?.roomId
  const {
    groupedSessions,
    roleIntents,
    live,
    loading,
    error,
    refreshSessions,
  } = useAdminLive()

  const totalCount = useMemo(
    () => ROLES.reduce((sum, role) => sum + (groupedSessions[role.key]?.length ?? 0), 0),
    [groupedSessions],
  )

  const roleWithActiveRoom = useMemo(() => {
    if (!roomId) return null
    const id = Number(roomId)
    for (const role of ROLES) {
      if ((groupedSessions[role.key] ?? []).some((s) => s.id === id)) {
        return role.key
      }
    }
    return null
  }, [groupedSessions, roomId])

  return (
    <div className="admin admin--chatroom">
      <header className="admin__header">
        <div>
          <h1 className="title">Admin</h1>
          <p className="admin__meta">
            <span className="chip chip--quiet">{totalCount} rooms</span>
            <span className={live ? 'status is-live' : 'status'}>
              {live ? 'Live' : 'Offline'}
            </span>
          </p>
        </div>
        <button
          type="button"
          className="btn"
          onClick={() => refreshSessions()}
          disabled={loading}
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </header>

      <div className="admin-layout">
        <aside className="admin-sidebar" aria-label="Agent boards">
          {ROLES.map((role) => {
            const sessions = groupedSessions[role.key] ?? []
            const defaultOpen =
              sessions.length > 0 || roleWithActiveRoom === role.key
            return (
              <RoleBoard
                key={role.key}
                role={role}
                intents={roleIntents[role.key] ?? []}
                sessions={sessions}
                activeRoomId={roomId}
                defaultOpen={defaultOpen}
              />
            )
          })}
        </aside>

        <main className="admin-main">
          <Outlet />
        </main>
      </div>

      {error && (
        <p className="banner banner--error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

function AdminLayout() {
  return (
    <AdminLiveProvider>
      <AdminShell />
    </AdminLiveProvider>
  )
}

export default AdminLayout
