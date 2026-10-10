import json
from types import SimpleNamespace

from breakwater.adjudicate import INTENDED, LIKELY_BUG, NEEDS_HUMAN, adjudicate, describe, material, quote_found
from breakwater.adversary import Finding
from breakwater.backtest import score_adjudication
from breakwater.models import Tier
from breakwater.repo import Context

CTX = Context(
    repo="r", base="b", head="h", target="pkg.tags:parse_tag", module_path="pkg/tags.py",
    diff="-    interpreters, abis, platforms = tag.split('-')\n+    component_parts = [c.split('.') for c in tag.split('-')]\n",
    module_source='class InvalidTag(ValueError):\n    """Raised when a tag has an empty interpreter, ABI, or platform component."""\n',
    diff_stat="",
)
EXC = Finding("P2|outcome|exc:builtins.ValueError|exc:pkg.tags.InvalidTag|plain", "P2", "outcome", [["-"]],
              {"status": "exc", "exc": "builtins.ValueError"}, {"status": "exc", "exc": "pkg.tags.InvalidTag"})
PICKLE = Finding("P4|base->head load|loads|exc:builtins.AttributeError", "P4", "base->head load", [["x"]],
                 "loads", {"status": "exc", "exc": "builtins.AttributeError"})
MROS = {"head": {"pkg.tags.InvalidTag": ["pkg.tags.InvalidTag", "builtins.ValueError", "builtins.Exception"]},
        "base": {"builtins.ValueError": ["builtins.ValueError", "builtins.Exception"]}}


class Scripted:
    def __init__(self, samples):
        self.samples, self.calls = samples, []

    def complete(self, tier, messages, **kw):
        self.calls.append((tier, kw, messages))
        texts = [json.dumps({"verdicts": s}) for s in self.samples]
        return SimpleNamespace(texts=texts, text=texts[0], usd=0.01)


def v(cid, label, evidence=()):
    return {"id": cid, "label": label, "rationale": f"{label} because", "evidence": list(evidence)}


def test_describe_states_facts_including_exception_relation():
    line = describe(EXC, MROS)
    assert 'Input ["-"]: base raises builtins.ValueError, head raises pkg.tags.InvalidTag' in line
    assert line.endswith("(pkg.tags.InvalidTag is a subclass of builtins.ValueError.)")  # relation, no verdict
    assert describe(PICKLE).endswith("fails to load: builtins.AttributeError.")


def test_quotes_must_occur_in_the_material():
    hay = material("perf: simplify parse_tag", CTX, "")
    assert quote_found("Raised when a tag has an empty interpreter", hay)
    assert quote_found("+    component_parts = [c.split('.') for c in tag.split('-')]", hay)  # diff marker ok
    assert quote_found('"perf: simplify parse_tag"', hay)
    assert not quote_found("Raises InvalidTag for every malformed tag", hay)  # invented
    assert not quote_found("tag", hay)  # too short to mean anything
    assert quote_found("component_parts = [c.split('.')\n    for c in tag.split('-')]", hay)  # re-flowed
    assert quote_found("component_parts = [c.split('.') ... tag.split('-')]", hay)  # elided
    assert not quote_found("component_parts = [c.split('.') ... raise SystemExit(1)", hay)  # elided + invented
    assert quote_found("class InvalidTag(ValueError):\\n    \"\"\"Raised when a tag", hay)  # literal \\n escapes


def test_majority_label_with_verified_evidence_wins():
    quote = "Raised when a tag has an empty interpreter"
    llm = Scripted([[v("C1", INTENDED, [quote]), v("C2", LIKELY_BUG, ["interpreters, abis, platforms = tag.split"])],
                    [v("C1", INTENDED, [quote]), v("C2", LIKELY_BUG, ["component_parts = [c.split"])],
                    [v("C1", LIKELY_BUG, [quote]), v("C2", NEEDS_HUMAN)]])
    res = adjudicate(llm, CTX, [EXC, PICKLE], title="perf: simplify parse_tag", mros=MROS)
    by = res.by_signature()
    assert by[EXC.signature].label == INTENDED and by[EXC.signature].votes == {INTENDED: 2, LIKELY_BUG: 1}
    assert by[PICKLE.signature].label == LIKELY_BUG
    tier, kw, messages = llm.calls[0]
    assert tier is Tier.REASONING and kw["thinking"] and kw["n"] == 3 and not kw["fallback_no_think"]
    assert "None: this PR changes no tests, docs or changelog." in messages[1]["content"]
    assert "pkg.tags.InvalidTag is a subclass of builtins.ValueError" in messages[1]["content"]


def test_unverified_evidence_and_split_votes_abstain():
    fake = "the maintainers said this is fine"
    llm = Scripted([[v("C1", INTENDED, [fake]), v("C2", LIKELY_BUG, ["component_parts = [c.split"])],
                    [v("C1", INTENDED, [fake]), v("C2", INTENDED, ["Raised when a tag has an empty"])],
                    [v("C1", INTENDED, []), v("C2", NEEDS_HUMAN)]])
    by = adjudicate(llm, CTX, [EXC, PICKLE]).by_signature()
    assert by[EXC.signature].label == NEEDS_HUMAN
    assert by[EXC.signature].reason == "evidence not found in the material"
    assert fake in by[EXC.signature].rejected
    assert by[PICKLE.signature].label == NEEDS_HUMAN and by[PICKLE.signature].reason == "no majority"


def test_lost_samples_are_topped_up_once_and_never_create_a_majority():
    llm = Scripted([[v("C1", LIKELY_BUG, ["component_parts = [c.split"])]])  # 1 of 3 samples comes back
    by = adjudicate(llm, CTX, [EXC]).by_signature()
    assert [kw["n"] for _, kw, _ in llm.calls] == [3, 2]  # one top-up for the two lost samples
    assert by[EXC.signature].votes == {LIKELY_BUG: 2} and by[EXC.signature].label == LIKELY_BUG  # 2 of 3

    class Flaky(Scripted):  # the top-up comes back empty too
        def complete(self, tier, messages, **kw):
            res = super().complete(tier, messages, **kw)
            return res if len(self.calls) == 1 else SimpleNamespace(texts=[], text="", usd=0.0)

    by = adjudicate(Flaky([[v("C1", LIKELY_BUG, ["component_parts = [c.split"])]]), CTX, [EXC]).by_signature()
    assert by[EXC.signature].label == NEEDS_HUMAN and by[EXC.signature].reason == "no majority"


def test_no_intent_statement_is_quotable_but_facts_are_not():
    hay = material("t", CTX, "")
    assert quote_found("None: this PR changes no tests, docs or changelog.", hay)
    assert not quote_found(describe(EXC, MROS), hay)


def test_scoring_treats_intended_on_a_known_issue_as_the_dangerous_miss():
    def item(iid, labels):
        return {"id": iid, "known": [{"id": "k", "status": "verified"}],
                "targets": [{"usd": 0.01, "verdicts": [{"label": lab, "known": ["k"]} for lab in labels]
                             + [{"label": NEEDS_HUMAN, "known": []}]}]}

    s = score_adjudication([item("a", [LIKELY_BUG, NEEDS_HUMAN]), item("b", [INTENDED]), item("c", [NEEDS_HUMAN])])
    assert [i["outcome"] for i in s["issues"]] == [LIKELY_BUG, INTENDED, NEEDS_HUMAN]
    assert s["issues_likely_bug"] == 1 and s["issues_intended"] == 1 and s["issues_with_intended_class"] == 1
    assert s["known_classes"] == {LIKELY_BUG: 1, INTENDED: 1, NEEDS_HUMAN: 2}
    assert s["other_classes"][NEEDS_HUMAN] == 3


def test_report_blocks_only_on_likely_bugs():
    from breakwater.adjudicate import Verdict
    from breakwater.adversary import AuditReport, render_markdown

    rep = AuditReport("r", "repo", "b" * 10, "h" * 10, "t", "img", "docker", [], [], [EXC, PICKLE], {}, {})
    unlabelled = render_markdown(rep)
    assert "2 behavior divergence class(es)** (unadjudicated)" in unlabelled
    verdicts = {EXC.signature: Verdict(EXC.signature, INTENDED, {INTENDED: 3}, "docstring says so"),
                PICKLE.signature: Verdict(PICKLE.signature, NEEDS_HUMAN, {NEEDS_HUMAN: 2}, reason="model abstained")}
    md = render_markdown(rep, verdicts)
    assert "**REVIEW: 2 behavior divergence class(es)**: 1 needs-human, 1 intended." in md
    assert md.index("base->head load") < md.index("outcome")  # needs-human sorts above intended
    verdicts[PICKLE.signature] = Verdict(PICKLE.signature, LIKELY_BUG, {LIKELY_BUG: 3}, "pickles break")
    assert "**BLOCK:" in render_markdown(rep, verdicts)


def test_empty_or_partial_samples_are_topped_up_and_schema_is_pinned():
    from breakwater.adjudicate import schema_for

    good = [v("C1", LIKELY_BUG, ["component_parts = [c.split"]), v("C2", LIKELY_BUG, ["component_parts = [c.split"])]
    llm = Scripted([good, [], [v("C1", INTENDED, ["component_parts = [c.split"])]])  # one full, one empty, one half

    class TopUp(Scripted):
        def complete(self, tier, messages, **kw):
            if self.calls:  # the top-up returns full samples
                self.calls.append((tier, kw, messages))
                texts = [json.dumps({"verdicts": good})] * kw["n"]
                return SimpleNamespace(texts=texts, text=texts[0], usd=0.0)
            return super().complete(tier, messages, **kw)

    llm = TopUp(llm.samples)
    by = adjudicate(llm, CTX, [EXC, PICKLE]).by_signature()
    assert [kw["n"] for _, kw, _ in llm.calls] == [3, 1]  # the empty sample was refilled; the half one counted
    assert by[EXC.signature].label == LIKELY_BUG and by[PICKLE.signature].label == LIKELY_BUG
    arr = schema_for(["C1", "C2"])["json_schema"]["schema"]["properties"]["verdicts"]
    assert arr["minItems"] == arr["maxItems"] == 2 and arr["items"]["properties"]["id"]["enum"] == ["C1", "C2"]
    assert arr["items"]["properties"]["rationale"]["maxLength"] == 600
    assert arr["items"]["properties"]["evidence"]["maxItems"] == 3
