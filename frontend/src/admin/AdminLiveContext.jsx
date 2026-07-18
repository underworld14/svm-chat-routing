import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import {
  EMPTY_GROUPED,
  normalizeGrouped,
  removeSessionFromGrouped,
  sessionTitle,
  withAutoAckFlag,
} from './adminUtils'

const AdminLiveContext = createContext(null)

export function AdminLiveProvider({ children }) {
  const [groupedSessions, setGroupedSessions] = useState(EMPTY_GROUPED)
  const [roleIntents, setRoleIntents] = useState({})
  const [live, setLive] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const fetchSessionsRef = useRef(null)
  const activeRoomIdRef = useRef(null)
  const onRoomMessageRef = useRef(null)
  const onRoomClosedRef = useRef(null)

  const fetchRoleIntents = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/role-intents')
      if (!res.ok) return
      const data = await res.json()
      setRoleIntents(data && typeof data === 'object' ? data : {})
    } catch {
      // Non-blocking
    }
  }, [])

  const fetchSessions = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true)
    try {
      const res = await fetch('/api/admin/sessions/grouped')
      if (!res.ok) throw new Error('Could not load sessions. Click Refresh.')
      const data = await res.json()
      setGroupedSessions(normalizeGrouped(data))
      if (!silent) setError(null)
    } catch (err) {
      if (!silent) setError(err.message)
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

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

      ws.onopen = () => {
        attempt = 0
        setLive(true)
        setError(null)
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
          data.type !== 'message_new' &&
          data.type !== 'session_updated' &&
          data.type !== 'session_deleted'
        ) {
          return
        }

        const payload = data.payload ?? {}
        const activeId = activeRoomIdRef.current

        if (data.type === 'session_deleted') {
          setGroupedSessions((prev) => removeSessionFromGrouped(prev, payload.id))
          if (activeId != null && payload.id === activeId) {
            onRoomClosedRef.current?.('deleted')
          }
          refreshBoards()
          return
        }

        if (
          data.type === 'session_updated' &&
          (payload.status === 'archived' || payload.status === 'closed')
        ) {
          setGroupedSessions((prev) => removeSessionFromGrouped(prev, payload.id))
          if (activeId != null && payload.id === activeId) {
            onRoomClosedRef.current?.('archived')
          }
          refreshBoards()
          return
        }

        refreshBoards()

        if (
          data.type === 'message_new' &&
          activeId != null &&
          payload.session_id === activeId
        ) {
          onRoomMessageRef.current?.(withAutoAckFlag(payload))
        }
      }

      ws.onerror = () => setLive(false)

      ws.onclose = () => {
        setLive(false)
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
    }
  }, [])

  const setActiveRoom = useCallback((roomId, { onMessage, onClosed } = {}) => {
    activeRoomIdRef.current = roomId == null ? null : Number(roomId)
    onRoomMessageRef.current = onMessage ?? null
    onRoomClosedRef.current = onClosed ?? null
  }, [])

  const dropSessionOptimistic = useCallback((sessionId) => {
    setGroupedSessions((prev) => removeSessionFromGrouped(prev, sessionId))
  }, [])

  const value = useMemo(
    () => ({
      groupedSessions,
      roleIntents,
      live,
      loading,
      error,
      setError,
      refreshSessions: fetchSessions,
      fetchRoleIntents,
      sessionTitle,
      setActiveRoom,
      dropSessionOptimistic,
    }),
    [
      groupedSessions,
      roleIntents,
      live,
      loading,
      error,
      fetchSessions,
      fetchRoleIntents,
      setActiveRoom,
      dropSessionOptimistic,
    ],
  )

  return <AdminLiveContext.Provider value={value}>{children}</AdminLiveContext.Provider>
}

export function useAdminLive() {
  const ctx = useContext(AdminLiveContext)
  if (!ctx) {
    throw new Error('useAdminLive must be used within AdminLiveProvider')
  }
  return ctx
}
