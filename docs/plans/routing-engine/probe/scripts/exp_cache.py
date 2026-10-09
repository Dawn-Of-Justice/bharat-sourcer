"""Offline: shared-cache key collisions, HTML-200 poisoning, junk-query scoring, verify-path exceptions."""
import json
import random
import traceback

from bharat_sourcer.sourcing.cache import MemoryCache, normalise_part
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.politeness import Politeness
from bharat_sourcer.sourcing.seller_search import SellerSearch, overlap

# 1. Two different seller queries share one shared-cache key.
for a, b in [("10kohm resistor 1/4 w 5", "10k resistor 1/4 w 5"),
             ("10 x 220ohm resistors", "10 x 220 ohm resistors"),
             ("22 uf 16 v capacitor", "22uf 16v capacitor")]:
    print("same key:", normalise_part(a) == normalise_part(b), "|", a, "|", b, "->", normalise_part(a))

calls = []


class Fake:
    def get(self, url, **kw):
        calls.append(url)
        if "search/suggest.json" in url:
            # A store answering 200 with an HTML page (maintenance/password/soft block).
            return Page(url, 200, {"content-type": "text/html"}, b"<html>Store closed</html>")
        raise AssertionError(url)


registry = [{"domain": "shop.example", "enabled": True,
             "search": {"adapter": "shopify_suggest"}}]
cache = MemoryCache()
s = SellerSearch(Politeness(cache=cache, min_interval_s=0, sleep=lambda _: None), Fake(), registry)
r1 = s.search(["10kohm resistor 1/4 w 5", "10k resistor 1/4 w 5"])
print("run1 network calls:", len(calls), [d.status + ':' + str(d.detail) for d in r1.diagnostics])
# New service instance (new process / other job), same shared cache: no network, still error.
calls.clear()
s2 = SellerSearch(Politeness(cache=cache, min_interval_s=0, sleep=lambda _: None), Fake(), registry)
r2 = s2.search(["10k resistor 1/4 w 5"])
print("run2 network calls:", len(calls), [d.status + ':' + str(d.detail) for d in r2.diagnostics])

# 2. One-word junk queries score 1.0 and stop the per-seller query loop.
print("overlap('red', 'Red Jumper Wire 20cm') =", overlap("red", "Red Jumper Wire 20cm"))
print("overlap('compatible', 'Compatible charger for laptop') =",
      overlap("compatible", "Compatible charger for laptop"))
print("overlap('104', '104 Pcs Mixed Screws') =", overlap("104", "104 Pcs Mixed Screws"))

# 3. Fuzz the verify path with odd JSON-LD for exceptions the service does not catch.
from bharat_sourcer.sourcing.listings import meta_offer, page_images, verify_page, variant_url
from bharat_sourcer.sourcing.matching import build_candidate

weird_values = [None, 1, 1.5, "x", [], {}, [1], [{}], {"a": 1}, True, "10", "INR",
                {"@type": "Offer", "price": "10.00", "priceCurrency": "INR"},
                [{"@type": "Offer", "price": "10.00", "priceCurrency": "INR", "url": 5}],
                {"@type": "Offer", "price": "10.00", "priceCurrency": "INR", "availability": 5,
                 "itemOffered": {"name": 7}}]
keys = ["name", "offers", "image", "description", "additionalProperty", "sku", "brand", "url"]
random.seed(7)
uncaught = {}
for i in range(4000):
    product = {"@type": "Product", "name": "Test 10k resistor",
               "offers": {"@type": "Offer", "price": "10.00", "priceCurrency": "INR"}}
    for k in random.sample(keys, random.randint(1, 4)):
        product[k] = random.choice(weird_values)
    body = ("<html><head><title>t</title><script type=\"application/ld+json\">"
            + json.dumps(product) + "</script></head><body>Test 10k resistor</body></html>").encode()
    page = Page("https://shop.example/products/x", 200, {"content-type": "text/html"}, body)
    for name, fn in [("verify_page", lambda: verify_page(page, None)),
                     ("build_candidate", lambda: build_candidate(page, verify_page(page, None))),
                     ("meta_offer", lambda: meta_offer(page, None)),
                     ("page_images", lambda: page_images(page, "10k resistor")),
                     ("variant_url", lambda: variant_url(page, "10k resistor"))]:
        try:
            fn()
        except (ValueError, RecursionError):
            pass  # caught by service._verify_urls
        except Exception as exc:  # would escape _source_attempt -> SOURCING_FAILED
            sig = (name, type(exc).__name__, str(exc)[:80])
            if sig not in uncaught:
                uncaught[sig] = json.dumps(product)[:200]
for sig, example in uncaught.items():
    print("UNCAUGHT", sig, "\n    e.g.", example)
print("distinct uncaught:", len(uncaught))
