"""SQLAlchemy-Modelle. Laufen unveraendert auf SQLite und PostgreSQL."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Auf PostgreSQL JSONB (indizierbar), sonst der portable JSON-Typ.
JSONType = JSON().with_variant(JSONB(), "postgresql")

# BIGSERIAL/BIGINT gibt es in SQLite nicht als Autoincrement-PK, daher Variante.
PKType = BigInteger().with_variant(Integer(), "sqlite")


def utcnow() -> datetime:
    """Zeitzonen-bewusstes Jetzt in UTC."""
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    """SQLite liefert naive Datetimes zurueck; die gelten hier als UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class Resource(Base):
    """Ein gespeicherter Link."""

    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    # Die Spec fordert UNIQUE, erlaubt bei Duplikaten aber ausdruecklich
    # "Separat speichern". Deshalb nur ein Index, kein Unique-Constraint.
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    title: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)

    # Denormalisierte Tags als "|ai/agents|tools|" fuer portable LIKE-Suche.
    tags_text: Mapped[str] = mapped_column(Text, nullable=False, default="||")

    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="website")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    # "metadata" ist auf Declarative-Klassen reserviert, daher das Attribut "meta".
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict
    )

    __table_args__ = (
        Index("ix_resources_user_status_created", "user_id", "status", "created_at"),
        Index("ix_resources_user_hash", "user_id", "url_hash"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialisierbare Form fuer Exporte."""
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "tags": list(self.tags or []),
            "notes": self.notes,
            "source": self.source,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


class ResourceDuplicate(Base):
    """Verknuepft ein bewusst separat gespeichertes Duplikat mit dem Original."""

    __tablename__ = "resource_duplicates"

    original_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True
    )
    duplicate_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True
    )
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TagStat(Base):
    """Zaehler und Co-Occurrences pro Tag.

    Die Spec zeigt ``tag`` als alleinigen Primaerschluessel, fragt spaeter aber
    mit ``user_id`` ab. Der zusammengesetzte Schluessel loest diesen Widerspruch.
    """

    __tablename__ = "tag_stats"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tag: Mapped[str] = mapped_column(String(128), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    co_occurrences: Mapped[dict[str, int]] = mapped_column(
        JSONType, nullable=False, default=dict
    )


class ExportLog(Base):
    """Protokoll der versendeten Exporte."""

    __tablename__ = "export_logs"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    export_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    link_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
