from veriweb.domains import publisher_domain


def test_publisher_subdomains_do_not_count_as_independent_sources() -> None:
    assert publisher_domain("https://www.publisher.co.uk/article") == "publisher.co.uk"
    assert publisher_domain("https://news.publisher.co.uk/article") == "publisher.co.uk"
    assert publisher_domain("https://publisher.co.uk/article") == "publisher.co.uk"


def test_private_suffix_tenants_and_unknown_test_domains_remain_distinct() -> None:
    assert publisher_domain("https://one.blogspot.com/article") != publisher_domain(
        "https://two.blogspot.com/article"
    )
    assert publisher_domain("https://source1.example/article") == "source1.example"
