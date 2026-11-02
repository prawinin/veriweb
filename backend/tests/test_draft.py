from veriweb.draft import DraftReport, resolve_draft
from veriweb.schemas import Passage


def test_model_chooses_evidence_ids_and_server_preserves_exact_quotes() -> None:
    quote = "The program received ten billion dollars for manufacturing."
    evidence = [Passage(id="s1-p7", source_id="s1", quote=quote, start=0, end=len(quote), score=1)]
    draft = DraftReport.model_validate(
        {
            "claims": [
                {
                    "text": "The program received ten billion dollars.",
                    "section": "summary",
                    "evidence_ids": ["s1-p7"],
                },
                {"text": "Unknown evidence must be removed", "evidence_ids": ["s9-p9"]},
            ],
            "conflicts": [],
            "gaps": [],
        }
    )
    report = resolve_draft(draft, evidence)
    assert len(report.claims) == 1
    assert report.claims[0].citations[0].quote == quote
    assert report.claims[0].citations[0].source_id == "s1"
    assert report.gaps


def test_identical_claims_merge_evidence_instead_of_repeating_prose() -> None:
    quote = "The program received ten billion dollars for manufacturing."
    evidence = [
        Passage(id=f"s{i}-p{i}", source_id=f"s{i}", quote=quote, start=0, end=len(quote), score=1)
        for i in (1, 2)
    ]
    draft = DraftReport.model_validate(
        {
            "claims": [
                {"text": "The program received ten billion dollars.", "evidence_ids": ["s1-p1"]},
                {"text": "The program received ten billion dollars.", "evidence_ids": ["s2-p2"]},
            ]
        }
    )
    report = resolve_draft(draft, evidence)
    assert len(report.claims) == 1
    assert len(report.claims[0].citations) == 2
