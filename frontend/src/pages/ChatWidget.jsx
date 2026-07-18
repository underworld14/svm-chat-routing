import { useEffect, useRef, useState } from 'react'
import ChatBubble from '../components/ChatBubble'

function ChatWidget() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [routeInfo, setRouteInfo] = useState(null)
  const wsRef = useRef(null)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    if (!sessionId) return undefined

    let closedByCleanup = false
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/client/${sessionId}`)
    wsRef.current = ws

    ws.onopen = () => setError(null)

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'message_new' && data.payload) {
        setMessages((prev) => [...prev, data.payload])
      }
    }

    ws.onerror = () => {
      if (!closedByCleanup) setError('Connection lost. Refresh the page and try again.')
    }

    return () => {
      closedByCleanup = true
      ws.close()
      wsRef.current = null
    }
  }, [sessionId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function startChat(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      const res = await fetch('/api/chat/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email }),
      })
      if (!res.ok) throw new Error('Could not start chat. Check that the API is running.')
      const data = await res.json()
      setSessionId(data.session_id)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function sendMessage(e) {
    e.preventDefault()
    if (!input.trim() || !sessionId) return

    const content = input.trim()
    setInput('')
    setLoading(true)
    setError(null)

    setMessages((prev) => [
      ...prev,
      { role: 'user', content, created_at: new Date().toISOString() },
    ])

    try {
      const res = await fetch('/api/chat/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: content }),
      })
      if (!res.ok) throw new Error('Message failed to send. Try again.')
      const data = await res.json()
      setRouteInfo({
        intent: data.intent ?? 'unknown',
        agent: data.assigned_agent ?? null,
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!sessionId) {
    return (
      <section className="chat-page">
        <div className="panel panel--chat">
          <header className="panel__header">
            <h1 className="title">Start chat</h1>
            <p className="subtitle">
              Your first message is classified and assigned to the matching agent.
            </p>
          </header>
          <form className="stack" onSubmit={startChat}>
            <label className="field">
              <span className="field__label">Name</span>
              <input
                className="field__input"
                type="text"
                name="name"
                autoComplete="name"
                placeholder="Budi Santoso"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </label>
            <label className="field">
              <span className="field__label">Email</span>
              <input
                className="field__input"
                type="email"
                name="email"
                autoComplete="email"
                spellCheck={false}
                placeholder="budi@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </label>
            <button type="submit" className="btn btn--primary" disabled={loading}>
              {loading ? 'Starting…' : 'Start chat'}
            </button>
          </form>
          {error && (
            <p className="banner banner--error" role="alert">
              {error}
            </p>
          )}
        </div>
      </section>
    )
  }

  return (
    <section className="chat-page">
      <div className="panel panel--chat">
        <header className="panel__header panel__header--row">
          <div>
            <h1 className="title title--sm">Support chat</h1>
            <p className="subtitle">Session {sessionId}</p>
          </div>
          <span className="chip">SES-{String(sessionId).padStart(3, '0')}</span>
        </header>

        {routeInfo && (
          <div className="route" aria-live="polite">
            <div>
              <p className="route__label">Intent</p>
              <p className="route__value">{routeInfo.intent}</p>
            </div>
            <span className="route__sep" aria-hidden="true">
              →
            </span>
            <div>
              <p className="route__label">Agent</p>
              <p className="route__value">{routeInfo.agent ?? 'Unassigned'}</p>
            </div>
          </div>
        )}

        <div className="thread" aria-live="polite">
          {messages.length === 0 ? (
            <p className="empty">Send a message to begin routing.</p>
          ) : (
            messages.map((msg, i) => (
              <ChatBubble
                key={msg.id ?? i}
                role={msg.role}
                content={msg.content}
                timestamp={
                  msg.created_at
                    ? new Intl.DateTimeFormat(undefined, {
                        hour: 'numeric',
                        minute: '2-digit',
                      }).format(new Date(msg.created_at))
                    : null
                }
              />
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        <form className="composer" onSubmit={sendMessage}>
          <label className="field composer__field">
            <span className="visually-hidden">Message</span>
            <input
              className="field__input"
              type="text"
              name="message"
              autoComplete="off"
              placeholder="Type a message…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
              aria-label="Message"
            />
          </label>
          <button type="submit" className="btn btn--primary" disabled={loading || !input.trim()}>
            Send
          </button>
        </form>
        {error && (
          <p className="banner banner--error" role="alert">
            {error}
          </p>
        )}
      </div>
    </section>
  )
}

export default ChatWidget
