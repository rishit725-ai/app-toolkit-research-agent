"""Shared settings, paths, vocabulary and helpers used by every script in agent/.

Everything the pipeline reads or writes lives under data/, review/ or site/.
"""
import csv
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REVIEW = ROOT / "review"
SITE = ROOT / "site"
TASK_FILE = next((ROOT / "task").glob("*.md"), None)

APPS_CSV = DATA / "apps.csv"
RESEARCH = DATA / "research"          # research/pass1, research/pass2, research/audit
COMPOSIO_JSON = DATA / "composio_toolkits.json"
FLAGS_DIR = DATA / "flags"            # flags/pass1.csv, flags/pass2.csv
AUDIT_SAMPLE = DATA / "audit_sample.csv"
HUMAN_AUDIT = REVIEW / "human_audit.csv"
ACCURACY_JSON = DATA / "accuracy.json"
FINAL_CSV = DATA / "final.csv"
ANALYSIS_JSON = DATA / "analysis.json"
INSIGHTS_MD = REVIEW / "insights.md"


def load_env():
    """Read KEY=VALUE lines from .env into os.environ (no extra dependency needed)."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ---------------------------------------------------------------- vocabulary
# Controlled values keep 100 answers comparable, so the patterns can be counted.
VOCAB = {
    "auth_methods": ["oauth2", "api_key", "bearer_token", "basic", "jwt", "hmac_signature", "other", "none"],
    "credential_access": ["self_serve_free", "self_serve_trial", "paid_plan", "admin_approval",
                          "partner_or_sales_gated", "open_source_local", "unclear"],
    "api_styles": ["rest", "graphql", "soap", "websocket", "sdk_or_cli_only", "none"],
    "api_breadth": ["broad", "moderate", "narrow", "none", "unclear"],
    "official_mcp": ["yes", "no", "unclear"],
    "buildability": ["ready_now", "ready_with_constraints", "outreach_required", "not_buildable_now"],
    "primary_blocker": ["none", "credential_gate", "admin_or_partner_approval", "no_public_api",
                        "narrow_or_read_only_api", "unstable_or_undocumented", "local_only",
                        "compliance_or_scope", "unclear"],
    "confidence": ["high", "medium", "low"],
}
LIST_FIELDS = {"auth_methods", "api_styles"}
# Fields scored in the accuracy check (free text is not scored).
SCORED_FIELDS = ["auth_methods", "credential_access", "api_styles", "official_mcp",
                 "buildability", "primary_blocker"]

SELF_SERVE = {"self_serve_free", "self_serve_trial", "open_source_local"}
GATED = {"paid_plan", "admin_approval", "partner_or_sales_gated"}


# ---------------------------------------------------------------- io helpers
def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0].keys()) if rows else [])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _cell(v) for k, v in r.items()})


def _cell(v):
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return ";".join(v)
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return v


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def record_path(stage, app):
    return RESEARCH / stage / f"{int(app['id']):03d}-{slug(app['app'])}.json"


def load_stage(stage):
    """All records of one stage, keyed by app id (int)."""
    out = {}
    for p in sorted((RESEARCH / stage).glob("*.json")):
        r = read_json(p)
        if r and not r.get("error"):
            out[int(r["id"])] = r
    return out


def load_apps():
    return read_csv(APPS_CSV)


def norm_value(field, value):
    """Normalise a field value so two answers can be compared fairly."""
    if field in LIST_FIELDS:
        if isinstance(value, str):
            value = [v for v in re.split(r"[;,]", value) if v.strip()]
        return sorted({str(v).strip().lower() for v in (value or [])})
    return str(value or "").strip().lower()


def validate_record(r):
    """Return a list of schema problems (empty list = valid)."""
    problems = []
    for field, allowed in VOCAB.items():
        v = r.get(field)
        if field in LIST_FIELDS:
            if not isinstance(v, list) or not v:
                problems.append(f"{field} missing")
            elif any(x not in allowed for x in v):
                problems.append(f"{field} has value outside vocabulary: {v}")
        elif v not in allowed:
            problems.append(f"{field}={v!r} outside vocabulary")
    for field in ("description", "rationale"):
        if not str(r.get(field, "")).strip():
            problems.append(f"{field} empty")
    ev = r.get("evidence") or []
    if not ev:
        problems.append("no evidence links")
    for e in ev:
        if not str(e.get("url", "")).startswith("http"):
            problems.append(f"bad evidence url: {e.get('url')}")
    return problems
