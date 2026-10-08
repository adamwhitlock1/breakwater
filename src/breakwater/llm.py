"""Nemotron on Token Factory, with the API quirks handled in one place.

Known quirks (see docs/day1-checklist.md for the checks that confirm them):
  * Reasoning is ON by default. `reasoning_effort` is accepted and ignored; use
    `chat_template_kwargs={"enable_thinking": ...}` via extra_body.
  * Thinking can consume all of max_tokens and return empty content, so we keep
    headroom and retry once with thinking off.
  * Some responses inline `<think>...</think>`; strip it before parsing.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from breakwater import ledger
from breakwater.models import Model, Tier, model_for

BASE_URL = os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
_THINK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def strip_think(text: str | None) -> str:
    if not text:
        return ""
    text = _THINK.sub("", text)
    # An unterminated think block means the model ran out of budget mid-thought.
    if "<think>" in text:
        text = text.split("<think>", 1)[0]
    return text.strip()


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

    @property
    def text(self) -> str:
        return self.texts[0] if self.texts else ""


class Nemotron:
    def __init__(self, api_key: str | None = None, base_url: str = BASE_URL, run_id: str | None = None):
        key = api_key or os.environ.get("NEBIUS_API_KEY")
        if not key:
            raise RuntimeError("NEBIUS_API_KEY is not set (copy .env.example to .env)")
        self.client = OpenAI(api_key=key, base_url=base_url)
        self.run_id = run_id

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
    ) -> Completion:
        model = model_for(tier)
        extra: dict[str, Any] = {"chat_template_kwargs": {"enable_thinking": thinking, **(template_kwargs or {})}}
        kwargs: dict[str, Any] = dict(
            model=model.id, messages=messages, max_tokens=max_tokens, n=n,
            temperature=temperature, top_p=top_p, extra_body=extra,
        )
        if response_format:
            kwargs["response_format"] = response_format
        if service_tier:
            kwargs["service_tier"] = service_tier

        t0 = time.perf_counter()
        resp = self.client.chat.completions.create(**kwargs)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        texts = [strip_think(c.message.content) for c in resp.choices]
        usage = resp.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0
        details = getattr(usage, "completion_tokens_details", None)
        reasoning = getattr(details, "reasoning_tokens", 0) or 0
        usd = model.cost(tokens_in, tokens_out)
        ok = any(texts)
        ledger.append(ledger.Entry(
            tier=tier.value, model=model.id, purpose=purpose, tokens_in=tokens_in, tokens_out=tokens_out,
            reasoning_tokens=reasoning, usd=usd, latency_ms=latency_ms, ok=ok, run_id=self.run_id,
        ))
        if not ok and thinking:
            # Thinking ate the budget. Retry once without it rather than silently returning nothing.
            return self.complete(
                tier, messages, purpose=purpose + ":retry-no-think", thinking=False, max_tokens=max_tokens, n=n,
                temperature=temperature, top_p=top_p, response_format=response_format,
                template_kwargs=template_kwargs, service_tier=service_tier,
            )
        return Completion(texts, model, tokens_in, tokens_out, reasoning, usd, latency_ms, resp)
