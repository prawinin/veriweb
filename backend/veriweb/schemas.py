import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResearchRequest(StrictModel):
    question: str = Field(min_length=12, max_length=1500)
    mode: Literal["research", "excerpts"] = "research"

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 12 or any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("Enter a research question of at least 12 characters")
        return value


class RequestedDimension(StrictModel):
    year: str | None = Field(default=None, pattern=r"^(19|20)\d{2}$")
    qualifier: str | None = Field(default=None, max_length=80)
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    label: str = Field(min_length=1, max_length=80)
    kind: Literal["quantitative", "availability", "date", "qualitative"]


class QuestionRequirements(StrictModel):
    subjects: list[str] = Field(default_factory=list, max_length=4)
    dimensions: list[RequestedDimension] = Field(default_factory=list, max_length=6)


class SourceLink(StrictModel):
    url: str = Field(max_length=2000)
    title: str = Field(min_length=1, max_length=200)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        return str(HttpUrl(value))


class Source(StrictModel):
    id: str = Field(pattern=r"^s[1-8]$")
    title: str = Field(min_length=1, max_length=500)
    url: str
    text: str = Field(min_length=1, max_length=100_000)
    retrieved_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    published_at: str | None = None
    source_type: Literal["public_institution", "research", "technical", "other"] = "other"
    links: list[SourceLink] = Field(default_factory=list, max_length=16)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        return str(HttpUrl(value))


class Passage(StrictModel):
    id: str
    source_id: str
    quote: str = Field(min_length=1, max_length=1400)
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    score: float


class Citation(StrictModel):
    source_id: str
    quote: str = Field(min_length=15, max_length=1400)


class Claim(StrictModel):
    text: str = Field(min_length=1, max_length=1600)
    section: Literal["summary", "finding"] = "finding"
    citations: list[Citation] = Field(min_length=1, max_length=4)


class Conflict(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    explanation: str = Field(min_length=1, max_length=1000)
    kind: Literal["numeric", "date", "claim", "scope", "unresolved"]
    left: Citation
    right: Citation
    left_quantity: str | None = Field(default=None, max_length=80)
    right_quantity: str | None = Field(default=None, max_length=80)


class EvidenceCell(StrictModel):
    dimension: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=200)
    citation: Citation


class CoverageValue(StrictModel):
    value: str = Field(min_length=1, max_length=200)
    citation: Citation
    published_at: str | None = None


class CoverageCell(StrictModel):
    subject: str
    status: Literal["supported", "missing"]
    values: list[CoverageValue] = Field(default_factory=list, max_length=3)


class CoverageRow(StrictModel):
    dimension: str
    label: str
    kind: Literal["quantitative", "availability", "date", "qualitative"]
    cells: list[CoverageCell] = Field(max_length=4)


class ModelReport(StrictModel):
    cells: list[EvidenceCell] = Field(default_factory=list, max_length=24)
    claims: list[Claim] = Field(max_length=12)
    conflicts: list[Conflict] = Field(default_factory=list, max_length=5)
    gaps: list[str] = Field(default_factory=list, max_length=8)


class Telemetry(StrictModel):
    model: str | None = None
    backend: str = "unverified"
    retrieval_seconds: float | None = None
    generation_seconds: float | None = None
    tokens_per_second: float | None = None
    ranking: str = "BM25"
    paragraphs: int = 0


class ResearchResult(StrictModel):
    coverage: list[CoverageRow] = Field(default_factory=list, max_length=6)
    id: str
    question: str
    status: Literal["complete", "incomplete", "excerpts"]
    queries: list[str]
    sources: list[Source]
    passages: list[Passage]
    claims: list[Claim]
    conflicts: list[Conflict]
    gaps: list[str]
    telemetry: Telemetry
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class RunEvent(StrictModel):
    type: Literal["log", "queries", "source", "result", "error", "heartbeat"]
    stage: str
    message: str
    level: Literal["info", "success", "warning", "error"] = "info"
    elapsed: float = 0
    queries: list[str] | None = None
    source: Source | None = None
    result: ResearchResult | None = None


def valid_citation(
    citation: Citation, sources: list[Source], passages: list[Passage] | None = None
) -> bool:
    original = any(s.id == citation.source_id and citation.quote in s.text for s in sources)
    retained = passages is None or any(
        p.source_id == citation.source_id and citation.quote in p.quote for p in passages
    )
    return original and retained


def numeric_claim_supported(claim: Claim, subjects: list[str] | None = None) -> bool:
    pattern = re.compile(
        r"(?<![\w.])(?P<number>\d+(?:,\d{3})*(?:\.\d+)?)(?:\s*(?P<scale>trillion|billion|million|bn|mn)(?:\b|(?=(?-i:[A-Z]))))?",
        re.I,
    )
    scales = {
        "trillion": Decimal("1e12"),
        "billion": Decimal("1e9"),
        "bn": Decimal("1e9"),
        "million": Decimal("1e6"),
        "mn": Decimal("1e6"),
    }

    def quantities(text: str) -> set[Decimal]:
        return {
            Decimal(match.group("number").replace(",", ""))
            * scales.get((match.group("scale") or "").lower(), Decimal(1))
            for match in pattern.finditer(text)
        }

    cited = set().union(*(quantities(ref.quote) for ref in claim.citations))
    if not quantities(claim.text).issubset(cited):
        return False
    if subjects:

        def associated(text: str) -> dict[str, set[tuple[Decimal, str]]]:
            result: dict[str, set[tuple[Decimal, str]]] = {subject: set() for subject in subjects}
            mentions = sorted(
                (match.start(), subject)
                for subject in subjects
                if subject != "Requested answer"
                for match in re.finditer(
                    r"(?<!\w)"
                    + re.escape(re.sub(r"\s+batter(?:y|ies)$", "", subject, flags=re.I))
                    + r"(?!\w)",
                    text,
                    re.I,
                )
            )
            for match in pattern.finditer(text):
                candidates = [item for item in mentions if item[0] <= match.start()]
                if candidates:
                    unit_match = re.match(
                        r"\s*(tb|gb|mb|kb|twh|gwh|mwh|kwh|wh|cycles?|years?|months?|hours?|residents?|people|countries|percent|%)\b",
                        text[match.end() :],
                        re.I,
                    )
                    unit = unit_match.group().strip().lower() if unit_match else ""
                    currency = re.search(
                        r"(USD|US\$|\$|€|£)\s*$",
                        text[max(0, match.start() - 5) : match.start()],
                        re.I,
                    )
                    if currency:
                        unit = (
                            "usd"
                            if currency.group(1).upper() in {"USD", "US$", "$"}
                            else currency.group(1)
                        )
                    result[max(candidates)[1]].update(
                        (number, unit) for number in quantities(match.group())
                    )
            return result

        claimed = associated(claim.text)
        quoted: dict[str, set[tuple[Decimal, str]]] = {subject: set() for subject in subjects}
        for reference in claim.citations:
            for subject, values in associated(reference.quote).items():
                quoted[subject].update(values)
        if any(not values.issubset(quoted[subject]) for subject, values in claimed.items()):
            return False
    return True


def validate_claims(
    claims: list[Claim],
    sources: list[Source],
    passages: list[Passage] | None = None,
    subjects: list[str] | None = None,
) -> tuple[list[Claim], int]:
    valid = [
        c
        for c in claims
        if all(valid_citation(ref, sources, passages) for ref in c.citations)
        and numeric_claim_supported(c, subjects)
    ]
    return valid, len(claims) - len(valid)


def validate_conflicts(
    conflicts: list[Conflict], sources: list[Source], passages: list[Passage] | None = None
) -> list[Conflict]:
    return [
        c
        for c in conflicts
        if c.left.source_id != c.right.source_id
        and valid_citation(c.left, sources, passages)
        and valid_citation(c.right, sources, passages)
    ]
