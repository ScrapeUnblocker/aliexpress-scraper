from __future__ import annotations

import csv
import io
import json

import pytest
from conftest import FakeClient, card, cards, search_html

from aliexpress_scraper import AliExpressScraper, cli, csv_string, products_to_csv
from aliexpress_scraper.parsing import parse_search_page


@pytest.fixture
def fake(monkeypatch):
    """Route the CLI's scraper to a fake client; returns the client."""
    holder = {}

    def install(routes):
        client = FakeClient(routes)

        def make(args):
            return AliExpressScraper(
                client=client, country=args.country, retries=0, transient_errors=()
            )

        monkeypatch.setattr(cli, "_scraper", make)
        holder["client"] = client
        return client

    return install


def test_parser_defaults_and_options():
    args = cli.build_parser().parse_args(
        [
            "search",
            "phone case",
            "lamp",
            "--sort",
            "orders",
            "--attr",
            "3079-4148335",
            "--attr",
            "10483-4190422",
            "--free-shipping",
            "--min-rating",
            "4.5",
            "-p",
            "3",
            "-c",
            "gb",
        ]
    )
    assert args.queries == ["phone case", "lamp"] and args.pages == 3 and args.country == "gb"
    assert cli._filters(args) == {
        "sort": "orders",
        "free_shipping": True,
        "attributes": ["3079-4148335", "10483-4190422"],
    }
    assert args.min_rating == 4.5 and args.format == "json"
    defaults = cli.build_parser().parse_args(["search", "x"])
    assert defaults.country == "us" and defaults.retries == 3 and cli._filters(defaults) == {}


def test_bad_choices_exit():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["search", "x", "--sort", "newest"])
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["frobnicate"])


def test_dry_run(capsys):
    assert cli.main(["search", "desk lamp", "--choice", "--max-price", "20", "--dry-run"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == (
        "https://www.aliexpress.com/w/wholesale-desk-lamp.html?SearchText=desk+lamp"
        "&maxPrice=20&selectedSwitches=filterCode%3Achoice_atm"
    )


def test_invalid_values_return_2(capsys):
    assert cli.main(["search", "x", "--min-price", "9", "--max-price", "1", "--dry-run"]) == 2
    assert "min_price" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.main(["search"])  # neither QUERY nor --url


def test_search_json_to_stdout(fake, capsys):
    client = fake({"/w/": search_html(cards([1, 2]), finished=True)})
    assert cli.main(["search", "lamp", "-q", "-c", "de"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [p["id"] for p in data] == ["1", "2"] and data[0]["query"] == "lamp"
    assert client.calls[0][1] == {"proxy_country": "DE"}


def test_search_csv_to_file(fake, tmp_path, capsys):
    fake({"/w/": search_html(cards([1, 2]), finished=True)})
    out = tmp_path / "lamps.csv"
    assert cli.main(["search", "lamp", "-f", "csv", "-o", str(out)]) == 0
    raw = out.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM for Excel
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    assert [r["id"] for r in rows] == ["1", "2"]
    assert rows[0]["choice"] == "true" and "images" not in rows[0]
    assert rows[0]["category_ids"] == "202192403 | 202228401 | 202229005"
    err = capsys.readouterr().err
    assert "lamp: page 1/60 -> 2 products of 84,092 (USD)" in err and "wrote 2 product(s)" in err


def test_search_reports_loose_matches(fake, capsys):
    fake({"/w/": search_html(cards([1]), result_type="few_result", finished=True)})
    assert cli.main(["search", "zzqqxx", "-f", "jsonl"]) == 0
    captured = capsys.readouterr()
    assert "no close match" in captured.err and captured.out.count("\n") == 1


def test_search_filter_error_returns_1(fake, capsys):
    fake({"/w/": search_html(cards([1]))})
    assert cli.main(["search", "lamp", "--sort", "orders", "-q"]) == 1
    assert "AliExpressFilterError" in capsys.readouterr().err


def test_filters_command(fake, capsys):
    fake({"/w/": search_html([card()], switches=["filterCode:choice_atm"])})
    assert cli.main(["filters", "phone case", "-q"]) == 0
    out = capsys.readouterr().out
    assert "84,092 products, prices in USD" in out
    assert "Main color (--attr):" in out and "3079-4148335" in out and "Black" in out
    assert "--choice" in out and "[applied]" in out
    assert "Shipping from (--ship-from):" in out
    assert "Related searches:" in out


def test_filters_command_json(fake, capsys):
    fake({"/w/": search_html([card()])})
    assert cli.main(["filters", "phone case", "--json", "-q"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["currency"] == "USD" and data["filters"][0]["kind"] == "sort"


def test_csv_helpers():
    products = parse_search_page(search_html([card()])).products
    text = csv_string(products)
    assert text.splitlines()[0].startswith("id,title,url,price")
    assert "images" in text.splitlines()[0]
    buffer = io.StringIO()
    assert products_to_csv(products, buffer) == 1
    assert ",images," not in buffer.getvalue().splitlines()[0]
