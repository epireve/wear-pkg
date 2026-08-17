from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import FrozenSet, Sequence


@dataclass(frozen=True)
class Candidate:
    """An item that was available to rank in one retrieval episode."""

    item_id: str
    label: int = 0


@dataclass(frozen=True)
class InteractionEvent:
    """A past interaction available at ranking time."""

    user_id: str
    item_id: str
    timestamp: datetime
    action: str
    concepts: FrozenSet[str] = field(default_factory=frozenset)
    contexts: FrozenSet[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class RetrievalEpisode:
    """A point-in-time candidate-ranking problem."""

    episode_id: str
    user_id: str
    timestamp: datetime
    intent: object
    candidates: Sequence[Candidate]
