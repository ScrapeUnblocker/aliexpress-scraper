"""Shortlist well-rated, proven AliExpress products for several niches, to CSV.

python examples/dropshipping_shortlist.py "pet hair remover" "led strip lights" "phone holder"
python examples/dropshipping_shortlist.py "yoga mat" --ship-from US --max-price 25
"""

from __future__ import annotations

import argparse

from aliexpress_scraper import AliExpressScraper, products_to_csv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("queries", nargs="+", help="One search per niche")
    parser.add_argument("--min-rating", type=float, default=4.6)
    parser.add_argument("--min-sold", type=int, default=500)
    parser.add_argument("--max-price", type=float, help="Highest price (storefront currency)")
    parser.add_argument("--ship-from", help="Only products shipping from this country, e.g. US")
    parser.add_argument("--pages", type=int, default=2, help="Pages per niche (60 products each)")
    parser.add_argument("--output", default="shortlist.csv")
    args = parser.parse_args()

    ali = AliExpressScraper()  # reads SCRAPEUNBLOCKER_KEY
    shortlist = ali.search_many(  # merged and de-duplicated across niches
        args.queries,
        sort="orders",
        pages=args.pages,
        max_price=args.max_price,
        ship_from=args.ship_from,
        min_rating=args.min_rating,
        min_sold=args.min_sold,
        skip_sponsored=True,
        on_query=lambda query, found: print(f"{query}: {len(found)} products kept"),
    )
    shortlist.sort(key=lambda p: (p.query or "", -(p.sold or 0)))
    products_to_csv(shortlist, args.output)
    print(f"{len(shortlist)} products written to {args.output}")


if __name__ == "__main__":
    main()
