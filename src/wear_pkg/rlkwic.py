from __future__ import annotations

import bisect
import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlparse

from .metrics import MetricAccumulator
from .models import InteractionEvent
from .salience import SalienceWeights, combine, normalize_within_episode, raw_features
from .text import tokenize


@dataclass(frozen=True)
class RlkWicConfig:
    alpha: float = 0.5
    half_life_hours: float = 24.0
    min_history_events: int = 1
    partition: str = "all"
    train_fraction: float = 0.8
    salience_weights: SalienceWeights = SalienceWeights()


@dataclass(frozen=True)
class RlkWicEpisode:
    participant_id: str
    context_id: str
    timestamp_ms: int
    content: str
    candidates: tuple[tuple[str, int], ...]


def _root(dataset_dir: Path) -> Path:
    if (dataset_dir / "p1" / "contexts.csv").is_file():
        return dataset_dir
    nested = dataset_dir / "RLKWiC"
    if (nested / "p1" / "contexts.csv").is_file():
        return nested
    raise FileNotFoundError(f"Could not find participant folders below {dataset_dir}")


def _entity_tokens(value: str) -> frozenset[str]:
    parsed = urlparse(value)
    label = parsed.path.rsplit("/", 1)[-1] or value
    return frozenset(f"entity:{token}" for token in tokenize(label.replace("_", " ")))


def _overlap(left: frozenset[str], right: frozenset[str]) -> float:
    return len(left & right) / len(left | right) if left and right else 0.0


def _rank(values: list[tuple[int, float, str]]) -> list[int]:
    return [label for label, _score, item_id in sorted(values, key=lambda value: (-value[1], value[2]))]


def _load_contexts(participant_dir: Path) -> dict[str, str]:
    with (participant_dir / "contexts.csv").open(encoding="utf-8", newline="") as handle:
        return {row["id"]: row["label"] for row in csv.DictReader(handle) if row.get("id")}


def _load_history(participant_id: str, participant_dir: Path) -> dict[str, list[InteractionEvent]]:
    with (participant_dir / "kg_resources.csv").open(encoding="utf-8", newline="") as handle:
        resources = {row["id"]: row["label"] for row in csv.DictReader(handle) if row.get("id")}
    with (participant_dir / "kg_spo.csv").open(encoding="utf-8", newline="") as handle:
        triples = {row["id"]: (row["s"], row["p"], row["o"]) for row in csv.DictReader(handle) if row.get("id")}
    history: dict[str, list[InteractionEvent]] = defaultdict(list)
    with (participant_dir / "events.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            context_id = row.get("selected_context_id")
            triple = triples.get(row.get("spo_id", ""))
            if not context_id or context_id == "None" or not triple:
                continue
            labels = " ".join(resources.get(resource_id, "") for resource_id in triple)
            concepts = _entity_tokens(labels)
            if not concepts:
                continue
            history[context_id].append(
                InteractionEvent(
                    user_id=participant_id,
                    item_id=row["spo_id"],
                    timestamp=datetime.fromtimestamp(int(row["timestamp_received"]) / 1000, tz=timezone.utc),
                    action=row.get("cause", "event"),
                    concepts=concepts,
                    contexts=frozenset({f"context:{participant_id}:{context_id}"}),
                )
            )
    for events in history.values():
        events.sort(key=lambda event: event.timestamp)
    return history


def _load_episodes(root: Path) -> list[RlkWicEpisode]:
    recommendations = root.parent / "Recommendations.csv"
    if not recommendations.is_file():
        raise FileNotFoundError(f"Missing human-scored recommendation file: {recommendations}")
    grouped: dict[tuple[str, str, str, str, str], dict[str, int]] = defaultdict(dict)
    with recommendations.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["Participant ID"], row["Context ID"], row["Timestamp"], row["Event"], row["Content"])
            entity = row["Recommended Entity"]
            grouped[key][entity] = max(grouped[key].get(entity, 0), int(row["Score"]))
    episodes = []
    for (participant_id, context_id, timestamp, _event, content), candidates in grouped.items():
        labels = tuple(sorted(candidates.items()))
        if len(labels) < 2 or not any(score > 0 for _entity, score in labels):
            continue
        episodes.append(RlkWicEpisode(participant_id, context_id, int(timestamp), content, labels))
    return sorted(episodes, key=lambda episode: (episode.timestamp_ms, episode.participant_id, episode.context_id, episode.content))


def _partition_details(episodes: list[RlkWicEpisode], config: RlkWicConfig) -> dict:
    if config.partition not in {"all", "train", "dev"}:
        raise ValueError("partition must be one of: all, train, dev")
    if not 0.0 < config.train_fraction < 1.0:
        raise ValueError("train_fraction must be between 0 and 1")
    if config.partition == "all":
        return {"partition": "all", "total_candidate_slates": len(episodes)}
    if len(episodes) < 2:
        raise ValueError("RLKWiC evaluation needs at least two candidate slates for a temporal partition")
    offset = min(max(int(len(episodes) * config.train_fraction), 1), len(episodes) - 1)
    cutoff_ms = episodes[offset].timestamp_ms
    return {
        "partition": config.partition,
        "total_candidate_slates": len(episodes),
        "train_fraction": config.train_fraction,
        "cutoff_timestamp_ms": cutoff_ms,
        "cutoff_utc": datetime.fromtimestamp(cutoff_ms / 1000, tz=timezone.utc).isoformat(),
        "rule": "train slates precede the cutoff; dev slates are at or after the cutoff",
    }


def _should_evaluate(timestamp_ms: int, details: dict) -> bool:
    if details["partition"] == "all":
        return True
    if details["partition"] == "train":
        return timestamp_ms < details["cutoff_timestamp_ms"]
    return timestamp_ms >= details["cutoff_timestamp_ms"]


def _config_dict(config: RlkWicConfig) -> dict:
    return {
        "alpha": config.alpha,
        "half_life_hours": config.half_life_hours,
        "min_history_events": config.min_history_events,
        "partition": config.partition,
        "train_fraction": config.train_fraction,
        "salience_weights": config.salience_weights.__dict__,
    }


def _evaluate_variants(dataset_dir: Path, variants: Mapping[str, RlkWicConfig]) -> dict:
    if not variants:
        raise ValueError("at least one RLKWiC variant is required")
    configs = list(variants.values())
    reference = configs[0]
    shared = ("partition", "train_fraction", "min_history_events")
    for config in configs[1:]:
        if any(getattr(config, name) != getattr(reference, name) for name in shared):
            raise ValueError("RLKWiC sweep variants must share partition, train_fraction, and min_history_events")
    root = _root(dataset_dir)
    contexts = {directory.name[1:]: _load_contexts(directory) for directory in sorted(root.glob("p[0-9]*"))}
    histories = {
        participant_id: _load_history(participant_id, root / f"p{participant_id}")
        for participant_id in contexts
    }
    episodes = _load_episodes(root)
    details = _partition_details(episodes, reference)
    metric_names = ("event_lexical", "frequency", "graph", "salience", "wear_pkg")
    metrics = {variant_id: {name: MetricAccumulator() for name in metric_names} for variant_id in variants}
    eligible = 0
    for episode in episodes:
        if not _should_evaluate(episode.timestamp_ms, details):
            continue
        events = histories.get(episode.participant_id, {}).get(episode.context_id, [])
        event_times = [event.timestamp.timestamp() * 1000 for event in events]
        prior = events[:bisect.bisect_left(event_times, episode.timestamp_ms)]
        if len(prior) < reference.min_history_events:
            continue
        context_label = contexts.get(episode.participant_id, {}).get(episode.context_id, "")
        intent = frozenset(f"entity:{token}" for token in tokenize(f"{context_label} {episode.content}"))
        now = datetime.fromtimestamp(episode.timestamp_ms / 1000, tz=timezone.utc)
        raw = {}
        relevance = {}
        for entity, _score in episode.candidates:
            concepts = _entity_tokens(entity)
            raw[entity] = raw_features(
                concepts,
                frozenset({f"context:{episode.participant_id}:{episode.context_id}"}),
                prior,
                now,
                reference.half_life_hours,
            )
            relevance[entity] = _overlap(intent, concepts)
        normalised = normalize_within_episode(raw)
        for variant_id, config in variants.items():
            scores = []
            for entity, label in episode.candidates:
                feature = normalised[entity]
                salience = combine(feature, config.salience_weights)
                scores.append((entity, label, relevance[entity], feature, salience))
            metrics[variant_id]["event_lexical"].add(_rank([(label, lexical, entity) for entity, label, lexical, _feature, _salience in scores]))
            metrics[variant_id]["frequency"].add(_rank([(label, feature.frequency, entity) for entity, label, _lexical, feature, _salience in scores]))
            metrics[variant_id]["graph"].add(_rank([(label, feature.graph, entity) for entity, label, _lexical, feature, _salience in scores]))
            metrics[variant_id]["salience"].add(_rank([(label, salience, entity) for entity, label, _lexical, _feature, salience in scores]))
            metrics[variant_id]["wear_pkg"].add(_rank([(label, config.alpha * lexical + (1 - config.alpha) * salience, entity) for entity, label, lexical, _feature, salience in scores]))
        eligible += 1
    return {
        "dataset": "RLKWiC",
        "intent_mode": "context_and_event_content",
        "eligible_candidate_slates": eligible,
        "temporal_partition": details,
        "variants": {
            variant_id: {
                "config": _config_dict(config),
                "metrics": {name: accumulator.as_dict() for name, accumulator in metrics[variant_id].items()},
            }
            for variant_id, config in variants.items()
        },
        "limitations": [
            "Only recommendation slates with at least two human-scored entities are ranked.",
            "Entity matching is lexical because the public resource graph does not directly identify every recommended DBpedia URI.",
            "The dataset has eight participants, so results are a construct check rather than a scale estimate.",
        ],
    }


def evaluate_rlkwic(dataset_dir: Path, config: RlkWicConfig = RlkWicConfig()) -> dict:
    result = _evaluate_variants(dataset_dir, {"single": config})
    single = result.pop("variants")["single"]
    result["config"] = single["config"]
    result["metrics"] = single["metrics"]
    return result


def evaluate_rlkwic_sweep(dataset_dir: Path, variants: Mapping[str, RlkWicConfig]) -> dict:
    return _evaluate_variants(dataset_dir, variants)
