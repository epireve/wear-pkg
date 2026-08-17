from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mind import MindRunConfig, evaluate_mind
from .salience import SalienceWeights


def _mind_run(arguments: argparse.Namespace) -> int:
    config = MindRunConfig(
        alpha=arguments.alpha,
        half_life_hours=arguments.half_life_hours,
        min_observed_history=arguments.min_observed_history,
        salience_weights=SalienceWeights(arguments.weight_recency, arguments.weight_frequency, arguments.weight_context, arguments.weight_graph),
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


def main() -> int:
    parser = argparse.ArgumentParser(prog="wear-pkg")
    subparsers = parser.add_subparsers(dest="command", required=True)
    mind = subparsers.add_parser("mind-run", help="Run chronological MIND profile-relevance and salience baselines")
    mind.add_argument("--dataset-dir", type=Path, required=True, help="Directory containing news.tsv and behaviors.tsv")
    mind.add_argument("--output", type=Path, required=True)
    mind.add_argument("--alpha", type=float, default=0.75, help="Profile-relevance weight in the final Wear-PKG score")
    mind.add_argument("--half-life-hours", type=float, default=24.0)
    mind.add_argument("--min-observed-history", type=int, default=1)
    mind.add_argument("--weight-recency", type=float, default=0.25)
    mind.add_argument("--weight-frequency", type=float, default=0.25)
    mind.add_argument("--weight-context", type=float, default=0.25)
    mind.add_argument("--weight-graph", type=float, default=0.25)
    mind.set_defaults(func=_mind_run)
    arguments = parser.parse_args()
    return arguments.func(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
