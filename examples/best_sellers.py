"""The best-selling AliExpress products for a search, as a table.

python examples/best_sellers.py "wireless earbuds"
python examples/best_sellers.py "phone case" --pages 2 --top 25 --country gb
"""

from __future__ import annotations

import argparse

from aliexpress_scraper import AliExpressScraper


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("query", help="Search keywords")
    parser.add_argument("--pages", type=int, default=1, help="Pages to read (60 products each)")
    parser.add_argument("--top", type=int, default=15, help="Rows to print")
    parser.add_argument("--country", default="us", help="Storefront (sets the currency)")
    args = parser.parse_args()

    ali = AliExpressScraper(country=args.country)  # reads SCRAPEUNBLOCKER_KEY
    products = ali.search(args.query, sort="orders", pages=args.pages, skip_sponsored=True)
    # "orders" is AliExpress's own popularity sort; re-sort by the exact count
    products.sort(key=lambda p: p.sold or 0, reverse=True)

    print(f"{'sold':>8}  {'rating':>6}  {'price':>10}  title")
    for p in products[: args.top]:
        price = f"{p.price:.2f} {p.currency}" if p.price is not None else "-"
        rating = f"{p.rating:.1f}" if p.rating is not None else "-"
        print(f"{p.sold or 0:>8,}  {rating:>6}  {price:>10}  {(p.title or '')[:70]}")


if __name__ == "__main__":
    main()
