import socket

import numpy as np
import pytest
from numpy.typing import NDArray
from pydantic import ValidationError
from veriweb.fetching import UnsafeURL, validate_public_url
from veriweb.retrieval import rank_passages
from veriweb.schemas import Citation, Claim, Passage, Source, validate_claims


def source(identifier: str, text: str) -> Source:
    return Source(
        id=identifier, title=identifier, url=f"https://{identifier}.example/article", text=text
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1/x",
        "http://[::1]/",
        "http://169.254.169.254/",
        "http://user:secret@example.com",
        "http://10.0.0.1/",
        "http://localhost/",
    ],
)
async def test_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(UnsafeURL):
        await validate_public_url(url)


async def test_rejects_private_dns_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.3", 443))],
    )
    with pytest.raises(UnsafeURL):
        await validate_public_url("https://public-looking.example/")


def test_ranking_selects_relevant_paragraphs_and_removes_duplicates() -> None:
    relevant = "Semiconductor subsidy funding supports new domestic chip manufacturing facilities and research."
    sources = [
        source("s1", "Garden flowers need water and sunlight every day.\n\n" + relevant),
        source("s2", relevant),
    ]
    ranked = rank_passages("semiconductor subsidy chip manufacturing", sources, limit=10)
    assert ranked[0].quote == relevant
    assert len([p for p in ranked if p.quote == relevant]) == 1
    assert all(p.quote in sources[int(p.source_id[1:]) - 1].text for p in ranked)


def test_rejects_fabricated_quotes_and_unknown_sources() -> None:
    sources = [source("s1", "The program received a budget of ten billion dollars.")]
    claims = [
        Claim(
            text="Funding is ten billion.",
            citations=[Citation(source_id="s1", quote="a budget of ten billion dollars")],
        ),
        Claim(
            text="Fabrication", citations=[Citation(source_id="s1", quote="twenty billion dollars")]
        ),
        Claim(
            text="Unknown",
            citations=[Citation(source_id="s8", quote="a budget of ten billion dollars")],
        ),
    ]
    valid, rejected = validate_claims(claims, sources)
    assert [c.text for c in valid] == ["Funding is ten billion."]
    assert rejected == 2


def test_numeric_claim_preserves_entity_association() -> None:
    from veriweb.schemas import Citation, Claim, Source, validate_claims

    quote = "Cobalt capacity is 8 TB. Quartz capacity is 16 TB."
    sources = [
        Source(id="s1", title="Device specification", url="https://lab.example/spec", text=quote)
    ]
    wrong = Claim(
        text="Cobalt capacity is 16 TB; Quartz capacity is 8 TB.",
        citations=[Citation(source_id="s1", quote=quote)],
    )
    correct = Claim(
        text="Cobalt capacity is 8 TB; Quartz capacity is 16 TB.",
        citations=[Citation(source_id="s1", quote=quote)],
    )
    retained, _ = validate_claims([wrong, correct], sources, subjects=["Cobalt", "Quartz"])
    assert retained == [correct]


def test_numeric_claim_cannot_change_a_reported_unit() -> None:
    from veriweb.schemas import Citation, Claim, Source, validate_claims

    quote = "Cobalt capacity is 8 TB under the standard configuration."
    source = Source(id="s1", title="Specification", url="https://lab.example/spec", text=quote)
    claim = Claim(
        text="Cobalt capacity is 8 GB.", citations=[Citation(source_id="s1", quote=quote)]
    )
    assert validate_claims([claim], [source], subjects=["Cobalt"])[0] == []


def test_claim_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        Claim(text="An unsupported assertion", citations=[])


def test_vector_work_is_bounded_by_lexical_candidate_budget() -> None:
    articles = [
        source(
            f"s{i}",
            "\n\n".join(
                f"Semiconductor subsidy program {i} regional manufacturing investment paragraph {j} records infrastructure spending."
                for j in range(60)
            ),
        )
        for i in range(1, 5)
    ]
    batch_sizes: list[int] = []

    def encode(texts: list[str]) -> NDArray[np.float32]:
        batch_sizes.append(len(texts))
        return np.ones((len(texts), 4), dtype=np.float32)

    ranked = rank_passages("semiconductor subsidy manufacturing", articles, encoder=encode)
    assert len(ranked) == 10
    assert max(batch_sizes) <= 97


def test_citation_cannot_span_artificially_joined_nonadjacent_passages() -> None:
    first = "The first retained paragraph describes semiconductor investment."
    last = "The final retained paragraph describes manufacturing capacity."
    text = first + "\n\nAn omitted paragraph changes the context entirely.\n\n" + last
    article = source("s1", text)
    passages = [
        Passage(id="s1-p1", source_id="s1", quote=first, start=0, end=len(first), score=1),
        Passage(
            id="s1-p3", source_id="s1", quote=last, start=text.index(last), end=len(text), score=1
        ),
    ]
    fabricated = first[-25:] + "\n\n" + last[:25]
    valid, rejected = validate_claims(
        [
            Claim(
                text="A fabricated joined citation",
                citations=[Citation(source_id="s1", quote=fabricated)],
            )
        ],
        [article],
        passages=passages,
    )
    assert valid == []
    assert rejected == 1


def test_cited_claim_cannot_change_a_number_or_its_scale() -> None:
    from veriweb.schemas import Citation, Claim, Source, validate_claims

    quote = "The Cobalt facility received USD 10 million in capital funding in 2025."
    sources = [
        Source(id="s1", title="Funding disclosure", url="https://lab.example/funding", text=quote)
    ]
    claims = [
        Claim(text=text, citations=[Citation(source_id="s1", quote=quote)])
        for text in (
            "Cobalt received USD 11 million.",
            "Cobalt received USD 10 billion.",
            "Cobalt received USD 10 million in 2025.",
        )
    ]
    retained, rejected = validate_claims(claims, sources)
    assert [claim.text for claim in retained] == ["Cobalt received USD 10 million in 2025."]
    assert rejected == 2
def test_short_factual_paragraphs_are_retained() -> None:
    from veriweb.retrieval import split_passages
    from veriweb.schemas import Source
    source = Source(id="s1", title="Specification", url="https://lab.example/spec", text="The price is USD 19.")
    assert [p.quote for p in split_passages([source])] == ["The price is USD 19."]
