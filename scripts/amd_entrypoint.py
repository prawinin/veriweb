"""Own the resident ROCm worker and stop it on container termination."""

import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.serve_rocm import RuntimeSettings  # noqa: E402


def main() -> int:
    settings = RuntimeSettings()
    settings.runtime_file.unlink(missing_ok=True)
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("serve_rocm.py"))])
    stopping = False

    def terminate(signum: int, frame: object) -> None:
        nonlocal stopping
        stopping = True
        process.terminate()

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    started = time.monotonic()
    ready = False
    try:
        with httpx.Client(timeout=2, trust_env=False) as client:
            while process.poll() is None and not stopping:
                if not ready:
                    if time.monotonic() - started > settings.startup_timeout:
                        print("ROCm model startup exceeded configured deadline", file=sys.stderr)
                        return 1
                    if settings.runtime_file.exists():
                        from app import runtime_settings

                        endpoint = runtime_settings(settings.runtime_file)["model_url"]
                        try:
                            ready = client.get(endpoint + "/models").is_success
                        except httpx.HTTPError:
                            ready = False
                time.sleep(0.2)
        return process.returncode or 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        settings.runtime_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
