"""Delayed read receipts and one-time WhatsApp auto-ack helpers."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from app.database import SessionLocal
from app.models import ChatSession, Message, MessageRole
from app.services.waha import WahaClient, WahaError, extract_outbound_id
from app.ws.manager import manager

logger = logging.getLogger(__name__)

READ_RECEIPT_DELAY_SECONDS = 1.5

ROLE_LABELS = {
    "support": "Support",
    "tech": "Tech",
    "marketing": "Marketing",
    "finance": "Finance",
    "logistik": "Logistik",
}


def role_display_label(role: str | None) -> str:
    if not role:
        return "Support"
    return ROLE_LABELS.get(role.lower(), role.title())


def build_auto_ack_text(role: str | None) -> str:
    label = role_display_label(role)
    return (
        "Terimakasih sudah menghubungi kami, Pesan anda sudah kami terima "
        f"dan sudah kami alihkan ke tim {label}"
    )


async def delayed_send_seen(chat_id: str, message_id: str | None) -> None:
    await asyncio.sleep(READ_RECEIPT_DELAY_SECONDS)
    try:
        client = WahaClient()
        message_ids = [message_id] if message_id else None
        await asyncio.to_thread(client.send_seen, chat_id, message_ids=message_ids)
    except Exception:
        logger.exception("Failed to send WhatsApp read receipt for %s", chat_id)


def _claim_auto_ack(db, session_id: int) -> bool:
    """Atomically claim one-time auto-ack. Returns True if this caller owns the send."""
    result = db.execute(
        text(
            "UPDATE chat_sessions SET auto_ack_sent = 1 "
            "WHERE id = :id AND auto_ack_sent = 0"
        ),
        {"id": session_id},
    )
    db.commit()
    return bool(result.rowcount and result.rowcount > 0)


def _release_auto_ack_claim(db, session_id: int) -> None:
    """Allow retry after a failed sendText."""
    db.execute(
        text("UPDATE chat_sessions SET auto_ack_sent = 0 WHERE id = :id"),
        {"id": session_id},
    )
    db.commit()


async def send_auto_ack(session_id: int, chat_id: str, role: str | None) -> None:
    """Send one-time auto-ack via WAHA; persist Message only after sendText succeeds.

    Claims auto_ack_sent before network I/O so concurrent webhooks cannot double-send.
    On send failure the claim is released so a later message can retry.
    """
    db = SessionLocal()
    claimed = False
    try:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session is None:
            return

        if not _claim_auto_ack(db, session_id):
            return
        claimed = True

        text_body = build_auto_ack_text(role)
        client = WahaClient()
        try:
            result = await asyncio.to_thread(client.send_text, chat_id, text_body)
        except WahaError as exc:
            logger.error(
                "WhatsApp auto-ack sendText failed session_id=%s chat_id=%s status=%s error=%s",
                session_id,
                chat_id,
                getattr(exc, "status_code", None),
                exc,
            )
            _release_auto_ack_claim(db, session_id)
            claimed = False
            return

        outbound_id = extract_outbound_id(result if isinstance(result, dict) else None)
        logger.info(
            "WhatsApp auto-ack sent session_id=%s chat_id=%s external_id=%s",
            session_id,
            chat_id,
            outbound_id,
        )

        db.refresh(session)
        ack = Message(
            session_id=session.id,
            role=MessageRole.agent,
            content=text_body,
            external_id=outbound_id,
        )
        db.add(ack)
        db.commit()
        db.refresh(ack)

        await manager.broadcast_admin(
            "message_new",
            {
                "id": ack.id,
                "session_id": session.id,
                "role": "agent",
                "content": text_body,
                "external_id": outbound_id,
                "created_at": ack.created_at.isoformat() if ack.created_at else None,
                "auto_ack": True,
            },
        )
    except Exception:
        logger.exception("Auto-ack handling failed for session %s chat_id=%s", session_id, chat_id)
        db.rollback()
        if claimed:
            try:
                _release_auto_ack_claim(db, session_id)
            except Exception:
                logger.exception("Failed to release auto-ack claim for session %s", session_id)
    finally:
        db.close()
