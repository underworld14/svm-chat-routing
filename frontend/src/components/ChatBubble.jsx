function ChatBubble({ role, label, content, timestamp }) {
  const isUser = role === 'user'

  return (
    <div className={`chat-bubble ${isUser ? 'chat-bubble--user' : 'chat-bubble--agent'}`}>
      {label ? <span className="chat-bubble__label">{label}</span> : null}
      <p className="chat-bubble__content">{content}</p>
      {timestamp ? (
        <time className="chat-bubble__time" dateTime={timestamp.iso || undefined}>
          {timestamp.display || timestamp}
        </time>
      ) : null}
    </div>
  )
}

export default ChatBubble
