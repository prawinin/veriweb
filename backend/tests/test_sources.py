from bs4 import BeautifulSoup
from veriweb.sources import article_links, prioritize_urls, source_type, table_text


def test_relevant_institutional_source_moves_ahead_of_marketing_results() -> None:
    candidates = [
        ("https://battery-shop.example/blog", "Why our sodium-ion batteries are best"),
        (
            "https://www.energy.gov/research/batteries",
            "Sodium-ion battery cost and cycle lifetime study",
        ),
        ("https://www.energy.gov/unrelated", "Department office addresses"),
    ]
    selected = prioritize_urls(candidates, "sodium-ion battery cost lifetime", 3)
    assert selected[0][0].endswith("/research/batteries")
    assert source_type(selected[0][0], selected[0][1]) == "public_institution"


def test_table_preserves_column_headers_and_quantities() -> None:
    soup = BeautifulSoup(
        "<table><tr><th>Metric</th><th>Sodium-ion</th><th>Lithium-ion</th></tr><tr><td>Cell cost</td><td>$70/kWh</td><td>$95/kWh</td></tr></table>",
        "html.parser",
    )
    text = table_text(soup)
    assert "| Metric | Sodium-ion | Lithium-ion |" in text
    assert "| Cell cost | $70/kWh | $95/kWh |" in text


def test_follow_links_remain_same_publisher_and_skip_control_urls() -> None:
    soup = BeautifulSoup(
        '<a href="/research/report">Battery cost report</a><a href="https://evil.example/report">Other site</a><a href="javascript:alert(1)">Battery specs</a><a href="/logout">Log out</a>',
        "html.parser",
    )
    links = article_links(soup, "https://lab.example/news")
    assert [(link.url, link.title) for link in links] == [
        ("https://lab.example/research/report", "Battery cost report")
    ]
