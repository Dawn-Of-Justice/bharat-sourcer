"""Cart engine: can a shopper's browser add this store's products to its cart from a link?

No per-platform rules. For each store the engine:

1. Reads the add-to-cart forms and buttons from a product page it already fetched (free).
   A page without one gets no link and no model call.
2. Asks Gemini (site `cart_recipe`) to decide from those snippets whether opening a URL
   adds a product with a quantity, described in parts: path, id and quantity parameter
   names, fixed parameters, an optional several-items path, and which form field holds
   the product id. Code builds the URL from the parts, always on the store's own host.
3. Checks every part (plain path, plain names) and that the id field yields one
   unambiguous id on this page; a failed answer is asked again, up to three times.
4. Caches the recipe per store and form shape: in memory and in the shared cache for 30
   days ("no link" for 7), so each store costs one call across all jobs.

Every listing then reads its own product id from its page's form, for free. A recipe is a
judgement, not a verified checkout: the order plan says links may still fail at the store.
"""

import contextvars
import json
import logging
import re
import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import quote, urlsplit

import httpx
from pydantic import Field, field_validator

from bharat_sourcer.config import Settings, site_generation, site_model
from bharat_sourcer.extraction import generation_schema
from bharat_sourcer.gemini_api import post_generate
from bharat_sourcer.schemas import CartRecipe, Model, VerifiedOffer
from bharat_sourcer.sourcing.cache import TTL, SharedCache, cache_key, stable_hash
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.platforms import detect_platform
from bharat_sourcer.sourcing.sellers import canonical_url, registrable_domain
from bharat_sourcer.usage import paid_allowed, record_usage

log = logging.getLogger(__name__)

SITE = "cart_recipe"
CARTISH = re.compile(r"cart|basket|bag|buy|add[-_ ]?to|checkout", re.I)
PATH = re.compile(r"^/[\w\-./]{0,80}$")
NAME = re.compile(r"^[\w\-\[\]]{1,40}$")
# A draft whose add link is the product's own page (the form posts back to it) is stored
# with this path, so one store recipe serves every product of that store.
OWN_PAGE = "{page}"
FIXED = re.compile(r"^[\w\-.]{0,40}$")
ATTEMPTS = 3
ID_VALUE = re.compile(r"^[\w-]{1,40}$")
MAX_FORMS = 4
MAX_FIELDS = 20
MAX_ELEMENTS = 6
NO_LINK_TTL = 7 * 24 * 3600

PROMPT = """You decide whether a shopper's web browser can add a product to an online
store's cart just by opening a URL (an HTTP GET link), with a chosen quantity.

You get the product page URL, a platform guess and the page's add-to-cart forms and
buttons (action, method, field names and values). Use what you know about the store's
platform and what the form shows.

Answer "single" when one GET link adds one product with a quantity; "multi" when, in
addition, the platform documents one link that adds several products as path segments
(like /prefix/ID:QTY,ID:QTY). Answer "none" when adding needs a POST with a session or
anti-forgery token that the store checks (a plugin's unrelated field does not count), a
JavaScript-only API, a login, or when you are not confident.

Describe the link in parts; code builds it. path is the URL path only (no query, no host),
id_param and qty_param are the query parameter names for the product id and quantity, and
fixed_params are any other query parameters with fixed values. For "multi", multi_path is
the path prefix the items follow, pair_sep sits between an id and its quantity and
item_sep between items. id_field names the form field (input or button name) or element
attribute (for example data-product_id) whose value on this page is the product id.
replaces_cart is true when opening the link starts a new cart instead of adding to the
current one, as cart permalinks usually do. Use "" for parts that do not apply."""


class FixedParam(Model):
    name: str = ""
    value: str = ""


class CartDraft(Model):
    # Field order is answer order: the reason first, then the decision it supports. The
    # model gives short parts and code builds the URL: free-text URL templates came back
    # garbled (second URLs glued on, other fields written inside the string).
    reason: str = Field(default="", description="One short sentence.")
    mode: Literal["multi", "single", "none"]
    path: str = Field(default="", description="URL path of the add link, e.g. /cart/add.")
    id_param: str = Field(default="", description="Query parameter name for the product id.")
    qty_param: str = Field(default="", description="Query parameter name for the quantity.")
    fixed_params: list[FixedParam] = Field(default_factory=list)
    multi_path: str = Field(default="", description='Path prefix before the items, or "".')
    pair_sep: Literal[":", "", "-", "|"] = ""
    item_sep: Literal[",", "", ";", "+"] = ""
    id_field: str = Field(default="", description="Form field or attribute holding the id.")
    replaces_cart: bool = False

    # Schema limits are not sent to the model (generation_schema), so cut long text here.
    @field_validator(
        "reason", "path", "id_param", "qty_param", "multi_path", "id_field", mode="before"
    )
    @classmethod
    def short_text(cls, value):
        return "" if value is None else value[:300] if isinstance(value, str) else value

    @field_validator("fixed_params", mode="before")
    @classmethod
    def few_params(cls, value):
        return value[:3] if isinstance(value, list) else value


class _Forms(HTMLParser):
    """Add-to-cart forms (action, method, fields) and cart buttons outside forms."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms: list[dict] = []
        self.elements: list[dict] = []
        self._form: dict | None = None
        self._button: dict | None = None

    def handle_starttag(self, tag, attrs):
        attr = {k: (v or "")[:120] for k, v in attrs if k}
        if tag == "form":
            self._form = {
                "action": attr.get("action", ""),
                "method": attr.get("method", "get").lower(),
                "fields": [],
            }
        elif tag in {"input", "select", "button"} and self._form is not None:
            if attr.get("name") and len(self._form["fields"]) < MAX_FIELDS:
                field = {
                    "tag": tag,
                    "name": attr["name"],
                    "type": attr.get("type", ""),
                    "value": attr.get("value", "")[:60],
                }
                self._form["fields"].append(field)
                if tag == "button":
                    self._button = field
        elif self._form is None and len(self.elements) < MAX_ELEMENTS:
            data = {
                k: v for k, v in attr.items() if k.startswith("data-") or k in {"name", "value"}
            }
            marker = " ".join([attr.get("class", ""), attr.get("id", ""), *data])
            if data and CARTISH.search(marker):
                self.elements.append({"tag": tag, "class": attr.get("class", "")[:80], **data})

    def handle_data(self, data):
        if self._button is not None and data.strip():
            self._button["text"] = data.strip()[:40]

    def handle_endtag(self, tag):
        if tag == "button":
            self._button = None
        if tag == "form" and self._form is not None:
            form, self._form = self._form, None
            text = " ".join(
                [form["action"], *(f"{f['name']} {f.get('text', '')}" for f in form["fields"])]
            )
            if CARTISH.search(text) and len(self.forms) < MAX_FORMS:
                self.forms.append(form)


def cart_forms(page: Page) -> tuple[list[dict], list[dict]]:
    if page.status != 200 or "html" not in page.headers.get("content-type", "text/html"):
        return [], []
    parser = _Forms()
    try:
        parser.feed(page.body[:1_500_000].decode("utf-8", errors="replace"))
    except Exception:
        return [], []
    return parser.forms, parser.elements


def form_target(action: str, page_url: str) -> str:
    """The form's target path, with the product's own page and numbers made generic."""
    path = urlsplit(action).path.rstrip("/")
    if not action or path == urlsplit(page_url).path.rstrip("/"):
        return OWN_PAGE
    return re.sub(r"\d+", "#", path)


def shape(page_url: str, forms: list[dict], elements: list[dict]) -> str:
    """Form structure without values or product slugs: the same for a store's products."""
    return stable_hash(
        {
            "forms": [
                [
                    form_target(form["action"], page_url),
                    form["method"],
                    sorted(f["name"] for f in form["fields"]),
                ]
                for form in forms
            ],
            "elements": sorted(sorted(k for k in el if k.startswith("data-")) for el in elements),
        }
    )


def product_id(forms: list[dict], elements: list[dict], id_field: str) -> str | None:
    for form in forms:
        for field in form["fields"]:
            if field["name"] == id_field and ID_VALUE.match(field["value"]):
                return field["value"]
    # Buttons outside forms are often related products: use them only when they agree.
    values = {
        value
        for element in elements
        if isinstance(value := element.get(id_field), str) and ID_VALUE.match(value)
    }
    return values.pop() if len(values) == 1 else None


def checked(draft: CartDraft, host: str, model: str) -> tuple[CartRecipe, str] | None:
    """Build the recipe from the draft's parts when every part passes, else None."""
    # The form submits the id under id_param, so that field holds it when none is named.
    id_field = draft.id_field or draft.id_param
    if draft.mode == "none" or not NAME.match(id_field):
        return None
    own_page = draft.path == OWN_PAGE
    if not own_page and (not PATH.match(draft.path) or "//" in draft.path):
        return None
    names = [draft.id_param, draft.qty_param, *(p.name for p in draft.fixed_params)]
    if not all(NAME.match(name) for name in names) or len(set(names)) != len(names):
        return None
    if not all(FIXED.match(p.value) for p in draft.fixed_params):
        return None
    query = "&".join(
        [
            *(f"{quote(p.name)}={quote(p.value)}" for p in draft.fixed_params),
            f"{quote(draft.id_param)}={{id}}",
            f"{quote(draft.qty_param)}={{qty}}",
        ]
    )
    multi = None
    if (
        draft.mode == "multi"
        and PATH.match(draft.multi_path)
        and "//" not in draft.multi_path
        and draft.pair_sep
        and draft.item_sep
    ):
        multi = f"https://{host}{draft.multi_path.rstrip('/')}/{{items}}"
    return (
        CartRecipe(
            single_url=("{page}" if own_page else f"https://{host}{draft.path}") + f"?{query}",
            multi_url=multi,
            multi_item=f"{{id}}{draft.pair_sep}{{qty}}" if multi else None,
            multi_join=draft.item_sep if multi else None,
            replaces_cart=draft.replaces_cart,
            model=model,
        ),
        id_field,
    )


class CartEngine:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        cache: SharedCache | None = None,
        deadline_s: float = 8,
    ):
        self.settings, self.transport, self.cache = settings, transport, cache
        # Sourcing waits at most this long; a slower decision finishes in the background
        # and is cached, so the store's next listings get links.
        self.deadline_s = deadline_s
        self._memory: dict[str, dict] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="carts")

    def label_offers(self, offers: list[VerifiedOffer], pages: list[Page]) -> None:
        """Set `cart_recipe` and `cart_id` on offers whose store supports add-to-cart links."""
        by_url = {canonical_url(page.url): page for page in pages}
        pending: list[tuple[VerifiedOffer, list, list, Future]] = []
        for offer in offers:
            page = by_url.get(canonical_url(str(offer.url)))
            host = urlsplit(str(offer.url)).hostname
            if page is None or not host:
                continue
            forms, elements = cart_forms(page)
            if not (forms or elements):
                continue
            # Copy the context so model calls count against this job's budget and ledger.
            context = contextvars.copy_context()
            future = self._executor.submit(context.run, self.recipe, page, host, forms, elements)
            pending.append((offer, forms, elements, future))
        wait([future for *_, future in pending], timeout=self.deadline_s)
        for offer, forms, elements, future in pending:
            # Only finished decisions label offers: a late one must not change a saved offer.
            if not future.done() or future.exception() is not None:
                if future.done():
                    log.warning("CART_ENGINE_FAILED", exc_info=future.exception())
                continue
            found = future.result()
            if found is None:
                continue
            recipe, id_field = found
            cart_id = product_id(forms, elements, id_field)
            if cart_id:
                offer.cart_id, offer.cart_recipe = cart_id, recipe

    def recipe(self, page, host, forms, elements) -> tuple[CartRecipe, str] | None:
        key = cache_key(SITE, registrable_domain(host), shape(page.url, forms, elements))
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        # Parallel lines from one store wait for the first call instead of repeating it.
        with lock:
            entry = self._memory.get(key)
            if entry is None and self.cache is not None:
                entry = self.cache.get(key)
            if entry is None:
                entry = self._decide(page, host, forms, elements)
                if entry is None:
                    return None  # not decided (budget, failure): try again later
                if self.cache is not None:
                    # A "no link" answer is retried sooner: one wrong answer must not stick.
                    self.cache.set(key, entry, TTL[SITE] if entry.get("draft") else NO_LINK_TTL)
            self._memory[key] = entry
        if not entry.get("draft"):
            return None
        try:
            draft = CartDraft.model_validate(entry["draft"])
        except ValueError:
            return None
        return checked(draft, host, entry.get("model") or "")

    def _decide(self, page: Page, host: str, forms, elements) -> dict | None:
        """Ask up to ATTEMPTS times; keep the first answer that passes every check.

        One cached answer serves the store for weeks, so "no link" stands only when two
        answers say so; answers that fail the checks count as neither.
        """
        body = {
            "page_url": page.url,
            "platform_guess": detect_platform(page),
            "forms": forms,
            "buttons_outside_forms": elements,
        }
        model = site_model(self.settings, SITE)
        nones = 0
        for _ in range(ATTEMPTS):
            if not paid_allowed():
                log.warning("CART_ENGINE_SKIPPED budget reached")
                return None
            draft = self._call(body)
            if draft is None:
                continue
            if draft.path.rstrip("/") == urlsplit(page.url).path.rstrip("/"):
                draft = draft.model_copy(update={"path": OWN_PAGE})
            if draft.mode == "none":
                nones += 1
                if nones == 2:
                    break
                continue
            found = checked(draft, host, model)
            if found and product_id(forms, elements, found[1]):
                log.info("CART_RECIPE host=%s mode=%s", host, draft.mode)
                return {"draft": draft.model_dump(mode="json"), "model": model}
            log.info("CART_RECIPE_REJECTED host=%s", host)
        if nones == 0:
            return None  # nothing usable and no clear "no": decide again next time
        log.info("CART_RECIPE host=%s mode=none", host)
        return {"draft": None, "model": model}

    def _call(self, body: dict) -> CartDraft | None:
        key = self.settings.gemini_api_key
        if key is None or not key.get_secret_value().strip():
            return None
        model = site_model(self.settings, SITE)
        payload = {
            "systemInstruction": {"parts": [{"text": PROMPT}]},
            "contents": [
                {"role": "user", "parts": [{"text": json.dumps(body, ensure_ascii=False)}]}
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": generation_schema(CartDraft),
                "maxOutputTokens": 4096,
                **site_generation(self.settings, SITE),
            },
        }
        try:
            with httpx.Client(timeout=20, transport=self.transport) as client:
                response = post_generate(client, self.settings, SITE, model, payload)
            response.raise_for_status()
            data = response.json()
            record_usage(SITE, model, data)
            candidate = data["candidates"][0]
            if candidate.get("finishReason") != "STOP":
                raise ValueError(f"Incomplete cart recipe output: {candidate.get('finishReason')}")
            return CartDraft.model_validate_json(
                "".join(
                    p.get("text", "")
                    for p in candidate["content"]["parts"]
                    if not p.get("thought", False)
                )
            )
        except Exception:
            log.warning("CART_RECIPE_FAILED", exc_info=True)
            return None


def render(recipe: CartRecipe, cart_id: str, qty: int, page_url: str) -> str:
    """The add link for one listing; `page_url` fills {page} for own-page recipes."""
    page = urlsplit(page_url)
    url = recipe.single_url.replace("{page}", f"https://{page.hostname}{page.path}")
    return url.replace("{id}", quote(cart_id, safe="")).replace("{qty}", str(qty))


def render_many(recipe: CartRecipe, items: list[tuple[str, int]]) -> str | None:
    if not (recipe.multi_url and recipe.multi_item and recipe.multi_join):
        return None
    rendered = recipe.multi_join.join(
        recipe.multi_item.replace("{id}", quote(cart_id, safe="")).replace("{qty}", str(qty))
        for cart_id, qty in items
    )
    return recipe.multi_url.replace("{items}", rendered)
