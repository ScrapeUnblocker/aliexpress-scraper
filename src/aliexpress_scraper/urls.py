"""Build AliExpress search URLs.

AliExpress search pages live at ``/w/wholesale-<slug>.html?SearchText=<query>``
and category pages at ``/category/<id>/<slug>.html``. Both take the same query
parameters, all checked against live pages:

=====================  ===================================================
``page``               1-based page number, 60 products per page, 60 pages max
``SortType``           ``total_tranpro_desc`` (orders), ``price_asc``, ``price_desc``
``minPrice/maxPrice``  price range, in the currency of the storefront
``selectedSwitches``   ``filterCode:freeshipping``, ``filterCode:choice_atm``
``shpf_co``            ship-from country code, e.g. ``US``
``attr``               attribute filters such as ``3079-4148335`` (comma-joined)
=====================  ===================================================

AliExpress silently ignores parameters it does not understand. The page echoes
back the sort and filters it actually applied, and
:func:`aliexpress_scraper.scraper.check_applied` compares the two.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

BASE_URL = "https://www.aliexpress.com"
PAGE_SIZE = 60
MAX_PAGES = 60

SORTS: dict[str, str | None] = {
    "best-match": None,
    "orders": "total_tranpro_desc",
    "price-asc": "price_asc",
    "price-desc": "price_desc",
}
"""``sort`` value -> ``SortType`` URL parameter (``None`` = AliExpress default)."""

SORT_ECHO = {
    "best-match": "default:default",
    "orders": "orders:desc",
    "price-asc": "price:asc",
    "price-desc": "price:desc",
}
"""``sort`` value -> how the page's sort bar reports it as selected."""

SWITCHES = {
    "free_shipping": "filterCode:freeshipping",
    "choice": "filterCode:choice_atm",
}
"""Boolean filters -> ``selectedSwitches`` values."""

_ATTR = re.compile(r"^\d+-\d+$")
_COUNTRY = re.compile(r"^[A-Za-z]{2}$")
_PRODUCT_ID = re.compile(r"/item/(\d+)\.html")


def query_slug(query: str) -> str:
    """The cosmetic ``wholesale-<slug>`` part of a search URL.

    AliExpress reads the query from ``SearchText``; the slug only mirrors it.
    """
    slug = re.sub(r"[^0-9a-z]+", "-", query.lower()).strip("-")
    return slug or "products"


def sort_type(sort: str | None) -> str | None:
    """Validate ``sort`` and return its ``SortType`` value."""
    if sort is None:
        return None
    key = sort.strip().lower().replace("_", "-")
    if key not in SORTS:
        raise ValueError(f"unknown sort {sort!r}; use one of: {', '.join(SORTS)}")
    return SORTS[key]


def normalize_sort(sort: str | None) -> str | None:
    """``"price_asc"`` -> ``"price-asc"``; validates the value."""
    if sort is None:
        return None
    sort_type(sort)
    return sort.strip().lower().replace("_", "-")


def normalize_attributes(attributes: Iterable[str] | str | None) -> list[str]:
    """Validate attribute filters (``"<attribute id>-<value id>"``)."""
    if not attributes:
        return []
    if isinstance(attributes, str):
        attributes = attributes.split(",")
    found: list[str] = []
    for raw in attributes:
        value = str(raw).strip()
        if not value:
            continue
        if not _ATTR.match(value):
            raise ValueError(
                f"attribute filter {raw!r} must look like '3079-4148335' "
                "(see the `filters` command for the values of a search)"
            )
        if value not in found:
            found.append(value)
    return found


def normalize_country(code: str | None) -> str | None:
    """Validate a two-letter ship-from country code (``"us"`` -> ``"US"``)."""
    if code is None or not str(code).strip():
        return None
    code = str(code).strip()
    if not _COUNTRY.match(code):
        raise ValueError(f"ship-from country must be a 2-letter code like 'US', got {code!r}")
    return code.upper()


def _price(value: float | int | str | None, name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number, got {value!r}") from None
    if number < 0:
        raise ValueError(f"{name} must not be negative")
    return number


def _number(value: float) -> str:
    return f"{value:g}"


def filter_params(
    *,
    sort: str | None = None,
    min_price: float | int | str | None = None,
    max_price: float | int | str | None = None,
    free_shipping: bool = False,
    choice: bool = False,
    ship_from: str | None = None,
    attributes: Iterable[str] | str | None = None,
) -> list[tuple[str, str]]:
    """The query parameters for a sort order and a set of filters."""
    params: list[tuple[str, str]] = []
    sort_value = sort_type(sort)
    if sort_value:
        params.append(("SortType", sort_value))
    low = _price(min_price, "min_price")
    high = _price(max_price, "max_price")
    if low is not None and high is not None and low > high:
        raise ValueError("min_price is greater than max_price")
    if low is not None:
        params.append(("minPrice", _number(low)))
    if high is not None:
        params.append(("maxPrice", _number(high)))
    switches = [
        SWITCHES[name] for name, on in (("free_shipping", free_shipping), ("choice", choice)) if on
    ]
    if switches:
        params.append(("selectedSwitches", ",".join(switches)))
    country = normalize_country(ship_from)
    if country:
        params.append(("shpf_co", country))
    attrs = normalize_attributes(attributes)
    if attrs:
        params.append(("attr", ",".join(attrs)))
    return params


def build_search_url(query: str, *, page: int = 1, **filters: object) -> str:
    """The URL of one page of search results.

    >>> build_search_url("phone case", page=2, sort="orders", free_shipping=True)
    'https://www.aliexpress.com/w/wholesale-phone-case.html?SearchText=phone+case&page=2&SortType=total_tranpro_desc&selectedSwitches=filterCode%3Afreeshipping'
    """
    text = " ".join(str(query or "").split())
    if not text:
        raise ValueError("give a search query, e.g. 'wireless earbuds'")
    params: list[tuple[str, str]] = [("SearchText", text)]
    if page_number(page) > 1:
        params.append(("page", str(page)))
    params += filter_params(**filters)  # type: ignore[arg-type]
    return f"{BASE_URL}/w/wholesale-{query_slug(text)}.html?{urlencode(params)}"


def page_number(page: int) -> int:
    """Validate a 1-based page number."""
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise ValueError(f"page must be a whole number >= 1, got {page!r}")
    if page > MAX_PAGES:
        raise ValueError(f"AliExpress serves at most {MAX_PAGES} pages per search")
    return page


def is_search_url(url: str) -> bool:
    """True for AliExpress search (``/w/...``, ``/wholesale``) and category URLs."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if parts.scheme not in ("http", "https") or "aliexpress." not in host:
        return False
    path = parts.path.lower()
    return path.startswith(("/w/", "/category/", "/wholesale"))


def with_params(url: str, page: int = 1, extra: Iterable[tuple[str, str]] = ()) -> str:
    """``url`` with its ``page`` set (dropped for page 1) and ``extra`` parameters
    added or replaced."""
    page_number(page)
    parts = urlsplit(url.strip())
    extra = list(extra)
    replace = {key for key, _ in extra} | {"page"}
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in replace]
    if page > 1:
        query.append(("page", str(page)))
    query += extra
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def product_url(product_id: str | int) -> str:
    """The product page of an AliExpress item ID."""
    return f"{BASE_URL}/item/{product_id}.html"


def product_id(value: str | int) -> str:
    """The item ID from an ID or a product URL (``.../item/1005006016124137.html``)."""
    text = str(value).strip()
    if text.isdigit():
        return text
    match = _PRODUCT_ID.search(text)
    if not match:
        raise ValueError(f"not an AliExpress item ID or product URL: {value!r}")
    return match.group(1)
