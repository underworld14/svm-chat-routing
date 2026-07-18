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
  if (!session) {
    return (
      <div className="panel panel--empty">
        <p className="empty">Select a session to view the conversation and reply.</p>
      </div>
    )
  }

  const isArchive = mode === 'archive'

  return (
    <div className="panel panel--desk">
      <header className="desk__header">
        <div>
          <h2 className="title title--sm">
            {session.user?.name ?? `Session #${session.id}`}
          </h2>
          <p className="subtitle">{session.user?.email}</p>
        </div>
        <div className="desk__aside">
          <div className="route route--compact">
            <div>
              <p className="route__label">Intent</p>
              <p className="route__value">{session.intent?.name ?? 'unclassified'}</p>
            </div>
            <span className="route__sep" aria-hidden="true">
              →
            </span>
            <div>
              <p className="route__label">Agent</p>
              <p className="route__value">{session.assigned_agent?.name ?? 'Unassigned'}</p>
            </div>
          </div>
          <div className="desk__actions">
            {isArchive ? (
              <button
                type="button"
                className="btn"
                onClick={onRestore}
                disabled={actionBusy}
              >
                Restore
              </button>
            ) : (
              <button
                type="button"
                className="btn"
                onClick={onArchive}
                disabled={actionBusy}
              >
                Archive
              </button>
            )}
            <button
              type="button"
              className="btn btn--danger"
              onClick={onDelete}
              disabled={actionBusy}
            >
              Delete
            </button>
          </div>
        </div>
      </header>

      <div className="thread thread--desk" aria-live="polite">
        {messages.length === 0 ? (
          <p className="empty">No messages yet.</p>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`note note--${msg.role}`}>
              <span className="note__role">{msg.role}</span>
              <p>{msg.content}</p>
            </div>
          ))
        )}
      </div>

      {!isArchive && (
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault()
            onSendReply()
          }}
        >
          <label className="field">
            <span className="field__label">Reply</span>
            <textarea
              className="field__textarea"
              name="reply"
              value={reply}
              onChange={(e) => onReplyChange(e.target.value)}
              placeholder="Type your reply…"
              rows={3}
              autoComplete="off"
            />
          </label>
          <button type="submit" className="btn btn--primary" disabled={sending || !reply.trim()}>
            {sending ? 'Sending…' : 'Send reply'}
          </button>
        </form>
      )}
    </div>
  )
}

export default AgentPanel
