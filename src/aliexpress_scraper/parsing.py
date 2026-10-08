"""Turn AliExpress search pages into :class:`~aliexpress_scraper.models.Product` records.

AliExpress renders its search and category pages from a JSON blob embedded in
the HTML::

    window._dida_config_._init_data_= { data: {"hierarchy": ..., "data": {...}} }

``data.root.fields`` holds the page info (total, page, result type), the sort
bar, the filters and ``mods.itemList.content``: the product cards. Each card
has a display block (title, prices, rating, units sold, badges) and a
``trace.utLogMap`` block with exact values (units sold, item ID, delivery
estimate, category IDs) that this module reads as well.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from typing import Any

from .models import FilterGroup, FilterOption, Product, SearchPage
from .urls import SORT_ECHO, SORTS, SWITCHES, product_url


class AliExpressError(Exception):
    """Base class for errors raised by this package."""


class AliExpressParseError(AliExpressError):
    """The page did not contain AliExpress search data (retried automatically)."""


class AliExpressBlockedError(AliExpressParseError):
    """AliExpress answered with a slider / CAPTCHA challenge instead of results
    (retried automatically; these come in short waves)."""


class AliExpressFilterError(AliExpressError):
    """AliExpress did not apply a requested sort or filter."""


_INIT = re.compile(r"_init_data_\s*=\s*\{\s*data\s*:\s*")
_CHALLENGE = ("_____tmd_____", "x5secdata", "/punish?", "baxia-punish")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_EXACT_SOLD = re.compile(r"^\s*(\d{1,3}(?:[.,\s]\d{3})+|\d+)\s+\D")

_SORT_NAMES = {echo: name for name, echo in SORT_ECHO.items()}
_SWITCH_NAMES = {value: name for name, value in SWITCHES.items()}
_DELIVERY_SOURCE = "ETA_atm"


def is_challenge(html: str) -> bool:
    """True when the page is an anti-bot challenge rather than content."""
    return any(marker in html for marker in _CHALLENGE)


def extract_init_data(html: str) -> dict[str, Any]:
    """The JSON object embedded as ``_init_data_`` in a search page.

    Raises:
        AliExpressBlockedError: the page is a slider / CAPTCHA challenge.
        AliExpressParseError: the page holds no search data.
    """
    match = _INIT.search(html or "")
    if match is None:
        if is_challenge(html or ""):
            raise AliExpressBlockedError("AliExpress answered with a verification challenge")
        raise AliExpressParseError("no AliExpress search data found in the page")
    try:
        data, _ = json.JSONDecoder().raw_decode(html, match.end())
    except ValueError as exc:
        raise AliExpressParseError(f"could not decode AliExpress search data: {exc}") from exc
    if not isinstance(data, dict):
        raise AliExpressParseError("unexpected AliExpress search data")
    return data


# --------------------------------------------------------------------------- #
# Small converters
# --------------------------------------------------------------------------- #


def _float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _image(url: Any) -> str | None:
    if not url or not isinstance(url, str):
        return None
    return "https:" + url if url.startswith("//") else url


def _date(value: Any) -> str | None:
    text = str(value or "").strip()
    return text[:10] if _DATE.match(text) else None


def exact_sold(text: str | None) -> int | None:
    """``"498 sold"`` -> 498; rounded labels like ``"10,000+ sold"`` -> None."""
    if not text or "+" in text:
        return None
    match = _EXACT_SOLD.match(text)
    if not match:
        return None
    return int(re.sub(r"\D", "", match.group(1)))


def parse_delivery(value: Any) -> tuple[int | None, int | None, str | None, str | None]:
    """``"8,12,2026-10-16,2026-10-20"`` -> ``(8, 12, "2026-10-16", "2026-10-20")``."""
    parts = str(value or "").split(",")
    if len(parts) < 4:
        return None, None, None, None
    return _int(parts[0]), _int(parts[1]), _date(parts[2]), _date(parts[3])


# --------------------------------------------------------------------------- #
# Product cards
# --------------------------------------------------------------------------- #


def _url_sku(card: dict[str, Any]) -> str | None:
    """The SKU ID from a deal card's link (``...&skuId=12000050854070498``)."""
    for url in (card.get("productDetailUrl"), (card.get("rainbow") or {}).get("url")):
        match = re.search(r"[?&]skuId=(\d+)", str(url or ""))
        if match:
            return match.group(1)
    return None


def is_product_card(card: Any) -> bool:
    """True for search hits; False for "more to love" recommendation cards."""
    return isinstance(card, dict) and card.get("itemType") == "productV3"


def _tracking(card: dict[str, Any]) -> dict[str, Any]:
    trace = card.get("trace") or {}
    data = trace.get("utLogMap") if isinstance(trace, dict) else None
    return data if isinstance(data, dict) else {}


def _images(card: dict[str, Any]) -> list[str]:
    found: list[str] = []
    main = _image((card.get("image") or {}).get("imgUrl"))
    if main:
        found.append(main)
    for item in card.get("images") or []:
        url = _image(item.get("imgUrl")) if isinstance(item, dict) else None
        if url and url not in found:
            found.append(url)
    return found


def parse_card(
    card: dict[str, Any], *, currency: str | None = None, position: int | None = None
) -> Product | None:
    """One search-result card as a :class:`Product` (``None`` if it has no item ID)."""
    tracking = _tracking(card)
    item_id = str(tracking.get("x_object_id") or card.get("productId") or "").strip()
    if not item_id.isdigit():
        return None

    prices = card.get("prices") or {}
    sale = prices.get("salePrice") or {}
    original = prices.get("originalPrice") or {}
    price = _float(sale.get("minPrice"))
    hidden = not prices
    if price is None:
        # A new-shopper card hides its price. The tracking data usually still
        # carries the sale price in cents (on cards that do show a price it
        # always matches the shown one); free-gift cards have none.
        cents = _int(tracking.get("salePriceAmount"))
        if cents is not None:
            price = cents / 100
    original_price = _float(original.get("minPrice")) if not hidden else None
    discount = _int(sale.get("discount")) if not hidden else None

    sources: set[str] = set()
    badges: list[str] = []
    for point in card.get("sellingPoints") or []:
        if not isinstance(point, dict):
            continue
        source = str(point.get("source") or "")
        sources.add(source)
        content = point.get("tagContent") or {}
        text = _text(content.get("tagText"))
        if text and source != _DELIVERY_SOURCE and text not in badges:
            badges.append(text)

    sold_text = _text((card.get("trade") or {}).get("tradeDesc"))
    sold = _int(tracking.get("real_trade_count"))
    if sold is None:
        sold = exact_sold(sold_text)
    days_min, days_max, date_from, date_to = parse_delivery(tracking.get("delivery_info"))
    images = _images(card)
    categories = [c for c in str(tracking.get("categoryId") or "").split(",") if c.strip()]

    return Product(
        id=item_id,
        title=_text((card.get("title") or {}).get("displayTitle")),
        url=product_url(item_id),
        price=price,
        original_price=original_price,
        discount_percent=discount,
        currency=(sale.get("currencyCode") or currency) if price is not None else None,
        price_text=_text(sale.get("formattedPrice")),
        price_hidden=hidden,
        welcome_deal=hidden or any("new_user" in s or "welcomedeal" in s for s in sources),
        rating=_float((card.get("evaluation") or {}).get("starRating")),
        sold=sold,
        sold_text=sold_text,
        choice="choice_atm" in sources or str(tracking.get("isChoice")).lower() == "true",
        free_shipping="Free_Shipping_atm" in sources,
        local_warehouse=any(s.startswith("localplus") for s in sources),
        sponsored=card.get("productType") == "ad",
        delivery_min_days=days_min,
        delivery_max_days=days_max,
        delivery_from=date_from,
        delivery_to=date_to,
        listed_date=_date(card.get("lunchTime")),
        category_ids=categories,
        sku_id=_text(prices.get("skuId") or tracking.get("sku_id")) or _url_sku(card),
        badges=badges,
        image=images[0] if images else None,
        images=images,
        position=position,
    )


# --------------------------------------------------------------------------- #
# Page-level data
# --------------------------------------------------------------------------- #


def page_currency(root: dict[str, Any], cards: Iterable[dict[str, Any]] = ()) -> str | None:
    """The storefront currency of a page."""
    info = root.get("pageInfo") or {}
    trace = (info.get("trace") or {}).get("utLogMap") or {}
    code = trace.get("currency") if isinstance(trace, dict) else None
    if isinstance(code, str) and re.fullmatch(r"[A-Z]{3}", code):
        return code
    config = ((root.get("p4pObjectConfig") or {}).get("bcfg") or {}).get("currencyType")
    if isinstance(config, str) and re.fullmatch(r"[A-Z]{3}", config):
        return config
    seen = Counter(
        ((card.get("prices") or {}).get("salePrice") or {}).get("currencyCode")
        for card in cards
        if isinstance(card, dict)
    )
    seen.pop(None, None)
    return seen.most_common(1)[0][0] if seen else None


def _filter_groups(mods: dict[str, Any]) -> list[dict[str, Any]]:
    groups = (mods.get("searchRefineFilters") or {}).get("content") or []
    return [g for g in groups if isinstance(g, dict)]


def _selected(group: dict[str, Any]) -> list[str]:
    return [
        str(option.get("selectedValue"))
        for option in group.get("content") or []
        if isinstance(option, dict) and option.get("selected") and option.get("selectedValue")
    ]


def applied_filters(mods: dict[str, Any]) -> dict[str, Any]:
    """The sort and filters the page reports as applied."""
    applied: dict[str, Any] = {
        "sort": None,
        "switches": [],
        "ship_from": None,
        "attributes": [],
        "min_price": None,
        "max_price": None,
    }
    for entry in (mods.get("sortBar") or {}).get("content") or []:
        for order in entry.get("sortOrders") or []:
            if order.get("selected"):
                echo = f"{entry.get('sortType')}:{order.get('order')}"
                applied["sort"] = _SORT_NAMES.get(echo, echo)
    for group in _filter_groups(mods):
        kind, selected = group.get("type"), _selected(group)
        if kind == "featureSwitchGroup":
            applied["switches"] += selected
        elif kind == "attribute":
            applied["attributes"] += selected
        elif kind == "logistics" and selected:
            applied["ship_from"] = selected[0]
        elif kind == "priceRange":
            applied["min_price"] = _float(group.get("minPrice"))
            applied["max_price"] = _float(group.get("maxPrice"))
    return applied


def filter_options(
    mods: dict[str, Any], applied: dict[str, Any] | None = None
) -> list[FilterGroup]:
    """The sorts and filters AliExpress offers for this search."""
    applied = applied if applied is not None else applied_filters(mods)
    groups = [
        FilterGroup(
            kind="sort",
            title="Sort by",
            param="SortType",
            options=[FilterOption(name, name, applied.get("sort") == name) for name in SORTS],
        )
    ]
    switches: list[FilterOption] = []
    for group in _filter_groups(mods):
        kind = group.get("type")
        options = [o for o in group.get("content") or [] if isinstance(o, dict)]
        if kind == "featureSwitchGroup":
            for option in options:
                name = _SWITCH_NAMES.get(str(option.get("selectedValue")))
                if name:
                    switches.append(
                        FilterOption(
                            name, _text(option.get("text")) or name, bool(option.get("selected"))
                        )
                    )
        elif kind in ("attribute", "logistics"):
            groups.append(
                FilterGroup(
                    kind="attribute" if kind == "attribute" else "ship_from",
                    title=_text(group.get("title")) or "",
                    param=str(group.get("paramName") or ""),
                    options=[
                        FilterOption(
                            str(o.get("selectedValue")),
                            _text(o.get("text")) or str(o.get("selectedValue")),
                            bool(o.get("selected")),
                        )
                        for o in options
                        if o.get("selectedValue")
                    ],
                )
            )
    if switches:
        groups.insert(1, FilterGroup("switch", "Deals & delivery", "selectedSwitches", switches))
    return groups


def _component(data: dict[str, Any], prefix: str) -> dict[str, Any]:
    for key, value in data.items():
        if key.startswith(prefix) and isinstance(value, dict):
            return value.get("fields") or {}
    return {}


def parse_search_page(html: str, url: str = "") -> SearchPage:
    """Parse a search or category page.

    Raises:
        AliExpressBlockedError: the page is a verification challenge.
        AliExpressParseError: the page holds no search data.
    """
    init = extract_init_data(html)
    data = init.get("data") or {}
    root = (data.get("root") or {}).get("fields") or {}
    info = root.get("pageInfo")
    if not isinstance(info, dict):
        raise AliExpressParseError("AliExpress search data has no page info")
    mods = root.get("mods") or {}
    cards = [c for c in (mods.get("itemList") or {}).get("content") or [] if isinstance(c, dict)]
    currency = page_currency(root, cards)

    products: list[Product] = []
    recommended = 0
    for card in cards:
        if not is_product_card(card):
            recommended += 1
            continue
        product = parse_card(card, currency=currency, position=len(products) + 1)
        if product is not None:
            product.page = _int(info.get("page"))
            products.append(product)

    query = ((root.get("runConfigs") or {}).get("searchQuery")) or {}
    related = _component(data, "relatedSearch").get("relatedKeywords") or []
    tips = (mods.get("searchTips") or {}).get("content") or {}
    applied = applied_filters(mods)
    category = query.get("CatId")
    return SearchPage(
        url=url,
        page=_int(info.get("page")),
        page_size=_int(info.get("pageSize")),
        total=_int(info.get("totalResults")),
        result_type=_text(info.get("searchResultType")),
        finished=bool(info.get("finished")),
        currency=currency,
        search_text=_text(query.get("SearchText")),
        category_id=str(category) if category else None,
        products=products,
        recommended=recommended,
        applied=applied,
        filters=filter_options(mods, applied),
        related_searches=[
            name
            for name in (_text(r.get("displayName")) for r in related if isinstance(r, dict))
            if name
        ],
        message=_text(tips.get("tipsMessage")) if isinstance(tips, dict) else None,
    )
