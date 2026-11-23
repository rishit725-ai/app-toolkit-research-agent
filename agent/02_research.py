"""Step 2: the research agent. Gemini + URL-context reading of official docs, one app at a time.

Modes
  pass1  research every app from scratch                     -> data/research/pass1/
  pass2  re-research only apps flagged by 03_verify.py        -> data/research/pass2/
         (unflagged apps are copied over unchanged)
  audit  blind, independent research of the 20 audit apps   -> data/research/audit/
         (never sees pass1 answers)

Run:  python agent/02_research.py --mode pass1            (all 100, resumes if stopped)
      python agent/02_research.py --mode pass1 --only 1 2 (just a couple, to test)

Each app is saved as its own JSON file as soon as it finishes, so a crash or a
rate limit only costs the app in progress. Rerunning skips finished apps.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import date

import requests

from common import (FLAGS_DIR, AUDIT_SAMPLE, VOCAB, load_apps, load_env, read_csv,
                    read_json, record_path, validate_record, write_json)

load_env()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
SLEEP = float(os.environ.get("GEMINI_SLEEP_SECONDS", "7"))   # free tier is ~10 requests/min

SCHEMA_HINT = f"""Return ONLY one JSON object, no prose, with exactly these keys:
{{
  "description": "one line: what the app does",
  "auth_methods": [one or more of {VOCAB['auth_methods']}],
  "auth_notes": "short: how auth works, e.g. 'OAuth2 auth code for public apps; private app access tokens'",
  "credential_access": one of {VOCAB['credential_access']},
  "credential_notes": "short: exactly how a developer gets credentials and what it costs / who must approve",
  "api_styles": [one or more of {VOCAB['api_styles']}],
  "api_breadth": one of {VOCAB['api_breadth']},
  "api_notes": "short: what the API covers",
  "official_mcp": one of {VOCAB['official_mcp']},
  "mcp_notes": "short: official MCP server by the vendor? community MCP? give names",
  "buildability": one of {VOCAB['buildability']},
  "primary_blocker": one of {VOCAB['primary_blocker']},
  "rationale": "one sentence explaining the buildability verdict",
  "confidence": one of {VOCAB['confidence']},
  "evidence": [{{"supports": "auth|credentials|api|mcp|buildability", "url": "https://...", "note": "what this page shows"}}],
  "open_questions": "anything you could not confirm, or empty string"
}}"""

RULES = """Definitions and rules:
- credential_access: self_serve_free = any developer can sign up and get API credentials free (free plan or free developer account/sandbox);
  self_serve_trial = only during a free trial; paid_plan = API access needs a paid plan/tier; admin_approval = needs an app review or
  workspace-admin/marketplace approval before real use; partner_or_sales_gated = needs partnership, contact sales or an enterprise contract;
  open_source_local = open source / self-hosted / local tool; unclear = sources do not say.
- Do NOT assume self-serve just because API docs are public. Do NOT assume an API key is free just because the API uses keys.
- buildability: ready_now = public documented API + self-serve credentials; ready_with_constraints = buildable but with limits
  (paid tier, app review, narrow API, rate limits); outreach_required = needs partnership/sales/approval first; not_buildable_now = no usable API.
- primary_blocker must be 'none' only when buildability is ready_now.
- official_mcp = 'yes' only if the vendor itself publishes or announces an MCP server. Community servers go in mcp_notes only.
- Evidence: prefer official developer docs, official pricing/help pages, official GitHub. Give real URLs you found, at least one
  for auth and one for credentials. Never invent URLs. If you are not sure, say so in open_questions and lower confidence.
- Today's date is """ + date.today().isoformat() + "."


def prompt_pass1(app):
    return f"""You are researching apps for an AI-agent tool platform. Use the official documentation pages listed at the end (they are fetched for you) to check current facts.

App: {app['app']}
Category: {app['category']}
Hint from the brief: {app['hint']}

Find: what it does, its API auth method(s), whether a developer can get credentials self-serve and free,
the public API surface, whether an MCP server exists, and whether it could become an agent toolkit today.

{RULES}

{SCHEMA_HINT}"""


def prompt_pass2(app, previous, flags):
    prev = {k: v for k, v in previous.items() if k not in ("grounding_sources", "search_queries", "candidate_urls")}
    return f"""You are a fact-checker. Another research agent produced the answer below for {app['app']}
({app['category']}; hint: {app['hint']}). Automatic checks flagged these problems:
{flags}

Use the official documentation pages listed at the end (fetched for you) to re-check EVERY field against current official documentation, paying most attention to the
flagged ones. Keep values that you can confirm, correct values that are wrong, and replace evidence URLs that are
dead or do not support the claim with working official URLs.

Previous answer:
{json.dumps(prev, indent=1, ensure_ascii=False)}

{RULES}

{SCHEMA_HINT[:-1]},
  "changes": "list each field you changed and why, or 'none'"
}}"""


def prompt_audit(app):
    return f"""You are an independent auditor double-checking API research. Be skeptical and precise. Use the pages listed at the end (fetched for you) and rely on
official developer documentation, official pricing pages and official repositories only.

App: {app['app']}
Category: {app['category']}
Hint: {app['hint']}

Determine from primary sources: auth methods, how a developer actually obtains credentials (free? paid plan? approval? sales?),
API style and breadth, whether the vendor publishes an official MCP server, and the buildability verdict.

{RULES}

{SCHEMA_HINT}"""


# ------------------------------------------------------------------ gemini
def get_client():
    try:
        from google import genai
    except ImportError:
        sys.exit("Missing package. Run:  pip install -r requirements.txt")
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY is not set. Put it in the .env file (see START_HERE.md).")
    from google.genai import types
    return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=180_000))  # ms; avoid hung calls


def ask_gemini(client, prompt, urls=None):
    """One Gemini call. With urls, the URL-context tool fetches those pages and the model answers from them.
    (Google Search grounding returned 429 quota errors on the free key, so the agent reads official pages
    directly instead: find_urls() proposes them, URL context fetches them, and only fetched pages count as sources.)"""
    from google.genai import types
    config = types.GenerateContentConfig(temperature=0.2)
    if urls:
        config.tools = [types.Tool(url_context=types.UrlContext())]
        prompt = (prompt + "\n\nPages to read (fetched for you; cite only pages that actually support a claim):\n"
                  + "\n".join(urls[:20]))
    for attempt in range(6):
        try:
            return client.models.generate_content(model=MODEL, contents=prompt, config=config)
        except Exception as e:  # rate limits and transient server errors: back off and retry
            msg = str(e)
            if any(s in msg for s in ("429", "RESOURCE_EXHAUSTED", "500", "503", "504", "UNAVAILABLE",
                                       "DEADLINE_EXCEEDED", "timed out")):
                wait = 20 * (attempt + 1)
                print(f"    rate-limited / transient error, waiting {wait}s ({msg[:80]})")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("gave up after repeated rate limits; rerun later to resume")


def find_urls(client, app):
    """Ask the model (no tools) for the official pages worth reading for this app."""
    resp = ask_gemini(client, f"""List the official URLs a developer would read to research the API of {app['app']}
(official site: {app['official_url']}). Include, where they exist: API authentication docs, how to get API keys /
create an app (developer portal), API pricing or plan limits, the API reference overview, and any official MCP server
page or official GitHub repo. Only URLs on the vendor's own domains or official GitHub. At most 10.
Return ONLY a JSON array of URL strings.""")
    text = re.sub(r"^```(?:json)?|```$", "", (resp.text or "").strip(), flags=re.M).strip()
    try:
        urls = json.loads(text[text.find("["):text.rfind("]") + 1])
    except Exception:
        urls = re.findall(r"https?://[^\s\"'<>\]]+", text)
    return [u for u in urls if isinstance(u, str) and u.startswith("http")][:10]


def parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start:end + 1])


def resolve(uri):
    """Grounding links are Google redirect URLs; follow one hop to get the real page."""
    try:
        r = requests.head(uri, allow_redirects=False, timeout=8)
        return r.headers.get("Location", uri)
    except Exception:
        return uri


def grounding_info(resp):
    """Pages the URL-context tool actually fetched successfully (these are the grounding sources)."""
    try:
        um = resp.candidates[0].url_context_metadata
    except (AttributeError, IndexError):
        return []
    sources = []
    for m in (getattr(um, "url_metadata", None) or []):
        status = str(getattr(m, "url_retrieval_status", ""))
        if m.retrieved_url and "SUCCESS" in status:
            sources.append({"title": "", "url": m.retrieved_url})
    return sources


def research_one(client, app, prompt, stage, extra_urls=()):
    found = find_urls(client, app)
    time.sleep(SLEEP)
    urls = list(dict.fromkeys([app["official_url"], *extra_urls, *found]))
    resp = ask_gemini(client, prompt, urls)
    try:
        rec = parse_json(resp.text)
    except Exception:
        time.sleep(SLEEP)
        resp = ask_gemini(client, prompt + "\n\nIMPORTANT: reply with the JSON object only.", urls)
        rec = parse_json(resp.text)
    sources = grounding_info(resp)
    rec.update({"id": int(app["id"]), "app": app["app"], "category": app["category"],
                "official_url": app["official_url"], "stage": stage, "model": MODEL,
                "researched_on": date.today().isoformat(),
                "grounding_sources": sources, "search_queries": [], "candidate_urls": urls})
    rec["schema_problems"] = validate_record(rec)
    return rec


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["pass1", "pass2", "audit"], required=True)
    ap.add_argument("--only", type=int, nargs="*", help="app ids to run (default: all for this mode)")
    ap.add_argument("--force", action="store_true", help="redo apps that already have a file")
    ap.add_argument("--serious-only", action="store_true",
                    help="pass2: only re-research apps with serious flags (failures, logic, dead links, auth not on page)")
    args = ap.parse_args()

    apps = load_apps()
    flags = {}
    if args.mode == "audit":
        if not AUDIT_SAMPLE.exists():
            sys.exit("No audit sample yet. Run:  python agent/05_audit.py sample")
        ids = {int(r["id"]) for r in read_csv(AUDIT_SAMPLE)}
        apps = [a for a in apps if int(a["id"]) in ids]
    if args.mode == "pass2":
        fpath = FLAGS_DIR / "pass1.csv"
        if not fpath.exists():
            sys.exit("No flags yet. Run:  python agent/03_verify.py --stage pass1")
        flags = {int(r["id"]): r["flags"] for r in read_csv(fpath) if r["flags"]}
        if args.serious_only:   # skip apps whose only flags are 'confidence low' / 'credential access unclear'
            minor = ("agent confidence low", "credential access unclear")
            flags = {i: f for i, f in flags.items()
                     if any(x.strip() and x.strip() not in minor for x in f.split(";"))}
            print(f"pass2 --serious-only: re-researching {len(flags)} apps with serious flags")
        if AUDIT_SAMPLE.exists():   # audit-sample apps first, so the pass1-vs-pass2 accuracy comparison is covered
            sample = {int(r["id"]) for r in read_csv(AUDIT_SAMPLE)}
            apps = sorted(apps, key=lambda a: int(a["id"]) not in sample)
    if args.only:
        apps = [a for a in apps if int(a["id"]) in set(args.only)]

    client = None
    done = failed = copied = 0
    for i, app in enumerate(apps, 1):
        out = record_path(args.mode, app)
        if out.exists() and not args.force and not read_json(out, {}).get("error"):
            continue
        if args.mode == "pass2" and int(app["id"]) not in flags:
            prev = read_json(record_path("pass1", app))
            if prev:   # not flagged: carry pass1 forward unchanged
                prev.update({"stage": "pass2", "changes": "not flagged, kept from pass1"})
                write_json(out, prev)
                copied += 1
            continue

        client = client or get_client()
        print(f"[{i}/{len(apps)}] {args.mode}: {app['app']}")
        try:
            if args.mode == "pass1":
                prompt = prompt_pass1(app)
            elif args.mode == "audit":
                prompt = prompt_audit(app)
            extra = []
            if args.mode == "pass2":
                prev = read_json(record_path("pass1", app))
                if not prev or prev.get("error"):   # pass1 failed / never reached: research from scratch
                    prompt = prompt_pass1(app)
                else:
                    prompt = prompt_pass2(app, prev, flags[int(app["id"])])
                    extra = [e.get("url") for e in prev.get("evidence", []) if str(e.get("url", "")).startswith("http")]
            rec = research_one(client, app, prompt, args.mode, extra)
            write_json(out, rec)
            note = f"  schema problems: {rec['schema_problems']}" if rec["schema_problems"] else ""
            print(f"    -> {rec.get('buildability')} / {rec.get('credential_access')} / "
                  f"{rec.get('auth_methods')} ({rec.get('confidence')}){note}")
            done += 1
        except Exception as e:
            print(f"    !! failed: {e}")
            write_json(out, {"id": int(app["id"]), "app": app["app"], "error": str(e)})
            failed += 1
        time.sleep(SLEEP)

    print(f"\nDone. researched={done} failed={failed} carried_over={copied}")
    if failed:
        print("Rerun the same command to retry the failed apps.")


if __name__ == "__main__":
    main()
