from collections.abc import Sequence
from typing import Literal

from pydantic import Field

from veriweb.schemas import (
    Citation,
    Claim,
    Conflict,
    EvidenceCell,
    ModelReport,
    Passage,
    QuestionRequirements,
    StrictModel,
)


class EvidenceInput(Passage):
    source_title: str
    source_url: str
    published_at: str | None


class DraftClaim(StrictModel):
    text: str = Field(min_length=1, max_length=1600)
    section: Literal["summary", "finding"] = "finding"
    evidence_ids: list[str] = Field(min_length=1, max_length=4)


class DraftConflict(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    explanation: str = Field(min_length=1, max_length=1000)
    kind: Literal["numeric", "date", "claim", "scope"]
    left_id: str
    right_id: str


class DraftCell(StrictModel):
    dimension: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=200)
    evidence_id: str


class CellExtraction(StrictModel):
    cells: list[DraftCell] = Field(max_length=24)


def cell_extraction_schema(
    requirements: QuestionRequirements, passages: Sequence[Passage]
) -> dict[str, object]:
    fields: dict[str, object] = {
        "dimension": {
            "type": "string",
            "enum": [dimension.key for dimension in requirements.dimensions],
        },
        "subject": {"type": "string", "enum": requirements.subjects},
        "value": {"type": "string", "minLength": 1, "maxLength": 200},
        "evidence_id": {"type": "string", "enum": [passage.id for passage in passages]},
    }
    return {
        "type": "object",
        "properties": {
            "cells": {
                "type": "array",
                "maxItems": 24,
                "items": {
                    "type": "object",
                    "properties": fields,
                    "required": list(fields),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["cells"],
        "additionalProperties": False,
    }


class DraftReport(StrictModel):
    cells: list[DraftCell] = Field(default_factory=list, max_length=24)
    claims: list[DraftClaim] = Field(max_length=8)
    conflicts: list[DraftConflict] = Field(default_factory=list, max_length=5)
    gaps: list[str] = Field(default_factory=list, max_length=8)


def resolve_draft(draft: DraftReport, passages: Sequence[Passage]) -> ModelReport:
    by_id = {passage.id: passage for passage in passages}
    claims: dict[str, Claim] = {}
    conflicts: list[Conflict] = []
    rejected = 0

    def citation(identifier: str) -> Citation:
        passage = by_id[identifier]
        return Citation(source_id=passage.source_id, quote=passage.quote)

    for claim in draft.claims:
        if any(identifier not in by_id for identifier in claim.evidence_ids):
            rejected += 1
            continue
        key = " ".join(claim.text.lower().split())
        refs = [citation(identifier) for identifier in dict.fromkeys(claim.evidence_ids)]
        if key in claims:
            existing = claims[key]
            for ref in refs:
                if ref not in existing.citations and len(existing.citations) < 4:
                    existing.citations.append(ref)
        else:
            claims[key] = Claim(text=claim.text, section=claim.section, citations=refs)
    for conflict in draft.conflicts:
        if (
            conflict.left_id not in by_id
            or conflict.right_id not in by_id
            or by_id[conflict.left_id].source_id == by_id[conflict.right_id].source_id
        ):
            rejected += 1
            continue
        conflicts.append(
            Conflict(
                title=conflict.title,
                explanation=conflict.explanation,
                kind=conflict.kind,
                left=citation(conflict.left_id),
                right=citation(conflict.right_id),
            )
        )
    cells: list[EvidenceCell] = []
    for cell in draft.cells:
        if cell.evidence_id not in by_id:
            rejected += 1
            continue
        cells.append(
            EvidenceCell(
                dimension=cell.dimension,
                subject=cell.subject,
                value=cell.value,
                citation=citation(cell.evidence_id),
            )
        )
    resolved = list(claims.values())
    if resolved and not any(claim.section == "summary" for claim in resolved):
        resolved[0].section = "summary"
    gaps = draft.gaps[:]
    if rejected:
        gaps.append(f"Removed {rejected} model entries referencing unavailable evidence.")
    return ModelReport(claims=resolved, conflicts=conflicts, gaps=gaps, cells=cells)
