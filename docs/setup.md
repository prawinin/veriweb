# Model and AMD setup

The basic application runs without PyTorch or a model server in Evidence only mode. For synthesis, configure an endpoint supporting chat completions and JSON-schema output. The tested local path uses a quantized GGUF model with llama.cpp Vulkan.

## Reuse the installed ML stack

Create the project virtual environment with `--system-site-packages` when ROCm PyTorch is installed globally. Confirm the intended installation before adding embeddings:

```sh
.venv/bin/python -c 'import torch; print(torch.__version__, torch.version.hip)'
.venv/bin/python -m pip install -e '.[embeddings]'
.venv/bin/python scripts/setup_models.py embeddings
```

This downloads BAAI/bge-small-en-v1.5 into `models/`. Enable it in `.env`:

```dotenv
VERIWEB_EMBEDDINGS_MODEL=models/bge-small-en-v1.5
VERIWEB_EMBEDDINGS_DEVICE=cpu
```

If PyTorch is absent, install the appropriate CPU or ROCm build for the machine first. The setup scripts do not install GPU drivers or choose a CUDA distribution.

## Local Qwen model

Download the model used in the demo:

```sh
.venv/bin/python scripts/setup_models.py llm   --repo Qwen/Qwen2.5-3B-Instruct-GGUF   --file qwen2.5-3b-instruct-q4_k_m.gguf
```

The GGUF download is about 2.1 GB. The default `scripts/setup_models.py llm` command instead downloads the smaller 1.5B Q4_K_M model.

Use an existing GPU-capable llama-server, selected through `VERIWEB_LLAMA_SERVER`, or build a project-local Vulkan runtime:

```sh
.venv/bin/python scripts/build_runtime.py --jobs 6
.venv/bin/python scripts/doctor.py
```

The build needs Git, CMake, Ninja, a C++ compiler, the Vulkan loader, and `glslc`. It fetches a pinned llama.cpp revision and builds under `.runtime/`; it does not replace system drivers.

Use the device list from the doctor to identify the discrete Radeon. The demonstrated laptop used `Vulkan1`; device numbering can differ on another machine. Configure the model path, alias, endpoint, and selected device in `.env`:

```dotenv
VERIWEB_GGUF_PATH=models/llm/qwen2.5-3b-instruct-q4_k_m.gguf
VERIWEB_MODEL_NAME=Qwen2.5-3B-Q4_K_M
VERIWEB_MODEL_BACKEND=vulkan
VERIWEB_MODEL_URL=http://127.0.0.1:8080/v1
VERIWEB_MODEL_HOST=127.0.0.1
VERIWEB_MODEL_PORT=8080
VERIWEB_GPU_DEVICE=Vulkan1
VERIWEB_GPU_LAYERS=99
VERIWEB_MODEL_CONTEXT=8192
```

The endpoint host and port must agree with the server configuration. Then run:

```sh
.venv/bin/python scripts/dev.py --with-model
```

The launcher owns the model, API, and frontend processes. Ctrl+C stops them together. `--ephemeral` chooses unused frontend and API ports. The local model uses one inference slot, six CPU threads, and bounded batches. Keep embeddings on the CPU on a 4GB card. Larger models or contexts require fresh memory measurements; 7B/8B FP16 models do not fit this GPU.

ROCm PyTorch and a llama.cpp executable are separate runtimes. A working ROCm installation does not make a CPU-only llama-server GPU-capable. `VERIWEB_MODEL_BACKEND` is a configuration label; the dashboard does not treat it as hardware attestation.

## Remote model

Set `VERIWEB_MODEL_URL`, `VERIWEB_MODEL_NAME`, and optional `VERIWEB_MODEL_KEY`. Use an endpoint with structured JSON-schema support. Set the backend label to match the actual provider. Model keys and optional `VERIWEB_TAVILY_KEY` remain in environment variables.

## Containers

`docker compose up --build` builds the dashboard and API. It does not bundle model weights or ROCm. To use an external model, set `VERIWEB_CONTAINER_MODEL_URL` to an address reachable from the container; its loopback address is not the host's loopback address.

`Dockerfile.amd` is a separate candidate profile with a resident Transformers/HIP worker. It requires compatible Transformers weights rather than the GGUF file above. Downloads are disabled unless explicitly enabled. The pinned base image is roughly a 20.5GB compressed download. This profile has not been built or executed in the recorded local verification.

Container ports, origins, model paths, deadlines, and memory settings are configurable through the variables listed in `.env.example`. Before external hosting, add authentication and per-user isolation.
