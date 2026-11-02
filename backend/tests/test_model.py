import json

import httpx
from veriweb.config import Settings
from veriweb.model import ModelClient
from veriweb.pipeline import Researcher
from veriweb.schemas import ModelReport


async def test_structured_generation_sends_the_schema_to_the_inference_runtime() -> None:
    captured: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"claims":[],"conflicts":[],"gaps":[]}'}}],
                "usage": {"completion_tokens": 15},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        model = ModelClient(Settings(model_url="http://model.test/v1"), client)
        await model.complete(
            "Produce an evidence report",
            "Retrieved evidence",
            schema=ModelReport.model_json_schema(),
        )
    assert captured[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "research_output",
            "strict": True,
            "schema": ModelReport.model_json_schema(),
        },
    }
    assert model.last_tps is not None


async def test_numeric_pass_enriches_an_already_detected_conflict_without_duplicates() -> None:
    quotes = [
        "The 2026 semiconductor program budget totals $10 billion.",
        "The 2026 semiconductor program budget totals $8.2 billion.",
    ]
    evidence = [
        {
            "id": f"s{i}-p{i}",
            "source_id": f"s{i}",
            "quote": quote,
            "start": 0,
            "end": len(quote),
            "score": 1,
            "source_title": f"Source {i}",
            "source_url": f"https://source{i}.example/article",
            "published_at": None,
        }
        for i, quote in enumerate(quotes, 1)
    ]

    def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        properties = payload["response_format"]["json_schema"]["schema"]["properties"]
        content = (
            {
                "comparisons": [
                    {
                        "candidate_id": "c1",
                        "title": "Different budgets",
                        "explanation": "The same program has competing reported budgets.",
                        "relation": "conflict",
                    }
                ]
            }
            if "comparisons" in properties
            else {
                "claims": [
                    {
                        "text": "The first source reports ten billion dollars.",
                        "evidence_ids": ["s1-p1"],
                    }
                ],
                "conflicts": [
                    {
                        "title": "Different budgets",
                        "explanation": "The figures differ.",
                        "kind": "numeric",
                        "left_id": "s1-p1",
                        "right_id": "s2-p2",
                    }
                ],
            }
        )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(content)}}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        researcher = Researcher(Settings(model_url="http://model.test/v1"), client)
        report = await researcher.synthesize("Compare the program budgets", json.dumps(evidence))
    assert len(report.conflicts) == 1
    assert report.conflicts[0].left_quantity == "$10B"
    assert report.conflicts[0].right_quantity == "$8.2B"
