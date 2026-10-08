from __future__ import annotations

import pytest
from conftest import CHALLENGE_HTML, FlakyError, card, cards, search_html

from aliexpress_scraper import (
    AliExpressBlockedError,
    AliExpressFilterError,
    AliExpressScraper,
    check_applied,
    parse_search_page,
)

SEARCH = "/w/wholesale-"


def test_search_one_page(make_scraper):
    scraper, client = make_scraper({SEARCH: search_html(cards(range(1, 4)))})
    products = scraper.search("Phone  Case")
    assert [p.id for p in products] == ["1", "2", "3"]
    assert all(p.query == "Phone Case" and p.page == 1 for p in products)
    assert client.urls() == [
        "https://www.aliexpress.com/w/wholesale-phone-case.html?SearchText=Phone+Case"
    ]
    assert client.calls[0][1] == {"proxy_country": "US"}


def test_country_routing(make_scraper):
    scraper, client = make_scraper({SEARCH: search_html(cards([1]))}, country=" gb ")
    scraper.search("lamp")
    assert client.calls[0][1] == {"proxy_country": "GB"}
    scraper, client = make_scraper({SEARCH: search_html(cards([1]))}, country=None)
    scraper.search("lamp")
    assert client.calls[0][1] == {}


def test_pages_stop_when_aliexpress_is_done(make_scraper):
    scraper, client = make_scraper(
        {
            SEARCH: search_html(cards(range(1, 61)), page=1, total=5000),
            "page=2": search_html(cards(range(61, 91)), page=2, total=5000, finished=True),
        }
    )
    products = scraper.search("lamp", pages=10)
    assert len(products) == 90 and len(client.calls) == 2
    assert products[-1].page == 2 and products[-1].position == 30


def test_pages_stop_at_the_last_page(make_scraper):
    scraper, client = make_scraper(
        {
            SEARCH: search_html(cards(range(1, 61)), page=1, total=70),
            "page=2": search_html(cards(range(61, 71)), page=2, total=70),
        }
    )
    assert len(scraper.search("lamp", pages=5)) == 70
    assert len(client.calls) == 2


def test_pages_stop_when_a_page_repeats(make_scraper):
    same = cards(range(1, 61))
    scraper, client = make_scraper({SEARCH: search_html(same, total=5000)})
    assert len(scraper.search("lamp", pages=5)) == 60
    assert len(client.calls) == 2


def test_zero_results(make_scraper):
    empty = search_html([], total=0, result_type="zero_result", finished=True)
    scraper, client = make_scraper({SEARCH: empty})
    assert scraper.search("zzqqxx", pages=3, sort="orders") == []
    assert len(client.calls) == 1


def test_limit(make_scraper):
    scraper, client = make_scraper({SEARCH: search_html(cards(range(1, 61)), total=5000)})
    assert [p.id for p in scraper.search("lamp", pages=5, limit=7)] == [str(i) for i in range(1, 8)]
    assert len(client.calls) == 1


def test_result_filters(make_scraper):
    page = [
        card("1", rating=4.9, sold=500, site_id=None),
        card("2", rating=4.2, sold=5000, site_id=None),
        card("3", rating=None, sold=None, sold_text=None, site_id=None),
        card("4", rating=4.8, sold=20, site_id=None),
        card("5", rating=5.0, sold=900, product_type="ad", site_id=None),
    ]
    scraper, _ = make_scraper({SEARCH: search_html(page)})
    found = scraper.search("lamp", min_rating=4.5, min_sold=100, skip_sponsored=True)
    assert [p.id for p in found] == ["1"]


def test_search_many_dedupes(make_scraper):
    scraper, client = make_scraper(
        {
            "SearchText=lamp": search_html(cards([1, 2, 3]), finished=True),
            "SearchText=desk+lamp": search_html(cards([3, 4]), finished=True),
        }
    )
    seen_queries = []
    found = scraper.search_many(
        ["lamp", "desk lamp"], on_query=lambda q, items: seen_queries.append((q, len(items)))
    )
    assert [p.id for p in found] == ["1", "2", "3", "4"]
    assert found[-1].query == "desk lamp"
    assert seen_queries == [("lamp", 3), ("desk lamp", 1)]


def test_retries_transient_errors(make_scraper, sleeps):
    retries = []
    scraper, client = make_scraper(
        {SEARCH: [FlakyError("timeout"), FlakyError("timeout"), search_html(cards([1]))]},
        on_retry=lambda attempt, delay, error: retries.append((attempt, delay)),
    )
    assert len(scraper.search("lamp")) == 1
    assert sleeps == [5.0, 10.0] and retries == [(1, 5.0), (2, 10.0)]
    assert len(client.calls) == 3


def test_retries_verification_challenges(make_scraper, sleeps):
    scraper, _ = make_scraper({SEARCH: [CHALLENGE_HTML, search_html(cards([1]))]})
    assert len(scraper.search("lamp")) == 1 and sleeps == [5.0]


def test_gives_up_after_retries(make_scraper, sleeps):
    scraper, client = make_scraper({SEARCH: CHALLENGE_HTML}, retries=2, max_backoff=7)
    with pytest.raises(AliExpressBlockedError):
        scraper.search("lamp")
    assert len(client.calls) == 3 and sleeps == [5.0, 7.0]


def test_other_errors_are_not_retried(make_scraper, sleeps):
    scraper, client = make_scraper({SEARCH: RuntimeError("bad key")})
    with pytest.raises(RuntimeError):
        scraper.search("lamp")
    assert len(client.calls) == 1 and sleeps == []


def test_filters_are_sent_and_verified(make_scraper):
    applied = search_html(
        cards([1]),
        sort=("orders", "desc"),
        switches=["filterCode:freeshipping"],
        ship_from="US",
        attributes=["3079-4148335"],
        price_range=(5, 10),
    )
    scraper, client = make_scraper({SEARCH: applied})
    found = scraper.search(
        "lamp",
        sort="orders",
        free_shipping=True,
        ship_from="us",
        attributes=["3079-4148335"],
        min_price=5,
        max_price=10,
    )
    assert len(found) == 1
    url = client.urls()[0]
    assert "SortType=total_tranpro_desc" in url and "shpf_co=US" in url and "minPrice=5" in url


def test_dropped_filters_raise(make_scraper):
    scraper, _ = make_scraper({SEARCH: search_html(cards([1]))})
    with pytest.raises(AliExpressFilterError) as info:
        scraper.search("lamp", sort="price-asc", choice=True, attributes="3079-4148335")
    message = str(info.value)
    assert "sort=price-asc" in message and "choice" in message and "3079-4148335" in message
    # the check can be switched off
    page = scraper.search_page("lamp", choice=True, check_filters=False)
    assert len(page.products) == 1


def test_check_applied_on_price_range():
    page = parse_search_page(search_html(cards([1]), price_range=(5, 10)))
    check_applied(page, min_price=5, max_price="10")
    with pytest.raises(AliExpressFilterError):
        check_applied(page, min_price=6)
    empty = parse_search_page(search_html([], result_type="zero_result"))
    check_applied(empty, sort="orders")  # nothing to check


def test_category_url_with_filters(make_scraper):
    url = "https://www.aliexpress.com/category/100003109/women-clothing.html"
    scraper, client = make_scraper(
        {
            "/category/": search_html(
                cards(range(1, 61)), sort=("orders", "desc"), search_text=None, category_id=1
            ),
        }
    )
    found = scraper.search(url=url, pages=2, sort="orders")
    assert len(found) == 60 and found[0].query == url
    first, second = client.urls()
    assert first == url + "?SortType=total_tranpro_desc"
    assert second == url + "?page=2&SortType=total_tranpro_desc"


def test_filters_lookup(make_scraper):
    scraper, client = make_scraper({SEARCH: search_html(cards([1]))})
    page = scraper.filters("lamp")
    assert page.filters and page.related_searches
    assert len(client.calls) == 1


def test_argument_errors(make_scraper):
    scraper, client = make_scraper({SEARCH: search_html(cards([1]))})
    with pytest.raises(ValueError):
        scraper.search("lamp", pages=0)
    with pytest.raises(ValueError):
        scraper.search("lamp", limit=0)
    with pytest.raises(TypeError):
        scraper.search("lamp", colour="red")
    with pytest.raises(ValueError):
        scraper.search()
    assert client.calls == []


def test_uses_the_sdk_client_by_default(monkeypatch):
    import scrapeunblocker

    made = {}

    class Client:
        def __init__(self, api_key=None, timeout=None):
            made.update(api_key=api_key, timeout=timeout)

    monkeypatch.setattr(scrapeunblocker, "Client", Client)
    AliExpressScraper(api_key="test-key", timeout=90)
    assert made == {"api_key": "test-key", "timeout": 90}
