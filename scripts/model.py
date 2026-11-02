"""Launch a user-selected GGUF model using an existing llama.cpp server."""

import argparse
import os
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument(
        "--gpu-layers",
        type=int,
        default=0,
        help="Start at zero; increase only with a compatible backend",
    )
    parser.add_argument("--device", help="Device name from llama-server --list-devices")
    parser.add_argument("--context", type=int, default=8192)
    args = parser.parse_args()
    bundled = Path(__file__).resolve().parent.parent / ".runtime" / "llama" / "bin" / "llama-server"
    default_binary = str(bundled) if bundled.is_file() else "llama-server"
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    binary = shutil.which(os.getenv("VERIWEB_LLAMA_SERVER", default_binary))
    if not binary or not args.model.is_file():
        parser.error("A working llama-server executable and existing GGUF model file are required")
    if (
        args.model.suffix.lower() != ".gguf"
        or args.gpu_layers < 0
        or not 4096 <= args.context <= 32768
    ):
        parser.error("Use a GGUF file, nonnegative layer count, and context between 4096 and 32768")
    host = os.getenv("VERIWEB_MODEL_HOST", "127.0.0.1")
    port = int(os.getenv("VERIWEB_MODEL_PORT", "8080"))
    if not 0 <= port <= 65535:
        parser.error("Invalid model port")
    command = [
        binary,
        "--model",
        str(args.model.resolve()),
        "--alias",
        os.getenv("VERIWEB_MODEL_NAME", "local-model"),
        "--host",
        host,
        "--port",
        str(port),
        "--ctx-size",
        str(args.context),
        "--parallel",
        "1",
        "--threads",
        "6",
        "--threads-batch",
        "6",
        "--n-gpu-layers",
        str(args.gpu_layers),
        "--batch-size",
        "256",
        "--ubatch-size",
        "128",
    ]
    if args.device:
        command.extend(["--device", args.device])
    library_paths = [str(Path(binary).resolve().parent)]
    if inherited := os.getenv("LD_LIBRARY_PATH"):
        library_paths.append(inherited)
    os.execvpe(
        binary,
        command,
        {**os.environ, "OMP_NUM_THREADS": "6", "LD_LIBRARY_PATH": os.pathsep.join(library_paths)},
    )


if __name__ == "__main__":
    main()
