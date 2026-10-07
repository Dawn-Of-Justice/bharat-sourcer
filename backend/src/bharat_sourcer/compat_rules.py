"""Deterministic compatibility rules between a required part and an offered substitute.

Rules decide; nothing here calls a model. Each rule adds findings with a grade floor and the
"what changes" text. Facts carry a source: catalogue facts describe a typical module, so on
the offered side they may raise warnings but never count as known for a positive grade.
"""

from dataclasses import dataclass, field
from typing import Any

from bharat_sourcer.catalog import CatalogEntry
from bharat_sourcer.countries import INDIA

ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "X": 4}
LABELS = {
    "A": "Works as is",
    "B": "Works with a small setting change",
    "C": "Works with wiring or power changes",
    "D": "Different part, similar result",
    "X": "Don't use",
}
# Sources that count as declared for the offered part.
DECLARED = {"seller", "seller_title", "user", "test"}
META = {
    "aliases",
    "generic",
    "notes",
    "source",
    "verified",
    "substitutes",
    "lookalikes",
    "verify",
    "part_specs",
    "family",
    "name",
    "wiring_note",
}
# Fields where an empty list is still a meaningful catalogue value.
EMPTY_OK = {"features"}
TOLERANCE_V = 0.05
MAINS_MIN_RATING_VAC = 250


@dataclass
class Side:
    """Known facts about one part; `sources[field]` says where each value came from."""

    values: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    entry: CatalogEntry | None = None

    def set(self, name: str, value: Any, source: str) -> None:
        if value is None or (value == [] and name not in EMPTY_OK) or value == {}:
            return
        self.values[name] = value
        self.sources[name] = source

    def get(self, name: str) -> Any:
        return self.values.get(name)


def side_from_entry(entry: CatalogEntry, source: str = "catalog") -> Side:
    side = Side(entry=entry)
    for name, value in entry.model_dump().items():
        if name in META or (name in {"mains", "logic_follows_supply"} and value is False):
            continue
        if name == "features" and entry.category not in {"dev_board", "power"}:
            continue
        side.set(name, value, source)
    return side


def side_from_facts(source: str = "test", entry: CatalogEntry | None = None, **values) -> Side:
    """Build a side from explicit facts (tests and seller data); entry facts fill gaps."""
    side = side_from_entry(entry) if entry else Side()
    for name, value in values.items():
        side.set(name, value, source)
    return side


@dataclass
class Context:
    """Project facts: the controller the part connects to, rails and stated needs."""

    controller: str | None = None
    controller_logic_v: float | None = None
    controller_5v_tolerant: bool | None = None
    rails: tuple[float, ...] = ()
    rail_v: float | None = None
    source_controller: str | None = None
    strapping_pins: tuple[int, ...] = ()
    input_only_pins: tuple[int, ...] = ()
    mains_vac: float = INDIA.mains_vac
    uses_battery: bool | None = None
    needs: frozenset[str] = frozenset()
    motor_supply_v: float | None = None
    motor_current_a: float | None = None
    load_current_a: float | None = None
    led_count: int | None = None
    psu_current_a: float | None = None
    ranges: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    steps: dict[str, float] = field(default_factory=dict)
    i2c_in_use: frozenset[str] = frozenset()


@dataclass
class Finding:
    rule: str
    grade: str
    area: str
    message: str
    change: str | None = None
    basis: list[str] = field(default_factory=list)


@dataclass
class Outcome:
    grade: str | None
    findings: list[Finding]
    missing: list[str]

    @property
    def status(self) -> str:
        if self.grade is None:
            return "unknown"
        return {"A": "compatible", "X": "incompatible"}.get(self.grade, "changes_required")


def fmt(value: float) -> str:
    return f"{value:g}"


def span(value) -> str:
    return f"{fmt(value[0])}–{fmt(value[1])}"


def within(value: float, bounds) -> bool:
    return bounds[0] - TOLERANCE_V <= value <= bounds[1] + TOLERANCE_V


class Run:
    def __init__(self, required: Side, offered: Side, ctx: Context):
        self.req, self.off, self.ctx = required, offered, ctx
        self.findings: list[Finding] = []
        self.missing: list[str] = []

    def _miss(self, name: str) -> None:
        if name not in self.missing:
            self.missing.append(name)

    def need(self, side: str, name: str) -> Any:
        """Return a fact; record it as missing when unknown or, if offered, only catalogued."""
        source = self.req if side == "required" else self.off
        value = source.get(name)
        if value is None or (side == "offered" and source.sources.get(name) not in DECLARED):
            self._miss(f"{side}.{name}")
        return value

    def need_context(self, name: str) -> None:
        self._miss(f"context.{name}")

    def basis(self, *names: str) -> list[str]:
        out = []
        for name in names:
            side, _, key = name.partition(".")
            source = (self.req if side == "required" else self.off).sources.get(key)
            if source:
                out.append(f"{name}:{source}")
            elif side == "context":
                out.append(f"{name}:project")
        return out

    def add(self, rule, grade, area, message, change=None, basis=()) -> None:
        self.findings.append(Finding(rule, grade, area, message, change, self.basis(*basis)))


def effective_logic(side: Side, rail: float | None) -> float | None:
    if side.get("logic_follows_supply") and rail is not None:
        return 3.3 if rail < 4 else 5.0
    return side.get("logic_v")


def chosen_rail(run: Run) -> float | None:
    ctx = run.ctx
    if ctx.rail_v is not None:
        return ctx.rail_v
    rails = list(
        dict.fromkeys(
            ([ctx.controller_logic_v] if ctx.controller_logic_v else []) + list(ctx.rails)
        )
    )
    supply = run.req.get("supply_v")
    for rail in rails:
        if supply is None or within(rail, supply):
            return rail
    return rails[0] if rails else None


def rule_identity(run: Run) -> bool:
    """Returns False when the parts are too different for further checks to mean much."""
    req_cat = run.need("required", "category")
    off_cat = run.need("offered", "category")
    if req_cat and off_cat and req_cat != off_cat:
        run.add(
            "identity",
            "X",
            "verify",
            f"Different kind of part: {req_cat.replace('_', ' ')} vs {off_cat.replace('_', ' ')}",
            basis=("required.category", "offered.category"),
        )
        return False
    req_id, off_id = run.req.get("id"), run.off.get("id")
    edge = next(
        (s for s in (run.req.entry.substitutes if run.req.entry else []) if s.id == off_id), None
    )
    if edge:
        for change in edge.changes:
            run.add("curated_substitute", edge.grade, change.area, change.text, change.text)
        return True
    req_chip, off_chip = run.need("required", "chip"), run.need("offered", "chip")
    if not (req_chip and off_chip) or req_chip == off_chip or req_id == off_id:
        return True
    category = req_cat or off_cat
    if category == "dev_board":
        run.add(
            "board_chip",
            "D",
            "code",
            f"Different microcontroller ({req_chip} → {off_chip})",
            "Port the code, pin map and libraries to the new microcontroller.",
            ("required.chip", "offered.chip"),
        )
    elif category in {"sensor", "display", "motor_driver", "relay", "power", "led", "actuator"}:
        pass  # Category rules (measures, controller, drive, mains, output, protocol) grade these.
    else:
        run.add(
            "chip",
            "D",
            "code",
            f"Different chip ({req_chip} → {off_chip}); behaviour and pinout may differ",
            "Check the substitute's datasheet and adapt wiring and code.",
            ("required.chip", "offered.chip"),
        )
    return True


def rule_interface(run: Run) -> None:
    required = run.need("required", "interfaces")
    offered = run.need("offered", "interfaces")
    if not required or not offered:
        return
    primary = required[0]
    if primary in offered:
        return
    common = [i for i in required if i in offered]
    if common:
        run.add(
            "interface",
            "C",
            "wiring",
            f"Uses {common[0].upper()} instead of {primary.upper()}",
            f"Rewire for {common[0].upper()} and change the driver set-up in code.",
            ("required.interfaces", "offered.interfaces"),
        )
    else:
        run.add(
            "interface",
            "X",
            "wiring",
            f"No common interface: needs {', '.join(required)}, offers {', '.join(offered)}",
            basis=("required.interfaces", "offered.interfaces"),
        )


def rule_supply(run: Run) -> None:
    if run.req.get("supply_v") is None and run.off.get("supply_v") is None:
        return  # Neither part has a supply pin (e.g. an SSR or a driver with its own regulator).
    offered = run.need("offered", "supply_v")
    required = run.req.get("supply_v")
    rail = chosen_rail(run)
    if offered is None:
        return
    basis = ("required.supply_v", "offered.supply_v", "context.rails")
    if rail is not None:
        if within(rail, offered):
            return
        others = [r for r in run.ctx.rails if r != rail and within(r, offered)]
        if others:
            run.add(
                "supply_range",
                "C",
                "power",
                f"Supply range {span(offered)} V does not include the {fmt(rail)} V rail",
                f"Power it from the {fmt(others[0])} V rail instead of {fmt(rail)} V.",
                basis,
            )
        else:
            rails = ", ".join(fmt(r) for r in (run.ctx.rails or (rail,)))
            run.add(
                "supply_range",
                "X",
                "power",
                f"No project rail ({rails} V) is within the {span(offered)} V supply range",
                basis=basis,
            )
        return
    if required is None:
        run.need("required", "supply_v")
        return
    if within(required[0], offered) and within(required[1], offered):
        return
    if offered[0] <= required[1] and required[0] <= offered[1]:
        run.add(
            "supply_range",
            "C",
            "power",
            f"Narrower supply range ({span(offered)} V vs {span(required)} V)",
            f"Confirm the rail you power it from is within {span(offered)} V.",
            basis,
        )
    else:
        run.add(
            "supply_range",
            "X",
            "power",
            f"Supply ranges do not overlap ({span(offered)} V vs {span(required)} V)",
            basis=basis,
        )


def rule_logic(run: Run) -> None:
    ctx, rail = run.ctx, chosen_rail(run)
    if not any(s.get("logic_v") or s.get("logic_follows_supply") for s in (run.req, run.off)):
        return
    # The supply rule may already have moved the part to another rail.
    for finding in run.findings:
        if finding.rule == "supply_range" and finding.grade == "C" and ctx.rails:
            moved = [r for r in ctx.rails if within(r, run.off.get("supply_v"))]
            rail = moved[0] if moved else rail
    supply, mcu_rail = run.off.get("supply_v"), ctx.controller_logic_v
    if (
        run.off.get("logic_follows_supply")
        and supply
        and mcu_rail
        and rail != mcu_rail
        and mcu_rail in ctx.rails
        and within(mcu_rail, supply)
    ):
        # A module whose signals follow its supply can run from the controller's rail.
        rail = mcu_rail
        run.add(
            "supply_rail",
            "A",
            "power",
            f"Runs from {fmt(mcu_rail)} V, so its signals match the controller",
            f"Power it from the {fmt(mcu_rail)} V rail.",
            ("offered.supply_v", "context.controller_logic_v"),
        )
    off_logic = effective_logic(run.off, rail)
    source = "logic_follows_supply" if run.off.get("logic_follows_supply") else "logic_v"
    if off_logic is None or run.off.sources.get(source) not in DECLARED:
        run.need("offered", source if off_logic is not None else "logic_v")
    if off_logic is None:
        return
    req_logic = effective_logic(run.req, chosen_rail(run))
    basis = ("offered.logic_v", "context.controller_logic_v")
    mcu = ctx.controller_logic_v
    if mcu is None:
        if req_logic is None:
            run.need("required", "logic_v")
        elif req_logic != off_logic:
            run.add(
                "logic_level",
                "C",
                "wiring",
                f"Logic level differs ({fmt(req_logic)} V → {fmt(off_logic)} V)",
                "Add a level shifter, or confirm your controller's logic level.",
                ("required.logic_v", "offered.logic_v"),
            )
        return
    name = ctx.controller or "the controller"
    if mcu < 4 and off_logic >= 4:
        signals = run.off.get("output_signals") or []
        if signals and ctx.controller_5v_tolerant is not True:
            run.add(
                "logic_level",
                "C",
                "wiring",
                f"{'/'.join(signals)} drives 5 V into {name}, whose inputs are not 5 V tolerant",
                f"Add a 1 kΩ/2 kΩ divider or a level shifter on {'/'.join(signals)}.",
                basis,
            )
        accepts = run.off.get("input_3v3_ok")
        if accepts is None:
            run.need("offered", "input_3v3_ok")
        elif accepts is False:
            same = run.req.get("input_3v3_ok") is False and req_logic is not None and req_logic >= 4
            run.add(
                "logic_level",
                "A" if same else "C",
                "wiring",
                "3.3 V signals are below this part's 5 V input threshold"
                + ("; the original design has the same limit" if same else ""),
                "Add a 74AHCT125 level shifter on the data line"
                + (" (optional upgrade)." if same else "."),
                basis,
            )
    elif mcu >= 4 and off_logic < 4:
        tolerant = run.need("offered", "io_5v_tolerant")
        if tolerant is False or (tolerant is None and run.off.get("io_5v_tolerant") is False):
            run.add(
                "logic_level",
                "C",
                "wiring",
                f"3.3 V part on a 5 V controller ({name})",
                "Add a level shifter (e.g. a BSS138 board) between the controller and the part.",
                basis,
            )


def rule_i2c(run: Run) -> None:
    required = run.req.get("interfaces") or []
    offered = run.off.get("interfaces") or []
    if "i2c" not in required or (offered and "i2c" not in offered):
        return
    req_addrs = run.need("required", "i2c_addresses")
    off_addrs = run.need("offered", "i2c_addresses")
    if not req_addrs or not off_addrs:
        return
    want, have = req_addrs[0], off_addrs[0]
    basis = ("required.i2c_addresses", "offered.i2c_addresses")
    if have != want:
        if want in off_addrs:
            change = f"Set the address jumper (ADDR/SDO) for {want}, or use {have} in code."
        else:
            change = f"Change the I2C address in code from {want} to {have} (e.g. begin({have}))."
        run.add(
            "i2c_address", "B", "code", f"Default I2C address is {have}, not {want}", change, basis
        )
    if have in run.ctx.i2c_in_use and have != want:
        run.add(
            "i2c_collision",
            "C",
            "wiring",
            f"Address {have} collides with another device on the bus",
            "Move one device with its address jumper or add a TCA9548A multiplexer.",
            basis,
        )


CONNECTOR_NAMES = {"stemma_qt": "STEMMA QT", "qwiic": "Qwiic", "grove": "Grove", "jst_ph": "JST-PH"}


def rule_connector(run: Run) -> None:
    required, offered = run.req.get("connector"), run.off.get("connector")
    if required is None or required == "header":
        return
    offered = run.need("offered", "connector")
    if offered is None or offered == required or {required, offered} == {"stemma_qt", "qwiic"}:
        return
    basis = ("required.connector", "offered.connector")
    if required in CONNECTOR_NAMES and offered == "header":
        run.add(
            "connector",
            "B",
            "wiring",
            f"No {CONNECTOR_NAMES[required]} connector",
            "Solder headers and use jumper wires (VIN, GND, SCL, SDA).",
            basis,
        )
    elif required == "pi_hat":
        note = (run.req.entry.wiring_note if run.req.entry else None) or "Wire it with jumpers."
        run.add("connector", "C", "wiring", "Not a HAT: it does not plug onto the Pi", note, basis)
    elif required == "feather":
        run.add(
            "connector",
            "A",
            "wiring",
            "Different form factor: FeatherWings will not stack",
            "Plan breadboard wiring instead of stacking FeatherWings.",
            basis,
        )
    elif required == "pololu_stepstick" or offered == "pololu_stepstick":
        run.add(
            "footprint",
            "C",
            "wiring",
            "Footprint differs from the original driver",
            "Rewire the driver by pin function.",
            basis,
        )
    else:
        run.add(
            "connector",
            "C",
            "wiring",
            f"Connector differs ({required} vs {offered})",
            "Use an adapter cable or rewire.",
            basis,
        )


def pin_key(pins: list[str]) -> list[str]:
    return [
        {"VIN": "VCC", "+": "VCC", "5V": "VCC", "3.3V": "VCC"}.get(p.upper(), p.upper())
        for p in pins
    ]


def rule_header_order(run: Run) -> None:
    required = run.req.get("pins")
    if not required:
        if run.req.get("category") == "display" and run.req.get("connector") in {None, "header"}:
            run.need("required", "pins")  # Header order varies between display makers.
        return
    if run.req.get("connector") not in {None, "header"}:
        return
    offered = run.need("offered", "pins")
    if not offered:
        if run.req.get("category") == "display":
            run.add(
                "header_order",
                "A",
                "verify",
                "Header order is not declared",
                "Check the VCC/GND order on the silkscreen before powering it.",
            )
        return
    left, right = pin_key(required), pin_key(offered)
    basis = ("required.pins", "offered.pins")
    if left == right:
        return
    if sorted(left) == sorted(right):
        run.add(
            "header_order",
            "C",
            "wiring",
            f"Pin order differs: {','.join(required)} vs {','.join(offered)}",
            "Wire by the silkscreen labels: a reversed VCC/GND kills the module.",
            basis,
        )
    else:
        run.add(
            "header_order",
            "C",
            "wiring",
            f"Pins differ: {','.join(required)} vs {','.join(offered)}",
            "Rewire by pin function; a safe mapping must be checked against both datasheets.",
            basis,
        )


def rule_measures(run: Run) -> None:
    required = run.need("required", "measures")
    offered = run.need("offered", "measures")
    if not required or not offered:
        return
    lost = [q for q in required if q not in offered]
    basis = ("required.measures", "offered.measures")
    if lost:
        core = [q for q in lost if q in run.ctx.needs]
        run.add(
            "measured_superset",
            "X" if core else "D",
            "code",
            f"Does not measure {', '.join(lost)}"
            + ("; the project uses it" if core else "; the original does"),
            None
            if core
            else "Treat it as a functional alternative and drop or replace that reading.",
            basis,
        )
    elif run.req.get("chip") and run.off.get("chip") and run.req.get("chip") != run.off.get("chip"):
        libs = run.off.get("libraries") or []
        same = set(libs) & set(run.req.get("libraries") or [])
        if not same:
            run.add(
                "library_change",
                "B",
                "code",
                f"Different sensor chip ({run.req.get('chip')} → {run.off.get('chip')})",
                f"Switch to the {libs[0] if libs else 'matching'} library; readings stay the same.",
                ("required.chip", "offered.chip"),
            )
    req_ranges, off_ranges = run.req.get("ranges") or {}, run.off.get("ranges") or {}
    for quantity, bounds in req_ranges.items():
        if quantity.split("_")[0] in lost:
            continue
        have = off_ranges.get(quantity)
        if have is None:
            run.need("offered", f"ranges.{quantity}")
            continue
        need_lo, need_hi = run.ctx.ranges.get(quantity, (None, None))
        label = quantity.replace("_", " ")
        if (need_lo is not None and have[0] > need_lo) or (
            need_hi is not None and have[1] < need_hi
        ):
            run.add(
                "measured_range",
                "X",
                "verify",
                f"{label} range {span(have)} cannot cover the project's need",
                basis=("offered.ranges", "context.ranges"),
            )
        elif have[0] > bounds[0] + 0.01 or have[1] < bounds[1] - 0.01:
            run.add(
                "measured_range",
                "D",
                "verify",
                f"Narrower {label} range ({span(have)} vs {span(bounds)})",
                "Confirm the project stays inside the narrower range.",
                ("required.ranges", "offered.ranges"),
            )
    req_steps, off_steps = run.req.get("steps") or {}, run.off.get("steps") or {}
    for quantity, step in req_steps.items():
        have = off_steps.get(quantity)
        if have is None or quantity.split("_")[0] in lost:
            continue
        need = run.ctx.steps.get(quantity)
        label = quantity.replace("_", " ")
        if need is not None and have > need:
            run.add(
                "measured_resolution",
                "X",
                "verify",
                f"{label} resolution {fmt(have)} is coarser than the {fmt(need)} the project needs",
                basis=("offered.steps", "context.steps"),
            )
        elif have > step * 1.5:
            run.add(
                "measured_resolution",
                "D",
                "verify",
                f"Coarser {label} resolution ({fmt(have)} vs {fmt(step)})",
                "Readings lose precision; confirm that is acceptable.",
                ("required.steps", "offered.steps"),
            )


def rule_display(run: Run) -> None:
    required = run.need("required", "display_controller")
    offered = run.need("offered", "display_controller")
    if required and offered and required != offered:
        if not any(f.rule == "curated_substitute" for f in run.findings):
            libs = run.off.get("libraries") or []
            run.add(
                "display_controller",
                "B",
                "code",
                f"Display controller differs ({required} → {offered})",
                f"Switch to a library that supports {offered}"
                + (f" ({libs[0]})" if libs else "")
                + "; check the constructor and colour constants.",
                ("required.display_controller", "offered.display_controller"),
            )
    required = run.need("required", "display_resolution")
    offered = run.need("offered", "display_resolution")
    if required and offered and required != offered:
        run.add(
            "display_resolution",
            "D",
            "code",
            f"Resolution differs ({required} → {offered})",
            "Redraw the screen layout for the new resolution.",
            ("required.display_resolution", "offered.display_resolution"),
        )


def rule_driver(run: Run) -> None:
    ctx = run.ctx
    mcu = ctx.controller_logic_v
    if mcu is not None and mcu < 4 and run.need("offered", "input_3v3_ok") is False:
        run.add(
            "logic_level",
            "C",
            "wiring",
            "Control inputs do not accept 3.3 V logic",
            "Add a level shifter on the control lines.",
            ("offered.input_3v3_ok", "context.controller_logic_v"),
        )
    elif mcu is not None and mcu >= 4 and run.need("offered", "io_5v_tolerant") is False:
        run.add(
            "logic_level",
            "C",
            "wiring",
            "Control inputs are not 5 V tolerant",
            "Add a level shifter on the control lines.",
            ("offered.io_5v_tolerant", "context.controller_logic_v"),
        )
    req_ctl = run.need("required", "control_interface")
    off_ctl = run.need("offered", "control_interface")
    if req_ctl and off_ctl and req_ctl != off_ctl:
        run.add(
            "control_interface",
            "D",
            "code",
            f"Control interface differs ({req_ctl} → {off_ctl})",
            "Rewrite the motor code and rewire the control pins.",
            ("required.control_interface", "offered.control_interface"),
        )
    req_chip, off_chip = run.req.get("chip"), run.off.get("chip")
    edge = any(f.rule == "curated_substitute" for f in run.findings)
    if req_chip and off_chip and req_chip != off_chip and not edge and req_ctl == off_ctl:
        run.add(
            "driver_chip",
            "C",
            "power",
            f"Different driver chip ({req_chip} → {off_chip})",
            "Re-tune the current limit with the new driver's formula and check its pin table.",
            ("required.chip", "offered.chip"),
        )
    required = run.need("required", "current_a")
    offered = run.need("offered", "current_a")
    if offered is not None:
        if ctx.motor_current_a is not None:
            if offered < ctx.motor_current_a:
                run.add(
                    "driver_current",
                    "X",
                    "power",
                    f"Rated {fmt(offered)} A; the motor needs {fmt(ctx.motor_current_a)} A",
                    basis=("offered.current_a", "context.motor_current_a"),
                )
        elif required is not None and offered < required * 0.95:
            run.add(
                "driver_current",
                "C",
                "power",
                f"Lower current rating ({fmt(offered)} A vs {fmt(required)} A)",
                f"Confirm the motor draws at most {fmt(offered)} A per phase.",
                ("required.current_a", "offered.current_a"),
            )
    required = run.need("required", "motor_supply_v")
    offered = run.need("offered", "motor_supply_v")
    if offered is None:
        return
    if ctx.motor_supply_v is not None:
        if not within(ctx.motor_supply_v, offered):
            run.add(
                "motor_supply",
                "X",
                "power",
                f"Motor supply {fmt(ctx.motor_supply_v)} V is outside {span(offered)} V",
                basis=("offered.motor_supply_v", "context.motor_supply_v"),
            )
    elif required is not None and (
        offered[0] > required[0] + 0.5 or offered[1] < required[1] - 0.5
    ):
        run.add(
            "motor_supply",
            "C",
            "power",
            f"Narrower motor-supply range ({span(offered)} V vs {span(required)} V)",
            f"Confirm the motor supply is within {span(offered)} V.",
            ("required.motor_supply_v", "offered.motor_supply_v"),
        )


def rule_mains(run: Run) -> None:
    if not (run.req.get("mains") or run.off.get("mains")):
        return
    threshold = max(MAINS_MIN_RATING_VAC, run.ctx.mains_vac + 20)
    rating = run.need("offered", "mains_rating_vac")
    if rating is not None and rating < threshold:
        run.add(
            "mains_rating",
            "X",
            "safety",
            f"Rated {fmt(rating)} VAC; India's mains is {fmt(run.ctx.mains_vac)} V "
            f"and needs at least {fmt(threshold)} VAC",
            basis=("offered.mains_rating_vac",),
        )
    if run.req.get("enclosed") and run.need("offered", "enclosed") is False:
        run.add(
            "mains_enclosure",
            "C",
            "safety",
            "Bare mains module replaces an enclosed product",
            "Mount it in an insulated enclosure with earth, a fuse and strain relief; "
            "no exposed 230 V.",
            ("required.enclosed", "offered.enclosed"),
        )
    req_level = run.req.get("active_level")
    off_level = run.need("offered", "active_level") if req_level else None
    if req_level and off_level and req_level != off_level:
        run.add(
            "polarity",
            "B",
            "code",
            f"Control input is active-{off_level.upper()} (original: active-{req_level.upper()})",
            "Invert the control logic in code (swap HIGH and LOW in digitalWrite).",
            ("required.active_level", "offered.active_level"),
        )
    control = run.off.get("control_v")
    mcu = run.ctx.controller_logic_v
    if control and mcu and not within(mcu, control):
        run.add(
            "control_voltage",
            "C",
            "wiring",
            f"Control input needs {span(control)} V; the controller gives {fmt(mcu)} V",
            "Drive the input through a transistor stage.",
            ("offered.control_v", "context.controller_logic_v"),
        )


def rule_power(run: Run) -> None:
    ctx = run.ctx
    want = run.req.get("output_v")
    have = run.need("offered", "output_v") if want else run.off.get("output_v")
    if want and have and abs(want - have) > 0.1:
        run.add(
            "output_voltage",
            "X",
            "power",
            f"Outputs {fmt(have)} V instead of {fmt(want)} V",
            basis=("required.output_v", "offered.output_v"),
        )
    want = run.req.get("current_a")
    have = run.need("offered", "current_a") if want else run.off.get("current_a")
    if have is not None:
        if ctx.load_current_a is not None:
            if have < ctx.load_current_a:
                run.add(
                    "output_current",
                    "X",
                    "power",
                    f"Rated {fmt(have)} A; the load needs {fmt(ctx.load_current_a)} A",
                    basis=("offered.current_a", "context.load_current_a"),
                )
        elif want is not None and have < want * 0.95:
            run.add(
                "output_current",
                "C",
                "power",
                f"Lower current rating ({fmt(have)} A vs {fmt(want)} A)",
                f"Confirm the load including motor peaks stays under {fmt(have)} A.",
                ("required.current_a", "offered.current_a"),
            )
    if run.req.get("input_vac") or run.off.get("input_vac"):
        vac = run.need("offered", "input_vac")
        if vac and not within(ctx.mains_vac, vac):
            run.add(
                "mains_input",
                "X",
                "safety",
                f"Input {span(vac)} VAC: not usable on India's {fmt(ctx.mains_vac)} V mains",
                basis=("offered.input_vac",),
            )
        plug = run.off.get("plug")
        if plug and plug.startswith("us_"):
            run.add(
                "plug",
                "C",
                "power",
                "US plug",
                "Prefer an adapter with an Indian Type D/M plug.",
                ("offered.plug",),
            )
    want = run.req.get("barrel")
    have = run.need("offered", "barrel") if want else None
    if want and have and want != have:
        run.add(
            "barrel",
            "C",
            "power",
            f"Barrel {have.replace('x', '×')} instead of {want.replace('x', '×')}",
            "A mismatched barrel gives intermittent contact: match the jack or use an adapter.",
            ("required.barrel", "offered.barrel"),
        )
    want = run.req.get("polarity")
    have = run.need("offered", "polarity") if want else None
    if want and have and want != have:
        run.add(
            "polarity",
            "X",
            "power",
            "Barrel polarity is reversed; it can destroy the device",
            basis=("required.polarity", "offered.polarity"),
        )
    if "battery_protection" in (run.req.get("features") or []) and "battery_protection" not in (
        run.off.get("features") or []
    ):
        run.add(
            "battery_protection",
            "C",
            "safety",
            "No battery protection (DW01) on the substitute",
            "Use a protected cell or add a DW01 protection board.",
            ("required.features", "offered.features"),
        )


def rule_led(run: Run) -> None:
    ctx = run.ctx
    want = run.need("required", "protocol")
    have = run.need("offered", "protocol")
    if want and have and want != have:
        if {want, have} == {"ws2812b", "sk6812_rgbw"}:
            run.add(
                "led_protocol",
                "B",
                "code",
                "Pixel type differs (RGB vs RGBW)",
                "Use NEO_GRBW instead of NEO_GRB (or the reverse) in the strip constructor.",
                ("required.protocol", "offered.protocol"),
            )
        elif "apa102" in {want, have}:
            run.add(
                "led_protocol",
                "C",
                "wiring",
                "APA102 uses data and clock lines",
                "Rewire data plus clock and switch to the DotStar/FastLED driver.",
                ("required.protocol", "offered.protocol"),
            )
        else:
            run.add(
                "led_protocol",
                "D",
                "code",
                f"LED protocol differs ({want} → {have})",
                "Rewrite the LED driver code.",
                ("required.protocol", "offered.protocol"),
            )
    per_led = run.off.get("ma_per_led")
    if ctx.led_count and ctx.psu_current_a and per_led:
        amps = ctx.led_count * per_led / 1000
        if amps > ctx.psu_current_a:
            same = run.req.get("ma_per_led") == per_led
            run.add(
                "current_headroom",
                "A" if same else "C",
                "power",
                f"{ctx.led_count} LEDs × {fmt(per_led)} mA ≈ {amps:.1f} A at full white, "
                f"above the {fmt(ctx.psu_current_a)} A supply",
                f"Use a 5 V supply of at least {amps:.1f} A "
                "or limit brightness (setBrightness(64)).",
                ("offered.ma_per_led", "context.psu_current_a"),
            )


def rule_board(run: Run) -> None:
    ctx = run.ctx
    if any(f.rule == "board_chip" for f in run.findings):
        return
    want, have = run.need("required", "logic_v"), run.need("offered", "logic_v")
    if want and have and want != have:
        run.add(
            "board_logic",
            "C",
            "wiring",
            f"Board logic changes from {fmt(want)} V to {fmt(have)} V",
            "Check every connected module's supply and logic level.",
            ("required.logic_v", "offered.logic_v"),
        )
    want, have = run.req.get("clock_mhz"), run.off.get("clock_mhz")
    if want and have and want != have:
        run.add(
            "board_clock",
            "B",
            "code",
            f"Clock is {have} MHz (original {want} MHz)",
            f"Select the {have} MHz board variant before uploading.",
            ("required.clock_mhz", "offered.clock_mhz"),
        )
    want = run.req.get("board_target")
    have = run.need("offered", "board_target") if want else None
    if want and have and want != have:
        run.add(
            "board_target",
            "B",
            "code",
            "Different board definition",
            f"Select board {have} in the IDE (PlatformIO/Arduino).",
            ("required.board_target", "offered.board_target"),
        )
    want = run.req.get("usb_serial")
    have = run.need("offered", "usb_serial") if want else None
    if want and have and want != have and have not in {"native"}:
        run.add(
            "usb_driver",
            "B",
            "code",
            f"USB-serial chip is {have.upper()}",
            f"Install the {have.upper()} USB driver if the port does not appear.",
            ("required.usb_serial", "offered.usb_serial"),
        )
    if run.off.get("bootloader") == "old" and run.req.get("bootloader") != "old":
        run.add(
            "bootloader",
            "B",
            "code",
            "Ships with the old bootloader",
            "If uploads fail, select 'ATmega328P (Old Bootloader)'.",
            ("offered.bootloader",),
        )
    want, have = run.req.get("pin_labels"), run.off.get("pin_labels")
    if want and have and want != have:
        run.add(
            "pin_labels",
            "B",
            "wiring",
            "Silkscreen uses D-labels instead of GPIO numbers"
            if have == "d_labels"
            else "Silkscreen uses GPIO numbers instead of D-labels",
            "Rewrite wiring steps with the new labels (D1 = GPIO5, D2 = GPIO4 on ESP8266).",
            ("required.pin_labels", "offered.pin_labels"),
        )
    required = run.req.get("features") or []
    offered = run.need("offered", "features") if required else None
    if offered is None:
        return
    for feature in [f for f in required if f not in offered]:
        if feature == "lipo_charger":
            if ctx.uses_battery is None:
                run.need_context("uses_battery")
                run.add(
                    "battery_charger",
                    "A",
                    "power",
                    "No LiPo charger on the substitute",
                    "If the project runs from a battery, add a TP4056 with DW01 protection.",
                )
            elif ctx.uses_battery:
                run.add(
                    "battery_charger",
                    "C",
                    "power",
                    "No LiPo charger or battery connector",
                    "Add a TP4056 module with DW01 protection plus a regulator, "
                    "or drop the battery.",
                    ("required.features", "offered.features", "context.uses_battery"),
                )
        elif feature in ctx.needs:
            run.add(
                "board_feature",
                "X",
                "code",
                f"No {feature.replace('_', ' ')}, which the project uses",
                basis=("required.features", "offered.features"),
            )
        else:
            run.need_context(f"uses_{feature}")
            run.add(
                "board_feature",
                "A",
                "code",
                f"No {feature.replace('_', ' ')} on the substitute",
                f"Confirm the project does not use {feature.replace('_', ' ')}.",
            )


def rule_pin_function(run: Run) -> None:
    ctx = run.ctx
    if not (ctx.source_controller and ctx.controller) or ctx.source_controller == ctx.controller:
        return
    avoid = []
    if ctx.strapping_pins:
        avoid.append("strapping pins " + ", ".join(map(str, ctx.strapping_pins)))
    if ctx.input_only_pins:
        avoid.append("input-only pins " + ", ".join(map(str, ctx.input_only_pins)) + " for outputs")
    run.add(
        "pin_function",
        "B",
        "wiring",
        f"Controller changes from {ctx.source_controller} to {ctx.controller}",
        "Remap the pins in wiring and code" + (f"; avoid {' and '.join(avoid)}." if avoid else "."),
        ("context.controller",),
    )


def rule_legacy(run: Run) -> None:
    """Fields from the original typed specs that only some families declare."""
    for name in ("output_mode", "data_support", "connector_a", "connector_b"):
        want = run.req.get(name)
        if want is None:
            continue
        have = run.need("offered", name)
        if have is None or have == want:
            continue
        if name == "data_support":
            if want and not have:
                run.add(
                    "usb_data", "X", "wiring", "Project needs USB data; the cable is charge-only"
                )
        else:
            run.add(
                name,
                "X",
                "wiring",
                f"{name.replace('_', ' ')} differs: needs {want}, offers {have}",
                basis=(f"required.{name}", f"offered.{name}"),
            )
    want, have = run.req.get("active_level"), run.off.get("active_level")
    if run.req.get("category") != "relay" and want and have and want != have:
        run.add(
            "polarity",
            "B",
            "code",
            f"Output is active-{have.upper()} (original: active-{want.upper()})",
            "Invert the logic that reads this signal.",
            ("required.active_level", "offered.active_level"),
        )
    elif run.req.get("category") != "relay" and want:
        run.need("offered", "active_level")


def rule_lookalike(run: Run) -> None:
    entry = run.off.entry or run.req.entry
    if entry and (entry.lookalikes or entry.verify):
        text = entry.verify or "Check the chip markings on arrival; look-alike parts are common."
        run.add("lookalike_risk", "A", "verify", "Look-alike parts are sold under this name", text)


SKIP_ELECTRICAL = {"dev_board", "passive", "cable", "misc"}


def evaluate(required: Side, offered: Side, ctx: Context | None = None) -> Outcome:
    ctx = ctx or Context()
    run = Run(required, offered, ctx)
    if rule_identity(run):
        category = required.get("category") or offered.get("category")
        if category not in SKIP_ELECTRICAL | {"power"}:
            rule_interface(run)
            if category != "motor_driver":
                rule_supply(run)
                rule_logic(run)
            rule_i2c(run)
            rule_header_order(run)
        rule_connector(run)
        if category == "sensor":
            rule_measures(run)
        if category == "display":
            rule_display(run)
        if category == "motor_driver":
            rule_driver(run)
        if category in {"relay", "power"}:
            rule_mains(run)
        if category == "power":
            rule_power(run)
        if category == "led":
            rule_led(run)
        if category == "dev_board":
            rule_board(run)
        else:
            rule_pin_function(run)
        rule_legacy(run)
        rule_lookalike(run)
    worst = max((f.grade for f in run.findings), key=ORDER.get, default="A")
    # Unknown specifications block positive grades; known problems stay visible.
    grade = None if run.missing and ORDER[worst] <= ORDER["B"] else worst
    return Outcome(grade, run.findings, run.missing)
