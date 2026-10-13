"""Cart engine and add-to-cart links on the order plan.

Every store, page, id and Gemini answer here is SYNTHETIC test data (example.com shops);
no network call runs: Gemini answers come from httpx.MockTransport.
"""

import json

import httpx

from bharat_sourcer.carts import line_cart_url, seller_cart
from bharat_sourcer.config import Settings
from bharat_sourcer.recommend import build_order_plan
from bharat_sourcer.schemas import (
    BomItem,
    CartRecipe,
    LineRecommendation,
    Report,
    ReportLine,
    VerifiedOffer,
)
from bharat_sourcer.sourcing.cart_engine import CartEngine
from bharat_sourcer.sourcing.fetch import Page

PERMALINK = {
    "reason": "Synthetic store: cart permalinks.",
    "mode": "multi",
    "path": "/cart/add",
    "id_param": "id",
    "qty_param": "quantity",
    "fixed_params": [],
    "multi_path": "/cart/",
    "pair_sep": ":",
    "item_sep": ",",
    "id_field": "id",
    "replaces_cart": True,
}


def page(url, form):
    html = f"<html><body><h1>Synthetic product</h1>{form}</body></html>"
    return Page(url=url, status=200, headers={"content-type": "text/html"}, body=html.encode())


def shop_form(variant):
    return (
        '<form action="/cart/add" method="post">'
        f'<input type="hidden" name="id" value="{variant}">'
        '<input name="quantity" value="1"><button name="add">Add to cart</button></form>'
    )


def offer(url, price="100.00"):
    return VerifiedOffer(
        url=url, seller=url.split("/")[2], title="Synthetic listing", price_inr=price
    )


class DictCache(dict):
    def set(self, key, value, ttl_s):
        self[key] = value


def engine(answer, cache=None):
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        text = json.dumps(answer)
        return httpx.Response(
            200,
            json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]},
        )

    settings = Settings(_env_file=None, demo_mode=False, gemini_api_key="test-secret")
    return CartEngine(settings, transport=httpx.MockTransport(handle), cache=cache), calls


def test_one_call_per_store_then_every_listing_reads_its_own_id():
    cache = DictCache()
    carts, calls = engine(PERMALINK, cache)
    urls = ["https://shop.example/products/esp32", "https://shop.example/products/oled"]
    offers = [offer(url) for url in urls]
    carts.label_offers(offers, [page(urls[0], shop_form(111)), page(urls[1], shop_form(222))])
    assert len(calls) == 1
    sent = json.loads(calls[0]["contents"][0]["parts"][0]["text"])
    assert sent["forms"][0]["action"] == "/cart/add"
    assert [o.cart_id for o in offers] == ["111", "222"]
    assert (
        offers[0].cart_recipe.single_url == "https://shop.example/cart/add?id={id}&quantity={qty}"
    )
    # Another worker sharing the cache makes no call.
    again, more = engine(PERMALINK, cache)
    later = offer("https://shop.example/products/led")
    again.label_offers([later], [page(str(later.url), shop_form(333))])
    assert more == [] and later.cart_id == "333"


def test_pages_without_a_cart_form_cost_nothing():
    carts, calls = engine(PERMALINK)
    item = offer("https://n.example/p/2")
    carts.label_offers([item], [page("https://n.example/p/2", "<p>Call us to order</p>")])
    assert calls == [] and item.cart_recipe is None


def test_an_id_from_buttons_outside_forms_must_be_unambiguous():
    answer = {**PERMALINK, "mode": "single", "id_field": "data-product_id"}
    related = "".join(
        f'<a class="add_to_cart_button" data-product_id="{n}">Add to basket</a>' for n in (5, 6)
    )
    carts, _ = engine(answer)
    item = offer("https://shop.example/products/esp32")
    carts.label_offers([item], [page(str(item.url), related)])
    assert item.cart_recipe is None
    alone, _ = engine(answer)
    item = offer("https://shop.example/products/esp32")
    single = '<a class="add_to_cart_button" data-product_id="7">Add to basket</a>'
    alone.label_offers([item], [page(str(item.url), single)])
    assert item.cart_id == "7"


def test_unsafe_or_unknown_answers_give_no_link():
    for bad in [
        {**PERMALINK, "path": "https://evil.example/add"},
        {**PERMALINK, "path": "/cart/add?id=1 /other"},
        {**PERMALINK, "qty_param": "id"},
        {**PERMALINK, "fixed_params": [{"name": "t", "value": "a b&c=d"}]},
        {**PERMALINK, "id_field": "sku"},
    ]:
        carts, _ = engine(bad)
        item = offer("https://shop.example/products/esp32")
        carts.label_offers([item], [page(str(item.url), shop_form(111))])
        assert item.cart_recipe is None, bad


def test_a_link_on_the_product_page_itself_serves_the_whole_store():
    answer = {
        **PERMALINK,
        "mode": "single",
        "path": "/product/esp32/",
        "id_param": "add-to-cart",
        "id_field": "",
    }
    woo = (
        '<form class="cart" action="https://woo.example/product/esp32/" method="post">'
        '<input name="quantity" value="1">'
        '<button name="add-to-cart" value="555">Add to cart</button></form>'
    )
    carts, calls = engine(answer)
    first = offer("https://woo.example/product/esp32/")
    carts.label_offers([first], [page(str(first.url), woo)])
    assert first.cart_id == "555"
    assert (
        line_cart_url(first, 2) == "https://woo.example/product/esp32/?add-to-cart=555&quantity=2"
    )
    other = offer("https://woo.example/product/oled/")
    oled = woo.replace("555", "556").replace("/product/esp32/", "/product/oled/")
    carts.label_offers([other], [page(str(other.url), oled)])
    assert line_cart_url(other, 1) == "https://woo.example/product/oled/?add-to-cart=556&quantity=1"
    assert len(calls) == 1  # one decision for the store, not one per product


def test_a_no_link_answer_needs_two_votes_and_is_cached():
    cache = DictCache()
    carts, calls = engine({"mode": "none", "reason": "Synthetic: needs a session."}, cache)
    for n in (1, 2):
        item = offer(f"https://shop.example/products/{n}")
        carts.label_offers([item], [page(str(item.url), shop_form(n))])
        assert item.cart_recipe is None
    assert len(calls) == 2


def test_a_garbled_answer_is_asked_again():
    answers = iter(
        [
            {**PERMALINK, "path": "/cart/add?id=<id>&quantity=<qty>/cart/add"},
            PERMALINK,
        ]
    )
    calls = []

    def handle(request):
        calls.append(1)
        text = json.dumps(next(answers))
        return httpx.Response(
            200,
            json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]},
        )

    settings = Settings(_env_file=None, demo_mode=False, gemini_api_key="test-secret")
    carts = CartEngine(settings, transport=httpx.MockTransport(handle))
    item = offer("https://shop.example/products/esp32")
    carts.label_offers([item], [page(str(item.url), shop_form(111))])
    assert len(calls) == 2 and item.cart_id == "111"


def recipe(multi=True):  # what the engine builds from PERMALINK
    return CartRecipe(
        single_url="https://shop.example/cart/add?id={id}&quantity={qty}",
        multi_url="https://shop.example/cart/{items}?storefront=true" if multi else None,
        multi_item="{id}:{qty}" if multi else None,
        multi_join="," if multi else None,
        replaces_cart=multi,
    )


def carted(url, cart_id, multi=True):
    item = offer(url)
    item.cart_id, item.cart_recipe = cart_id, recipe(multi)
    return item


def test_links_are_filled_from_the_recipe():
    one = carted("https://shop.example/products/a", "111")
    assert line_cart_url(one, 2) == "https://shop.example/cart/add?id=111&quantity=2"
    assert line_cart_url(offer("https://shop.example/products/b"), 1) is None
    url, ids, replaces = seller_cart(
        [
            ("L01", one, 2),
            ("L02", carted("https://shop.example/products/b", "222"), 1),
            ("L03", offer("https://shop.example/products/c"), 1),
        ]
    )
    assert url == "https://shop.example/cart/111:2,222:1?storefront=true"
    assert ids == ["L01", "L02"] and replaces
    single = carted("https://shop.example/products/a", "111", multi=False)
    assert seller_cart([("L01", single, 1)]) == (None, [], False)


def test_order_plan_leaves_lines_waiting_for_confirmation_out_of_the_cart():
    chosen = carted("https://shop.example/products/esp32", "111")
    waiting = carted("https://shop.example/products/wires", "222")
    lines = [
        ReportLine(
            item=BomItem(line_id="L01", raw_name="ESP32 board", qty=1),
            sourcing_status="offers_found",
            offers=[chosen],
            selected_offer_url=chosen.url,
            price_inr=chosen.price_inr,
        ),
        # Recommended but not selected: the user still has to confirm this seller.
        ReportLine(
            item=BomItem(line_id="L02", raw_name="Jumper wires", qty=1),
            sourcing_status="offers_found",
            offers=[waiting],
            recommended_offer_url=waiting.url,
            recommendation=LineRecommendation(
                status="recommended", offer_url=waiting.url, blocked_reason="Needs a value"
            ),
        ),
    ]
    seller = build_order_plan(Report(demo=False, summary="Synthetic", lines=lines)).sellers[0]
    assert [entry.line_id for entry in seller.lines] == ["L01", "L02"]
    assert seller.cart_line_ids == ["L01"] and seller.cart_replaces
    assert str(seller.cart_url) == "https://shop.example/cart/111:1?storefront=true"
    assert str(seller.lines[1].cart_url) == "https://shop.example/cart/add?id=222&quantity=1"


def test_a_slow_decision_does_not_hold_sourcing_and_is_cached_for_later():
    import time

    cache = DictCache()

    def handle(request):
        time.sleep(0.4)
        text = json.dumps(PERMALINK)
        return httpx.Response(
            200,
            json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]},
        )

    settings = Settings(_env_file=None, demo_mode=False, gemini_api_key="test-secret")
    carts = CartEngine(
        settings, transport=httpx.MockTransport(handle), cache=cache, deadline_s=0.05
    )
    item = offer("https://shop.example/products/esp32")
    started = time.monotonic()
    carts.label_offers([item], [page(str(item.url), shop_form(111))])
    assert time.monotonic() - started < 0.3 and item.cart_recipe is None
    carts._executor.shutdown(wait=True)
    assert len(cache) == 1  # the next listing from this store gets its link from the cache
