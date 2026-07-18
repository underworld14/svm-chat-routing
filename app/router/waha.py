from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.dependencies import get_db
from app.models import ChatChannel, ChatSession, Message, User
from app.services.router import ChatService
from app.services.waha import (
    WahaClient,
    is_user_chat,
    normalize_chat_id,
    normalize_phone,
    to_chat_id,
)
from app.services.whatsapp_acks import delayed_send_seen, send_auto_ack
from app.ws.manager import manager

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _extract_push_name(body: dict[str, Any], envelope: dict[str, Any]) -> str:
    """Best-effort WhatsApp contact name from WAHA/GOWS payload shapes."""
    candidates: list[object] = [
        body.get("notifyName"),
        body.get("pushName"),
        body.get("senderName"),
    ]
    data = body.get("_data")
    if isinstance(data, dict):
        candidates.extend(
            [
                data.get("notifyName"),
                data.get("pushName"),
                data.get("verifiedBizName"),
            ]
        )
        info = data.get("info")
        if isinstance(info, dict):
            candidates.append(info.get("PushName"))
            candidates.append(info.get("pushName"))

    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _latest_user_message(db: Session, session_id: int) -> Message | None:
    return (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .first()
    )


def _verify_waha_hmac(raw_body: bytes, signature: str | None) -> None:
    secret = (settings.WAHA_HOOK_HMAC_KEY or "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="WAHA_HOOK_HMAC_KEY is not configured")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing X-Webhook-Hmac header")

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, signature.strip()):
        raise HTTPException(status_code=401, detail="Invalid webhook HMAC")


@router.post("/waha")
async def waha_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_webhook_hmac: str | None = Header(default=None, alias="X-Webhook-Hmac"),
) -> dict[str, str]:
    raw_body = await request.body()
    _verify_waha_hmac(raw_body, x_webhook_hmac)

    try:
        payload: dict[str, Any] = json.loads(raw_body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event = str(payload.get("event") or "")

    if event == "session.status":
        return {"status": "ok", "event": event}

    if event != "message":
        return {"status": "ignored", "event": event}

    body = payload.get("payload") or {}
    if not isinstance(body, dict):
        return {"status": "ignored", "reason": "invalid_payload"}

    if body.get("fromMe") is True:
        return {"status": "ignored", "reason": "from_me"}

    from_id = normalize_chat_id(str(body.get("from") or ""))
    if not from_id or not is_user_chat(from_id):
        return {"status": "ignored", "reason": "non_user_chat"}

    text = str(body.get("body") or "").strip()
    if not text:
        return {"status": "ignored", "reason": "empty_or_media"}

    # Prefer phone identity when available so @lid and @c.us map to one sticky session.
    phone = normalize_phone(from_id) or None
    phone_chat_id: str | None = to_chat_id(phone) if phone else None
    if from_id.endswith("@lid") and not phone:
        try:
            resolved = WahaClient().get_phone_by_lid(from_id)
        except Exception:
            resolved = None
        if resolved:
            phone_chat_id = resolved
            phone = normalize_phone(resolved) or None

    # Canonical sticky key: phone@c.us when known, else the inbound chat id (@lid/@c.us).
    client_id = phone_chat_id or from_id

    external_id = str(body.get("id") or "") or None
    push_name = _extract_push_name(body, payload)
    display_name = push_name or (f"WA {phone}" if phone else f"WA {from_id}")

    service = ChatService()
    open_session = service.find_open_whatsapp_session(
        db,
        chat_id=from_id,
        phone=phone,
        phone_chat_id=phone_chat_id,
    )

    if open_session is None:
        open_session = service.start_chat(
            db,
            name=display_name,
            phone=phone,
            channel=ChatChannel.whatsapp,
            client_id=client_id,
        )
        open_session = db.query(ChatSession).filter(ChatSession.id == open_session.id).first()

    assert open_session is not None

    dirty = False
    # Always keep the latest inbound chat id for outbound send (may be @lid).
    if open_session.whatsapp_chat_id != from_id:
        open_session.whatsapp_chat_id = from_id
        dirty = True
    # Upgrade legacy/LID client_id to phone@c.us once resolved.
    if phone_chat_id and open_session.client_id != phone_chat_id:
        open_session.client_id = phone_chat_id
        dirty = True
    if dirty:
        db.commit()

    # Refresh display name when WhatsApp provides a real push name.
    if open_session.user_id is not None and push_name:
        user = db.query(User).filter(User.id == open_session.user_id).first()
        if user is not None:
            service.update_user_profile(db, user, name=push_name, phone=phone)

    needs_auto_ack = not open_session.auto_ack_sent
    raw_event = json.dumps(payload, ensure_ascii=False)

    result = service.classify_and_route(
        db,
        open_session.id,
        text,
        external_id=external_id,
        raw_event=raw_event,
    )

    if result.get("duplicate") == "1":
        return {"status": "ok", "duplicate": "true"}

    session = (
        db.query(ChatSession)
        .options(joinedload(ChatSession.assigned_agent))
        .filter(ChatSession.id == open_session.id)
        .first()
    )
    user_message = _latest_user_message(db, open_session.id)

    intent = result.get("intent_name")
    assigned_agent = result.get("agent_name")
    role = session.assigned_agent.role if session and session.assigned_agent else None

    ws_payload: dict[str, object] = {
        "session_id": open_session.id,
        "content": text,
        "role": "user",
        "intent": intent if isinstance(intent, str) else "unknown",
        "assigned_agent": assigned_agent if isinstance(assigned_agent, str) else None,
        "channel": (
            session.channel.value
            if session is not None and hasattr(session.channel, "value")
            else "whatsapp"
        ),
    }
    if user_message is not None:
        ws_payload["id"] = user_message.id
        ws_payload["created_at"] = user_message.created_at.isoformat()

    # Push board updates immediately (not only via BackgroundTasks) so the
    # admin WebSocket refreshes even if a later background job fails.
    await manager.broadcast_admin("message_new", ws_payload)
    await manager.broadcast_admin(
        "session_updated",
        {
            "id": open_session.id,
            "channel": "whatsapp",
            "client_id": client_id,
            "whatsapp_chat_id": from_id,
            "status": (
                session.status.value
                if session is not None and hasattr(session.status, "value")
                else "active"
            ),
            "intent": {"name": intent} if isinstance(intent, str) else None,
            "assigned_agent": (
                {
                    "name": assigned_agent,
                    "role": role,
                }
                if isinstance(assigned_agent, str)
                else None
            ),
        },
    )

    # Read receipt ~1.5s after server accepted the message.
    background_tasks.add_task(delayed_send_seen, from_id, external_id)

    # One-time auto-ack after first classify/route (before human admin reply).
    if needs_auto_ack and session is not None:
        background_tasks.add_task(send_auto_ack, session.id, from_id, role)

    return {"status": "ok", "session_id": str(open_session.id)}
