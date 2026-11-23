# Agent toolkit research: 100 apps

Composio take-home. A small agent pipeline that researches 100 apps (auth, self-serve vs gated, API surface,
MCP, buildability), verifies its own answers, measures its accuracy against a hand-checked sample, and
publishes one self-explanatory HTML page.

**Live page:** _add Vercel link_ · **Run sheet:** [START_HERE.md](START_HERE.md)

## How it works

```
apps.csv ─► research agent (pass 1) ─► auto-verify ─► fact-checker (pass 2, flagged apps only) ─┐
               Gemini + official docs     rules + link checks                                   ├─► analyze ─► site/index.html
Composio SDK ─► "already a toolkit?" ───────────────────────────────────────────────────────────┤
20-app sample ─► blind auditor agent ─► human check vs official docs ─► accuracy score ─────────┘
```

| Script | Role |
|---|---|
| `agent/01_extract_apps.py` | Parses the 100 apps from the brief into `data/apps.csv` (asserts 10 × 10). |
| `agent/02_research.py` | **The agent.** Gemini 3.5 Flash-Lite reading official docs via the URL-context tool (the model first proposes the vendor's official auth, pricing, API and MCP pages; only pages actually fetched count as sources). Modes: `pass1` (all apps), `pass2` (re-research flagged apps as a fact-checker), `audit` (blind, independent research of the sample). Controlled vocabulary, evidence URLs required, one JSON per app, resumable. |
| `agent/03_verify.py` | Deterministic verification: schema, internal logic (e.g. "ready now" can't be partner-gated), fetches every evidence URL, checks the claimed auth appears on the page, flags low confidence. |
| `agent/04_composio_lookup.py` | Composio SDK call listing existing toolkits, matched to the 100 apps. |
| `agent/05_audit.py` | Stratified sample (2 per category, fixed seed), human checklist, and scoring of pass 1 vs pass 2 against the human gold set. |
| `agent/06_analyze.py` | Builds the final dataset and computes every pattern and number shown on the page. |
| `agent/07_build_site.py` | Generates the single self-contained `site/index.html` (+ CSV/JSON for agents). |

## Where a human was needed

- Choosing the controlled vocabulary and the definitions of "self-serve", "gated" and "buildable".
- Hand-checking the 20-app audit sample against official docs (`review/human_audit.csv`). This is the ground truth for accuracy.
- Confirming fuzzy Composio name matches.
- Writing the pattern summary (`review/insights.md`) from the computed numbers.

## Run it

Python 3.10+. Free keys only: Gemini (aistudio.google.com) and Composio.

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                                  # add GEMINI_API_KEY and COMPOSIO_API_KEY
python agent/01_extract_apps.py
python agent/02_research.py --mode pass1              # add --only 1 2 3 to try a few apps
python agent/03_verify.py --stage pass1
python agent/02_research.py --mode pass2
python agent/03_verify.py --stage pass2
python agent/04_composio_lookup.py
python agent/05_audit.py sample
python agent/02_research.py --mode audit
python agent/05_audit.py checklist                    # then fill review/human_audit.csv by hand
python agent/05_audit.py score
python agent/06_analyze.py
python agent/07_build_site.py --repo <repo url> --live <vercel url>
```

Deploy: import the repo into Vercel with **Root Directory = `site`**, framework "Other", no build command.

## Limitations

- Accuracy is measured on 20 hand-checked apps, not all 100. The sample is stratified and random (2 per category), not a separate held-out split: prompts were not tuned on it, but it is the only test set.
- The human labels started from the blind auditor's answers, so there is some anchoring risk. 18 of 20 rows were corrected, each with a note.
- Some docs sites block bots or render with JavaScript, so their evidence links are "unverifiable" rather than confirmed, and the model may fill gaps from memory.
- Gating is one column. Sandbox vs production access and extra requirements (developer tokens, app review, business verification) are not split out, so gating is the least reliable field.
- MCP is official yes/no; community MCP servers appear only in notes. Composio coverage is a separate cross-check from Composio's catalog and was never fed to the research agent.
- Temperature 0.2 on an overloaded model, so reruns can differ slightly.
- Results reflect the docs on the day the agent ran.
- Google Search grounding was the original design, but the free Gemini keys returned 429 quota errors for search, so the agent reads official pages it proposes itself via URL context. It can miss pages it does not think to read (e.g. a newly announced MCP server).
