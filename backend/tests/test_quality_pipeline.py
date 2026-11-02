from collections.abc import AsyncIterator

import httpx
from veriweb.config import Settings
from veriweb.coverage import requirements_for
from veriweb.pipeline import Researcher
from veriweb.schemas import Citation, Claim, ModelReport, Source, SourceLink


async def test_three_sources_and_valid_quotes_do_not_complete_unanswered_dimensions() -> None:
    class IncompleteResearcher(Researcher):
        async def decompose(self, question: str) -> list[str]:
            return [question]

        async def search(self, queries: list[str]) -> list[tuple[str, str]]:
            return [
                (f"https://source{index}.example/article", "Battery report") for index in range(3)
            ]

        async def collect(self, urls: list[tuple[str, str]]) -> AsyncIterator[Source | str]:
            for index, (url, _) in enumerate(urls):
                yield Source(
                    id=f"s{index + 1}",
                    title="Battery report",
                    url=url,
                    text=f"Sodium-ion batteries have emerging commercial applications in region {index}. They are described as cost-effective alternatives.",
                )

        async def synthesize(self, question: str, evidence: str) -> ModelReport:
            return ModelReport(
                claims=[
                    Claim(
                        text="Sodium-ion batteries are described as cost-effective.",
                        citations=[
                            Citation(
                                source_id="s1",
                                quote="They are described as cost-effective alternatives.",
                            )
                        ],
                    )
                ]
            )

    async with httpx.AsyncClient() as client:
        researcher = IncompleteResearcher(Settings(), client)
        researcher.model_available = True
        events = [
            item
            async for item in researcher.run(
                "Compare sodium-ion batteries versus lithium-ion batteries for grid storage. Compare costs and lifetimes."
            )
        ]
    result = events[-1].result
    assert result is not None
    assert result.claims == []
    assert result.status == "incomplete"
    assert {row.dimension for row in result.coverage} == {"cost", "lifetime"}
    assert all(cell.status == "missing" for row in result.coverage for cell in row.cells)


async def test_collection_follows_only_one_hop_within_total_page_budget(monkeypatch) -> None:
    visited: list[str] = []

    async def fetch(client: httpx.AsyncClient, url: str, identifier: str) -> Source:
        visited.append(url)
        return Source(
            id=identifier,
            title="Battery research",
            url=url,
            text="A battery research article with sufficient text for exact evidence extraction.",
            links=[SourceLink(url=url + "/report", title="Battery cost research report")],
        )

    monkeypatch.setattr("veriweb.pipeline.fetch_source", fetch)
    async with httpx.AsyncClient() as client:
        researcher = Researcher(Settings(max_sources=4, follow_links=1), client)
        researcher.requirements = requirements_for(
            "Compare sodium-ion batteries versus lithium-ion batteries. Compare costs."
        )
        urls = [(f"https://source{index}.example/article", "Battery news") for index in range(4)]
        results = [item async for item in researcher.collect(urls)]
    assert len(visited) == 4
    assert visited[-1].endswith("/report")
    assert not any(url.endswith("/report/report") for url in visited)
    assert {item.id for item in results if isinstance(item, Source)} == {"s1", "s2", "s3", "s4"}
