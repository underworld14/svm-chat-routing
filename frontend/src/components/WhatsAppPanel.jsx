import { useCallback, useEffect, useState } from 'react'

function WhatsAppPanel() {
  const [status, setStatus] = useState(null)
  const [qr, setQr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    setError(null)
    try {
      const statusRes = await fetch('/api/admin/whatsapp/status')
      if (!statusRes.ok) {
        const detail = await statusRes.json().catch(() => ({}))
        throw new Error(detail.detail || 'Could not reach WAHA. Is docker compose up?')
      }
      const statusData = await statusRes.json()
      setStatus(statusData)

      const current = String(statusData.status || '').toUpperCase()
      if (current === 'SCAN_QR_CODE' || current === 'STARTING') {
        const qrRes = await fetch('/api/admin/whatsapp/qr')
        if (qrRes.ok) {
          const qrData = await qrRes.json()
          setQr(qrData.qr || null)
        } else {
          setQr(null)
        }
      } else {
        setQr(null)
      }
    } catch (err) {
      setError(err.message)
      setStatus(null)
      setQr(null)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = window.setInterval(refresh, 5000)
    return () => window.clearInterval(id)
  }, [refresh])

  async function startSession() {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/admin/whatsapp/session/start', { method: 'POST' })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail.detail || 'Failed to start WhatsApp session')
      }
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const state = String(status?.status || 'UNKNOWN').toUpperCase()
  const meId = status?.me?.id || status?.me?.pushName || null
  const connected = state === 'WORKING'

  return (
    <section className="wa-panel panel">
      <header className="wa-panel__head">
        <div>
          <h2 className="title title--sm">WhatsApp</h2>
          <p className="subtitle">
            Pair the main business number via QR (WAHA GOWS).
          </p>
        </div>
        <div className="wa-panel__actions">
          <button type="button" className="btn" onClick={refresh} disabled={busy}>
            Refresh
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={startSession}
            disabled={busy || connected}
          >
            {busy ? 'Starting…' : connected ? 'Connected' : 'Start / reconnect'}
          </button>
        </div>
      </header>

      <div className="wa-panel__body">
        <p className="wa-panel__status">
          Status:{' '}
          <span className={connected ? 'status is-live' : 'status'}>{state}</span>
          {meId ? <span className="chip chip--quiet">{meId}</span> : null}
        </p>

        {qr ? (
          <div className="wa-panel__qr">
            <img
              src={qr.startsWith('data:') ? qr : `data:image/png;base64,${qr}`}
              alt="WhatsApp QR code"
              width={220}
              height={220}
            />
            <p className="subtitle">Scan with WhatsApp → Linked devices</p>
          </div>
        ) : (
          <p className="empty">
            {connected
              ? 'Number is linked. Customer chats will route here.'
              : 'Start the session to show a QR code when scanning is required.'}
          </p>
        )}

        {error ? (
          <p className="banner banner--error" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  )
}

export default WhatsAppPanel
