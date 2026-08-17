from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class QueryIntent:
    """An actual issued query. KuaiSAR will use this directly."""

    tokens: FrozenSet[str]


@dataclass(frozen=True)
class ProfileIntent:
    """A history-derived interest profile. Used by MIND; this is not a query."""

    item_ids: tuple[str, ...]


@dataclass(frozen=True)
class ContextIntent:
    """An explicit work context, such as an RLKWiC user-defined context."""

    context_id: str
    tokens: FrozenSet[str]
