from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Sequence


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
        self.mrr += reciprocal_rank(ranked_labels)
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


def reciprocal_rank(labels: Sequence[int]) -> float:
    first = next((index for index, value in enumerate(labels, start=1) if value > 0), None)
    return 1.0 / first if first is not None else 0.0


def ndcg(labels: Sequence[int], k: int) -> float:
    observed = sum(value / math.log2(index + 2) for index, value in enumerate(labels[:k]))
    ideal = sum(value / math.log2(index + 2) for index, value in enumerate(sorted(labels, reverse=True)[:k]))
    return observed / ideal if ideal else 0.0


@dataclass
class PairedClusterAccumulator:
    """User-clustered paired metric contributions for deterministic bootstrap CIs."""

    values: dict[str, list[float]] = field(default_factory=dict)

    def add(self, cluster_id: str, full_labels: Sequence[int], baseline_labels: Sequence[int]) -> None:
        if not any(value > 0 for value in full_labels):
            return
        aggregate = self.values.setdefault(cluster_id, [0.0] * 7)
        aggregate[0] += 1
        aggregate[1] += reciprocal_rank(full_labels)
        aggregate[2] += reciprocal_rank(baseline_labels)
        aggregate[3] += ndcg(full_labels, 5)
        aggregate[4] += ndcg(baseline_labels, 5)
        aggregate[5] += ndcg(full_labels, 10)
        aggregate[6] += ndcg(baseline_labels, 10)

    def bootstrap(self, samples: int, seed: int) -> dict:
        if samples <= 0:
            raise ValueError("bootstrap samples must be positive")
        clusters = list(self.values.values())
        if not clusters:
            return {"cluster_unit": "user", "clusters": 0, "episodes": 0, "samples": samples, "seed": seed, "metrics": {}}
        totals = [sum(cluster[index] for cluster in clusters) for index in range(7)]
        point = {
            "mrr": totals[1] / totals[0] - totals[2] / totals[0],
            "ndcg@5": totals[3] / totals[0] - totals[4] / totals[0],
            "ndcg@10": totals[5] / totals[0] - totals[6] / totals[0],
        }
        draws = {name: [] for name in point}
        generator = random.Random(seed)
        for _sample in range(samples):
            sampled = [clusters[generator.randrange(len(clusters))] for _ in range(len(clusters))]
            count = sum(cluster[0] for cluster in sampled)
            if not count:
                continue
            draws["mrr"].append(sum(cluster[1] for cluster in sampled) / count - sum(cluster[2] for cluster in sampled) / count)
            draws["ndcg@5"].append(sum(cluster[3] for cluster in sampled) / count - sum(cluster[4] for cluster in sampled) / count)
            draws["ndcg@10"].append(sum(cluster[5] for cluster in sampled) / count - sum(cluster[6] for cluster in sampled) / count)

        def percentile(values: list[float], quantile: float) -> float:
            ordered = sorted(values)
            position = (len(ordered) - 1) * quantile
            lower = int(position)
            upper = min(lower + 1, len(ordered) - 1)
            return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

        return {
            "cluster_unit": "user",
            "clusters": len(clusters),
            "episodes": int(totals[0]),
            "samples": samples,
            "seed": seed,
            "metrics": {
                name: {
                    "difference": value,
                    "ci95": [percentile(draws[name], 0.025), percentile(draws[name], 0.975)],
                    "positive_share": sum(draw > 0 for draw in draws[name]) / len(draws[name]),
                }
                for name, value in point.items()
            },
        }
