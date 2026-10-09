import json
from urllib.parse import unquote
from bharat_sourcer.sourcing.cache import MemoryCache
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.politeness import Politeness
from bharat_sourcer.sourcing.seller_search import SellerSearch
sent = []
class Fake:
    def get(self, url, **kw):
        q = unquote(url.split("q=")[1].split("&")[0]); sent.append(q)
        body = {"resources": {"results": {"products": [{"handle": "led-holder", "title": "LED holder"}]}}}
        return Page(url, 200, {"content-type": "application/json"}, json.dumps(body).encode())
reg = [{"domain": "shop.example", "enabled": True, "search": {"adapter": "shopify_suggest"}}]
for cache in (None, MemoryCache()):
    sent.clear()
    s = SellerSearch(Politeness(cache=cache, min_interval_s=0, sleep=lambda _: None), Fake(), reg)
    r = s.search(["10kohm resistor 1/4 w 5", "10k resistor 1/4 w 5", "10k resistor"])
    print("cache" if cache else "no cache", "-> queries actually sent:", sent, "diag queries:", r.diagnostics[0].queries)
