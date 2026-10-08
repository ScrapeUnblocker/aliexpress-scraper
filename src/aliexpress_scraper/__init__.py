"""Scrape AliExpress product search results with the ScrapeUnblocker API.

Search AliExpress by keyword or category with its own sorts and filters
(orders, price, price range, free shipping, Choice, ship-from country,
attributes such as colour or material) and get every product card as a typed
record: item ID, title, sale and original price with currency, discount,
rating, exact units sold, Choice / free-shipping / sponsored flags, delivery
estimate and images. Pages are fetched through the ScrapeUnblocker
``getPageSource`` API, which loads them in a real browser.

    >>> from aliexpress_scraper import AliExpressScraper
    >>> ali = AliExpressScraper()                    # reads SCRAPEUNBLOCKER_KEY
    >>> products = ali.search("wireless earbuds", sort="orders", pages=2)
    >>> products[0].title, products[0].price, products[0].sold
"""

from .export import csv_string, products_to_csv, to_json, to_jsonl, write_csv
from .models import FilterGroup, FilterOption, Product, SearchPage
from .parsing import (
    AliExpressBlockedError,
    AliExpressError,
    AliExpressFilterError,
    AliExpressParseError,
    parse_search_page,
)
from .scraper import AliExpressScraper, check_applied, search_url
from .urls import MAX_PAGES, PAGE_SIZE, SORTS, build_search_url, product_id, product_url

__version__ = "0.1.0"

__all__ = [
    "MAX_PAGES",
    "PAGE_SIZE",
    "SORTS",
    "AliExpressBlockedError",
    "AliExpressError",
    "AliExpressFilterError",
    "AliExpressParseError",
    "AliExpressScraper",
    "FilterGroup",
    "FilterOption",
    "Product",
    "SearchPage",
    "build_search_url",
    "check_applied",
    "csv_string",
    "parse_search_page",
    "product_id",
    "product_url",
    "products_to_csv",
    "search_url",
    "to_json",
    "to_jsonl",
    "write_csv",
    "__version__",
]
