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
    protected: bool = False


@dataclass(frozen=True)
class RankedLifecycleItem:
    item_id: str
    score: float
    graph: float
    pinned: bool


@dataclass(frozen=True)
class ArchivePolicy:
    """Inspectable StableLow policy for recommendations requiring user action."""

    max_salience: float = 0.28
    dormancy_days: int = 90
    persistence_days: int = 30
    half_life_hours: float = 24.0 * 60
    salience_weights: SalienceWeights = SalienceWeights(0.7, 0.1, 0.1, 0.1)

    def __post_init__(self) -> None:
        if not 0.0 <= self.max_salience <= 1.0:
            raise ValueError("max_salience must be between zero and one")
        if self.dormancy_days < 1 or self.persistence_days < 1 or self.half_life_hours <= 0:
            raise ValueError("dormancy, persistence, and half-life must be positive")


@dataclass(frozen=True)
class ArchiveRecommendation:
    item_id: str
    eligible: bool
    current_salience: float | None
    checkpoint_salience: float | None
    reason_codes: tuple[str, ...]


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

    def _event_item_id(self, event: InteractionEvent) -> str:
        return self._resolve(event.item_id) if event.item_id in self.items else event.item_id

    def _direct_events(self, item_id: str, history: Iterable[InteractionEvent], at: datetime) -> tuple[InteractionEvent, ...]:
        return tuple(
            event
            for event in history
            if event.timestamp <= at and self._event_item_id(event) == item_id
        )

    def _archive_salience(
        self,
        item_id: str,
        history: Iterable[InteractionEvent],
        at: datetime,
        policy: ArchivePolicy,
    ) -> float:
        item = self.items[item_id]
        observed = tuple(event for event in history if event.timestamp <= at)
        feature = raw_features(item.concepts, item.contexts, observed, at, policy.half_life_hours)
        bounded = RawSalience(
            min(feature.recency, 1.0),
            min(feature.frequency, 1.0),
            min(feature.context, 1.0),
            min(feature.graph, 1.0),
        )
        return combine(bounded, policy.salience_weights)

    def _has_active_dependency(
        self,
        item_id: str,
        history: Iterable[InteractionEvent],
        now: datetime,
        policy: ArchivePolicy,
    ) -> bool:
        cutoff = now - timedelta(days=policy.dormancy_days)
        for edge in self.graph_edges:
            if item_id not in edge:
                continue
            neighbour = next(value for value in edge if value != item_id)
            if neighbour in self.archived:
                continue
            if neighbour in self.pinned or self.items[neighbour].protected:
                return True
            if any(event.timestamp >= cutoff for event in self._direct_events(neighbour, history, now)):
                return True
        return False

    def recommend_archive(
        self,
        item_id: str,
        history: Iterable[InteractionEvent],
        now: datetime,
        policy: ArchivePolicy = ArchivePolicy(),
    ) -> ArchiveRecommendation:
        """Return a recommendation only; archiving remains an explicit action."""
        if item_id in self.corrections:
            return ArchiveRecommendation(item_id, False, None, None, ("corrected_item",))
        resolved = self._resolve(item_id)
        if resolved in self.archived:
            return ArchiveRecommendation(resolved, False, None, None, ("already_archived",))
        if resolved in self.pinned:
            return ArchiveRecommendation(resolved, False, None, None, ("pinned",))
        if self.items[resolved].protected:
            return ArchiveRecommendation(resolved, False, None, None, ("protected",))
        observed = tuple(history)
        if self._has_active_dependency(resolved, observed, now, policy):
            return ArchiveRecommendation(resolved, False, None, None, ("active_graph_dependency",))
        recent_cutoff = now - timedelta(days=policy.dormancy_days)
        if any(event.timestamp >= recent_cutoff for event in self._direct_events(resolved, observed, now)):
            return ArchiveRecommendation(resolved, False, None, None, ("recent_interaction",))
        checkpoint = now - timedelta(days=policy.persistence_days)
        current_salience = self._archive_salience(resolved, observed, now, policy)
        checkpoint_salience = self._archive_salience(resolved, observed, checkpoint, policy)
        if current_salience > policy.max_salience or checkpoint_salience > policy.max_salience:
            return ArchiveRecommendation(
                resolved,
                False,
                current_salience,
                checkpoint_salience,
                ("not_stable_low",),
            )
        return ArchiveRecommendation(
            resolved,
            True,
            current_salience,
            checkpoint_salience,
            ("inactive_for_dormancy_window", "stable_low_salience", "eligible_for_user_review"),
        )

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

    policy = ArchivePolicy()
    policy_ranker = LifecycleRanker(
        {
            "stable_low": LifecycleItem("stable_low", frozenset({"stable_low"}), frozenset({"maintenance"})),
            "unstable_low": LifecycleItem("unstable_low", frozenset({"unstable_low"}), frozenset({"maintenance"})),
            "recent": LifecycleItem("recent", frozenset({"recent"}), frozenset({"maintenance"})),
            "pinned": LifecycleItem("pinned", frozenset({"pinned"}), frozenset({"maintenance"})),
            "protected": LifecycleItem("protected", frozenset({"protected"}), frozenset({"maintenance"}), protected=True),
            "dependent": LifecycleItem("dependent", frozenset({"dependent"}), frozenset({"maintenance"})),
            "active_support": LifecycleItem("active_support", frozenset({"active_support"}), frozenset({"maintenance"})),
        }
    )
    policy_ranker.pin("pinned")
    policy_ranker.connect("dependent", "active_support")
    policy_history = (
        InteractionEvent("controlled-user", "stable_low", now - timedelta(days=400), "open", frozenset({"stable_low"}), frozenset({"maintenance"})),
        InteractionEvent("controlled-user", "unstable_low", now - timedelta(days=200), "open", frozenset({"unstable_low"}), frozenset({"maintenance"})),
        InteractionEvent("controlled-user", "recent", now - timedelta(days=1), "open", frozenset({"recent"}), frozenset({"maintenance"})),
        InteractionEvent("controlled-user", "pinned", now - timedelta(days=400), "open", frozenset({"pinned"}), frozenset({"maintenance"})),
        InteractionEvent("controlled-user", "protected", now - timedelta(days=400), "open", frozenset({"protected"}), frozenset({"maintenance"})),
        InteractionEvent("controlled-user", "dependent", now - timedelta(days=400), "open", frozenset({"dependent"}), frozenset({"maintenance"})),
        InteractionEvent("controlled-user", "active_support", now - timedelta(days=1), "open", frozenset({"active_support"}), frozenset({"maintenance"})),
    )
    recommendations = {
        item_id: policy_ranker.recommend_archive(item_id, policy_history, now, policy)
        for item_id in ("stable_low", "unstable_low", "recent", "pinned", "protected", "dependent")
    }
    policy_ranker.archive("stable_low")
    after_user_archive = [item.item_id for item in policy_ranker.rank(("stable_low", "recent"), policy_history, now)]
    policy_ranker.restore("stable_low")
    after_user_restore = [item.item_id for item in policy_ranker.rank(("stable_low", "recent"), policy_history, now)]

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
        {
            "id": "stable_low_recommendation",
            "passed": recommendations["stable_low"].eligible
            and recommendations["stable_low"].reason_codes == ("inactive_for_dormancy_window", "stable_low_salience", "eligible_for_user_review"),
            "recommendation": recommendations["stable_low"].__dict__,
        },
        {
            "id": "archive_safety_gates",
            "passed": not recommendations["recent"].eligible
            and recommendations["recent"].reason_codes == ("recent_interaction",)
            and recommendations["pinned"].reason_codes == ("pinned",)
            and recommendations["protected"].reason_codes == ("protected",)
            and recommendations["dependent"].reason_codes == ("active_graph_dependency",),
            "recommendations": {item_id: recommendation.__dict__ for item_id, recommendation in recommendations.items() if item_id != "stable_low"},
        },
        {
            "id": "stable_low_persistence",
            "passed": not recommendations["unstable_low"].eligible and recommendations["unstable_low"].reason_codes == ("not_stable_low",),
            "recommendation": recommendations["unstable_low"].__dict__,
        },
        {
            "id": "user_controlled_archive_restore",
            "passed": "stable_low" not in after_user_archive and "stable_low" in after_user_restore,
            "after_archive": after_user_archive,
            "after_restore": after_user_restore,
        },
    ]
    return {"suite": "controlled_lifecycle", "passed": all(scenario["passed"] for scenario in scenarios), "scenarios": scenarios}
