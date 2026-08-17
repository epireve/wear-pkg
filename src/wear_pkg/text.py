from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, Mapping

TOKEN_RE = re.compile(r"[\w]+", flags=re.UNICODE)


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in TOKEN_RE.findall(text or ""))


def tf(tokens: Iterable[str]) -> Counter[str]:
    return Counter(tokens)


def cosine(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(weight * right.get(token, 0.0) for token, weight in left.items())
    left_norm = math.sqrt(sum(weight * weight for weight in left.values()))
    right_norm = math.sqrt(sum(weight * weight for weight in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0
