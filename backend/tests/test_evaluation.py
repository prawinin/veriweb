import importlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError


def evaluation() -> ModuleType:
    assert importlib.util.find_spec("veriweb.evaluation") is not None, "evaluation harness missing"
    return importlib.import_module("veriweb.evaluation")


def fixture_path() -> Path:
    return Path(__file__).resolve().parents[2] / "evals" / "controlled-fixtures.json"


def artifact() -> dict[str, object]:
    return {
        "id": "scorer-test",
        "question": "What was the population of Alder in 2025, measured in residents?",
        "status": "complete",
        "queries": [],
        "passages": [],
        "sources": [
            {
                "id": "s1",
                "title": "Controlled census",
                "url": "https://alpha.example/census",
                "text": "Alder population in 2025 was 12,400 residents.",
            }
        ],
        "claims": [
            {
                "text": "Alder had 12,400 residents.",
                "section": "summary",
                "citations": [
                    {"source_id": "s1", "quote": "Alder population in 2025 was 12,400 residents."}
                ],
            }
        ],
        "conflicts": [],
        "gaps": [],
        "telemetry": {},
        "coverage": [
            {
                "dimension": "population",
                "label": "Population",
                "kind": "quantitative",
                "cells": [
                    {
                        "subject": "Alder",
                        "status": "supported",
                        "values": [
                            {
                                "value": "12,400 residents",
                                "published_at": None,
                                "citation": {
                                    "source_id": "s1",
                                    "quote": "Alder population in 2025 was 12,400 residents.",
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_exact_answer_and_provenance_are_separate_from_semantic_entailment() -> None:
    harness = evaluation()
    case = harness.load_cases(fixture_path())[0]
    score = harness.score_result(case, artifact(), wall_seconds=2.5)
    assert score.answer_accuracy == 1.0
    assert score.coverage_recall == 1.0
    assert score.provenance_rate == 1.0
    assert score.semantic_entailment == "not_automatically_verified"
    assert score.wall_seconds == 2.5
    broken = artifact()
    broken["coverage"][0]["cells"][0]["values"][0]["value"] = "99 residents"
    wrong = harness.score_result(case, broken)
    assert wrong.answer_accuracy == 0.0
    assert wrong.provenance_rate == 1.0


def test_fabricated_or_wrong_source_quotes_do_not_earn_answer_credit() -> None:
    harness = evaluation()
    case = harness.load_cases(fixture_path())[0]
    result = artifact()
    result["coverage"][0]["cells"][0]["values"][0]["citation"]["quote"] = (
        "Invented population quotation."
    )
    score = harness.score_result(case, result)
    assert score.answer_accuracy == 0.0
    assert score.provenance_rate < 1.0
    result = artifact()
    result["coverage"][0]["cells"][0]["values"][0]["citation"]["source_id"] = "s2"
    assert harness.score_result(case, result).answer_accuracy == 0.0


def test_conflict_pair_kind_precision_penalizes_scope_as_real_conflict() -> None:
    harness = evaluation()
    case = next(c for c in harness.load_cases(fixture_path()) if c.id == "scope-population")
    result = artifact()
    result["question"] = case.question
    result["sources"] = [s.model_dump() for s in case.sources]
    result["claims"] = []
    result["coverage"] = []
    result["conflicts"] = [
        {
            "title": "Population differs",
            "explanation": "The areas differ.",
            "kind": "scope",
            "left": {"source_id": "s1", "quote": case.sources[0].text},
            "right": {"source_id": "s2", "quote": case.sources[1].text},
        }
    ]
    score = harness.score_result(case, result)
    assert score.conflict_precision == 1.0
    assert score.conflict_recall == 1.0
    result["conflicts"][0]["kind"] = "numeric"
    wrong = harness.score_result(case, result)
    assert wrong.conflict_precision == 0.0
    assert wrong.conflict_recall == 0.0


def test_missing_facet_requires_missing_cell_incomplete_and_no_invented_values() -> None:
    harness = evaluation()
    case = next(c for c in harness.load_cases(fixture_path()) if c.id == "unanswerable-budget")
    result = artifact()
    result["question"] = case.question
    result["status"] = "incomplete"
    result["claims"] = []
    result["coverage"] = [
        {
            "dimension": "budget",
            "label": "Budget",
            "kind": "quantitative",
            "cells": [{"subject": "Fern", "status": "missing", "values": []}],
        }
    ]
    assert harness.score_result(case, result).abstention_accuracy == 1.0
    result["status"] = "complete"
    assert harness.score_result(case, result).abstention_accuracy == 0.0
    result["status"] = "incomplete"
    result["coverage"][0]["cells"][0]["status"] = "supported"
    assert harness.score_result(case, result).abstention_accuracy == 0.0


def test_fixture_manifest_is_twenty_valid_cases_with_no_answer_keys_in_source_text() -> None:
    harness = evaluation()
    cases = harness.load_cases(fixture_path())
    assert len(cases) == 20
    assert len({c.id for c in cases}) == 20
    assert {"numeric", "comparison", "conflict", "scope_date", "unanswerable"} == {
        c.category for c in cases
    }
    assert all(len(c.sources) >= 3 for c in cases)
    assert all(c.fixture_kind == "controlled_synthetic" for c in cases)
    assert all("expected_facets" not in s.text for c in cases for s in c.sources)


def test_strict_boundary_rejects_unknown_fields_and_duplicate_source_ids(tmp_path: Path) -> None:
    harness = evaluation()
    manifest = json.loads(fixture_path().read_text())
    manifest["cases"][0]["unexpected"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValidationError):
        harness.load_cases(path)
    manifest["cases"][0].pop("unexpected")
    manifest["cases"][0]["sources"][1]["id"] = "s1"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValidationError):
        harness.load_cases(path)


def test_old_results_without_coverage_are_scored_as_missing_not_guessed() -> None:
    harness = evaluation()
    case = harness.load_cases(fixture_path())[0]
    result = artifact()
    result.pop("coverage")
    score = harness.score_result(case, result)
    assert score.answer_accuracy == 0.0
    assert score.coverage_recall == 0.0
    assert score.provenance_rate == 1.0


async def test_live_ndjson_requires_terminal_result_and_validates_events() -> None:
    import httpx

    harness = evaluation()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, text='{"type":"heartbeat","stage":"working","message":"waiting"}\n'
            )
        )
    ) as client:
        with pytest.raises(ValueError, match="terminal"):
            await harness.run_live(
                "What is the measured population?", "https://service.example", client, 1
            )


def test_cli_scores_saved_artifact_and_writes_reviewable_reports(tmp_path: Path) -> None:
    import subprocess
    import sys

    results = tmp_path / "artifacts"
    results.mkdir()
    (results / "numeric-population.json").write_text(json.dumps(artifact()))
    output = tmp_path / "report"
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "evaluate.py"),
            "--mode",
            "score",
            "--cases",
            "numeric-population",
            "--results",
            str(results),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads((output / "summary.json").read_text())
    assert report["scores"][0]["answer_accuracy"] == 1.0
    assert report["scores"][0]["semantic_entailment"] == "not_automatically_verified"
    assert "not a live-web benchmark" in (output / "report.md").read_text()


def test_extra_supported_value_and_duplicate_cells_cannot_earn_exact_answer_credit() -> None:
    harness = evaluation()
    case = harness.load_cases(fixture_path())[0]
    result = artifact()
    cell = result["coverage"][0]["cells"][0]
    cell["values"].append({**cell["values"][0], "value": "99 residents"})
    assert harness.score_result(case, result).answer_accuracy == 0.0
    result = artifact()
    result["coverage"][0]["cells"].append(result["coverage"][0]["cells"][0])
    score = harness.score_result(case, result)
    assert score.answer_accuracy == 0.0
    assert score.coverage_recall == 0.0


async def test_live_ndjson_returns_real_validated_result_and_rejects_error_event() -> None:
    import httpx

    harness = evaluation()
    payload = artifact()
    payload.pop("coverage")
    line = json.dumps(
        {"type": "result", "stage": "complete", "message": "Finished", "result": payload}
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=line + "\n"))
    ) as client:
        result = await harness.run_live(payload["question"], "https://service.example", client, 1)
        assert result.id == "scorer-test"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, text='{"type":"error","stage":"error","message":"failure"}\n'
            )
        )
    ) as client:
        with pytest.raises(ValueError, match="error event"):
            await harness.run_live(payload["question"], "https://service.example", client, 1)


def test_fully_unanswerable_case_cannot_abstain_while_emitting_factual_claims() -> None:
    harness = evaluation()
    case = next(c for c in harness.load_cases(fixture_path()) if c.id == "unanswerable-budget")
    result = artifact()
    result["question"] = case.question
    result["status"] = "incomplete"
    result["sources"] = [source.model_dump() for source in case.sources]
    result["claims"] = [
        {
            "text": "Fern has a budget of USD 20 million.",
            "section": "summary",
            "citations": [{"source_id": "s1", "quote": case.sources[0].text}],
        }
    ]
    result["coverage"] = [
        {
            "dimension": "budget",
            "label": "Budget",
            "kind": "quantitative",
            "cells": [{"subject": "Fern", "status": "missing", "values": []}],
        }
    ]
    assert harness.score_result(case, result).abstention_accuracy == 0.0


async def test_fixture_adapter_uses_real_ranking_with_no_web_fetches() -> None:
    import httpx
    from veriweb.config import Settings

    harness = evaluation()
    case = harness.load_cases(fixture_path())[0]

    def forbid_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Controlled fixture retrieval must not access the web")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbid_network)) as client:
        researcher = harness.FixtureResearcher(case, Settings(), client)
        events = [event async for event in researcher.run(case.question, "excerpts")]
    result = events[-1].result
    assert result is not None
    assert result.status == "excerpts"
    assert len(result.sources) == 3
    assert len(result.passages) == 3
    assert result.claims == []
    assert result.passages[0].source_id == "s1"


@pytest.mark.parametrize("deadline", [0.0, -1.0, float("inf"), float("nan")])
async def test_live_runner_rejects_unbounded_or_invalid_deadline(deadline: float) -> None:
    import httpx

    harness = evaluation()
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="Deadline"):
            await harness.run_live(
                "What is the measured population?", "https://service.example", client, deadline
            )
