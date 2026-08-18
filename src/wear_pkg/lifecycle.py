from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .models import InteractionEvent
from .salience import RawSalience, SalienceWeights, combine, raw_features


@dataclass(frozen=True)
class LifecycleItem:
    item_id: str
    concepts: frozenset[str]
    contexts: frozenset[str]
    relevance: float = 0.0


@dataclass(frozen=True)
class RankedLifecycleItem:
    item_id: str
    score: float
    graph: float
    pinned: bool


@dataclass
class LifecycleRanker:
    """A deterministic ranking surface for lifecycle-state invariants."""

    items: dict[str, LifecycleItem]
    weights: SalienceWeights = SalienceWeights(0.0, 0.0, 0.0, 1.0)
    archived: set[str] = field(default_factory=set)
    pinned: set[str] = field(default_factory=set)
    corrections: dict[str, str] = field(default_factory=dict)
    graph_edges: set[frozenset[str]] = field(default_factory=set)

    def _resolve(self, item_id: str) -> str:
        seen: set[str] = set()
        current = item_id
        while current in self.corrections:
            if current in seen:
                raise ValueError("correction chain contains a cycle")
            seen.add(current)
            current = self.corrections[current]
        if current not in self.items:
            raise KeyError(f"unknown lifecycle item: {current}")
        return current

    def pin(self, item_id: str) -> None:
        self.pinned.add(self._resolve(item_id))

    def unpin(self, item_id: str) -> None:
        self.pinned.discard(self._resolve(item_id))

    def archive(self, item_id: str) -> None:
        resolved = self._resolve(item_id)
        self.archived.add(resolved)
        self.pinned.discard(resolved)

    def restore(self, item_id: str) -> None:
        self.archived.discard(self._resolve(item_id))

    def correct(self, item_id: str, replacement_id: str) -> None:
        source = self._resolve(item_id)
        replacement = self._resolve(replacement_id)
        if source == replacement:
            raise ValueError("a correction must point to a different item")
        self.corrections[source] = replacement
        self.archived.add(source)
        self.pinned.discard(source)

    def connect(self, left: str, right: str) -> None:
        self.graph_edges.add(frozenset((self._resolve(left), self._resolve(right))))

    def disconnect(self, left: str, right: str) -> None:
        self.graph_edges.discard(frozenset((self._resolve(left), self._resolve(right))))

    def _active_candidates(self, candidate_ids: Iterable[str]) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()
        for item_id in candidate_ids:
            resolved = self._resolve(item_id)
            if resolved in self.archived or resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(resolved)
        return candidates

    def rank(self, candidate_ids: Iterable[str], history: Iterable[InteractionEvent], now: datetime) -> list[RankedLifecycleItem]:
        active = self._active_candidates(candidate_ids)
        history = tuple(history)
        ranked: list[RankedLifecycleItem] = []
        historical_ids = {self._resolve(event.item_id) for event in history if event.item_id in self.items}
        for item_id in active:
            item = self.items[item_id]
            feature = raw_features(item.concepts, item.contexts, history, now, half_life_hours=24.0)
            graph = float(any(frozenset((item_id, historical_id)) in self.graph_edges for historical_id in historical_ids))
            adjusted = RawSalience(feature.recency, feature.frequency, feature.context, graph)
            ranked.append(
                RankedLifecycleItem(
                    item_id=item_id,
                    score=item.relevance + combine(adjusted, self.weights),
                    graph=graph,
                    pinned=item_id in self.pinned,
                )
            )
        return sorted(ranked, key=lambda value: (not value.pinned, -value.score, value.item_id))


def _history(item: LifecycleItem, now: datetime) -> InteractionEvent:
    return InteractionEvent(
        user_id="controlled-user",
        item_id=item.item_id,
        timestamp=now - timedelta(hours=1),
        action="open",
        concepts=item.concepts,
        contexts=item.contexts,
    )


def run_lifecycle_validation() -> dict:
    """Run the fixed lifecycle scenarios used to verify state transitions."""
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)

    pin_ranker = LifecycleRanker(
        {
            "normal": LifecycleItem("normal", frozenset({"normal"}), frozenset({"general"}), relevance=0.9),
            "pinned": LifecycleItem("pinned", frozenset({"pinned"}), frozenset({"general"}), relevance=0.1),
        }
    )
    pin_before = [item.item_id for item in pin_ranker.rank(("normal", "pinned"), (), now)]
    pin_ranker.pin("pinned")
    pin_during = [item.item_id for item in pin_ranker.rank(("normal", "pinned"), (), now)]
    pin_ranker.unpin("pinned")
    pin_after = [item.item_id for item in pin_ranker.rank(("normal", "pinned"), (), now)]

    archive_ranker = LifecycleRanker(
        {
            "active": LifecycleItem("active", frozenset({"active"}), frozenset({"general"}), relevance=0.1),
            "archivable": LifecycleItem("archivable", frozenset({"archivable"}), frozenset({"general"}), relevance=0.9),
        }
    )
    archive_ranker.archive("archivable")
    archive_during = [item.item_id for item in archive_ranker.rank(("active", "archivable"), (), now)]
    archive_ranker.restore("archivable")
    archive_after = [item.item_id for item in archive_ranker.rank(("active", "archivable"), (), now)]

    correction_ranker = LifecycleRanker(
        {
            "outdated": LifecycleItem("outdated", frozenset({"version"}), frozenset({"general"}), relevance=0.9),
            "corrected": LifecycleItem("corrected", frozenset({"version"}), frozenset({"general"}), relevance=0.8),
            "other": LifecycleItem("other", frozenset({"other"}), frozenset({"general"}), relevance=0.1),
        }
    )
    correction_ranker.correct("outdated", "corrected")
    correction_after = [item.item_id for item in correction_ranker.rank(("outdated", "other"), (), now)]

    graph_ranker = LifecycleRanker(
        {
            "history": LifecycleItem("history", frozenset({"history"}), frozenset({"history"})),
            "a_plain": LifecycleItem("a_plain", frozenset({"plain"}), frozenset({"plain"})),
            "z_linked": LifecycleItem("z_linked", frozenset({"linked"}), frozenset({"linked"})),
        }
    )
    graph_history = (_history(graph_ranker.items["history"], now),)
    graph_ranker.connect("history", "z_linked")
    graph_before = graph_ranker.rank(("a_plain", "z_linked"), graph_history, now)
    graph_ranker.disconnect("history", "z_linked")
    graph_after = graph_ranker.rank(("a_plain", "z_linked"), graph_history, now)

    scenarios = [
        {
            "id": "pin_unpin",
            "passed": pin_before == ["normal", "pinned"] and pin_during == ["pinned", "normal"] and pin_after == pin_before,
            "before": pin_before,
            "pinned": pin_during,
            "unpinned": pin_after,
        },
        {
            "id": "archive_restore",
            "passed": archive_during == ["active"] and archive_after == ["archivable", "active"],
            "archived": archive_during,
            "restored": archive_after,
        },
        {
            "id": "correction_redirect",
            "passed": correction_after == ["corrected", "other"] and "outdated" not in correction_after,
            "ranked": correction_after,
        },
        {
            "id": "graph_disconnection",
            "passed": graph_before[0].item_id == "z_linked" and graph_before[0].graph == 1.0 and graph_after[0].item_id == "a_plain" and graph_after[1].graph == 0.0,
            "connected": [item.__dict__ for item in graph_before],
            "disconnected": [item.__dict__ for item in graph_after],
        },
    ]
    return {"suite": "controlled_lifecycle", "passed": all(scenario["passed"] for scenario in scenarios), "scenarios": scenarios}
