"""Explicitly download optional embedding or quantized language-model artifacts."""

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["embeddings", "llm"])
    parser.add_argument("--repo", help="Override the default Hugging Face model repository")
    parser.add_argument("--file", help="GGUF filename in the language-model repository")
    args = parser.parse_args()
    os.environ.setdefault("HF_HOME", str(ROOT / ".cache" / "huggingface"))
    from huggingface_hub import hf_hub_download, snapshot_download

    if args.kind == "embeddings":
        destination = ROOT / "models" / "bge-small-en-v1.5"
        snapshot_download(
            repo_id=args.repo or "BAAI/bge-small-en-v1.5",
            local_dir=destination,
            allow_patterns=["*.json", "*.txt", "*.safetensors", "*.model", "1_Pooling/*"],
            max_workers=2,
        )
    else:
        destination = ROOT / "models" / "llm"
        hf_hub_download(
            repo_id=args.repo or "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
            filename=args.file or "qwen2.5-1.5b-instruct-q4_k_m.gguf",
            local_dir=destination,
        )
    print(f"Model artifacts saved in {destination.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
