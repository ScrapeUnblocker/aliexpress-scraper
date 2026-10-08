# AliExpress Scraper

[![CI](https://github.com/ScrapeUnblocker/aliexpress-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/ScrapeUnblocker/aliexpress-scraper/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Powered by ScrapeUnblocker](https://img.shields.io/badge/powered%20by-ScrapeUnblocker-6f42c1.svg)](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)

**Scrape [AliExpress](https://www.aliexpress.com) product search results into clean JSON
or CSV: prices, discounts, exact units sold, ratings, Choice and shipping flags, delivery
estimates and images, for any keyword or category, on any country storefront.** Use
AliExpress's own sorts and filters (best-selling, price, price range, free shipping,
Choice, ship-from country, attributes such as brand, colour or material) and collect up
to 60 pages of 60 products per search. Built for product research, dropshipping
shortlists and price monitoring.

Powered by [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos):
the `getPageSource` API loads every AliExpress page in a real browser and returns it, and
this package turns the JSON that AliExpress embeds in its search pages into typed records.
You don't need an AliExpress account or affiliate API key, proxies, a headless browser or
retry logic of your own.

## Features

- **Search any keyword or category.** Pass keywords, or paste any AliExpress search or
  category URL from your browser. 60 products per page, 60 pages per search. Several
  queries in one run are merged and de-duplicated.
- **AliExpress's own sorts and filters.** Sort by best match, orders, or price (ascending
  or descending). Filter by price range, free shipping, AliExpress Choice, ship-from
  country (e.g. products that ship from the US) and attribute values (brand, colour, material,
  compatible model, ...). The `filters` command lists the attribute values available for a
  search.
- **Filters are verified.** AliExpress silently ignores parameters it does not understand.
  Every page reports the sort and filters it actually applied, and this package raises an
  error if one was dropped, so you never get unfiltered data by mistake.
- **Clean product records.** Item ID, title, URL, sale price, original price, discount
  percentage, currency, exact units sold (plus the rounded `10,000+ sold` label), star
  rating, Choice / free-shipping / local-warehouse / sponsored / welcome-deal flags,
  delivery estimate in days and dates, listing date, category IDs, SKU ID, badges such as
  "Top selling on AliExpress" or "Lowest price in 90 days", main image and all gallery
  images.
- **Any storefront and currency.** Route requests through another country to get that
  storefront's prices: `us` gives USD, `gb` GBP, `de` EUR, `ca` CAD, `au` AUD, and so on.
- **Result filters of its own.** Keep only products with a minimum rating or minimum units
  sold, and drop sponsored cards.
- **Resilient.** Timeouts, transient API errors, half-loaded pages and AliExpress
  verification challenges are retried with doubling backoff.
- **JSON, JSON Lines or CSV.** CSV files are UTF-8 with a BOM, so Excel shows currency
  symbols and non-English titles correctly.
- **CLI + Python library.** Fully typed, and tested offline with a mocked client.

## Install

```bash
git clone https://github.com/ScrapeUnblocker/aliexpress-scraper.git
cd aliexpress-scraper
pip install .
```

Get an API key at [scrapeunblocker.com](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)
and expose it as `SCRAPEUNBLOCKER_KEY` (the official SDK reads it from there):

```bash
export SCRAPEUNBLOCKER_KEY=your_key_here        # Windows PowerShell: $env:SCRAPEUNBLOCKER_KEY="your_key_here"
```

You can also copy `.env.example` to `.env` and load it with your tool of choice.

## CLI usage

```bash
# Best-selling wireless earbuds, 2 pages, to CSV
aliexpress-scraper search "wireless earbuds" --sort orders -p 2 -f csv -o earbuds.csv

# What can I filter on? Attribute values (brand, colour, ...), ship-from countries, related searches
aliexpress-scraper filters "wireless earbuds"

# Lenovo earbuds between $10 and $30 with free shipping, rated 4.5+
aliexpress-scraper search "wireless earbuds" --attr 2250-4154449 --free-shipping \
    --min-price 10 --max-price 30 --min-rating 4.5 --pretty

# Products that ship from the US, cheapest first
aliexpress-scraper search "yoga mat" --ship-from US --sort price-asc -p 3 -f jsonl -o mats.jsonl

# Several niches in one run, merged and de-duplicated, ads dropped
aliexpress-scraper search "pet hair remover" "led strip lights" --sort orders \
    --min-sold 500 --skip-sponsored -p 2 -f csv -o niches.csv

# A category page from the browser, on the UK storefront (prices in GBP)
aliexpress-scraper search --url "https://www.aliexpress.com/category/100003109/women-clothing.html" \
    --sort orders -c gb -n 100 -f csv -o womens_clothing_uk.csv

# Only print the URL that would be fetched (no API call)
aliexpress-scraper search "desk lamp" --choice --max-price 20 --dry-run
```

| Command | What it returns |
| --- | --- |
| `search [QUERY ...]` | Products for each query (60 per page, `--pages` up to 60) |
| `filters QUERY` | The sorts, switches, attribute values and ship-from countries of a search, plus related searches |

| Option | Meaning |
| --- | --- |
| `--url` | An AliExpress search or category URL from the browser, instead of QUERY |
| `--sort` | `best-match` (default), `orders`, `price-asc`, `price-desc` |
| `--min-price`, `--max-price` | Price range, in the storefront's currency |
| `--free-shipping`, `--choice` | Only free-shipping / only AliExpress Choice products |
| `--ship-from CC` | Only products shipping from this country (e.g. `US`) |
| `--attr ID` | Attribute filter such as `3079-4148335` (Black); repeat for several. Values come from `filters` |
| `--min-rating`, `--min-sold`, `--skip-sponsored` | Result filters applied by this tool |
| `-p, --pages`, `-n, --limit` | Pages per query (1-60) and maximum products per query |
| `-c, --country` | Storefront country, which sets the currency (default `us`) |
| `-f, --format json\|jsonl\|csv`, `-o, --output`, `--pretty` | Output format, file and indentation |
| `--images` | CSV only: add a column with every gallery image URL |
| `--retries`, `-q` | Retries per page, no progress output |

Run `aliexpress-scraper <command> --help` for every option. `python -m aliexpress_scraper`
works too.

## Library usage

```python
from aliexpress_scraper import AliExpressScraper, products_to_csv

ali = AliExpressScraper()  # reads SCRAPEUNBLOCKER_KEY; or AliExpressScraper(api_key="...")

# Best sellers with filters
products = ali.search(
    "wireless earbuds",
    sort="orders",
    min_price=10,
    max_price=30,
    free_shipping=True,
    pages=2,
)
for p in products[:5]:
    print(p.sold, p.rating, p.price, p.currency, p.title)
products_to_csv(products, "earbuds.csv")

# Discover attribute filters (brand, colour, material, ...) for a search
page = ali.filters("wireless earbuds")
for group in page.filters:
    print(group.title, [(o.value, o.label) for o in group.options][:5])

# Use one: Lenovo only
lenovo = ali.search("wireless earbuds", attributes=["2250-4154449"])

# Only products that ship from the US
local = ali.search("yoga mat", ship_from="US", sort="price-asc")

# Several niches, merged and de-duplicated, with result filters
shortlist = ali.search_many(
    ["pet hair remover", "led strip lights"],
    sort="orders",
    min_rating=4.6,
    min_sold=500,
    skip_sponsored=True,
)

# A category page, on the UK storefront
uk = AliExpressScraper(country="gb")
clothing = uk.search(url="https://www.aliexpress.com/category/100003109/women-clothing.html", pages=3)

# One page at a time, with the page details
page = ali.search_page("desk lamp", page=1, sort="price-asc")
print(page.total, page.total_pages, page.currency, page.result_type, len(page.products))
```

`search` raises `AliExpressFilterError` if AliExpress did not apply a requested sort or
filter, and `AliExpressBlockedError` if a verification challenge persists after every
retry. Invalid arguments (an unknown sort, a minimum price above the maximum, a malformed
attribute ID, ...) raise `ValueError` before any request is made.

## Example output

One product from `aliexpress-scraper search "wireless earbuds" --attr 2250-4154449
--free-shipping --min-price 10 --max-price 30` (gallery shortened):

```json
{
  "id": "1005007352046243",
  "title": "Original Lenovo XT80 Sports Wireless Earphones with Mics, LED Power Display,Hifi Stereo Sound Bluetooth 5.3 TWS HeadphHeadphones",
  "url": "https://www.aliexpress.com/item/1005007352046243.html",
  "price": 12.33,
  "original_price": 35.04,
  "discount_percent": 64,
  "currency": "USD",
  "price_text": "US $12.33",
  "price_hidden": false,
  "welcome_deal": false,
  "rating": 4.7,
  "sold": 38576,
  "sold_text": "10,000+ sold",
  "choice": true,
  "free_shipping": false,
  "local_warehouse": false,
  "sponsored": false,
  "delivery_min_days": 8,
  "delivery_max_days": 12,
  "delivery_from": "2026-10-16",
  "delivery_to": "2026-10-20",
  "listed_date": "2024-07-11",
  "category_ids": ["44", "100000306", "63705"],
  "sku_id": "12000040387598352",
  "badges": ["Top selling on AliExpress"],
  "image": "https://ae-pic-a1.aliexpress-media.com/kf/Sc304388c77474000888a8dd1027131046.jpg",
  "images": ["https://ae-pic-a1.aliexpress-media.com/kf/Sc304388c77474000888a8dd1027131046.jpg", "..."],
  "query": "wireless earbuds",
  "page": 1,
  "position": 1
}
```

`python examples/best_sellers.py "mechanical keyboard" --top 5` (your results will
differ):

```text
    sold  rating       price  title
  33,403     4.9   21.68 USD  AJAZZ AK820 and AK820PRO Mechanical Gaming Keyboard 75% Layout PBT OEM
  22,470     4.9   33.18 USD  Akko MonsGeek FUN68 FUN60 PRO&MAX HE Magnetic Keyboard 60% 65% Gaming
  16,972     4.9   13.09 USD  AJAZZ NK61 Wired Mechanical Gaming Keyboard, Supports Full-Key Hot-Swa
  15,279     4.7   28.59 USD  AJAZZ NK61 Wired Gaming Mechanical Keyboard 60% RGB Hot-Swappable 61 K
  14,687     4.9    4.33 USD  USB Mechanical Keyboard Gamer 3Keys Macro Custom Keyboard RGB Gaming C
```

## Good to know

- **Up to 3,600 products per search.** AliExpress serves 60 pages of 60 products. To go
  further, split a search into narrower ones (price ranges, attributes, related keywords)
  and merge them; `search_many` and the shared `seen` set de-duplicate for you. The total
  AliExpress reports is an estimate and can change from one page to the next.
- **Storefront and currency.** Prices are in the currency of the country the request is
  routed through (`--country`). Some storefronts also translate titles (`de` returns
  German titles) and the rounded `sold_text` label; the exact `sold` count is the same
  number everywhere.
- **New-shopper prices.** On some storefronts (US and Canada in our tests) AliExpress
  hides the price of some cards behind a "welcome deal" for first-time visitors. The
  card's tracking data still carries the sale price, so `price` is filled in and
  `price_hidden` is `true` (with `price_text`, `original_price` and `discount_percent`
  empty). Free-gift cards carry no sale price at all and keep `price` empty. Every card
  with such an offer has `welcome_deal: true`.
- **Units sold.** `sold` is the exact count from the card's data, while `sold_text` is the
  rounded label AliExpress shows. The `orders` sort is AliExpress's own popularity
  ranking, which is close to, but not strictly the same as, ordering by `sold`.
- **Sponsored cards** (ads) appear on many pages and are marked `sponsored: true`. They
  can repeat on later pages; duplicates are removed. Drop them with `--skip-sponsored`.
- **Loose matches and recommendations.** When nothing matches closely, AliExpress shows
  loosely related products instead (`result_type: "few_result"`; the CLI prints a note).
  "More to love" recommendation cards that some pages append after the real results are
  left out.
- **`free_shipping` and `choice`** describe the badges on a card. The `--free-shipping`
  and `--choice` filters use AliExpress's own filters, which can match products whose card
  does not show the badge.
- **Search pages only.** Every field comes from the search results; the package does not
  open product pages.

## Responsible use

This project reads public search pages that anyone can open without logging in. Respect
AliExpress's terms of service, keep request volumes reasonable, and check the rules that
apply to you before republishing product data or images.

## Project layout

```text
src/aliexpress_scraper/
  __init__.py     package exports and version
  scraper.py      AliExpressScraper: search, pagination, filter checks, retries
  parsing.py      embedded-JSON extraction, product cards, applied filters
  urls.py         search URL builder, sorts, filters, validation
  models.py       Product, SearchPage, FilterGroup dataclasses
  export.py       JSON, JSON Lines and CSV writers
  cli.py          the aliexpress-scraper command
examples/
  best_sellers.py             the best-selling products for a search, as a table
  dropshipping_shortlist.py   well-rated, proven products for several niches, to CSV
  price_watch.py              track prices and sales of the top products over time
tests/            offline tests with synthetic AliExpress pages and a fake client
```

## Development

```bash
make install   # pip install -e ".[dev]"
make lint      # ruff check .
make format    # ruff format .
make test      # pytest -q (offline, no API credit used)
```

Optionally run `pre-commit install` to lint and format on every commit.

## Links

- [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos): web scraping API with real browsers
- [ScrapeUnblocker documentation](https://docs.scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos): `getPageSource` and the SDKs
- [Python SDK on PyPI](https://pypi.org/project/scrapeunblocker/)

## License

[MIT](LICENSE) © ScrapeUnblocker
