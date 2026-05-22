"""Weekly diff. Reads this week's and last week's snapshots, produces change events.

Implements the five-pass logic discussed in the design phase:
  1. Health gate — skip competitors whose scrapes failed
  2. Package-level diff — package_added, package_removed (2-week grace), price_change
  3. Channel-level raw diff — adds and removes per package
  4. Cross-package reconciliation — collapses add+remove of same channel into channel_moved_tier
  5. Promo diff — (TODO: not yet implemented)

Output: events/<scrape_week>.json containing all detected change_events.
No LLM calls. The 'why_it_matters' field is left empty; that's filled in
Monday morning via the Cowork chat.
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.normalize import normalize

PRICE_CHANGE_THRESHOLD_CENTS = 100  # $1.00 minimum to count as a change


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def load_snapshot(competitor_id: str, week: date) -> dict | None:
    path = PROJECT_ROOT / "snapshots" / week.isoformat() / f"{competitor_id}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def find_pkg(packages: list[dict], slug: str) -> dict | None:
    for p in packages:
        if p["package_slug"] == slug:
            return p
    return None


def diff_competitor(
    competitor_id: str,
    current_week: date,
) -> list[dict]:
    """Run the five-pass diff for one competitor. Returns a list of event dicts."""
    events: list[dict] = []
    current = load_snapshot(competitor_id, current_week)
    previous = load_snapshot(competitor_id, current_week - timedelta(days=7))
    two_weeks_ago = load_snapshot(competitor_id, current_week - timedelta(days=14))

    # --- Step 1: health gate ---
    if not current or not previous:
        return events  # first scrape or missing data; nothing to diff
    if current["scrape_health"] == "failed":
        return events
    if previous["scrape_health"] == "failed":
        return events  # nothing trustworthy to compare against

    curr_packages = {p["package_slug"]: p for p in current["packages"]}
    prev_packages = {p["package_slug"]: p for p in previous["packages"]}

    # --- Step 2: package-level diff ---
    # Additions: fire immediately
    for slug in curr_packages.keys() - prev_packages.keys():
        pkg = curr_packages[slug]
        events.append({
            "event_type": "package_added",
            "competitor_id": competitor_id,
            "package_slug": slug,
            "before_value": None,
            "after_value": {
                "package_name": pkg["package_name"],
                "rack_price_cents": pkg["rack_price_cents"],
                "channel_count": pkg["channel_count"],
            },
            "confidence": 1.0,
            "scrape_week": current_week.isoformat(),
        })

    # Removals: require two-week confirmation
    for slug in prev_packages.keys() - curr_packages.keys():
        was_present_two_weeks_ago = (
            two_weeks_ago
            and two_weeks_ago.get("scrape_health") != "failed"
            and any(p["package_slug"] == slug for p in two_weeks_ago.get("packages", []))
        )
        if was_present_two_weeks_ago:
            events.append({
                "event_type": "package_removed",
                "competitor_id": competitor_id,
                "package_slug": slug,
                "before_value": {
                    "package_name": prev_packages[slug]["package_name"],
                },
                "after_value": None,
                "confidence": 0.9,
                "scrape_week": current_week.isoformat(),
            })
        # else: still in 1-week grace period; emit nothing

    # Price changes on surviving packages
    surviving = curr_packages.keys() & prev_packages.keys()
    for slug in surviving:
        curr = curr_packages[slug]
        prev = prev_packages[slug]
        if curr["rack_price_cents"] < 0 or prev["rack_price_cents"] < 0:
            continue  # don't diff against unknown prices
        delta = abs(curr["rack_price_cents"] - prev["rack_price_cents"])
        if delta >= PRICE_CHANGE_THRESHOLD_CENTS:
            confidence = 0.7 if current["scrape_health"] == "partial" else 1.0
            events.append({
                "event_type": "price_change",
                "competitor_id": competitor_id,
                "package_slug": slug,
                "before_value": {"cents": prev["rack_price_cents"]},
                "after_value": {"cents": curr["rack_price_cents"]},
                "confidence": confidence,
                "scrape_week": current_week.isoformat(),
            })

    # --- Step 3: raw channel-level diff ---
    # Skip channel diffs entirely if either snapshot is partial — too risky
    if current["scrape_health"] != "success" or previous["scrape_health"] != "success":
        return events

    raw_adds: list[tuple[str, str]] = []     # (package_slug, canonical_channel)
    raw_removes: list[tuple[str, str]] = []

    for slug in surviving:
        curr = curr_packages[slug]
        prev = prev_packages[slug]
        # Empty channel lists mean the parser didn't extract them; don't diff
        if not curr.get("channel_list") or not prev.get("channel_list"):
            continue
        curr_channels = {normalize(c) for c in curr["channel_list"]}
        prev_channels = {normalize(c) for c in prev["channel_list"]}
        for ch in curr_channels - prev_channels:
            raw_adds.append((slug, ch))
        for ch in prev_channels - curr_channels:
            raw_removes.append((slug, ch))

    # --- Step 4: cross-package reconciliation ---
    adds_by_channel: dict[str, list[str]] = defaultdict(list)
    removes_by_channel: dict[str, list[str]] = defaultdict(list)
    for slug, ch in raw_adds:
        adds_by_channel[ch].append(slug)
    for slug, ch in raw_removes:
        removes_by_channel[ch].append(slug)

    moved_channels = set(adds_by_channel) & set(removes_by_channel)

    for ch in moved_channels:
        from_slugs = removes_by_channel[ch]
        to_slugs = adds_by_channel[ch]
        # Tier direction: compare prices of from/to packages
        from_price = max(
            (curr_packages[s]["rack_price_cents"] for s in from_slugs if s in curr_packages),
            default=-1,
        )
        # Actually look at where the channel WAS, which is in prev packages
        from_price = max(
            (prev_packages[s]["rack_price_cents"] for s in from_slugs if s in prev_packages),
            default=-1,
        )
        to_price = min(
            (curr_packages[s]["rack_price_cents"] for s in to_slugs if s in curr_packages),
            default=-1,
        )
        direction = "unknown"
        if from_price >= 0 and to_price >= 0:
            direction = "up" if to_price > from_price else ("down" if to_price < from_price else "lateral")

        events.append({
            "event_type": "channel_moved_tier",
            "competitor_id": competitor_id,
            "channel_name": ch,
            "before_value": {"from_packages": from_slugs},
            "after_value": {"to_packages": to_slugs, "direction": direction},
            "confidence": 0.95,
            "scrape_week": current_week.isoformat(),
        })

    # Emit remaining real adds and removes
    for slug, ch in raw_adds:
        if ch in moved_channels:
            continue
        events.append({
            "event_type": "channel_added",
            "competitor_id": competitor_id,
            "package_slug": slug,
            "channel_name": ch,
            "before_value": None,
            "after_value": {"channel": ch, "package_slug": slug},
            "confidence": 0.9,
            "scrape_week": current_week.isoformat(),
        })
    for slug, ch in raw_removes:
        if ch in moved_channels:
            continue
        events.append({
            "event_type": "channel_removed",
            "competitor_id": competitor_id,
            "package_slug": slug,
            "channel_name": ch,
            "before_value": {"channel": ch, "package_slug": slug},
            "after_value": None,
            "confidence": 0.85,
            "scrape_week": current_week.isoformat(),
        })

    return events


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--week", help="ISO date of any day in the target week; defaults to today", default=None)
    args = p.parse_args()

    import yaml
    target = date.fromisoformat(args.week) if args.week else date.today()
    scrape_week = monday_of(target)
    print(f"=== Diff week: {scrape_week.isoformat()} ===")

    with open(PROJECT_ROOT / "config" / "competitors.yml") as f:
        competitors = yaml.safe_load(f)["competitors"]

    all_events: list[dict] = []
    for c in competitors:
        if not c.get("active", True):
            continue
        events = diff_competitor(c["competitor_id"], scrape_week)
        print(f"[{c['competitor_id']}] {len(events)} events")
        all_events.extend(events)

    out_path = PROJECT_ROOT / "events" / f"{scrape_week.isoformat()}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"scrape_week": scrape_week.isoformat(), "events": all_events}, f, indent=2)

    print(f"\nTotal events: {len(all_events)}")
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
