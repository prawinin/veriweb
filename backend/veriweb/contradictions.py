import math
import re
from collections.abc import Sequence
from decimal import Decimal
from itertools import combinations
from typing import Literal

from pydantic import Field

from veriweb.schemas import Citation, Conflict, Passage, StrictModel

NUMBER = re.compile(
    r"(?P<currency>US\$|USD\s*|EUR\s*|GBP\s*|INR\s*|\$|€|£)?(?P<number>\d+(?:,\d{3})*(?:\.\d+)?)(?:\s*(?P<scale>trillion|billion|million|bn|mn|[bmk])(?:\b|(?=(?-i:[A-Z]))))?(?:\s*(?P<unit>twh|gwh|mwh|kwh|percent|%|countries|nations|member states|residents|people|hours?|cycles?|days?|years?))?",
    re.IGNORECASE,
)
STOP_WORDS = frozenset(
    "the a an of for to in is are was were and or its it that this from by with as at about around than on used use has have had total totals official reported reports".split()
)
SCALES = {
    "trillion": 1e12,
    "billion": 1e9,
    "bn": 1e9,
    "b": 1e9,
    "million": 1e6,
    "mn": 1e6,
    "m": 1e6,
    "k": 1e3,
}
ENERGY = {"twh": 1e12, "gwh": 1e9, "mwh": 1e6, "kwh": 1e3}


def format_quantity(value: float, unit: str) -> str:
    if unit == "Wh":
        for threshold, label in ((1e12, "TWh"), (1e9, "GWh"), (1e6, "MWh"), (1e3, "kWh")):
            if abs(value) >= threshold:
                return f"{value / threshold:g} {label}"
        return f"{value:g} Wh"
    if unit == "percent":
        return f"{value:g}%"
    if unit == "country_count":
        return f"{value:g} countries"
    number = f"{value:g}"
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= threshold:
            number = f"{value / threshold:g}{suffix}"
            break
    if unit in {"$", "€", "£"}:
        return f"{unit}{number}"
    if unit in {"USD", "EUR", "GBP", "INR"}:
        return f"{unit} {number}"
    if unit in {"residents", "hours", "cycles", "days", "years"}:
        return f"{value:g} {unit}"
    return number


def conflict_is_evidenced(conflict: Conflict, passages: Sequence[Passage]) -> bool:
    for candidate in numeric_candidates(passages):
        left = next(p for p in passages if p.id == candidate.left_id)
        right = next(p for p in passages if p.id == candidate.right_id)
        if any(
            a.source_id == conflict.left.source_id
            and conflict.left.quote in a.quote
            and b.source_id == conflict.right.source_id
            and conflict.right.quote in b.quote
            for a, b in ((left, right), (right, left))
        ):
            return True
    if conflict.kind not in {"claim", "date"}:
        return False
    left_text, right_text = conflict.left.quote.lower(), conflict.right.quote.lower()
    shared = set(re.findall(r"\w+", left_text)) & set(re.findall(r"\w+", right_text)) - STOP_WORDS
    if len(shared) < 3:
        return False
    if conflict.kind == "date":
        left_dates = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", left_text))
        right_dates = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", right_text))
        return bool(left_dates and right_dates and left_dates != right_dates)
    for positive, negative in (
        (r"\bpermitted\b", r"\bprohibited\b"),
        (r"\bapproved\b", r"\brejected\b"),
        (r"\bavailable\b", r"\b(?:not\s+(?:commercially\s+)?available|unavailable)\b"),
    ):
        if (re.search(positive, left_text) and re.search(negative, right_text)) or (
            re.search(positive, right_text) and re.search(negative, left_text)
        ):
            return True
    return False


class NumericCandidate(StrictModel):
    id: str
    left_id: str
    right_id: str
    left_value: float
    right_value: float
    unit: str


class Comparison(StrictModel):
    candidate_id: str
    title: str = Field(min_length=1, max_length=200)
    explanation: str = Field(min_length=1, max_length=1000)
    relation: Literal["conflict", "scope", "date", "not_comparable"]


class Comparisons(StrictModel):
    comparisons: list[Comparison] = Field(min_length=1, max_length=4)


def quantities(text: str) -> list[tuple[str, float]]:
    results: list[tuple[str, float]] = []
    for match in NUMBER.finditer(text):
        currency = (match.group("currency") or "").strip().upper()
        scale = (match.group("scale") or "").lower()
        unit = (match.group("unit") or "").lower()
        if not currency and not unit and not scale:
            continue
        value = float(
            Decimal(match.group("number").replace(",", "")) * Decimal(str(SCALES.get(scale, 1)))
        )
        if currency:
            unit = "USD" if currency in {"USD", "US$"} else currency
        elif unit in ENERGY:
            value *= ENERGY[unit]
            unit = "Wh"
        elif unit in {"countries", "nations", "member states"}:
            unit = "country_count"
        elif unit in {"residents", "people"}:
            unit = "residents"
        elif unit in {"hour", "hours", "cycle", "cycles", "day", "days", "year", "years"}:
            unit = unit.rstrip("s") + "s"
        elif unit in {"%", "percent"}:
            unit = "percent"
        else:
            unit = "scaled_count"
        if math.isfinite(value) and (unit, value) not in results:
            results.append((unit, value))
    return results[:8]


def numeric_candidates(passages: Sequence[Passage]) -> list[NumericCandidate]:
    candidates: list[NumericCandidate] = []
    seen: set[tuple[str, str, str, float, float]] = set()
    for left, right in combinations(passages, 2):
        if left.source_id == right.source_id:
            continue
        left_words = set(re.findall(r"[a-z]+", left.quote.lower())) - STOP_WORDS
        right_words = set(re.findall(r"[a-z]+", right.quote.lower())) - STOP_WORDS
        shared = len(left_words & right_words)
        if shared < 3 or shared / max(1, min(len(left_words), len(right_words))) < 0.35:
            continue
        for left_unit, left_value in quantities(left.quote):
            for right_unit, right_value in quantities(right.quote):
                if left_unit != right_unit or math.isclose(left_value, right_value, rel_tol=0.005):
                    continue
                key = (left.source_id, right.source_id, left_unit, left_value, right_value)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    NumericCandidate(
                        id=f"c{len(candidates) + 1}",
                        left_id=left.id,
                        right_id=right.id,
                        left_value=left_value,
                        right_value=right_value,
                        unit=left_unit,
                    )
                )
                if len(candidates) == 4:
                    return candidates
    return candidates


def resolve_comparisons(
    comparisons: Comparisons, candidates: list[NumericCandidate], passages: Sequence[Passage]
) -> tuple[list[Conflict], list[str]]:
    by_id = {passage.id: passage for passage in passages}
    classified = {item.candidate_id: item for item in comparisons.comparisons}
    conflicts: list[Conflict] = []
    unresolved = 0
    for candidate in candidates:
        comparison = classified.get(candidate.id)
        left, right = by_id[candidate.left_id], by_id[candidate.right_id]
        if comparison is None or comparison.relation == "not_comparable":
            unresolved += 1
            kind: Literal["numeric", "scope", "date", "unresolved"] = "unresolved"
            title = "Different figures need context"
            explanation = "These passages contain different reported quantities. The model did not establish a comparable scope or period. Inspect the original context before treating this as a contradiction."
        else:
            kind = "numeric" if comparison.relation == "conflict" else comparison.relation
            title, explanation = comparison.title, comparison.explanation
        conflicts.append(
            Conflict(
                title=title,
                explanation=explanation,
                kind=kind,
                left_quantity=format_quantity(candidate.left_value, candidate.unit),
                right_quantity=format_quantity(candidate.right_value, candidate.unit),
                left=Citation(source_id=left.source_id, quote=left.quote),
                right=Citation(source_id=right.source_id, quote=right.quote),
            )
        )
    gaps = (
        [f"{unresolved} numeric differences remain unresolved and require review."]
        if unresolved
        else []
    )
    return conflicts, gaps
