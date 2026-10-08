"""Typed records returned by the scraper."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

from .urls import MAX_PAGES


@dataclass
class Product:
    """One product card from an AliExpress search or category page.

    Prices are in the currency of the storefront the request was routed
    through (USD for the US, GBP for the UK, EUR for Germany, ...).
    """

    id: str
    """AliExpress item ID (the number in ``/item/<id>.html``)."""
    title: str | None
    url: str
    price: float | None
    """Sale price shown on the card (the lowest price across variants)."""
    original_price: float | None
    """Price before discount, when the card shows one."""
    discount_percent: int | None
    currency: str | None
    price_text: str | None
    """The price as AliExpress formats it, e.g. ``"US $1.33"``."""
    price_hidden: bool
    """The card hid its price behind a new-shopper offer. ``price`` then comes
    from the card's tracking data (``None`` for free-gift cards, which carry no
    sale price), and ``price_text``, ``original_price`` and ``discount_percent``
    are empty."""
    welcome_deal: bool
    """The card carries a new-shopper "welcome deal" or free-gift offer."""
    rating: float | None
    """Average star rating (0-5); ``None`` for products without reviews."""
    sold: int | None
    """Units sold, exact (the card shows a rounded ``sold_text``)."""
    sold_text: str | None
    choice: bool
    """AliExpress Choice product."""
    free_shipping: bool
    """The card advertises free shipping."""
    local_warehouse: bool
    """Ships from a local warehouse ("Local+" badge)."""
    sponsored: bool
    """Paid placement (ad)."""
    delivery_min_days: int | None
    delivery_max_days: int | None
    delivery_from: str | None
    """Earliest estimated delivery date (ISO), when the card shows one."""
    delivery_to: str | None
    listed_date: str | None
    """Date the product was first listed on AliExpress (ISO)."""
    category_ids: list[str] = field(default_factory=list)
    sku_id: str | None = None
    badges: list[str] = field(default_factory=list)
    """Text badges on the card ("Top selling on AliExpress", "Lowest price in 90 days", ...)."""
    image: str | None = None
    images: list[str] = field(default_factory=list)
    query: str | None = None
    """The search query (or URL) that found the product."""
    page: int | None = None
    position: int | None = None
    """Place on the results page, 1-based."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FilterOption:
    value: str
    label: str
    selected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FilterGroup:
    """A filter AliExpress offers for a search (see :meth:`AliExpressScraper.filters`)."""

    kind: str
    """``sort``, ``switch``, ``attribute`` or ``ship_from``."""
    title: str
    param: str
    """URL parameter the options go into."""
    options: list[FilterOption] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchPage:
    """One page of AliExpress search results."""

    url: str
    page: int | None
    page_size: int | None
    total: int | None
    """Number of matching products AliExpress reports for the search."""
    result_type: str | None
    """``normal_result``, ``few_result`` (no close match, loosely related
    products instead) or ``zero_result``."""
    finished: bool
    """AliExpress says this is the last page."""
    currency: str | None
    search_text: str | None
    category_id: str | None
    products: list[Product] = field(default_factory=list)
    recommended: int = 0
    """"More to love" recommendation cards that were dropped from ``products``."""
    applied: dict[str, Any] = field(default_factory=dict)
    """The sort and filters AliExpress reports as applied."""
    filters: list[FilterGroup] = field(default_factory=list)
    related_searches: list[str] = field(default_factory=list)
    message: str | None = None
    """AliExpress's notice for empty searches, e.g. "No search results for ...". """

    @property
    def total_pages(self) -> int | None:
        if not self.total or not self.page_size:
            return None
        return min(math.ceil(self.total / self.page_size), MAX_PAGES)

    @property
    def has_next(self) -> bool:
        if self.finished or not self.products or self.result_type == "zero_result":
            return False
        pages = self.total_pages
        return pages is None or (self.page or 1) < pages

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_pages"] = self.total_pages
        return data
