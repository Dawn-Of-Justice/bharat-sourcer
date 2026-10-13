"""Add-to-cart links for the order plan, from each offer's cart engine recipe.

The recipe (sourcing/cart_engine.py) is decided per store from its own add-to-cart form;
this module only fills in ids and quantities. No store or platform is special-cased here.
"""

from urllib.parse import urlsplit

from bharat_sourcer.schemas import VerifiedOffer
from bharat_sourcer.sourcing.cart_engine import render, render_many

MAX_QTY = 10000


def line_cart_url(offer: VerifiedOffer | None, packs: int) -> str | None:
    if offer is None or offer.cart_recipe is None or not offer.cart_id:
        return None
    if not 1 <= packs <= MAX_QTY:
        return None
    return render(offer.cart_recipe, offer.cart_id, packs, str(offer.url))


def seller_cart(
    entries: list[tuple[str, VerifiedOffer | None, int]],
) -> tuple[str | None, list[str], bool]:
    """One link adding several of a seller's lines, when its recipe supports that.

    Returns (url, line ids it adds, whether it empties the cart first).
    """
    usable = [
        (line_id, offer, packs)
        for line_id, offer, packs in entries
        if offer and offer.cart_recipe and offer.cart_recipe.multi_url and offer.cart_id
    ]
    if not usable:
        return None, [], False
    recipe = usable[0][1].cart_recipe
    host = urlsplit(str(usable[0][1].url)).hostname
    added: dict[str, int] = {}
    ids: list[str] = []
    for line_id, offer, packs in usable:
        cart_id = offer.cart_id
        if not cart_id or offer.cart_recipe != recipe or urlsplit(str(offer.url)).hostname != host:
            continue
        added[cart_id] = min(MAX_QTY, added.get(cart_id, 0) + packs)
        ids.append(line_id)
    url = render_many(recipe, list(added.items()))
    return (url, ids, recipe.replaces_cart) if url else (None, [], False)
