"""Step 7: merge the final dataset and compute the patterns. Every number on the page comes from here.

final record = pass2 (falls back to pass1)  +  your human corrections for audited apps  +  Composio column

Run:  python agent/06_analyze.py
Writes data/final.csv and data/analysis.json
"""
from collections import Counter, defaultdict

from common import (ACCURACY_JSON, ANALYSIS_JSON, COMPOSIO_JSON, FINAL_CSV, FLAGS_DIR, GATED, HUMAN_AUDIT,
                    LIST_FIELDS, SCORED_FIELDS, SELF_SERVE, load_apps, load_stage, read_csv, read_json,
                    write_csv, write_json)


def build_final():
    p1, p2 = load_stage("pass1"), load_stage("pass2")
    human = {int(r["id"]): r for r in read_csv(HUMAN_AUDIT)} if HUMAN_AUDIT.exists() else {}
    composio = (read_json(COMPOSIO_JSON, {}) or {}).get("apps", {})
    final = []
    for a in load_apps():
        i = int(a["id"])
        r = dict(p2.get(i) or p1.get(i) or {"id": i, "app": a["app"], "category": a["category"]})
        r["review_status"] = "pass1 only" if (i in p1 or i in p2) else "not researched (time limit)"
        if i in p2:
            ch = str(p2[i].get("changes", ""))
            r["review_status"] = ("passed auto-checks" if ch.startswith("not flagged")
                                  else "flagged, not re-checked (time limit)" if ch.startswith("flagged, not re-checked")
                                  else "flagged, re-researched")
        h = human.get(i)
        if h and h["status"].strip() in ("confirmed", "corrected"):
            for f in SCORED_FIELDS:
                r[f] = [v for v in h[f].split(";") if v] if f in LIST_FIELDS else h[f]
            r["review_status"] = f"human {h['status'].strip()}"
            r["human_note"] = h["your_note"]
        c = composio.get(str(i)) or composio.get(i) or {}
        r["composio_toolkit"] = "yes" if c.get("composio_toolkit") else ("check" if c.get("match") == "fuzzy_needs_review" else "no" if c else "not checked")
        r["evidence_urls"] = [e.get("url") for e in r.get("evidence", []) if e.get("url")]
        final.append(r)
    return final


def pct(n, d):
    return round(100 * n / d) if d else 0


def analyze(final):
    n = len(final)
    auth = Counter(m for r in final for m in r.get("auth_methods", []))
    cred = Counter(r.get("credential_access") for r in final)
    build = Counter(r.get("buildability") for r in final)
    blockers = Counter(r.get("primary_blocker") for r in final if r.get("primary_blocker") not in (None, "none"))
    styles = Counter(s for r in final for s in r.get("api_styles", []))

    by_cat = defaultdict(lambda: Counter())
    for r in final:
        c = by_cat[r["category"]]
        c["apps"] += 1
        c["self_serve"] += r.get("credential_access") in SELF_SERVE
        c["gated"] += r.get("credential_access") in GATED
        c["oauth2"] += "oauth2" in r.get("auth_methods", [])
        c["api_key"] += "api_key" in r.get("auth_methods", [])
        c["ready_now"] += r.get("buildability") == "ready_now"
        c["outreach"] += r.get("buildability") in ("outreach_required", "not_buildable_now")
        c["composio"] += r.get("composio_toolkit") == "yes"
        c["official_mcp"] += r.get("official_mcp") == "yes"

    def short(r):
        return {"app": r["app"], "category": r["category"], "why": r.get("rationale", ""),
                "blocker": r.get("primary_blocker"), "credential_access": r.get("credential_access")}

    easy_wins = [short(r) for r in final if r.get("buildability") == "ready_now" and r.get("composio_toolkit") != "yes"]
    outreach = [short(r) for r in final if r.get("buildability") in ("outreach_required", "not_buildable_now")]
    self_serve_n = sum(cred[k] for k in SELF_SERVE)
    gated_n = sum(cred[k] for k in GATED)
    top_auth = auth.most_common(1)[0] if auth else ("-", 0)
    top_blocker = blockers.most_common(1)[0] if blockers else ("-", 0)

    return {
        "n_apps": n,
        "kpis": {
            "self_serve_pct": pct(self_serve_n, n), "gated_pct": pct(gated_n, n),
            "ready_now": build["ready_now"], "buildable_any": build["ready_now"] + build["ready_with_constraints"],
            "outreach": build["outreach_required"] + build["not_buildable_now"],
            "oauth2_pct": pct(auth["oauth2"], n), "api_key_pct": pct(auth["api_key"], n),
            "official_mcp": sum(r.get("official_mcp") == "yes" for r in final),
            "composio_covered": sum(r.get("composio_toolkit") == "yes" for r in final),
            "easy_wins": len(easy_wins),
        },
        "auto_headline": (f"{top_auth[0]} is the most common auth ({top_auth[1]} of {n} apps); "
                          f"{pct(self_serve_n, n)}% are self-serve vs {pct(gated_n, n)}% gated; "
                          f"{build['ready_now']} apps are buildable today, and the most common blocker is "
                          f"{top_blocker[0].replace('_', ' ')} ({top_blocker[1]} apps)."),
        "auth": dict(auth.most_common()), "credential_access": dict(cred.most_common()),
        "buildability": dict(build.most_common()), "blockers": dict(blockers.most_common()),
        "api_styles": dict(styles.most_common()),
        "by_category": {k: dict(v) for k, v in by_cat.items()},
        "easy_wins": easy_wins, "outreach": outreach,
        "low_confidence_left": [r["app"] for r in final if r.get("confidence") == "low" and not str(r.get("review_status", "")).startswith("human")],
        "verification": {
            "pass1": read_json(FLAGS_DIR / "pass1_summary.json"),
            "pass2": read_json(FLAGS_DIR / "pass2_summary.json"),
            "accuracy": read_json(ACCURACY_JSON),
            "composio_method": (read_json(COMPOSIO_JSON, {}) or {}).get("method"),
            "changed_in_pass2": sum(1 for r in final if r.get("changes") and not str(r["changes"]).startswith(("not flagged", "flagged, not re-checked"))
                                    and str(r["changes"]).strip().lower() != "none"),
        },
    }


def main():
    final = build_final()
    cols = ["id", "app", "category", "description", "auth_methods", "credential_access", "credential_notes",
            "api_styles", "api_breadth", "official_mcp", "mcp_notes", "composio_toolkit", "buildability",
            "primary_blocker", "rationale", "confidence", "review_status", "evidence_urls"]
    write_csv(FINAL_CSV, final, cols)
    write_json(FINAL_CSV.with_suffix(".json"), final)
    a = analyze(final)
    write_json(ANALYSIS_JSON, a)
    print(a["auto_headline"])
    print("KPIs:", a["kpis"])
    print(f"Wrote {FINAL_CSV} and {ANALYSIS_JSON}")


if __name__ == "__main__":
    main()
