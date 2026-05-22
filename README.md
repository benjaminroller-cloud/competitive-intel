# Competitive Intelligence — Weekly Run

Weekly scraper, diff engine, and reporting workflow for vMVPD competitors.

## What this does

Every Monday morning, this project:

1. Scrapes pricing & package pages from 7 vMVPD competitors
2. Pulls industry news from RSS feeds + per-competitor Google News searches
3. Diffs this week's snapshots against last week's, producing structured change events
4. Hands the structured output to Claude (via Cowork) to write the HTML report
5. Claude drafts an email; you review and send

The Python does the mechanical work. The narrative work — interpreting changes,
writing "why it matters" — happens in the Cowork chat, with a human review pass
before anything is sent.

## File layout

```
competitive-intel/
├── HANDOFF.md               # READ FIRST in any new session
├── HANDOFF_HISTORY.md       # append-only revision log
├── README.md
├── requirements.txt
├── .gitignore               # snapshots/news/events stay out of git
├── config/
│   ├── competitors.yml      # who to track, where to scrape
│   ├── news_feeds.yml       # RSS feeds
│   └── channel_aliases.yml  # channel name normalization table
├── lib/
│   ├── __init__.py
│   ├── normalize.py         # canonicalize channel names
│   ├── health_gate.py       # detect bad scrapes
│   └── scrapers/
│       ├── __init__.py
│       ├── base.py          # parser interface + slugify helper
│       ├── philo.py         # reference implementation
│       └── *.py             # six skeleton parsers
├── docs/
│   ├── dashboard_sketch.html        # the visual design target
│   └── ci_data_model_samples.xlsx   # schema reference with sample rows
├── scrape.py                # weekly scrape orchestrator
├── diff.py                  # weekly diff engine
├── run_weekly.py            # Monday morning entry point
└── (created at runtime, not in git:)
    ├── snapshots/<week>/<competitor>.json
    ├── news/<week>.json
    ├── events/<week>.json
    └── reports/<week>_report.html
```

## Setup

```bash
git clone <repo-url>
cd competitive-intel
pip install -r requirements.txt
```

## The Monday morning workflow

1. Cowork triggers `python run_weekly.py`
2. The script writes the week's snapshots, news, and events to disk
3. You open Cowork; Claude reads `events/<this_monday>.json` and `news/<this_monday>.json`
4. Claude drafts the HTML report into `reports/<this_monday>_report.html`
5. You review on screen, ask for edits
6. Claude drafts the email; you hit send

## Status as of initial build

| Competitor      | Parser status         |
|-----------------|-----------------------|
| Philo           | ✅ reference impl     |
| YouTube TV      | ⚠ skeleton (TODO)     |
| Hulu + Live TV  | ⚠ skeleton (TODO)     |
| Fubo            | ⚠ skeleton (TODO)     |
| Sling TV        | ⚠ skeleton (TODO)     |
| DirecTV Stream  | ⚠ skeleton (TODO)     |
| Frndly TV       | ⚠ skeleton (TODO)     |

The six skeleton parsers raise `NotImplementedError` and will produce 'failed'
snapshots until they're implemented. We'll fill them in one at a time in
subsequent sessions by looking at the actual HTML of each site.

## Things deliberately not done yet

- **Promo snapshots** — schema is designed but the scrapers and diff don't
  capture promo prices separately yet. Easy add when needed.
- **Add-on snapshots** — out of scope per current decision.
- **LLM annotation in the pipeline** — by design. Annotation happens in the
  Cowork chat, not the script.
- **Email send** — by design. Email goes out via human review, not automation.
- **Cloud storage of history** — local folder is the starting point; revisit
  after first month.

## Adding a new competitor

1. Add a row to `config/competitors.yml`
2. Create `lib/scrapers/<name>.py` following `philo.py` as the template
3. Done. The orchestrator picks it up on the next run.

## Adding a channel alias

Edit `config/channel_aliases.yml`. The normalizer reloads on import; in
long-running processes, call `normalize.reload_aliases()`.
