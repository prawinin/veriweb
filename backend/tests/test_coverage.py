from veriweb.coverage import build_coverage, requirements_for
from veriweb.schemas import (
    Citation,
    EvidenceCell,
    Passage,
    QuestionRequirements,
    RequestedDimension,
    Source,
)

QUESTION = "Compare sodium-ion batteries versus lithium-ion batteries for grid storage. Compare costs, lifetimes, and commercial availability."


def evidence(text: str) -> tuple[list[Source], list[Passage]]:
    return (
        [Source(id="s1", title="Technical study", url="https://lab.example/study", text=text)],
        [Passage(id="s1-p1", source_id="s1", quote=text, start=0, end=len(text), score=1)],
    )


def test_explicit_comparison_dimensions_survive_without_a_model() -> None:
    plan = requirements_for(QUESTION)
    assert plan.subjects == ["sodium-ion batteries", "lithium-ion batteries"]
    assert {item.key for item in plan.dimensions} == {"cost", "lifetime", "availability"}


def test_flattering_prose_does_not_answer_numeric_comparison() -> None:
    plan = requirements_for(QUESTION)
    sources, passages = evidence(
        "Sodium-ion batteries are cost-effective and have a long lifetime."
    )
    rows, gaps = build_coverage(plan, [], sources, passages)
    assert len(rows) == 3
    assert all(cell.status == "missing" for row in rows for cell in row.cells)
    assert any("Cost" in gap for gap in gaps)
    assert any("Lifetime" in gap for gap in gaps)


def test_exact_quantity_is_bound_to_its_subject_and_dimension() -> None:
    plan = requirements_for(QUESTION)
    text = "Sodium-ion batteries cost $70/kWh. Lithium-ion batteries cost $95/kWh. These are cell-level estimates for 2025."
    sources, passages = evidence(text)
    rows, _ = build_coverage(
        plan,
        [
            EvidenceCell(
                dimension="cost",
                subject=plan.subjects[0],
                value="$70/kWh",
                citation=Citation(source_id="s1", quote=text),
            )
        ],
        sources,
        passages,
    )
    assert rows[0].cells[0].values[0].value == "$70/kWh"
    assert rows[0].cells[1].status == "missing"


def test_wrong_entity_quantity_and_wrong_unit_are_rejected() -> None:
    plan = requirements_for(QUESTION)
    text = "Sodium-ion batteries cost $70/kWh and retain 90% capacity. Lithium-ion batteries cost $95/kWh."
    sources, passages = evidence(text)
    cells = [
        EvidenceCell(
            dimension="cost",
            subject=plan.subjects[0],
            value=value,
            citation=Citation(source_id="s1", quote=text),
        )
        for value in ("$95/kWh", "90%", "$900/kWh")
    ]
    rows, _ = build_coverage(plan, cells, sources, passages)
    assert rows[0].cells[0].status == "missing"


def test_table_column_values_remain_associated_with_column_subject() -> None:
    plan = requirements_for(QUESTION)
    text = "| Metric | Sodium-ion batteries | Lithium-ion batteries |\n| Cell cost | $70/kWh | $95/kWh |\n| Cycle lifetime | 3000 cycles | 5000 cycles |"
    sources, passages = evidence(text)
    rows, _ = build_coverage(
        plan,
        [
            EvidenceCell(
                dimension="cost",
                subject=plan.subjects[0],
                value=value,
                citation=Citation(source_id="s1", quote=text),
            )
            for value in ("$70/kWh", "$95/kWh")
        ],
        sources,
        passages,
    )
    assert [value.value for value in rows[0].cells[0].values] == ["$70/kWh"]


def test_short_value_cannot_borrow_a_substring_from_another_measurement() -> None:
    plan = requirements_for(QUESTION)
    text = "Sodium-ion batteries cost $170/kWh in the factory-level estimate. Lithium-ion batteries cost $95/kWh."
    sources, passages = evidence(text)
    rows, _ = build_coverage(
        plan,
        [
            EvidenceCell(
                dimension="cost",
                subject=plan.subjects[0],
                value="70",
                citation=Citation(source_id="s1", quote=text),
            )
        ],
        sources,
        passages,
    )
    assert rows[0].cells[0].status == "missing"


def test_planning_preserves_subjects_and_does_not_turn_qualifiers_into_dimensions() -> None:
    question = "Compare the storage capacity of Cobalt and Quartz in TB."
    proposed = QuestionRequirements(
        dimensions=[
            RequestedDimension(key="system", label="Cobalt and Quartz", kind="qualitative"),
            RequestedDimension(key="unit", label="TB", kind="quantitative"),
        ]
    )
    plan = requirements_for(question, proposed)
    assert plan.subjects == ["Cobalt", "Quartz"]
    assert [item.key for item in plan.dimensions] == ["capacity"]


def test_negative_availability_is_an_answer_and_generic_cost_is_not() -> None:
    plan = requirements_for("Is Cobalt commercially available?")
    text = "Cobalt is commercially unavailable; it remains a laboratory prototype."
    sources, passages = evidence(text)
    rows, _ = build_coverage(
        plan,
        [
            EvidenceCell(
                dimension="availability",
                subject="Cobalt",
                value="commercially unavailable",
                citation=Citation(source_id="s1", quote=text),
            )
        ],
        sources,
        passages,
    )
    assert rows[0].cells[0].status == "supported"


def test_model_dimension_plural_does_not_duplicate_a_required_metric() -> None:
    proposed = QuestionRequirements(
        subjects=["sodium-ion batteries", "lithium-ion batteries"],
        dimensions=[RequestedDimension(key="costs", label="costs", kind="quantitative")],
    )
    plan = requirements_for(QUESTION, proposed)
    assert len(plan.dimensions) == 3


def test_partial_planner_subjects_cannot_erase_an_explicit_comparison() -> None:
    plan = requirements_for(
        "Compare Cobalt versus Quartz capacity.", QuestionRequirements(subjects=["Cobalt"])
    )
    assert plan.subjects == ["Cobalt", "Quartz"]


def test_negated_truncated_or_unqualified_values_never_establish_coverage() -> None:
    examples = [
        ("What is Cobalt cost?", "Cobalt cost is $500 per installed unit.", "cost", "$50"),
        (
            "What is Cobalt cost?",
            "Cobalt cost is not $50; its price remains undisclosed.",
            "cost",
            "$50",
        ),
        (
            "Is Cobalt commercially available?",
            "Cobalt is not commercially available at this time.",
            "availability",
            "available",
        ),
        (
            "What is Cobalt capacity?",
            "Cobalt capacity in 2025 remains undisclosed.",
            "capacity",
            "2025",
        ),
    ]
    for question, text, dimension, value in examples:
        plan = requirements_for(question)
        sources, passages = evidence(text)
        rows, _ = build_coverage(
            plan,
            [
                EvidenceCell(
                    dimension=dimension,
                    subject="Cobalt",
                    value=value,
                    citation=Citation(source_id="s1", quote=text),
                )
            ],
            sources,
            passages,
        )
        assert all(cell.status == "missing" for row in rows for cell in row.cells)


def test_deterministic_extraction_keeps_units_and_negative_availability() -> None:
    from veriweb.coverage import extract_values

    plan = requirements_for("What is Cobalt cost and commercial availability?")
    text = "Cobalt cost is USD 37 million. Cobalt is invitation only."
    sources, passages = evidence(text)
    rows, _ = build_coverage(plan, extract_values(plan, passages), sources, passages)
    assert rows[0].cells[0].values[0].value == "USD 37 million"
    assert rows[1].cells[0].values[0].value == "invitation only"


def test_scope_planning_preserves_years_and_cost_boundaries() -> None:
    plan = requirements_for("Compare Cobalt funding in 2023 and 2026. Explain the difference.")
    assert plan.subjects == ["Cobalt"]
    assert [d.label for d in plan.dimensions] == ["2023 funding", "2026 funding"]
    plan = requirements_for("Compare Quartz equipment-only cost and installed cost.")
    assert [d.label for d in plan.dimensions] == ["equipment-only cost", "installed cost"]


def test_single_year_and_cost_scope_cannot_borrow_other_measurements() -> None:
    from veriweb.coverage import extract_values

    for question, text in [
        ("What was Cobalt funding in 2024?", "Cobalt received funding of USD 20 million in 2023."),
        ("What is Cobalt installed cost?", "Cobalt equipment-only cost is USD 100 per unit."),
    ]:
        plan = requirements_for(question)
        sources, passages = evidence(text)
        rows, _ = build_coverage(plan, extract_values(plan, passages), sources, passages)
        assert all(cell.status == "missing" for row in rows for cell in row.cells)


def test_each_amount_uses_its_own_year_clause() -> None:
    from veriweb.coverage import extract_values

    plan = requirements_for("Compare Cobalt funding in 2023 and 2024.")
    sources, passages = evidence(
        "Cobalt funding was USD 10 million in 2023 and USD 20 million in 2024."
    )
    rows, _ = build_coverage(plan, extract_values(plan, passages), sources, passages)
    assert [[v.value for v in row.cells[0].values] for row in rows] == [
        ["USD 10 million"],
        ["USD 20 million"],
    ]


def test_plural_orbital_period_has_typed_scope() -> None:
    from veriweb.coverage import extract_values

    plan = requirements_for("Compare the orbital periods of Mercury and Venus in Earth days.")
    assert plan.dimensions[0].key == "orbital_period"
    sources, passages = evidence(
        "Mercury solar day equals 176 Earth days. Mercury orbits the Sun every 88 Earth days."
    )
    rows, _ = build_coverage(plan, extract_values(plan, passages), sources, passages)
    assert all(v.value != "176 Earth days" for cell in rows[0].cells for v in cell.values)


def test_exact_date_and_instruction_words_preserve_requested_scope() -> None:
    date_plan = requirements_for("On what exact date was the Elm archive released to the public?")
    assert date_plan.dimensions[0].kind == "date"
    conflict_plan = requirements_for(
        "What population figures do the records report for Sable? Identify any same-scope conflict."
    )
    assert conflict_plan.subjects == ["Sable"]


def test_coordinated_population_scopes_keep_shared_entity() -> None:
    plan = requirements_for(
        "Compare Vale city and metropolitan population figures for 2025. Explain the difference."
    )
    assert plan.subjects == ["Vale city", "Vale metropolitan"]


def test_metric_qualifiers_and_dataset_names_do_not_create_entities_or_facets() -> None:
    proposed = QuestionRequirements(
        subjects=["Xenia equipment-only"],
        dimensions=[RequestedDimension(key="cost", label="Cost", kind="quantitative")],
    )
    plan = requirements_for(
        "Compare Xenia equipment-only cost and installed cost in 2025.", proposed
    )
    assert plan.subjects == ["Xenia"]
    proposed = QuestionRequirements(
        subjects=["Acorn"],
        dimensions=[RequestedDimension(key="dataset", label="Acorn dataset", kind="qualitative")],
    )
    plan = requirements_for(
        "On what exact date was the Acorn dataset first publicly released?", proposed
    )
    assert [d.key for d in plan.dimensions] == ["date"]


def test_scope_variants_share_identity_without_merging_distinct_subjects() -> None:
    from veriweb.coverage import subject_identity

    assert subject_identity("Vale city") == subject_identity("Vale metropolitan")
    assert subject_identity("Vale city") != subject_identity("Sable city")
    assert subject_identity("sodium-ion batteries") != subject_identity("lithium-ion batteries")


def test_reference_units_are_not_extra_comparison_subjects() -> None:
    plan = requirements_for("What is the orbital period of Mercury in Earth days?")
    assert plan.subjects == ["Mercury"]


def test_orbital_period_does_not_use_rotation_or_solar_day() -> None:
    from veriweb.coverage import extract_values

    plan = requirements_for("What is the orbital period of Mercury in Earth days?")
    text = "Mercury completes one rotation every 59 Earth days. One Mercury solar day equals 176 Earth days. Mercury zips around the Sun every 88 Earth days."
    sources, passages = evidence(text)
    rows, _ = build_coverage(plan, extract_values(plan, passages), sources, passages)
    assert [v.value for v in rows[0].cells[0].values] == ["88 Earth days"]


def test_orbital_period_excludes_solar_and_synodic_cycles() -> None:
    from veriweb.coverage import extract_values

    plan = requirements_for("Compare the orbital periods of Mercury and Venus in Earth days.")
    text = (
        "Mercury's full cycle of daylight and darkness lasts 176 Earth days, which is more than two Mercurian years. "
        "Jupiter has a synodic period of 398.8 days while Venus has a synodic period of 1.6 years."
    )
    sources, passages = evidence(text)
    rows, gaps = build_coverage(plan, extract_values(plan, passages), sources, passages)
    assert all(not cell.values for cell in rows[0].cells)
    assert gaps


def test_orbital_values_bind_to_preceding_orbit_clause() -> None:
    from veriweb.coverage import extract_values

    examples = [
        (
            "Venus",
            "Your day would be 243 Earth days long — longer than a Venus year (one trip around the Sun), which takes only 225 Earth days.",
            ["225 Earth days"],
        ),
        (
            "Jupiter",
            "One day on Jupiter takes 9.9 hours, and Jupiter makes a complete orbit around the Sun in about 12 Earth years (4,333 Earth days).",
            ["4,333 Earth days"],
        ),
        (
            "Mars",
            "On Earth the seasons last 3 months, while on Mars the seasons vary because of its orbit around the Sun.",
            [],
        ),
        ("Jupiter", "Jupiter's Great Red Spot has persisted for more than 300 years.", []),
    ]
    for subject, text, expected in examples:
        plan = requirements_for(f"What is {subject} orbital period in Earth days?")
        sources, passages = evidence(text)
        rows, _ = build_coverage(plan, extract_values(plan, passages), sources, passages)
        assert [v.value for v in rows[0].cells[0].values] == expected


def test_single_subject_cannot_use_another_entity_value() -> None:
    plan = requirements_for("What is Cobalt cost?")
    text = "Quartz cost is USD 70 per unit under the standard configuration."
    sources, passages = evidence(text)
    rows, _ = build_coverage(
        plan,
        [
            EvidenceCell(
                dimension="cost",
                subject="Cobalt",
                value="USD 70 per unit",
                citation=Citation(source_id="s1", quote=text),
            )
        ],
        sources,
        passages,
    )
    assert rows[0].cells[0].status == "missing"
