"""Step 3: automatic verification loop. No LLM here: plain rules plus fetching the evidence pages.

For every record of a stage it checks:
  1. schema   - every field filled with an allowed value
  2. logic    - the answers agree with each other (e.g. 'ready_now' cannot be partner-gated)
  3. links    - every evidence URL actually loads (403/429 bot blocks are counted as 'unverifiable', not dead)
  4. grounding- the claimed auth method is actually mentioned on the evidence pages
  5. confidence - the agent's own 'low' confidence answers are always re-checked

Flagged apps are what 02_research.py --mode pass2 re-researches.

Run:  python agent/03_verify.py --stage pass1
"""
import argparse
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests

from common import FLAGS_DIR, GATED, load_apps, read_json, record_path, validate_record, write_csv, write_json

HEADERS = {"User-Agent": "Mozilla/5.0 (research-verifier; take-home project)"}
AUTH_WORDS = {
    "oauth2": ["oauth"],
    "api_key": ["api key", "api_key", "apikey", "api-key", "x-api-key", "access key", "secret key"],
    "bearer_token": ["bearer", "token"],
    "basic": ["basic auth", "basic authentication", "username and password", "authorization: basic"],
    "jwt": ["jwt", "json web token"],
    "hmac_signature": ["hmac", "signature"],
}


def fetch(url):
    """Return (status_label, page_text_lowercase)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        if r.status_code in (401, 403, 429, 999):
            return "unverifiable", ""
        if r.status_code >= 400:
            return "dead", ""
        text = re.sub(r"<[^>]+>", " ", r.text).lower()
        return "ok", text
    except Exception:
        return "dead", ""


def logic_flags(r):
    f = []
    b, blocker, cred = r.get("buildability"), r.get("primary_blocker"), r.get("credential_access")
    if b == "ready_now" and blocker != "none":
        f.append("ready_now but has a blocker")
    if blocker == "none" and b != "ready_now":
        f.append(f"no blocker but verdict is {b}")
    if b == "ready_now" and cred in GATED | {"unclear"}:
        f.append(f"ready_now but credentials are {cred}")
    if b in ("ready_now", "ready_with_constraints") and r.get("api_breadth") == "none":
        f.append("buildable but no API")
    if r.get("official_mcp") == "yes" and not any(e.get("supports") == "mcp" for e in r.get("evidence", [])):
        f.append("official MCP claimed without MCP evidence")
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["pass1", "pass2", "audit"], required=True)
    args = ap.parse_args()

    apps = load_apps()
    records = {int(a["id"]): read_json(record_path(args.stage, a)) for a in apps}
    urls = sorted({e.get("url") for r in records.values() if r and not r.get("error")
                   for e in r.get("evidence", []) if str(e.get("url", "")).startswith("http")})
    print(f"Checking {len(urls)} evidence links ...")
    with ThreadPoolExecutor(max_workers=12) as pool:
        pages = dict(zip(urls, pool.map(fetch, urls)))

    rows, flag_types = [], Counter()
    link_stats = Counter(status for status, _ in pages.values())
    for a in apps:
        r = records[int(a["id"])]
        flags = []
        if not r:
            flags.append("not researched")
        elif r.get("error"):
            flags.append("research failed")
        else:
            flags += [f"schema: {p}" for p in validate_record(r)]
            flags += logic_flags(r)
            ev = [e.get("url") for e in r.get("evidence", [])]
            dead = [u for u in ev if pages.get(u, ("dead",))[0] == "dead"]
            if dead:
                flags.append(f"{len(dead)} dead evidence link(s)")
            readable = " ".join(pages[u][1] for u in ev if u in pages and len(pages[u][1]) > 1500)
            if readable:
                for m in r.get("auth_methods", []):
                    words = AUTH_WORDS.get(m)
                    if words and not any(w in readable for w in words):
                        flags.append(f"auth '{m}' not found on evidence pages")
            if r.get("confidence") == "low":
                flags.append("agent confidence low")
            if r.get("credential_access") == "unclear":
                flags.append("credential access unclear")
        for fl in flags:   # group similar flags for the summary, e.g. "auth not found on evidence pages"
            kind = "schema problem" if fl.startswith("schema") else re.sub(r"^\d+ |'[^']*' ?", "", fl)
            flag_types[kind.strip()] += 1
        rows.append({"id": a["id"], "app": a["app"], "category": a["category"], "flags": "; ".join(flags)})

    flagged = [r for r in rows if r["flags"]]
    write_csv(FLAGS_DIR / f"{args.stage}.csv", rows, ["id", "app", "category", "flags"])
    summary = {"stage": args.stage, "records": sum(1 for r in records.values() if r and not r.get("error")),
               "flagged": len(flagged), "links_checked": len(urls), "link_status": dict(link_stats),
               "flag_types": dict(flag_types.most_common())}
    write_json(FLAGS_DIR / f"{args.stage}_summary.json", summary)

    print(f"\n{len(flagged)} of {len(rows)} apps flagged  ->  {FLAGS_DIR / (args.stage + '.csv')}")
    print(f"Links: {dict(link_stats)}")
    for t, n in flag_types.most_common():
        print(f"  {n:>3}  {t}")


if __name__ == "__main__":
    main()
