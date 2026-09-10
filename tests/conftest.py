"""Gemeinsame Pytest-Fixtures."""

from __future__ import annotations

import pytest

from linkbuddy.db import Database, ResourceRepository


@pytest.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    await database.create_schema()
    try:
        yield database
    finally:
        await database.dispose()


@pytest.fixture
async def repo(db: Database):
    async with db.session() as session:
        yield ResourceRepository(session)
