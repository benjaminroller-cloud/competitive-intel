"""Monday morning entry point. Runs scrape then diff, then prints a summary
suitable for the Cowork chat to read at the start of the weekly report session.
"""

import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def main():
    scrape_week = monday_of(date.today())
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  Competitive Intel — Weekly Run              ║")
    print(f"║  Week of {scrape_week.isoformat()}                       ║")
    print(f"╚══════════════════════════════════════════════╝\n")

    print("STEP 1: scraping competitor sites + news feeds...")
    r = subprocess.run([sys.executable, str(PROJECT_ROOT / "scrape.py")], cwd=PROJECT_ROOT)
    if r.returncode != 0:
        print(f"\nscrape.py exited {r.returncode} — proceeding to diff anyway", file=sys.stderr)

    print("\nSTEP 2: running diff vs last week...")
    r = subprocess.run([sys.executable, str(PROJECT_ROOT / "diff.py")], cwd=PROJECT_ROOT)
    if r.returncode != 0:
        print(f"\ndiff.py exited {r.returncode}", file=sys.stderr)

    print("\n╔══════════════════════════════════════════════╗")
    print(f"║  Outputs ready in:                           ║")
    print(f"║    snapshots/{scrape_week.isoformat()}/                  ║")
    print(f"║    news/{scrape_week.isoformat()}.json                   ║")
    print(f"║    events/{scrape_week.isoformat()}.json                 ║")
    print(f"║                                              ║")
    print(f"║  Next: open Cowork to write the report.      ║")
    print(f"╚══════════════════════════════════════════════╝")


if __name__ == "__main__":
    main()
