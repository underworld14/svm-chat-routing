export const ROLES = [
  { key: 'support', label: 'Support' },
  { key: 'tech', label: 'Tech' },
  { key: 'marketing', label: 'Marketing' },
  { key: 'finance', label: 'Finance' },
  { key: 'logistik', label: 'Logistik' },
  { key: 'unassigned', label: 'Unassigned' },
]

export const EMPTY_GROUPED = {
  support: [],
  tech: [],
  marketing: [],
  finance: [],
  logistik: [],
  unassigned: [],
}

export function isLiveSession(session) {
  return session?.status === 'waiting' || session?.status === 'active'
}

export function normalizeGrouped(data) {
  return {
    support: (data.support ?? []).filter(isLiveSession),
    tech: (data.tech ?? []).filter(isLiveSession),
    marketing: (data.marketing ?? []).filter(isLiveSession),
    finance: (data.finance ?? []).filter(isLiveSession),
    logistik: (data.logistik ?? []).filter(isLiveSession),
    unassigned: (data.unassigned ?? []).filter(isLiveSession),
  }
}

export function removeSessionFromGrouped(grouped, sessionId) {
  const next = { ...EMPTY_GROUPED }
  for (const role of Object.keys(EMPTY_GROUPED)) {
    next[role] = (grouped[role] ?? []).filter((s) => s.id !== sessionId)
  }
  return next
}

export function sessionTitle(session) {
  const name = session?.user?.name?.trim()
  if (name) return name
  return session?.user?.phone || session?.client_id || `Room #${session?.id}`
}

export function withAutoAckFlag(msg) {
  if (msg.auto_ack) return msg
  const text = String(msg.content || '')
  if (text.startsWith('Terimakasih sudah menghubungi kami')) {
    return { ...msg, auto_ack: true }
  }
  return msg
}

export function findSessionInGrouped(grouped, roomId) {
  const id = Number(roomId)
  if (!Number.isFinite(id)) return null
  for (const role of Object.keys(EMPTY_GROUPED)) {
    const found = (grouped[role] ?? []).find((s) => s.id === id)
    if (found) return found
  }
  return null
}

/** Short local timestamp for chat bubbles. */
export function formatMessageTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)

  const now = new Date()
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()

  if (sameDay) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  return date.toLocaleString([], {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}
