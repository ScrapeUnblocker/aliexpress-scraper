"""Shared fixtures: synthetic AliExpress search pages shaped like the real ones.

AliExpress search and category pages embed their data as::

    window._dida_config_._init_data_= { data: {"hierarchy": ..., "data": {...}} }

with the page info, sort bar, filters and product cards under
``data.root.fields``. The builders below produce the same structure so the
tests run offline and spend no API credit.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any

import pytest

IMG = "//ae-pic-a1.aliexpress-media.com/kf/S28f397c19b0040ecac9bc4a3f73a9f123.jpg"
IMG2 = "//ae-pic-a1.aliexpress-media.com/kf/Se9b8691758c7472eb920fbeb39052084c.jpg"


def point(source: str, text: str | None = None) -> dict[str, Any]:
    """A selling point (badge) on a card: an image tag, or a text tag if ``text``."""
    if text is None:
        content: dict[str, Any] = {"displayTagType": "image", "tagImgUrl": "https://x/tag.png"}
    else:
        content = {"displayTagType": "text", "tagText": text}
    return {"sellingPointTagId": "m0000094", "source": source, "tagContent": content}


def card(
    item_id: str = "1005010439419248",
    title: str = "Magnetic Clear Case For iPhone 17 16 15",
    *,
    price: float | None = 1.33,
    original: float | None = 3.22,
    discount: int | None = 58,
    currency: str = "USD",
    symbol: str = "US $",
    rating: float | None = 4.9,
    sold: int | None = 59637,
    sold_text: str | None = "50,000+ sold",
    product_type: str = "natural",
    points: Sequence[dict[str, Any]] = (
        point("choice_atm"),
        point("ETA_atm", "Delivery: Oct 16 - 20"),
        point("1000668623", "Top selling on AliExpress"),
    ),
    delivery: str | None = "8,12,2026-10-16,2026-10-20",
    hidden_cents: int | None = None,
    site_id: str | None = "3256810253104496",
    listed: str = "2025-11-25 00:00:00",
    categories: str = "202192403,202228401,202229005",
    sku: str | None = "12000059808812185",
    detail_url: str | None = None,
) -> dict[str, Any]:
    """One product card from ``mods.itemList.content``.

    ``price=None`` builds a new-shopper card without a ``prices`` block; its
    tracking data carries ``hidden_cents`` (if given) as the sale price.
    """
    tracking: dict[str, Any] = {"x_object_id": item_id, "categoryId": categories}
    if sold is not None:
        tracking["real_trade_count"] = str(sold)
    if delivery is not None:
        tracking["delivery_info"] = delivery
    raw: dict[str, Any] = {
        "redirectedId": site_id or item_id,
        "itemType": "productV3",
        "productType": product_type,
        "productId": site_id or item_id,
        "lunchTime": listed,
        "image": {"imgUrl": IMG, "imgWidth": 350, "imgHeight": 350},
        "images": [{"imgUrl": IMG}, {"imgUrl": IMG2}],
        "title": {"displayTitle": title},
        "sellingPoints": list(points),
        "trace": {"utLogMap": tracking},
    }
    if price is not None:
        prices: dict[str, Any] = {
            "skuId": sku,
            "currencySymbol": "$",
            "salePrice": {
                "currencyCode": currency,
                "minPrice": price,
                "formattedPrice": f"{symbol}{price:.2f}",
                "cent": round(price * 100),
            },
        }
        if discount is not None:
            prices["salePrice"]["discount"] = discount
        if original is not None:
            prices["originalPrice"] = {"currencyCode": currency, "minPrice": original}
        raw["prices"] = prices
        tracking["salePriceAmount"] = str(round(price * 100))
        if sku:
            tracking["sku_id"] = sku
    elif hidden_cents is not None:
        tracking["salePriceAmount"] = str(hidden_cents)
    if rating is not None:
        raw["evaluation"] = {"starRating": rating}
    if sold_text is not None:
        raw["trade"] = {"tradeDesc": sold_text}
    if detail_url is not None:
        raw["productDetailUrl"] = detail_url
    return raw


def recommendation(item_id: str = "1005009307329056") -> dict[str, Any]:
    """A "more to love" card AliExpress appends after the real results."""
    return {
        "productType": "natural",
        "tItemType": "ahe_app_rcmd_new_card",
        "productId": item_id,
        "title": {"displayTitle": "Unrelated recommended product"},
        "prices": {"salePrice": {"currencyCode": "USD", "minPrice": 10.78}},
    }


def _switch(value: str, text: str, selected: Iterable[str]) -> dict[str, Any]:
    return {"selectedValue": value, "text": text, "selected": value in selected}


def search_html(
    cards: list[dict[str, Any]],
    *,
    page: int | None = 1,
    total: int = 84092,
    page_size: int = 60,
    result_type: str = "normal_result",
    finished: bool = False,
    currency: str | None = "USD",
    sort: tuple[str, str] = ("default", "default"),
    switches: Iterable[str] = (),
    ship_from: str | None = None,
    attributes: Iterable[str] = (),
    price_range: tuple[float, float] | None = None,
    search_text: str | None = "phone case",
    category_id: int | None = None,
    related: Iterable[str] = ("glass phone case", "magsafe case"),
    tips: str | None = None,
) -> str:
    """A search page with its embedded ``_init_data_`` (as getPageSource returns it)."""
    switches, attributes = list(switches), list(attributes)
    sort_bar = []
    for sort_type, orders in (
        ("default", ["default"]),
        ("orders", ["desc"]),
        ("price", ["asc", "desc"]),
    ):
        sort_bar.append(
            {
                "sortType": sort_type,
                "sortOrders": [
                    {"order": o, "selected": (sort_type, o) == tuple(sort)} for o in orders
                ],
            }
        )
    groups: list[dict[str, Any]] = [
        {
            "type": "featureSwitchGroup",
            "paramName": "selectedSwitches",
            "title": "Deals & discounts",
            "existSelectedValue": "filterCode:freeshipping" in switches,
            "content": [_switch("filterCode:freeshipping", "Free shipping", switches)],
        },
        {
            "type": "featureSwitchGroup",
            "paramName": "selectedSwitches",
            "title": "Delivery & service",
            "content": [
                _switch("filterCode:shipfrom", "Local+", switches),
                _switch("filterCode:choice_atm", "Choice", switches),
            ],
        },
        {
            "type": "featureSwitchGroup",
            "paramName": "selectedSwitches",
            "title": "Quality & trust",
            "content": [_switch("filterCode:4StarRating", "& up", switches)],
        },
        {
            "attributeId": "3079",
            "type": "attribute",
            "paramName": "attr",
            "title": "Main color",
            "content": [
                _switch("3079-4148335", "Black", attributes),
                _switch("3079-4148340", "Pink", attributes),
            ],
        },
        {
            "attributeId": "10483",
            "type": "attribute",
            "paramName": "attr",
            "title": "Main Material",
            "content": [_switch("10483-4190422", "TPU", attributes)],
        },
        {
            "type": "logistics",
            "paramName": "shpf_co",
            "title": "Shipping from ",
            "content": [
                {"selectedValue": "US", "text": "United States", "selected": ship_from == "US"}
            ],
        },
        {"type": "views", "paramName": "style", "title": "View as ", "content": []},
    ]
    price_group: dict[str, Any] = {"type": "priceRange", "paramName": "pr", "content": []}
    if price_range:
        price_group["minPrice"] = f"{price_range[0]:.1f}"
        price_group["maxPrice"] = f"{price_range[1]:.1f}"
    groups.append(price_group)
    mods: dict[str, Any] = {
        "searchRefineFilters": {"content": groups},
        "sortBar": {"content": sort_bar},
    }
    if cards:
        mods["itemList"] = {"content": cards}
    if tips:
        mods["searchTips"] = {"content": {"tipsMessage": tips, "tipsType": "no_items_found"}}
    trace: dict[str, Any] = {"page": {"ab": "1"}}
    if currency:
        trace["utLogMap"] = {"currency": currency}
    search_query: dict[str, Any] = {"isCategoryBrowse": category_id is not None}
    if search_text:
        search_query["SearchText"] = search_text
    if category_id:
        search_query["CatId"] = category_id
    root = {
        "pageInfo": {
            "searchResultType": result_type,
            "totalResults": total,
            "page": page,
            "pageSize": page_size,
            "finished": finished,
            "trace": trace,
        },
        "mods": mods,
        "runConfigs": {"searchQuery": search_query},
    }
    data = {
        "hierarchy": {"root": "root"},
        "data": {
            "root": {"id": "root", "fields": root},
            "relatedSearch_3741": {
                "fields": {"relatedKeywords": [{"displayName": r, "name": "1"} for r in related]}
            },
        },
        "global": {},
    }
    return (
        "<!DOCTYPE html>\n<html>\n <head>\n  <script>\n"
        # a decoy: the page's loader script mentions _init_data_ before the data itself
        "   if(window._dida_config_&&!window._dida_config_._init_data_){var t=1}\n"
        '   window._dida_config_ = {"pageName":"search-pc"};'
        "/*!-->init-data-start--*/ window._dida_config_._init_data_= { data: "
        f"{json.dumps(data)} }}\n  </script>\n </head>\n <body></body>\n</html>"
    )


CHALLENGE_HTML = (
    '<html><body><iframe src="https://acs.aliexpress.com//h5/x/1.0/_____tmd_____/punish'
    '?x5secdata=abc&action=captcha"></iframe></body></html>'
)


def cards(ids: Iterable[str], **options: Any) -> list[dict[str, Any]]:
    return [card(str(i), f"Product {i}", site_id=None, **options) for i in ids]


class FakeClient:
    """Stands in for ``scrapeunblocker.Client``.

    ``routes`` maps a URL substring to a response, or to a list of responses
    used in order (an Exception instance is raised instead of returned). Keys
    are tried last to first, so list the more specific ones later.
    """

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = {k: (list(v) if isinstance(v, list) else v) for k, v in routes.items()}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_page_source(self, url: str, **options: Any) -> str:
        self.calls.append((url, options))
        for key in reversed(list(self.routes)):
            if key in url:
                value = self.routes[key]
                if isinstance(value, list):
                    value = value.pop(0) if len(value) > 1 else value[0]
                if isinstance(value, BaseException):
                    raise value
                return value
        raise AssertionError(f"unexpected URL {url}")

    def urls(self) -> list[str]:
        return [url for url, _ in self.calls]


class FlakyError(Exception):
    """A transient error type for retry tests."""


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def make_scraper(sleeps):
    from aliexpress_scraper import AliExpressScraper

    def make(routes: dict[str, Any], **options: Any) -> tuple[AliExpressScraper, FakeClient]:
        client = FakeClient(routes)
        options.setdefault("transient_errors", (FlakyError,))
        scraper = AliExpressScraper(client=client, sleep=sleeps.append, **options)
        return scraper, client

    return make
