"""Weekly scraper. Run once per week (Monday morning).

For each active competitor:
  1. Fetch the pricing page HTML
  2. Hand it to the competitor's parser
  3. Apply health gates (volume anomaly vs last week)
  4. Write the snapshot to snapshots/<scrape_week>/<competitor_id>.json

Also pulls RSS feeds and writes them to news/<scrape_week>.json.

The script never modifies a snapshot once written. All corrections happen
in a separate corrections/ file (not yet implemented).
"""

import argparse
import importlib
import json
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import yaml

# Make 'lib' importable from the project root
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.scrapers.base import PackageSnapshot, slugify
from lib.health_gate import apply_volume_check

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30


def monday_of(d: date) -> date:
    """Snap a date to the Monday of its week."""
    return d - timedelta(days=d.weekday())


def load_competitors() -> list[dict]:
    with open(PROJECT_ROOT / "config" / "competitors.yml") as f:
        return yaml.safe_load(f)["competitors"]


def load_previous_snapshot(competitor_id: str, current_week: date) -> dict | None:
    """Look for the previous week's snapshot for this competitor."""
    prev_week = current_week - timedelta(days=7)
    path = PROJECT_ROOT / "snapshots" / prev_week.isoformat() / f"{competitor_id}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def fetch_html(url: str) -> tuple[str, str]:
    """Fetch a URL. Returns (html, status). status is 'success' or 'failed'."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.text, "success"
    except Exception as e:
        print(f"  fetch failed: {e}", file=sys.stderr)
        return "", "failed"


def scrape_one(competitor: dict, scrape_week: date) -> dict:
    """Scrape one competitor. Returns the snapshot dict to write to disk."""
    cid = competitor["competitor_id"]
    print(f"[{cid}] fetching {competitor['pricing_url']}")
    html, fetch_status = fetch_html(competitor["pricing_url"])

    snapshot = {
        "competitor_id": cid,
        "display_name": competitor["display_name"],
        "scrape_week": scrape_week.isoformat(),
        "scrape_timestamp": datetime.utcnow().isoformat() + "Z",
        "source_url": competitor["pricing_url"],
        "zip_code": competitor.get("zip_code", "80112"),
        "parent_company": competitor.get("parent_company"),
        "affiliations": competitor.get("affiliations", []),
        "packages": [],
        "scrape_health": "failed",
        "errors": [],
    }

    if fetch_status == "failed":
        snapshot["errors"].append("HTTP fetch failed")
        return snapshot

    # Dispatch to the right parser
    try:
        parser_mod = importlib.import_module(f"lib.scrapers.{competitor['parser_module']}")
        packages: list[PackageSnapshot] = parser_mod.parse(html)
    except NotImplementedError as e:
        snapshot["errors"].append(f"Parser not implemented: {e}")
        return snapshot
    except Exception as e:
        snapshot["errors"].append(f"Parser raised: {e}\n{traceback.format_exc()}")
        return snapshot

    if not packages:
        snapshot["errors"].append("Parser returned zero packages")
        return snapshot

    # Convert to dicts
    snapshot["packages"] = [p.to_dict() for p in packages]
    snapshot["scrape_health"] = "success"

    # Apply volume anomaly check vs last week, per package
    previous = load_previous_snapshot(cid, scrape_week)
    if previous and previous.get("scrape_health") == "success":
        prev_packages_by_slug = {p["package_slug"]: p for p in previous.get("packages", [])}
        worst_health = "success"
        for pkg in snapshot["packages"]:
            prev_pkg = prev_packages_by_slug.get(pkg["package_slug"])
            prev_count = prev_pkg["channel_count"] if prev_pkg else None
            new_health = apply_volume_check(
                pkg["channel_count"], prev_count, "success"
            )
            if new_health == "partial":
                worst_health = "partial"
                snapshot["errors"].append(
                    f"Volume anomaly on {pkg['package_slug']}: "
                    f"{prev_count} -> {pkg['channel_count']}"
                )
        snapshot["scrape_health"] = worst_health

    return snapshot


def scrape_all_competitors(scrape_week: date) -> dict:
    """Scrape every active competitor and write results to disk.
    Returns a summary dict for logging."""
    competitors = load_competitors()
    week_dir = PROJECT_ROOT / "snapshots" / scrape_week.isoformat()
    week_dir.mkdir(parents=True, exist_ok=True)

    summary = {"success": [], "partial": [], "failed": []}
    for c in competitors:
        if not c.get("active", True):
            continue
        snap = scrape_one(c, scrape_week)
        out_path = week_dir / f"{c['competitor_id']}.json"
        with open(out_path, "w") as f:
            json.dump(snap, f, indent=2)
        summary[snap["scrape_health"]].append(c["competitor_id"])
        print(f"  -> {snap['scrape_health']}")

    return summary


def fetch_news(scrape_week: date) -> dict:
    """Pull RSS feeds. Returns a summary dict and writes news/<week>.json."""
    try:
        import feedparser
    except ImportError:
        print("feedparser not installed; skipping news", file=sys.stderr)
        return {"items": 0, "feeds_failed": 0}

    with open(PROJECT_ROOT / "config" / "news_feeds.yml") as f:
        cfg = yaml.safe_load(f)

    competitors = load_competitors()
    items = []
    feeds_failed = 0

    # Curated feeds
    for feed in cfg.get("feeds", []):
        try:
            parsed = feedparser.parse(feed["url"])
            for entry in parsed.entries[:25]:
                items.append({
                    "source_name": feed["name"],
                    "source_url": entry.get("link", ""),
                    "headline": entry.get("title", ""),
                    "published_at": entry.get("published", ""),
                    "category": feed["category"],
                })
        except Exception as e:
            print(f"feed {feed['name']} failed: {e}", file=sys.stderr)
            feeds_failed += 1

    # Per-competitor Google News searches
    for c in competitors:
        if not c.get("active", True):
            continue
        from urllib.parse import quote
        q = quote(f'"{c["display_name"]}" pricing OR package OR channel')
        url = f"https://news.google.com/rss/search?q={q}"
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries[:10]:
                items.append({
                    "source_name": "Google News",
                    "source_url": entry.get("link", ""),
                    "headline": entry.get("title", ""),
                    "published_at": entry.get("published", ""),
                    "category": "competitor_specific",
                    "competitor_id": c["competitor_id"],
                })
        except Exception as e:
            print(f"google news for {c['competitor_id']} failed: {e}", file=sys.stderr)
            feeds_failed += 1

    out_path = PROJECT_ROOT / "news" / f"{scrape_week.isoformat()}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"scrape_week": scrape_week.isoformat(), "items": items}, f, indent=2)

    return {"items": len(items), "feeds_failed": feeds_failed}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--week", help="ISO date of any day in the target week; defaults to today", default=None)
    args = p.parse_args()

    target = date.fromisoformat(args.week) if args.week else date.today()
    scrape_week = monday_of(target)
    print(f"=== Scrape week: {scrape_week.isoformat()} ===")

    summary = scrape_all_competitors(scrape_week)
    print("\n=== Scrape summary ===")
    for status, ids in summary.items():
        print(f"  {status}: {len(ids)} ({', '.join(ids) if ids else '-'})")

    print("\n=== News ===")
    news_summary = fetch_news(scrape_week)
    print(f"  items: {news_summary['items']}, feeds_failed: {news_summary['feeds_failed']}")


if __name__ == "__main__":
    main()
