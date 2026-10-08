"""Day-1 Token Factory checks. Answers the questions the Breakwater design depends on.

    uv run python scripts/day1/check_token_factory.py                 # core checks, ~$0.05
    uv run python scripts/day1/check_token_factory.py --burst 40      # + rate-limit burst on Lightning
    uv run python scripts/day1/check_token_factory.py --memorization  # + ask Ultra about packaging #1082/#1155

Writes artifacts/day1/token_factory.json. Paste the summary into docs/day1-checklist.md.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from breakwater.llm import BASE_URL, strip_think  # noqa: E402
from breakwater.models import Tier, model_for  # noqa: E402

OUT = Path("artifacts/day1/token_factory.json")
PUZZLE = "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much is the ball? Answer with just the amount."
SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "hypothesis",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"assumption": {"type": "string"}, "attack": {"type": "string"}},
            "required": ["assumption", "attack"],
            "additionalProperties": False,
        },
    },
}

spent = 0.0


def call(client: OpenAI, tier: Tier, prompt: str, *, kwargs: dict | None = None, extra: dict | None = None,
         max_tokens: int = 2048) -> dict[str, Any]:
    """One chat call. Returns content, token counts, headers and errors without raising."""
    global spent
    model = model_for(tier)
    t0 = time.perf_counter()
    try:
        raw = client.chat.completions.with_raw_response.create(
            model=model.id, messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens,
            extra_body=extra or None, **(kwargs or {}),
        )
        resp = raw.parse()
    except Exception as e:  # noqa: BLE001 - we want the error text in the report
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}
    usage = resp.usage
    details = getattr(usage, "completion_tokens_details", None)
    msg = resp.choices[0].message
    cost = model.cost(usage.prompt_tokens, usage.completion_tokens) if usage else 0.0
    spent += cost
    return {
        "ok": True,
        "latency_ms": int((time.perf_counter() - t0) * 1000),
        "choices": len(resp.choices),
        "content": strip_think(msg.content)[:300],
        "raw_has_think_tag": "<think>" in (msg.content or ""),
        "reasoning_field_len": len(getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None) or ""),
        "completion_tokens": usage.completion_tokens if usage else None,
        "reasoning_tokens": getattr(details, "reasoning_tokens", None) if details else None,
        "usd": round(cost, 6),
        "ratelimit_headers": {k: v for k, v in raw.headers.items() if k.lower().startswith("x-ratelimit")},
    }


def think(on: bool, **more: Any) -> dict:
    return {"chat_template_kwargs": {"enable_thinking": on, **more}}


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--burst", type=int, default=0, help="parallel Lightning calls for the rate-limit check")
    ap.add_argument("--memorization", action="store_true")
    args = ap.parse_args()
    if not os.environ.get("NEBIUS_API_KEY"):
        print("NEBIUS_API_KEY is not set; copy .env.example to .env")
        return 2
    client = OpenAI(api_key=os.environ["NEBIUS_API_KEY"], base_url=BASE_URL)
    report: dict[str, Any] = {"base_url": BASE_URL, "ts": time.time()}

    print("1. model IDs")
    ids = sorted(m.id for m in client.models.list())
    nemotron = [i for i in ids if "nemotron" in i.lower()]
    report["nemotron_models"] = nemotron
    report["tier_ids_present"] = {t.value: model_for(t).id in ids for t in Tier}
    print(f"   nemotron models: {nemotron}\n   our tier IDs present: {report['tier_ids_present']}")

    print("2. thinking off/on per tier")
    report["thinking"] = {}
    for tier in Tier:
        off = call(client, tier, PUZZLE, extra=think(False))
        on = call(client, tier, PUZZLE, extra=think(True))
        report["thinking"][tier.value] = {"off": off, "on": on}
        print(f"   {tier.value:9s} off: {off.get('completion_tokens')} tok '{off.get('content', off.get('error'))[:40]}' | "
              f"on: {on.get('completion_tokens')} tok (reasoning {on.get('reasoning_tokens')})")

    print("3. reasoning controls")
    r = report["reasoning_controls"] = {
        "lightning_default_no_kwargs": call(client, Tier.VOLUME, PUZZLE),
        "lightning_reasoning_effort_low": call(client, Tier.VOLUME, PUZZLE, kwargs={"reasoning_effort": "low"}),
        "super_low_effort": call(client, Tier.PROPOSER, PUZZLE, extra=think(True, low_effort=True)),
        "ultra_medium_effort": call(client, Tier.REASONING, PUZZLE, extra=think(True, medium_effort=True)),
    }
    for k, v in r.items():
        print(f"   {k:32s} {v.get('completion_tokens', v.get('error'))} tok")
    print("   (compare with step 2 'on' counts; single samples, so only large gaps mean anything)")

    print("4. n=4, flex tier, json_schema, empty-content repro")
    report["n4"] = call(client, Tier.VOLUME, "Name a fruit.", kwargs={"n": 4, "temperature": 1.0}, extra=think(False))
    report["flex"] = call(client, Tier.VOLUME, "Say OK.", kwargs={"service_tier": "flex"}, extra=think(False))
    report["json_schema"] = {}
    for tier in Tier:
        res = call(client, tier, "Propose one assumption a fast path in a version parser might make, and an input "
                   "that attacks it.", kwargs={"response_format": SCHEMA}, extra=think(False))
        try:
            json.loads(res.get("content", ""))
            res["parses"] = True
        except json.JSONDecodeError:
            res["parses"] = False
        report["json_schema"][tier.value] = res
    report["empty_content_small_budget"] = call(client, Tier.VOLUME, PUZZLE, extra=think(True), max_tokens=48)
    print(f"   n=4 choices: {report['n4'].get('choices', report['n4'].get('error'))}")
    print(f"   flex accepted: {report['flex'].get('ok')} {report['flex'].get('error', '')}")
    print(f"   json_schema parses: { {k: v.get('parses') for k, v in report['json_schema'].items()} }")
    print(f"   thinking on + max_tokens=48 -> content: {report['empty_content_small_budget'].get('content')!r}")

    print("5. responses API (NeMo Gym policy server)")
    try:
        resp = client.responses.create(model=model_for(Tier.VOLUME).id, input="Say OK.",
                                       extra_body=think(False), max_output_tokens=64)
        report["responses_api"] = {"ok": True, "text": (resp.output_text or "")[:80]}
    except Exception as e:  # noqa: BLE001
        report["responses_api"] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}
    print(f"   {report['responses_api']}")

    headers = report["thinking"][Tier.VOLUME.value]["off"].get("ratelimit_headers", {})
    print(f"6. rate-limit headers: {headers or 'none returned'}")

    if args.burst:
        print(f"7. burst: {args.burst} parallel Lightning calls")
        with cf.ThreadPoolExecutor(max_workers=args.burst) as pool:
            results = list(pool.map(lambda _: call(client, Tier.VOLUME, "Say OK.", extra=think(False), max_tokens=8),
                                     range(args.burst)))
        lat = [r["latency_ms"] for r in results if r["ok"]]
        errors = [r["error"][:80] for r in results if not r["ok"]]
        report["burst"] = {"n": args.burst, "ok": len(lat), "errors": errors,
                           "p50_ms": statistics.median(lat) if lat else None, "max_ms": max(lat) if lat else None}
        print(f"   {report['burst']}")

    if args.memorization:
        print("8. memorization probe (contamination risk for the backtest)")
        q = ("What changed in pypa/packaging pull request #1082 (fast path for simple versions), and what bugs did "
             "reviewers find in it? What did PR #1155 fix? If you do not know, say so.")
        report["memorization"] = call(client, Tier.REASONING, q, extra=think(True), max_tokens=4096)
        print("   " + report["memorization"].get("content", report["memorization"].get("error", ""))[:300])

    report["usd_spent"] = round(spent, 4)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nspent ${spent:.4f}; wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
