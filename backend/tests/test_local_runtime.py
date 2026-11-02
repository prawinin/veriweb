import os
import runpy
import sys
from pathlib import Path
from unittest.mock import patch


def test_model_launcher_resolves_libraries_beside_selected_binary(tmp_path: Path) -> None:
    binary = tmp_path / "runtime" / "llama-server"
    binary.parent.mkdir()
    binary.write_text("runtime")
    model = tmp_path / "model.gguf"
    model.write_bytes(b"GGUF")
    script = Path(__file__).resolve().parents[2] / "scripts" / "model.py"
    with (
        patch.object(sys, "argv", [str(script), "--model", str(model)]),
        patch("shutil.which", return_value=str(binary)),
        patch.dict(os.environ, {"LD_LIBRARY_PATH": "/existing/libraries"}),
        patch("os.execvpe") as execute,
    ):
        runpy.run_path(str(script), run_name="__main__")
    environment = execute.call_args.args[2]
    assert environment["LD_LIBRARY_PATH"] == f"{binary.parent}:/existing/libraries"
