# HANDOFF.md

```
last_updated: 2026-05-22
session: 1 (initial build, repo prep)
version: 1.1
changed_since_last: reorganized into GitHub repo layout; added .gitignore, requirements.txt, lib/__init__.py files; moved dashboard sketch + data workbook into docs/; removed Run_Weekly_Diff.py (was pseudocode, never runnable)
```

**Read this first.** Then check `HANDOFF_HISTORY.md` only if you need older context. If this file's `last_updated` is more than 2 weeks stale, ask the user before trusting it.

---

## What this project is

A weekly competitive intelligence pipeline for a US national vMVPD operator. Tracks pricing, packaging, and channel lineups for 7 competitors, plus industry news. Outputs a structured diff each Monday that Claude (in Cowork) turns into an HTML email report. The user reviews and sends the email manually.

**Audience for the report**: a single distribution list combining executives, retention, and acquisition teams. Mostly high-level info. One unified view, no role-based personalization.

**Hard constraints from the user**:
- No paid API keys anywhere (so no LLM calls in the script — annotation happens in Cowork chat)
- Local file storage to start (revisit cloud storage after first month)
- Email goes out via human review, not automation
- Weekly cadence, Monday morning
- Single market, zip code 80112

## Competitors tracked

| competitor_id    | parser status   | notes                                              |
|------------------|-----------------|----------------------------------------------------|
| philo            | ✅ reference    | simplest target; the implementation template       |
| youtube_tv       | ⚠ skeleton      | hardest — heavy JS, Google anti-bot                |
| hulu_live        | ⚠ skeleton      | Disney/Fubo JV with `fubo`                         |
| fubo             | ⚠ skeleton      | Disney/Fubo JV with `hulu_live`                    |
| sling            | ⚠ skeleton      | trickiest data shape (Orange/Blue parallel bases)  |
| directv_stream   | ⚠ skeleton      | standard ladder structure                          |
| frndly           | ⚠ skeleton      | low priority — only on list per user request       |

## Non-obvious decisions (and why)

**Asymmetric add/remove timing.** Package additions and channel additions fire immediately on detection. Removals require a two-week confirmation — present 2 weeks ago, missing 1 week ago, still missing this week. This is because false-positive additions are rare (you have to find data that doesn't exist) while false-positive removals are common (any scraping glitch produces apparent removals). See `diff.py` and the design discussion.

**$1.00 price change threshold.** Sub-dollar changes are ignored as noise but the new price still becomes the baseline for next week. Constant in `diff.py`: `PRICE_CHANGE_THRESHOLD_CENTS = 100`.

**20% volume anomaly threshold.** If channel_count moves more than ±20% week over week, downgrade the snapshot from `success` to `partial` regardless of what the scraper claimed. Constant in `lib/health_gate.py`: `VOLUME_ANOMALY_THRESHOLD = 0.20`. The diff engine refuses to emit channel-level events from partial snapshots.

**No LLM in the script.** Architectural choice driven by the no-paid-API-keys constraint. The Python produces structured `change_events`; the narrative ("why it matters") is written by Claude in the Cowork chat each Monday. Side benefit: human review of every report before send.

**Per-competitor parsers.** Each competitor's parsing logic lives in its own file under `lib/scrapers/`. When Comp B's HTML changes, only `comp_b.py` is at risk. Don't be tempted to "refactor common logic" — the common interface is `parse(html) -> list[PackageSnapshot]`; everything else should stay isolated.

**Disney/Fubo JV affiliation.** `competitors.yml` has `parent_company` and `affiliations` fields. Hulu+Live TV and Fubo are flagged as a JV (Disney 70% owner, deal closed Oct 2025). When both move in the same week, the report narrative should call that out — it's not coincidence, it's coordinated pricing power.

**channel_aliases.yml is a living document.** Every time we see a new variant of an existing channel name ("ESPN East" vs "ESPN", "Max" vs "HBO"), we add a line. Expect this file to grow weekly for the first 2-3 months before stabilizing.

## Current state

**Working:**
- Schema (7 tables): `competitors`, `package_snapshots`, `promo_snapshots`, `addon_snapshots`, `change_events`, `news_items`, plus derived dashboard views
- Diff engine: all 5 passes (health gate, package diff, channel diff, cross-package reconciliation, idempotent insert). Verified end-to-end on synthetic data including a `channel_moved_tier` test case.
- Philo parser (heuristic regex against page text — works on synthetic HTML, not yet validated against live site)
- Orchestrator (`run_weekly.py`) wires scrape + diff together
- News ingestion from RSS feeds + Google News per-competitor

**Not yet built:**
- 6 of 7 competitor parsers (all raise `NotImplementedError`)
- Promo snapshot scraping/diff (schema designed, code not written)
- Add-on snapshot scraping (deferred by user decision; skinny bundles tracked as packages instead)
- Playwright / JS rendering (will be needed for at least YouTube TV)
- Cloud storage of history

**Designed but not in repo:**
- Dashboard sketch (HTML wireframe) — produced in session 1, lives in user's downloads
- Data model sample workbook — produced in session 1, lives in user's downloads
- Channel-centric dashboard view (transposed matrix) — discussed but not built

## Where to pick up next session

**Decided in session 1, do this next:**
1. Build the Sling parser. Chosen as parser #2 because its Orange/Blue parallel base plans validate that the schema and slugging handle non-standard tier structures. If Sling works, the others will.
2. Test `run_weekly.py` end-to-end against the live Philo site to validate the orchestrator. Expect to discover that the heuristic regex needs replacement with CSS selectors against real HTML.
3. Only after #1 and #2 succeed, set up the Cowork weekly trigger.

**Then in following sessions, in this order:**
- DirecTV Stream parser (standard ladder, similar to Hulu Live; do these together)
- Hulu + Live TV parser
- Fubo parser
- Frndly parser
- YouTube TV parser (last, because it's hardest — will likely need Playwright)

## Open questions

These are punted, not forgotten:

- **Cloud storage.** Local folder is fine for the first month. After that, push for Google Drive or similar so a drive failure doesn't lose the dataset.
- **Channel-centric view.** Sketched in conversation but not in the repo. Worth building once we have 4-6 weeks of real data and can see if the transposed view actually answers different questions than the package view.
- **multiple to_packages in channel_moved_tier.** What if a channel is promoted into two tiers at once during a restructure? Current code handles it but the event shape may want a `restructure_id` to group related moves. Revisit when we see one in real data.
- **Frndly's continued inclusion.** User asked to track it; worth re-evaluating after a few weeks. If retention team confirms customers don't actually shop between us and Frndly, drop it to reduce scraping surface area.
- **The Disney/Fubo Sports & Broadcasting service.** Announced as part of the JV; not yet launched. When it appears in Fubo scrapes, it'll show up as a `package_added` event. Worth flagging proactively in the report when it lands.

## Pointers

In-repo artifacts:
- `docs/dashboard_sketch.html` — produced session 1; opens in any browser. Shows header strip, package matrix, activity feed, channel count, view toggle.
- `docs/ci_data_model_samples.xlsx` — produced session 1; 7 sheets with sample rows for every table plus a `join_example` sheet showing how the dashboard queries the schema. Authoritative reference for the schema.

External:
- **This conversation** (and subsequent Cowork sessions) — if saved, contains the full design reasoning. Reference for "why did we decide X" questions that this handoff doesn't answer.

Code pointers within this repo:
- `lib/scrapers/philo.py` — read this first to understand the parser contract
- `diff.py` — the heart of the project; the five-pass logic
- `config/competitors.yml` — add/remove competitors here, not in code

## Self-update protocol

When you finish a session that changes anything material, before closing the Cowork conversation:
1. Update this file's `last_updated`, `session`, `version`, and `changed_since_last` fields
2. Append a new entry to `HANDOFF_HISTORY.md` with the same info plus a 2-3 line summary of what the session accomplished
3. If you added or changed a non-obvious decision, add it to the "Non-obvious decisions" section above
4. If you completed something in "Not yet built", move it to "Working" and update the parser status table

Material changes that warrant a version bump:
- A parser moves from skeleton to working
- A new architectural decision is made
- A threshold or constant is changed
- A new competitor is added or removed
- An open question is resolved

Cosmetic edits (typos, wording) don't need a version bump but should still update `last_updated`.
