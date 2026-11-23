"""Step 1: turn the 100-app tables in the task brief into data/apps.csv.

Run:  python agent/01_extract_apps.py
"""
import re
from collections import Counter

from common import APPS_CSV, TASK_FILE, write_csv

LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def clean_hint(cell):
    """'[zoho.com/crm](http://zoho.com/crm) (note)' -> ('https://zoho.com/crm', 'zoho.com/crm (note)')."""
    m = LINK.search(cell)
    url = m.group(2) if m else cell.split()[0]
    text = LINK.sub(lambda x: x.group(1), cell).strip()
    url = url.rstrip("/")
    if "." not in url:           # e.g. "paygent (NMI-powered)" is a hint, not a URL
        return "", text
    if not url.startswith("http"):
        url = "https://" + url
    return url.replace("http://", "https://"), text


def main():
    text = TASK_FILE.read_text(encoding="utf-8")
    apps, category = [], None
    for line in text.splitlines():
        h = re.match(r"^###\s+\d+\.\s+(.+)$", line.strip())
        if h:
            category = h.group(1).strip()
            continue
        row = re.match(r"^\|\s*(\d+)\s*\|(.+?)\|(.+?)\|\s*$", line.strip())
        if row and category:
            name = LINK.sub(lambda x: x.group(1), row.group(2)).strip()
            url, hint = clean_hint(row.group(3).strip())
            apps.append({"id": int(row.group(1)), "app": name, "category": category,
                         "official_url": url, "hint": hint})

    ids = [a["id"] for a in apps]
    per_cat = Counter(a["category"] for a in apps)
    assert len(apps) == 100 and len(set(ids)) == 100, f"expected 100 unique apps, got {len(apps)}"
    assert len(per_cat) == 10 and set(per_cat.values()) == {10}, f"expected 10x10, got {per_cat}"

    write_csv(APPS_CSV, apps, ["id", "app", "category", "official_url", "hint"])
    print(f"Wrote {len(apps)} apps across {len(per_cat)} categories to {APPS_CSV}")
    for c, n in per_cat.items():
        print(f"  {n:>3}  {c}")


if __name__ == "__main__":
    main()
