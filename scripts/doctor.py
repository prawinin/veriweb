"""Inspect the actual local compute stack without downloading model weights."""

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path


def main() -> None:
    bundled = Path(__file__).resolve().parent.parent / ".runtime" / "llama" / "bin" / "llama-server"
    default_binary = str(bundled) if bundled.is_file() else "llama-server"
    result: dict[str, object] = {
        "gpu_devices_visible": Path("/dev/kfd").exists(),
        "render_devices": len(list(Path("/dev/dri").glob("renderD*"))),
        "llama_server": shutil.which(os.getenv("VERIWEB_LLAMA_SERVER", default_binary)),
    }
    if importlib.util.find_spec("torch"):
        import torch

        result.update(
            {
                "torch": torch.__version__,
                "hip": torch.version.hip,
                "torch_gpu_available": torch.cuda.is_available(),
            }
        )
        if torch.cuda.is_available():
            result["devices"] = [
                {
                    "index": i,
                    "name": torch.cuda.get_device_name(i),
                    "vram_gib": round(
                        torch.cuda.get_device_properties(i).total_memory / 1024**3, 2
                    ),
                }
                for i in range(torch.cuda.device_count())
            ]
            torch.cuda.empty_cache()
    binary = result["llama_server"]
    if isinstance(binary, str):
        try:
            library_paths = [str(Path(binary).resolve().parent)]
            if inherited := os.getenv("LD_LIBRARY_PATH"):
                library_paths.append(inherited)
            process = subprocess.run(
                [binary, "--list-devices"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
                env={**os.environ, "LD_LIBRARY_PATH": os.pathsep.join(library_paths)},
            )
            result["llama_devices"] = (process.stdout + process.stderr)[-4000:]
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["llama_devices"] = f"Device probe failed: {type(exc).__name__}"
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
