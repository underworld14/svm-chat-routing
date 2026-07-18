function ChatBubble({ role, content, timestamp }) {
  const isUser = role === 'user'

  return (
    <div className={`chat-bubble ${isUser ? 'chat-bubble--user' : 'chat-bubble--agent'}`}>
      <p className="chat-bubble__content">{content}</p>
      {timestamp && <time className="chat-bubble__time">{timestamp}</time>}
    </div>
  )
}

export default ChatBubble
