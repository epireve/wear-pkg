from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence


@dataclass
class MetricAccumulator:
    count: int = 0
    mrr: float = 0.0
    ndcg_at_5: float = 0.0
    ndcg_at_10: float = 0.0
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0

    def add(self, ranked_labels: Sequence[int]) -> None:
        positives = sum(1 for value in ranked_labels if value > 0)
        if positives == 0:
            return
        self.count += 1
        first = next((index for index, value in enumerate(ranked_labels, start=1) if value > 0), None)
        if first is not None:
            self.mrr += 1.0 / first
        self.ndcg_at_5 += ndcg(ranked_labels, 5)
        self.ndcg_at_10 += ndcg(ranked_labels, 10)
        self.recall_at_5 += recall(ranked_labels, 5)
        self.recall_at_10 += recall(ranked_labels, 10)

    def as_dict(self) -> dict[str, float | int]:
        if self.count == 0:
            return {"episodes": 0, "mrr": 0.0, "ndcg@5": 0.0, "ndcg@10": 0.0, "recall@5": 0.0, "recall@10": 0.0}
        return {
            "episodes": self.count,
            "mrr": self.mrr / self.count,
            "ndcg@5": self.ndcg_at_5 / self.count,
            "ndcg@10": self.ndcg_at_10 / self.count,
            "recall@5": self.recall_at_5 / self.count,
            "recall@10": self.recall_at_10 / self.count,
        }


def recall(labels: Sequence[int], k: int) -> float:
    positives = sum(1 for value in labels if value > 0)
    return sum(1 for value in labels[:k] if value > 0) / positives if positives else 0.0


def ndcg(labels: Sequence[int], k: int) -> float:
    observed = sum(value / math.log2(index + 2) for index, value in enumerate(labels[:k]))
    ideal = sum(value / math.log2(index + 2) for index, value in enumerate(sorted(labels, reverse=True)[:k]))
    return observed / ideal if ideal else 0.0
