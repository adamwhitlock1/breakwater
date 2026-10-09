"""Check the OpenRouter development provider before relying on it (free routes, $0).

    BREAKWATER_PROVIDER=openrouter uv run python scripts/day1/check_openrouter.py

Answers, per tier:
  * does `reasoning={"enabled": false}` actually turn reasoning off (reasoning tokens ~0)?
  * does a JSON schema placed in the prompt (free Ultra / Lightning) come back as parseable JSON?
  * latency, and whether rate-limit retries kick in
All calls go through breakwater.llm.Nemotron, so they land in the ledger as provider "openrouter".
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from breakwater.adversary import extract_json  # noqa: E402
from breakwater.llm import Nemotron  # noqa: E402
from breakwater.models import Provider, Tier  # noqa: E402

PUZZLE = [{"role": "user", "content": "A bat and a ball cost $1.10. The bat costs $1.00 more than the ball. "
                                      "How much is the ball? Answer with just the amount."}]
SCHEMA = {"type": "json_schema", "json_schema": {"name": "h", "strict": True, "schema": {
    "type": "object", "properties": {"assumption": {"type": "string"}, "attack": {"type": "string"}},
    "required": ["assumption", "attack"], "additionalProperties": False}}}
ASK = [{"role": "user", "content": "Name one assumption a fast path in a version parser might make, "
                                   "and an input that attacks it."}]


def main() -> int:
    load_dotenv()
    llm = Nemotron(provider=Provider.OPENROUTER, run_id="check-openrouter")
    report: dict = {}
    for tier in Tier:
        row: dict = {}
        for thinking in (False, True):
            t0 = time.perf_counter()
            c = llm.complete(tier, PUZZLE, purpose="check", thinking=thinking, max_tokens=4000, fallback_no_think=False)
            row[f"thinking_{thinking}"] = {"answer": c.text[:40], "out_tokens": c.tokens_out,
                                           "reasoning_tokens": c.reasoning_tokens, "s": round(time.perf_counter() - t0, 1)}
        c = llm.complete(tier, ASK, purpose="check:schema", thinking=False, max_tokens=800, response_format=SCHEMA)
        try:
            parsed = extract_json(c.text)
            row["schema"] = {"model_accepts_response_format": c.model.json_schema, "parses": True,
                             "keys": sorted(parsed)}
        except Exception as e:  # noqa: BLE001
            row["schema"] = {"model_accepts_response_format": c.model.json_schema, "parses": False,
                             "error": str(e)[:120], "text": c.text[:200]}
        report[tier.value] = row
        print(tier.value, json.dumps(row, ensure_ascii=False))
    out = Path("artifacts/day1/openrouter.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
