"""Serialized local Transformers inference on a real ROCm device."""

import asyncio
import gc
import json
import os
import socket
import threading
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol, cast

import torch
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VERIWEB_AMD_", extra="ignore")
    host: str = Field(default="127.0.0.1", pattern=r"^(127\.0\.0\.1|localhost)$")
    port: int = Field(default=0, ge=0, le=65535)
    model: str = Field(default="Qwen/Qwen2.5-1.5B-Instruct", min_length=1, max_length=512)
    model_name: str = Field(default="veriweb-rocm", min_length=1, max_length=200)
    allow_download: bool = False
    context: int = Field(default=8192, ge=4096, le=16384)
    max_tokens: int = Field(default=1600, ge=16, le=2048)
    request_timeout: float = Field(default=120, ge=5, le=300)
    startup_timeout: float = Field(default=540, ge=10, le=600)
    memory_fraction: float = Field(default=0.85, gt=0.1, le=0.9)
    threads: int = Field(default=6, ge=1, le=6)
    runtime_file: Path = Path(__file__).resolve().parents[1] / "output" / "runtime.json"


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(pattern=r"^(system|user|assistant)$")
    content: str = Field(max_length=100_000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=200)
    messages: list[Message] = Field(min_length=1, max_length=16)
    max_tokens: int = Field(default=512, ge=1, le=2048)
    temperature: float = Field(default=0, ge=0, le=2)
    stream: bool = False
    response_format: dict[str, object] | None = None


class Tokenizer(Protocol):
    eos_token_id: int

    def apply_chat_template(self, messages: list[dict[str, str]], **kwargs: object) -> str: ...
    def __call__(self, text: str, **kwargs: object) -> Mapping[str, torch.Tensor]: ...
    def decode(self, tokens: torch.Tensor, **kwargs: object) -> str: ...


class LoadedModel(Protocol):
    def to(self, device: str) -> object: ...
    def eval(self) -> object: ...


class LanguageModel(Protocol):
    def generate(self, **kwargs: object) -> torch.Tensor: ...


def check_gpu(available: bool, hip: str | None, count: int, free: int, required: int) -> None:
    if not available or not hip or count < 1:
        raise RuntimeError("A real ROCm PyTorch GPU is required; CPU/CUDA fallback is disabled")
    if free < required:
        raise RuntimeError("Insufficient GPU memory for FP16 weights, bounded KV cache and reserve")


class Runtime:
    def __init__(self, settings: RuntimeSettings) -> None:
        self.settings = settings
        self.model: LanguageModel | None = None
        self.tokenizer: Tokenizer | None = None
        self.lock = asyncio.Lock()
        self.cancel = threading.Event()

    def load(self) -> None:
        os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
        os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "15")
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

        torch.set_num_threads(self.settings.threads)
        check_gpu(torch.cuda.is_available(), torch.version.hip, torch.cuda.device_count(), 1, 0)
        local = not self.settings.allow_download
        config = AutoConfig.from_pretrained(
            self.settings.model, local_files_only=local, trust_remote_code=False
        )
        hidden = int(config.hidden_size)
        layers = int(config.num_hidden_layers)
        vocabulary = int(config.vocab_size)
        heads = int(config.num_attention_heads)
        kv_heads = int(getattr(config, "num_key_value_heads", heads))
        weights = (12 * hidden * hidden * layers + 2 * vocabulary * hidden) * 2
        cache = 2 * layers * kv_heads * (hidden // heads) * self.settings.context * 2
        required = weights + cache + 1024**3
        free, _ = torch.cuda.mem_get_info()
        check_gpu(
            True,
            torch.version.hip,
            torch.cuda.device_count(),
            int(free * self.settings.memory_fraction),
            required,
        )
        torch.cuda.set_per_process_memory_fraction(self.settings.memory_fraction)
        self.tokenizer = cast(
            Tokenizer,
            AutoTokenizer.from_pretrained(
                self.settings.model, local_files_only=local, trust_remote_code=False
            ),
        )
        model = cast(
            LoadedModel,
            AutoModelForCausalLM.from_pretrained(
                self.settings.model,
                local_files_only=local,
                trust_remote_code=False,
                dtype=torch.float16,
                attn_implementation="sdpa",
            ),
        )
        model.to("cuda:0")
        model.eval()
        self.model = cast(LanguageModel, model)

    def generate(self, request: ChatRequest) -> tuple[str, int]:
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("Model is not loaded")
        messages = [message.model_dump() for message in request.messages]
        if request.response_format:
            schema = json.dumps(request.response_format)
            if len(schema) > 32_000:
                raise ValueError("Response schema exceeds size budget")
            messages.append(
                {
                    "role": "system",
                    "content": "Return only a JSON object matching this response format: " + schema,
                }
            )
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        encoded = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
        length = int(encoded["input_ids"].shape[-1])
        budget = min(request.max_tokens, self.settings.max_tokens)
        if length + budget > self.settings.context:
            raise ValueError("Prompt and requested output exceed context budget")
        deadline = time.monotonic() + self.settings.request_timeout
        cancelled = self.cancel

        def stop(input_ids: torch.Tensor, scores: object, **kwargs: object) -> torch.Tensor:
            return torch.full(
                (input_ids.shape[0],),
                cancelled.is_set() or time.monotonic() >= deadline,
                device=input_ids.device,
                dtype=torch.bool,
            )

        with torch.inference_mode():
            output = self.model.generate(
                **{key: value.to("cuda:0") for key, value in encoded.items()},
                max_new_tokens=budget,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
                stopping_criteria=[stop],
            )
        if cancelled.is_set() or time.monotonic() >= deadline:
            raise TimeoutError("Generation cancelled or timed out")
        tokens = output[0, length:]
        return self.tokenizer.decode(tokens, skip_special_tokens=True), int(tokens.shape[0])

    def close(self) -> None:
        self.cancel.set()
        self.model = None
        self.tokenizer = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def create_app(runtime: Runtime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            await asyncio.to_thread(runtime.load)
            yield
        finally:
            runtime.close()

    app = FastAPI(lifespan=lifespan)

    @app.get("/v1/models")
    async def models() -> dict[str, object]:
        return {"data": [{"id": runtime.settings.model_name, "object": "model"}]}

    @app.post("/v1/chat/completions")
    async def complete(body: ChatRequest, request: Request) -> dict[str, object]:
        if body.model != runtime.settings.model_name or body.stream:
            raise HTTPException(400, "Unknown model or unsupported streaming request")
        if runtime.lock.locked():
            raise HTTPException(429, "One inference request is already active")
        async with runtime.lock:
            runtime.cancel.clear()
            worker = asyncio.create_task(asyncio.to_thread(runtime.generate, body))
            deadline = time.monotonic() + runtime.settings.request_timeout
            try:
                while not worker.done():
                    if await request.is_disconnected() or time.monotonic() >= deadline:
                        runtime.cancel.set()
                    await asyncio.wait({worker}, timeout=0.05)
                content, count = worker.result()
            except asyncio.CancelledError:
                runtime.cancel.set()
                await asyncio.shield(worker)
                raise
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            except TimeoutError as exc:
                raise HTTPException(504, "Inference deadline exceeded") from exc
            except RuntimeError as exc:
                raise HTTPException(503, "GPU inference failed") from exc
            return {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"completion_tokens": count},
            }

    return app


def main() -> None:
    settings = RuntimeSettings()
    with socket.socket() as listener:
        listener.bind((settings.host, settings.port))
        listener.listen(16)
        port = listener.getsockname()[1]
        settings.runtime_file.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(settings.runtime_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            json.dump(
                {
                    "model_url": f"http://{settings.host}:{port}/v1",
                    "model_name": settings.model_name,
                },
                handle,
            )
        runtime = Runtime(settings)
        try:
            server = uvicorn.Server(
                uvicorn.Config(
                    create_app(runtime),
                    timeout_keep_alive=5,
                    timeout_graceful_shutdown=15,
                    log_level="warning",
                )
            )
            server.run(sockets=[listener])
        finally:
            runtime.close()
            settings.runtime_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
