from __future__ import annotations

import csv
import json
import math
import sqlite3
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .metrics import MetricAccumulator


@dataclass(frozen=True)
class KuaiSarConfig:
    alpha: float = 0.65
    half_life_hours: float = 72.0
    min_history_events: int = 1
    max_sessions: int | None = None


@dataclass(frozen=True)
class Item:
    item_id: str
    tokens: frozenset[str]
    author: str
    category: str

    @property
    def concepts(self) -> frozenset[str]:
        return frozenset({f"author:{self.author}", f"category:{self.category}"})


@dataclass(frozen=True)
class Event:
    timestamp_ms: int
    item: Item
    source: str
    action_strength: float


def _root(dataset_dir: Path) -> Path:
    if (dataset_dir / "src_inter.csv").is_file():
        return dataset_dir
    candidates = [child for child in dataset_dir.iterdir() if child.is_dir() and (child / "src_inter.csv").is_file()]
    if len(candidates) == 1:
        return candidates[0]
    raise FileNotFoundError(f"Could not find src_inter.csv below {dataset_dir}")


def _tokens(value: str) -> frozenset[str]:
    try:
        decoded = json.loads(value)
        return frozenset(str(token) for token in decoded) if isinstance(decoded, list) else frozenset()
    except (json.JSONDecodeError, TypeError):
        return frozenset()


def _strength(row: dict[str, str]) -> float:
    duration = float(row["duration_ms"] or 0.0)
    playing = float(row["playing_time"] or 0.0)
    completion = min(playing / duration, 1.0) if duration > 0 else 0.0
    return (
        1.0 * int(row["click"] or 0)
        + 0.75 * int(row["forward"] or 0)
        + 0.5 * int(row["like"] or 0)
        + 0.4 * int(row["follow"] or 0)
        + 0.3 * int(row["search"] or 0)
        + 0.5 * completion
    )


def build_index(dataset_dir: Path, database_path: Path | None = None) -> Path:
    """Create a local SQLite index from the direct KuaiSAR release."""
    root = _root(dataset_dir)
    database_path = database_path or root / ".wear_pkg_kuaisar.sqlite3"
    source_files = (root / "item_features.csv", root / "src_inter.csv", root / "rec_inter.csv")
    if database_path.exists() and database_path.stat().st_mtime >= max(path.stat().st_mtime for path in source_files):
        return database_path
    if database_path.exists():
        database_path.unlink()
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            CREATE TABLE items (item_id TEXT PRIMARY KEY, caption TEXT, author_id TEXT, category_id TEXT);
            CREATE TABLE search_sessions (session_key TEXT PRIMARY KEY, user_id TEXT, session_id TEXT, time_ms INTEGER, keyword TEXT, source TEXT);
            CREATE TABLE search_candidates (session_key TEXT, item_id TEXT, click INTEGER);
            CREATE TABLE rec_events (row_id INTEGER PRIMARY KEY, user_id TEXT, time_ms INTEGER, item_id TEXT, strength REAL);
            """
        )
        _ingest_items(connection, root / "item_features.csv")
        _ingest_search(connection, root / "src_inter.csv")
        _ingest_recommendations(connection, root / "rec_inter.csv")
        connection.executescript(
            """
            CREATE INDEX idx_sessions_user_time ON search_sessions(user_id, time_ms, session_key);
            CREATE INDEX idx_candidates_session ON search_candidates(session_key);
            CREATE INDEX idx_rec_user_time ON rec_events(user_id, time_ms, row_id);
            """
        )
        connection.commit()
    finally:
        connection.close()
    return database_path


def _ingest_items(connection: sqlite3.Connection, path: Path) -> None:
    batch = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            batch.append((row["item_id"], row["caption"], row["author_id"], row["second_level_category_id"] or row["first_level_category_id"]))
            if len(batch) == 20_000:
                connection.executemany("INSERT INTO items VALUES (?, ?, ?, ?)", batch)
                batch.clear()
    if batch:
        connection.executemany("INSERT INTO items VALUES (?, ?, ?, ?)", batch)


def _ingest_search(connection: sqlite3.Connection, path: Path) -> None:
    sessions, candidates = [], []
    seen = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = f"{row['user_id']}:{row['search_session_id']}"
            if key not in seen:
                seen.add(key)
                sessions.append((key, row["user_id"], row["search_session_id"], int(float(row["search_session_timestamp"])), row["keyword"], row["search_source"]))
            candidates.append((key, row["item_id"], int(row["click_cnt"] or 0)))
            if len(candidates) >= 20_000:
                connection.executemany("INSERT INTO search_sessions VALUES (?, ?, ?, ?, ?, ?)", sessions)
                connection.executemany("INSERT INTO search_candidates VALUES (?, ?, ?)", candidates)
                sessions.clear()
                candidates.clear()
    if sessions:
        connection.executemany("INSERT INTO search_sessions VALUES (?, ?, ?, ?, ?, ?)", sessions)
    if candidates:
        connection.executemany("INSERT INTO search_candidates VALUES (?, ?, ?)", candidates)


def _ingest_recommendations(connection: sqlite3.Connection, path: Path) -> None:
    batch = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row_id, row in enumerate(csv.DictReader(handle)):
            batch.append((row_id, row["user_id"], int(float(row["timestamp"])), row["item_id"], _strength(row)))
            if len(batch) >= 20_000:
                connection.executemany("INSERT INTO rec_events VALUES (?, ?, ?, ?, ?)", batch)
                batch.clear()
    if batch:
        connection.executemany("INSERT INTO rec_events VALUES (?, ?, ?, ?, ?)", batch)


def _overlap(left: frozenset[str], right: frozenset[str]) -> float:
    return len(left & right) / len(left | right) if left and right else 0.0


def _rank(values: list[tuple[int, float, str]]) -> list[int]:
    return [label for label, _score, _item_id in sorted(values, key=lambda value: (-value[1], value[2]))]


def evaluate_kuaisar(dataset_dir: Path, config: KuaiSarConfig = KuaiSarConfig()) -> dict:
    database_path = build_index(dataset_dir)
    connection = sqlite3.connect(database_path)
    item_cache: OrderedDict[str, Item | None] = OrderedDict()

    def item(item_id: str) -> Item | None:
        if item_id in item_cache:
            item_cache.move_to_end(item_id)
            return item_cache[item_id]
        row = connection.execute("SELECT caption, author_id, category_id FROM items WHERE item_id = ?", (item_id,)).fetchone()
        value = Item(item_id, _tokens(row[0]), row[1], row[2]) if row else None
        item_cache[item_id] = value
        if len(item_cache) > 250_000:
            item_cache.popitem(last=False)
        return value

    metrics = {name: MetricAccumulator() for name in ("query_lexical", "frequency", "action", "salience", "wear_pkg")}
    sessions = connection.execute("SELECT session_key, user_id, time_ms, keyword, source FROM search_sessions ORDER BY user_id, time_ms, session_key")
    prior_user: str | None = None
    prior_time = -1
    history: list[Event] = []
    ranked_sessions = 0
    try:
        for session_key, user_id, time_ms, keyword, source in sessions:
            if user_id != prior_user:
                prior_user, prior_time, history = user_id, -1, []
            rec_rows = connection.execute(
                "SELECT time_ms, item_id, strength FROM rec_events WHERE user_id = ? AND time_ms > ? AND time_ms < ? ORDER BY time_ms, row_id",
                (user_id, prior_time, time_ms),
            )
            for rec_time, item_id, strength in rec_rows:
                rec_item = item(item_id)
                if rec_item:
                    history.append(Event(rec_time, rec_item, "recommendation", strength))
            prior_time = time_ms
            query = _tokens(keyword)
            candidates = []
            for candidate_id, click in connection.execute("SELECT item_id, click FROM search_candidates WHERE session_key = ?", (session_key,)):
                candidate_item = item(candidate_id)
                if candidate_item:
                    candidates.append((candidate_item, click))
            if len(history) >= config.min_history_events and candidates:
                raw = []
                half_life = max(config.half_life_hours, 0.001) * 3600 * 1000
                for candidate, click in candidates:
                    related = [(event, _overlap(candidate.concepts, event.item.concepts)) for event in history]
                    related = [(event, similarity) for event, similarity in related if similarity > 0]
                    recency = max((similarity * math.exp(-math.log(2) * (time_ms - event.timestamp_ms) / half_life) for event, similarity in related), default=0.0)
                    frequency = sum(similarity for _, similarity in related)
                    action = sum(similarity * event.action_strength for event, similarity in related)
                    context = min(1.0, len({event.source for event, _ in related}) / 2)
                    graph = max((1.0 if candidate.author == event.item.author else 0.0 for event, _ in related), default=0.0)
                    relevance = _overlap(query, candidate.tokens)
                    raw.append((candidate, click, relevance, recency, frequency, action, context, graph))
                maxima = [max((row[index] for row in raw), default=0.0) for index in range(3, 8)]
                scored = []
                for candidate, click, relevance, recency, frequency, action, context, graph in raw:
                    features = [value / maximum if maximum else 0.0 for value, maximum in zip((recency, frequency, action, context, graph), maxima, strict=True)]
                    salience = 0.15 * features[0] + 0.30 * features[1] + 0.30 * features[2] + 0.10 * features[3] + 0.15 * features[4]
                    scored.append((candidate.item_id, click, relevance, features, salience))
                metrics["query_lexical"].add(_rank([(click, relevance, item_id) for item_id, click, relevance, _, _ in scored]))
                metrics["frequency"].add(_rank([(click, features[1], item_id) for item_id, click, _, features, _ in scored]))
                metrics["action"].add(_rank([(click, features[2], item_id) for item_id, click, _, features, _ in scored]))
                metrics["salience"].add(_rank([(click, salience, item_id) for item_id, click, _, _, salience in scored]))
                metrics["wear_pkg"].add(_rank([(click, config.alpha * relevance + (1 - config.alpha) * salience, item_id) for item_id, click, relevance, _, salience in scored]))
                ranked_sessions += 1
                if config.max_sessions and ranked_sessions >= config.max_sessions:
                    break
            for candidate, click in candidates:
                if click:
                    history.append(Event(time_ms, candidate, "search", 1.0))
    finally:
        connection.close()
    return {
        "dataset": "KuaiSAR",
        "intent_mode": "actual_query_to_caption",
        "ranked_sessions": ranked_sessions,
        "config": config.__dict__,
        "metrics": {name: accumulator.as_dict() for name, accumulator in metrics.items()},
        "limitations": [
            "The small release covers a short observation window.",
            "Hashed tokens support lexical matching but not human-readable semantic explanations.",
            "Search click labels are implicit feedback and may be affected by automatic playback.",
        ],
    }
