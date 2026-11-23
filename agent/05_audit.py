"""Step 5: the accuracy audit (blind agent + human gold set).

  python agent/05_audit.py sample      pick 20 apps, 2 per category, fixed seed -> data/audit_sample.csv
  (then)  python agent/02_research.py --mode audit   independent agent researches those 20 blind
  python agent/05_audit.py checklist   make review/human_audit.csv for YOU to check against real docs
  (you)   open the docs, fix any wrong value in the CSV, set status = confirmed / corrected / unresolved
  python agent/05_audit.py score       compare pass1, pass2 and the audit agent with your answers

The checklist only shows the audit agent's answers, never pass1, so your check is not anchored on
the answers being scored.
"""
import argparse
import random
import sys
from collections import defaultdict

from common import (ACCURACY_JSON, AUDIT_SAMPLE, DATA, HUMAN_AUDIT, SCORED_FIELDS, load_apps,
                    load_stage, norm_value, read_csv, write_csv, write_json)

SEED = 20261123


def sample(size_per_category=2):
    by_cat = defaultdict(list)
    for a in load_apps():
        by_cat[a["category"]].append(a)
    rng = random.Random(SEED)
    picked = [a for cat in by_cat for a in rng.sample(by_cat[cat], size_per_category)]
    write_csv(AUDIT_SAMPLE, picked, ["id", "app", "category", "official_url", "hint"])
    print(f"Sampled {len(picked)} apps (seed {SEED}) -> {AUDIT_SAMPLE}")
    for a in picked:
        print(f"  {a['id']:>3}  {a['app']:<28} {a['category']}")


def checklist(force):
    if HUMAN_AUDIT.exists() and not force:
        sys.exit(f"{HUMAN_AUDIT} already exists (it may hold your answers). Use --force to rebuild it.")
    audit = load_stage("audit")
    rows = []
    for a in read_csv(AUDIT_SAMPLE):
        r = audit.get(int(a["id"]))
        if not r:
            print(f"  missing audit record for {a['app']}; run 02_research.py --mode audit first")
            continue
        row = {"id": a["id"], "app": a["app"], "category": a["category"],
               "docs_to_open": " | ".join(e["url"] for e in r.get("evidence", [])[:4])}
        for f in SCORED_FIELDS:
            v = r.get(f)
            row[f] = ";".join(v) if isinstance(v, list) else v
        row.update({"status": "", "your_note": "", "agent_notes": f"{r.get('credential_notes', '')} {r.get('auth_notes', '')}"})
        rows.append(row)
    fields = ["id", "app", "category", "status", "your_note"] + SCORED_FIELDS + ["docs_to_open", "agent_notes"]
    write_csv(HUMAN_AUDIT, rows, fields)
    print(f"Wrote {len(rows)} rows -> {HUMAN_AUDIT}\nNow follow 'Step 6' in START_HERE.md to check them by hand.")


def score():
    truth = {int(r["id"]): r for r in read_csv(HUMAN_AUDIT)}
    unchecked = [r["app"] for r in truth.values() if r["status"].strip() not in ("confirmed", "corrected", "unresolved")]
    if unchecked:
        print(f"WARNING: {len(unchecked)} rows have no status yet: {unchecked}")
    gold = {i: r for i, r in truth.items() if r["status"].strip() in ("confirmed", "corrected")}
    stages = {s: load_stage(s) for s in ("pass1", "pass2", "audit")}

    result, diffs = {"gold_apps": len(gold), "fields": SCORED_FIELDS, "stages": {}}, []
    for stage, recs in stages.items():
        per_field = {f: [0, 0] for f in SCORED_FIELDS}
        perfect = 0
        for i, g in gold.items():
            r = recs.get(i)
            if not r:
                continue
            all_ok = True
            for f in SCORED_FIELDS:
                ok = norm_value(f, r.get(f)) == norm_value(f, g[f])
                per_field[f][0] += ok
                per_field[f][1] += 1
                all_ok &= ok
                if not ok and stage in ("pass1", "pass2"):
                    diffs.append({"stage": stage, "id": i, "app": g["app"], "field": f,
                                  "agent": ";".join(norm_value(f, r.get(f))) if f in ("auth_methods", "api_styles") else r.get(f),
                                  "truth": g[f], "human_note": g["your_note"]})
            perfect += all_ok
        right = sum(v[0] for v in per_field.values())
        total = sum(v[1] for v in per_field.values())
        result["stages"][stage] = {
            "field_accuracy": round(right / total, 3) if total else None, "right": right, "total": total,
            "perfect_apps": perfect, "apps_scored": len([i for i in gold if i in recs]),
            "per_field": {f: round(v[0] / v[1], 3) if v[1] else None for f, v in per_field.items()}}
    result["human_status"] = {s: sum(1 for r in truth.values() if r["status"].strip() == s)
                              for s in ("confirmed", "corrected", "unresolved")}
    write_json(ACCURACY_JSON, result)
    write_csv(DATA / "audit_diffs.csv", diffs, ["stage", "id", "app", "field", "agent", "truth", "human_note"])

    for stage, s in result["stages"].items():
        if s["field_accuracy"] is not None:
            print(f"{stage:<6} field accuracy {s['field_accuracy']:.0%} ({s['right']}/{s['total']}), "
                  f"perfect apps {s['perfect_apps']}/{s['apps_scored']}")
    print(f"Misses listed in {DATA / 'audit_diffs.csv'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["sample", "checklist", "score"])
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    {"sample": sample, "checklist": lambda: checklist(args.force), "score": score}[args.action]()
