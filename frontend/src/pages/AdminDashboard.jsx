import { useCallback, useEffect, useRef, useState } from 'react'
import AgentPanel from '../components/AgentPanel'

const ROLES = [
  { key: 'support', label: 'Support' },
  { key: 'tech', label: 'Tech' },
  { key: 'marketing', label: 'Marketing' },
  { key: 'finance', label: 'Finance' },
  { key: 'logistik', label: 'Logistik' },
  { key: 'unassigned', label: 'Unassigned' },
]

const EMPTY_GROUPED = {
  support: [],
  tech: [],
  marketing: [],
  finance: [],
  logistik: [],
  unassigned: [],
}

function RolePanel({ label, sessions, selectedSessionId, onSelectSession }) {
  return (
    <section className="queue">
      <header className="queue__head">
        <h2 className="queue__title">{label}</h2>
        <span className="queue__count">{sessions.length}</span>
      </header>
      <div className="queue__list">
        {sessions.length === 0 ? (
          <p className="empty">No sessions</p>
        ) : (
          <ul>
            {sessions.map((session) => {
              const active = selectedSessionId === session.id
              return (
                <li key={session.id}>
                  <button
                    type="button"
                    className={active ? 'card is-active' : 'card'}
                    onClick={() => onSelectSession(session)}
                  >
                    <strong className="card__name">
                      {session.user?.name ?? `Session #${session.id}`}
                    </strong>
                    <span className="card__intent">
                      {session.intent?.name ?? 'unclassified'}
                    </span>
                    <span className="card__meta">
                      <span>{session.status}</span>
                      <span>{session.assigned_agent?.name ?? 'Unassigned'}</span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </section>
  )
}

function AdminDashboard() {
  const [groupedSessions, setGroupedSessions] = useState(EMPTY_GROUPED)
  const [selectedSession, setSelectedSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [reply, setReply] = useState('')
  const [sending, setSending] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [live, setLive] = useState(false)
  const wsRef = useRef(null)
  const selectedSessionRef = useRef(null)
  const fetchSessionsRef = useRef(null)

  const fetchSessions = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/admin/sessions/grouped')
      if (!res.ok) throw new Error('Could not load sessions. Click Refresh.')
      const data = await res.json()

      const normalized = {
        support: data.support ?? [],
        tech: data.tech ?? [],
        marketing: data.marketing ?? [],
        finance: data.finance ?? [],
        logistik: data.logistik ?? [],
        unassigned: data.unassigned ?? [],
      }
      setGroupedSessions(normalized)

      setSelectedSession((prev) => {
        if (!prev) return null
        const all = Object.values(normalized).flat()
        return all.find((s) => s.id === prev.id) ?? null
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
      const data = await res.json()
      setMessages(data)
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    selectedSessionRef.current = selectedSession
  }, [selectedSession])

  useEffect(() => {
    fetchSessionsRef.current = fetchSessions
  }, [fetchSessions])

  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  useEffect(() => {
    let closedByCleanup = false
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/admin`)
    wsRef.current = ws

    ws.onopen = () => {
      setLive(true)
      setError(null)
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (
        data.type === 'message_new' ||
        data.type === 'session_updated' ||
        data.type === 'session_deleted'
      ) {
        fetchSessionsRef.current?.()
        const current = selectedSessionRef.current
        if (data.type === 'session_deleted' && current && data.payload?.id === current.id) {
          setSelectedSession(null)
          setMessages([])
          return
        }
        if (data.type === 'message_new' && current && data.payload?.session_id === current.id) {
          setMessages((prev) => [...prev, data.payload])
        }
      }
    }

    ws.onerror = () => {
      setLive(false)
      if (!closedByCleanup) setError('Live updates disconnected. Refresh to reconnect.')
    }

    ws.onclose = () => setLive(false)

    return () => {
      closedByCleanup = true
      ws.close()
      wsRef.current = null
    }
  }, [])

  function selectSession(session) {
    setSelectedSession(session)
    setReply('')
    fetchMessages(session.id)
  }

  async function sendReply() {
    if (!selectedSession || !reply.trim()) return

    setSending(true)
    setError(null)

    try {
      const res = await fetch('/api/admin/reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: selectedSession.id,
          agent_id: 1,
          content: reply.trim(),
        }),
      })
      if (!res.ok) throw new Error('Reply failed to send. Try again.')
      setReply('')
      await fetchMessages(selectedSession.id)
    } catch (err) {
      setError(err.message)
    } finally {
      setSending(false)
    }
  }

  async function archiveSession() {
    if (!selectedSession) return
    setActionBusy(true)
    setError(null)
    try {
      const res = await fetch(`/api/admin/sessions/${selectedSession.id}/archive`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error('Archive failed. Try again.')
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

  const totalCount = ROLES.reduce(
    (sum, role) => sum + (groupedSessions[role.key]?.length ?? 0),
    0,
  )

  return (
    <div className="admin">
      <header className="admin__header">
        <div>
          <h1 className="title">Admin</h1>
          <p className="admin__meta">
            <span className="chip chip--quiet">{totalCount} sessions</span>
            <span className={live ? 'status is-live' : 'status'}>
              {live ? 'Live' : 'Offline'}
            </span>
          </p>
        </div>
        <button type="button" className="btn" onClick={fetchSessions} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </header>

      <div className="admin__queues">
        {ROLES.map((role) => (
          <RolePanel
            key={role.key}
            label={role.label}
            sessions={groupedSessions[role.key] ?? []}
            selectedSessionId={selectedSession?.id}
            onSelectSession={selectSession}
          />
        ))}
      </div>

      <AgentPanel
        session={selectedSession}
        messages={messages}
        reply={reply}
        onReplyChange={setReply}
        onSendReply={sendReply}
        sending={sending}
        onArchive={archiveSession}
        onDelete={deleteSession}
        actionBusy={actionBusy}
      />

      {error && (
        <p className="banner banner--error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

export default AdminDashboard




