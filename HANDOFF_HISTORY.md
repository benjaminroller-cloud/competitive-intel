# HANDOFF_HISTORY.md

Append-only log of revisions to `HANDOFF.md`. Newest entries at the top.

Read `HANDOFF.md` first; only consult this file if you need older context or want to see how decisions evolved.

---

## v1.1 — 2026-05-22 — Session 1 (continued): Repo prep

**Session summary**: Reorganized the project for GitHub. Restored the proper directory layout (project files had flattened on upload — `lib/` and `lib/scrapers/` weren't being preserved). Added `.gitignore` to keep scraped data (snapshots/news/events/reports) out of version control. Added `requirements.txt`. Added empty `__init__.py` files in `lib/` and `lib/scrapers/` so Python recognizes them as packages. Moved the dashboard sketch HTML and the sample data workbook into `docs/` so the design artifacts travel with the code. Removed `Run_Weekly_Diff.py` — that file was pseudocode from the design discussion that got mistakenly saved as a project file; it referenced functions that don't exist and was never runnable. The real diff engine is `diff.py`.

**Decisions made this session**:
- Project lives on GitHub (public repo), not in conversation uploads
- Scraped data stays local — never committed to git
- Design artifacts (dashboard sketch, data workbook) live in `docs/` alongside code

**Next session's first task**: Same as v1.0 — build the Sling parser. The reorganization didn't change the technical roadmap.

---

## v1.0 — 2026-05-22 — Session 1: Initial build

**Session summary**: Designed the project from scratch in conversation with the user. Established audience (executives + retention + acquisition, unified view, on-demand), data sources (web scraping + RSS news), and constraints (weekly, file-based, no paid API keys, Monday Cowork run, email via human review). Worked through dashboard sketch, data model (7 tables), and change-detection logic (5-pass diff). Built the initial codebase: config files, normalize/health-gate libraries, Philo parser as reference implementation, six skeleton parsers, scrape orchestrator, diff engine, run_weekly entry point. Verified diff logic end-to-end on synthetic data (price changes, channel adds, channel_moved_tier reconciliation all produced correct events).

**Decisions made this session**:
- 7-competitor list locked: Philo, YouTube TV, Hulu + Live TV, Fubo, Sling, DirecTV Stream, Frndly
- Disney/Fubo JV reflected in `competitors.yml` via `parent_company` and `affiliations` fields
- Two-week confirmation for removals, immediate emission for additions
- $1.00 price change threshold; 20% volume anomaly threshold
- No LLM in the script — annotation lives in Cowork chat
- One parser per competitor, isolated under `lib/scrapers/`
- File-based storage to start, revisit cloud after first month
- Add-ons skipped; skinny bundles tracked as packages

**Next session's first task**: Build the Sling parser (parser #2). Then live-test against Philo. Then schedule the Cowork weekly trigger.

**Files produced outside the repo**: dashboard sketch HTML, sample data workbook (xlsx). Both delivered to user via downloads.

---

<!-- Add new entries above this line, newest first.
     Each entry: ## vX.Y — YYYY-MM-DD — Session N: short title
                  one-paragraph summary
                  bullet list of decisions made
                  next session's first task
-->
