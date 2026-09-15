import asyncio
import json
import time
from dataclasses import asdict, dataclass

import httpx


class TokenFactoryError(RuntimeError):
    pass


@dataclass
class ModelUsage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    seconds: float = 0.0


class UsageLedger:
    def __init__(self, log_path: str | None = None):
        self.by_model: dict[str, ModelUsage] = {}
        self.by_stage: dict[str, ModelUsage] = {}
        self.log_path = log_path

    def record(self, model: str, stage: str, usage: dict, seconds: float) -> None:
        details = usage.get("completion_tokens_details") or {}
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        reasoning = int(details.get("reasoning_tokens") or 0)
        for key, table in ((model, self.by_model), (stage, self.by_stage)):
            entry = table.setdefault(key, ModelUsage())
            entry.calls += 1
            entry.prompt_tokens += prompt
            entry.completion_tokens += completion
            entry.reasoning_tokens += reasoning
            entry.seconds += seconds
        if self.log_path:
            with open(self.log_path, "a") as fh:
                fh.write(json.dumps({"ts": time.time(), "model": model, "stage": stage, "prompt_tokens": prompt, "completion_tokens": completion, "seconds": round(seconds, 3)}) + "\n")

    @property
    def total_tokens(self) -> int:
        return sum(u.prompt_tokens + u.completion_tokens for u in self.by_model.values())

    def snapshot(self) -> dict:
        return {
            "by_model": {k: {**asdict(v), "seconds": round(v.seconds, 2)} for k, v in self.by_model.items()},
            "by_stage": {k: {**asdict(v), "seconds": round(v.seconds, 2)} for k, v in self.by_stage.items()},
            "total_tokens": self.total_tokens,
        }


@dataclass
class ChatResult:
    model: str
    content: str
    reasoning: str
    finish_reason: str
    usage: dict
    seconds: float


RETRYABLE = {408, 409, 429, 500, 502, 503, 504}


class TokenFactoryClient:
    def __init__(self, api_key: str, base_url: str, ledger: UsageLedger, timeout: float = 240.0, transport: httpx.AsyncBaseTransport | None = None):
        self.ledger = ledger
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def chat(self, model: str, messages: list[dict], *, stage: str, max_tokens: int, temperature: float = 0.2, thinking: bool | None = None, retries: int = 2) -> ChatResult:
        payload: dict = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if thinking is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": thinking}
        last_error = "unknown error"
        for attempt in range(retries + 1):
            started = time.perf_counter()
            try:
                response = await self._http.post("/chat/completions", json=payload)
            except httpx.TransportError as exc:
                last_error = f"{model} transport error: {type(exc).__name__}"
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            seconds = time.perf_counter() - started
            if response.status_code in RETRYABLE and attempt < retries:
                last_error = f"{model} HTTP {response.status_code}"
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if response.status_code >= 400:
                raise TokenFactoryError(f"{model} HTTP {response.status_code}: {response.text[:300]}")
            data = response.json()
            choice = data["choices"][0]
            message = choice.get("message") or {}
            usage = data.get("usage") or {}
            self.ledger.record(model, stage, usage, seconds)
            content = message.get("content") or ""
            finish = choice.get("finish_reason") or ""
            if not content.strip() and finish == "length":
                raise TokenFactoryError(f"{model} ran out of max_tokens={max_tokens} before answering")
            return ChatResult(model, content, message.get("reasoning_content") or message.get("reasoning") or "", finish, usage, seconds)
        raise TokenFactoryError(last_error)
