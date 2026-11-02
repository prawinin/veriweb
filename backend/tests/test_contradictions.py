from veriweb.contradictions import Comparisons, numeric_candidates, resolve_comparisons
from veriweb.schemas import Passage


def passage(identifier: str, source: str, quote: str) -> Passage:
    return Passage(id=identifier, source_id=source, quote=quote, start=0, end=len(quote), score=1)


def test_typed_population_lifetime_and_euro_values_are_compared() -> None:
    for left, right in [
        (
            "Sable municipal population in 2025 was 41,200 residents inside the boundary.",
            "Sable municipal population in 2025 was 44,900 residents inside the boundary.",
        ),
        (
            "Umber rated lifetime is 3,100 hours under continuous use at room temperature.",
            "Umber rated lifetime is 3,700 hours under continuous use at room temperature.",
        ),
        (
            "Xenia equipment cost is EUR 640 per unit including the standard configuration.",
            "Xenia installed cost is EUR 910 per unit including the standard configuration.",
        ),
    ]:
        assert numeric_candidates([passage("a", "s1", left), passage("b", "s2", right)])


def test_shortlists_competing_budget_figures_without_declaring_truth() -> None:
    evidence = [
        passage(
            "s1-p1", "s1", "The official 2026 semiconductor program budget totals $10 billion."
        ),
        passage("s2-p2", "s2", "The 2026 semiconductor program budget totals $8.2 billion."),
    ]
    candidates = numeric_candidates(evidence)
    assert len(candidates) == 1
    assert candidates[0].left_id == "s1-p1"
    assert candidates[0].right_id == "s2-p2"
    assert candidates[0].left_value != candidates[0].right_value
    assert candidates[0].right_value == 8_200_000_000


def test_does_not_compare_unrelated_units_or_identical_figures() -> None:
    evidence = [
        passage("s1-p1", "s1", "The 2026 semiconductor program budget totals $10 billion."),
        passage("s2-p2", "s2", "The 2026 semiconductor program budget totals $10 billion."),
        passage("s3-p3", "s3", "The 2026 semiconductor program uses 8.2 TWh of electricity."),
    ]
    assert numeric_candidates(evidence) == []


def test_does_not_treat_reporting_years_alone_as_numeric_conflicts() -> None:
    evidence = [
        passage("s1-p1", "s1", "The semiconductor program published its budget in 2024."),
        passage("s2-p2", "s2", "The semiconductor program published its budget in 2025."),
    ]
    assert numeric_candidates(evidence) == []


def test_extracting_adjacent_heading_text_does_not_change_numeric_scale() -> None:
    evidence = [
        passage(
            "s1-p1",
            "s1",
            "$52.7 billionThe CHIPS Act authorizes semiconductor funding and research.",
        ),
        passage(
            "s2-p2",
            "s2",
            "The CHIPS Act authorizes $52.7 billion in semiconductor funding and research.",
        ),
    ]
    assert numeric_candidates(evidence) == []


def test_unresolved_numeric_differences_remain_visible_without_a_truth_verdict() -> None:
    evidence = [
        passage("s1-p1", "s1", "The 2026 semiconductor program budget totals $10 billion."),
        passage("s2-p2", "s2", "The 2026 semiconductor program budget totals $8.2 billion."),
    ]
    candidates = numeric_candidates(evidence)
    classification = Comparisons.model_validate(
        {
            "comparisons": [
                {
                    "candidate_id": "c1",
                    "relation": "not_comparable",
                    "title": "Uncertain context",
                    "explanation": "Scope could not be established.",
                }
            ]
        }
    )
    conflicts, gaps = resolve_comparisons(classification, candidates, evidence)
    assert len(conflicts) == 1
    assert conflicts[0].kind == "unresolved"
    assert conflicts[0].left_quantity == "$10B"
    assert conflicts[0].right_quantity == "$8.2B"
    assert conflicts[0].left.quote == evidence[0].quote
    assert conflicts[0].right.quote == evidence[1].quote
    assert gaps


def test_numeric_conflict_needs_two_competing_measurements() -> None:
    from veriweb.contradictions import conflict_is_evidenced
    from veriweb.schemas import Citation, Conflict, Passage

    quotes = [
        "Cobalt cost is USD 37 per unit in its standard configuration.",
        "Cobalt uses a standard configuration and excludes speculative future revisions.",
    ]
    passages = [
        Passage(id=f"s{i}-p1", source_id=f"s{i}", quote=q, start=0, end=len(q), score=1)
        for i, q in enumerate(quotes, 1)
    ]
    conflict = Conflict(
        title="Invented disagreement",
        explanation="The second source contains no competing figure.",
        kind="numeric",
        left=Citation(source_id="s1", quote=quotes[0]),
        right=Citation(source_id="s2", quote=quotes[1]),
    )
    assert not conflict_is_evidenced(conflict, passages)
