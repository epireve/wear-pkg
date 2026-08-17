from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mind import MindRunConfig, evaluate_mind, evaluate_mind_sweep
from .salience import SalienceWeights


def _mind_run(arguments: argparse.Namespace) -> int:
    config = MindRunConfig(
        alpha=arguments.alpha,
        half_life_hours=arguments.half_life_hours,
        min_observed_history=arguments.min_observed_history,
        salience_weights=SalienceWeights(arguments.weight_recency, arguments.weight_frequency, arguments.weight_context, arguments.weight_graph),
        use_provided_history=arguments.use_provided_history,
    )
    try:
        result = evaluate_mind(arguments.dataset_dir, config)
    except (FileNotFoundError, ValueError) as error:
        raise SystemExit(f"error: {error}") from error
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {arguments.output}")
    print(json.dumps(result["metrics"], indent=2, sort_keys=True))
    return 0


def _mind_sweep(arguments: argparse.Namespace) -> int:
    source = json.loads(arguments.config.read_text(encoding="utf-8"))
    try:
        use_provided_history = source["use_provided_history"]
        variants = {
            item["id"]: MindRunConfig(
                alpha=float(item["alpha"]),
                half_life_hours=float(item["half_life_hours"]),
                min_observed_history=int(source.get("min_observed_history", 1)),
                use_provided_history=bool(use_provided_history),
                salience_weights=SalienceWeights(
                    float(item["weights"]["recency"]),
                    float(item["weights"]["frequency"]),
                    float(item["weights"]["context"]),
                    float(item["weights"]["graph"]),
                ),
            )
            for item in source["variants"]
        }
        if len(variants) != len(source["variants"]):
            raise ValueError("Every sweep variant id must be unique")
        result = evaluate_mind_sweep(arguments.dataset_dir, variants)
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"error: {error}") from error
    metric = source.get("selection_metric", "ndcg@10")
    if metric not in {"mrr", "ndcg@5", "ndcg@10", "recall@5", "recall@10"}:
        raise SystemExit(f"error: unsupported selection metric: {metric}")
    selected_id, selected = max(result["variants"].items(), key=lambda pair: (pair[1]["metrics"][metric], pair[0]))
    result["selection"] = {"metric": metric, "variant_id": selected_id, "metric_value": selected["metrics"][metric]}
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {arguments.output}")
    print(json.dumps(result["selection"], indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="wear-pkg")
    subparsers = parser.add_subparsers(dest="command", required=True)
    mind = subparsers.add_parser("mind-run", help="Run chronological MIND profile-relevance and salience baselines")
    mind.add_argument("--dataset-dir", type=Path, required=True, help="Directory containing news.tsv and behaviors.tsv")
    mind.add_argument("--output", type=Path, required=True)
    mind.add_argument("--alpha", type=float, default=0.75, help="Profile-relevance weight in the final Wear-PKG score")
    mind.add_argument("--half-life-hours", type=float, default=24.0)
    mind.add_argument("--min-observed-history", type=int, default=1)
    mind.add_argument("--use-provided-history", action="store_true", help="Use MIND's supplied history for profile/frequency/context/graph, never recency")
    mind.add_argument("--weight-recency", type=float, default=0.25)
    mind.add_argument("--weight-frequency", type=float, default=0.25)
    mind.add_argument("--weight-context", type=float, default=0.25)
    mind.add_argument("--weight-graph", type=float, default=0.25)
    mind.set_defaults(func=_mind_run)
    sweep = subparsers.add_parser("mind-sweep", help="Select a MIND configuration from a train-only JSON grid")
    sweep.add_argument("--dataset-dir", type=Path, required=True, help="Directory containing news.tsv and behaviors.tsv")
    sweep.add_argument("--config", type=Path, required=True, help="JSON file containing sweep variants")
    sweep.add_argument("--output", type=Path, required=True)
    sweep.set_defaults(func=_mind_sweep)
    arguments = parser.parse_args()
    return arguments.func(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
