from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from aliexpress_scraper import build_search_url, product_id, product_url, search_url
from aliexpress_scraper.urls import (
    filter_params,
    is_search_url,
    normalize_attributes,
    query_slug,
    with_params,
)


def params(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


def test_plain_search_url():
    url = build_search_url("  phone   case ")
    assert url == "https://www.aliexpress.com/w/wholesale-phone-case.html?SearchText=phone+case"


def test_search_url_with_every_filter():
    url = build_search_url(
        "USB-C cable 100W",
        page=3,
        sort="price_asc",
        min_price=5,
        max_price="12.5",
        free_shipping=True,
        choice=True,
        ship_from="us",
        attributes=["3079-4148335", " 10483-4190422 ", "3079-4148335"],
    )
    assert urlsplit(url).path == "/w/wholesale-usb-c-cable-100w.html"
    assert params(url) == {
        "SearchText": ["USB-C cable 100W"],
        "page": ["3"],
        "SortType": ["price_asc"],
        "minPrice": ["5"],
        "maxPrice": ["12.5"],
        "selectedSwitches": ["filterCode:freeshipping,filterCode:choice_atm"],
        "shpf_co": ["US"],
        "attr": ["3079-4148335,10483-4190422"],
    }


def test_sort_values():
    assert params(build_search_url("x", sort="orders"))["SortType"] == ["total_tranpro_desc"]
    assert params(build_search_url("x", sort="price-desc"))["SortType"] == ["price_desc"]
    assert "SortType" not in params(build_search_url("x", sort="best-match"))


@pytest.mark.parametrize(
    "options",
    [
        {"sort": "newest"},
        {"min_price": 10, "max_price": 5},
        {"min_price": -1},
        {"min_price": "cheap"},
        {"ship_from": "USA"},
        {"attributes": ["black"]},
    ],
)
def test_invalid_filters(options):
    with pytest.raises(ValueError):
        build_search_url("x", **options)


def test_invalid_query_and_page():
    with pytest.raises(ValueError):
        build_search_url("   ")
    with pytest.raises(ValueError):
        build_search_url("x", page=0)
    with pytest.raises(ValueError):
        build_search_url("x", page=61)


def test_slug():
    assert query_slug("Wireless Earbuds (Bluetooth 5.3)") == "wireless-earbuds-bluetooth-5-3"
    assert query_slug("耳机") == "products"


def test_attributes_from_string():
    assert normalize_attributes("3079-4148335,10483-4190422") == ["3079-4148335", "10483-4190422"]
    assert normalize_attributes(None) == []


def test_filter_params_empty():
    assert filter_params() == []


def test_with_params_on_a_category_url():
    url = "https://www.aliexpress.com/category/100003109/women-clothing.html?page=4&spm=a2g0o"
    out = with_params(url, 2, filter_params(sort="orders"))
    assert urlsplit(out).path == "/category/100003109/women-clothing.html"
    assert params(out) == {"spm": ["a2g0o"], "page": ["2"], "SortType": ["total_tranpro_desc"]}
    assert "page" not in params(with_params(url, 1))


def test_search_url_helper():
    url = "https://www.aliexpress.com/w/wholesale-lamp.html?SearchText=lamp"
    assert params(search_url(url=url, page=2, choice=True)) == {
        "SearchText": ["lamp"],
        "page": ["2"],
        "selectedSwitches": ["filterCode:choice_atm"],
    }
    with pytest.raises(ValueError):
        search_url("lamp", url=url)
    with pytest.raises(ValueError):
        search_url(url="https://www.amazon.com/s?k=lamp")
    with pytest.raises(ValueError):
        search_url()
    with pytest.raises(TypeError):
        search_url("lamp", colour="red")


def test_is_search_url():
    assert is_search_url("https://www.aliexpress.com/w/wholesale-lamp.html")
    assert is_search_url("https://de.aliexpress.com/category/100003109/x.html")
    assert is_search_url("https://www.aliexpress.us/w/wholesale-lamp.html")
    assert not is_search_url("https://www.aliexpress.com/item/1005006016124137.html")
    assert not is_search_url("ftp://www.aliexpress.com/w/x.html")


def test_product_ids():
    assert product_url(1005006016124137) == "https://www.aliexpress.com/item/1005006016124137.html"
    assert product_id("https://www.aliexpress.us/item/3256805766812345.html?spm=x") == (
        "3256805766812345"
    )
    assert product_id(" 1005006016124137 ") == "1005006016124137"
    with pytest.raises(ValueError):
        product_id("https://www.aliexpress.com/store/123")
