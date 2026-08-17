from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping

from .models import InteractionEvent


@dataclass(frozen=True)
class SalienceWeights:
    recency: float = 0.25
    frequency: float = 0.25
    context: float = 0.25
    graph: float = 0.25

    def normalized(self) -> "SalienceWeights":
        total = self.recency + self.frequency + self.context + self.graph
        if total <= 0:
            raise ValueError("At least one salience weight must be positive")
        return SalienceWeights(*(value / total for value in (self.recency, self.frequency, self.context, self.graph)))


@dataclass(frozen=True)
class RawSalience:
    recency: float
    frequency: float
    context: float
    graph: float


def _overlap(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def raw_features(
    candidate_concepts: frozenset[str],
    candidate_contexts: frozenset[str],
    history: Iterable[InteractionEvent],
    now: datetime,
    half_life_hours: float,
    seed_concepts: Iterable[frozenset[str]] = (),
    seed_contexts: Iterable[frozenset[str]] = (),
) -> RawSalience:
    events = list(history)
    related_events = [(event, _overlap(candidate_concepts, event.concepts)) for event in events]
    related_events = [(event, similarity) for event, similarity in related_events if similarity > 0]
    seed_pairs = list(zip(seed_concepts, seed_contexts, strict=True))
    related_seeds = [
        (concepts, contexts, _overlap(candidate_concepts, concepts))
        for concepts, contexts in seed_pairs
    ]
    related_seeds = [(concepts, contexts, similarity) for concepts, contexts, similarity in related_seeds if similarity > 0]
    if not related_events and not related_seeds:
        return RawSalience(0.0, 0.0, 0.0, 0.0)

    half_life_seconds = max(half_life_hours, 0.001) * 3600
    recency = max(
        (
            similarity * math.exp(-math.log(2) * max((now - event.timestamp).total_seconds(), 0.0) / half_life_seconds)
            for event, similarity in related_events
        ),
        default=0.0,
    )
    frequency = sum(similarity for _, similarity in related_events) + sum(similarity for _, _, similarity in related_seeds)
    historical_contexts = set()
    for event, _ in related_events:
        historical_contexts.update(event.contexts)
    for _concepts, contexts, _ in related_seeds:
        historical_contexts.update(contexts)
    context = len(candidate_contexts & historical_contexts) / len(candidate_contexts) if candidate_contexts else 0.0

    candidate_entities = frozenset(concept for concept in candidate_concepts if concept.startswith("entity:"))
    historical_entities = set()
    for event, _ in related_events:
        historical_entities.update(event.concepts)
    for concepts, _contexts, _ in related_seeds:
        historical_entities.update(concepts)
    graph = len(candidate_entities & historical_entities) / len(candidate_entities) if candidate_entities else 0.0
    return RawSalience(recency, frequency, context, graph)


def normalize_within_episode(values: Mapping[str, RawSalience]) -> dict[str, RawSalience]:
    maxima = RawSalience(
        max((value.recency for value in values.values()), default=0.0),
        max((value.frequency for value in values.values()), default=0.0),
        max((value.context for value in values.values()), default=0.0),
        max((value.graph for value in values.values()), default=0.0),
    )

    def normalise(value: float, maximum: float) -> float:
        return value / maximum if maximum else 0.0

    return {
        item_id: RawSalience(
            normalise(value.recency, maxima.recency),
            normalise(value.frequency, maxima.frequency),
            normalise(value.context, maxima.context),
            normalise(value.graph, maxima.graph),
        )
        for item_id, value in values.items()
    }


def combine(features: RawSalience, weights: SalienceWeights) -> float:
    weights = weights.normalized()
    return (
        weights.recency * features.recency
        + weights.frequency * features.frequency
        + weights.context * features.context
        + weights.graph * features.graph
    )
