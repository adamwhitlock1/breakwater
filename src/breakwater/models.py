"""Nemotron tiers and the providers that serve them.

Token Factory is the provider of record: the hackathon requires NVIDIA model calls to go through it,
and only its runs feed published numbers. OpenRouter serves the same Nemotron models (free routes)
and exists for development, so prompt tuning does not spend Token Factory credit.

Select with BREAKWATER_PROVIDER=tokenfactory|openrouter (default tokenfactory).

Token Factory IDs and prices: public catalog (tokenfactory.nebius.com/model-catalog.md, 2026-10-08);
override with BREAKWATER_MODEL_<TIER>. OpenRouter IDs and capabilities: openrouter.ai/api/v1/models
(2026-10-08); override with BREAKWATER_OPENROUTER_MODEL_<TIER>, e.g. a paid route when a free one is
rate-limited.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from enum import StrEnum


class Tier(StrEnum):
    VOLUME = "volume"  # adversary strategy writing, summaries, boilerplate
    PROPOSER = "proposer"  # contract drafting, family variants, candidate patches
    REASONING = "reasoning"  # white-box attack planning, adjudication with abstain


class Provider(StrEnum):
    TOKENFACTORY = "tokenfactory"
    OPENROUTER = "openrouter"


@dataclass(frozen=True)
class ProviderConfig:
    name: Provider
    base_url: str
    key_env: str
    max_n: int  # choices per request; larger n is split across requests
    publishable: bool  # may results produced with this provider be published?


PROVIDERS: dict[Provider, ProviderConfig] = {
    Provider.TOKENFACTORY: ProviderConfig(
        Provider.TOKENFACTORY, os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"),
        "NEBIUS_API_KEY", max_n=3, publishable=True),
    Provider.OPENROUTER: ProviderConfig(
        Provider.OPENROUTER, "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", max_n=1, publishable=False),
}


def active_provider() -> Provider:
    name = os.environ.get("BREAKWATER_PROVIDER", Provider.TOKENFACTORY.value).strip().lower()
    try:
        return Provider(name)
    except ValueError:
        raise ValueError(f"BREAKWATER_PROVIDER={name!r}; expected one of {[p.value for p in Provider]}") from None


@dataclass(frozen=True)
class Model:
    id: str
    usd_per_m_in: float
    usd_per_m_out: float
    context: int
    json_schema: bool = True  # route accepts response_format; otherwise the schema goes in the prompt

    def cost(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in * self.usd_per_m_in + tokens_out * self.usd_per_m_out) / 1_000_000


_TOKENFACTORY: dict[Tier, Model] = {
    Tier.VOLUME: Model("nvidia/Nemotron-3_5-Lightning", 0.06, 0.24, 1_048_576),
    Tier.PROPOSER: Model("nvidia/nemotron-3-super-120b-a12b", 0.30, 0.90, 262_144),
    Tier.REASONING: Model("nvidia/Nemotron-3-Ultra-550b-a55b", 1.00, 3.00, 1_048_576),
}

# Free routes lack response_format for Lightning and Ultra (Super's free route has it).
_OPENROUTER: dict[Tier, Model] = {
    Tier.VOLUME: Model("nvidia/nemotron-3.5-lightning:free", 0, 0, 1_000_000, json_schema=False),
    Tier.PROPOSER: Model("nvidia/nemotron-3-super-120b-a12b:free", 0, 0, 262_144, json_schema=True),
    Tier.REASONING: Model("nvidia/nemotron-3-ultra-550b-a55b:free", 0, 0, 1_000_000, json_schema=False),
}
# Paid OpenRouter routes, for overrides (prices per M tokens; all accept response_format).
_OPENROUTER_PAID: dict[str, Model] = {
    m.id: m for m in (
        Model("nvidia/nemotron-3.5-lightning", 0.049, 0.14, 262_144),
        Model("nvidia/nemotron-3-super-120b-a12b", 0.08, 0.45, 262_144),
        Model("nvidia/nemotron-3-ultra-550b-a55b", 0.50, 2.20, 262_144),
    )
}


def model_for(tier: Tier, provider: Provider | None = None) -> Model:
    provider = provider or active_provider()
    if provider is Provider.OPENROUTER:
        override = os.environ.get(f"BREAKWATER_OPENROUTER_MODEL_{tier.name}")
        if not override:
            return _OPENROUTER[tier]
        if override in _OPENROUTER_PAID:
            return _OPENROUTER_PAID[override]
        free = override.endswith(":free")
        return replace(_OPENROUTER[tier], id=override, json_schema=not free)
    base = _TOKENFACTORY[tier]
    override = os.environ.get(f"BREAKWATER_MODEL_{tier.name}")
    return replace(base, id=override) if override else base
