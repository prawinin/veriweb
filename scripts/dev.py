"""Start and cleanly stop the local API and Next.js workbench."""

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def port(value: str) -> int:
    number = int(value)
    if not 0 <= number <= 65535:
        raise ValueError("Ports must be between 0 and 65535")
    return number


def free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((host, 0))
        return int(listener.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ephemeral", action="store_true", help="Choose unused API and web ports")
    parser.add_argument(
        "--with-model",
        action="store_true",
        help="Start the configured local GGUF model as an owned child",
    )
    parser.add_argument(
        "--production", action="store_true", help="Serve the existing frontend production build"
    )
    args = parser.parse_args()
    python = ROOT / ".venv" / "bin" / "python"
    if not python.exists() or not (ROOT / "web" / "node_modules").exists():
        parser.error("Install the Python and frontend dependencies described in README.md first")
    if Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        os.execv(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]])
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    host = os.getenv("HOST", "127.0.0.1")
    api_host = os.getenv("VERIWEB_API_HOST", "127.0.0.1")
    api_port = (
        free_port(api_host) if args.ephemeral else port(os.getenv("VERIWEB_API_PORT", "8000"))
    )
    web_port = free_port(host) if args.ephemeral else port(os.getenv("PORT", "3000"))
    if api_port == 0:
        api_port = free_port(api_host)
    env = {
        **os.environ,
        "HOST": host,
        "PORT": str(web_port),
        "VERIWEB_API_URL": f"http://{api_host}:{api_port}",
        "NEXT_TELEMETRY_DISABLED": "1",
        "OMP_NUM_THREADS": "6",
        "TOKENIZERS_PARALLELISM": "false",
    }
    model_command: list[str] | None = None
    if args.with_model:
        model_path = Path(
            os.getenv("VERIWEB_GGUF_PATH", "models/llm/qwen2.5-1.5b-instruct-q4_k_m.gguf")
        )
        if not model_path.is_absolute():
            model_path = ROOT / model_path
        if not model_path.is_file():
            parser.error("Download the configured GGUF model first")
        model_host = os.getenv("VERIWEB_MODEL_HOST", "127.0.0.1")
        model_port = port(os.getenv("VERIWEB_MODEL_PORT", "8080")) or free_port(model_host)
        env.update(
            {
                "VERIWEB_MODEL_PORT": str(model_port),
                "VERIWEB_MODEL_URL": f"http://{model_host}:{model_port}/v1",
            }
        )
        model_command = [
            str(python),
            str(ROOT / "scripts" / "model.py"),
            "--model",
            str(model_path),
            "--gpu-layers",
            os.getenv("VERIWEB_GPU_LAYERS", "0"),
            "--context",
            os.getenv("VERIWEB_MODEL_CONTEXT", "8192"),
        ]
        device = os.getenv("VERIWEB_GPU_DEVICE")
        if device:
            model_command.extend(["--device", device])
    children: list[subprocess.Popen[bytes]] = []
    exit_code = 0

    def stop(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        if model_command is not None:
            children.append(
                subprocess.Popen(model_command, cwd=ROOT, env=env, start_new_session=True)
            )
        children.append(
            subprocess.Popen(
                [
                    str(python),
                    "-m",
                    "uvicorn",
                    "veriweb.app:app",
                    "--app-dir",
                    "backend",
                    "--host",
                    api_host,
                    "--port",
                    str(api_port),
                    "--no-access-log",
                ],
                cwd=ROOT,
                env=env,
                start_new_session=True,
            )
        )
        children.append(
            subprocess.Popen(
                ["npm", "run", "start" if args.production else "dev"],
                cwd=ROOT / "web",
                env=env,
                start_new_session=True,
            )
        )
        while all(child.poll() is None for child in children):
            time.sleep(0.3)
        exit_code = next((child.returncode for child in children if child.returncode), 0)
    except KeyboardInterrupt:
        print("Stopping Veriweb services.")
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                with suppress(ProcessLookupError):
                    os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=3)
        # Let Python finalize multiprocessing resources before stopping remaining descendants.
        for child in children:
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGTERM)
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
