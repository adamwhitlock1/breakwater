"""Nemotron tiers on Nebius Token Factory.

Model IDs and prices come from the public catalog (tokenfactory.nebius.com/model-catalog.md,
checked 2026-10-08). Confirm IDs with `GET /v1/models` (scripts/day1/check_token_factory.py)
and override with BREAKWATER_MODEL_<TIER> if the casing differs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class Tier(StrEnum):
    VOLUME = "volume"  # adversary strategy writing, summaries, boilerplate
    PROPOSER = "proposer"  # contract drafting, candidate patches (stretch: harden mode)
    REASONING = "reasoning"  # white-box attack planning, adjudication with abstain


@dataclass(frozen=True)
class Model:
    id: str
    usd_per_m_in: float
    usd_per_m_out: float
    context: int

    def cost(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in * self.usd_per_m_in + tokens_out * self.usd_per_m_out) / 1_000_000


_DEFAULTS: dict[Tier, Model] = {
    Tier.VOLUME: Model("nvidia/Nemotron-3_5-Lightning", 0.06, 0.24, 1_048_576),
    Tier.PROPOSER: Model("nvidia/nemotron-3-super-120b-a12b", 0.30, 0.90, 262_144),
    Tier.REASONING: Model("nvidia/Nemotron-3-Ultra-550b-a55b", 1.00, 3.00, 1_048_576),
}


def model_for(tier: Tier) -> Model:
    base = _DEFAULTS[tier]
    override = os.environ.get(f"BREAKWATER_MODEL_{tier.name}")
    if override:
        return Model(override, base.usd_per_m_in, base.usd_per_m_out, base.context)
    return base
