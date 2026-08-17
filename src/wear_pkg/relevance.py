from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Mapping

from .intent import ContextIntent, ProfileIntent, QueryIntent
from .text import cosine


@dataclass
class LexicalRelevance:
    """Inspectable TF-IDF relevance for profiles, queries, and contexts."""

    item_tokens: Mapping[str, tuple[str, ...]]
    idf: Mapping[str, float]

    @classmethod
    def from_documents(cls, documents: Mapping[str, tuple[str, ...]]) -> "LexicalRelevance":
        document_frequency: Counter[str] = Counter()
        for tokens in documents.values():
            document_frequency.update(set(tokens))
        total = max(len(documents), 1)
        idf = {
            token: math.log((total + 1) / (frequency + 1)) + 1.0
            for token, frequency in document_frequency.items()
        }
        return cls(item_tokens=documents, idf=idf)

    def vector(self, tokens: tuple[str, ...]) -> dict[str, float]:
        counts = Counter(tokens)
        return {token: count * self.idf.get(token, 0.0) for token, count in counts.items()}

    def query_score(self, intent: QueryIntent | ContextIntent, item_id: str) -> float:
        return cosine(self.vector(tuple(intent.tokens)), self.vector(self.item_tokens.get(item_id, ())))

    def profile_vector(self, intent: ProfileIntent) -> dict[str, float]:
        profile: Counter[str] = Counter()
        for historical_id in intent.item_ids:
            profile.update(self.item_tokens.get(historical_id, ()))
        return self.vector(tuple(profile.elements()))

    def vector_score(self, intent_vector: Mapping[str, float], item_id: str) -> float:
        return cosine(intent_vector, self.vector(self.item_tokens.get(item_id, ())))

    def profile_score(self, intent: ProfileIntent, item_id: str) -> float:
        return self.vector_score(self.profile_vector(intent), item_id)

    def score(self, intent: QueryIntent | ProfileIntent | ContextIntent, item_id: str) -> float:
        if isinstance(intent, ProfileIntent):
            return self.profile_score(intent, item_id)
        return self.query_score(intent, item_id)
