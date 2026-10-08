"""Scrape AliExpress search results through the ScrapeUnblocker ``getPageSource`` API.

ScrapeUnblocker loads each AliExpress page in a real browser and returns the
HTML; :mod:`aliexpress_scraper.parsing` turns the JSON embedded in it into
:class:`~aliexpress_scraper.models.Product` records.

The storefront follows the country the request is routed through: prices come
in that country's currency (USD for ``us``, GBP for ``gb``, EUR for ``de``, ...)
and some storefronts translate titles. Timeouts, transient API errors,
half-loaded pages and verification challenges are retried with doubling
backoff, so a long collection run keeps going.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator, Sequence
from typing import Any, Callable

from .models import Product, SearchPage
from .parsing import AliExpressFilterError, AliExpressParseError, parse_search_page
from .urls import (
    MAX_PAGES,
    SWITCHES,
    build_search_url,
    filter_params,
    is_search_url,
    normalize_attributes,
    normalize_country,
    normalize_sort,
    with_params,
)

_TRANSIENT_NAMES = (
    "UpstreamOutageError",
    "RateLimitError",
    "ScrapeTimeoutError",
    "BrowserTimeoutError",
    "BlockedError",
    "ServerError",
    "ConnectionError",
)

FILTERS = ("sort", "min_price", "max_price", "free_shipping", "choice", "ship_from", "attributes")


def _transient_errors() -> tuple[type[BaseException], ...]:
    """Best-effort tuple of ScrapeUnblocker exceptions worth retrying.

    Imported lazily so the package is usable (and unit-testable) even when the
    ``scrapeunblocker`` SDK is not installed or is an older release.
    """
    try:
        import scrapeunblocker  # type: ignore
    except Exception:  # pragma: no cover - depends on SDK availability
        return ()
    found = (getattr(scrapeunblocker, name, None) for name in _TRANSIENT_NAMES)
    return tuple(cls for cls in found if isinstance(cls, type))


def _check_filters(filters: dict[str, Any]) -> None:
    unknown = set(filters) - set(FILTERS)
    if unknown:
        raise TypeError(f"unknown search filter(s): {', '.join(sorted(unknown))}")


def search_url(
    query: str | None = None, *, page: int = 1, url: str | None = None, **filters: Any
) -> str:
    """The URL of one page of results, from a query + filters or a copied URL.

    ``url`` may be any AliExpress search or category URL from the browser;
    ``page`` and the filters are added to it.
    """
    _check_filters(filters)
    if url:
        if query:
            raise ValueError("give a search query or a url, not both")
        if not is_search_url(url):
            raise ValueError(f"not an AliExpress search or category URL: {url!r}")
        return with_params(url, page, filter_params(**filters))
    if not query or not query.strip():
        raise ValueError("give a search query (e.g. 'wireless earbuds') or a search url")
    return build_search_url(query, page=page, **filters)


def check_applied(page: SearchPage, **filters: Any) -> None:
    """Raise :class:`AliExpressFilterError` when the page shows that a requested
    sort or filter was not applied.

    Pages without products are not checked (there is nothing to mislabel).
    """
    _check_filters(filters)
    if not page.products:
        return
    applied = page.applied
    missing: list[str] = []
    sort = normalize_sort(filters.get("sort"))
    if sort and sort != "best-match" and applied.get("sort") != sort:
        missing.append(f"sort={sort}")
    switches = set(applied.get("switches") or [])
    for name in ("free_shipping", "choice"):
        if filters.get(name) and SWITCHES[name] not in switches:
            missing.append(name)
    country = normalize_country(filters.get("ship_from"))
    if country and str(applied.get("ship_from") or "").upper() != country:
        missing.append(f"ship_from={country}")
    have = set(applied.get("attributes") or [])
    missing += [
        f"attribute={a}" for a in normalize_attributes(filters.get("attributes")) if a not in have
    ]
    for name in ("min_price", "max_price"):
        wanted = filters.get(name)
        if wanted in (None, ""):
            continue
        got = applied.get(name)
        if got is None or abs(float(got) - float(wanted)) > 0.005:
            missing.append(f"{name}={wanted}")
    if missing:
        raise AliExpressFilterError(
            f"AliExpress did not apply: {', '.join(missing)} (url: {page.url})"
        )


class AliExpressScraper:
    """Search AliExpress and collect product cards as typed records.

    Args:
        api_key: ScrapeUnblocker key. If omitted, the SDK reads
            ``SCRAPEUNBLOCKER_KEY`` from the environment.
        client: A pre-built client (or any object exposing
            ``get_page_source(url, proxy_country=...)``). Mainly for testing.
        country: Storefront country to route requests through (default ``us``).
            It sets the currency of every price: ``us`` USD, ``gb`` GBP,
            ``de`` EUR, ``ca`` CAD, ``au`` AUD, ...
        retries: Extra attempts per page on transient failures.
        backoff: Seconds before the first retry; doubles on every further retry.
        max_backoff: Upper bound for a single wait between retries.
        timeout: Per-request timeout passed to the SDK client.
        transient_errors: Exception classes treated as retryable. Defaults to
            the ScrapeUnblocker transient set.
        on_retry: Optional callback ``(attempt, delay_seconds, error)`` invoked
            before every retry (handy for progress output).
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: Any | None = None,
        country: str | None = "us",
        retries: int = 3,
        backoff: float = 5.0,
        max_backoff: float = 60.0,
        timeout: float = 180.0,
        transient_errors: Sequence[type[BaseException]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        on_retry: Callable[[int, float, BaseException], None] | None = None,
    ) -> None:
        if client is None:
            from scrapeunblocker import Client  # local import: optional dep

            client = Client(api_key=api_key, timeout=timeout)
        self._client = client
        self.country = country.strip().upper() if country and country.strip() else None
        self.retries = max(0, int(retries))
        self.backoff = float(backoff)
        self.max_backoff = float(max_backoff)
        self.on_retry = on_retry
        transient = tuple(transient_errors) if transient_errors is not None else _transient_errors()
        self._transient = (*transient, AliExpressParseError)
        self._sleep = sleep

    # ------------------------------------------------------------------ #
    # Fetching
    # ------------------------------------------------------------------ #

    def _fetch(self, url: str) -> SearchPage:
        """Fetch and parse one page, retrying transient failures with backoff."""
        attempt = 0
        while True:
            try:
                options: dict[str, Any] = {}
                if self.country:
                    options["proxy_country"] = self.country
                html = self._client.get_page_source(url, **options)
                return parse_search_page(html if isinstance(html, str) else "", url)
            except Exception as exc:
                if not isinstance(exc, self._transient) or attempt >= self.retries:
                    raise
                attempt += 1
                delay = min(self.backoff * 2 ** (attempt - 1), self.max_backoff)
                if self.on_retry is not None:
                    self.on_retry(attempt, delay, exc)
                self._sleep(delay)

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    def search_url(
        self, query: str | None = None, *, page: int = 1, url: str | None = None, **filters: Any
    ) -> str:
        """The URL :meth:`search_page` would fetch."""
        return search_url(query, page=page, url=url, **filters)

    def search_page(
        self,
        query: str | None = None,
        *,
        page: int = 1,
        url: str | None = None,
        check_filters: bool = True,
        **filters: Any,
    ) -> SearchPage:
        """Fetch one page of results (up to 60 products).

        Args:
            query: Keywords, e.g. ``"wireless earbuds"``.
            page: 1-based page number (AliExpress serves 60 pages at most).
            url: An AliExpress search or category URL copied from the browser,
                instead of ``query``. ``page`` and ``filters`` are added to it.
            check_filters: Raise :class:`AliExpressFilterError` if the page shows
                that a requested sort or filter was not applied.
            **filters: ``sort`` (``orders``, ``price-asc``, ``price-desc``,
                ``best-match``), ``min_price``, ``max_price``, ``free_shipping``,
                ``choice``, ``ship_from`` (country code) and ``attributes``
                (IDs like ``"3079-4148335"`` from :meth:`filters`).
        """
        target = self.search_url(query, page=page, url=url, **filters)
        result = self._fetch(target)
        if check_filters:
            check_applied(result, **filters)
        return result

    def iter_search(
        self,
        query: str | None = None,
        *,
        pages: int = 1,
        limit: int | None = None,
        url: str | None = None,
        seen: set[str] | None = None,
        skip_sponsored: bool = False,
        min_rating: float | None = None,
        min_sold: int | None = None,
        on_page: Callable[[SearchPage], None] | None = None,
        **filters: Any,
    ) -> Iterator[Product]:
        """Yield products page by page; see :meth:`search` for the arguments."""
        if pages < 1:
            raise ValueError("pages must be at least 1")
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        seen = set() if seen is None else seen
        label = " ".join(query.split()) if query else url
        found_here: set[str] = set()
        yielded = 0
        for number in range(1, min(pages, MAX_PAGES) + 1):
            result = self.search_page(query, page=number, url=url, **filters)
            if on_page is not None:
                on_page(result)
            fresh = 0
            for product in result.products:
                if product.id not in found_here:
                    found_here.add(product.id)
                    fresh += 1
                if product.id in seen:
                    continue
                seen.add(product.id)
                if skip_sponsored and product.sponsored:
                    continue
                if min_rating is not None and (product.rating or 0) < min_rating:
                    continue
                if min_sold is not None and (product.sold or 0) < min_sold:
                    continue
                product.query = label
                yield product
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            if not result.has_next or not fresh:
                return

    def search(
        self,
        query: str | None = None,
        *,
        pages: int = 1,
        limit: int | None = None,
        url: str | None = None,
        seen: set[str] | None = None,
        skip_sponsored: bool = False,
        min_rating: float | None = None,
        min_sold: int | None = None,
        on_page: Callable[[SearchPage], None] | None = None,
        **filters: Any,
    ) -> list[Product]:
        """Search AliExpress and collect products across pages.

        Args:
            query: Keywords, e.g. ``"phone case"``.
            pages: Pages to fetch (up to 60 products each, 60 pages at most).
                Stops early when AliExpress has no more results.
            limit: Return at most this many products.
            url: An AliExpress search or category URL copied from the browser.
            seen: Shared set of product IDs; products already in it are skipped.
                Pass the same set to several calls to de-duplicate across searches.
            skip_sponsored: Drop sponsored (ad) cards.
            min_rating: Keep only products rated at least this (0-5).
            min_sold: Keep only products with at least this many units sold.
            on_page: Callback invoked with every fetched :class:`SearchPage`.
            **filters: ``sort``, ``min_price``, ``max_price``, ``free_shipping``,
                ``choice``, ``ship_from``, ``attributes``; see :meth:`search_page`.
        """
        return list(
            self.iter_search(
                query,
                pages=pages,
                limit=limit,
                url=url,
                seen=seen,
                skip_sponsored=skip_sponsored,
                min_rating=min_rating,
                min_sold=min_sold,
                on_page=on_page,
                **filters,
            )
        )

    def search_many(
        self,
        queries: Iterable[str],
        *,
        on_query: Callable[[str, list[Product]], None] | None = None,
        **options: Any,
    ) -> list[Product]:
        """Run :meth:`search` for several queries, merged and de-duplicated."""
        seen: set[str] = options.pop("seen", None) or set()
        results: list[Product] = []
        for query in queries:
            found = self.search(query, seen=seen, **options)
            if on_query is not None:
                on_query(query, found)
            results.extend(found)
        return results

    def filters(self, query: str | None = None, *, url: str | None = None) -> SearchPage:
        """First page of a search, for its filter options (``page.filters``:
        sorts, attribute values such as colours or materials, ship-from
        countries) and ``page.related_searches``."""
        return self.search_page(query, url=url, check_filters=False)
