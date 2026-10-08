"""Track prices and sales of the top AliExpress products for a search over time.

Run it on a schedule (cron, Task Scheduler, CI). Every run appends a snapshot to
a CSV history file and prints what changed since the previous run.

python examples/price_watch.py "mechanical keyboard"
python examples/price_watch.py "robot vacuum" --top 30 --history vacuums.csv
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

from aliexpress_scraper import AliExpressScraper

FIELDS = ["checked_at", "id", "price", "currency", "sold", "rating", "title", "url"]


def last_snapshot(path: Path) -> dict[str, dict[str, str]]:
    """The most recent row per product ID in the history file."""
    if not path.exists():
        return {}
    latest: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            latest[row["id"]] = row
    return latest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("query", help="Search keywords")
    parser.add_argument("--top", type=int, default=20, help="Products to track")
    parser.add_argument("--history", default="price_history.csv")
    args = parser.parse_args()

    history = Path(args.history)
    before = last_snapshot(history)
    ali = AliExpressScraper()  # reads SCRAPEUNBLOCKER_KEY
    products = ali.search(args.query, sort="orders", limit=args.top, skip_sponsored=True)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    is_new = not history.exists()
    with history.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        for p in products:
            writer.writerow(
                {
                    "checked_at": now,
                    "id": p.id,
                    "price": p.price,
                    "currency": p.currency,
                    "sold": p.sold,
                    "rating": p.rating,
                    "title": p.title,
                    "url": p.url,
                }
            )
            old = before.get(p.id)
            if old is None:
                print(f"new      {p.price} {p.currency}  {(p.title or '')[:60]}")
                continue
            if old["price"] and p.price is not None and float(old["price"]) != p.price:
                print(f"price    {old['price']} -> {p.price} {p.currency}  {(p.title or '')[:60]}")
            if old["sold"] and p.sold is not None and p.sold > int(old["sold"]):
                print(f"sold     +{p.sold - int(old['sold'])}  {(p.title or '')[:60]}")
    print(f"{len(products)} products checked, history in {history}")


if __name__ == "__main__":
    main()
