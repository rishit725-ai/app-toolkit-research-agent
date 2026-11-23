# START HERE: step-by-step run sheet

Target: submit by **10:30 PM**. Every command runs in **PowerShell** from inside the `compozio` folder.
Times are rough. Steps marked 👤 need you; the rest just run.

---

## Step 0 · One-time setup (10 min)

```powershell
cd "$HOME\OneDrive\Desktop\compozio"
py -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass      # only needed so the next line is allowed
.\.venv\Scripts\Activate.ps1                  # your prompt now starts with (.venv)
pip install -r requirements.txt
```

### 👤 Put your keys in a `.env` file (never paste keys into chat or code)

```powershell
copy .env.example .env
notepad .env
```

In Notepad, fill in the two lines and save:

```
GEMINI_API_KEY=AIza...your key...
COMPOSIO_API_KEY=...your key...
```

- **Gemini key:** aistudio.google.com → **Get API key** → copy it.
- **Composio key:** log in at the Composio dashboard → **Settings → API Keys** → create/copy one.
  (You do NOT need to add Composio as a Claude connector. The take-home needs *your code* to call Composio, and the key above is what lets it.)

`.env` is listed in `.gitignore`, so it will never be pushed to GitHub. Every script reads it automatically.

---

## Step 1 · Extract the 100 apps (1 min)

```powershell
python agent/01_extract_apps.py
```
Expect: `Wrote 100 apps across 10 categories`. Output: `data/apps.csv`.

## Step 2 · Smoke test the agent on 2 apps (3 min)

```powershell
python agent/02_research.py --mode pass1 --only 1 61
```
Open `data/research/pass1/001-salesforce.json` and `061-github.json`. Do they look sensible?
If yes, continue. If something is off, tell Claude what you see before running all 100.

## Step 3 · Research all 100, pass 1 (30–40 min, runs by itself)

```powershell
python agent/02_research.py --mode pass1
```
- It saves each app as it finishes. If it stops (rate limit, laptop sleep), **run the same command again**: it skips finished apps.
- If you hit the daily free quota, add `GEMINI_MODEL=gemini-3.1-flash-lite` to `.env` and rerun.
- While it runs, do Step 4 in a second PowerShell window (activate `.venv` there too).

## Step 4 · Composio lookup (2 min)

```powershell
python agent/04_composio_lookup.py
```
Prints which apps Composio already has a toolkit for. 👤 Look at any `fuzzy_needs_review` rows; if the match is wrong,
edit `data/composio_toolkits.json` and set `"composio_toolkit"` to `false` (or `true` if it is right).

## Step 5 · Verification loop (15–25 min)

```powershell
python agent/03_verify.py --stage pass1        # rules + evidence-link checks, flags problem apps
python agent/02_research.py --mode pass2       # fact-checker re-researches only the flagged apps
python agent/03_verify.py --stage pass2        # check again, to show the flags went down
```
**pass1 is never edited after this point.** It is the "before" for the accuracy story.

## Step 6 · 👤 Blind audit + your hand check (45 min, the most important step)

```powershell
python agent/05_audit.py sample                # 20 apps, 2 per category, fixed seed
python agent/02_research.py --mode audit       # an independent auditor agent researches those 20 blind
python agent/05_audit.py checklist             # creates review/human_audit.csv
```

Open `review/human_audit.csv` in Excel. For each of the 20 rows (~2 min each):
1. Open the links in `docs_to_open` (or search the vendor's developer docs yourself).
2. Check each value: `auth_methods`, `credential_access`, `api_styles`, `official_mcp`, `buildability`, `primary_blocker`.
   Allowed values and their meaning are in `review/allowed_values.md`.
3. If a value is wrong, **overwrite it with the correct one**.
4. Set `status` to `confirmed` (all right), `corrected` (you changed something) or `unresolved` (docs don't settle it).
5. Add a short `your_note` when you correct something, e.g. "Pricing page: API needs Enterprise plan".

Save as CSV (keep the name). Then:

```powershell
python agent/05_audit.py score
```
Prints pass1 vs pass2 accuracy against your answers. Misses go to `data/audit_diffs.csv`.

## Step 7 · Analyze (1 min)

```powershell
python agent/06_analyze.py
```
Then tell Claude it's done. Claude will read `data/analysis.json` and draft `review/insights.md`
(the headline and pattern bullets at the top of the page). 👤 Edit it so it sounds like you.

## Step 8 · Build the page (1 min)

```powershell
python agent/07_build_site.py --repo https://github.com/YOUR-NAME/composio-toolkit-research
start site\index.html
```

## Step 9 · 👤 Publish (15 min)

1. Create an empty **public** GitHub repo (e.g. `composio-toolkit-research`), then:
   ```powershell
   git init; git add .; git commit -m "Agent toolkit research"
   git branch -M main
   git remote add origin https://github.com/YOUR-NAME/composio-toolkit-research.git
   git push -u origin main
   ```
   Before pushing, run `git status` and make sure `.env` is **not** listed.
2. vercel.com → **Add New → Project** → import the repo → **Root Directory: `site`**, Framework: **Other**, no build command → Deploy.
3. Rebuild with the live link and push again:
   ```powershell
   python agent/07_build_site.py --repo https://github.com/YOUR-NAME/composio-toolkit-research --live https://YOUR-PROJECT.vercel.app
   git add .; git commit -m "Add live link"; git push
   ```
4. Submit the Vercel link + the repo link.

---

## What to review (for you, so you can explain it)

| Folder | What's in it | Review? |
|---|---|---|
| `agent/` | The 7 scripts, numbered in run order. `02_research.py` is "the agent". | Yes: read the prompts in `02_research.py` and the checks in `03_verify.py` |
| `data/` | Everything the scripts produce. One JSON per app per stage. | Skim |
| `review/` | The only files **you** edit: `human_audit.csv`, `insights.md` | Yes |
| `site/` | The generated page. Never edit by hand; rerun step 8. | Look at it |
| `task/` | The original brief | — |

If any command errors, copy the error into the chat and Claude will fix it.
