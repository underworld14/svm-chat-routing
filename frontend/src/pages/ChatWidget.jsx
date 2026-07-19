import WhatsAppPanel from '../components/WhatsAppPanel'

/**
 * /chat — WhatsApp (WAHA) pairing page.
 * Customer messages arrive via WhatsApp webhook, not a web widget.
 */
function ChatWidget() {
  return (
    <div className="page page--chat">
      <header className="page__intro">
        <h1 className="title">WhatsApp</h1>
        <p className="subtitle">
          Pair the business number here. Incoming chats are classified and routed on the Admin board —
          replies are sent back through WhatsApp only.
        </p>
      </header>
      <WhatsAppPanel />
    </div>
  )
}

export default ChatWidget
