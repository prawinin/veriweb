import re
from collections.abc import Sequence
from typing import Literal

from veriweb.schemas import (
    Citation,
    CoverageCell,
    CoverageRow,
    CoverageValue,
    EvidenceCell,
    Passage,
    QuestionRequirements,
    RequestedDimension,
    Source,
    valid_citation,
)

DIMENSIONS: tuple[
    tuple[str, str, Literal["quantitative", "availability", "date", "qualitative"], str], ...
] = (
    ("cost", "Cost", "quantitative", r"\b(?:costs?|prices?|pricing)\b"),
    (
        "funding",
        "Funding",
        "quantitative",
        r"\b(?:funding|budgets?|subsid(?:y|ies)|appropriat\w+)\b",
    ),
    (
        "lifetime",
        "Lifetime",
        "quantitative",
        r"\b(?:lifetimes?|lifespans?|cycle life|cycle counts?|durability)\b",
    ),
    (
        "availability",
        "Commercial availability",
        "availability",
        r"\b(?:availability|available|commercial(?:ly|ization)?|deployments?|ordering|on sale)\b",
    ),
    (
        "date",
        "Date",
        "date",
        r"\b(?:release dates?|launch dates?|(?:what|which) (?:exact )?date|when|enacted|publication date)\b",
    ),
    (
        "orbital_period",
        "Orbital period",
        "quantitative",
        r"\b(?:orbital periods?|orbit periods?)\b",
    ),
    ("population", "Population", "quantitative", r"\bpopulation\b"),
    ("count", "Count", "quantitative", r"\b(?:how many|number of)\b"),
    ("capacity", "Capacity", "quantitative", r"\b(?:capacity|capacities)\b"),
)
NUMBER = r"\d[\d,.]*(?:\s*[–-]\s*\d[\d,.]*)?"
MONEY = re.compile(
    rf"(?:[$€£₹]\s*{NUMBER}|\b(?:USD|EUR|GBP|INR)\s*{NUMBER}|{NUMBER}\s*(?:billion|million|trillion|dollars?|euros?|rupees?|USD|EUR|GBP|INR)\b)",
    re.I,
)
LIFETIME = re.compile(
    rf"{NUMBER}\s*(?:charge[- ]discharge\s+)?(?:cycles?|years?|months?|hours?|(?:Earth\s+)?days?)\b",
    re.I,
)
DATE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,?\s+\d{4})?|(?:19|20)\d{2})\b",
    re.I,
)
AVAILABILITY = re.compile(
    r"\b(?:commercial(?:ly)?|invitation only|early access|available|unavailable|sold|selling|sale|shipp\w*|launched|announc\w*|pilot|prototype|production|deployed|commissioned|operational|demonstration|market|not\s+(?:yet\s+)?available)\b",
    re.I,
)
NEGATION = re.compile(
    r"\b(?:not reported|not disclosed|not specified|no (?:data|figure|price)|unknown|unavailable)\b",
    re.I,
)


def normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def subject_alias(value: str) -> str:
    words = normalized(value).split()
    if words and words[-1] in {"batteries", "battery", "technology", "technologies"}:
        words.pop()
    return " ".join(words)


def subject_identity(value: str) -> str:
    return re.sub(
        r"\s+(?:city|municipal|metropolitan|regional|national)$", "", subject_alias(value)
    )


def requirements_for(
    question: str, proposed: QuestionRequirements | None = None
) -> QuestionRequirements:
    dimensions = [
        RequestedDimension(key=key, label=label, kind=kind)
        for key, label, kind, pattern in DIMENSIONS
        if re.search(pattern, question, re.I)
    ]
    subjects: list[str] = []
    if proposed:
        for subject in proposed.subjects:
            if normalized(subject) in normalized(question) and subject not in subjects:
                subjects.append(subject[:200])
        existing = {item.key for item in dimensions}
        requested_tail = [
            part.strip()
            for part in re.split(
                r"[?;.]|\b(?:compare|report|include|provide|show|cover)\b", question, flags=re.I
            )
            if part.strip()
        ][-1]
        for dimension in proposed.dimensions:
            if normalized(dimension.label) not in normalized(requested_tail):
                continue
            canonical = next(
                (
                    key
                    for key, _, _, pattern in DIMENSIONS
                    if re.search(pattern, dimension.label, re.I)
                ),
                None,
            )
            if (
                canonical in existing
                or dimension.key
                in {
                    "subject",
                    "entity",
                    "system",
                    "time",
                    "currency",
                    "unit",
                    "plan",
                    "program",
                    "archive",
                    "dataset",
                }
                or re.fullmatch(r"[\d\s,.-]+", dimension.label)
            ):
                continue
            if any(normalized(dimension.label) in normalized(subject) for subject in subjects):
                continue
            if len(dimensions) >= 6:
                break
            if dimension.key not in existing and normalized(dimension.label) in normalized(
                question
            ):
                dimensions.append(dimension)
                existing.add(dimension.key)
    match = re.search(r"(.+?)\s+(?:versus|vs\.?|compared (?:with|to))\s+(.+)", question, re.I)
    if match:
        left = re.split(
            r"\b(?:about|between|compare|comparing|contrast|of|in)\b", match[1], flags=re.I
        )[-1]
        right = re.split(
            r"\b(?:for|in|on|with respect to)\b|[?.;]", match[2], maxsplit=1, flags=re.I
        )[0]
        for _, _, _, pattern in DIMENSIONS:
            right = re.sub("(?:" + pattern + r")\s*$", "", right, flags=re.I)
        subjects = [left.strip(" ,:"), right.strip(" ,:")]
        subjects = [subject[:200] for subject in subjects if subject.strip()]
    scoped = re.search(
        r"\bcompare\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(city|municipal|metropolitan|regional|national)\s+and\s+(city|municipal|metropolitan|regional|national)\s+population\b",
        question,
        re.I,
    )
    if scoped:
        subjects = [f"{scoped[1]} {scoped[2]}", f"{scoped[1]} {scoped[3]}"]
    if not subjects:
        excluded = {
            "what",
            "when",
            "how",
            "compare",
            "report",
            "is",
            "are",
            "which",
            "did",
            "does",
            "give",
            "state",
            "the",
            "please",
            "in",
            "on",
            "explain",
            "according",
        }
        subjects = [
            match.group()
            for match in re.finditer(
                r"\b[A-Z][a-z][a-z0-9-]*(?:\s+[A-Z][a-z][a-z0-9-]*)*\b", question
            )
            if match.group().lower() not in excluded
        ]
        subjects = [
            " ".join(
                word
                for index, word in enumerate(subject.split())
                if index or word.lower() not in excluded
            )
            for subject in subjects
        ]
        subjects = list(dict.fromkeys(subject for subject in subjects if subject))[:4]
    if not subjects:
        subjects = ["Requested answer"]
    if not dimensions:
        dimensions = [
            RequestedDimension(key="answer", label="Requested answer", kind="qualitative")
        ]
    subjects = [
        re.sub(r"\s+(?:funding|budget|population|capacity|cost)$", "", subject, flags=re.I)
        for subject in subjects
        if normalized(subject)
        not in {"on", "explain", "according", "identify", "distinguish", "describe", "flag", "list"}
    ]
    for dimension in list(dimensions):
        if dimension.key == "funding":
            years = list(dict.fromkeys(re.findall(r"\b(?:19|20)\d{2}\b", question)))
            if len(years) > 1:
                dimensions = [d for d in dimensions if d.key != "funding"] + [
                    RequestedDimension(
                        key=f"funding_{year}", label=f"{year} funding", kind="quantitative"
                    )
                    for year in years
                ]
            elif re.search(r"\bbudget\b", question, re.I) and not re.search(
                r"\bfunding\b", question, re.I
            ):
                dimension.label = "Budget"
        if dimension.key == "cost":
            scopes = re.findall(
                r"\b(equipment-only|installed|operating|capital)\s+cost\b", question, re.I
            )
            if len(set(scopes)) > 1:
                dimensions = [d for d in dimensions if d.key != "cost"] + [
                    RequestedDimension(
                        key=f"cost_{scope.lower().replace('-', '_')}",
                        label=f"{scope.lower()} cost",
                        kind="quantitative",
                    )
                    for scope in dict.fromkeys(scopes)
                ]
    if (
        not match
        and len(subjects) > 1
        and re.search(r"\b(?:in|per)\s+Earth\s+(?:days|years|hours)\b", question, re.I)
    ):
        subjects = [subject for subject in subjects if normalized(subject) != "earth"]
    requested_years = list(dict.fromkeys(re.findall(r"\b(?:19|20)\d{2}\b", question)))
    requested_qualifiers = list(
        dict.fromkeys(
            re.findall(r"\b(equipment-only|installed|operating|capital)\s+cost\b", question, re.I)
        )
    )
    if len(set(requested_qualifiers)) > 1:
        subjects = list(
            dict.fromkeys(
                re.sub(
                    r"\s+(?:equipment-only|installed|operating|capital)$", "", subject, flags=re.I
                )
                for subject in subjects
            )
        )
    for dimension in dimensions:
        if dimension.key.startswith("funding_"):
            dimension.year = dimension.key.rsplit("_", 1)[-1]
        elif len(requested_years) == 1:
            dimension.year = requested_years[0]
        if dimension.key.startswith("cost_"):
            dimension.qualifier = dimension.label.removesuffix(" cost")
        elif dimension.key == "cost" and len(requested_qualifiers) == 1:
            dimension.qualifier = requested_qualifiers[0].lower()
    return QuestionRequirements(
        subjects=subjects[:4] or ["Requested answer"], dimensions=dimensions[:6]
    )


def valid_measurement(value: str, dimension: RequestedDimension) -> bool:
    if NEGATION.search(value) and dimension.kind != "availability":
        return False
    if dimension.key.startswith(("cost", "funding")):
        return MONEY.search(value) is not None
    if dimension.key in {"lifetime", "orbital_period"}:
        return LIFETIME.search(value) is not None
    if dimension.kind == "date":
        return DATE.search(value) is not None
    if dimension.kind == "availability":
        return AVAILABILITY.search(value) is not None
    if dimension.key == "capacity":
        return (
            re.search(
                rf"{NUMBER}\s*(?:[kmgtpe]?i?b|[kmgt]?wh|mah|ah|liters?|litres?|m3)\b", value, re.I
            )
            is not None
        )
    if dimension.key == "population":
        return (
            re.search(rf"{NUMBER}\s*(?:residents?|people|persons?|inhabitants?)\b", value, re.I)
            is not None
        )
    if dimension.kind == "quantitative":
        return (
            re.search(
                rf"{NUMBER}\s*(?:%|percent|countries|nations|units?|users?|items?|[kmgt]?wh|[kmgt]?w|[kmgtpe]?i?b|cycles?|years?|months?|hours?|seconds?|ms|fps|kg|km|meters?|liters?|degrees?|°[cf])\b",
                value,
                re.I,
            )
            is not None
        )
    return len(value.strip()) >= 3


def scope_matches(value: str, quote: str, dimension: RequestedDimension) -> bool:
    if not dimension.year and not dimension.qualifier:
        return True
    table_lines = [line for line in quote.splitlines() if "|" in line]
    if len(table_lines) > 1:
        headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
        for line in table_lines[1:]:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            for index, cell in enumerate(cells):
                if value not in cell:
                    continue
                context = (headers[index] if index < len(headers) else "") + " " + cells[0]
                if (not dimension.year or dimension.year in context) and (
                    not dimension.qualifier
                    or normalized(dimension.qualifier) in normalized(context)
                ):
                    return True
        return False
    all_years = set(re.findall(r"\b(?:19|20)\d{2}\b", quote))
    all_qualifiers = set(
        re.findall(r"\b(?:equipment-only|installed|operating|capital)\b", quote.lower())
    )
    for clause in re.split(r"(?<=[.;])\s+|\n|;\s*|\s+and\s+", quote):
        if not re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", clause):
            continue
        years = set(re.findall(r"\b(?:19|20)\d{2}\b", clause)) or all_years
        qualifiers = (
            set(re.findall(r"\b(?:equipment-only|installed|operating|capital)\b", clause.lower()))
            or all_qualifiers
        )
        if dimension.year and years != {dimension.year}:
            continue
        if dimension.qualifier and qualifiers != {dimension.qualifier}:
            continue
        return True
    return False


def valid_value_context(value: str, quote: str, dimension: RequestedDimension) -> bool:
    if not scope_matches(value, quote, dimension):
        return False
    for occurrence in re.finditer(r"(?<!\w)" + re.escape(value) + r"(?!\w)", quote):
        prefix = re.split(
            r"[.!?;,\n]", quote[max(0, occurrence.start() - 90) : occurrence.start()]
        )[-1]
        omitted_negative = re.search(r"\b(?:not|never|no longer)\s+(?:\w+\s+){0,3}$", prefix, re.I)
        if dimension.key == "orbital_period":
            lead = re.split(
                r"(?<=[.!?;])\s+|\s+[—–]\s+|\s+(?:and|but|while|whereas|yet)\s+",
                quote[max(0, occurrence.start() - 220) : occurrence.start()],
                flags=re.I,
            )[-1]
            anchors = list(
                re.finditer(
                    r"\borbits?\b|\borbital\b|\baround (?:the )?sun\b|\byear(?: on [a-z][a-z-]*)? (?:lasts|takes|is)\b",
                    lead,
                    re.I,
                )
            )
            if not anchors:
                continue
            relation = lead[anchors[-1].start() :]
            if re.search(
                r"solar day|rotat|spins|local noon|daylight|darkness|synodic|opposition|conjunction|seasons?",
                relation,
                re.I,
            ):
                continue
        if omitted_negative:
            continue
        if dimension.kind == "quantitative" and re.search(r"\b(?:not|never)\b", value, re.I):
            continue
        return True
    return False


def belongs_to_subject(value: str, quote: str, subject: str, subjects: Sequence[str]) -> bool:
    if subject == "Requested answer":
        return True
    alias = subject_alias(subject)
    if not alias or alias not in normalized(quote):
        return False
    if len(subjects) == 1:
        return True
    lines = [line for line in quote.splitlines() if "|" in line]
    if len(lines) >= 2:
        headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
        columns = [index for index, header in enumerate(headers) if alias in normalized(header)]
        if columns:
            for line in lines[1:]:
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if any(index < len(cells) and value in cells[index] for index in columns):
                    return True
            return False
    words = list(re.finditer(r"[a-z0-9]+", quote.lower()))
    tokens = [word.group() for word in words]
    mentions: list[tuple[int, str]] = []
    for candidate in subjects:
        parts = subject_alias(candidate).split()
        for index in range(len(tokens) - len(parts) + 1):
            if parts and tokens[index : index + len(parts)] == parts:
                mentions.append((words[index].start(), candidate))
    for occurrence in re.finditer(re.escape(value), quote):
        preceding = [item for item in mentions if item[0] <= occurrence.start()]
        if preceding and max(preceding, key=lambda item: item[0])[1] == subject:
            return True
        if not preceding and mentions and min(mentions, key=lambda item: item[0])[1] == subject:
            return True
    return False


def extract_values(
    requirements: QuestionRequirements, passages: list[Passage]
) -> list[EvidenceCell]:
    extracted: list[EvidenceCell] = []
    for dimension in requirements.dimensions:
        if dimension.key.startswith(("cost", "funding")):
            pattern = re.compile(
                MONEY.pattern
                + r"(?:\s+(?:million|billion|trillion)\b)?(?:\s*(?:per\s+[\w-]+|/[\w-]+))?",
                re.I,
            )
        elif dimension.key in {"lifetime", "orbital_period"}:
            pattern = LIFETIME
        elif dimension.key == "population":
            pattern = re.compile(rf"{NUMBER}\s*(?:residents?|people|persons?|inhabitants?)\b", re.I)
        elif dimension.key == "capacity":
            pattern = re.compile(
                rf"{NUMBER}\s*(?:[kmgtpe]?i?b|[kmgt]?wh|mah|ah|liters?|litres?|m3)\b", re.I
            )
        elif dimension.kind == "date":
            pattern = DATE
        elif dimension.kind == "availability":
            pattern = re.compile(
                r"\b(?:not\s+(?:yet\s+)?(?:commercially\s+)?available|commercially unavailable|publicly available|commercially available|invitation only|early commercial|early access|prototype|pilot production)\b",
                re.I,
            )
        else:
            continue
        for passage in passages:
            if dimension.key.startswith("funding") and not re.search(
                r"\b(?:funding|budget|received|awarded|grant|appropriat\w*)\b", passage.quote, re.I
            ):
                continue
            if dimension.key.startswith("cost") and not re.search(
                r"\b(?:cost|price|pricing|subscription)\b", passage.quote, re.I
            ):
                continue
            if dimension.kind == "date" and not re.search(
                r"\b(?:released?|launched?|published|enacted|effective|commissioned)\b",
                passage.quote,
                re.I,
            ):
                continue
            if (
                dimension.key.startswith("funding_")
                and dimension.key.rsplit("_", 1)[-1] not in passage.quote
            ):
                continue
            if dimension.key.startswith("cost_") and normalized(dimension.label) not in normalized(
                passage.quote
            ):
                continue
            for match in pattern.finditer(passage.quote):
                value = match.group().rstrip(".,; ")
                for subject in requirements.subjects:
                    if subject != "Requested answer" and subject_alias(subject) not in normalized(
                        passage.quote
                    ):
                        continue
                    if valid_value_context(value, passage.quote, dimension) and belongs_to_subject(
                        value, passage.quote, subject, requirements.subjects
                    ):
                        extracted.append(
                            EvidenceCell(
                                dimension=dimension.key,
                                subject=subject,
                                value=value,
                                citation=Citation(source_id=passage.source_id, quote=passage.quote),
                            )
                        )
    return extracted


def build_coverage(
    requirements: QuestionRequirements,
    evidence_cells: Sequence[EvidenceCell],
    sources: list[Source],
    passages: list[Passage],
) -> tuple[list[CoverageRow], list[str]]:
    by_source = {source.id: source for source in sources}
    rows: list[CoverageRow] = []
    gaps: list[str] = []
    for dimension in requirements.dimensions:
        cells: list[CoverageCell] = []
        for subject in requirements.subjects:
            values: list[CoverageValue] = []
            for entry in evidence_cells:
                if normalized(entry.dimension) not in {
                    normalized(dimension.key),
                    normalized(dimension.label),
                } or normalized(entry.subject) != normalized(subject):
                    continue
                if not valid_citation(entry.citation, sources, passages):
                    continue
                if not valid_value_context(
                    entry.value, entry.citation.quote, dimension
                ) or not valid_measurement(entry.value, dimension):
                    continue
                if not belongs_to_subject(
                    entry.value, entry.citation.quote, subject, requirements.subjects
                ):
                    continue
                if (
                    dimension.key.startswith("funding_")
                    and dimension.key.rsplit("_", 1)[-1] not in entry.citation.quote
                ):
                    continue
                if dimension.key.startswith("cost_") and normalized(
                    dimension.label
                ) not in normalized(entry.citation.quote):
                    continue
                item = CoverageValue(
                    value=entry.value.rstrip(".,; "),
                    citation=entry.citation,
                    published_at=by_source[entry.citation.source_id].published_at,
                )
                if item not in values and len(values) < 3:
                    values.append(item)
            cells.append(
                CoverageCell(
                    subject=subject, status="supported" if values else "missing", values=values
                )
            )
        rows.append(
            CoverageRow(
                dimension=dimension.key, label=dimension.label, kind=dimension.kind, cells=cells
            )
        )
        missing = [cell.subject for cell in cells if cell.status == "missing"]
        if missing:
            gaps.append(
                f"{dimension.label}: no validated {'figure with units' if dimension.kind == 'quantitative' else 'answer'} for {', '.join(missing)} in retained evidence."
            )
    return rows, gaps


def select_evidence(
    requirements: QuestionRequirements, ranked: list[Passage], limit: int = 10
) -> list[Passage]:
    selected: list[Passage] = []
    for dimension in requirements.dimensions:
        for subject in requirements.subjects:
            for passage in ranked:
                if passage in selected:
                    continue
                if subject != "Requested answer" and subject_alias(subject) not in normalized(
                    passage.quote
                ):
                    continue
                if valid_measurement(passage.quote, dimension):
                    selected.append(passage)
                    break
            if len(selected) >= limit:
                return selected
    for passage in ranked:
        if passage not in selected:
            selected.append(passage)
        if len(selected) == limit:
            break
    return selected
