import re
from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray
from rank_bm25 import BM25Plus

from veriweb.schemas import Passage, Source

Encoder = Callable[[list[str]], NDArray[np.float32]]


def tokenize(text: str) -> list[str]:
    return re.findall(r"[\w]+", text.lower())


def split_passages(sources: list[Source]) -> list[Passage]:
    passages: list[Passage] = []
    seen: set[str] = set()
    for source in sources:
        for match in re.finditer(r"^\|[^\n]*(?:\n\|[^\n]*)*|[^\n]+", source.text, re.M):
            for start in range(match.start(), match.end(), 1200):
                quote = source.text[start : min(start + 1200, match.end())].strip()
                normalized = " ".join(tokenize(quote))
                if len(quote) < 15 or normalized in seen:
                    continue
                seen.add(normalized)
                exact_start = source.text.index(quote, start)
                passages.append(
                    Passage(
                        id=f"{source.id}-p{len(passages) + 1}",
                        source_id=source.id,
                        quote=quote,
                        start=exact_start,
                        end=exact_start + len(quote),
                        score=0,
                    )
                )
                if len(passages) >= 1200:
                    return passages
    return passages


def rank_passages(
    question: str,
    sources: list[Source],
    limit: int = 10,
    encoder: Encoder | None = None,
    candidate_limit: int = 96,
) -> list[Passage]:
    passages = split_passages(sources)
    if not passages:
        return []
    scores = np.asarray(
        BM25Plus([tokenize(p.quote) for p in passages]).get_scores(tokenize(question))
    )
    orders = [np.argsort(-scores, kind="stable")]
    if encoder:
        candidates = orders[0][: max(limit, candidate_limit)]
        vectors = encoder([question, *[passages[int(i)].quote for i in candidates]])
        norm = np.linalg.norm(vectors, axis=1, keepdims=True)
        normalized = vectors / np.maximum(norm, 1e-9)
        semantic = normalized[1:] @ normalized[0]
        orders.append(candidates[np.argsort(-semantic, kind="stable")])
    fused = np.zeros(len(passages))
    for order in orders:
        for rank, idx in enumerate(order):
            fused[idx] += 1 / (60 + rank + 1)
    selected = np.argsort(-fused, kind="stable")[:limit]
    return [
        passages[int(i)].model_copy(update={"score": round(float(fused[i]), 6)}) for i in selected
    ]
