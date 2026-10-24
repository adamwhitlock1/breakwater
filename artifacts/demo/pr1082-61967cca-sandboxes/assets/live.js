// Live view of a running `breakwater audit`: polls events.jsonl (see src/breakwater/events.py) and
// renders the attack feed, cards as they land, the sandbox gauge and the cost meter.
// Everything is rendered with textContent: model output is untrusted text.
(function () {
  "use strict";

  const TIERS = { reasoning: "Ultra", proposer: "Super", volume: "Lightning" };
  const TIER_ORDER = ["reasoning", "proposer", "volume"];
  const STEPS = [
    ["build", "Build", ["build"]],
    ["plan", "Plan", ["plan"]],
    ["generate", "Strategies", ["generate"]],
    ["search", "Search", ["search"]],
    ["batch", "Probes", ["batch"]],
    ["adjudicate", "Adjudicate", ["adjudicate"]],
    ["tests", "Tests", ["tests"]],
    ["perf", "Perf", ["perf-plan", "perf-screen", "perf-expand", "perf-full"]],
    ["report", "Report", ["report"]],
  ];
  const PHASE_TEXT = {
    build: "Building base and head images (repo at each commit + harness)",
    plan: "Nemotron 3 Ultra reads the diff and plans attacks",
    generate: "Nemotron 3.5 Lightning writes Hypothesis strategies",
    search: "Strategies search base vs head in sandboxes",
    batch: "Deterministic probes on planned inputs, mutations and samples",
    adjudicate: "Ultra labels each divergence (evidence-checked votes)",
    tests: "Writing a pytest per divergence and checking it passes on base, fails on head",
    "perf-plan": "Ultra plans slowdown input families",
    "perf-screen": "Screening every family by instruction count",
    "perf-expand": "Nemotron 3 Super writes variants of the slowest families",
    "perf-full": "Full size ladders, 2 → 4,096",
    report: "Writing the report",
  };
  const LABELS = { "likely-bug": ["bug", "Likely bug"], "needs-human": ["human", "Needs a human"], intended: ["ok", "Intended"] };

  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  };
  const money = (u) => (u >= 0.1 ? "$" + u.toFixed(2) : "$" + u.toFixed(3));
  const num = (n) => Number(n || 0).toLocaleString("en-US");

  const state = { seq: 0, t: 0, done: false, phase: null, tiers: {}, cards: {}, start: Date.now(), inflight: {}, speed: 1 };

  // Requests in flight, shown as "Ultra · plan · thinking 1:12" until their llm event arrives.
  function renderThinking() {
    const box = $("thinking");
    box.textContent = "";
    const now = (Date.now() - state.start) / 1000;
    for (const [key, f] of Object.entries(state.inflight)) {
      if (f.count <= 0) continue;
      const row = el("div", "thinking-row");
      row.appendChild(el("span", "dot"));
      row.appendChild(el("span", null, (TIERS[f.tier] || f.tier) + " · " + key.split("|")[1] + " · thinking " +
        fmtTime(runTime(now - f.since))));
      box.appendChild(row);
    }
  }

  function feed(text, cls, t) {
    const li = el("li", cls);
    li.appendChild(el("span", "t", fmtTime(runTime(t))));
    li.appendChild(el("span", "msg", text));
    const list = $("feed");
    list.insertBefore(li, list.firstChild);
    while (list.children.length > 300) list.removeChild(list.lastChild);
  }

  // During a replay, show the run's recorded time, not the playback time.
  function runTime(t) { return (t || 0) * (state.speed || 1); }

  function fmtTime(t) {
    t = Math.max(0, Math.round(t || 0));
    return String(Math.floor(t / 60)).padStart(2, "0") + ":" + String(t % 60).padStart(2, "0");
  }

  function setPhase(name) {
    state.phase = name;
    const idx = STEPS.findIndex((s) => s[2].includes(name));
    document.querySelectorAll("#steps li").forEach((li, i) => {
      li.className = i < idx ? "done" : i === idx ? "now" : "";
    });
    $("phase-text").textContent = PHASE_TEXT[name] || name;
  }

  function renderCost() {
    const box = $("cost");
    box.textContent = "";
    let total = 0;
    for (const tier of TIER_ORDER) {
      const t = state.tiers[tier];
      if (!t) continue;
      total += t.usd;
      const row = el("div", "meter-row");
      row.appendChild(el("span", "meter-name", TIERS[tier] || tier));
      row.appendChild(el("span", "meter-sub", num(t.calls) + " calls · " + num(t.out) + " out tok"));
      row.appendChild(el("span", "meter-val", money(t.usd)));
      box.appendChild(row);
    }
    $("cost-total").textContent = money(total);
  }

  function card(ev) {
    const c = el("article", "card card-none fresh");
    const head = el("header");
    head.appendChild(el("span", "probe", ev.probe));
    head.appendChild(el("h3", null, ev.title));
    const chip = el("span", "chip none", "Unlabelled");
    head.appendChild(chip);
    c.appendChild(head);
    for (const [k, v] of ev.inputs) {
      const io = el("div", "io");
      io.appendChild(el("span", "k", k));
      io.appendChild(el("code", null, v));
      c.appendChild(io);
    }
    const sides = el("div", "sides");
    for (const [k, v, exc] of [["base", ev.base, ev.base_exc], ["head", ev.head, ev.head_exc]]) {
      const s = el("div", "side " + k);
      if (exc) s.title = exc;
      s.appendChild(el("span", "k", k));
      s.appendChild(document.createTextNode(v));
      sides.appendChild(s);
    }
    c.appendChild(sides);
    const why = el("p", "facts", "");
    c.appendChild(why);
    c.appendChild(el("p", "found", "Found by: " + ev.found_by));
    state.cards[ev.signature] = { node: c, chip: chip, why: why };
    $("cards").insertBefore(c, $("cards").firstChild);
    $("card-count").textContent = String(Object.keys(state.cards).length);
    setTimeout(() => c.classList.remove("fresh"), 1200);
  }

  function label(ev) {
    const entry = state.cards[ev.signature];
    if (!entry) return;
    const [cls, text] = LABELS[ev.label] || ["none", ev.label];
    entry.chip.className = "chip " + cls;
    entry.chip.textContent = text;
    entry.node.className = "card card-" + ev.label;
    if (ev.rationale) entry.why.textContent = ev.rationale;
  }

  function family(ev) {
    const row = el("li");
    const r = ev.screen_ratio;
    const bar = el("span", "fam-bar " + (r > 1.02 ? "slow" : r < 0.98 ? "fast" : ""));
    bar.style.width = r ? Math.min(100, (r / 3) * 100).toFixed(1) + "%" : "0%";
    const track = el("span", "fam-track");
    track.appendChild(bar);
    row.appendChild(el("code", "fam-id", ev.id));
    row.appendChild(el("span", "fam-name", ev.family));
    row.appendChild(track);
    row.appendChild(el("span", "fam-val", r ? r.toFixed(2) + "×" : ev.error ? "error" : "n/a"));
    if (ev.valid_fraction !== null && ev.valid_fraction < 0.5) row.classList.add("invalid");
    $("families").appendChild(row);
  }

  function handle(ev) {
    state.t = ev.t;
    switch (ev.kind) {
      case "run":
        $("title").textContent = ev.title || "Audit of " + ev.target;
        $("meta").textContent = ev.repo.replace("https://github.com/", "") + " · " + ev.base.slice(0, 10) +
          " → " + ev.head.slice(0, 10) + " · " + ev.target + " · run " + ev.run_id;
        state.provider = ev.provider === "tokenfactory" ? "Nebius Token Factory" : ev.provider;
        $("cost-title").textContent = "Nemotron on " + (ev.provider === "tokenfactory" ? "Token Factory" : ev.provider);
        if (ev.provider !== "tokenfactory") {
          $("dev").hidden = false;
          $("dev").textContent = "Development run (provider: " + ev.provider + "). Not from Nebius Token Factory.";
        }
        break;
      case "replay":
        $("clock").insertAdjacentElement("afterend", el("span", "replay-badge", "replay ×" + ev.speed + " of run " + ev.run_id));
        state.speed = ev.speed;
        break;
      case "phase":
        setPhase(ev.name);
        feed("▶ " + (PHASE_TEXT[ev.name] || ev.name), "phase", ev.t);
        break;
      case "llm-start": {
        const key = ev.tier + "|" + ev.purpose;
        const f = (state.inflight[key] = state.inflight[key] || { tier: ev.tier, count: 0, since: ev.t });
        if (f.count <= 0) f.since = ev.t;
        f.count += Math.max(1, ev.requests || 1);
        renderThinking();
        break;
      }
      case "llm": {
        const key = ev.tier + "|" + ev.purpose;
        if (state.inflight[key]) state.inflight[key].count -= 1;  // one llm event per request
        renderThinking();
        const t = (state.tiers[ev.tier] = state.tiers[ev.tier] || { usd: 0, calls: 0, out: 0 });
        t.usd += ev.usd; t.calls += 1; t.out += ev.tokens_out;
        renderCost();
        const think = ev.reasoning_tokens ? " (" + num(ev.reasoning_tokens) + " reasoning)" : "";
        feed((TIERS[ev.tier] || ev.tier) + " · " + ev.purpose + " · " + num(ev.tokens_out) + " tokens" + think +
          " · " + money(ev.usd) + " · " + (ev.latency_ms / 1000).toFixed(1) + "s", "llm " + ev.tier, ev.t);
        break;
      }
      case "image":
        if ($("sb-image")) $("sb-image").textContent = (ev.backend === "contree" ? "Token Factory Sandboxes image " : "image ") + ev.image;
        break;
      case "sandbox":
        $("sb-now").textContent = String(ev.in_flight);
        $("sb-runs").textContent = num(ev.runs);
        if (ev.cpu_s !== undefined) $("sb-cpu").textContent = ev.cpu_s.toFixed(1) + "s";
        if (ev.usd !== undefined && $("sb-usd")) $("sb-usd").textContent = money(ev.usd);
        $("sb-gauge").style.width = Math.min(100, ev.in_flight * 12.5) + "%";
        break;
      case "plan":
        for (const a of ev.attacks) {
          feed(a.id + " · " + a.assumption, "plan", ev.t);
          const li = el("li");
          const h = el("div", "attack-head");
          h.appendChild(el("code", null, a.id));
          h.appendChild(el("strong", null, a.assumption));
          li.appendChild(h);
          li.appendChild(el("p", "muted small", a.why_it_breaks));
          $("attacks").appendChild(li);
        }
        break;
      case "strategies": {
        const valid = ev.jobs.filter((j) => j.valid).length;
        feed("Lightning wrote " + ev.jobs.length + " strategies (" + valid + " pass the hygiene check)", "llm volume", ev.t);
        const first = ev.jobs.find((j) => j.valid);
        if (first) $("strategy").textContent = "# " + first.id + "\n" + first.source;
        break;
      }
      case "strategy":
        feed(ev.id + " searched " + num(ev.examples) + " inputs" + (ev.findings ? " → " + ev.findings + " hit(s)" : "") +
          (ev.error ? " · error" : ""), ev.findings ? "hit" : "", ev.t);
        break;
      case "finding":
        card(ev);
        feed("New divergence class: " + ev.title + " · " + ev.inputs.map((x) => x[1]).join(" vs "), "hit", ev.t);
        break;
      case "batch":
        feed("Probed " + num(ev.inputs) + " inputs (" + num(ev.mutations) + " hostile mutations); " + ev.classes +
          " classes so far", "", ev.t);
        break;
      case "verdict":
        label(ev);
        break;
      case "tests":
        feed(ev.verified + " of " + ev.generated + " regression tests verified (pass on base, fail on head)" +
          (ev.skipped ? "; " + ev.skipped + " class(es) without a test" : ""), "hit", ev.t);
        break;
      case "family":
        family(ev);
        break;
      case "measured": {
        const rs = ev.ladder.filter((p) => p.judged !== false).map((p) => p.ratio).filter((r) => r);
        const span = rs.length ? Math.min(...rs).toFixed(2) + "×–" + Math.max(...rs).toFixed(2) + "×" : "n/a";
        feed("Measured " + ev.family_id + ": " + ev.verdict + " (" + span + " head/base instructions)",
          ev.verdict === "slower" || ev.verdict === "complexity-regression" ? "hit" : "", ev.t);
        break;
      }
      case "error":
        feed("Error: " + ev.message, "err", ev.t);
        break;
      case "done": {
        state.done = true;
        setPhase("report");
        document.querySelectorAll("#steps li").forEach((li) => (li.className = "done"));
        $("phase-text").textContent = "Done in " + fmtTime(runTime(ev.t));
        $("clock").textContent = fmtTime(runTime(ev.t));
        const box = $("verdict");
        box.hidden = false;
        box.className = "verdict-box " + ev.verdict.toLowerCase();
        box.textContent = "";
        box.appendChild(el("span", "verdict " + ev.verdict.toLowerCase(), ev.verdict));
        box.appendChild(el("p", null, ev.classes + " divergence class(es) · " + money(ev.usd) + " on " +
          (state.provider || "Nebius Token Factory")));
        const a = el("a", "button", "Open the report →");
        a.href = ev.report;
        box.appendChild(a);
        break;
      }
    }
  }

  async function poll() {
    try {
      const res = await fetch("events.jsonl", { cache: "no-store" });
      if (res.ok) {
        const lines = (await res.text()).split("\n");
        for (const line of lines) {
          if (!line.trim()) continue;
          let ev;
          try { ev = JSON.parse(line); } catch (e) { continue; } // a line still being written
          if (ev.seq <= state.seq) continue;
          state.seq = ev.seq;
          handle(ev);
        }
        // Joining a run already in progress: the clock follows the run, not the page load.
        state.start = Math.min(state.start, Date.now() - state.t * 1000);
      }
    } catch (e) { /* server restarting; try again */ }
    if (!state.done) setTimeout(poll, 800);
  }

  setInterval(() => {
    if (state.done) return;
    $("clock").textContent = fmtTime(runTime((Date.now() - state.start) / 1000));
    renderThinking();
  }, 500);
  const steps = $("steps");
  for (const s of STEPS) steps.appendChild(el("li", null, s[1]));
  poll();
})();
