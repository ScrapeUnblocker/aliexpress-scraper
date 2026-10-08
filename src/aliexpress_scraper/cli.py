"""Command-line interface: ``aliexpress-scraper <command> ...``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from . import __version__
from .export import products_to_csv, to_json, to_jsonl
from .models import Product, SearchPage
from .scraper import AliExpressScraper, search_url
from .urls import MAX_PAGES, SORTS

FORMATS_OUT = ("json", "jsonl", "csv")


def _stdout() -> TextIO:
    """stdout that always accepts UTF-8 (Windows consoles default to a legacy codepage)."""
    stream = sys.stdout
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # pragma: no cover - exotic streams
            pass
    return stream


def _log(args: argparse.Namespace, message: str) -> None:
    if not getattr(args, "quiet", False):
        print(message, file=sys.stderr, flush=True)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-c",
        "--country",
        default="us",
        help="Storefront country, sets the currency: us (USD), gb (GBP), de (EUR), ... "
        "(default: us)",
    )
    parser.add_argument("--retries", type=int, default=3, help="Retries per page (default 3)")
    parser.add_argument("-q", "--quiet", action="store_true", help="No progress on stderr")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aliexpress-scraper",
        description="Scrape AliExpress product search results via the ScrapeUnblocker API.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Search products (60 per page, 60 pages max)")
    search.add_argument("queries", nargs="*", metavar="QUERY", help="Search keywords")
    search.add_argument(
        "--url", help="An AliExpress search or category URL copied from the browser"
    )
    group = search.add_argument_group("AliExpress filters")
    group.add_argument("--sort", choices=list(SORTS), help="Sort order (default: best-match)")
    group.add_argument("--min-price", type=float, metavar="N", help="Lowest price")
    group.add_argument("--max-price", type=float, metavar="N", help="Highest price")
    group.add_argument("--free-shipping", action="store_true", help="Free shipping only")
    group.add_argument("--choice", action="store_true", help="AliExpress Choice products only")
    group.add_argument("--ship-from", metavar="CC", help="Ships from this country, e.g. US")
    group.add_argument(
        "--attr",
        action="append",
        default=[],
        metavar="ID",
        help="Attribute filter like 3079-4148335 (repeatable; see the `filters` command)",
    )
    local = search.add_argument_group("result filters (applied by this tool)")
    local.add_argument("--min-rating", type=float, metavar="N", help="Minimum star rating (0-5)")
    local.add_argument("--min-sold", type=int, metavar="N", help="Minimum units sold")
    local.add_argument("--skip-sponsored", action="store_true", help="Drop sponsored cards")
    search.add_argument(
        "-p", "--pages", type=int, default=1, help=f"Pages per query (1-{MAX_PAGES}, default 1)"
    )
    search.add_argument("-n", "--limit", type=int, help="Maximum products per query")
    search.add_argument("-f", "--format", choices=FORMATS_OUT, default="json")
    search.add_argument("-o", "--output", help="Write to this file instead of stdout")
    search.add_argument("--pretty", action="store_true", help="Indent JSON output")
    search.add_argument(
        "--images", action="store_true", help="CSV: include every image URL, not just the main one"
    )
    search.add_argument(
        "--dry-run", action="store_true", help="Print the search URL(s) and exit (no API call)"
    )
    _add_common(search)

    filters = sub.add_parser(
        "filters", help="Show the sorts, attribute filters and ship-from countries of a search"
    )
    filters.add_argument("query", nargs="?", metavar="QUERY", help="Search keywords")
    filters.add_argument("--url", help="An AliExpress search or category URL")
    filters.add_argument("--json", action="store_true", help="Print JSON instead of a list")
    _add_common(filters)
    return parser


def _filters(args: argparse.Namespace) -> dict[str, Any]:
    filters = {
        "sort": args.sort,
        "min_price": args.min_price,
        "max_price": args.max_price,
        "free_shipping": args.free_shipping,
        "choice": args.choice,
        "ship_from": args.ship_from,
        "attributes": args.attr,
    }
    return {k: v for k, v in filters.items() if v not in (None, False, [])}


def _scraper(args: argparse.Namespace) -> AliExpressScraper:
    def on_retry(attempt: int, delay: float, error: BaseException) -> None:
        _log(args, f"  retry {attempt} in {delay:.0f}s ({type(error).__name__})")

    return AliExpressScraper(country=args.country, retries=args.retries, on_retry=on_retry)


def _emit(args: argparse.Namespace, records: list[Product]) -> None:
    if args.format == "csv":
        target: Any = args.output or _stdout()
        products_to_csv(records, target, images=args.images)
    else:
        text = to_jsonl(records) if args.format == "jsonl" else to_json(records, pretty=args.pretty)
        if not text.endswith("\n"):
            text += "\n"
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(text)
        else:
            out = _stdout()
            out.write(text)
            out.flush()
    if args.output:
        _log(args, f"wrote {len(records)} product(s) to {Path(args.output)}")


def _page_note(page: SearchPage) -> str | None:
    if page.result_type == "few_result":
        return "AliExpress found no close match; these are loosely related products"
    if page.result_type == "zero_result" and page.page in (None, 1):
        return page.message or "no results"
    return None


def cmd_search(args: argparse.Namespace) -> int:
    if args.url and args.queries:
        raise SystemExit("error: --url already holds the search; drop QUERY")
    if not args.url and not args.queries:
        raise SystemExit("error: give a search QUERY or --url")
    filters = _filters(args)
    queries: list[str | None] = list(args.queries) or [None]
    if args.dry_run:
        out = _stdout()
        for query in queries:
            out.write(search_url(query, url=args.url, **filters) + "\n")
        return 0
    scraper = _scraper(args)
    seen: set[str] = set()
    found: list[Product] = []
    for query in queries:
        label = query or args.url

        def on_page(page: SearchPage, label: str = label) -> None:
            total = f" of {page.total:,}" if page.total else ""
            pages = page.total_pages or "-"
            _log(
                args,
                f"{label}: page {page.page or '-'}/{pages} -> {len(page.products)} products"
                f"{total} ({page.currency or '?'})",
            )
            note = _page_note(page)
            if note:
                _log(args, f"  note: {note}")

        found += scraper.search(
            query,
            url=args.url,
            pages=args.pages,
            limit=args.limit,
            seen=seen,
            skip_sponsored=args.skip_sponsored,
            min_rating=args.min_rating,
            min_sold=args.min_sold,
            on_page=on_page,
            **filters,
        )
    _log(args, f"{len(found)} unique product(s)")
    _emit(args, found)
    return 0


def cmd_filters(args: argparse.Namespace) -> int:
    if bool(args.url) == bool(args.query):
        raise SystemExit("error: give a search QUERY or --url")
    page = _scraper(args).filters(args.query, url=args.url)
    out = _stdout()
    if args.json:
        data = {
            "search_text": page.search_text,
            "category_id": page.category_id,
            "total": page.total,
            "currency": page.currency,
            "filters": [g.to_dict() for g in page.filters],
            "related_searches": page.related_searches,
        }
        out.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return 0
    flags = {
        "sort": "--sort",
        "switch": "",
        "attribute": "--attr",
        "ship_from": "--ship-from",
    }
    total = f"{page.total:,}" if page.total is not None else "?"
    out.write(f"{total} products, prices in {page.currency or '?'}\n")
    for group in page.filters:
        out.write(
            f"\n{group.title}" + (f" ({flags[group.kind]})" if flags[group.kind] else "") + ":\n"
        )
        for option in group.options:
            value = (
                f"--{option.value.replace('_', '-')}" if group.kind == "switch" else option.value
            )
            mark = "  [applied]" if option.selected else ""
            out.write(f"  {value:<22}{option.label}{mark}\n")
    if page.related_searches:
        out.write("\nRelated searches:\n  " + ", ".join(page.related_searches) + "\n")
    return 0


COMMANDS = {"search": cmd_search, "filters": cmd_filters}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
