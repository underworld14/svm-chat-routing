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

function isLiveSession(session) {
  return session?.status === 'waiting' || session?.status === 'active'
}

function normalizeGrouped(data) {
  const next = {
    support: (data.support ?? []).filter(isLiveSession),
    tech: (data.tech ?? []).filter(isLiveSession),
    marketing: (data.marketing ?? []).filter(isLiveSession),
    finance: (data.finance ?? []).filter(isLiveSession),
    logistik: (data.logistik ?? []).filter(isLiveSession),
    unassigned: (data.unassigned ?? []).filter(isLiveSession),
  }
  return next
}

function removeSessionFromGrouped(grouped, sessionId) {
  const next = { ...EMPTY_GROUPED }
  for (const role of Object.keys(EMPTY_GROUPED)) {
    next[role] = (grouped[role] ?? []).filter((s) => s.id !== sessionId)
  }
  return next
}

function sessionTitle(session) {
  const name = session.user?.name?.trim()
  if (name) return name
  return session.user?.phone || session.client_id || `Session #${session.id}`
}

function withAutoAckFlag(msg) {
  if (msg.auto_ack) return msg
  const text = String(msg.content || '')
  if (text.startsWith('Terimakasih sudah menghubungi kami')) {
    return { ...msg, auto_ack: true }
  }
  return msg
}

function RolePanel({ label, roleKey, intents = [], sessions, selectedSessionId, onSelectSession }) {
  const [intentsOpen, setIntentsOpen] = useState(false)
  const isUnassigned = roleKey === 'unassigned'
  const intentCount = intents.length
  const canToggle = isUnassigned || intentCount > 0

  return (
    <section className="queue">
      <header className="queue__head">
        <div className="queue__head-main">
          <div className="queue__head-row">
            <h2 className="queue__title">{label}</h2>
            <span className="queue__count">{sessions.length}</span>
          </div>
          {canToggle && (
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
        </div>
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
                    <strong className="card__name">{sessionTitle(session)}</strong>
                    <span className="card__intent">
                      WA · {session.intent?.name ?? 'unclassified'}
                    </span>
                    <span className="card__meta">
                      <span>{session.user?.phone || session.client_id}</span>
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
  const [roleIntents, setRoleIntents] = useState({})
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

  const fetchRoleIntents = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/role-intents')
      if (!res.ok) return
      const data = await res.json()
      setRoleIntents(data && typeof data === 'object' ? data : {})
    } catch {
      // Non-blocking: board still works without intent legend.
    }
  }, [])

  const fetchSessions = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true)
    try {
      const res = await fetch('/api/admin/sessions/grouped')
      if (!res.ok) throw new Error('Could not load sessions. Click Refresh.')
      const data = await res.json()
      const normalized = normalizeGrouped(data)
      setGroupedSessions(normalized)

      setSelectedSession((prev) => {
        if (!prev) return null
        const all = Object.values(normalized).flat()
        return all.find((s) => s.id === prev.id) ?? null
      })
      if (!silent) setError(null)
    } catch (err) {
      if (!silent) setError(err.message)
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  const fetchMessages = useCallback(async (sessionId) => {
    try {
      const res = await fetch(`/api/admin/sessions/${sessionId}/messages`)
      if (!res.ok) throw new Error('Could not load messages.')
      const data = await res.json()
      setMessages(Array.isArray(data) ? data.map(withAutoAckFlag) : data)
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
    fetchRoleIntents()
  }, [fetchSessions, fetchRoleIntents])

  useEffect(() => {
    let closedByCleanup = false
    let reconnectTimer = null
    let attempt = 0
    let ws = null

    const refreshBoards = () => {
      fetchSessionsRef.current?.({ silent: true })
    }

    const connect = () => {
      if (closedByCleanup) return
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      ws = new WebSocket(`${protocol}//${window.location.host}/ws/admin`)
      wsRef.current = ws

      ws.onopen = () => {
        attempt = 0
        setLive(true)
        setError(null)
        // Catch anything missed while disconnected.
        refreshBoards()
      }

      ws.onmessage = (event) => {
        let data
        try {
          data = JSON.parse(event.data)
        } catch {
          return
        }
        if (
          data.type === 'message_new' ||
          data.type === 'session_updated' ||
          data.type === 'session_deleted'
        ) {
          const current = selectedSessionRef.current
          const payload = data.payload ?? {}

          if (data.type === 'session_deleted' && current && payload.id === current.id) {
            setSelectedSession(null)
            setMessages([])
            setGroupedSessions((prev) => removeSessionFromGrouped(prev, payload.id))
            refreshBoards()
            return
          }

          if (
            data.type === 'session_updated' &&
            (payload.status === 'archived' || payload.status === 'closed')
          ) {
            const closedId = payload.id
            setGroupedSessions((prev) => removeSessionFromGrouped(prev, closedId))
            if (current && current.id === closedId) {
              setSelectedSession(null)
              setMessages([])
            }
            refreshBoards()
            return
          }

          refreshBoards()
          if (data.type === 'message_new' && current && payload.session_id === current.id) {
            setMessages((prev) => {
              if (payload.id && prev.some((m) => m.id === payload.id)) return prev
              return [...prev, withAutoAckFlag(payload)]
            })
          }
        }
      }

      ws.onerror = () => {
        setLive(false)
      }

      ws.onclose = () => {
        setLive(false)
        wsRef.current = null
        if (closedByCleanup) return
        const delay = Math.min(1000 * 2 ** attempt, 15000)
        attempt += 1
        reconnectTimer = window.setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      closedByCleanup = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      if (ws) ws.close()
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
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail.detail || 'Reply failed to send. Try again.')
      }
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
    if (!window.confirm('Are you sure to archive and close this session?')) return

    const closedId = selectedSession.id
    setActionBusy(true)
    setError(null)
    // Optimistic: drop from live board immediately.
    setGroupedSessions((prev) => removeSessionFromGrouped(prev, closedId))
    setSelectedSession(null)
    setMessages([])
    try {
      const res = await fetch(`/api/admin/sessions/${closedId}/archive`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error('Archive failed. Try again.')
      await fetchSessions()
    } catch (err) {
      setError(err.message)
      await fetchSessions()
    } finally {
      setActionBusy(false)
    }
  }

  async function deleteSession() {
    if (!selectedSession) return
    if (!window.confirm('Delete this session permanently? This cannot be undone.')) return

    const closedId = selectedSession.id
    setActionBusy(true)
    setError(null)
    setGroupedSessions((prev) => removeSessionFromGrouped(prev, closedId))
    setSelectedSession(null)
    setMessages([])
    try {
      const res = await fetch(`/api/admin/sessions/${closedId}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error('Delete failed. Try again.')
      await fetchSessions()
    } catch (err) {
      setError(err.message)
      await fetchSessions()
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
            roleKey={role.key}
            intents={roleIntents[role.key] ?? []}
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
