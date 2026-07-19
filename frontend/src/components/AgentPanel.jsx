import { useEffect, useRef } from 'react'
import ChatBubble from './ChatBubble'
import { formatMessageTime } from '../admin/adminUtils'

function displayUserName(session) {
  const name = session?.user?.name?.trim()
  if (name) return name
  return session?.user?.phone || session?.client_id || `Room #${session?.id}`
}

function messageLabel(msg, session) {
  if (msg.role === 'user') {
    return displayUserName(session)
  }
  if (msg.role === 'system') {
    return 'System'
  }
  if (msg.auto_ack) {
    return 'Auto-ack'
  }
  return session?.assigned_agent?.name || 'Agent'
}

function AgentPanel({
  session,
  messages,
  reply,
  onReplyChange,
  onSendReply,
  sending,
  mode = 'live',
  onArchive,
  onRestore,
  onDelete,
  actionBusy = false,
}) {
  const threadRef = useRef(null)
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  if (!session) {
    return (
      <div className="chatroom chatroom--empty">
        <p className="empty">Select a room to view the conversation and reply.</p>
      </div>
    )
  }

  const isArchive = mode === 'archive'
  const contact = session.user?.phone || session.whatsapp_chat_id || session.client_id

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!sending && reply.trim()) onSendReply()
    }
  }

  return (
    <div className="chatroom">
      <header className="chatroom__header">
        <div className="chatroom__identity">
          <h2 className="chatroom__title">{displayUserName(session)}</h2>
          <p className="chatroom__subtitle">
            <span className="chatroom__room-id">#{session.id}</span>
            <span aria-hidden="true">·</span>
            <span>WhatsApp</span>
            <span aria-hidden="true">·</span>
            <span>{contact}</span>
          </p>
        </div>
        <div className="chatroom__meta">
          <div className="chatroom__route">
            <span className="chatroom__route-pill">
              <span className="chatroom__route-label">Intent</span>
              <span className="chatroom__route-value">
                {session.intent?.name ?? 'unclassified'}
              </span>
            </span>
            <span className="chatroom__route-arrow" aria-hidden="true">
              →
            </span>
            <span className="chatroom__route-pill">
              <span className="chatroom__route-label">Agent</span>
              <span className="chatroom__route-value">
                {session.assigned_agent?.name ?? 'Unassigned'}
              </span>
            </span>
          </div>
          <div className="chatroom__actions">
            {isArchive ? (
              <button
                type="button"
                className="btn btn--sm"
                onClick={onRestore}
                disabled={actionBusy}
              >
                Restore
              </button>
            ) : (
              <button
                type="button"
                className="btn btn--sm"
                onClick={onArchive}
                disabled={actionBusy}
              >
                Archive
              </button>
            )}
            <button
              type="button"
              className="btn btn--sm btn--danger"
              onClick={onDelete}
              disabled={actionBusy}
            >
              Delete
            </button>
          </div>
        </div>
      </header>

      <div className="chatroom__stage">
        <div className="chatroom__thread" ref={threadRef} aria-live="polite">
          {messages.length === 0 ? (
            <p className="empty">No messages yet.</p>
          ) : (
            messages.map((msg) => (
              <ChatBubble
                key={msg.id}
                role={msg.role === 'user' ? 'user' : 'agent'}
                label={messageLabel(msg, session)}
                content={msg.content}
                timestamp={
                  msg.created_at
                    ? { iso: msg.created_at, display: formatMessageTime(msg.created_at) }
                    : null
                }
              />
            ))
          )}
          <div ref={endRef} />
        </div>

        {!isArchive && (
          <form
            className="chatroom__composer"
            onSubmit={(e) => {
              e.preventDefault()
              onSendReply()
            }}
          >
            <label className="chatroom__composer-field">
              <span className="visually-hidden">Reply</span>
              <textarea
                className="chatroom__input"
                name="reply"
                value={reply}
                onChange={(e) => onReplyChange(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type a message…"
                rows={1}
                autoComplete="off"
              />
            </label>
            <button
              type="submit"
              className="btn btn--primary chatroom__send"
              disabled={sending || !reply.trim()}
            >
              {sending ? '…' : 'Send'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}

export default AgentPanel
