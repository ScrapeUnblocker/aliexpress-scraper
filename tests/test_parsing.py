from __future__ import annotations

import pytest
from conftest import CHALLENGE_HTML, card, point, recommendation, search_html

from aliexpress_scraper import (
    AliExpressBlockedError,
    AliExpressParseError,
    parse_search_page,
)
from aliexpress_scraper.parsing import exact_sold, parse_card, parse_delivery


def test_priced_card():
    page = parse_search_page(search_html([card()]), "https://www.aliexpress.com/w/x.html")
    (p,) = page.products
    # the item ID comes from the tracking data, not the storefront's own ID
    assert p.id == "1005010439419248"
    assert p.url == "https://www.aliexpress.com/item/1005010439419248.html"
    assert p.title == "Magnetic Clear Case For iPhone 17 16 15"
    assert (p.price, p.original_price, p.discount_percent) == (1.33, 3.22, 58)
    assert p.currency == "USD" and p.price_text == "US $1.33"
    assert p.price_hidden is False and p.welcome_deal is False
    assert p.rating == 4.9
    assert p.sold == 59637 and p.sold_text == "50,000+ sold"
    assert p.choice is True and p.free_shipping is False and p.sponsored is False
    # the delivery text is parsed into fields, not repeated as a badge
    assert p.badges == ["Top selling on AliExpress"]
    assert (p.delivery_min_days, p.delivery_max_days) == (8, 12)
    assert (p.delivery_from, p.delivery_to) == ("2026-10-16", "2026-10-20")
    assert p.listed_date == "2025-11-25"
    assert p.category_ids == ["202192403", "202228401", "202229005"]
    assert p.sku_id == "12000059808812185"
    assert p.image.startswith("https://ae-pic-a1.aliexpress-media.com/")
    assert len(p.images) == 2 and p.images[0] == p.image
    assert (p.page, p.position) == (1, 1)


def test_hidden_price_comes_from_tracking_data():
    hidden = card(
        "1005010018401645",
        price=None,
        hidden_cents=133,
        points=[point("choice_atm"), point("card_new_user_freegift_atm")],
        detail_url="https://www.aliexpress.com/ssr/1/welcomegiftspmpc?productIds=1&skuId=12000050854070498",
    )
    (p,) = parse_search_page(search_html([hidden])).products
    assert p.price == 1.33 and p.currency == "USD"
    assert p.price_hidden is True and p.welcome_deal is True
    assert p.original_price is None and p.discount_percent is None and p.price_text is None
    assert p.sku_id == "12000050854070498"


def test_free_gift_card_without_any_price():
    (p,) = parse_search_page(search_html([card(price=None)])).products
    assert p.price is None and p.currency is None and p.price_hidden is True


def test_sponsored_card_and_sold_from_label():
    ad = card("1005013147079642", product_type="ad", sold=None, sold_text="498 sold", rating=None)
    rounded = card("1005000000000001", sold=None, sold_text="10,000+ sold")
    first, second = parse_search_page(search_html([ad, rounded])).products
    assert first.sponsored is True and first.sold == 498 and first.rating is None
    assert second.sold is None and second.sold_text == "10,000+ sold"


def test_flags_from_selling_points():
    flagged = card(
        points=[
            point("Free_Shipping_atm", "Free shipping"),
            point("localplus_flag"),
            point("card_new_user_welcomedeal_atm"),
            point("lowest_price_90_atm", "Lowest price in 90 days"),
        ]
    )
    (p,) = parse_search_page(search_html([flagged])).products
    assert p.free_shipping and p.local_warehouse and p.welcome_deal and not p.choice
    assert p.badges == ["Free shipping", "Lowest price in 90 days"]


def test_recommendations_are_dropped():
    page = parse_search_page(search_html([card(), recommendation(), recommendation("2")]))
    assert len(page.products) == 1 and page.recommended == 2


def test_legacy_item_ids_and_cards_without_id():
    legacy = card("33030095240", site_id="2251832843780488")
    broken = card()
    broken["trace"] = {}
    broken["productId"] = None
    page = parse_search_page(search_html([legacy, broken]))
    assert [p.id for p in page.products] == ["33030095240"]


def test_page_info():
    page = parse_search_page(search_html([card()], page=2, total=84092), "u")
    assert (page.page, page.page_size, page.total) == (2, 60, 84092)
    assert page.total_pages == 60  # 1,402 pages of results, but AliExpress serves 60
    assert page.has_next is True
    assert page.result_type == "normal_result" and page.search_text == "phone case"
    assert page.related_searches == ["glass phone case", "magsafe case"]
    assert page.to_dict()["total_pages"] == 60

    small = parse_search_page(search_html([card()], total=100))
    assert small.total_pages == 2 and small.has_next is True
    last = parse_search_page(search_html([card()], page=2, total=100))
    assert last.has_next is False
    done = parse_search_page(search_html([card()], finished=True))
    assert done.has_next is False


def test_zero_results_and_category_pages():
    empty = parse_search_page(
        search_html([], total=0, result_type="zero_result", finished=True, tips="No results")
    )
    assert empty.products == [] and empty.has_next is False and empty.message == "No results"
    category = parse_search_page(search_html([card()], search_text=None, category_id=100003109))
    assert category.category_id == "100003109" and category.search_text is None


def test_currency_fallbacks():
    gbp = card(currency="GBP")
    hidden = card("1005000000000002", price=None, hidden_cents=99)
    page = parse_search_page(search_html([gbp, hidden], currency=None))
    assert page.currency == "GBP"
    assert [p.currency for p in page.products] == ["GBP", "GBP"]


def test_applied_filters_and_options():
    page = parse_search_page(
        search_html(
            [card()],
            sort=("orders", "desc"),
            switches=["filterCode:freeshipping", "filterCode:choice_atm"],
            ship_from="US",
            attributes=["3079-4148335"],
            price_range=(5, 10),
        )
    )
    assert page.applied == {
        "sort": "orders",
        "switches": ["filterCode:freeshipping", "filterCode:choice_atm"],
        "ship_from": "US",
        "attributes": ["3079-4148335"],
        "min_price": 5.0,
        "max_price": 10.0,
    }
    kinds = [g.kind for g in page.filters]
    assert kinds == ["sort", "switch", "attribute", "attribute", "ship_from"]
    sort, switch, color = page.filters[:3]
    assert [o.value for o in sort.options if o.selected] == ["orders"]
    # only the switches this package supports are offered
    assert [(o.value, o.selected) for o in switch.options] == [
        ("free_shipping", True),
        ("choice", True),
    ]
    assert color.title == "Main color" and color.param == "attr"
    assert [(o.value, o.label, o.selected) for o in color.options] == [
        ("3079-4148335", "Black", True),
        ("3079-4148340", "Pink", False),
    ]
    assert page.filters[-1].options[0].value == "US"


def test_default_sort_echo():
    page = parse_search_page(search_html([card()]))
    assert page.applied["sort"] == "best-match" and page.applied["min_price"] is None


def test_challenge_and_missing_data():
    with pytest.raises(AliExpressBlockedError):
        parse_search_page(CHALLENGE_HTML)
    with pytest.raises(AliExpressParseError):
        parse_search_page("<html><body>Loading...</body></html>")
    with pytest.raises(AliExpressParseError):
        parse_search_page("window._dida_config_._init_data_= { data: {broken")
    assert issubclass(AliExpressBlockedError, AliExpressParseError)


def test_helpers():
    assert exact_sold("498 sold") == 498
    assert exact_sold("1,234 sold") == 1234
    assert exact_sold("2 verkauft") == 2
    assert exact_sold("5.000+ verkauft") is None
    assert exact_sold("100K+ sold") is None
    assert exact_sold(None) is None
    assert parse_delivery("8,12,2026-10-16,2026-10-20") == (8, 12, "2026-10-16", "2026-10-20")
    assert parse_delivery(",,,") == (None, None, None, None)
    assert parse_delivery(None) == (None, None, None, None)
    assert parse_card({"trace": {"utLogMap": {}}}) is None
