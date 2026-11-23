"""Step 4: ask Composio which of the 100 apps it already has a toolkit for.

Uses the Composio Python SDK to list toolkits (falls back to Composio's REST API with the
same key if the SDK call shape differs in your installed version; the output records which was used).
This is a fact lookup, not research: it fills the 'composio_toolkit' column.

Run:  python agent/04_composio_lookup.py
"""
import difflib
import os
import re
import sys

import requests

from common import COMPOSIO_JSON, load_apps, load_env, write_json

load_env()

# Apps whose Composio slug is not just their name squashed together. Check a few by hand.
ALIASES = {
    "Meta Ads": ["metaads", "facebookads", "facebook"],
    "LinkedIn Ads": ["linkedinads", "linkedin"],
    "Threads (Meta)": ["threads"],
    "WhatsApp Business": ["whatsapp"],
    "Lark (Larksuite)": ["lark", "larksuite"],
    "Magento (Adobe Commerce)": ["magento", "adobecommerce"],
    "Amazon Selling Partner": ["amazonsellingpartner", "amazonsp", "amazon"],
    "Salesforce Commerce Cloud": ["salesforcecommercecloud"],
    "Monday.com": ["monday", "mondaycom"],
    "Jira": ["jira"],
    "YouTube Transcript": ["youtubetranscript", "transcriptapi", "youtube"],
    "Mermaid CLI": ["mermaid", "mermaidcli"],
    "Twenty": ["twenty", "twentycrm"],
    "Close": ["close", "closecrm"],
    "Copper": ["copper", "coppercrm"],
    "Plain": ["plain", "plaincom"],
    "systeme.io": ["systemeio", "systeme"],
    "Waterfall.io": ["waterfall", "waterfallio"],
    "Otter AI": ["otter", "otterai"],
    "NotebookLM": ["notebooklm"],
}


def squash(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def list_toolkits(key):
    """Return (list of {slug,name}, method_used)."""
    try:
        from composio import Composio
        client = Composio(api_key=key)
        # toolkits.get() returns only the first page (1000 of ~1800), so page through toolkits.list().
        out, cursor = [], None
        while True:
            res = client.toolkits.list(limit=1000, **({"cursor": cursor} if cursor else {}))
            for t in res.items:
                d = t if isinstance(t, dict) else (t.model_dump() if hasattr(t, "model_dump") else vars(t))
                out.append({"slug": d.get("slug", ""), "name": d.get("name", "")})
            cursor = getattr(res, "next_cursor", None)
            if not cursor:
                break
        if out:
            return out, "composio python SDK: Composio().toolkits.list() (paginated)"
    except Exception as e:
        print(f"SDK call did not work in this version ({str(e)[:120]}); using the REST API instead.")

    out, cursor = [], None
    while True:
        params = {"limit": 1000}
        if cursor:
            params["cursor"] = cursor
        r = requests.get("https://backend.composio.dev/api/v3/toolkits",
                         headers={"x-api-key": key}, params=params, timeout=30)
        r.raise_for_status()
        body = r.json()
        out += [{"slug": t.get("slug", ""), "name": t.get("name", "")} for t in body.get("items", [])]
        cursor = body.get("next_cursor")
        if not cursor:
            break
    return out, "composio REST API: GET /api/v3/toolkits"


def main():
    key = os.environ.get("COMPOSIO_API_KEY")
    if not key:
        sys.exit("COMPOSIO_API_KEY is not set. Put it in the .env file (see START_HERE.md).")
    toolkits, method = list_toolkits(key)
    print(f"Composio returned {len(toolkits)} toolkits via {method}")

    by_key = {}
    for t in toolkits:
        by_key.setdefault(squash(t["slug"]), t)
        by_key.setdefault(squash(t["name"]), t)

    results = {}
    for app in load_apps():
        name = app["app"]
        candidates = ALIASES.get(name, []) + [squash(name), squash(re.sub(r"\(.*?\)", "", name))]
        hit = next((by_key[c] for c in candidates if c in by_key), None)
        match = "exact" if hit else "none"
        if not hit:   # suggest a near match for a human to confirm, never count it automatically
            close = difflib.get_close_matches(squash(name), list(by_key), n=1, cutoff=0.85)
            if close:
                hit, match = by_key[close[0]], "fuzzy_needs_review"
        results[app["id"]] = {"app": name, "composio_toolkit": match == "exact",
                              "match": match, "slug": hit["slug"] if hit else ""}
        print(f"  {name:<28} {match:<20} {hit['slug'] if hit else ''}")

    write_json(COMPOSIO_JSON, {"method": method, "toolkit_count": len(toolkits), "apps": results})
    n = sum(r["composio_toolkit"] for r in results.values())
    print(f"\n{n}/100 apps already have a Composio toolkit -> {COMPOSIO_JSON}")
    print("Check any 'fuzzy_needs_review' rows by hand and edit the JSON if needed.")


if __name__ == "__main__":
    main()
