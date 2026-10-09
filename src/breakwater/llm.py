"""Nemotron through one client, with each provider's API quirks handled in one place.

Token Factory (provider of record; quirks confirmed 2026-10-08, artifacts/day1/token_factory.json):
  * Reasoning is ON by default. Control it with `chat_template_kwargs={"enable_thinking": ...}`
    via extra_body (plus `medium_effort` / `low_effort`); `reasoning_effort` is not reliable.
  * Reasoning normally arrives in a separate `reasoning_content` field and `content` is clean.
    But if reasoning exhausts max_tokens, finish_reason is "length" and `content` holds the raw,
    untagged reasoning. Such choices are discarded, and if none survive we retry once without
    thinking (unless the caller opts out).
  * `n` is capped at 3 on serverless (non-dedicated) models; larger n is split across calls.

OpenRouter (development only; see models.py):
  * Reasoning is controlled with `reasoning={"enabled": bool}` or `{"effort": "low"|"medium"}`;
    the same `thinking` / `template_kwargs` arguments are translated.
  * No `n`: samples are separate requests, run in parallel.
  * Free Lightning and Ultra routes reject `response_format`; the schema is put in the prompt
    instead, and callers already parse JSON leniently.

Both: rate limits, timeouts, connection errors and 5xx are retried with backoff.
`<think>...</think>` is stripped defensively in case a model inlines it.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import openai
from openai import OpenAI

from breakwater import ledger
from breakwater.models import PROVIDERS, Model, Provider, Tier, active_provider, model_for

BASE_URL = PROVIDERS[Provider.TOKENFACTORY].base_url  # kept for scripts that call Token Factory directly
MAX_N = PROVIDERS[Provider.TOKENFACTORY].max_n
RETRY_DELAYS_S = (2, 5, 10, 20, 40, 60)
_RETRYABLE = (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError)
_THINK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


class EmptyResponse(Exception):
    """A 200 response without choices (OpenRouter returns these when an upstream fails)."""


def strip_think(text: str | None) -> str:
    if not text:
        return ""
    text = _THINK.sub("", text)
    # An unterminated think block means the model ran out of budget mid-thought.
    if "<think>" in text:
        text = text.split("<think>", 1)[0]
    return text.strip()


def request_kwargs(provider: Provider, model: Model, messages: list[dict[str, str]], *, thinking: bool,
                   max_tokens: int, temperature: float, top_p: float, response_format: dict | None,
                   template_kwargs: dict | None, service_tier: str | None) -> dict[str, Any]:
    """Translate one logical request into the provider's parameters (pure, for testing)."""
    kw: dict[str, Any] = dict(model=model.id, max_tokens=max_tokens, temperature=temperature, top_p=top_p)
    tk = template_kwargs or {}
    if provider is Provider.TOKENFACTORY:
        kw["extra_body"] = {"chat_template_kwargs": {"enable_thinking": thinking, **tk}}
        if service_tier:
            kw["service_tier"] = service_tier
    else:
        if not thinking:
            reasoning: dict[str, Any] = {"enabled": False}
        elif tk.get("medium_effort"):
            reasoning = {"effort": "medium"}
        elif tk.get("low_effort"):
            reasoning = {"effort": "low"}
        else:
            reasoning = {"enabled": True}
        kw["extra_body"] = {"reasoning": reasoning}
    if response_format and model.json_schema:
        kw["response_format"] = response_format
    elif response_format:
        messages = _schema_in_prompt(messages, response_format)
    kw["messages"] = messages
    return kw


def _schema_in_prompt(messages: list[dict[str, str]], response_format: dict) -> list[dict[str, str]]:
    schema = response_format.get("json_schema", {}).get("schema", response_format)
    note = ("\n\nReply with only a JSON object that matches this JSON Schema, with no other text:\n"
            + json.dumps(schema, separators=(",", ":")))
    out = [dict(m) for m in messages]
    last = next(i for i in range(len(out) - 1, -1, -1) if out[i]["role"] == "user")
    out[last]["content"] = out[last]["content"] + note
    return out


@dataclass
class Completion:
    texts: list[str]
    model: Model
    tokens_in: int
    tokens_out: int
    reasoning_tokens: int
    usd: float
    latency_ms: int
    raw: Any
    provider: Provider = Provider.TOKENFACTORY

    @property
    def text(self) -> str:
        return self.texts[0] if self.texts else ""


class Nemotron:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, run_id: str | None = None,
                 provider: Provider | str | None = None):
        self.provider = Provider(provider) if provider else active_provider()
        cfg = PROVIDERS[self.provider]
        key = api_key or os.environ.get(cfg.key_env)
        if not key:
            raise RuntimeError(f"{cfg.key_env} is not set for provider {self.provider.value} "
                               "(copy .env.example to .env)")
        headers = {"HTTP-Referer": "https://github.com/adamwhitlock1/breakwater", "X-Title": "Breakwater"} \
            if self.provider is Provider.OPENROUTER else None
        # Retries are ours (longer backoff than the SDK's), so the SDK's are off.
        self.client = OpenAI(api_key=key, base_url=base_url or cfg.base_url, max_retries=0, default_headers=headers)
        self.max_n = cfg.max_n
        self.run_id = run_id
        self.on_call: Any = None  # called with each ledger.Entry (the live page's cost meter)
        self.on_start: Any = None  # called with (tier, purpose, requests) before sending (the live "thinking")

    def _create(self, **kw: Any) -> Any:
        for delay in (*RETRY_DELAYS_S, None):
            try:
                resp = self.client.chat.completions.create(**kw)
                if not resp.choices:
                    raise EmptyResponse(str(getattr(resp, "error", "") or "no choices"))
                return resp
            except (*_RETRYABLE, EmptyResponse) as e:
                if delay is None:
                    raise
                retry_after = getattr(getattr(e, "response", None), "headers", {}).get("retry-after")
                wait = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else delay
                time.sleep(min(wait, 120))
        raise AssertionError("unreachable")

    def complete(
        self,
        tier: Tier,
        messages: list[dict[str, str]],
        *,
        purpose: str,
        thinking: bool,
        max_tokens: int = 4096,
        n: int = 1,
        temperature: float = 1.0,
        top_p: float = 0.95,
        response_format: dict | None = None,
        template_kwargs: dict | None = None,
        service_tier: str | None = None,
        fallback_no_think: bool = True,
    ) -> Completion:
        """`fallback_no_think`: if reasoning truncates every choice, retry once with thinking off.
        Right for cheap calls; wrong for planning, where an answer without reasoning is worse than none."""
        model = model_for(tier, self.provider)
        kwargs = request_kwargs(self.provider, model, messages, thinking=thinking, max_tokens=max_tokens,
                                temperature=temperature, top_p=top_p, response_format=response_format,
                                template_kwargs=template_kwargs, service_tier=service_tier)
        batches = [min(self.max_n, n - i) for i in range(0, n, self.max_n)]
        if self.on_start:
            self.on_start(tier.value, purpose, len(batches))

        def one(batch: int) -> tuple[list[str], int, int, int, float, int, Any]:
            t0 = time.perf_counter()
            resp = self._create(n=batch, **kwargs) if batch > 1 else self._create(**kwargs)
            call_ms = int((time.perf_counter() - t0) * 1000)
            usage = resp.usage
            c_in = usage.prompt_tokens if usage else 0
            c_out = usage.completion_tokens if usage else 0
            details = getattr(usage, "completion_tokens_details", None)
            c_reason = getattr(details, "reasoning_tokens", 0) or 0
            reported = getattr(usage, "cost", None) if usage else None  # OpenRouter reports actual cost
            c_usd = float(reported) if isinstance(reported, (int, float)) else model.cost(c_in, c_out)
            # A "length" finish with thinking on means content is truncated reasoning, not an answer.
            good = [strip_think(c.message.content) for c in resp.choices
                    if not (thinking and c.finish_reason == "length")]
            entry = ledger.Entry(
                tier=tier.value, model=model.id, purpose=purpose, tokens_in=c_in, tokens_out=c_out,
                reasoning_tokens=c_reason, usd=c_usd, latency_ms=call_ms, ok=any(good), run_id=self.run_id,
                provider=self.provider.value,
            )
            ledger.append(entry)
            if self.on_call:
                self.on_call(entry)
            return [t for t in good if t], c_in, c_out, c_reason, c_usd, call_ms, resp

        if len(batches) == 1:
            results = [one(batches[0])]
        else:
            with cf.ThreadPoolExecutor(max_workers=min(len(batches), 4)) as pool:
                results = list(pool.map(one, batches))
        texts = [t for r in results for t in r[0]]
        tokens_in, tokens_out, reasoning = (sum(r[i] for r in results) for i in (1, 2, 3))
        usd = sum(r[4] for r in results)
        latency_ms = max(r[5] for r in results)
        if not texts and thinking and fallback_no_think:
            # Reasoning ate the budget on every choice. Retry once without it rather than return nothing.
            return self.complete(
                tier, messages, purpose=purpose + ":retry-no-think", thinking=False, max_tokens=max_tokens, n=n,
                temperature=temperature, top_p=top_p, response_format=response_format,
                template_kwargs=template_kwargs, service_tier=service_tier,
            )
        return Completion(texts, model, tokens_in, tokens_out, reasoning, usd, latency_ms, results[-1][6], self.provider)
