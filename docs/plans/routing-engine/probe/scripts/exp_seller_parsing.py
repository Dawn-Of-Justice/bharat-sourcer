"""Offline experiments against pure seller-page parsing functions (no network)."""

import json

from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.listings import (
    extract_product,
    meta_offer,
    offer_options,
    sane_price,
    stock_of,
    verify_page,
)
from bharat_sourcer.sourcing.platforms import detect_platform, storefront_offer
from bharat_sourcer.sourcing.politeness import challenge_reason
from bharat_sourcer.sourcing.tax import detect_tax_included
from bharat_sourcer.sourcing.trust import KNOWN_SELLERS, registrable_domain
from bharat_sourcer.costing import seller_key

HTML = {"content-type": "text/html; charset=utf-8"}
URL = "https://shop.example.in/product/oled-096/"


def ld(obj, typ="application/ld+json"):
    return f'<script type="{typ}">{json.dumps(obj) if not isinstance(obj, str) else obj}</script>'


def page(body, url=URL, status=200, headers=HTML):
    return Page(url, status, dict(headers), f"<html><head><title>T</title>{body}</head></html>".encode())


def offer(**kw):
    base = {"@type": "Offer", "price": "299.00", "priceCurrency": "INR",
            "availability": "https://schema.org/InStock"}
    base.update(kw)
    return base


def product(offers, **kw):
    p = {"@context": "https://schema.org", "@type": "Product", "name": "0.96 inch OLED", "offers": offers}
    p.update(kw)
    return p


def show(label, value):
    if value is not None and hasattr(value, "price_inr"):
        value = f"OFFER price={value.price_inr} stock={value.stock} seller={value.seller} url={value.url}"
    print(f"{label:<62} -> {value}")


print("== JSON-LD shapes ==")
show("baseline single Offer", verify_page(page(ld(product(offer())))))
show("@graph with Product", verify_page(page(ld({"@context": "https://schema.org", "@graph": [{"@type": "WebPage"}, product(offer())]}))))
show("Product nested in WebPage.mainEntity", verify_page(page(ld({"@type": "ItemPage", "mainEntity": product(offer())}))))
pg = {"@type": "ProductGroup", "name": "0.96 inch OLED", "hasVariant": [product(offer(price="299.00")), product(offer(price="349.00"))]}
show("ProductGroup + hasVariant", extract_product(page(ld(pg))))
show("@type IndividualProduct", verify_page(page(ld({**product(offer()), "@type": "IndividualProduct"}))))
show("script type 'application/ld+json; charset=utf-8'", verify_page(page(ld(product(offer()), "application/ld+json; charset=utf-8"))))
show("JSON-LD wrapped in //<![CDATA[ ]]>", verify_page(page(ld("//<![CDATA[\n" + json.dumps(product(offer())) + "\n//]]>"))))
show("JSON-LD with trailing comma", verify_page(page(ld(json.dumps(product(offer()))[:-1] + ",}"))))
show("duplicate Product (theme + SEO plugin)", verify_page(page(ld(product(offer())) + ld(product(offer())))))
show("Product + related Product in @graph", verify_page(page(ld({"@graph": [product(offer()), {**product(offer(price="99.00")), "name": "Other"}]}))))
show("AggregateOffer low==high", verify_page(page(ld(product({"@type": "AggregateOffer", "lowPrice": "299", "highPrice": "299", "priceCurrency": "INR", "availability": "InStock"})))))
show("AggregateOffer low!=high (no nested offers)", offer_options({"@type": "AggregateOffer", "lowPrice": "299", "highPrice": "349", "priceCurrency": "INR"}))
show("valid Offer + one unresolvable AggregateOffer", offer_options([offer(), {"@type": "AggregateOffer", "lowPrice": "1", "highPrice": "2", "priceCurrency": "INR"}]))
show("price only in priceSpecification (UnitPriceSpecification)", verify_page(page(ld(product({"@type": "Offer", "priceSpecification": {"@type": "UnitPriceSpecification", "price": "299.00", "priceCurrency": "INR"}, "availability": "InStock"})))))
show("priceCurrency missing", verify_page(page(ld(product(offer(priceCurrency=None))))))
show("priceCurrency lowercase 'inr'", verify_page(page(ld(product(offer(priceCurrency="inr"))))))
show("priceCurrency on Product, not Offer", verify_page(page(ld(product(offer(priceCurrency=None), priceCurrency="INR")))))
show("Offer @type missing", verify_page(page(ld(product({k: v for k, v in offer().items() if k != "@type"})))))

print("\n== price strings ==")
for raw in ["299", 299, 299.5, "1299.00", "1,299.00", "₹1,299.00", "Rs. 1,299", "1,23,456.00", " 299.00 ", "299.000", "299.99000001", "₹ 299"]:
    show(f"sane_price({raw!r})", sane_price(raw))

print("\n== availability ==")
for raw in ["https://schema.org/InStock", "http://schema.org/InStock", "InStock", "schema:InStock", "https://schema.org/LimitedAvailability",
            "https://schema.org/BackOrder", "https://schema.org/OnlineOnly", "https://schema.org/PreOrder", "https://schema.org/SoldOut",
            "https://schema.org/Discontinued", "In stock", "instock ", None, "https://schema.org/InStock/"]:
    show(f"stock_of({raw!r})", stock_of(raw))

print("\n== URL identity (single Offer, offer.url vs fetched page.url) ==")
show("offer.url == page", verify_page(page(ld(product(offer(url=URL))))))
show("page has ?srsltid= (Google) tracking", verify_page(page(ld(product(offer(url=URL))), url=URL + "?srsltid=AfmBOoq")))
show("page has ?utm_source=", verify_page(page(ld(product(offer(url=URL))), url=URL + "?utm_source=google")))
show("offer.url is www.<host>", verify_page(page(ld(product(offer(url=URL.replace("shop.", "www.shop.")))))))
show("offer.url is http://", verify_page(page(ld(product(offer(url=URL.replace("https", "http")))))))
show("offer.url relative '/product/oled-096/'", verify_page(page(ld(product(offer(url="/product/oled-096/"))))))
show("offer.url points to a category page", verify_page(page(ld(product(offer(url="https://shop.example.in/category/displays/"))))))

print("\n== meta / microdata fallback ==")
og = '<meta property="og:title" content="0.96 inch OLED"><meta property="product:price:amount" content="{p}"><meta property="product:price:currency" content="INR">'
show("og price '299.00'", meta_offer(page(og.format(p="299.00"))))
show("og price '1,299.00'", meta_offer(page(og.format(p="1,299.00"))))
md = '<div itemscope itemtype="https://schema.org/Product"><h1 itemprop="name">0.96 inch OLED</h1><span itemprop="price">₹299.00</span><meta itemprop="priceCurrency" content="INR"></div>'
show("microdata price as element text (no content=)", meta_offer(page(md)))
md2 = '<meta itemprop="name" content="0.96 inch OLED"><meta itemprop="price" content="299.00"><meta itemprop="priceCurrency" content="INR"><s>MRP <meta itemprop="price" content="499.00"></s>'
show("microdata sale + MRP both itemprop=price", meta_offer(page(md2)))
show("og price on page that embeds a cdn.shopify.com image", meta_offer(page(og.format(p="299.00") + '<img src="https://cdn.shopify.com/x.png">')))
show("og price on Magento-like page (data-price-amount only)", meta_offer(page('<span data-price-amount="299" data-price-type="finalPrice">₹299.00</span><meta property="og:title" content="0.96 inch OLED">')))

print("\n== JSON-LD present but no offers on Shopify ==")
shop = ld(product([])) + '<link href="https://cdn.shopify.com/s/x.css">'
p = page(shop, url="https://store.example.in/products/oled-096")
show("verify_page", verify_page(p))
show("storefront_offer (fetcher never called)", storefront_offer(p, None, fetcher=None))
show("meta_offer", meta_offer(p))

print("\n== platform detection ==")
cases = {
    "WordPress blog mentioning 'woocommerce' + Shopify image": "<p>woocommerce tips</p><img src='https://cdn.shopify.com/a.png'>",
    "Dukaan store (mydukaan.io assets)": "<script src='https://mydukaan.io/static/app.js'></script>",
    "Instamojo store": "<script src='https://www.instamojo.com/x.js'></script>",
    "Wix": "<meta name='generator' content='Wix.com Website Builder'>",
    "PrestaShop": "<script>var prestashop = {};</script>",
    "OpenCart": "<a href='index.php?route=product/product&product_id=1'>x</a>",
    "BigCommerce": "<script src='https://cdn11.bigcommerce.com/s-abc/x.js'></script>",
    "Zoho Commerce": "<script src='https://static.zohocdn.com/commerce/x.js'></script>",
}
for name, body in cases.items():
    show(name, detect_platform(page(body)))

print("\n== host -> domain / registry lookup ==")
for host in ["www.robocraze.com", "m.robocraze.com", "robocraze.com.", "WWW.Robocraze.com", "store.myshopify.com",
             "abc.mydukaan.io", "xyz.wixsite.com", "foo.instamojo.com", "dir.indiamart.com", "www.amazon.in",
             "probots.co.in", "shop.probots.co.in", "in.element14.com", "xn--h2brj9c.in"]:
    dom = registrable_domain(host)
    known = KNOWN_SELLERS.get(dom, {})
    print(f"{host:<24} registrable={dom:<22} known={bool(known)} established={known.get('established')} costing_key={seller_key(host)}")

print("\n== challenge / soft-404 ==")
cf200 = Page(URL, 200, dict(HTML), b"<html><head><title>Just a moment...</title></head></html>")
show("Cloudflare title on 200", challenge_reason(cf200))
sucuri = Page(URL, 200, dict(HTML), b"<html><title>Sucuri WebSite Firewall - Access Denied</title></html>")
show("Sucuri firewall page on 200", challenge_reason(sucuri))
imperva = Page(URL, 200, dict(HTML), b"<html><head><meta name='robots' content='noindex'><script src='/_Incapsula_Resource?x'></script></head></html>")
show("Imperva/Incapsula on 200", challenge_reason(imperva))
soft404 = page(ld(product(offer(availability="https://schema.org/OutOfStock"), name="Product not found")) )
show("soft-404 still with JSON-LD", verify_page(soft404))

print("\n== tax phrases ==")
for text in ["₹299 (incl. GST)", "₹299 Inclusive of all taxes", "₹299 + GST", "₹299 excluding 18% GST", "₹299 including 18% GST",
             "₹299 (Without GST)", "₹299 (With GST)", "Price: ₹254 Ex. GST ₹299 Inc. GST", "MRP ₹499 inclusive of all taxes",
             "₹299 GST included", "Prices exclusive of GST. Related: ₹99 incl. GST"]:
    show(repr(text), detect_tax_included({}, f"<p>{text}</p>"))
