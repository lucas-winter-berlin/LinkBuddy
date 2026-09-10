from datetime import datetime, timedelta, timezone

import pytest

from linkbuddy.db import Database, ResourceRepository
from linkbuddy.services.export import build_export


USER = 42


async def _seed(repo: ResourceRepository, **overrides):
    defaults = {
        "user_id": USER,
        "url": "https://example.com/a",
        "url_hash": "hash-a",
        "tags": ["ai/agents", "tools"],
        "title": "Agents",
        "notes": "Notiz",
        "source": "website",
    }
    defaults.update(overrides)
    return await repo.create(**defaults)


@pytest.mark.asyncio
async def test_create_search_and_duplicate(db: Database):
    async with db.session() as session:
        repo = ResourceRepository(session)
        await _seed(repo)
        page = await repo.search(USER, "agents")
        assert page.total == 1
        assert page.items[0].title == "Agents"

        dup = await repo.find_duplicate(USER, "hash-a")
        assert dup is not None


@pytest.mark.asyncio
async def test_tag_hierarchy_and_counts(db: Database):
    async with db.session() as session:
        repo = ResourceRepository(session)
        await _seed(repo, url="https://a.test", url_hash="h1", tags=["ai/agents"])
        await _seed(repo, url="https://b.test", url_hash="h2", tags=["ai/evals", "tools"])
        await _seed(repo, url="https://c.test", url_hash="h3", tags=["berlin"])

        page = await repo.by_tag(USER, "ai")
        assert page.total == 2

        counts = await repo.tag_counts(USER)
        assert counts["ai/agents"] == 1
        assert counts["tools"] == 1

        tree = await repo.tag_tree(USER)
        assert tree["ai"]["_total"] == 2
        assert tree["ai"]["ai/agents"] == 1


@pytest.mark.asyncio
async def test_tag_stats_and_related(db: Database):
    async with db.session() as session:
        repo = ResourceRepository(session)
        resource = await _seed(
            repo, tags=["ai/agents", "ai/evals"], url="https://x.test", url_hash="hx"
        )
        related = await repo.related_tags(USER, "ai/agents")
        assert related[0][0] == "ai/evals"

        await repo.update_content(resource, tags=["tools"])
        related_after = await repo.related_tags(USER, "ai/agents")
        assert related_after == []

        known = await repo.known_tags(USER)
        assert "tools" in known
        assert "ai/agents" not in known


@pytest.mark.asyncio
async def test_soft_delete_hides_from_search(db: Database):
    async with db.session() as session:
        repo = ResourceRepository(session)
        resource = await _seed(repo)
        await repo.soft_delete(resource)
        page = await repo.search(USER, "agents")
        assert page.total == 0
        assert await repo.get(USER, resource.id) is None


@pytest.mark.asyncio
async def test_period_and_timeline(db: Database):
    now = datetime.now(timezone.utc)
    async with db.session() as session:
        repo = ResourceRepository(session)
        recent = await _seed(repo, url="https://new.test", url_hash="hn", tags=["ai"])
        recent.created_at = now - timedelta(hours=1)
        old = await _seed(
            repo, url="https://old.test", url_hash="ho", tags=["ai"], title="Alt"
        )
        old.created_at = now - timedelta(days=40)
        await session.flush()

        week = await repo.by_period(USER, since=now - timedelta(days=7), limit=10)
        assert week.total == 1

        buckets = await repo.timeline(USER, "ai", weeks=12)
        assert sum(count for _, count in buckets) == 2


@pytest.mark.asyncio
async def test_similar_and_export(db: Database):
    async with db.session() as session:
        repo = ResourceRepository(session)
        source = await _seed(
            repo, url="https://src.test", url_hash="hs", tags=["ai/agents", "ai/evals"]
        )
        await _seed(
            repo, url="https://sim.test", url_hash="hm", tags=["ai/agents", "tools"], title="Sim"
        )
        await _seed(repo, url="https://other.test", url_hash="ho", tags=["berlin"])

        matches = await repo.similar(USER, source, limit=5)
        assert len(matches) == 1
        assert matches[0][1] == ["ai/agents"]

        resources = await repo.list_for_export(USER, tag="ai")
        export = build_export(resources, fmt="json", tag_filter="ai")
        assert b"ai/agents" in export.content
        assert export.filename.endswith(".json")

        md = build_export(resources, fmt="markdown", tag_filter="ai")
        assert b"# Ressourcen Export" in md.content
