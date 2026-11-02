"""Controlled-fixture evaluation; answer keys never enter the research pipeline."""

import asyncio
import math
import re
import time
import unicodedata
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from veriweb.config import Settings
from veriweb.model import ModelClient
from veriweb.pipeline import Researcher
from veriweb.schemas import Citation, ResearchRequest, ResearchResult, RunEvent, Source


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ExpectedValue(EvaluationModel):
    value: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class ExpectedFacet(EvaluationModel):
    dimension: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    subject: str = Field(min_length=1)
    kind: Literal["quantitative", "availability", "date", "qualitative"]
    status: Literal["supported", "missing"]
    values: list[ExpectedValue]

    @model_validator(mode="after")
    def coherent_status(self) -> Self:
        if bool(self.values) != (self.status == "supported"):
            raise ValueError("Supported facets require values; missing facets forbid them")
        return self


class ExpectedConflict(EvaluationModel):
    source_ids: list[str] = Field(min_length=2, max_length=2)
    kind: Literal["numeric", "date", "claim", "scope", "unresolved"]

    @model_validator(mode="after")
    def distinct_sources(self) -> Self:
        if len(set(self.source_ids)) != 2:
            raise ValueError("Conflicts require two distinct sources")
        return self


class EvaluationCase(EvaluationModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    fixture_kind: Literal["controlled_synthetic"]
    category: Literal["numeric", "comparison", "conflict", "scope_date", "unanswerable"]
    question: str = Field(min_length=12, max_length=1500)
    sources: list[Source] = Field(min_length=1, max_length=8)
    expected_facets: list[ExpectedFacet] = Field(min_length=1)
    expected_conflicts: list[ExpectedConflict] = Field(default_factory=list)
    allowed_conflicts: list[ExpectedConflict] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_truth(self) -> Self:
        ResearchRequest(question=self.question)
        by_id = {source.id: source for source in self.sources}
        if len(by_id) != len(self.sources):
            raise ValueError("Fixture source IDs must be unique")
        keys = [(normalize(f.dimension), normalize(f.subject)) for f in self.expected_facets]
        if len(set(keys)) != len(keys):
            raise ValueError("Requested facets must be unique")
        for facet in self.expected_facets:
            for value in facet.values:
                if len(set(value.source_ids)) != len(value.source_ids):
                    raise ValueError("Expected source IDs must be unique")
                for source_id in value.source_ids:
                    if source_id not in by_id or normalize(value.value) not in normalize(
                        by_id[source_id].text
                    ):
                        raise ValueError(
                            "Expected value must occur in each designated fixture source"
                        )
        for conflict in self.expected_conflicts + self.allowed_conflicts:
            if any(source_id not in by_id for source_id in conflict.source_ids):
                raise ValueError("Expected conflict refers to unknown source")
        allowed = {conflict_key(c.source_ids, c.kind) for c in self.allowed_conflicts}
        if any(conflict_key(c.source_ids, c.kind) not in allowed for c in self.expected_conflicts):
            raise ValueError("Required conflicts must also be allowed")
        return self


class EvaluationManifest(EvaluationModel):
    version: Literal[1]
    description: str = Field(min_length=1)
    cases: list[EvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_cases(self) -> Self:
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Fixture case IDs must be unique")
        return self


class EvaluationValue(EvaluationModel):
    value: str
    citation: Citation
    published_at: str | None = None


class EvaluationCell(EvaluationModel):
    subject: str
    status: Literal["supported", "missing"]
    values: list[EvaluationValue]


class EvaluationCoverage(EvaluationModel):
    dimension: str
    label: str
    kind: Literal["quantitative", "availability", "date", "qualitative"]
    cells: list[EvaluationCell]


class CaseScore(EvaluationModel):
    case_id: str
    category: str
    answer_accuracy: float | None
    coverage_recall: float
    abstention_accuracy: float | None
    conflict_precision: float
    conflict_recall: float
    provenance_rate: float | None
    provenance_valid: int
    provenance_total: int
    semantic_entailment: Literal["not_automatically_verified"] = "not_automatically_verified"
    missing_facets: list[str]
    incorrect_facets: list[str]
    passed: bool
    wall_seconds: float | None = None
    model_seconds: float | None = None
    model_calls: int | None = None
    generation_seconds: float | None = None


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold().strip()
    text = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", text)
    return " ".join(text.split())


def conflict_key(source_ids: list[str], kind: str) -> tuple[str, str, str]:
    left, right = sorted(source_ids)
    return left, right, kind


def load_cases(path: Path) -> list[EvaluationCase]:
    if path.stat().st_size > 2_000_000:
        raise ValueError("Fixture manifest exceeds size limit")
    return EvaluationManifest.model_validate_json(path.read_bytes(), strict=True).cases


def _read_result(
    payload: ResearchResult | dict[str, object],
) -> tuple[ResearchResult, list[EvaluationCoverage]]:
    data = payload.model_dump(mode="json") if isinstance(payload, ResearchResult) else dict(payload)
    coverage = TypeAdapter(list[EvaluationCoverage]).validate_python(
        data.get("coverage", []), strict=True
    )
    if "coverage" not in ResearchResult.model_fields:
        data.pop("coverage", None)
    return ResearchResult.model_validate(data, strict=True), coverage


def score_result(
    case: EvaluationCase,
    payload: ResearchResult | dict[str, object],
    *,
    wall_seconds: float | None = None,
    model_seconds: float | None = None,
    model_calls: int | None = None,
) -> CaseScore:
    result, coverage = _read_result(payload)
    if normalize(result.question) != normalize(case.question):
        raise ValueError("Result question does not match the selected case")
    result_sources = {source.id: source for source in result.sources}
    fixture_sources = {source.id: source for source in case.sources}

    def provenance(ref: Citation) -> bool:
        original = fixture_sources.get(ref.source_id)
        returned = result_sources.get(ref.source_id)
        return bool(
            original and returned and ref.quote in original.text and ref.quote in returned.text
        )

    citations = [ref for claim in result.claims for ref in claim.citations]
    citations += [ref for conflict in result.conflicts for ref in (conflict.left, conflict.right)]
    citations += [value.citation for row in coverage for cell in row.cells for value in cell.values]
    valid_count = sum(provenance(ref) for ref in citations)
    supported_count = sum(f.status == "supported" for f in case.expected_facets)
    missing_count = len(case.expected_facets) - supported_count
    answered = 0
    abstained = 0
    covered = 0
    missing: list[str] = []
    incorrect: list[str] = []
    for facet in case.expected_facets:
        labels = {normalize(label) for label in [facet.dimension, *facet.aliases]}
        matches = [
            cell
            for row in coverage
            if row.kind == facet.kind
            and (normalize(row.dimension) in labels or normalize(row.label) in labels)
            for cell in row.cells
            if normalize(cell.subject) == normalize(facet.subject)
        ]
        name = f"{facet.subject}: {facet.dimension}"
        if len(matches) != 1:
            missing.append(name)
            continue
        cell = matches[0]
        covered += 1
        if facet.status == "missing":
            correct = (
                cell.status == "missing"
                and not cell.values
                and result.status == "incomplete"
                and (supported_count > 0 or not result.claims)
            )
            abstained += correct
        else:
            expected = {normalize(value.value) for value in facet.values}
            actual = {normalize(value.value) for value in cell.values}
            correct = (
                cell.status == "supported"
                and expected == actual
                and all(
                    any(
                        normalize(value.value) == normalize(wanted.value)
                        and value.citation.source_id in wanted.source_ids
                        and normalize(wanted.value) in normalize(value.citation.quote)
                        and provenance(value.citation)
                        for wanted in facet.values
                    )
                    for value in cell.values
                )
            )
            answered += correct
        if not correct:
            incorrect.append(name)
    allowed = {conflict_key(c.source_ids, c.kind) for c in case.allowed_conflicts}
    required = {conflict_key(c.source_ids, c.kind) for c in case.expected_conflicts}
    predicted = {
        conflict_key([c.left.source_id, c.right.source_id], c.kind)
        for c in result.conflicts
        if c.left.source_id != c.right.source_id and provenance(c.left) and provenance(c.right)
    }
    precision = len(predicted & allowed) / len(result.conflicts) if result.conflicts else 1.0
    recall = len(predicted & required) / len(required) if required else 1.0
    answer_accuracy = answered / supported_count if supported_count else None
    abstention_accuracy = abstained / missing_count if missing_count else None
    provenance_rate = valid_count / len(citations) if citations else None
    return CaseScore(
        case_id=case.id,
        category=case.category,
        answer_accuracy=answer_accuracy,
        coverage_recall=covered / len(case.expected_facets),
        abstention_accuracy=abstention_accuracy,
        conflict_precision=precision,
        conflict_recall=recall,
        provenance_rate=provenance_rate,
        provenance_valid=valid_count,
        provenance_total=len(citations),
        missing_facets=missing,
        incorrect_facets=incorrect,
        passed=not missing
        and not incorrect
        and precision == 1
        and recall == 1
        and valid_count == len(citations),
        wall_seconds=wall_seconds,
        model_seconds=model_seconds,
        model_calls=model_calls,
        generation_seconds=result.telemetry.generation_seconds,
    )


class FixtureResearcher(Researcher):
    """Replace external retrieval only; model planning, ranking and synthesis remain real."""

    def __init__(self, case: EvaluationCase, settings: Settings, client: httpx.AsyncClient) -> None:
        super().__init__(settings, client)
        self.case = case

    async def search(self, queries: list[str]) -> list[tuple[str, str]]:
        return [(source.url, source.title) for source in self.case.sources]

    async def collect(self, urls: list[tuple[str, str]]) -> AsyncIterator[Source | str]:
        selected = {url for url, _ in urls}
        for source in self.case.sources:
            if source.url in selected:
                yield source.model_copy(deep=True)


class TimedModelClient(ModelClient):
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        super().__init__(settings, client)
        self.total_seconds = 0.0
        self.calls = 0

    async def complete(
        self,
        system: str,
        content: str,
        max_tokens: int = 1600,
        schema: dict[str, object] | None = None,
    ) -> str:
        started = time.perf_counter()
        self.calls += 1
        try:
            return await super().complete(system, content, max_tokens, schema)
        finally:
            self.total_seconds += time.perf_counter() - started


async def run_fixture(
    case: EvaluationCase, settings: Settings, deadline: float
) -> tuple[ResearchResult, CaseScore]:
    if not math.isfinite(deadline) or deadline <= 0 or deadline > 3600:
        raise ValueError("Deadline must be positive and at most 3600 seconds")
    started = time.perf_counter()
    async with (
        asyncio.timeout(deadline),
        httpx.AsyncClient(
            timeout=httpx.Timeout(settings.model_timeout),
            trust_env=False,
            limits=httpx.Limits(max_connections=6),
            follow_redirects=False,
        ) as client,
    ):
        researcher = FixtureResearcher(case, settings, client)
        model = TimedModelClient(settings, client)
        researcher.model = model
        researcher.model_available = await model.available()
        if not researcher.model_available:
            raise ValueError(
                "Configured inference endpoint is unavailable; fixture benchmark requires real synthesis"
            )
        async for event in researcher.run(case.question):
            if event.type == "error":
                raise ValueError("Research pipeline returned an error")
            if event.result is not None:
                score = score_result(
                    case,
                    event.result,
                    wall_seconds=time.perf_counter() - started,
                    model_seconds=model.total_seconds,
                    model_calls=model.calls,
                )
                return event.result, score
    raise ValueError("Research stream ended without a terminal result")


async def run_live(
    question: str, base_url: str, client: httpx.AsyncClient, deadline: float
) -> ResearchResult:
    request = ResearchRequest(question=question)
    endpoint = urlsplit(base_url)
    if (
        endpoint.scheme not in {"http", "https"}
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
    ):
        raise ValueError("BASE_URL must be HTTP(S) without embedded credentials")
    if not math.isfinite(deadline) or deadline <= 0 or deadline > 3600:
        raise ValueError("Deadline must be positive and at most 3600 seconds")
    async with (
        asyncio.timeout(deadline),
        client.stream(
            "POST",
            f"{base_url.rstrip('/')}/api/research",
            json=request.model_dump(),
            timeout=deadline,
        ) as response,
    ):
        response.raise_for_status()
        total = 0
        async for line in response.aiter_lines():
            total += len(line)
            if total > 8_000_000 or len(line) > 2_000_000:
                raise ValueError("Research stream exceeds size limit")
            if not line.strip():
                continue
            event = RunEvent.model_validate_json(line, strict=True)
            if event.type == "error":
                raise ValueError("Research stream returned an error event")
            if event.result is not None:
                return event.result
    raise ValueError("Research stream ended without a terminal result")


def markdown_report(scores: list[CaseScore], errors: dict[str, str], mode: str) -> str:
    lines = [
        "# Controlled fixture evaluation",
        "",
        f"Mode: {mode}.",
        "",
        "Authored synthetic fixtures; not a live-web benchmark or demonstrated unseen held-out accuracy.",
        "Semantic entailment is not automatically verified. Quote substring provenance is a separate check.",
        "",
        "| Case | Exact answers | Coverage | Abstention | Candidate precision | Candidate recall | Provenance | Pass |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    def rate(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.2f}"

    for score in scores:
        lines.append(
            f"| {score.case_id} | {rate(score.answer_accuracy)} | {rate(score.coverage_recall)} | "
            f"{rate(score.abstention_accuracy)} | {rate(score.conflict_precision)} | "
            f"{rate(score.conflict_recall)} | {rate(score.provenance_rate)} | {score.passed} |"
        )
    lines += [
        "",
        f"Passed {sum(score.passed for score in scores)}/{len(scores) + len(errors)} attempted cases.",
    ]
    if errors:
        lines += ["", "Execution or artifact errors:", ""] + [
            f"- {key}: {value}" for key, value in errors.items()
        ]
    lines += [
        "",
        "Latency fields in JSON separate whole-run wall time, total model-call wall time, and synthesis telemetry.",
        "",
    ]
    return "\n".join(lines)
