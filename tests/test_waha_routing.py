"""Focused tests for WhatsApp sticky routing, LID chat ids, and acks."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal, ensure_sqlite_columns
from app.main import app
from app.models import Agent, ChatChannel, ChatSession, Message, MessageRole, SessionStatus
from app.services.router import ChatService
from app.services.waha import (
    WahaError,
    extract_outbound_id,
    is_group_or_broadcast,
    is_user_chat,
    normalize_chat_id,
    normalize_phone,
    to_chat_id,
)
from app.services.whatsapp_acks import build_auto_ack_text, role_display_label, send_auto_ack


@pytest.fixture()
def client() -> TestClient:
    ensure_sqlite_columns()
    return TestClient(app)


def _hmac_headers(body: bytes) -> dict[str, str]:
    digest = hmac.new(
        settings.WAHA_HOOK_HMAC_KEY.encode("utf-8"),
        body,
        hashlib.sha512,
    ).hexdigest()
    return {"X-Webhook-Hmac": digest, "Content-Type": "application/json"}


def test_normalize_phone_and_chat_id() -> None:
    assert normalize_phone("628123456789@c.us") == "628123456789"
    assert normalize_phone("254953738227912@lid") == ""
    assert normalize_chat_id("6281@s.whatsapp.net") == "6281@c.us"
    assert to_chat_id("628123456789") == "628123456789@c.us"
    assert is_group_or_broadcast("120363@g.us") is True
    assert is_user_chat("628123@c.us") is True
    assert is_user_chat("254953738227912@lid") is True
    assert is_user_chat("120363@g.us") is False


def test_auto_ack_copy() -> None:
    assert role_display_label("support") == "Support"
    assert "tim Tech" in build_auto_ack_text("tech")
    assert "tim Support" in build_auto_ack_text(None)


def test_extract_outbound_id() -> None:
    assert extract_outbound_id({"id": "true_123"}) == "true_123"
    assert extract_outbound_id({"key": {"_serialized": "true_abc"}}) == "true_abc"
    assert extract_outbound_id({"data": {"messageId": "mid_1"}}) == "mid_1"
    assert extract_outbound_id(None) is None
    assert extract_outbound_id({}) is None


def test_find_open_whatsapp_session_matches_lid_and_phone() -> None:
    db = SessionLocal()
    try:
        svc = ChatService()
        session = svc.start_chat(
            db,
            name="Alias User",
            phone="628111222333",
            channel=ChatChannel.whatsapp,
            client_id="628111222333@c.us",
        )
        session.whatsapp_chat_id = "999888777666555@lid"
        db.commit()

        found = svc.find_open_whatsapp_session(
            db,
            chat_id="999888777666555@lid",
            phone="628111222333",
            phone_chat_id="628111222333@c.us",
        )
        assert found is not None
        assert found.id == session.id
    finally:
        db.close()


def test_sticky_classify_and_archive_reopens(client: TestClient) -> None:
    db = SessionLocal()
    try:
        svc = ChatService()
        session = svc.start_chat(
            db,
            name="Sticky User",
            phone="6287770001",
            channel=ChatChannel.whatsapp,
            client_id="6287770001@c.us",
        )
        agent_before = db.query(Agent).filter(Agent.name == "Budi").first()
        assert agent_before is not None
        load_before = agent_before.current_load

        r1 = svc.classify_and_route(db, session.id, "saya mau komplain pesanan rusak")
        r2 = svc.classify_and_route(db, session.id, "masih menunggu balasan")
        assert r1.get("agent_name") == r2.get("agent_name")
        msgs = db.query(Message).filter(Message.session_id == session.id).count()
        assert msgs == 2

        agent_after = db.query(Agent).filter(Agent.id == agent_before.id).first()
        assert agent_after is not None
        assert agent_after.current_load == load_before + 1

        res = client.post(f"/api/admin/sessions/{session.id}/archive")
        assert res.status_code == 200

        db.expire_all()
        archived = db.query(ChatSession).filter(ChatSession.id == session.id).first()
        assert archived is not None
        assert archived.status == SessionStatus.archived

        agent_closed = db.query(Agent).filter(Agent.id == agent_before.id).first()
        assert agent_closed is not None
        assert agent_closed.current_load == load_before

        # Restore must put load back; archive→delete must not double-decrement.
        res_restore = client.post(f"/api/admin/sessions/{session.id}/restore")
        assert res_restore.status_code == 200
        db.expire_all()
        agent_restored = db.query(Agent).filter(Agent.id == agent_before.id).first()
        assert agent_restored is not None
        assert agent_restored.current_load == load_before + 1

        res_archive2 = client.post(f"/api/admin/sessions/{session.id}/archive")
        assert res_archive2.status_code == 200
        db.expire_all()
        assert (
            db.query(Agent).filter(Agent.id == agent_before.id).first().current_load
            == load_before
        )

        res_del = client.delete(f"/api/admin/sessions/{session.id}")
        assert res_del.status_code == 200
        db.expire_all()
        agent_after_delete = db.query(Agent).filter(Agent.id == agent_before.id).first()
        assert agent_after_delete is not None
        assert agent_after_delete.current_load == load_before
    finally:
        db.close()


def test_webhook_rejects_missing_hmac(client: TestClient) -> None:
    payload = {"event": "message", "payload": {"from": "6281@c.us", "body": "hi", "fromMe": False}}
    res = client.post("/api/webhooks/waha", json=payload)
    assert res.status_code == 401


@patch("app.services.whatsapp_acks.WahaClient")
@patch("app.router.waha.delayed_send_seen", new_callable=MagicMock)
def test_webhook_lid_stores_chat_id_and_acks_once(
    mock_delayed_seen: MagicMock,
    mock_waha_cls: MagicMock,
    client: TestClient,
) -> None:
    mock_client = MagicMock()
    mock_client.send_text.return_value = {"id": "true_auto_ack_out"}
    mock_waha_cls.return_value = mock_client

    # Make BackgroundTasks run send_auto_ack with our mock client.
    async def _immediate_auto_ack(session_id: int, chat_id: str, role: str | None) -> None:
        from app.services.whatsapp_acks import send_auto_ack

        await send_auto_ack(session_id, chat_id, role)

    lid = f"{uuid.uuid4().int % 10**15}@lid"
    msg_a = f"true_{lid}_AAA"
    msg_b = f"true_{lid}_BBB"

    with patch("app.router.waha.send_auto_ack", side_effect=_immediate_auto_ack):
        body_dict = {
            "event": "message",
            "session": "default",
            "payload": {
                "id": msg_a,
                "from": lid,
                "fromMe": False,
                "body": "saya mau komplain barang rusak",
            },
        }
        raw = json.dumps(body_dict).encode("utf-8")
        res = client.post("/api/webhooks/waha", content=raw, headers=_hmac_headers(raw))
        assert res.status_code == 200, res.json()
        session_id = int(res.json()["session_id"])

    db = SessionLocal()
    try:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        assert session is not None
        assert session.whatsapp_chat_id == lid
        assert session.client_id == lid
        assert session.auto_ack_sent is True
        assert session.user is None or session.user.phone is None
        ack = (
            db.query(Message)
            .filter(Message.session_id == session.id, Message.role == MessageRole.agent)
            .first()
        )
        assert ack is not None
        assert ack.external_id == "true_auto_ack_out"
        assert "Terimakasih sudah menghubungi kami" in ack.content
    finally:
        db.close()

    mock_client.send_text.assert_called()
    ack_chat_id = mock_client.send_text.call_args.args[0]
    assert ack_chat_id == lid
    assert "tim Support" in mock_client.send_text.call_args.args[1]

    mock_delayed_seen.assert_called()
    assert mock_delayed_seen.call_args.args[0] == lid
    assert mock_delayed_seen.call_args.args[1] == msg_a

    # Sticky second message: no second auto-ack
    mock_client.reset_mock()
    with patch("app.router.waha.send_auto_ack") as mock_ack:
        body2 = dict(body_dict)
        body2["payload"] = dict(body_dict["payload"])
        body2["payload"]["id"] = msg_b
        body2["payload"]["body"] = "tolong diproses"
        raw2 = json.dumps(body2).encode("utf-8")
        res2 = client.post("/api/webhooks/waha", content=raw2, headers=_hmac_headers(raw2))
        assert res2.status_code == 200
        assert res2.json()["session_id"] == str(session_id)
        mock_ack.assert_not_called()


@patch("app.services.whatsapp_acks.WahaClient")
def test_auto_ack_does_not_persist_when_send_fails(mock_waha_cls: MagicMock) -> None:
    import asyncio

    mock_client = MagicMock()
    mock_client.send_text.side_effect = WahaError("boom", status_code=500)
    mock_waha_cls.return_value = mock_client

    db = SessionLocal()
    try:
        svc = ChatService()
        session = svc.start_chat(
            db,
            name="Fail Ack",
            phone="628999000111",
            channel=ChatChannel.whatsapp,
            client_id="628999000111@c.us",
        )
        session.whatsapp_chat_id = "628999000111@c.us"
        db.commit()
        session_id = session.id
    finally:
        db.close()

    asyncio.run(send_auto_ack(session_id, "628999000111@c.us", "support"))

    db = SessionLocal()
    try:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        assert session is not None
        assert session.auto_ack_sent is False
        agents = (
            db.query(Message)
            .filter(Message.session_id == session_id, Message.role == MessageRole.agent)
            .count()
        )
        assert agents == 0
    finally:
        db.close()


@patch("app.router.admin.WahaClient")
def test_admin_reply_uses_stored_lid_chat_id(mock_waha_cls: MagicMock, client: TestClient) -> None:
    mock_client = MagicMock()
    mock_client.send_text.return_value = {"id": "true_admin_out"}
    mock_waha_cls.return_value = mock_client

    lid = f"{uuid.uuid4().int % 10**15}@lid"
    db = SessionLocal()
    try:
        svc = ChatService()
        session = svc.start_chat(
            db,
            name="LID User",
            phone=None,
            channel=ChatChannel.whatsapp,
            client_id=lid,
        )
        session.whatsapp_chat_id = lid
        session.auto_ack_sent = True
        db.commit()
        session_id = session.id
    finally:
        db.close()

    res = client.post(
        "/api/admin/reply",
        json={"session_id": session_id, "content": "ya bisa dijelaskan kendalanya"},
    )
    assert res.status_code == 200
    mock_client.send_text.assert_called_once()
    assert mock_client.send_text.call_args.args[0] == lid
    assert mock_client.send_text.call_args.args[1] == "ya bisa dijelaskan kendalanya"
    assert res.json()["reply"]["external_id"] == "true_admin_out"


@patch("app.router.admin.WahaClient")
def test_admin_reply_fails_without_db_message(mock_waha_cls: MagicMock, client: TestClient) -> None:
    mock_client = MagicMock()
    mock_client.send_text.side_effect = WahaError("nope", status_code=502)
    mock_waha_cls.return_value = mock_client

    db = SessionLocal()
    try:
        svc = ChatService()
        session = svc.start_chat(
            db,
            name="No Send",
            phone="628111000222",
            channel=ChatChannel.whatsapp,
            client_id="628111000222@c.us",
        )
        session.whatsapp_chat_id = "628111000222@c.us"
        db.commit()
        session_id = session.id
        before = db.query(Message).filter(Message.session_id == session_id).count()
    finally:
        db.close()

    res = client.post(
        "/api/admin/reply",
        json={"session_id": session_id, "content": "halo"},
    )
    assert res.status_code == 502

    db = SessionLocal()
    try:
        after = db.query(Message).filter(Message.session_id == session_id).count()
        assert after == before
    finally:
        db.close()


@patch("app.services.whatsapp_acks.WahaClient")
@patch("app.router.waha.delayed_send_seen", new_callable=MagicMock)
@patch("app.router.waha.send_auto_ack", new_callable=MagicMock)
def test_webhook_sticky_and_dedup(
    _mock_ack: MagicMock,
    _mock_seen: MagicMock,
    _mock_waha: MagicMock,
    client: TestClient,
) -> None:
    chat = f"628{uuid.uuid4().int % 10**10}@c.us"
    msg_a = f"true_{chat}_AAA_{uuid.uuid4().hex[:8]}"
    msg_b = f"true_{chat}_BBB_{uuid.uuid4().hex[:8]}"

    body_dict = {
        "event": "message",
        "session": "default",
        "payload": {
            "id": msg_a,
            "from": chat,
            "fromMe": False,
            "body": "saya mau komplain barang rusak",
        },
    }
    raw = json.dumps(body_dict).encode("utf-8")
    res = client.post("/api/webhooks/waha", content=raw, headers=_hmac_headers(raw))
    assert res.status_code == 200
    assert "session_id" in res.json(), res.json()
    session_id = res.json()["session_id"]

    body2 = dict(body_dict)
    body2["payload"] = dict(body_dict["payload"])
    body2["payload"]["id"] = msg_b
    body2["payload"]["body"] = "tolong diproses"
    raw2 = json.dumps(body2).encode("utf-8")
    res2 = client.post("/api/webhooks/waha", content=raw2, headers=_hmac_headers(raw2))
    assert res2.status_code == 200
    assert res2.json()["session_id"] == session_id

    res3 = client.post("/api/webhooks/waha", content=raw, headers=_hmac_headers(raw))
    assert res3.status_code == 200
    assert res3.json().get("duplicate") == "true"

    db = SessionLocal()
    try:
        session = db.query(ChatSession).filter(ChatSession.id == int(session_id)).first()
        assert session is not None
        assert session.whatsapp_chat_id == chat
        msgs = db.query(Message).filter(Message.session_id == int(session_id)).count()
        assert msgs == 2
    finally:
        db.close()


def test_webhook_ignores_from_me_and_groups(client: TestClient) -> None:
    from_me = {
        "event": "message",
        "payload": {"id": "x1", "from": "6281@c.us", "fromMe": True, "body": "hi"},
    }
    raw = json.dumps(from_me).encode("utf-8")
    res = client.post("/api/webhooks/waha", content=raw, headers=_hmac_headers(raw))
    assert res.status_code == 200
    assert res.json().get("reason") == "from_me"

    group = {
        "event": "message",
        "payload": {"id": "x2", "from": "120363@g.us", "fromMe": False, "body": "hi"},
    }
    raw = json.dumps(group).encode("utf-8")
    res = client.post("/api/webhooks/waha", content=raw, headers=_hmac_headers(raw))
    assert res.status_code == 200
    assert res.json().get("reason") == "non_user_chat"
