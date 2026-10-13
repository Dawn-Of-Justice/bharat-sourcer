"""Add-to-cart links on the order plan, built only from ids the store published.

Every offer here is SYNTHETIC test data (example shops, made-up ids); no network call runs.
"""

from bharat_sourcer.carts import line_cart_url, seller_cart
from bharat_sourcer.recommend import build_order_plan
from bharat_sourcer.schemas import BomItem, LineRecommendation, Report, ReportLine, VerifiedOffer


def offer(url, verification="shopify_storefront_json", cart_id=None, price="100.00"):
    return VerifiedOffer(
        url=url,
        seller=url.split("/")[2],
        title="Synthetic listing",
        price_inr=price,
        stock="in_stock",
        verification=verification,
        cart_id=cart_id,
    )


def test_shopify_and_woocommerce_lines_get_cart_links():
    shop = offer("https://shop.example/products/esp32", cart_id="111")
    assert line_cart_url(shop, 2) == "https://shop.example/cart/111:2?storefront=true"
    variant = offer("https://shop.example/products/oled?variant=222")
    assert line_cart_url(variant, 1) == "https://shop.example/cart/222:1?storefront=true"
    woo = offer("https://woo.example/product/tp4056/", "woocommerce_store_api", "333")
    assert line_cart_url(woo, 3) == "https://woo.example/?add-to-cart=333&quantity=3"
    # No published id, or a platform without add-to-cart links: nothing.
    assert line_cart_url(offer("https://shop.example/products/x"), 1) is None
    assert (
        line_cart_url(offer("https://other.example/p/1", "seller_structured_data", "9"), 1) is None
    )


def test_one_shopify_permalink_adds_the_whole_seller_order():
    url, ids = seller_cart(
        [
            ("L01", offer("https://shop.example/products/a", cart_id="111"), 2),
            ("L02", offer("https://shop.example/products/b?variant=222"), 1),
            ("L03", offer("https://shop.example/products/c"), 1),
        ]
    )
    assert url == "https://shop.example/cart/111:2,222:1?storefront=true"
    assert ids == ["L01", "L02"]
    woo = offer("https://woo.example/product/a/", "woocommerce_store_api", "5")
    assert seller_cart([("L01", woo, 1)]) == (None, [])


def test_order_plan_carries_the_links():
    lines = []
    for i, (name, item_offer) in enumerate(
        [
            ("ESP32 board", offer("https://shop.example/products/esp32", cart_id="111")),
            ("OLED display", offer("https://shop.example/products/oled", cart_id="222")),
        ],
        1,
    ):
        item = BomItem(line_id=f"L0{i}", raw_name=name, qty=i)
        lines.append(
            ReportLine(
                item=item,
                sourcing_status="offers_found",
                offers=[item_offer],
                selected_offer_url=item_offer.url,
                price_inr=item_offer.price_inr,
            )
        )
    plan = build_order_plan(Report(demo=False, summary="Synthetic", lines=lines))
    seller = plan.sellers[0]
    assert str(seller.cart_url) == "https://shop.example/cart/111:1,222:2?storefront=true"
    assert seller.cart_line_ids == ["L01", "L02"]
    assert str(seller.lines[1].cart_url) == "https://shop.example/cart/222:2?storefront=true"


def test_lines_waiting_for_confirmation_stay_out_of_the_seller_cart():
    chosen = offer("https://shop.example/products/esp32", cart_id="111")
    waiting = offer("https://shop.example/products/wires", cart_id="222")
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
    assert seller.cart_line_ids == ["L01"]
    assert str(seller.cart_url) == "https://shop.example/cart/111:1?storefront=true"
