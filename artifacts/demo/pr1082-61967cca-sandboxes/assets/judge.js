// Judge box: runs real pypa/packaging versions in the browser with Pyodide and classifies differences
// with Breakwater's own compare.py. Pyodide loads from jsDelivr only after the visitor clicks Start.
(function () {
  "use strict";
  const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.27.2/full/";
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  };
  const meta = JSON.parse($("judge-meta").textContent);  // versions (no sources), known classes
  let py = null;

  function status(text) { $("judge-status").textContent = text; }

  async function start() {
    $("judge-start").disabled = true;
    status("Downloading Python (Pyodide, about 10 MB, from cdn.jsdelivr.net)…");
    await new Promise((ok, fail) => {
      const s = document.createElement("script");
      s.src = PYODIDE + "pyodide.js";
      s.onload = ok;
      s.onerror = () => fail(new Error("could not load Pyodide"));
      document.head.appendChild(s);
    });
    py = await loadPyodide({ indexURL: PYODIDE });
    status("Loading four versions of pypa/packaging…");
    const [bundle, judgeSrc, compareSrc] = await Promise.all([
      fetch("data/judge.json").then((r) => r.json()),
      fetch("assets/judge.py").then((r) => r.text()),
      fetch("assets/compare.py").then((r) => r.text()),
    ]);
    py.FS.mkdirTree("/judge_lib");
    py.FS.writeFile("/judge_lib/judge.py", judgeSrc);
    py.FS.writeFile("/judge_lib/compare.py", compareSrc);
    py.globals.set("bundle_json", JSON.stringify(bundle.versions));
    py.runPython("import sys, json; sys.path.insert(0, '/judge_lib'); import judge; judge.load(json.loads(bundle_json))");
    status("Ready. Python " + py.runPython("import sys; sys.version.split()[0]") + " is running in this page.");
    $("judge-form").hidden = false;
    $("judge-start").hidden = true;
    evaluate($("judge-input").value);
  }

  function describe(o) {
    if (o.status === "exc") return ["raises " + o.exc.split(".").pop(), o.message];
    const rel = JSON.stringify(o.obs["attr:release"]);
    return ["returns " + o.obs["str"], "release " + rel + " · public " + JSON.stringify(o.obs["attr:public"])];
  }

  function evaluate(text) {
    if (!py) return;
    py.globals.set("judge_input", text);
    const res = JSON.parse(py.runPython("json.dumps(judge.run(judge_input))"));
    const body = $("judge-rows");
    body.textContent = "";
    for (const v of meta.versions) {
      const o = res.outcomes[v.key];
      const [head, sub] = describe(o);
      const diffs = res.diffs[v.key] || [];
      const tr = el("tr", diffs.length ? "diff" : "");
      const who = el("td");
      who.appendChild(el("strong", null, v.label));
      const a = el("a", "small", v.commit.slice(0, 10));
      a.href = meta.repo + "/commit/" + v.commit;
      who.appendChild(el("br"));
      who.appendChild(a);
      tr.appendChild(who);
      const res_ = el("td", "judge-out");
      res_.appendChild(el("code", "bidi", head));
      if (sub) res_.appendChild(el("small", null, sub));
      tr.appendChild(res_);
      const d = el("td");
      if (v.key === meta.versions[0].key) d.appendChild(el("span", "muted small", "reference"));
      else if (!diffs.length) d.appendChild(el("span", "chip ok sm", "same as base"));
      for (const x of diffs) {
        const known = (meta.known[v.key] || {})[x.signature];
        d.appendChild(el("span", "chip bug sm", x.probe + " " + (x.probe === "P1" ? x.detail + " changed" : "outcome changed")));
        const p = el("p", "small");
        p.appendChild(el("code", null, x.signature));
        if (known) {
          p.appendChild(document.createTextNode(" · Breakwater found this class; "));
          const link = el("a", null, known.label === "Unlabelled" ? "see the card"
            : "Ultra labelled it " + known.label.toLowerCase());
          link.href = known.href;
          p.appendChild(link);
        }
        d.appendChild(p);
      }
      tr.appendChild(d);
      body.appendChild(tr);
    }
  }

  $("judge-start").addEventListener("click", () => start().catch((e) => status("Error: " + e.message)));
  $("judge-form").addEventListener("submit", (e) => { e.preventDefault(); evaluate($("judge-input").value); });
  $("judge-input").addEventListener("input", () => evaluate($("judge-input").value));
  document.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
    const v = b.dataset.preset === "HUGE" ? "1" + "0".repeat(4400) : b.dataset.preset;
    $("judge-input").value = v;
    evaluate(v);
  }));
})();
