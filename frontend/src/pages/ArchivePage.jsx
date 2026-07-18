import { useCallback, useEffect, useState } from 'react'
import AgentPanel from '../components/AgentPanel'

function formatDate(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

function ArchivePage() {
  const [sessions, setSessions] = useState([])
  const [selectedSession, setSelectedSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const [error, setError] = useState(null)

  const fetchSessions = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/admin/sessions/archived')
      if (!res.ok) throw new Error('Could not load archived sessions.')
      const data = await res.json()
      setSessions(data)

      setSelectedSession((prev) => {
        if (!prev) return null
        return data.find((s) => s.id === prev.id) ?? null
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchMessages = useCallback(async (sessionId) => {
    try {
      const res = await fetch(`/api/admin/sessions/${sessionId}/messages`)
      if (!res.ok) throw new Error('Could not load messages.')
      setMessages(await res.json())
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  function selectSession(session) {
    setSelectedSession(session)
    fetchMessages(session.id)
  }

  async function restoreSession() {
    if (!selectedSession) return
    setActionBusy(true)
    setError(null)
    try {
      const res = await fetch(`/api/admin/sessions/${selectedSession.id}/restore`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error('Restore failed. Try again.')
      setSelectedSession(null)
      setMessages([])
      await fetchSessions()
    } catch (err) {
      setError(err.message)
    } finally {
      setActionBusy(false)
    }
  }

  async function deleteSession() {
    if (!selectedSession) return
    if (!window.confirm('Delete this session permanently? This cannot be undone.')) return

    setActionBusy(true)
    setError(null)
    try {
      const res = await fetch(`/api/admin/sessions/${selectedSession.id}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error('Delete failed. Try again.')
      setSelectedSession(null)
      setMessages([])
      await fetchSessions()
    } catch (err) {
      setError(err.message)
    } finally {
      setActionBusy(false)
    }
  }

  return (
    <div className="admin archive">
      <header className="admin__header">
        <div>
          <h1 className="title">Archive</h1>
          <p className="admin__meta">
            <span className="chip chip--quiet">{sessions.length} archived</span>
          </p>
        </div>
        <button type="button" className="btn" onClick={fetchSessions} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </header>

      <div className="archive__layout">
        <section className="archive__list panel">
          {sessions.length === 0 ? (
            <p className="empty">No archived sessions.</p>
          ) : (
            <ul className="archive__items">
              {sessions.map((session) => {
                const active = selectedSession?.id === session.id
                return (
                  <li key={session.id}>
                    <button
                      type="button"
                      className={active ? 'card is-active' : 'card'}
                      onClick={() => selectSession(session)}
                    >
                      <strong className="card__name">
                        {session.user?.name ?? `Session #${session.id}`}
                      </strong>
                      <span className="card__intent">
                        WA · {session.intent?.name ?? 'unclassified'}
                      </span>
                      <span className="card__meta">
                        <span>{session.assigned_agent?.name ?? 'Unassigned'}</span>
                        <span>{formatDate(session.created_at)}</span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        <AgentPanel
          session={selectedSession}
          messages={messages}
          mode="archive"
          onRestore={restoreSession}
          onDelete={deleteSession}
          actionBusy={actionBusy}
        />
      </div>

      {error && (
        <p className="banner banner--error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

export default ArchivePage
