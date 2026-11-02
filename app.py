"""Exact-answer CLI implementing the user-supplied Match 4 contract."""

import argparse
import asyncio
import os
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

# Include third-party import time in the CLI deadline.
PROCESS_STARTED = time.monotonic()

import httpx  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field, ValidationError  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from veriweb.config import Settings  # noqa: E402
from veriweb.contract import ContractResult, ContractTelemetry, answer_query  # noqa: E402
from veriweb.pipeline import Researcher  # noqa: E402
from veriweb.schemas import ResearchRequest, ResearchResult, RunEvent  # noqa: E402


class RuntimeInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_url: str = Field(max_length=2048)
    model_name: str = Field(min_length=1, max_length=200)


def runtime_settings(path: Path) -> dict[str, str]:
    with path.open("rb") as handle:
        info = os.fstat(handle.fileno())
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("Runtime file must be owned by this user with mode 600")
        data = handle.read(4097)
    if len(data) > 4096:
        raise ValueError("Runtime file exceeds size limit")
    runtime = RuntimeInfo.model_validate_json(data)
    parsed = urlsplit(runtime.model_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("Runtime model endpoint must use loopback HTTP")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Runtime endpoint contains unsupported URL components")
    return {
        "model_url": runtime.model_url,
        "model_name": runtime.model_name,
        "model_backend": "rocm",
    }


def write_result(path: Path, result: ResearchResult | ContractResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".research-", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(result.model_dump_json(indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


async def run_question(
    question: str,
    mode: str,
    output: Path,
    deadline: float,
    settings: Settings,
    client: httpx.AsyncClient,
) -> ResearchResult:
    request = ResearchRequest.model_validate({"question": question, "mode": mode})
    if not 0 < deadline <= 600:
        raise ValueError("Deadline must be greater than zero and at most 600 seconds")
    researcher = Researcher(settings, client)
    async with asyncio.timeout(deadline):
        researcher.model_available = mode == "research" and await researcher.model.available()
        if mode == "research" and not researcher.model_available:
            raise RuntimeError("Research mode requires an available model endpoint")
        stream = cast(
            AsyncGenerator[RunEvent, None], researcher.run(request.question, request.mode)
        )
        try:
            async for event in stream:
                if event.result is not None:
                    write_result(output, event.result)
                    return event.result
        finally:
            await stream.aclose()
    raise RuntimeError("Research pipeline produced no result")


async def execute(args: argparse.Namespace) -> None:
    updates = runtime_settings(args.runtime_file) if args.runtime_file.exists() else {}
    settings = Settings.model_validate({**Settings().model_dump(), **updates})
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.fetch_timeout), follow_redirects=False, trust_env=False
    ) as client:
        if args.report:
            await run_question(
                args.question, args.mode, args.output, args.deadline, settings, client
            )
        else:
            result = await answer_query(
                args.question, args.query_id, args.url, args.corpus, settings, client, args.deadline
            )
            write_result(args.output, result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", "--question", dest="question", required=True)
    parser.add_argument("--url")
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--query-id", default="query")
    parser.add_argument(
        "--report",
        action="store_true",
        help="Export the full dashboard ResearchResult instead of the bounded answer contract",
    )
    parser.add_argument("--mode", choices=["research", "excerpts"], default="research")
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).resolve().parent / "output" / "_output.json"
    )
    parser.add_argument("--deadline", type=float, default=25)
    parser.add_argument(
        "--runtime-file",
        type=Path,
        default=Path(
            os.environ.get(
                "VERIWEB_AMD_RUNTIME_FILE",
                str(Path(__file__).resolve().parent / "output" / "runtime.json"),
            )
        ),
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.report and not args.worker:
        if not 0 < args.deadline <= 25:
            parser.error("Exact-answer deadline must be between zero and 25 seconds")
        started = time.monotonic()
        empty = ContractResult(
            query_id=args.query_id,
            telemetry=ContractTelemetry(runtime="unverified", latency_ms=0, device="unverified"),
        )
        write_result(args.output, empty)
        try:
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--worker"],
                timeout=max(
                    0.1, min(23, args.deadline - (time.monotonic() - PROCESS_STARTED) - 0.5)
                ),
                check=False,
            )
            if completed.returncode:
                return completed.returncode
        except subprocess.TimeoutExpired:
            empty.telemetry.latency_ms = round((time.monotonic() - started) * 1000)
            write_result(args.output, empty)
        return 0
    try:
        asyncio.run(execute(args))
    except (
        ValueError,
        ValidationError,
        RuntimeError,
        TimeoutError,
        httpx.HTTPError,
        OSError,
    ) as exc:
        print(f"Research failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
