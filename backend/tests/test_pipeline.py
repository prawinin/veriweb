import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest
from veriweb.app import create_app
from veriweb.config import Settings
from veriweb.pipeline import Researcher
from veriweb.schemas import ModelReport, Source


async def test_disconnect_releases_busy_slot_while_waiting_for_model() -> None:
    app = create_app(Settings())
    waiting = asyncio.Event()
    disconnected = asyncio.Event()
    closed = asyncio.Event()
    delivered = False
    payload = json.dumps({"question": "Compare semiconductor funding policies"}).encode()

    async def stream(question: str, mode: str) -> AsyncIterator[str]:
        try:
            yield '{"type":"log","stage":"plan","message":"Working"}\n'
            waiting.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": payload, "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        return None

    app.state.stream_factory = stream
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/research",
        "raw_path": b"/api/research",
        "root_path": "",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("test", 0),
        "server": ("test", 0),
    }
    task = asyncio.create_task(app(scope, receive, send))
    await asyncio.wait_for(waiting.wait(), timeout=2)
    disconnected.set()
    await asyncio.wait_for(task, timeout=2)
    assert closed.is_set()
    assert app.state.busy is False


class FixtureResearcher(Researcher):
    def __init__(self, count: int = 3, model: bool = True) -> None:
        super().__init__(Settings(), httpx.AsyncClient())
        self.count = count
        self.model_available = model

    async def decompose(self, question: str) -> list[str]:
        return [question, question + " primary sources", question + " latest evidence"]

    async def search(self, queries: list[str]) -> list[tuple[str, str]]:
        return [(f"https://source{i}.example/article", f"Source {i}") for i in range(self.count)]

    async def collect(self, urls: list[tuple[str, str]]) -> AsyncIterator[Source | str]:
        for i, (url, title) in enumerate(urls):
            yield Source(
                id=f"s{i + 1}",
                title=title,
                url=url,
                text=f"The semiconductor program received {10 + i} billion dollars for chip manufacturing facilities. "
                * 4,
            )

    async def synthesize(self, question: str, evidence: str) -> ModelReport:
        return ModelReport.model_validate(
            {
                "claims": [
                    {
                        "text": "The first program received ten billion dollars.",
                        "section": "summary",
                        "citations": [
                            {
                                "source_id": "s1",
                                "quote": "The semiconductor program received 10 billion dollars",
                            }
                        ],
                    },
                    {
                        "text": "Invented evidence",
                        "citations": [
                            {"source_id": "s1", "quote": "The budget is a trillion dollars"}
                        ],
                    },
                ],
                "cells": [
                    {
                        "dimension": "funding",
                        "subject": "Requested answer",
                        "value": "10 billion dollars",
                        "citation": {
                            "source_id": "s1",
                            "quote": "The semiconductor program received 10 billion dollars",
                        },
                    }
                ],
                "conflicts": [
                    {
                        "title": "Different budgets",
                        "explanation": "The figures need scope review.",
                        "kind": "numeric",
                        "left": {
                            "source_id": "s1",
                            "quote": "The semiconductor program received 10 billion dollars",
                        },
                        "right": {
                            "source_id": "s2",
                            "quote": "The semiconductor program received 11 billion dollars",
                        },
                    }
                ],
            }
        )


async def test_identical_syndicated_articles_do_not_establish_independent_evidence() -> None:
    class Syndicated(FixtureResearcher):
        async def collect(self, urls: list[tuple[str, str]]) -> AsyncIterator[Source | str]:
            for i, (url, title) in enumerate(urls):
                yield Source(
                    id=f"s{i + 1}",
                    title=title,
                    url=url,
                    text="The semiconductor program received 10 billion dollars for manufacturing capacity.",
                )

        async def synthesize(self, question: str, evidence: str) -> ModelReport:
            return ModelReport.model_validate(
                {
                    "claims": [
                        {
                            "text": "Funding is ten billion dollars.",
                            "citations": [
                                {
                                    "source_id": "s1",
                                    "quote": "The semiconductor program received 10 billion dollars",
                                }
                            ],
                        }
                    ]
                }
            )

    researcher = Syndicated()
    try:
        events = [event async for event in researcher.run("Compare semiconductor funding policies")]
    finally:
        await researcher.client.aclose()
    result = events[-1].result
    assert result is not None
    assert result.status == "incomplete"
    assert result.claims == []
    assert any("independent" in gap.lower() for gap in result.gaps)


async def test_pipeline_validates_claims_and_streams_real_stages() -> None:
    researcher = FixtureResearcher()
    try:
        events = [event async for event in researcher.run("Compare semiconductor funding policies")]
    finally:
        await researcher.client.aclose()
    result = events[-1].result
    assert result is not None
    assert len(result.claims) == 1
    assert len(result.conflicts) == 1
    assert result.status == "incomplete"
    assert any("unsupported" in gap.lower() for gap in result.gaps)
    assert {"search", "extract", "rank", "verify"} <= {e.stage for e in events}


@pytest.mark.parametrize("count,model", [(2, True), (3, False)])
async def test_sparse_or_model_free_research_cannot_claim_completion(
    count: int, model: bool
) -> None:
    researcher = FixtureResearcher(count=count, model=model)
    try:
        events = [event async for event in researcher.run("Compare semiconductor funding policies")]
    finally:
        await researcher.client.aclose()
    result = events[-1].result
    assert result is not None
    assert result.status != "complete"
    assert result.claims == []
    assert result.gaps
    assert result.passages


async def test_api_rejects_invalid_payload_and_parallel_runs() -> None:
    app = create_app(Settings())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post("/api/research", json={"question": "short"})).status_code == 422
        app.state.busy = True
        response = await client.post(
            "/api/research", json={"question": "Compare semiconductor funding policies"}
        )
        assert response.status_code == 409


async def test_api_releases_run_slot_after_failure() -> None:
    app = create_app(Settings())

    async def broken(question: str, mode: str = "research") -> AsyncIterator[str]:
        raise RuntimeError("private internal details")
        yield question

    app.state.stream_factory = broken
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/research", json={"question": "Compare semiconductor funding policies"}
        )
        assert '"type":"error"' in response.text
        assert "private internal details" not in response.text
        assert app.state.busy is False
