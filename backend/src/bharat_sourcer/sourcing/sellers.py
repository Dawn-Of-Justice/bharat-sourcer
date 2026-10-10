"""Shared seller identity and conservative listing URL comparison. No network lookups."""

import contextlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

IN_SECOND_LEVEL = {"co", "net", "org", "firm", "gen", "ind", "ac", "edu", "res", "gov", "mil"}
PLATFORM_SUFFIXES = {
    "myshopify.com",
    "mydukaan.io",
    "dukaan.app",
    "myinstamojo.com",
    "instamojo.com",
    "wixsite.com",
    "zohocommerce.in",
    "zohostore.in",
    "blogspot.com",
}
MARKETPLACES = {
    "amazon.in": "Amazon India",
    "flipkart.com": "Flipkart",
    "meesho.com": "Meesho",
    "indiamart.com": "IndiaMART",
    "moglix.com": "Moglix",
    "industrybuying.com": "Industrybuying",
    "snapdeal.com": "Snapdeal",
    "tatacliq.com": "Tata CLiQ",
    "jiomart.com": "JioMart",
}
TRACKING = {
    "srsltid",
    "gclid",
    "gbraid",
    "wbraid",
    "fbclid",
    "msclkid",
    "_pos",
    "_psq",
    "_ss",
    "_sid",
    "_v",
    "_fid",
    "ref",
    "ref_",
    "tag",
    "sr",
    "qid",
    "keywords",
    "spm",
    "mc_cid",
    "mc_eid",
}
REGISTRY = json.loads((Path(__file__).parent / "known_sellers.json").read_text("utf-8"))["sellers"]


def host_of(url_or_host: str) -> str:
    parts = urlsplit(url_or_host if "://" in url_or_host else "//" + url_or_host)
    host = (parts.hostname or "").lower().rstrip(".")
    with contextlib.suppress(UnicodeError, ValueError):
        host = host.encode("ascii").decode("idna")
    while host.split(".")[0] in {"www", "m", "amp"}:
        host = host.split(".", 1)[1] if "." in host else ""
    return host.casefold()


def registrable_domain(host: str) -> str:
    host = host_of(host)
    for suffix in PLATFORM_SUFFIXES:
        if host.endswith("." + suffix):
            return ".".join(host.split(".")[-(len(suffix.split(".")) + 1) :])
    labels = host.split(".")
    count = 3 if len(labels) >= 3 and labels[-1] == "in" and labels[-2] in IN_SECOND_LEVEL else 2
    return ".".join(labels[-count:])


@dataclass(frozen=True)
class SellerIdentity:
    domain: str
    name: str
    kind: Literal["direct", "marketplace", "platform_hosted"]


def identify(url: str) -> SellerIdentity:
    domain = registrable_domain(url)
    if domain in MARKETPLACES:
        return SellerIdentity(domain, MARKETPLACES[domain], "marketplace")
    if any(domain.endswith("." + suffix) for suffix in PLATFORM_SUFFIXES):
        return SellerIdentity(domain, domain, "platform_hosted")
    for seller in REGISTRY:
        aliases = [seller["domain"], (seller.get("search") or {}).get("host", "")]
        if any(alias and registrable_domain(alias) == domain for alias in aliases):
            return SellerIdentity(domain, seller["name"], "direct")
    return SellerIdentity(domain, domain, "direct")


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING and not k.lower().startswith(("utm_", "pf_rd_", "pd_rd_"))
    ]
    # Preserve the fetch authority, credentials and port; SafeFetcher validates them.
    netloc = parts.netloc
    if parts.hostname and parts.hostname.endswith("."):
        netloc = netloc.replace(parts.hostname, parts.hostname.rstrip("."), 1)
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), ""))


def listing_key(url: str) -> str:
    parts = urlsplit(canonical_url(url))
    path = re.sub(r"%[0-9a-fA-F]{2}", lambda m: m.group().upper(), parts.path.rstrip("/"))
    host = host_of(url)
    if parts.port and parts.port not in {80, 443}:
        host += f":{parts.port}"
    return urlunsplit(
        ("https", host, path, urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True))), "")
    )


def same_listing(a: str, b: str, base: str | None = None) -> bool:
    return listing_key(urljoin(base or b, a)) == listing_key(urljoin(base or a, b))
