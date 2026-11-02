"""Build an isolated Radeon Vulkan inference runtime without modifying system packages."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVISION = "0ec4027a2a0183de87c007069adddc06e665f7de"


def run(arguments: list[str], timeout: int = 180) -> None:
    subprocess.run(arguments, check=True, timeout=timeout)


def clone(url: str, destination: Path) -> None:
    if not destination.exists():
        run(["git", "clone", "--depth", "1", url, str(destination)])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=6)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 6:
        parser.error("Use between one and six build workers")
    if any(shutil.which(tool) is None for tool in ("git", "cmake", "ninja", "glslc")):
        parser.error("Install git, cmake, ninja, and the Vulkan shader compiler glslc first")
    runtime = ROOT / ".runtime" / "llama"
    source = runtime / "source"
    vulkan = runtime / "vulkan-headers"
    spirv = runtime / "spirv-headers"
    sdk = runtime / "sdk"
    runtime.mkdir(parents=True, exist_ok=True)
    clone(os.getenv("VERIWEB_LLAMA_SOURCE", "https://github.com/ggml-org/llama.cpp.git"), source)
    run(["git", "-C", str(source), "fetch", "--depth", "1", "origin", REVISION])
    run(["git", "-C", str(source), "checkout", "--detach", REVISION])
    clone(
        os.getenv(
            "VERIWEB_VULKAN_HEADERS_SOURCE", "https://github.com/KhronosGroup/Vulkan-Headers.git"
        ),
        vulkan,
    )
    clone(
        os.getenv(
            "VERIWEB_SPIRV_HEADERS_SOURCE", "https://github.com/KhronosGroup/SPIRV-Headers.git"
        ),
        spirv,
    )
    run(["cmake", "-S", str(spirv), "-B", str(spirv / "build"), f"-DCMAKE_INSTALL_PREFIX={sdk}"])
    run(["cmake", "--install", str(spirv / "build")])
    build = runtime / "build"
    run(
        [
            "cmake",
            "-S",
            str(source),
            "-B",
            str(build),
            "-G",
            "Ninja",
            "-DGGML_VULKAN=ON",
            "-DLLAMA_CURL=OFF",
            "-DLLAMA_BUILD_TESTS=OFF",
            f"-DVulkan_INCLUDE_DIR={vulkan / 'include'}",
            f"-DCMAKE_PREFIX_PATH={sdk}",
            "-DCMAKE_BUILD_TYPE=Release",
        ]
    )
    run(
        ["cmake", "--build", str(build), "--target", "llama-server", "-j", str(args.jobs)],
        timeout=1800,
    )
    destination = runtime / "bin"
    destination.mkdir(exist_ok=True)
    for artifact in (build / "bin").iterdir():
        if artifact.name == "llama-server" or ".so" in artifact.name:
            shutil.copy2(artifact.resolve(), destination / artifact.name)
    print(f"Built {destination.relative_to(ROOT) / 'llama-server'}")


if __name__ == "__main__":
    main()
