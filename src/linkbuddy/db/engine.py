"""Engine- und Session-Verwaltung."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base


class Database:
    """Haelt Engine und Session-Factory und legt bei Bedarf das Schema an."""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        connect_args: dict[str, object] = {}
        if url.startswith("sqlite"):
            connect_args["timeout"] = 30
        self.engine: AsyncEngine = create_async_engine(
            url, echo=echo, pool_pre_ping=True, connect_args=connect_args
        )
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    async def create_schema(self) -> None:
        """Legt fehlende Tabellen an. Ersetzt fuer den MVP ein Migrationstool."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Session mit Commit bei Erfolg und Rollback bei Fehler."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        await self.engine.dispose()
