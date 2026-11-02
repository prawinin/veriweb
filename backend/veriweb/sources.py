import re
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from veriweb.domains import publisher_domain
from veriweb.schemas import SourceLink

RESEARCH_HOSTS = {
    "arxiv.org",
    "nature.com",
    "science.org",
    "sciencedirect.com",
    "springer.com",
    "wiley.com",
    "ieee.org",
    "pnas.org",
    "pubmed.ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "osti.gov",
}
DOCUMENT_WORDS = re.compile(
    r"\b(?:research|study|paper|report|publication|datasheet|data sheet|specifications?|technical|results|cost|lifetime|cycles|deployment)\b",
    re.I,
)
CONTROL_PATH = re.compile(
    r"(?:login|log-in|logout|sign-in|signout|privacy|cookie|cart|checkout|terms|subscribe)", re.I
)


def source_type(
    url: str, title: str
) -> Literal["public_institution", "research", "technical", "other"]:
    host = (urlsplit(url).hostname or "").lower()
    domain = publisher_domain(url)
    if re.search(r"(?:^|\.)(?:gov|mil)(?:\.[a-z]{2})?$", host) or re.search(
        r"\.(?:edu|ac)(?:\.[a-z]{2})?$", host
    ):
        return "public_institution"
    if host in RESEARCH_HOSTS or domain in RESEARCH_HOSTS:
        return "research"
    if re.search(r"\b(?:datasheet|specifications?|technical data|product manual)\b", title, re.I):
        return "technical"
    return "other"


def relevance(url: str, title: str, question: str) -> float:
    query = set(re.findall(r"[a-z0-9]+", question.lower())) - {
        "the",
        "and",
        "for",
        "with",
        "what",
        "does",
        "compare",
        "versus",
        "current",
        "evidence",
        "how",
    }
    tokens = set(re.findall(r"[a-z0-9]+", (title + " " + urlsplit(url).path).lower()))
    overlap = len(query & tokens)
    kind = source_type(url, title)
    bonus = (
        {"public_institution": 3.5, "research": 3.0, "technical": 2.0, "other": 0.0}[kind]
        if overlap
        else 0.0
    )
    return overlap * 2 + bonus + (0.5 if DOCUMENT_WORDS.search(title) and overlap else 0)


def prioritize_urls(
    candidates: list[tuple[str, str]], question: str, limit: int
) -> list[tuple[str, str]]:
    selected: list[tuple[str, str]] = []
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for url, title in sorted(
        candidates, key=lambda row: relevance(row[0], row[1], question), reverse=True
    ):
        host = publisher_domain(url)
        if counts.get(host, 0) >= 2 or url in seen:
            continue
        selected.append((url, title))
        seen.add(url)
        counts[host] = counts.get(host, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def article_links(soup: BeautifulSoup, base_url: str) -> list[SourceLink]:
    links: dict[str, SourceLink] = {}
    for anchor in soup.find_all("a", href=True, limit=800):
        title = anchor.get_text(" ", strip=True)
        if not 5 <= len(title) <= 200 or not DOCUMENT_WORDS.search(title):
            continue
        url = urljoin(base_url, str(anchor.get("href", "")))
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            continue
        if publisher_domain(url) != publisher_domain(base_url) or CONTROL_PATH.search(parsed.path):
            continue
        if parsed.path.lower().endswith((".pdf", ".zip", ".png", ".jpg", ".csv", ".xlsx")):
            continue
        clean = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
        if len(clean) > 2000 or clean == base_url:
            continue
        links.setdefault(clean, SourceLink(url=clean, title=title))
        if len(links) == 16:
            break
    return list(links.values())


def table_text(soup: BeautifulSoup) -> str:
    blocks: list[str] = []
    for table in soup.find_all("table", limit=6):
        lines: list[str] = []
        caption = table.find("caption")
        if caption:
            lines.append(caption.get_text(" ", strip=True)[:300])
        for row in table.find_all("tr", limit=20):
            cells = [
                cell.get_text(" ", strip=True).replace("|", "¦")[:240]
                for cell in row.find_all(["th", "td"], recursive=False, limit=10)
            ]
            if len(cells) >= 2 and any(cells):
                lines.append("| " + " | ".join(cells) + " |")
        if len(lines) >= 2:
            blocks.append("\n".join(lines)[:6000])
    return "\n\n".join(blocks)
