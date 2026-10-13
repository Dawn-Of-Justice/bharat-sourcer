"""Add-to-cart links for a seller's order, built only from ids the store itself published.

Shopify stores take every line in one cart permalink (`/cart/<variant>:<qty>,...`); it
replaces that shop's cart. WooCommerce adds one simple product per `?add-to-cart=` link.
Other platforms have no public add-to-cart link, so they get none.
"""

from urllib.parse import parse_qs, urlsplit

from bharat_sourcer.schemas import VerifiedOffer

MAX_QTY = 10000


def cart_target(offer: VerifiedOffer) -> tuple[str, str, str] | None:
    """(platform, https host, id) for an offer that can be added to its store's cart."""
    parts = urlsplit(str(offer.url))
    if parts.scheme != "https" or not parts.hostname:
        return None
    if offer.verification == "shopify_storefront_json":
        # Variant offers carry their id in the URL (`?variant=`), including older ones.
        variant = parse_qs(parts.query).get("variant", [None])[0]
        cart_id = offer.cart_id or variant
        if cart_id and cart_id.isdigit():
            return "shopify", parts.hostname, cart_id
    if offer.verification == "woocommerce_store_api" and offer.cart_id:
        return "woocommerce", parts.hostname, offer.cart_id
    return None


def line_cart_url(offer: VerifiedOffer | None, packs: int) -> str | None:
    target = cart_target(offer) if offer else None
    if target is None or not 1 <= packs <= MAX_QTY:
        return None
    platform, host, cart_id = target
    if platform == "shopify":
        return f"https://{host}/cart/{cart_id}:{packs}?storefront=true"
    return f"https://{host}/?add-to-cart={cart_id}&quantity={packs}"


def seller_cart(
    entries: list[tuple[str, VerifiedOffer | None, int]],
) -> tuple[str | None, list[str]]:
    """One Shopify permalink for a seller's lines: (url, line ids it adds)."""
    added: dict[str, int] = {}
    ids: list[str] = []
    host = None
    for line_id, offer, packs in entries:
        target = cart_target(offer) if offer else None
        if target is None or target[0] != "shopify" or (host and target[1] != host):
            continue
        host = target[1]
        added[target[2]] = min(MAX_QTY, added.get(target[2], 0) + packs)
        ids.append(line_id)
    if not added:
        return None, []
    items = ",".join(f"{cart_id}:{qty}" for cart_id, qty in added.items())
    return f"https://{host}/cart/{items}?storefront=true", ids
