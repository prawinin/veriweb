import httpx
from ddgs.exceptions import DDGSException
from veriweb.config import Settings
from veriweb.pipeline import Researcher


async def test_one_failed_subquery_does_not_discard_other_search_results() -> None:
    class PartialSearch(Researcher):
        def keyless_search(self, query: str) -> list[dict[str, str]]:
            if query == "bad":
                raise DDGSException("provider temporarily unavailable")
            return [{"href": f"https://{query}.example/article", "title": "A real result"}]

    async with httpx.AsyncClient() as client:
        researcher = PartialSearch(Settings(), client)
        results = await researcher.search(["good", "bad", "other"])
        assert {url for url, _ in results} == {
            "https://good.example/article",
            "https://other.example/article",
        }
        assert researcher.search_failures == 1
