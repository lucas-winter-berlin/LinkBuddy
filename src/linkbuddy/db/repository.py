"""Datenzugriff. Alle Queries sind bewusst so formuliert, dass sie sowohl auf
SQLite als auch auf PostgreSQL laufen: keine JSON-Operatoren, kein ILIKE, keine
DATE_TRUNC. Zeitfenster werden in Python berechnet, Tag-Filter laufen ueber das
denormalisierte Feld ``tags_text``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Sequence

from sqlalchemy import ColumnElement, Select, delete, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.tags import tags_to_text
from .models import ExportLog, Resource, ResourceDuplicate, TagStat, ensure_utc, utcnow

Period = Literal["all", "heute", "woche", "monat", "jahr"]

LIKE_ESCAPE = "\\"


def _escape_like(value: str) -> str:
    """Maskiert LIKE-Wildcards, damit "100%" nicht alles matcht."""
    return (
        value.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


@dataclass(frozen=True)
class Page:
    """Ein Ausschnitt einer Ergebnisliste."""

    items: list[Resource]
    total: int
    offset: int
    limit: int

    @property
    def page_number(self) -> int:
        return self.offset // self.limit + 1 if self.limit else 1

    @property
    def page_count(self) -> int:
        if not self.limit:
            return 1
        return max(1, -(-self.total // self.limit))

    @property
    def has_next(self) -> bool:
        return self.offset + len(self.items) < self.total

    @property
    def has_prev(self) -> bool:
        return self.offset > 0


class ResourceRepository:
    """Alle Lese- und Schreibzugriffe auf die Ressourcen eines Users."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Schreiben
    # ------------------------------------------------------------------

    async def create(
        self,
        *,
        user_id: int,
        url: str,
        url_hash: str,
        tags: list[str],
        title: str | None = None,
        notes: str | None = None,
        source: str = "website",
        meta: dict[str, Any] | None = None,
    ) -> Resource:
        now = utcnow()
        resource = Resource(
            user_id=user_id,
            url=url,
            url_hash=url_hash,
            title=title,
            tags=list(tags),
            tags_text=tags_to_text(tags),
            notes=notes,
            source=source,
            meta=meta or {},
            created_at=now,
            updated_at=now,
            status="active",
        )
        self.session.add(resource)
        await self.session.flush()
        await self.apply_tag_delta(user_id, [], tags, when=now)
        return resource

    async def update_content(
        self,
        resource: Resource,
        *,
        tags: list[str] | None = None,
        notes: str | None = None,
        title: str | None = None,
        url: str | None = None,
        url_hash: str | None = None,
    ) -> Resource:
        """Aendert Inhalte und haelt die Tag-Statistik synchron."""
        old_tags = list(resource.tags or [])
        if tags is not None:
            resource.tags = list(tags)
            resource.tags_text = tags_to_text(tags)
        if notes is not None:
            resource.notes = notes or None
        if title is not None:
            resource.title = title
        if url is not None:
            resource.url = url
        if url_hash is not None:
            resource.url_hash = url_hash
        resource.updated_at = utcnow()
        await self.session.flush()
        if tags is not None:
            await self.apply_tag_delta(
                resource.user_id, old_tags, list(tags), when=resource.updated_at
            )
        return resource

    async def soft_delete(self, resource: Resource) -> None:
        """Setzt Status auf 'deleted'; der Datensatz bleibt fuer Audits erhalten."""
        now = utcnow()
        resource.status = "deleted"
        resource.deleted_at = now
        resource.updated_at = now
        await self.session.flush()
        await self.apply_tag_delta(resource.user_id, list(resource.tags or []), [], when=now)

    async def link_duplicate(self, original_id: int, duplicate_id: int) -> None:
        self.session.add(
            ResourceDuplicate(
                original_id=original_id, duplicate_id=duplicate_id, merged_at=utcnow()
            )
        )
        await self.session.flush()

    # ------------------------------------------------------------------
    # Einzelne Datensaetze
    # ------------------------------------------------------------------

    async def get(self, user_id: int, resource_id: int) -> Resource | None:
        stmt = select(Resource).where(
            Resource.id == resource_id,
            Resource.user_id == user_id,
            Resource.status == "active",
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_duplicate(self, user_id: int, url_hash: str) -> Resource | None:
        """Aeltester aktiver Treffer mit gleichem URL-Hash."""
        stmt = (
            select(Resource)
            .where(
                Resource.user_id == user_id,
                Resource.url_hash == url_hash,
                Resource.status == "active",
            )
            .order_by(Resource.created_at.asc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    # ------------------------------------------------------------------
    # Listen und Suche
    # ------------------------------------------------------------------

    def _base(self, user_id: int) -> Select[tuple[Resource]]:
        return select(Resource).where(
            Resource.user_id == user_id, Resource.status == "active"
        )

    async def _paginate(
        self,
        condition: ColumnElement[bool],
        *,
        user_id: int,
        order_by: Any,
        limit: int,
        offset: int,
    ) -> Page:
        total = (
            await self.session.execute(
                select(func.count())
                .select_from(Resource)
                .where(Resource.user_id == user_id, Resource.status == "active", condition)
            )
        ).scalar_one()
        rows = (
            await self.session.execute(
                self._base(user_id).where(condition).order_by(order_by).limit(limit).offset(offset)
            )
        ).scalars().all()
        return Page(items=list(rows), total=int(total), offset=offset, limit=limit)

    async def search(
        self, user_id: int, keyword: str, *, limit: int = 5, offset: int = 0
    ) -> Page:
        """Volltextsuche ueber URL, Titel, Tags und Notiz."""
        pattern = f"%{_escape_like(keyword.lower())}%"
        condition = or_(
            func.lower(Resource.url).like(pattern, escape=LIKE_ESCAPE),
            func.lower(Resource.tags_text).like(pattern, escape=LIKE_ESCAPE),
            func.lower(func.coalesce(Resource.notes, "")).like(pattern, escape=LIKE_ESCAPE),
            func.lower(func.coalesce(Resource.title, "")).like(pattern, escape=LIKE_ESCAPE),
        )
        return await self._paginate(
            condition,
            user_id=user_id,
            order_by=Resource.updated_at.desc(),
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def tag_condition(tag: str) -> ColumnElement[bool]:
        """Trifft das Tag selbst und alle Untertags (#ai findet #ai/evals)."""
        exact = f"%|{_escape_like(tag)}|%"
        children = f"%|{_escape_like(tag)}/%"
        return or_(
            Resource.tags_text.like(exact, escape=LIKE_ESCAPE),
            Resource.tags_text.like(children, escape=LIKE_ESCAPE),
        )

    async def by_tag(
        self, user_id: int, tag: str, *, limit: int = 5, offset: int = 0
    ) -> Page:
        return await self._paginate(
            self.tag_condition(tag),
            user_id=user_id,
            order_by=Resource.created_at.desc(),
            limit=limit,
            offset=offset,
        )

    async def by_period(
        self,
        user_id: int,
        *,
        since: datetime | None = None,
        limit: int = 5,
        offset: int = 0,
    ) -> Page:
        condition = Resource.created_at >= since if since is not None else true()
        return await self._paginate(
            condition,
            user_id=user_id,
            order_by=Resource.created_at.desc(),
            limit=limit,
            offset=offset,
        )

    async def list_for_export(
        self,
        user_id: int,
        *,
        tag: str | None = None,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[Resource]:
        stmt = self._base(user_id).order_by(Resource.created_at.asc())
        if tag:
            stmt = stmt.where(self.tag_condition(tag))
        if since is not None:
            stmt = stmt.where(Resource.created_at >= since)
        if limit:
            stmt = stmt.limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def similar(self, user_id: int, resource: Resource, *, limit: int = 5) -> list[
        tuple[Resource, list[str]]
    ]:
        """Links mit mindestens einem gemeinsamen Tag, sortiert nach Ueberlappung."""
        source_tags = set(resource.tags or [])
        if not source_tags:
            return []
        condition = or_(*[self.tag_condition(t) for t in source_tags])
        rows = (
            await self.session.execute(
                self._base(user_id).where(condition, Resource.id != resource.id)
            )
        ).scalars().all()

        scored: list[tuple[int, Resource, list[str]]] = []
        for row in rows:
            shared = [t for t in (row.tags or []) if t in source_tags]
            if shared:
                scored.append((len(shared), row, shared))
        scored.sort(key=lambda item: (-item[0], -ensure_utc(item[1].created_at).timestamp()))
        return [(row, shared) for _, row, shared in scored[:limit]]

    # ------------------------------------------------------------------
    # Aggregationen
    # ------------------------------------------------------------------

    async def count(self, user_id: int, *, since: datetime | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(Resource)
            .where(Resource.user_id == user_id, Resource.status == "active")
        )
        if since is not None:
            stmt = stmt.where(Resource.created_at >= since)
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_between(self, user_id: int, start: datetime, end: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(Resource)
            .where(
                Resource.user_id == user_id,
                Resource.status == "active",
                Resource.created_at >= start,
                Resource.created_at < end,
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_tagged(
        self,
        user_id: int,
        tag: str,
        *,
        since: datetime | None = None,
        before: datetime | None = None,
    ) -> int:
        """Anzahl aktiver Links mit diesem Tag (inkl. Untertags) im Zeitfenster."""
        stmt = (
            select(func.count())
            .select_from(Resource)
            .where(
                Resource.user_id == user_id,
                Resource.status == "active",
                self.tag_condition(tag),
            )
        )
        if since is not None:
            stmt = stmt.where(Resource.created_at >= since)
        if before is not None:
            stmt = stmt.where(Resource.created_at < before)
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_by_source(self, user_id: int) -> list[tuple[str, int]]:
        stmt = (
            select(Resource.source, func.count())
            .where(Resource.user_id == user_id, Resource.status == "active")
            .group_by(Resource.source)
            .order_by(func.count().desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [(str(source), int(cnt)) for source, cnt in rows]

    async def oldest_created_at(self, user_id: int) -> datetime | None:
        stmt = (
            select(Resource.created_at)
            .where(Resource.user_id == user_id, Resource.status == "active")
            .order_by(Resource.created_at.asc())
            .limit(1)
        )
        value = (await self.session.execute(stmt)).scalars().first()
        return ensure_utc(value) if value else None

    async def _tag_rows(
        self, user_id: int, *, since: datetime | None = None, tag: str | None = None
    ) -> list[tuple[list[str], datetime]]:
        stmt = select(Resource.tags, Resource.created_at).where(
            Resource.user_id == user_id, Resource.status == "active"
        )
        if since is not None:
            stmt = stmt.where(Resource.created_at >= since)
        if tag:
            stmt = stmt.where(self.tag_condition(tag))
        rows = (await self.session.execute(stmt)).all()
        return [(list(tags or []), ensure_utc(created)) for tags, created in rows]

    async def tag_counts(
        self, user_id: int, *, since: datetime | None = None
    ) -> Counter[str]:
        """Zaehlt jedes Tag genau einmal pro Link (ohne Praefix-Rollup)."""
        counter: Counter[str] = Counter()
        for tags, _ in await self._tag_rows(user_id, since=since):
            counter.update(set(tags))
        return counter

    async def tag_tree(
        self, user_id: int, *, since: datetime | None = None
    ) -> dict[str, dict[str, int]]:
        """Gruppiert Tags nach oberster Ebene.

        Rueckgabe: {"ai": {"_total": 23, "ai/agents": 8, ...}}. ``_total`` zaehlt
        jeden Link nur einmal, auch wenn er mehrere #ai/*-Tags traegt.
        """
        totals: dict[str, set[int]] = defaultdict(set)
        exact: Counter[str] = Counter()
        stmt = select(Resource.id, Resource.tags).where(
            Resource.user_id == user_id, Resource.status == "active"
        )
        if since is not None:
            stmt = stmt.where(Resource.created_at >= since)
        for resource_id, tags in (await self.session.execute(stmt)).all():
            for tag in set(tags or []):
                exact[tag] += 1
                totals[tag.split("/")[0]].add(resource_id)

        tree: dict[str, dict[str, int]] = {}
        for root, ids in totals.items():
            branch = {"_total": len(ids)}
            for tag, cnt in exact.items():
                if tag == root or tag.startswith(root + "/"):
                    branch[tag] = cnt
            tree[root] = branch
        return dict(sorted(tree.items(), key=lambda kv: (-kv[1]["_total"], kv[0])))

    async def timeline(
        self, user_id: int, tag: str, *, weeks: int = 12
    ) -> list[tuple[datetime, int]]:
        """Links pro ISO-Woche fuer ein Tag, neueste zuerst."""
        rows = await self._tag_rows(user_id, tag=tag)
        buckets: Counter[datetime] = Counter()
        for _, created in rows:
            monday = created - timedelta(days=created.weekday())
            buckets[monday.replace(hour=0, minute=0, second=0, microsecond=0)] += 1
        ordered = sorted(buckets.items(), key=lambda kv: kv[0], reverse=True)
        return ordered[:weeks]

    async def related_tags(self, user_id: int, tag: str) -> list[tuple[str, int]]:
        """Tags, die haeufig gemeinsam mit `tag` vergeben werden."""
        counter: Counter[str] = Counter()
        for tags, _ in await self._tag_rows(user_id, tag=tag):
            unique = set(tags)
            for other in unique:
                if other != tag and not other.startswith(tag + "/"):
                    counter[other] += 1
        return counter.most_common()

    async def last_used(self, user_id: int, tag: str) -> datetime | None:
        stmt = (
            select(Resource.created_at)
            .where(
                Resource.user_id == user_id,
                Resource.status == "active",
                self.tag_condition(tag),
            )
            .order_by(Resource.created_at.desc())
            .limit(1)
        )
        value = (await self.session.execute(stmt)).scalars().first()
        return ensure_utc(value) if value else None

    # ------------------------------------------------------------------
    # Tag-Statistik (Co-Occurrences)
    # ------------------------------------------------------------------

    async def apply_tag_delta(
        self, user_id: int, old_tags: Sequence[str], new_tags: Sequence[str], *, when: datetime
    ) -> None:
        """Verrechnet einen Tag-Wechsel in tag_stats.

        Wird von jedem Schreibpfad aufgerufen, damit Zaehler und
        Co-Occurrences nicht auseinanderlaufen.
        """
        old_set, new_set = set(old_tags), set(new_tags)
        if old_set == new_set:
            return

        touched = old_set | new_set
        existing = {
            row.tag: row
            for row in (
                await self.session.execute(
                    select(TagStat).where(TagStat.user_id == user_id, TagStat.tag.in_(touched))
                )
            ).scalars()
        }

        def stat_for(tag: str) -> TagStat:
            row = existing.get(tag)
            if row is None:
                row = TagStat(user_id=user_id, tag=tag, count=0, co_occurrences={})
                self.session.add(row)
                existing[tag] = row
            return row

        for tag in new_set - old_set:
            row = stat_for(tag)
            row.count += 1
            row.last_used = when
        for tag in old_set - new_set:
            row = stat_for(tag)
            row.count = max(0, row.count - 1)

        def adjust_pairs(tags: set[str], step: int) -> None:
            for left in tags:
                row = stat_for(left)
                counts = dict(row.co_occurrences or {})
                for right in tags:
                    if left == right:
                        continue
                    counts[right] = counts.get(right, 0) + step
                    if counts[right] <= 0:
                        counts.pop(right, None)
                row.co_occurrences = counts

        adjust_pairs(old_set, -1)
        adjust_pairs(new_set, +1)

        await self.session.flush()
        stale = [tag for tag, row in existing.items() if row.count <= 0]
        if stale:
            await self.session.execute(
                delete(TagStat).where(TagStat.user_id == user_id, TagStat.tag.in_(stale))
            )

    async def known_tags(self, user_id: int, *, limit: int = 200) -> list[str]:
        """Bekannte Tags des Users, haeufigste zuerst -- Basis fuer Auto-Tagging."""
        stmt = (
            select(TagStat.tag)
            .where(TagStat.user_id == user_id, TagStat.count > 0)
            .order_by(TagStat.count.desc(), TagStat.tag.asc())
            .limit(limit)
        )
        return [str(t) for t in (await self.session.execute(stmt)).scalars().all()]

    async def co_occurrences(self, user_id: int, tag: str) -> dict[str, int]:
        stmt = select(TagStat.co_occurrences).where(
            TagStat.user_id == user_id, TagStat.tag == tag
        )
        value = (await self.session.execute(stmt)).scalars().first()
        return dict(value or {})

    async def all_co_occurrences(self, user_id: int) -> dict[str, dict[str, int]]:
        """Co-Occurrence-Matrix des Users in einer Abfrage."""
        stmt = select(TagStat.tag, TagStat.co_occurrences).where(TagStat.user_id == user_id)
        return {
            str(tag): dict(value or {})
            for tag, value in (await self.session.execute(stmt)).all()
        }

    # ------------------------------------------------------------------
    # Export-Log
    # ------------------------------------------------------------------

    async def log_export(
        self, user_id: int, *, link_count: int, file_path: str | None, status: str
    ) -> ExportLog:
        entry = ExportLog(
            user_id=user_id,
            export_date=utcnow(),
            link_count=link_count,
            file_path=file_path,
            status=status,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry
