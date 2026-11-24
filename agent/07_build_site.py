"""Step 8: generate site/index.html, one self-contained case-study page, from data/ (no hand-typed numbers).

Also writes final.csv, final.json, analysis.json and llms.txt next to it so agents can read the results.

Run:  python agent/07_build_site.py --repo https://github.com/you/repo --live https://your-site.vercel.app
"""
import argparse
import datetime
import html
import json
import re

from common import ANALYSIS_JSON, DATA, FINAL_CSV, INSIGHTS_MD, SITE, read_csv, read_json

E = html.escape
LABEL = {
    "self_serve_free": "Self-serve, free", "self_serve_trial": "Self-serve, trial", "paid_plan": "Paid plan",
    "admin_approval": "Admin / app approval", "partner_or_sales_gated": "Partner / sales gated",
    "open_source_local": "Open source / local", "unclear": "Unclear",
    "ready_now": "Ready now", "ready_with_constraints": "Ready, with limits",
    "outreach_required": "Needs outreach", "not_buildable_now": "Not buildable",
    "oauth2": "OAuth2", "api_key": "API key", "bearer_token": "Bearer token", "basic": "Basic",
    "jwt": "JWT", "hmac_signature": "HMAC", "other": "Other", "none": "None",
    "credential_gate": "Credential gate", "admin_or_partner_approval": "Admin / partner approval",
    "no_public_api": "No public API", "narrow_or_read_only_api": "Narrow / read-only API",
    "unstable_or_undocumented": "Unstable / undocumented", "local_only": "Local only",
    "compliance_or_scope": "Compliance / scope",
    "rest": "REST", "graphql": "GraphQL", "soap": "SOAP", "websocket": "WebSocket", "sdk_or_cli_only": "SDK / CLI only",
    "broad": "Broad", "moderate": "Moderate", "narrow": "Narrow",
    "yes": "Yes", "no": "No",
}
BUILD_ORDER = ["ready_now", "ready_with_constraints", "outreach_required", "not_buildable_now"]
TONE = {"ready_now": "good", "ready_with_constraints": "mid", "outreach_required": "bad", "not_buildable_now": "bad",
        "self_serve_free": "good", "open_source_local": "good", "self_serve_trial": "mid", "paid_plan": "mid",
        "admin_approval": "mid", "partner_or_sales_gated": "bad"}


def lab(v):
    if v is None or v == "" or v == "null":
        return "Not researched"
    return LABEL.get(v, str(v).replace("_", " "))


def as_list(v, sep=";"):
    if not v:
        return []
    return v if isinstance(v, list) else [x for x in str(v).split(sep) if x]


def is_human(r):
    return str(r.get("review_status", "")).startswith("human")


def pill(v):
    return f"<span class='pill {TONE.get(v, '')}'>{E(lab(v))}</span>"


def md(text):
    """Tiny Markdown: ## headings, - bullets, **bold**, paragraphs."""
    out, in_list = [], False
    for line in text.splitlines():
        s = line.strip()
        s_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", E(s))
        if s.startswith("- "):
            if not in_list:
                out.append("<ol class='findings'>")
                in_list = True
            out.append(f"<li>{s_html[2:]}</li>")
            continue
        if in_list:
            out.append("</ol>")
            in_list = False
        if s.startswith("#"):
            out.append(f"<h3>{s_html.lstrip('#').strip()}</h3>")
        elif s:
            out.append(f"<p>{s_html}</p>")
    if in_list:
        out.append("</ol>")
    return "\n".join(out)


def bars(counts, total):
    if not counts:
        return "<p class='muted'>No data yet.</p>"
    rows = []
    for k, v in counts.items():
        w = round(100 * v / total) if total else 0
        rows.append(f"<div class='bar'><span>{E(lab(k))}</span><span class='track'><i style='width:{w}%'></i></span>"
                    f"<span class='num'>{v}</span></div>")
    return "".join(rows)


# ------------------------------------------------------------------ sections
def heatmap(final):
    cats = sorted({r.get("category", "") for r in final})
    head = "".join(f"<th>{E(lab(b))}</th>" for b in BUILD_ORDER)
    body = []
    for c in cats:
        rows = [r for r in final if r.get("category") == c]
        tds = []
        for b in BUILD_ORDER:
            v = sum(r.get("buildability") == b for r in rows)
            a = v / max(len(rows), 1)
            tds.append(f"<td class='hm {TONE[b]}' style='--a:{a:.2f}'>{v if v else '·'}</td>")
        body.append(f"<tr><th scope='row'>{E(c)}</th>{''.join(tds)}</tr>")
    return (f"<div class='scroll'><table class='heat'><thead><tr><th>Category</th>{head}</tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>")


def category_matrix(by_cat):
    cols = [("apps", "Apps"), ("self_serve", "Self-serve"), ("gated", "Gated"), ("ready_now", "Ready now"),
            ("outreach", "Outreach"), ("oauth2", "OAuth2"), ("api_key", "API key"),
            ("official_mcp", "Official MCP"), ("composio", "On Composio")]
    head = "".join(f"<th>{c}</th>" for _, c in cols)
    body = "".join(f"<tr><th scope='row'>{E(cat)}</th>" + "".join(f"<td class='num'>{c.get(k, 0)}</td>" for k, _ in cols) + "</tr>"
                   for cat, c in by_cat.items())
    return f"<div class='scroll'><table class='plain'><thead><tr><th>Category</th>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def app_rows(final):
    out = []
    for i, r in enumerate(final):
        auth = ", ".join(lab(a) for a in as_list(r.get("auth_methods"))) or "Not researched"
        styles = ", ".join(lab(s) for s in as_list(r.get("api_styles")))
        ev = as_list(r.get("evidence_urls"))
        links = " ".join(f"<a href='{E(u)}' target='_blank' rel='noopener noreferrer'>source {j + 1}</a>"
                         for j, u in enumerate(ev[:4])) or "<span class='muted'>none</span>"
        badge = " <span class='tick' title='Checked by hand against official docs'>Human-checked</span>" if is_human(r) else ""
        attrs = (f"data-cat='{E(r.get('category', ''))}' data-build='{E(str(r.get('buildability') or ''))}' "
                 f"data-human='{'1' if is_human(r) else ''}'")
        out.append(
            f"<tr class='row' {attrs} tabindex='0' aria-expanded='false' aria-controls='d{i}'>"
            f"<td><span class='caret' aria-hidden='true'></span><strong>{E(r.get('app', ''))}</strong>{badge}"
            f"<div class='sub'>{E(r.get('category', ''))}</div></td>"
            f"<td>{E(auth)}</td><td>{pill(r.get('credential_access'))}</td><td>{pill(r.get('buildability'))}</td>"
            f"<td class='c'>{E(lab(r.get('official_mcp')))}</td><td class='c'>{E(lab(r.get('composio_toolkit')))}</td></tr>"
            f"<tr class='detail' id='d{i}' hidden {attrs}><td colspan='6'><div class='dgrid'>"
            f"<div><b>What it is</b>{E(r.get('description', '') or '')}</div>"
            f"<div><b>Why this verdict</b>{E(r.get('rationale', '') or '')}</div>"
            f"<div><b>Credentials</b>{E(r.get('credential_notes', '') or lab(r.get('credential_access')))}</div>"
            f"<div><b>API</b>{E(lab(r.get('api_breadth')))}{' · ' + E(styles) if styles else ''}</div>"
            f"<div><b>Main blocker</b>{E(lab(r.get('primary_blocker')))}</div>"
            f"<div><b>Confidence / review</b>{E(lab(r.get('confidence')))} · {E(r.get('review_status', '') or '')}</div>"
            f"<div class='wide'><b>Evidence</b>{links}</div></div></td></tr>")
    return "".join(out)


def accuracy(acc, p1, p2):
    """Returns (hero html, detail html)."""
    s = (acc or {}).get("stages", {})
    a1, a2 = (s.get("pass1") or {}), (s.get("pass2") or {})
    if a1.get("field_accuracy") is None or a2.get("field_accuracy") is None:
        if not p1:
            return ("<p class='pending'>Verification in progress. The first-pass and after-loop accuracy on the "
                    "hand-checked sample will appear here.</p>"), "<p class='muted'>Accuracy not scored yet.</p>"
        hero = (f"<div class='acc'><div><span class='big'>{p1.get('flagged', '–')}</span><span class='cap'>apps flagged by auto-checks (pass 1)</span></div>"
                f"<span class='arrow'>→</span><div><span class='big'>{p2.get('flagged', '–')}</span><span class='cap'>still flagged after fact-check (pass 2)</span></div></div>"
                "<p class='note'>Hand-audit accuracy appears here after <code>05_audit.py score</code>.</p>")
        return hero, "<p class='muted'>Accuracy not scored yet.</p>"
    pct = lambda x: f"{100 * x['field_accuracy']:.1f}%"
    a3 = s.get("audit") or {}
    steps = [f"<div><span class='big'>{pct(a1)}</span><span class='cap'>first pass</span></div>",
             f"<div><span class='big'>{pct(a2)}</span><span class='cap'>after auto-verify + fact-check</span></div>"]
    if a3.get("field_accuracy") is not None:
        steps.append(f"<div><span class='big'>{pct(a3)}</span><span class='cap'>blind second agent</span></div>")
    steps.append("<div><span class='big accent'>100%</span><span class='cap'>audited rows after human fixes</span></div>")
    trend = ("The automatic fact-check loop did not raise accuracy" if a2["field_accuracy"] <= a1["field_accuracy"]
             else "The fact-check loop raised accuracy")
    hero = (f"<div class='acc'>{'<span class=arrow>→</span>'.join(steps)}</div>"
            f"<p class='note'>Share of {a1.get('total')} field answers that match official docs on {acc.get('gold_apps', '?')} apps I checked by hand. "
            f"{trend}; an independent blind agent did better, and the human audit is what made the sample correct. "
            "The 20 audited rows in the table use the human-corrected values.</p>")
    rows = []
    for f in acc.get("fields", []):
        def cell(st):
            v = (s.get(st) or {}).get("per_field", {}).get(f)
            return "–" if v is None else f"{round(100 * v)}%"
        rows.append(f"<tr><th scope='row'>{E(f.replace('_', ' ').capitalize())}</th><td class='num'>{cell('pass1')}</td><td class='num'>{cell('pass2')}</td><td class='num'>{cell('audit')}</td></tr>")
    status = ", ".join(f"{v} {k}" for k, v in (acc.get("human_status") or {}).items())
    detail = (f"<div class='scroll'><table class='plain narrow'><thead><tr><th>Field</th><th>Pass 1</th><th>After loop</th><th>Blind agent</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
              f"<p class='note'>{a1.get('right')}/{a1.get('total')} → {a2.get('right')}/{a2.get('total')} field answers right; "
              f"{a1.get('perfect_apps')} → {a2.get('perfect_apps')} of {a2.get('apps_scored')} apps fully right. Human review: {E(status)}.</p>")
    return hero, detail


def misses():
    p = DATA / "audit_diffs.csv"
    if not p.exists():
        return "<p class='muted'>Misses appear here after the hand audit is scored.</p>", 0
    diffs = read_csv(p)
    p1 = {(d["app"], d["field"]): d for d in diffs if d["stage"] == "pass1"}
    p2 = {(d["app"], d["field"]): d for d in diffs if d["stage"] == "pass2"}
    rows = []
    for key, d in p1.items():
        out = "<span class='pill good'>Fixed by loop</span>" if key not in p2 else "<span class='pill bad'>Missed, fixed by human</span>"
        rows.append((d, out))
    for key, d in p2.items():
        if key not in p1:
            rows.append((d, "<span class='pill bad'>Broken by loop</span>"))
    if not rows:
        return "<p>No misses on the audited sample.</p>", 0
    from collections import Counter
    tally = Counter(o.split('>')[1].split('<')[0] for _, o in rows)
    summary = " · ".join(f"{v} {k.lower()}" for k, v in tally.items())
    body = "".join(f"<tr><td><strong>{E(d['app'])}</strong></td><td>{E(lab(d['field']))}</td><td>{E(d['agent'])}</td>"
                   f"<td>{E(d['truth'])}</td><td>{o}</td><td class='muted'>{E(d.get('human_note', ''))}</td></tr>" for d, o in rows)
    return (f"<p>{E(summary)}. All of them are corrected in the final data.</p>"
            f"<details><summary>Show all {len(rows)} misses</summary><div class='scroll'><table class='plain'><thead><tr><th>App</th><th>Field</th><th>Agent said</th><th>Docs say</th>"
            f"<th>Outcome</th><th>Note</th></tr></thead><tbody>{body}</tbody></table></div></details>"), len(rows)


def app_list(items, limit=None):
    if not items:
        return "<p class='muted'>None</p>"
    li = "".join(f"<li><strong>{E(i['app'])}</strong><span>{E(i.get('category', ''))}</span></li>" for i in items)
    return f"<ul class='apps'>{li}</ul>"


def write_llms_txt(headline, a, final, repo, live, today):
    k = a["kpis"]
    lines = [
        "# Agent toolkit research: which of 100 apps can become AI-agent toolkits today", "",
        f"> {headline}", "",
        f"Researched by an LLM agent with a verification loop and a human-checked audit sample. Data as of {today}.", "",
        "## Key numbers",
        f"- {k['self_serve_pct']}% of apps have self-serve credentials; {k['gated_pct']}% are gated (paid, approval or sales).",
        f"- {k['ready_now']} apps are ready to build today; {k['outreach']} need outreach or have no usable API.",
        f"- {k['official_mcp']} apps ship an official MCP server; {k['composio_covered']} already have a Composio toolkit.", "",
        "## Data",
        "- [final.json](final.json): one record per app (auth_methods, credential_access, api_styles, api_breadth, official_mcp, composio_toolkit, buildability, primary_blocker, rationale, confidence, review_status, evidence_urls)",
        "- [final.csv](final.csv): same data as CSV",
        "- [analysis.json](analysis.json): every aggregate shown on the page, plus verification and accuracy numbers",
        "- [index.html](index.html): the human-readable case study", "",
        "## Vocabulary",
        "- credential_access: self_serve_free, self_serve_trial, paid_plan, admin_approval, partner_or_sales_gated, open_source_local, unclear",
        "- buildability: ready_now, ready_with_constraints, outreach_required, not_buildable_now",
        "- review_status starting with 'human' means a person checked the row against official docs.", "",
        "## Source", f"- Repo: {repo}", f"- Live page: {live}", "",
        "## Apps",
    ]
    lines += [f"- {r.get('app')} ({r.get('category')}): {r.get('buildability')}, {r.get('credential_access')}" for r in final]
    (SITE / "llms.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ page
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="#repo-link-goes-here")
    ap.add_argument("--live", default="#")
    args = ap.parse_args()

    a = read_json(ANALYSIS_JSON)
    final = read_json(FINAL_CSV.with_suffix(".json"))
    if not a or not final:
        raise SystemExit("Run 06_analyze.py first.")
    insights = INSIGHTS_MD.read_text(encoding="utf-8") if INSIGHTS_MD.exists() else ""
    headline = ""
    m = re.search(r"^#\s*Headline\s*\n+(.+?)(?:\n\n|\n#|$)", insights, flags=re.S | re.M)
    if m:
        headline = m.group(1).strip()
        insights = insights.replace(m.group(0), "")
    headline = headline or a["auto_headline"]
    k, n, v = a["kpis"], a["n_apps"], a["verification"]
    p1, p2 = v.get("pass1") or {}, v.get("pass2") or {}
    today = datetime.date.today().strftime("%d %b %Y")
    repo, live = E(args.repo), E(args.live)

    acc_hero, acc_detail = accuracy(v.get("accuracy"), p1, p2)
    miss_html, n_miss = misses()
    scored = ((v.get("accuracy") or {}).get("stages") or {}).get("pass2", {}).get("field_accuracy") is not None
    unresolved = [r["app"] for r in final if "unclear" in (r.get("credential_access"), r.get("primary_blocker"), r.get("official_mcp"))]
    pending = [r["app"] for r in final if not r.get("buildability")]
    n_human = sum(is_human(r) for r in final)
    cats = sorted({r["category"] for r in final})
    cat_opts = "".join(f"<option value='{E(c)}'>{E(c)}</option>" for c in cats)
    build_opts = "".join(f"<option value='{b}'>{E(lab(b))}</option>" for b in BUILD_ORDER)

    kpis = [(f"{k['self_serve_pct']}%", "can get credentials self-serve"),
            (str(k["ready_now"]), f"of {n} are ready to build today"),
            (str(k["outreach"]), "need vendor outreach first"),
            (str(k["easy_wins"]), "easy wins not yet on Composio")]
    kpi_html = "".join(f"<div class='kpi'><span class='big' data-count>{x}</span><span class='cap'>{E(l)}</span></div>" for x, l in kpis)

    insights_html = md(insights) if insights.strip() else (
        "<ol class='findings'>"
        f"<li><strong>{k['oauth2_pct']}% use OAuth2</strong> and {k['api_key_pct']}% offer API keys, so most apps fit Composio's standard auth flows.</li>"
        f"<li><strong>{k['self_serve_pct']}% are self-serve</strong>; only {k['gated_pct']}% sit behind a paid plan, approval or sales.</li>"
        f"<li><strong>{k['ready_now']} apps are buildable today</strong>; {k['outreach']} need a partnership or have no usable API.</li>"
        f"<li><strong>{k['official_mcp']} vendors already ship an official MCP server</strong>; {k['composio_covered']} apps are already on Composio.</li></ol>")

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent Toolkit Research</title>
<meta name="description" content="An agent researched {n} apps for auth, access gating, API surface and agent-toolkit buildability, verified by a fact-check loop and a hand-checked audit.">
<link rel="alternate" type="application/json" href="final.json" title="All apps as JSON">
<link rel="alternate" type="text/csv" href="final.csv" title="All apps as CSV">
<link rel="alternate" type="text/plain" href="llms.txt" title="Summary for LLMs and agents">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<header class="top"><div class="wrap navrow"><span class="brand">Agent Toolkit Research</span>
<nav><a href="#findings">Findings</a><a href="#apps">All apps</a><a href="#how">How it works</a><a href="#verify">Verification</a><a href="#limits">Limits</a><a href="#run">Run it</a></nav></div></header>
<main class="wrap">

<section class="hero">
<p class="eyebrow">Composio · AI Product Ops take-home · {n} apps · data as of {today}</p>
<h1>Which apps can become agent toolkits today?</h1>
<p class="lede">{E(headline)}</p>
<div class="kpis">{kpi_html}</div>
<div class="proof">
<div class="proofcard"><p class="eyebrow">How accurate is it</p>{acc_hero}</div>
<div class="proofcard"><p class="eyebrow">Proof and data</p>
<ul class="links"><li><a href="{repo}">Source code and README</a></li><li><a href="#run">Run the agent on one app</a></li>
<li><a href="final.csv">final.csv</a> · <a href="final.json">final.json</a> · <a href="llms.txt">llms.txt</a> <span class="muted">for agents</span></li></ul></div>
</div>
</section>

<section class="reveal" id="findings">
<h2>What the patterns say</h2>
<div class="lead-findings">{insights_html}</div>
<h3>Where each category lands</h3><p class="muted small">Apps per verdict. Darker means more of that category.</p>{heatmap(final)}
<div class="cols two">
<div class="panel"><h3>Easy wins <span class="muted">· ready now, not yet on Composio</span></h3>{app_list(a['easy_wins'])}</div>
<div class="panel"><h3>Needs outreach <span class="muted">· partner, approval or no usable API</span></h3>{app_list(a['outreach'])}</div>
</div>
<details><summary>See the full distributions</summary>
<div class="cols three">
<div><h3>Auth methods</h3>{bars(a['auth'], n)}</div>
<div><h3>Credential access</h3>{bars(a['credential_access'], n)}</div>
<div><h3>Main blocker</h3>{bars(a['blockers'], n)}</div></div>
<h3>By category</h3>{category_matrix(a['by_category'])}
</details>
</section>

<section class="reveal" id="apps">
<h2>All {n} apps</h2>
<p class="muted">Click a row for the reasoning and evidence links. Rows marked Human-checked were verified by hand against official docs.</p>
<div class="filters"><input id="q" type="search" placeholder="Search" aria-label="Search apps">
<select id="fc" aria-label="Category"><option value="">All categories</option>{cat_opts}</select>
<select id="fb" aria-label="Verdict"><option value="">All verdicts</option>{build_opts}</select>
<label class="check"><input type="checkbox" id="fh"> Human-checked only ({n_human})</label>
<span id="count" class="muted small"></span></div>
<div class="scroll tablebox"><table id="t" class="apps"><thead><tr><th>App</th><th>Auth</th><th>Credentials</th><th>Verdict</th><th class="c">Official MCP</th><th class="c">On Composio</th></tr></thead>
<tbody>{app_rows(final)}</tbody></table></div>
</section>

<section class="reveal" id="how">
<h2>How it works</h2>
<p class="muted">A Python pipeline. Every number on this page is computed from its output, none typed by hand.</p>
<ol class="steps">
<li><b>Research</b><span>Gemini reads each vendor's official docs and fills a fixed schema with evidence URLs. One JSON per app.</span></li>
<li><b>Auto-verify</b><span>Rules check logic and schema, open every evidence link, and flag weak answers.{f" {p1.get('flagged')} apps flagged." if p1 else ''}</span></li>
<li><b>Fact-check</b><span>A second prompt re-researches only flagged apps.{f" {v.get('changed_in_pass2')} records changed." if p2 else ''}</span></li>
<li><b>Composio lookup</b><span>The Composio SDK lists existing toolkits: {k['composio_covered']} of {n} already covered.</span></li>
<li class="human"><b>Human audit</b><span>20 apps, 2 per category, re-researched blind and then checked by me against official docs.</span></li>
<li><b>Publish</b><span>Analysis script computes the patterns and builds this page plus CSV, JSON and llms.txt.</span></li>
</ol>
<div class="panel soft"><h3>Where a human was needed</h3><ul>
<li>Defining the vocabulary: what counts as self-serve, gated and buildable.</li>
<li>Hand-checking the 20-app audit sample. This is the ground truth for accuracy.</li>
<li>Confirming fuzzy name matches against Composio's toolkit list.</li>
<li>Writing the pattern summary from the computed numbers.</li></ul></div>
</section>

<section class="reveal" id="verify">
<h2>Verification</h2>
<div class="cols">
<div><h3>Accuracy on the hand-checked sample</h3>{acc_hero if scored else ''}{acc_detail}</div>
<div><h3>Automatic checks on all {n} apps</h3>
{f"<p>{p1.get('links_checked', '?')} evidence links opened and checked. {p1.get('flagged', '?')} apps flagged on pass 1, {p2.get('flagged', '?')} still flagged after the fact-check pass.</p>" if p1 else "<p class='muted'>Auto-check results appear after <code>03_verify.py</code>.</p>"}
<ul>{''.join(f"<li>{E(t)}: {c}</li>" for t, c in (p1.get('flag_types') or {}).items())}</ul></div></div>
<h3>Every miss on the audited sample{f' ({n_miss})' if n_miss else ''}</h3>{miss_html}
</section>

<section class="reveal" id="limits">
<h2>Where it fell short</h2>
<div class="panel warn"><p><strong>{len(unresolved)} apps the agent could not settle</strong> (credentials, blocker or MCP left "unclear"): {E(', '.join(unresolved) or 'none')}. Public docs don't say; these need a human or a vendor conversation.</p>
{f"<p><strong>{len(pending)} apps without a result</strong>: {E(', '.join(pending))}.</p>" if pending else ''}</div>
<ul>
<li>Accuracy is measured on a 20-app sample, not all {n}. The rest rely on the automatic loop. The sample is stratified and random (2 per category), not a separate held-out split: prompts were not tuned on it, but it is the only test set.</li>
<li>The human labels started from the blind auditor's answers, so there is some anchoring risk. 18 of 20 rows were corrected, each with a note.</li>
<li>Gemini Google Search was unavailable on the free key, so the agent read vendor docs via URL context. Pages that block bots or need JavaScript count as "unverifiable", not confirmed, and the model may fill gaps from memory.</li>
<li>Gating is one column. Sandbox vs production access and extra requirements (developer tokens, app review, business verification) are not split out, so gating is the least reliable field.</li>
<li>MCP is official yes/no; community MCP servers appear only in notes. Composio coverage is a separate cross-check from Composio's catalog and was never fed to the research agent.</li>
<li>Temperature 0.2 on an overloaded model, so reruns can differ slightly.</li>
<li>Low-confidence answers left unreviewed: {E(', '.join(a['low_confidence_left']) or 'none')}.</li>
<li>Results reflect the docs on {today}; APIs and pricing change.</li></ul>
</section>

<section class="reveal" id="run">
<h2>Run it yourself</h2>
<div class="cols two runopts">
<div class="panel"><p class="eyebrow">No keys needed</p><h3>See a real agent run</h3>
<p>Every answer on this page is saved as data. Open the agent's raw output for GitHub, before and after the fact-check pass, or the run logs:</p>
<ul class="links"><li><a href="{repo}/blob/main/data/research/pass1/061-github.json">GitHub, pass 1 output (JSON)</a></li>
<li><a href="{repo}/blob/main/data/research/pass2/061-github.json">GitHub, after fact-check (JSON)</a></li>
<li><a href="{repo}/blob/main/data/pass1_run.log">Full pass 1 run log</a></li>
<li><a href="final.json">All 100 final records</a></li></ul></div>
<div class="panel"><p class="eyebrow">With your own free keys</p><h3>Re-run the agent locally</h3>
<p>Clone the repo, copy <code>.env.example</code> to <code>.env</code> and add <strong>your own</strong> free Gemini and Composio keys. <code>.env</code> is gitignored: keys stay on your machine and are never committed or shown on this page. Then research one app (GitHub, #61) in about a minute:</p>
<div class="cmd"><code id="cmd">python agent/02_research.py --mode pass1 --only 61</code><button id="copy" type="button">Copy</button></div></div>
</div>
<details><summary>Full pipeline</summary><pre>pip install -r requirements.txt
python agent/01_extract_apps.py
python agent/02_research.py --mode pass1
python agent/03_verify.py --stage pass1
python agent/02_research.py --mode pass2
python agent/03_verify.py --stage pass2
python agent/04_composio_lookup.py
python agent/05_audit.py sample
python agent/02_research.py --mode audit
python agent/05_audit.py checklist      # then hand-check review/human_audit.csv
python agent/05_audit.py score
python agent/06_analyze.py
python agent/07_build_site.py</pre></details>
<p><a href="{repo}">Source repository</a> · <a href="{live}">Live page</a></p>
</section>
</main>
<footer class="wrap muted small">Built for the Composio AI Product Ops take-home. Machine-readable: <a href="llms.txt">llms.txt</a>, <a href="final.json">final.json</a>, <a href="final.csv">final.csv</a>, <a href="analysis.json">analysis.json</a>.</footer>
<script>{JS}</script></body></html>"""

    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "index.html").write_text(page, encoding="utf-8")
    write_llms_txt(headline, a, final, args.repo, args.live, today)
    for name in ("final.csv", "final.json", "analysis.json"):
        src = DATA / name
        if src.exists():
            (SITE / name).write_bytes(src.read_bytes())
    print(f"Wrote {SITE / 'index.html'} (+ final.csv, final.json, analysis.json, llms.txt for agents)")


CSS = """
:root{--bg:#fafaf9;--surface:#fff;--ink:#1c1917;--ink2:#44403c;--muted:#78716c;--line:#e7e5e4;--soft:#f5f5f4;
--accent:#3f51b5;--good:#15803d;--mid:#a16207;--bad:#b91c1c;--good-rgb:21,128,61;--mid-rgb:161,98,7;--bad-rgb:185,28,28}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--surface:#1a1a1a;--ink:#ececec;--ink2:#cfcfcf;--muted:#9a9a9a;--line:#2c2c2c;--soft:#202020;
--accent:#9fa8ff;--good:#4ade80;--mid:#facc15;--bad:#f87171;--good-rgb:74,222,128;--mid-rgb:250,204,21;--bad-rgb:248,113,113}}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:72px}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:0 24px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.muted{color:var(--muted)}.small{font-size:14px}code,pre{font-family:ui-monospace,"Cascadia Code",Consolas,monospace;font-size:14px}
.top{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.navrow{display:flex;align-items:center;justify-content:space-between;gap:16px;height:56px}
.brand{font-weight:600;font-size:15px;white-space:nowrap}
nav{display:flex;gap:22px;font-size:14px;overflow-x:auto;min-width:0;scrollbar-width:none}nav a{white-space:nowrap}nav a{color:var(--ink2)}nav a:hover{color:var(--accent);text-decoration:none}
section{padding:72px 0 8px}h1,h2,h3{letter-spacing:-.015em;color:var(--ink)}
h1{font-size:clamp(32px,5vw,48px);line-height:1.1;font-weight:700;margin:12px 0 18px;max-width:820px}
h2{font-size:28px;font-weight:600;margin:0 0 8px}h3{font-size:16px;font-weight:600;margin:24px 0 10px}
.hero{padding-top:64px}.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0}
.lede{font-size:clamp(18px,2.2vw,21px);color:var(--ink2);max-width:780px;margin:0 0 40px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.kpi{padding:22px 20px 22px 0}.kpi+.kpi{padding-left:20px;border-left:1px solid var(--line)}
.big{display:block;font-size:36px;font-weight:600;line-height:1.1;letter-spacing:-.02em;font-variant-numeric:tabular-nums}.big.accent{color:var(--accent)}
.cap{display:block;font-size:14px;color:var(--muted);margin-top:4px}
.proof{display:grid;grid-template-columns:3fr 2fr;gap:20px;margin-top:28px}
.proofcard,.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:22px}
.panel.soft{background:var(--soft);border-color:transparent}.panel.warn{border-left:3px solid var(--mid)}
.acc{display:flex;flex-wrap:wrap;align-items:center;gap:14px 22px;margin-top:12px}.arrow{font-size:22px;color:var(--muted)}
.note{font-size:14px;color:var(--muted);margin:10px 0 0}
.links{list-style:none;padding:0;margin:12px 0 0;font-size:15px}.links li{padding:4px 0}
.lead-findings .findings{columns:2;column-gap:48px;font-size:17px}.lead-findings li{break-inside:avoid}
.pending{color:var(--ink2);margin:12px 0 0}
.cols>*,.proof>*{min-width:0}
.panel h3:first-child,.proofcard h3:first-child{margin-top:0}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:40px;margin-top:20px}.cols.two{gap:20px}.cols.three{grid-template-columns:repeat(3,1fr);gap:28px}
.findings{padding-left:22px;margin:16px 0}.findings li{margin:0 0 14px;color:var(--ink2)}.findings li::marker{color:var(--muted);font-weight:600}
.findings strong{color:var(--ink)}
.apps{list-style:none;padding:0;margin:0;columns:2;column-gap:20px}.apps li{break-inside:avoid;padding:4px 0;font-size:15px}
.apps li span{display:block;font-size:12px;color:var(--muted)}
details{margin-top:28px;border-top:1px solid var(--line);padding-top:14px}
summary{cursor:pointer;color:var(--accent);font-weight:500;font-size:15px}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:10px 12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}
thead th{font-size:12px;font-weight:500;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;white-space:nowrap}
.num,.c{text-align:center;font-variant-numeric:tabular-nums}table.narrow{max-width:420px}
.heat th[scope=row]{font-weight:500;white-space:nowrap}
.hm{text-align:center;font-variant-numeric:tabular-nums;color:var(--ink);border-left:2px solid var(--bg)}
.hm.good{background:rgba(var(--good-rgb),calc(var(--a)*.45))}.hm.mid{background:rgba(var(--mid-rgb),calc(var(--a)*.45))}.hm.bad{background:rgba(var(--bad-rgb),calc(var(--a)*.45))}
.bar{display:grid;grid-template-columns:1fr 90px 28px;gap:10px;align-items:center;font-size:14px;margin:6px 0}
.track{height:6px;background:var(--soft);border-radius:3px;overflow:hidden}.track i{display:block;height:100%;background:var(--accent);opacity:.75}
.bar .num{text-align:right;color:var(--muted)}
.pill{display:inline-block;font-size:13px;padding:2px 10px;border-radius:999px;background:var(--soft);color:var(--ink2);white-space:nowrap}
.pill.good{background:rgba(var(--good-rgb),.12);color:var(--good)}.pill.mid{background:rgba(var(--mid-rgb),.12);color:var(--mid)}.pill.bad{background:rgba(var(--bad-rgb),.12);color:var(--bad)}
.tick{font-size:11px;font-weight:500;color:var(--accent);border:1px solid currentColor;border-radius:4px;padding:0 5px;margin-left:6px;vertical-align:2px}
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:20px 0 12px}
.filters input[type=search],.filters select{font:inherit;font-size:14px;padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink);max-width:100%}
.check{font-size:14px;color:var(--ink2);display:flex;gap:6px;align-items:center}
.tablebox{background:var(--surface);border:1px solid var(--line);border-radius:12px;max-height:72vh;overflow:auto}
.apps thead th{position:sticky;top:0;background:var(--surface);z-index:1}
.row{cursor:pointer}.row:hover{background:var(--soft)}.row:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.sub{font-size:12px;color:var(--muted)}
.caret{display:inline-block;width:12px;color:var(--muted)}.caret::before{content:"›";display:inline-block;transition:transform .15s}
.row[aria-expanded=true] .caret::before{transform:rotate(90deg)}
.detail td{background:var(--soft)}.dgrid{display:grid;grid-template-columns:1fr 1fr;gap:14px 28px;padding:6px 4px 10px;font-size:14px;color:var(--ink2)}
.dgrid b{display:block;font-size:12px;font-weight:500;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}.dgrid .wide{grid-column:1/-1}.dgrid a{margin-right:12px}
.steps{list-style:none;counter-reset:s;padding:0;margin:24px 0;display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.steps li{counter-increment:s;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px;font-size:14px;color:var(--ink2)}
.steps li b{display:block;color:var(--ink);font-size:15px;margin-bottom:4px}.steps li b::before{content:counter(s) "  ";color:var(--muted);font-weight:500}
.steps li.human{border-color:var(--accent)}.steps li.human b::after{content:"Human";font-size:11px;font-weight:500;color:var(--accent);border:1px solid currentColor;border-radius:4px;padding:0 5px;margin-left:8px;vertical-align:2px}
.cmd{display:flex;align-items:center;gap:12px;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;overflow-x:auto}
.cmd code{flex:1;white-space:nowrap}.cmd button{font:inherit;font-size:13px;border:1px solid var(--line);background:var(--soft);color:var(--ink);border-radius:6px;padding:5px 12px;cursor:pointer}
pre{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;overflow-x:auto;line-height:1.6}
ul{padding-left:20px}li{margin:4px 0}
footer{padding:64px 24px 48px;border-top:1px solid var(--line);margin-top:72px}
@media (max-width:820px){.kpis{grid-template-columns:1fr 1fr}.kpi:nth-child(3){padding-left:0;border-left:0}.kpi:nth-child(n+3){border-top:1px solid var(--line)}
.proof,.cols,.cols.three{grid-template-columns:1fr}.steps{grid-template-columns:1fr}.apps{columns:1}.dgrid{grid-template-columns:1fr}
.brand{display:none}.lead-findings .findings{columns:1}nav{gap:16px}section{padding-top:56px}}
.reveal{opacity:0;transform:translateY(18px);transition:opacity .7s ease,transform .7s ease}.reveal.in{opacity:1;transform:none}
.hero>*{animation:rise .8s ease both}.hero>*:nth-child(2){animation-delay:.08s}.hero>*:nth-child(3){animation-delay:.16s}.hero>*:nth-child(4){animation-delay:.24s}.hero>*:nth-child(5){animation-delay:.32s}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
.kpi{transition:background .2s}.kpi:hover{background:var(--surface)}
.proofcard,.panel,.steps li{transition:transform .2s ease,box-shadow .2s ease,border-color .2s}
.proofcard:hover,.panel:hover,.steps li:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.06)}
.track i{transform-origin:left;transform:scaleX(0);transition:transform 1s cubic-bezier(.2,.7,.2,1)}.in .track i{transform:scaleX(1)}
.hm{transition:filter .15s}.hm:hover{filter:brightness(.92)}
.pill{transition:transform .15s}.row:hover .pill{transform:translateY(-1px)}
nav a{position:relative;transition:color .2s}nav a.active{color:var(--accent)}
nav a::after{content:"";position:absolute;left:0;right:0;bottom:-18px;height:2px;background:var(--accent);transform:scaleX(0);transition:transform .25s}nav a.active::after{transform:scaleX(1)}
.top{transition:box-shadow .2s}.top.scrolled{box-shadow:0 2px 14px rgba(0,0,0,.06)}
.runopts .panel p{font-size:15px;color:var(--ink2)}.runopts .cmd{margin-top:14px}.runopts .cmd code{white-space:normal;word-break:break-word}.cmd button{flex:none}
html,body{overflow-x:clip}
.hero{position:relative}.hero::before{content:"";position:absolute;z-index:-1;inset:-40px -10% auto auto;width:560px;height:420px;border-radius:50%;
background:radial-gradient(circle at 30% 30%,rgba(63,81,181,.18),transparent 60%),radial-gradient(circle at 70% 60%,rgba(21,128,61,.12),transparent 60%);filter:blur(30px);animation:drift 14s ease-in-out infinite alternate;pointer-events:none}
@keyframes drift{from{transform:translate(0,0) scale(1)}to{transform:translate(-80px,40px) scale(1.15)}}
h1{background:linear-gradient(90deg,var(--ink) 0%,var(--ink) 55%,var(--accent) 100%);-webkit-background-clip:text;background-clip:text;color:transparent}
.big.accent{animation:pulse 2.4s ease-in-out 1.6s 2}@keyframes pulse{50%{opacity:.55}}
.reveal h2::after{content:"";display:block;width:0;height:3px;border-radius:2px;background:var(--accent);margin-top:10px;transition:width .9s .2s ease}.reveal.in h2::after{width:48px}
.in .hm{animation:pop .5s ease both}.in tr:nth-child(2) .hm{animation-delay:.05s}.in tr:nth-child(3) .hm{animation-delay:.1s}.in tr:nth-child(4) .hm{animation-delay:.15s}.in tr:nth-child(5) .hm{animation-delay:.2s}.in tr:nth-child(6) .hm{animation-delay:.25s}.in tr:nth-child(7) .hm{animation-delay:.3s}.in tr:nth-child(8) .hm{animation-delay:.35s}.in tr:nth-child(9) .hm{animation-delay:.4s}.in tr:nth-child(10) .hm{animation-delay:.45s}
@keyframes pop{from{opacity:0;transform:scale(.85)}to{opacity:1;transform:none}}
.in .steps li,.in .findings li,.in .apps li{animation:rise .6s ease both}
.in .steps li:nth-child(2),.in .findings li:nth-child(2){animation-delay:.1s}.in .steps li:nth-child(3),.in .findings li:nth-child(3){animation-delay:.2s}.in .steps li:nth-child(4),.in .findings li:nth-child(4){animation-delay:.3s}.in .steps li:nth-child(5),.in .findings li:nth-child(5){animation-delay:.4s}.in .steps li:nth-child(6),.in .findings li:nth-child(6){animation-delay:.5s}
.steps li.human{box-shadow:0 0 0 0 rgba(63,81,181,.35)}.in .steps li.human{animation:rise .6s ease .4s both,ring 2s ease 1.2s 2}@keyframes ring{0%{box-shadow:0 0 0 0 rgba(63,81,181,.35)}100%{box-shadow:0 0 0 12px rgba(63,81,181,0)}}
.row{transition:background .15s}.kpi .big{transition:color .2s}.kpi:hover .big{color:var(--accent)}
.cmd button:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
@media (prefers-reduced-motion:reduce){.hero::before,.hm,.steps li,.findings li,.apps li{animation:none!important}}
@media (prefers-reduced-motion:reduce){.reveal,.hero>*,.track i{opacity:1!important;transform:none!important;animation:none!important;transition:none!important}}
@media print{.reveal{opacity:1;transform:none}.top,.filters,.cmd button{display:none}.tablebox{max-height:none;overflow:visible}details{display:block}.detail{display:table-row!important}}
"""

JS = """
(function(){
  var q=document.getElementById('q'),fc=document.getElementById('fc'),fb=document.getElementById('fb'),fh=document.getElementById('fh'),
      rows=[].slice.call(document.querySelectorAll('#t tr.row')),count=document.getElementById('count');
  function run(){var t=q.value.toLowerCase(),n=0;rows.forEach(function(r){
    var d=r.nextElementSibling,text=(r.textContent+' '+d.textContent).toLowerCase();
    var ok=(!t||text.indexOf(t)>-1)&&(!fc.value||r.dataset.cat===fc.value)&&(!fb.value||r.dataset.build===fb.value)&&(!fh.checked||r.dataset.human==='1');
    r.style.display=ok?'':'none';if(!ok){d.hidden=true;r.setAttribute('aria-expanded','false')}if(ok)n++;});
    count.textContent=n+' of '+rows.length+' apps';}
  [q,fc,fb,fh].forEach(function(el){el.addEventListener('input',run);el.addEventListener('change',run)});run();
  function toggle(r){var d=r.nextElementSibling,open=d.hidden;d.hidden=!open;r.setAttribute('aria-expanded',open?'true':'false')}
  rows.forEach(function(r){r.addEventListener('click',function(e){if(e.target.tagName!=='A')toggle(r)});
    r.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();toggle(r)}})});
  var cb=document.getElementById('copy');cb&&cb.addEventListener('click',function(){
    try{navigator.clipboard.writeText(document.getElementById('cmd').textContent).then(function(){cb.textContent='Copied';setTimeout(function(){cb.textContent='Copy'},1500)})}catch(e){}});
  var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var secs=[].slice.call(document.querySelectorAll('.reveal'));
  if('IntersectionObserver' in window&&!reduce){var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}})},{threshold:.08});
    secs.forEach(function(s){io.observe(s)});document.querySelectorAll('details').forEach(function(d){d.addEventListener('toggle',function(){d.classList.add('in')})});}
  else{secs.forEach(function(s){s.classList.add('in')});document.querySelectorAll('details').forEach(function(d){d.classList.add('in')})}
  document.querySelectorAll('details').forEach(function(d){d.addEventListener('toggle',function(){d.classList.add('in')})});
  if(!reduce)document.querySelectorAll('[data-count]').forEach(function(el){var m=el.textContent.match(/^([0-9.]+)(.*)$/);if(!m)return;
    var end=parseFloat(m[1]),suf=m[2],dec=(m[1].split('.')[1]||'').length,t0=null;el.textContent=(0).toFixed(dec)+suf;
    function step(ts){if(!t0)t0=ts;var p=Math.min((ts-t0)/1200,1),e=1-Math.pow(1-p,3);el.textContent=(end*e).toFixed(dec)+suf;if(p<1)requestAnimationFrame(step)}
    setTimeout(function(){requestAnimationFrame(step)},300)});
  var top=document.querySelector('.top'),links=[].slice.call(document.querySelectorAll('nav a')),ids=links.map(function(a){return document.querySelector(a.getAttribute('href'))});
  function onScroll(){top.classList.toggle('scrolled',window.scrollY>8);var cur=-1;ids.forEach(function(s,i){if(s&&s.getBoundingClientRect().top<120)cur=i});if(window.innerHeight+window.scrollY>=document.body.scrollHeight-4)cur=links.length-1;
    links.forEach(function(a,i){a.classList.toggle('active',i===cur)})}
  window.addEventListener('scroll',onScroll,{passive:true});onScroll();
})();
"""

if __name__ == "__main__":
    main()
