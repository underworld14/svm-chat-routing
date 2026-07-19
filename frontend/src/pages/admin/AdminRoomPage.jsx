import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAdminLive } from '../../admin/AdminLiveContext'
import { findSessionInGrouped, withAutoAckFlag } from '../../admin/adminUtils'
import AgentPanel from '../../components/AgentPanel'

function AdminRoomPage() {
  const { roomId } = useParams()
  const navigate = useNavigate()
  const {
    groupedSessions,
    loading: boardsLoading,
    setError,
    refreshSessions,
    setActiveRoom,
    dropSessionOptimistic,
  } = useAdminLive()

  const fromBoards = findSessionInGrouped(groupedSessions, roomId)
  const [fetchedSession, setFetchedSession] = useState(null)
  const session = fromBoards || fetchedSession

  const [messages, setMessages] = useState([])
  const [reply, setReply] = useState('')
  const [sending, setSending] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const [loadingMessages, setLoadingMessages] = useState(true)
  const [notFound, setNotFound] = useState(false)

  const fetchMessages = useCallback(
    async (sessionId) => {
      setLoadingMessages(true)
      try {
        const res = await fetch(`/api/admin/sessions/${sessionId}/messages`)
        if (res.status === 404) {
          setNotFound(true)
          setMessages([])
          return
        }
        if (!res.ok) throw new Error('Could not load messages.')
        const data = await res.json()
        setNotFound(false)
        setMessages(Array.isArray(data) ? data.map(withAutoAckFlag) : [])
      } catch (err) {
        setError(err.message)
      } finally {
        setLoadingMessages(false)
      }
    },
    [setError],
  )

  useEffect(() => {
    const id = Number(roomId)
    if (!Number.isFinite(id)) {
      setNotFound(true)
      return undefined
    }

    setReply('')
    setFetchedSession(null)
    setNotFound(false)
    fetchMessages(id)

    setActiveRoom(id, {
      onMessage: (payload) => {
        setMessages((prev) => {
          if (payload.id && prev.some((m) => m.id === payload.id)) return prev
          return [...prev, payload]
        })
      },
      onClosed: () => {
        navigate('/admin', { replace: true })
      },
    })

    return () => setActiveRoom(null)
  }, [roomId, fetchMessages, setActiveRoom, navigate])

  useEffect(() => {
    if (fromBoards || boardsLoading || notFound) return
    const id = Number(roomId)
    if (!Number.isFinite(id)) return

    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/api/admin/sessions')
        if (!res.ok) return
        const data = await res.json()
        if (cancelled) return
        const found = Array.isArray(data) ? data.find((s) => s.id === id) : null
        if (found) setFetchedSession(found)
        else if (!loadingMessages) setNotFound(true)
      } catch {
        // ignore — messages 404 already covers missing rooms
      }
    })()

    return () => {
      cancelled = true
    }
  }, [fromBoards, boardsLoading, roomId, notFound, loadingMessages])

  async function sendReply() {
    if (!session || !reply.trim()) return
    setSending(true)
    setError(null)
    try {
      const res = await fetch('/api/admin/reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: session.id,
          content: reply.trim(),
        }),
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail.detail || 'Reply failed to send. Try again.')
      }
      setReply('')
      await fetchMessages(session.id)
    } catch (err) {
      setError(err.message)
    } finally {
      setSending(false)
    }
  }

  async function archiveSession() {
    if (!session) return
    if (!window.confirm('Are you sure to archive and close this session?')) return
    const closedId = session.id
    setActionBusy(true)
    setError(null)
    dropSessionOptimistic(closedId)
    try {
      const res = await fetch(`/api/admin/sessions/${closedId}/archive`, { method: 'POST' })
      if (!res.ok) throw new Error('Archive failed. Try again.')
      await refreshSessions({ silent: true })
      navigate('/admin', { replace: true })
    } catch (err) {
      setError(err.message)
      await refreshSessions()
    } finally {
      setActionBusy(false)
    }
  }

  async function deleteSession() {
    if (!session) return
    if (!window.confirm('Delete this session permanently? This cannot be undone.')) return
    const closedId = session.id
    setActionBusy(true)
    setError(null)
    dropSessionOptimistic(closedId)
    try {
      const res = await fetch(`/api/admin/sessions/${closedId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Delete failed. Try again.')
      await refreshSessions({ silent: true })
      navigate('/admin', { replace: true })
    } catch (err) {
      setError(err.message)
      await refreshSessions()
    } finally {
      setActionBusy(false)
    }
  }

  if (notFound) {
    return (
      <div className="admin-room admin-room--empty">
        <p className="empty">Room #{roomId} was not found or is no longer live.</p>
        <Link to="/admin" className="btn">
          Back to boards
        </Link>
      </div>
    )
  }

  if (!session) {
    return (
      <div className="admin-room admin-room--empty">
        <p className="empty">
          {boardsLoading || loadingMessages ? 'Loading room…' : `Room #${roomId} unavailable.`}
        </p>
        {!boardsLoading && !loadingMessages ? (
          <Link to="/admin" className="btn">
            Back to boards
          </Link>
        ) : null}
      </div>
    )
  }

  return (
    <div className="admin-room">
      <AgentPanel
        session={session}
        messages={messages}
        reply={reply}
        onReplyChange={setReply}
        onSendReply={sendReply}
        sending={sending}
        onArchive={archiveSession}
        onDelete={deleteSession}
        actionBusy={actionBusy}
      />
    </div>
  )
}

export default AdminRoomPage
