from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_sqlite_columns() -> None:
    """Add new columns on existing SQLite DBs (create_all does not migrate)."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    alters: list[str] = []
    indexes: list[str] = []

    if "users" in tables:
        user_cols = {col["name"] for col in inspector.get_columns("users")}
        if "phone" not in user_cols:
            alters.append("ALTER TABLE users ADD COLUMN phone VARCHAR(32)")
            indexes.append(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone ON users (phone)"
            )

    if "chat_sessions" in tables:
        session_cols = {col["name"] for col in inspector.get_columns("chat_sessions")}
        if "channel" not in session_cols:
            alters.append(
                "ALTER TABLE chat_sessions ADD COLUMN channel VARCHAR(20) "
                "NOT NULL DEFAULT 'whatsapp'"
            )
        if "whatsapp_chat_id" not in session_cols:
            alters.append("ALTER TABLE chat_sessions ADD COLUMN whatsapp_chat_id VARCHAR(128)")
            indexes.append(
                "CREATE INDEX IF NOT EXISTS ix_chat_sessions_whatsapp_chat_id "
                "ON chat_sessions (whatsapp_chat_id)"
            )
        if "auto_ack_sent" not in session_cols:
            alters.append(
                "ALTER TABLE chat_sessions ADD COLUMN auto_ack_sent BOOLEAN NOT NULL DEFAULT 0"
            )

    if "messages" in tables:
        message_cols = {col["name"] for col in inspector.get_columns("messages")}
        if "external_id" not in message_cols:
            alters.append("ALTER TABLE messages ADD COLUMN external_id VARCHAR(255)")
            indexes.append(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_messages_external_id "
                "ON messages (external_id)"
            )
        if "raw_event" not in message_cols:
            alters.append("ALTER TABLE messages ADD COLUMN raw_event TEXT")

    if not alters and not indexes:
        return

    with engine.begin() as conn:
        for stmt in alters:
            conn.execute(text(stmt))
        for stmt in indexes:
            conn.execute(text(stmt))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
