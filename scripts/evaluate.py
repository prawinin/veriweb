"""Run real synthesis over controlled sources or score saved research artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from pathlib import Path

import httpx
from pydantic import TypeAdapter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from veriweb.config import Settings  # noqa: E402
from veriweb.evaluation import (  # noqa: E402
    CaseScore,
    EvaluationCase,
    load_cases,
    markdown_report,
    run_fixture,
    run_live,
    score_result,
)


def deadline_argument(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Deadline must be a number") from exc
    if not math.isfinite(value) or not 0 < value <= 3600:
        raise argparse.ArgumentTypeError("Deadline must be positive and at most 3600 seconds")
    return value


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["fixture", "score", "live"], default="fixture")
    parser.add_argument(
        "--fixtures", type=Path, default=ROOT / "evals" / "controlled-fixtures.json"
    )
    parser.add_argument("--cases", help="Comma-separated case IDs; defaults to every case")
    parser.add_argument(
        "--category", choices=["numeric", "comparison", "conflict", "scope_date", "unanswerable"]
    )
    parser.add_argument(
        "--results",
        type=Path,
        help="Directory of CASE_ID.json ResearchResult artifacts (score mode)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directory for summary.json, report.md, and artifacts",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("BASE_URL"),
        help="HTTP service URL; defaults to BASE_URL (live mode)",
    )
    parser.add_argument(
        "--deadline", type=deadline_argument, default=360.0, help="Whole-case deadline in seconds"
    )
    args = parser.parse_args()
    if args.mode == "score" and args.results is None:
        parser.error("--results is required in score mode")
    if args.mode == "live" and not args.base_url:
        parser.error("--base-url or BASE_URL is required in live mode")
    return args


def write_private(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)


def select_cases(
    cases: list[EvaluationCase], ids: str | None, category: str | None
) -> list[EvaluationCase]:
    requested = {value.strip() for value in ids.split(",")} if ids is not None else None
    if requested is not None and requested - {case.id for case in cases}:
        raise ValueError("Selection contains unknown case IDs")
    selected = [
        case
        for case in cases
        if (requested is None or case.id in requested)
        and (category is None or case.category == category)
    ]
    if not selected:
        raise ValueError("No cases match the selection")
    return selected


def aggregate(scores: list[CaseScore]) -> dict[str, object]:
    metrics = [
        "answer_accuracy",
        "coverage_recall",
        "abstention_accuracy",
        "conflict_precision",
        "conflict_recall",
        "provenance_rate",
        "wall_seconds",
        "model_seconds",
    ]
    summary: dict[str, object] = {}
    for metric in metrics:
        values = [
            float(value)
            for score in scores
            if isinstance(value := getattr(score, metric), (int, float))
        ]
        summary[metric] = sum(values) / len(values) if values else None
    summary["passed"] = sum(score.passed for score in scores)
    summary["scored"] = len(scores)
    return summary


async def evaluate(args: argparse.Namespace) -> int:
    cases = select_cases(load_cases(args.fixtures), args.cases, args.category)
    args.output.mkdir(parents=True, exist_ok=True)
    artifact_dir = args.output / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    settings = Settings() if args.mode == "fixture" else None
    scores: list[CaseScore] = []
    errors: dict[str, str] = {}
    live_timings: dict[str, float] = {}
    async with httpx.AsyncClient(
        trust_env=False, follow_redirects=False, limits=httpx.Limits(max_connections=6)
    ) as client:
        for index, case in enumerate(cases, start=1):
            try:
                if args.mode == "fixture":
                    if settings is None:
                        raise ValueError("Fixture settings are unavailable")
                    result, score = await run_fixture(case, settings, args.deadline)
                    scores.append(score)
                    write_private(
                        artifact_dir / f"{case.id}.json", result.model_dump_json(indent=2) + "\n"
                    )
                elif args.mode == "score":
                    path = args.results / f"{case.id}.json"
                    if path.stat().st_size > 2_000_000:
                        raise ValueError("Research artifact exceeds size limit")
                    payload = TypeAdapter(dict[str, object]).validate_json(
                        path.read_bytes(), strict=True
                    )
                    scores.append(score_result(case, payload))
                else:
                    started = time.perf_counter()
                    result = await run_live(case.question, args.base_url, client, args.deadline)
                    live_timings[case.id] = time.perf_counter() - started
                    write_private(
                        artifact_dir / f"{case.id}.json", result.model_dump_json(indent=2) + "\n"
                    )
                print(f"{index}/{len(cases)} {case.id}: finished", flush=True)
            except (httpx.HTTPError, ValueError, OSError, TimeoutError) as exc:
                errors[case.id] = type(exc).__name__
                print(f"{index}/{len(cases)} {case.id}: {type(exc).__name__}", flush=True)
    report = {
        "schema_version": 1,
        "dataset": "authored controlled synthetic fixtures; no live-web or held-out accuracy claim",
        "mode": args.mode,
        "semantic_entailment": "not_automatically_verified",
        "selected_case_ids": [case.id for case in cases],
        "scores": [score.model_dump() for score in scores],
        "aggregate": aggregate(scores),
        "by_category": {
            category: aggregate([score for score in scores if score.category == category])
            for category in sorted({case.category for case in cases})
        },
        "errors": errors,
        "live_wall_seconds": live_timings,
        "live_scoring": "unscored: live sources do not share controlled fixture truth"
        if args.mode == "live"
        else None,
    }
    write_private(
        args.output / "summary.json", json.dumps(report, indent=2, allow_nan=False) + "\n"
    )
    markdown = markdown_report(scores, errors, args.mode)
    if args.mode == "live":
        markdown += "\nLive results are unscored: controlled fixture answers do not apply to live sources.\n"
    write_private(args.output / "report.md", markdown)
    return 1 if errors or any(not score.passed for score in scores) else 0


def main() -> int:
    try:
        return asyncio.run(evaluate(arguments()))
    except (ValueError, OSError) as exc:
        print(f"Evaluation failed: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
