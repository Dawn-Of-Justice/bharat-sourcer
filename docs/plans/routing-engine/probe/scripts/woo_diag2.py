import pathlib
import json, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[5] / "backend" / "src"))
from bharat_sourcer.sourcing.fetch import SafeFetcher
f = SafeFetcher()
out = []
tests = [
 ("zbotic.in", "search=lm2596"), ("zbotic.in", "search=sg90+servo"), ("zbotic.in", "search=servo%20sg90"),
 ("zbotic.in", "search=sg90%20servo%20motor"), ("zbotic.in", "search=servo%20motor"),
 ("zbotic.in", "search=arduino%20uno%20r3&orderby=relevance"),
 ("compoindia.com", "search=sg90"), ("compoindia.com", "search=tp4056"),
 ("sharvielectronics.com", "search=sg90"), ("www.rytronics.in", "search=sg90"),
 ("www.rytronics.in", "search=tp4056"), ("sharvielectronics.com", "search=100uf"),
]
for host, q in tests:
    url = f"https://{host}/wp-json/wc/store/v1/products?{q}&per_page=10"
    t = time.monotonic()
    try:
        p = f.get(url, max_bytes=1_000_000)
        body = p.body.decode("utf-8", "replace")
        try:
            data = json.loads(body); names = [d.get("name") for d in data] if isinstance(data, list) else data
        except ValueError:
            names = body[:300]
        out.append({"url": url, "status": p.status, "ctype": p.headers.get("content-type"),
                    "total": p.headers.get("x-wp-total"), "names": names, "s": round(time.monotonic()-t, 2)})
    except Exception as e:
        out.append({"url": url, "error": repr(e)})
    print(json.dumps(out[-1], ensure_ascii=True)[:400], flush=True)
open("woo_diag2.json", "w", encoding="utf-8").write(json.dumps(out, indent=1, ensure_ascii=False))
