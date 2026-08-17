from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .intent import ProfileIntent
from .metrics import MetricAccumulator
from .models import Candidate, InteractionEvent, RetrievalEpisode
from .relevance import LexicalRelevance
from .salience import SalienceWeights, combine, normalize_within_episode, raw_features
from .text import tokenize

TIMESTAMP_FORMAT = "%m/%d/%Y %I:%M:%S %p"


@dataclass(frozen=True)
class MindItem:
    item_id: str
    concepts: frozenset[str]
    contexts: frozenset[str]
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class MindRunConfig:
    alpha: float = 0.75
    half_life_hours: float = 24.0
    min_observed_history: int = 1
    salience_weights: SalienceWeights = SalienceWeights()


def _entities(value: str) -> tuple[str, ...]:
    try:
        decoded = json.loads(value or "[]")
    except json.JSONDecodeError:
        return ()
    result = []
    for entity in decoded if isinstance(decoded, list) else []:
        identifier = entity.get("WikidataId") or entity.get("EntityId") or entity.get("Label")
        if identifier:
            result.append(f"entity:{identifier}")
    return tuple(result)


def load_news(path: Path) -> dict[str, MindItem]:
    items: dict[str, MindItem] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for row in reader:
            if len(row) < 5:
                continue
            item_id, category, subcategory, title, abstract = row[:5]
            title_entities = row[6] if len(row) > 6 else "[]"
            abstract_entities = row[7] if len(row) > 7 else "[]"
            contexts = frozenset({f"category:{category}", f"subcategory:{category}/{subcategory}"})
            concepts = frozenset(set(contexts) | set(_entities(title_entities)) | set(_entities(abstract_entities)))
            items[item_id] = MindItem(item_id, concepts, contexts, tokenize(f"{title} {abstract}"))
    return items


def _parse_timestamp(value: str) -> int:
    return int(datetime.strptime(value, TIMESTAMP_FORMAT).timestamp() * 1000)


def build_event_index(dataset_dir: Path, database_path: Path | None = None) -> Path:
    """Build a local, reproducible event order without retaining all rows in RAM."""
    database_path = database_path or dataset_dir / ".wear_pkg_behaviors.sqlite3"
    behaviours = dataset_dir / "behaviors.tsv"
    if database_path.exists() and database_path.stat().st_mtime >= behaviours.stat().st_mtime:
        return database_path
    if database_path.exists():
        database_path.unlink()
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "CREATE TABLE episodes (row_id INTEGER PRIMARY KEY, impression_id TEXT, user_id TEXT, time_ms INTEGER, impressions TEXT)"
        )
        batch = []
        with behaviours.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t")
            for row_id, row in enumerate(reader):
                if len(row) < 5:
                    continue
                impression_id, user_id, timestamp, _history, impressions = row[:5]
                if not user_id:
                    continue
                batch.append((row_id, impression_id, user_id, _parse_timestamp(timestamp), impressions))
                if len(batch) >= 20_000:
                    connection.executemany("INSERT INTO episodes VALUES (?, ?, ?, ?, ?)", batch)
                    batch.clear()
        if batch:
            connection.executemany("INSERT INTO episodes VALUES (?, ?, ?, ?, ?)", batch)
        connection.execute("CREATE INDEX idx_episodes_user_time ON episodes(user_id, time_ms, row_id)")
        connection.commit()
    finally:
        connection.close()
    return database_path


def iter_episodes(database_path: Path) -> Iterator[RetrievalEpisode]:
    connection = sqlite3.connect(database_path)
    try:
        cursor = connection.execute("SELECT impression_id, user_id, time_ms, impressions FROM episodes ORDER BY user_id, time_ms, row_id")
        for impression_id, user_id, time_ms, impressions in cursor:
            candidates = []
            for token in impressions.split():
                try:
                    item_id, label = token.rsplit("-", 1)
                    candidates.append(Candidate(item_id=item_id, label=int(label)))
                except ValueError:
                    continue
            if candidates:
                yield RetrievalEpisode(
                    episode_id=impression_id,
                    user_id=user_id,
                    timestamp=datetime.fromtimestamp(time_ms / 1000),
                    intent=ProfileIntent(()),
                    candidates=tuple(candidates),
                )
    finally:
        connection.close()


def _rank(labels_and_scores: list[tuple[int, float, str]]) -> list[int]:
    return [label for label, _score, _item_id in sorted(labels_and_scores, key=lambda row: (-row[1], row[2]))]


def evaluate_mind(dataset_dir: Path, config: MindRunConfig = MindRunConfig()) -> dict:
    required = (dataset_dir / "news.tsv", dataset_dir / "behaviors.tsv")
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "MIND dataset directory must contain news.tsv and behaviors.tsv; missing: " + ", ".join(missing)
        )
    items = load_news(dataset_dir / "news.tsv")
    relevance = LexicalRelevance.from_documents({item_id: item.tokens for item_id, item in items.items()})
    index_path = build_event_index(dataset_dir)
    metrics = {name: MetricAccumulator() for name in ("profile_relevance", "recency", "frequency", "recency_frequency", "salience", "wear_pkg")}
    previous_user: str | None = None
    history: list[InteractionEvent] = []
    skipped_unknown_items = 0
    eligible_episodes = 0

    for episode in iter_episodes(index_path):
        if episode.user_id != previous_user:
            previous_user = episode.user_id
            history = []
        present = [candidate for candidate in episode.candidates if candidate.item_id in items]
        skipped_unknown_items += len(episode.candidates) - len(present)
        if len(history) >= config.min_observed_history and present:
            intent = ProfileIntent(tuple(event.item_id for event in history))
            raw = {
                candidate.item_id: raw_features(
                    items[candidate.item_id].concepts,
                    items[candidate.item_id].contexts,
                    history,
                    episode.timestamp,
                    config.half_life_hours,
                )
                for candidate in present
            }
            normalised = normalize_within_episode(raw)
            scores = []
            for candidate in present:
                profile = relevance.score(intent, candidate.item_id)
                feature = normalised[candidate.item_id]
                salience = combine(feature, config.salience_weights)
                scores.append((candidate, profile, feature, salience))
            metrics["profile_relevance"].add(_rank([(candidate.label, profile, candidate.item_id) for candidate, profile, _, _ in scores]))
            metrics["recency"].add(_rank([(candidate.label, feature.recency, candidate.item_id) for candidate, _, feature, _ in scores]))
            metrics["frequency"].add(_rank([(candidate.label, feature.frequency, candidate.item_id) for candidate, _, feature, _ in scores]))
            metrics["recency_frequency"].add(_rank([(candidate.label, (feature.recency + feature.frequency) / 2, candidate.item_id) for candidate, _, feature, _ in scores]))
            metrics["salience"].add(_rank([(candidate.label, salience, candidate.item_id) for candidate, _, _, salience in scores]))
            metrics["wear_pkg"].add(_rank([(candidate.label, config.alpha * profile + (1 - config.alpha) * salience, candidate.item_id) for candidate, profile, _, salience in scores]))
            eligible_episodes += 1

        # Append only after all candidates have been ranked: no future leakage.
        for candidate in present:
            if candidate.label > 0:
                item = items[candidate.item_id]
                history.append(
                    InteractionEvent(
                        user_id=episode.user_id,
                        item_id=candidate.item_id,
                        timestamp=episode.timestamp,
                        action="click",
                        concepts=item.concepts,
                        contexts=item.contexts,
                    )
                )

    return {
        "dataset": "MIND",
        "intent_mode": "profile_relevance_no_fabricated_query",
        "config": {
            "alpha": config.alpha,
            "half_life_hours": config.half_life_hours,
            "min_observed_history": config.min_observed_history,
            "salience_weights": config.salience_weights.__dict__,
        },
        "episodes_with_observed_history": eligible_episodes,
        "unknown_candidate_items_skipped": skipped_unknown_items,
        "metrics": {name: accumulator.as_dict() for name, accumulator in metrics.items()},
        "limitations": [
            "MIND initial history is excluded from timestamped wear because individual event times are unavailable.",
            "Click labels are implicit engagement under the logged news policy, not relevance or personal importance labels.",
            "This evaluates profile relevance plus graph-propagated salience, not query-conditioned retrieval.",
        ],
    }
