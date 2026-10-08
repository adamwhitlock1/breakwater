"""Nemotron on Token Factory, with the API quirks handled in one place.

Quirks confirmed on 2026-10-08 (artifacts/day1/token_factory.json):
  * Reasoning is ON by default. Control it with `chat_template_kwargs={"enable_thinking": ...}`
    via extra_body; with it off, Lightning answered in 5 tokens instead of ~1,400.
  * Reasoning normally arrives in a separate `reasoning_content` field and `content` is clean.
    But if reasoning exhausts max_tokens, finish_reason is "length" and `content` holds the raw,
    untagged reasoning. Such choices are discarded, and if none survive we retry once without
    thinking.
  * `n` is capped at 3 on serverless (non-dedicated) models; larger n is split across calls.
  * `<think>...</think>` is stripped defensively in case a model inlines it.
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
MAX_N = 3  # Token Factory limit for non-dedicated models
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
        fallback_no_think: bool = True,
    ) -> Completion:
        """`fallback_no_think`: if reasoning truncates every choice, retry once with thinking off.
        Right for cheap calls; wrong for planning, where an answer without reasoning is worse than none."""
        model = model_for(tier)
        extra: dict[str, Any] = {"chat_template_kwargs": {"enable_thinking": thinking, **(template_kwargs or {})}}
        kwargs: dict[str, Any] = dict(
            model=model.id, messages=messages, max_tokens=max_tokens,
            temperature=temperature, top_p=top_p, extra_body=extra,
        )
        if response_format:
            kwargs["response_format"] = response_format
        if service_tier:
            kwargs["service_tier"] = service_tier

        texts: list[str] = []
        tokens_in = tokens_out = reasoning = latency_ms = 0
        resp = None
        remaining = n
        while remaining > 0:
            batch = min(remaining, MAX_N)
            remaining -= batch
            t0 = time.perf_counter()
            resp = self.client.chat.completions.create(n=batch, **kwargs)
            call_ms = int((time.perf_counter() - t0) * 1000)
            latency_ms += call_ms
            usage = resp.usage
            c_in = usage.prompt_tokens if usage else 0
            c_out = usage.completion_tokens if usage else 0
            details = getattr(usage, "completion_tokens_details", None)
            c_reason = getattr(details, "reasoning_tokens", 0) or 0
            # A "length" finish with thinking on means content is truncated reasoning, not an answer.
            good = [strip_think(c.message.content) for c in resp.choices
                    if not (thinking and c.finish_reason == "length")]
            texts += [t for t in good if t]
            tokens_in, tokens_out, reasoning = tokens_in + c_in, tokens_out + c_out, reasoning + c_reason
            ledger.append(ledger.Entry(
                tier=tier.value, model=model.id, purpose=purpose, tokens_in=c_in, tokens_out=c_out,
                reasoning_tokens=c_reason, usd=model.cost(c_in, c_out), latency_ms=call_ms, ok=bool(good),
                run_id=self.run_id,
            ))
        usd = model.cost(tokens_in, tokens_out)
        if not texts and thinking and fallback_no_think:
            # Reasoning ate the budget on every choice. Retry once without it rather than return nothing.
            return self.complete(
                tier, messages, purpose=purpose + ":retry-no-think", thinking=False, max_tokens=max_tokens, n=n,
                temperature=temperature, top_p=top_p, response_format=response_format,
                template_kwargs=template_kwargs, service_tier=service_tier,
            )
        return Completion(texts, model, tokens_in, tokens_out, reasoning, usd, latency_ms, resp)
