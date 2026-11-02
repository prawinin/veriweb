import httpx
from veriweb.config import Settings
from veriweb.contract import answer_query


async def test_contract_reads_saved_html_and_abstains_on_missing_metrics(tmp_path):
    (tmp_path / "spec.html").write_text(
        "<html><title>Cobalt specification</title><article><p>Cobalt storage capacity is 24 TB under the standard configuration.</p></article></html>"
    )
    async with httpx.AsyncClient() as client:
        result = await answer_query(
            "What is Cobalt capacity?", "case1", None, tmp_path, Settings(model_url=None), client, 2
        )
        missing = await answer_query(
            "What is Cobalt cost?", "case2", None, tmp_path, Settings(model_url=None), client, 2
        )
    assert result.answer == "24 TB"
    assert result.query_id == "case1"
    assert result.citations == [str(tmp_path / "spec.html")]
    assert missing.answer == "" and missing.confidence == 0


async def test_equivalent_earth_day_notation_does_not_create_conflict(tmp_path):
    (tmp_path / "orbit.html").write_text(
        "<html><title>Mercury</title><article><p>Mercury orbits the Sun every 88 Earth days.</p>"
        "<p>Mercury speeds around the Sun every 88 days.</p></article></html>"
    )
    async with httpx.AsyncClient() as client:
        result = await answer_query(
            "What is Mercury orbital period in Earth days?",
            "same-unit",
            None,
            tmp_path,
            Settings(model_url=None),
            client,
            3,
        )
    assert result.answer == "88 Earth days"
    assert not result.conflict_detected


def test_process_deadline_leaves_current_query_abstention(tmp_path):
    import json
    import subprocess
    import sys
    import time
    from pathlib import Path

    output = tmp_path / "_output.json"
    started = time.monotonic()
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "app.py"),
            "--query",
            "What is Cobalt cost?",
            "--query-id",
            "deadline-case",
            "--url",
            "https://example.com",
            "--deadline",
            "0.2",
            "--output",
            str(output),
        ],
        timeout=5,
        check=False,
        capture_output=True,
    )
    payload = json.loads(output.read_text())
    assert result.returncode == 0
    assert time.monotonic() - started < 5
    assert payload["query_id"] == "deadline-case"
    assert payload["answer"] == "" and payload["citations"] == []
