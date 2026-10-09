import pytest

from bharat_sourcer.sourcing.sellers import (
    canonical_url,
    host_of,
    identify,
    registrable_domain,
    same_listing,
)


@pytest.mark.parametrize(
    "host,domain",
    [
        ("https://WWW.Probots.co.in./product", "probots.co.in"),
        ("m.robocraze.com", "robocraze.com"),
        ("amp.example.com", "example.com"),
        ("new.myshopify.com", "new.myshopify.com"),
        ("new.mydukaan.io", "new.mydukaan.io"),
        ("new.myinstamojo.com", "new.myinstamojo.com"),
        ("dir.indiamart.com", "indiamart.com"),
    ],
)
def test_domains(host, domain):
    assert registrable_domain(host) == domain


def test_identity():
    assert identify("https://www.rytronics.in/x").name == "Rytronics"
    assert identify("https://m.amazon.in/dp/x").kind == "marketplace"
    assert identify("https://new.myshopify.com/x").kind == "platform_hosted"
    assert host_of("xn--bcher-kva.example") == "bücher.example"


def test_url_comparison_keeps_variants_and_path_case():
    assert canonical_url("http://www.example.com./P?utm_source=x&variant=12#x") == (
        "http://www.example.com/P?variant=12"
    )
    assert same_listing("/P?variant=12", "http://www.example.com/P/?variant=12&utm_source=x")
    assert not same_listing("https://example.com/P?variant=12", "https://example.com/P?variant=13")
    assert not same_listing("https://example.com/P", "https://example.com/p")
