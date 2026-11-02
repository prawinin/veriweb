import json
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def project_cli():
    assert (ROOT / "app.py").is_file(), "project CLI missing"
    import app

    return app


async def test_project_cli_writes_real_research_result_from_controlled_http(tmp_path):
    cli = project_cli()
    from veriweb.config import Settings
    from veriweb.pipeline import Researcher

    async def search(self, queries):
        return [("https://official.example/report", "Official report")]

    async def collect(self, urls):
        from veriweb.schemas import Source

        response = await self.client.get(urls[0][0])
        yield Source(id="s1", title="Official report", url=urls[0][0], text=response.text)

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, text="The verified allocation was 42 million dollars during fiscal year 2026. " * 8
        )
    )
    from unittest.mock import patch

    output = tmp_path / "result.json"
    async with httpx.AsyncClient(transport=transport) as client:
        with (
            patch.object(Researcher, "search", search),
            patch.object(Researcher, "collect", collect),
        ):
            await cli.run_question(
                "What was the verified allocation in 2026?",
                "excerpts",
                output,
                5.0,
                Settings(),
                client,
            )
    payload = json.loads(output.read_text())
    assert payload["status"] == "excerpts"
    assert payload["sources"][0]["url"] == "https://official.example/report"
    assert payload["passages"]
    assert output.stat().st_mode & 0o777 == 0o600


def test_runtime_file_rejects_public_endpoint(tmp_path):
    cli = project_cli()
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps({"model_url": "https://external.example/v1", "model_name": "qwen"}))
    path.chmod(0o600)
    with pytest.raises(ValueError, match="loopback"):
        cli.runtime_settings(path)


def test_rocm_runtime_requires_real_hip_device():
    assert (ROOT / "scripts/serve_rocm.py").is_file(), "ROCm runtime missing"
    from scripts.serve_rocm import check_gpu

    with pytest.raises(RuntimeError, match="ROCm"):
        check_gpu(False, None, 0, 10_000, 100)


def test_rocm_runtime_refuses_unsafe_memory_budget():
    assert (ROOT / "scripts/serve_rocm.py").is_file(), "ROCm runtime missing"
    from scripts.serve_rocm import check_gpu

    with pytest.raises(RuntimeError, match="memory"):
        check_gpu(True, "rocm", 1, 3_000, 4_000)


async def test_cli_deadline_cancels_active_pipeline_without_output(tmp_path):
    import asyncio
    from unittest.mock import patch

    from veriweb.config import Settings
    from veriweb.pipeline import Researcher

    cli = project_cli()
    closed = asyncio.Event()

    async def slow_search(self, queries):
        try:
            await asyncio.sleep(10)
        finally:
            closed.set()

    output = tmp_path / "result.json"
    async with httpx.AsyncClient() as client:
        with patch.object(Researcher, "search", slow_search):
            with pytest.raises(TimeoutError):
                await cli.run_question(
                    "What was the allocation during 2026?",
                    "excerpts",
                    output,
                    0.02,
                    Settings(),
                    client,
                )
    assert closed.is_set()
    assert not output.exists()


async def test_runtime_rejects_parallel_generation_and_unknown_model():
    import asyncio
    import threading

    from scripts.serve_rocm import ChatRequest, Runtime, RuntimeSettings, create_app

    started = threading.Event()
    release = threading.Event()

    class ControlledRuntime(Runtime):
        def generate(self, request: ChatRequest) -> tuple[str, int]:
            started.set()
            assert release.wait(timeout=3)
            return '{"answer":"42"}', 6

    runtime = ControlledRuntime(RuntimeSettings())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://runtime"
    ) as client:
        payload = {
            "model": runtime.settings.model_name,
            "messages": [{"role": "user", "content": "Question"}],
        }
        first = asyncio.create_task(client.post("/v1/chat/completions", json=payload))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            second = await client.post("/v1/chat/completions", json=payload)
            assert second.status_code == 429
        finally:
            release.set()
        response = await first
        assert response.json()["usage"]["completion_tokens"] == 6
        payload["model"] = "unconfigured-model"
        assert (await client.post("/v1/chat/completions", json=payload)).status_code == 400


def test_cli_runs_directly_from_checkout_without_pythonpath():
    import os
    import subprocess

    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "app.py"), "--help"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "--question" in result.stdout
