"""Deterministic safety flags (M13). Hard-coded rules and templated text; no model calls.

The rules read saved BOM lines (names, families, requirements, specs, evidence text) and the
AI-written project understanding. They err towards flagging: a missed mains or lithium hazard
is worse than an extra banner. Flags are advice derived from text, not verified facts.
"""

import re
from dataclasses import dataclass

from bharat_sourcer.schemas import BomItem, Job, ProjectContext, SafetyFlag, SafetyTrigger

RULE_VERSION = "safety-rules-1"
LED_FULL_WHITE_A = 0.06
HIGH_CURRENT_A = 3.0
ADDRESSABLE_MIN_A = 1.0
MAX_TRIGGERS = 20


def rx(*patterns: str) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


# Anything that is, plugs into or switches 230 V / 120 V mains.
MAINS = rx(
    r"\bmains\b",
    r"\bline[- ]voltage\b",
    r"\bpower ?switch ?tail\b",
    r"\biot ?relay\b",
    r"\bwall (?:socket|outlet)s?\b",
    r"\b(?:ac|mains) (?:power )?(?:socket|outlet|plug|cord|appliance|load|bulb|lamp|motor|fan)s?\b",
    r"\bpower (?:strip|cord)s?\b",
    r"\bextension (?:cord|board|lead|box)s?\b",
    r"\bappliances?\b",
    r"\b(?:rice|slow|pressure) cookers?\b",
    r"\bcrock ?pot\b",
    r"\bkettles?\b",
    r"\btoasters?\b",
    r"\b(?:immersion|water|room|space) heaters?\b",
    r"\bgeysers?\b",
    r"\b(?:incandescent|light) bulbs?\b",
    r"\bbulb holders?\b",
    r"\b(?:e27|b22)\b",
    r"\b(?:ceiling|table|pedestal|exhaust) fans?\b",
    r"\bhlk-?pm\d+",
    r"\bhi-?link\b",
    r"\bac[- ]?(?:to[- ])?dc (?:module|converter|board|power module)s?\b",
    r"\bsmps\b",
    r"\bswitch(?:ing|ed)[- ]mode power suppl(?:y|ies)\b",
    r"\bswitching power suppl(?:y|ies)\b",
    r"\btriacs?\b",
    r"\bbt13[69]\b",
    r"\bbta\d{2}\b",
    r"\bmoc30[2-8]\d\b",
    r"\bzero[- ]cross",
    r"\bcontactors?\b",
    r"\b(?:mcb|rccb|elcb)\b",
    r"\bnema [156]-\d+",
    r"\bsolid[- ]state relays?\b",
    r"\bssr\b",
    r"\bssr-\d+",
    r"\b(?:step[- ]down|mains|power) transformers?\b",
    r"\b(?:50|60) ?hz\b",
)
# Plug tops on a part mean mains wiring; on an adapter they are just its plug.
PLUG = rx(r"\btype [abdgm] plugs?\b", r"\b(?:us|uk|indian|3[- ]pin) plugs?\b")
# US-only mains products (worked Case 2: PowerSwitch Tail II is 120 V / 60 Hz).
US_MAINS = rx(
    r"\bpower ?switch ?tail\b",
    r"\biot ?relay\b",
    r"\bnema [156]-\d+",
    r"\btype [ab] plugs?\b",
    r"\bus (?:plug|version|model|outlet|socket|mains)s?\b",
    r"\b60 ?hz\b",
)
# Sealed plug-in supplies: the maker never touches 230 V, so only US-only ones are flagged.
ADAPTER = rx(r"\b(?:adapter|adaptor|wall[- ]wart|charger|power bank)s?\b")
RELAY = rx(r"\brelays?\b", r"\bssr\b", r"\bcontactors?\b")
# A plain relay (5 V coil) is mains only when the project text says it switches AC loads.
RELAY_AC_HINT = rx(
    r"\blights?\b",
    r"\blamps?\b",
    r"\bbulbs?\b",
    r"\bfans?\b",
    r"\bappliances?\b",
    r"\bhome automation\b",
    r"\bsmart (?:home|switch|plug|socket)\b",
    r"\bswitchboard\b",
    r"\bsockets?\b",
    r"\boutlets?\b",
    r"\bheaters?\b",
    r"\bgeysers?\b",
    r"\bcookers?\b",
    r"\b(?:tv|television|air conditioner)\b",
)

LITHIUM = rx(
    r"\bli-?po(?:ly)?\b",
    r"\blithium[- ]?(?:ion|polymer)\b",
    r"\bli-?ion\b",
    r"\blifepo4\b",
    r"\b(?:18650|21700|26650|14500|16340|18350)\b",
    r"\blir\d{4}\b",
    r"\b[1-6]s (?:lipo|li-?ion|battery|pack)\b",
    r"\b3\.7 ?v (?:battery|cell|pack)\b",
    r"\blithium (?:battery|batteries|cells?|packs?)\b",
)
BATTERY = rx(r"\bbatter(?:y|ies)\b", r"\bcells?\b", r"\bbms\b", r"\bpacks?\b")
POWER_BANK = rx(r"\bpower ?banks?\b")
PROTECTION = rx(
    r"\bprotect(?:ed|ion)\b",
    r"\bbms\b",
    r"\bpcm\b",
    r"\bwith pcb\b",
    r"\bdw01",
    r"\b8205a?\b",
    r"\bfs312f",
    r"\bbattery management\b",
)
CHARGER = rx(
    r"\btp40\d\d\b",
    r"\bmcp738\d\d",
    r"\bip5306\b",
    r"\bbq2\d{3}",
    r"\bcn3065\b",
    r"\bcharg(?:er|ing)\b",
)

ADDRESSABLE = rx(r"\b(?:ws281[123]b?|sk6812|apa102|sk9822|neo ?pixels?)\b")
MULTI_LED = rx(r"\b(?:strip|tape|ring|stick|jewel|matrix|panel|grid|string)s?\b")
LED_STRIP = rx(r"\bled (?:strip|tape|matrix|panel)s?\b", r"\b(?:strip|tape) lights?\b")
LOAD = rx(
    r"\bmotors?\b",
    r"\bnema ?(?:14|17|23)\b",
    r"\bsteppers?\b",
    r"\bservos?\b",
    r"\b(?:sg90|mg90s?|mg99[56]r?)\b",
    r"\b(?:bldc|brushless)\b",
    r"\besc\b",
    r"\bsolenoids?\b",
    r"\bpumps?\b",
    r"\bpeltier\b",
    r"\btec1-\d+",
    r"\belectromagnets?\b",
    r"\bheat(?:er|ing) (?:pad|element|bed)s?\b",
    r"\bnichrome\b",
    r"\bheaters?\b",
    r"\bhigh[- ]power leds?\b",
    r"\b\d+(?:\.\d+)? ?w (?:led|laser)s?\b",
    r"\bl29[38]n?d?\b",
    r"\btb6612",
    r"\bdrv88\d\d",
    r"\ba4988\b",
    r"\btmc2\d{3}\b",
    r"\bbts7960\b",
    r"\bibt-?2\b",
    r"\bmx1508\b",
    r"\buln2003\b",
    r"\blead[- ]acid\b",
    r"\bsla batter(?:y|ies)\b",
    r"\bcar batter(?:y|ies)\b",
)
TINY_MOTOR = rx(r"\b(?:vibration|vibrating|coin|haptic) motors?\b")

CTRL_3V3 = rx(
    r"\besp32",
    r"\besp-?8266\b",
    r"\besp-?01s?\b",
    r"\bnodemcu\b",
    r"\bwemos\b",
    r"\bd1 mini\b",
    r"\brp2040\b",
    r"\brp2350\b",
    r"\bpi pico\b",
    r"\braspberry pi\b",
    r"\bstm32",
    r"\bblue ?pill\b",
    r"\bnano 33\b",
    r"\barduino (?:due|mkr|zero|giga)\b",
    r"\bteensy ?(?:3\.[2-6]|4\.[01])\b",
    r"\bnrf52",
    r"\bxiao\b",
    r"\bfeather\b",
    r"\bmicro:?bit\b",
    r"\b3\.3 ?v (?:logic|board|mcu|microcontroller)\b",
)
CTRL_5V = rx(
    r"\barduino (?:uno|mega|nano|leonardo|micro)\b",
    r"\buno\b",
    r"\bmega ?2560\b",
    r"\batmega ?(?:328p?|2560|32u4)\b",
    r"\bnano\b",
    r"\bpro (?:mini|micro)\b",
    r"\bdigispark\b",
    r"\battiny85\b",
    r"\b5 ?v (?:logic|board|mcu|microcontroller)\b",
)
LOW_VARIANT = rx(r"\b3\.3 ?v\b", r"\b3v3\b", r"\b8 ?mhz\b")
PERIPH_5V = rx(
    r"\b(?:ws281[123]b?|sk6812|apa102|sk9822|neo ?pixels?)\b",
    r"\bhc-?sr04\b",
    r"\blcd ?(?:1602|2004)a?\b",
    r"\b(?:1602|2004)a? ?lcd\b",
    r"\b(?:16x2|20x4)\b",
    r"\bpcf8574",
    r"\bmax7219\b",
    r"\bmq-?\d{1,3}\b",
    r"\b5 ?v (?:logic|only|sensor)\b",
    r"\b5v-only\b",
)
PERIPH_3V3 = rx(
    r"\bnrf24l01",
    r"\b(?:mf)?rc522\b",
    r"\bsx127\d",
    r"\bra-0[12]\b",
    r"\blora\b",
    r"\bhc-?0[56]\b",
    r"\b3\.3 ?v[- ]?only\b",
    r"\b3v3[- ]?only\b",
    r"\b(?:bme|bmp)280[- ]3\.3\b",
)
SHIFTER = rx(
    r"\blevel[- ]?(?:shifter|converter|translator)s?\b",
    r"\blogic level converter\b",
    r"\b74ahct\d+",
    r"\btx[sb]0108",
    r"\bbss138\b",
)
# Numeric spec/requirement voltages of these parts say nothing about logic levels.
NOT_LOGIC = rx(
    ADAPTER.pattern,
    LOAD.pattern,
    LITHIUM.pattern,
    r"\b(?:regulator|buck|boost|converter|lm2596|ams1117|lm7805|smps|power supply|psu)\b",
    r"\b(?:battery|batteries|cells?)\b",
    r"\b(?:resistor|capacitor|diode|leds?|wires?|jumper|breadboard|header|switch|button)s?\b",
    r"\b(?:buzzer|piezo|potentiometer|cable|connector|screw|enclosure|pcb|fuse)s?\b",
)
VOLT_TERMS = rx(r"volt", r"\blogic\b", r"\bsupply\b", r"\boperating\b", r"\bvcc\b", r"\bvin\b")

_NUM = r"(\d{1,3}(?:\.\d+)?)"
VOLT_RANGE = re.compile(
    rf"(?<![\w.]){_NUM}\s*v?\s*(?:-|–|to|~|/)\s*{_NUM}\s*(?:v|volts?)(?:\s*(ac|dc))?(?![a-z])",
    re.IGNORECASE,
)
VOLT = re.compile(
    rf"(?<![\w.])(\d)v(\d)(?![\w])"
    rf"|(?<![\w.]){_NUM}\s*(?:v|volts?)(?:\s*(ac|dc))?(?![a-z])"
    rf"|\b(ac|dc)\s*{_NUM}\s*v\b",
    re.IGNORECASE,
)
CURRENT = re.compile(r"(?<![\w.])(\d{1,4}(?:\.\d+)?)\s*(ma|a|amps?|amperes?)(?![a-z])", re.I)
WATTS = re.compile(r"(?<![\w.])(\d{1,4}(?:\.\d+)?)\s*(?:w|watts?)(?![a-z])", re.IGNORECASE)
LED_COUNT = re.compile(r"(?<![\w.])(\d{1,4})\s*(?:leds?|pixels?)(?!\s*/)\b", re.IGNORECASE)
LED_DENSITY = re.compile(r"(?<![\w.])(\d{2,3})\s*(?:leds?|pixels?)?\s*/\s*m\b", re.IGNORECASE)
LENGTH_M = re.compile(r"(?<![\w.])(\d{1,2}(?:\.\d+)?)\s*(?:m|metres?|meters?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Text:
    line_id: str | None
    field: str
    text: str


@dataclass(frozen=True)
class Volt:
    value: float
    kind: str | None  # "ac", "dc" or None when unlabelled
    matched: str


def voltages(text: str) -> list[Volt]:
    found = []
    for match in VOLT_RANGE.finditer(text):
        kind = (match.group(3) or "").lower() or None
        found += [Volt(float(match.group(i)), kind, match.group(0)) for i in (1, 2)]
    rest = VOLT_RANGE.sub(" ", text)
    for match in VOLT.finditer(rest):
        if match.group(1):
            value, kind = float(f"{match.group(1)}.{match.group(2)}"), None
        elif match.group(3):
            value, kind = float(match.group(3)), match.group(4)
        else:
            value, kind = float(match.group(6)), match.group(5)
        found.append(Volt(value, (kind or "").lower() or None, match.group(0)))
    return found


def currents(text: str) -> list[tuple[float, str]]:
    found = []
    for match in CURRENT.finditer(text):
        value = float(match.group(1))
        found.append((value / 1000 if match.group(2).lower() == "ma" else value, match.group(0)))
    # Watts only become amps when a low (DC) voltage is stated alongside them.
    low = [v.value for v in voltages(text) if 0 < v.value <= 60 and v.kind != "ac"]
    if low:
        for match in WATTS.finditer(text):
            found.append((float(match.group(1)) / max(low), match.group(0)))
    return found


def item_texts(item: BomItem) -> list[Text]:
    texts = [Text(item.line_id, "raw_name", item.raw_name)]
    if item.specs.family:
        texts.append(Text(item.line_id, "specs.family", item.specs.family))
    for index, requirement in enumerate(item.requirements):
        value = " ".join(filter(None, (requirement.name, requirement.value, requirement.unit)))
        texts.append(Text(item.line_id, f"requirements[{index}]", value))
        if requirement.reason:
            texts.append(Text(item.line_id, f"requirements[{index}].reason", requirement.reason))
    for index, evidence in enumerate(item.evidence):
        texts.append(Text(item.line_id, f"evidence[{index}].observation", evidence.observation))
        if evidence.quote:
            texts.append(Text(item.line_id, f"evidence[{index}].quote", evidence.quote))
    return texts


def project_texts(project: ProjectContext | None) -> list[Text]:
    if project is None:
        return []
    texts = [
        Text(None, f"project.{name}", getattr(project, name))
        for name in ("title", "description", "summary", "power", "controller")
        if getattr(project, name)
    ]
    for name in ("interfaces", "assumptions"):
        texts += [
            Text(None, f"project.{name}[{i}]", value)
            for i, value in enumerate(getattr(project, name))
        ]
    return texts


def identity(item: BomItem) -> str:
    """Name-level text used to decide what a part is (not what its evidence mentions)."""
    return " ".join(filter(None, (item.raw_name, item.specs.family)))


class Collector:
    def __init__(self, items: list[BomItem]):
        self.order = {item.line_id: index for index, item in enumerate(items)}
        self.triggers: dict[str, list[SafetyTrigger]] = {}
        self.notes: dict[str, list[str]] = {}

    def add(self, code: str, text: Text, matched: str) -> None:
        trigger = SafetyTrigger(line_id=text.line_id, field=text.field, matched=matched[:200])
        bucket = self.triggers.setdefault(code, [])
        if trigger not in bucket:
            bucket.append(trigger)

    def note(self, code: str, note: str) -> None:
        bucket = self.notes.setdefault(code, [])
        if note not in bucket:
            bucket.append(note)

    def line_ids(self, code: str) -> list[str]:
        ids = {t.line_id for t in self.triggers.get(code, []) if t.line_id in self.order}
        return sorted(ids, key=self.order.__getitem__)


def search(pattern: re.Pattern, text: Text) -> str | None:
    match = pattern.search(text.text)
    return match.group(0) if match else None


def mains_volts(text: str) -> list[Volt]:
    return [v for v in voltages(text) if 100 <= v.value <= 400 and v.kind != "dc"]


def low_dc(text: str) -> bool:
    return bool(re.search(r"\bdc\b", text, re.I)) or any(
        0 < v.value <= 60 for v in voltages(text) if v.kind != "ac"
    )


def us_mains(text: Text) -> str | None:
    """US-only product or a 100-130 V rating with no 230 V option alongside it."""
    ac = mains_volts(text.text)
    return search(US_MAINS, text) or (
        ac[0].matched if ac and all(v.value <= 130 for v in ac) else None
    )


def mains_rules(items, project_text, user_level, out: Collector) -> None:
    us = False
    for item in items:
        adapter = bool(ADAPTER.search(identity(item)))
        for text in item_texts(item):
            matched = us_mains(text)
            if matched:
                us = True
            elif not adapter:
                ac = mains_volts(text.text)
                matched = (
                    search(MAINS, text) or search(PLUG, text) or (ac[0].matched if ac else None)
                )
            if matched:
                out.add("MAINS", text, matched)
    for text in project_text:
        matched = us_mains(text)
        if matched:
            us = True
        else:
            # Prose about the supply ("a 100-240 V USB adapter") is not mains wiring.
            ac = [] if ADAPTER.search(text.text) else mains_volts(text.text)
            matched = search(MAINS, text) or (ac[0].matched if ac else None)
        if matched:
            out.add("MAINS", text, matched)
    relay_hits = [(item, RELAY.search(identity(item))) for item in items]
    relays = [(item, match.group(0)) for item, match in relay_hits if match]
    context = project_text + [
        Text(i.line_id, "raw_name", i.raw_name)
        for i in items
        if not RELAY.search(identity(i)) and not ADAPTER.search(identity(i))
    ]
    # "12 V DC fan" is a low-voltage load; only unlabelled or AC loads count as hints.
    context = [t for t in context if mains_volts(t.text) or not low_dc(t.text)]
    hints = [(text, search(RELAY_AC_HINT, text)) for text in context]
    hints = [(text, matched) for text, matched in hints if matched]
    if relays and ("MAINS" in out.triggers or hints):
        for item, matched in relays:
            out.add("MAINS", Text(item.line_id, "raw_name", item.raw_name), matched)
        for text, matched in hints:
            out.add("MAINS", text, matched)
    if us:
        out.note("MAINS", "us")
    if user_level == "beginner":
        out.note("MAINS", "beginner")


def lipo_rules(items, project_text, out: Collector) -> None:
    protected = charged = False
    for item in items:
        name = identity(item)
        battery_part = bool(LITHIUM.search(name) or CHARGER.search(name) or BATTERY.search(name))
        protected = protected or (battery_part and bool(PROTECTION.search(name)))
        charged = charged or bool(CHARGER.search(name))
        if POWER_BANK.search(name):
            continue
        for text in item_texts(item):
            matched = search(LITHIUM, text)
            if matched:
                out.add("LIPO", text, matched)
    for text in project_text:
        matched = search(LITHIUM, text)
        if matched and not POWER_BANK.search(text.text):
            out.add("LIPO", text, matched)
    if "LIPO" in out.triggers:
        # Only BOM lines count as protection or charger evidence, never AI project prose.
        if protected and charged:
            del out.triggers["LIPO"]
            return
        if not protected:
            out.note("LIPO", "no_protection")
        if not charged:
            out.note("LIPO", "no_charger")


def addressable_estimate(item: BomItem) -> float | None:
    """Full-white current in amps, or None when the LED count is unknown."""
    name = identity(item)
    qty = item.qty or 1
    count = LED_COUNT.search(name)
    density, length = LED_DENSITY.search(name), LENGTH_M.search(LED_DENSITY.sub(" ", name))
    if count:
        leds = int(count.group(1)) * qty
    elif density and length:
        leds = int(density.group(1)) * float(length.group(1)) * qty
    elif MULTI_LED.search(name):
        return None
    else:
        leds = qty
    return round(leds * LED_FULL_WHITE_A, 2)


def current_rules(items, project_text, out: Collector) -> None:
    for item in items:
        name = identity(item)
        name_text = Text(item.line_id, "raw_name", item.raw_name)
        if ADDRESSABLE.search(name) or LED_STRIP.search(name):
            estimate = addressable_estimate(item)
            strip = bool(LED_STRIP.search(name) or re.search(r"\bstrips?\b", name, re.I))
            if strip or estimate is None or estimate >= ADDRESSABLE_MIN_A:
                matched = ADDRESSABLE.search(name) or LED_STRIP.search(name)
                out.add("HIGH_CURRENT", name_text, matched.group(0))
                if estimate is not None:
                    out.note(
                        "HIGH_CURRENT",
                        f"{item.line_id}: about {estimate:g} A at full white "
                        f"({estimate / LED_FULL_WHITE_A:g} LEDs x 60 mA)",
                    )
        load = LOAD.search(name)
        if load and not TINY_MOTOR.search(name):
            out.add("HIGH_CURRENT", name_text, load.group(0))
        if RELAY.search(name):
            continue  # Relay contact ratings ("10A 250VAC") are not loads.
        for text in item_texts(item):
            for amps, matched in currents(text.text):
                if amps > HIGH_CURRENT_A:
                    out.add("HIGH_CURRENT", text, matched)
    for text in project_text:
        matched = search(ADDRESSABLE, text) or search(LED_STRIP, text)
        load = search(LOAD, text)
        if load and TINY_MOTOR.search(text.text):
            load = None
        for found in (matched, load):
            if found:
                out.add("HIGH_CURRENT", text, found)
        for amps, found in currents(text.text):
            if amps > HIGH_CURRENT_A:
                out.add("HIGH_CURRENT", text, found)


def controller_domain(item: BomItem) -> tuple[str, str] | None:
    name = identity(item)
    low, high = CTRL_3V3.search(name), CTRL_5V.search(name)
    if not (low or high):
        return None
    matched = (low or high).group(0)
    if item.specs.logic_v is not None:
        return ("3v3" if item.specs.logic_v == 3.3 else "5v"), matched
    if low:
        return "3v3", matched
    if LOW_VARIANT.search(name):
        return "3v3", matched + " (3.3 V variant)"
    return "5v", matched


def peripheral_domain(item: BomItem) -> tuple[str, Text, str] | None:
    name = identity(item)
    name_text = Text(item.line_id, "raw_name", item.raw_name)
    for domain, pattern in (("5v", PERIPH_5V), ("3v3", PERIPH_3V3)):
        matched = pattern.search(name)
        if matched:
            return domain, name_text, matched.group(0)
    if NOT_LOGIC.search(name):
        return None
    specs = item.specs
    if specs.logic_v is not None:
        return (
            ("3v3" if specs.logic_v == 3.3 else "5v"),
            Text(item.line_id, "specs.logic_v", str(specs.logic_v)),
            f"logic {specs.logic_v:g} V",
        )
    if specs.supply_max_v is not None and specs.supply_max_v <= 3.6:
        field = Text(item.line_id, "specs.supply_max_v", str(specs.supply_max_v))
        return "3v3", field, f"supply max {specs.supply_max_v:g} V"
    if specs.supply_min_v is not None and specs.supply_min_v >= 4.5:
        field = Text(item.line_id, "specs.supply_min_v", str(specs.supply_min_v))
        return "5v", field, f"supply min {specs.supply_min_v:g} V"
    for index, requirement in enumerate(item.requirements):
        value = " ".join(filter(None, (requirement.name, requirement.value, requirement.unit)))
        if not VOLT_TERMS.search(value):
            continue
        volts = [v for v in voltages(value) if v.kind != "ac"]
        if not volts and (requirement.unit or "").strip().lower() in {"v", "vdc", "volt", "volts"}:
            try:
                volts = [Volt(float(requirement.value), None, value)]
            except ValueError:
                volts = []
        text = Text(item.line_id, f"requirements[{index}]", value)
        if volts and all(v.value >= 4.5 for v in volts) and all(v.value <= 5.5 for v in volts):
            return "5v", text, value
        if volts and all(2.5 <= v.value <= 3.6 for v in volts):
            return "3v3", text, value
    return None


def level_rules(items, project_text, out: Collector) -> None:
    controllers: dict[str, list[tuple[Text, str]]] = {"3v3": [], "5v": []}
    devices: dict[str, list[tuple[Text, str]]] = {"3v3": [], "5v": []}
    shifters = []
    for item in items:
        if SHIFTER.search(identity(item)):
            shifters.append(item.line_id)
            continue
        found = controller_domain(item)
        if found:
            domain, matched = found
            entry = (Text(item.line_id, "raw_name", item.raw_name), matched)
            controllers[domain].append(entry)
            devices[domain].append(entry)
            continue
        found = peripheral_domain(item)
        if found:
            domain, text, matched = found
            devices[domain].append((text, matched))
    for text in project_text:
        low, high = search(CTRL_3V3, text), search(CTRL_5V, text)
        if low or high:
            domain = "3v3" if low else ("3v3" if LOW_VARIANT.search(text.text) else "5v")
            controllers[domain].append((text, low or high))
            devices[domain].append((text, low or high))
        for domain, pattern in (("5v", PERIPH_5V), ("3v3", PERIPH_3V3)):
            matched = search(pattern, text)
            if matched:
                devices[domain].append((text, matched))
    hits = []
    for domain, other in (("3v3", "5v"), ("5v", "3v3")):
        if controllers[domain] and devices[other]:
            hits += controllers[domain] + devices[other]
    for text, matched in hits:
        out.add("LEVEL_SHIFT", text, matched)
    if hits and shifters:
        out.note("LEVEL_SHIFT", "shifter:" + ", ".join(shifters))


MAINS_GUIDANCE = [
    "India's mains is 230 V / 50 Hz. US projects assume 120 V / 60 Hz, so every part that "
    "touches mains must be rated for at least 250 V AC.",
    "Indian sockets take Type D (6 A) and Type M (16 A) plugs. Do not force a US (Type A/B) "
    "or UK (Type G) plug into a loose travel adapter.",
    "Keep all 230 V wiring inside a closed, insulated enclosure with strain relief, a fuse "
    "and a continuous earth. Nothing at 230 V may be exposed on the low-voltage side.",
    "Switch the load with a 230 V-rated relay module or SSR (rated for at least twice the "
    "load current) from a reputable brand, ISI/BIS or CE marked where available.",
    "Where possible, use a certified smart plug to switch the appliance instead of wiring "
    "mains yourself.",
    "Have a qualified electrician check the build before you plug it in.",
]
US_GUIDANCE = (
    "A part here is a US 120 V / 60 Hz product. Do not use it in India; replace it with a "
    "230 V-rated equivalent or a certified smart plug."
)
BEGINNER_GUIDANCE = (
    "If you are new to electronics, consider a low-voltage version of this project, for "
    "example switching a 5-12 V DC load instead of an appliance."
)
LIPO_GUIDANCE = [
    "Use cells with a built-in protection circuit (DW01 or BMS) or add a protection board. "
    "Never use bare, unprotected cells.",
    "Charge only with a proper lithium charger, for example a TP4056 module with protection "
    "(DW01 + 8205A), at the cell's rated current.",
    "Check the battery connector polarity (JST packs vary) before plugging it in.",
    "Never leave cells charging unattended or on a flammable surface. Stop using swollen, "
    "dented or hot cells.",
    "Multi-cell packs (2S, 3S...) need a balance charger or a matching BMS.",
]
CURRENT_GUIDANCE = [
    "Add up the worst-case current of every load and pick a supply with at least 25% "
    "headroom. WS2812B/NeoPixel LEDs draw about 60 mA each at full white (74 LEDs is about "
    "4.4 A); limit brightness in code if the supply is smaller.",
    "Power motors, LED strips and other heavy loads from their own supply, not the board's "
    "5 V pin or a USB port. Connect the grounds together.",
    "Use wire thick enough for the current, keep high-current runs short and put a fuse "
    "near the supply.",
    "Choose a 230 V-input SMPS or adapter with an Indian (Type D) plug, preferably BIS "
    "marked, rated above the total load.",
    "Motors and solenoids need flyback protection, and their stall current can be several "
    "times the running current.",
]
LEVEL_GUIDANCE = [
    "A 5 V output into a 3.3 V input (for example HC-SR04 ECHO into an ESP32) needs a "
    "divider (1 kΩ / 2 kΩ) or a level-shifter module. ESP32, ESP8266 and RP2040 pins are "
    "not 5 V tolerant.",
    "3.3 V data into WS2812/NeoPixel LEDs powered at 5 V can flicker: add a 74AHCT125 level "
    "shifter, a 300-500 Ω series resistor and a 470 µF capacitor across the LED supply.",
    "For I2C between 3.3 V and 5 V parts, use a bidirectional (BSS138) level-shifter module "
    "and check which voltage the pull-up resistors go to.",
    "Prefer 3.3 V-capable variants where they exist (for example HC-SR04P or RCWL-1601).",
    "Power 3.3 V-only modules (nRF24L01, RC522, ESP-01, LoRa) from 3.3 V, never from 5 V.",
]


def build(code: str, out: Collector) -> SafetyFlag:
    notes = out.notes.get(code, [])
    guidance: list[str]
    if code == "MAINS":
        severity, title = "danger", "230 V mains: read before building"
        message = (
            "This project may connect to or switch mains power. Mains wiring can kill or "
            "start a fire. Read the checklist before building."
        )
        guidance = ([US_GUIDANCE] if "us" in notes else []) + MAINS_GUIDANCE
        if "beginner" in notes:
            guidance.append(BEGINNER_GUIDANCE)
    elif code == "LIPO":
        severity, title = "warning", "Lithium battery safety"
        missing = [
            text
            for key, text in (
                ("no_protection", "a protection circuit"),
                ("no_charger", "a charger"),
            )
            if key in notes
        ]
        message = (
            "This project uses lithium (LiPo or Li-ion) cells, which can catch fire if "
            "over-charged, over-discharged or shorted. The parts list does not show "
            + " or ".join(missing)
            + "."
        )
        guidance = list(LIPO_GUIDANCE)
    elif code == "HIGH_CURRENT":
        severity, title = "warning", "High current: size the power supply"
        message = (
            "Some parts can draw several amps. An undersized supply or thin wires can "
            "overheat, and a board's USB port cannot power them."
        )
        if notes:
            message += " Rule estimate, not measured: " + "; ".join(notes) + "."
        guidance = list(CURRENT_GUIDANCE)
    else:
        severity, title = "caution", "Mixed 3.3 V and 5 V logic"
        message = (
            "This project mixes 3.3 V and 5 V logic. A 5 V signal can damage a 3.3 V input, "
            "and 3.3 V data may not reliably drive 5 V parts."
        )
        shifter = next((n for n in notes if n.startswith("shifter:")), None)
        if shifter:
            message += (
                f" A level shifter is listed ({shifter.removeprefix('shifter:')}); check "
                "that every mixed-voltage signal goes through it."
            )
        guidance = list(LEVEL_GUIDANCE)
    return SafetyFlag(
        code=code,
        severity=severity,
        title=title,
        message=message,
        guidance=guidance,
        line_ids=out.line_ids(code),
        triggers=out.triggers[code][:MAX_TRIGGERS],
        rule_version=RULE_VERSION,
    )


def evaluate(
    items: list[BomItem], project: ProjectContext | None, user_level: str = "beginner"
) -> list[SafetyFlag]:
    """Pure and deterministic: the same BOM and project text always give the same flags."""
    out = Collector(items)
    texts = project_texts(project)
    mains_rules(items, texts, user_level, out)
    lipo_rules(items, texts, out)
    current_rules(items, texts, out)
    level_rules(items, texts, out)
    return [
        build(code, out)
        for code in ("MAINS", "LIPO", "HIGH_CURRENT", "LEVEL_SHIFT")
        if out.triggers.get(code)
    ]


def flags_for(job: Job) -> list[SafetyFlag]:
    return evaluate(job.items, job.project, job.input.user_level)
