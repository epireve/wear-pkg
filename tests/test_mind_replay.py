from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wear_pkg.intent import ProfileIntent, QueryIntent
from wear_pkg.mind import MindRunConfig, evaluate_mind
from wear_pkg.relevance import LexicalRelevance


class MindReplayTest(unittest.TestCase):
    def _dataset(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        news = [
            ["N1", "tech", "ai", "OpenAI model", "AI systems", "url", json.dumps([{"WikidataId": "Q1"}]), "[]"],
            ["N2", "sport", "football", "Football score", "Sports report", "url", json.dumps([{"WikidataId": "Q2"}]), "[]"],
            ["N3", "tech", "ai", "New AI model", "OpenAI research", "url", json.dumps([{"WikidataId": "Q1"}]), "[]"],
            ["N4", "finance", "markets", "Markets rise", "Finance update", "url", "[]", "[]"],
        ]
        (root / "news.tsv").write_text("\n".join("\t".join(row) for row in news) + "\n", encoding="utf-8")
        behaviours = [
            "1\tU1\t11/01/2019 09:00:00 AM\tN4\tN1-1 N2-0",
            "2\tU1\t11/01/2019 10:00:00 AM\tN1\tN2-0 N3-1",
            "3\tU1\t11/01/2019 11:00:00 AM\tN1 N3\tN4-1 N2-0",
        ]
        (root / "behaviors.tsv").write_text("\n".join(behaviours) + "\n", encoding="utf-8")
        return root

    def test_replay_uses_only_prior_observed_clicks(self) -> None:
        result = evaluate_mind(self._dataset(), MindRunConfig(min_observed_history=1))
        self.assertEqual(result["episodes_with_observed_history"], 2)
        self.assertEqual(result["metrics"]["wear_pkg"]["episodes"], 2)
        self.assertIn("never used for recency", result["limitations"][0])

    def test_provided_history_can_seed_only_non_temporal_signals(self) -> None:
        result = evaluate_mind(self._dataset(), MindRunConfig(min_observed_history=1, use_provided_history=True))
        self.assertEqual(result["episodes_with_observed_history"], 3)
        self.assertTrue(result["config"]["use_provided_history_for_non_temporal_signals"])

    def test_query_relevance_is_not_profile_relevance(self) -> None:
        lexical = LexicalRelevance.from_documents({"AI": ("openai", "model"), "SPORT": ("football", "score")})
        self.assertGreater(lexical.score(QueryIntent(frozenset({"football"})), "SPORT"), lexical.score(QueryIntent(frozenset({"football"})), "AI"))
        self.assertGreater(lexical.score(ProfileIntent(("AI",)), "AI"), lexical.score(ProfileIntent(("AI",)), "SPORT"))
        self.assertGreater(lexical.vector_score(lexical.profile_vector(ProfileIntent(("AI",))), "AI"), lexical.vector_score(lexical.profile_vector(ProfileIntent(("AI",))), "SPORT"))

    def test_missing_dataset_has_a_clear_error(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "must contain news.tsv"):
            evaluate_mind(Path("/tmp/wear-pkg-does-not-exist"))


if __name__ == "__main__":
    unittest.main()
