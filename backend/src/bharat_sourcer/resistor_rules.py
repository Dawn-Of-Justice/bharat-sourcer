"""Versioned, guarded low-voltage LED resistor suggestions. Never mutate the BOM."""

import logging
from decimal import ROUND_CEILING, Decimal
from threading import Lock
from uuid import uuid4

from bharat_sourcer.schemas import ResistorAdvice, ResistorInputs

E24 = (
    10,
    11,
    12,
    13,
    15,
    16,
    18,
    20,
    22,
    24,
    27,
    30,
    33,
    36,
    39,
    43,
    47,
    51,
    56,
    62,
    68,
    75,
    82,
    91,
)
_quarantined = False
_lock = Lock()
REFERENCE = "https://www.digikey.ie/en/resources/conversion-calculators/conversion-calculator-led-series-resistor"


def primary_select(minimum: Decimal) -> Decimal:
    for decade in range(-1, 7):
        for value in E24:
            candidate = Decimal(value) * Decimal(10) ** decade
            if candidate >= minimum:
                return candidate
    raise ValueError("Outside resistor range")


def fallback_select(minimum: Decimal) -> Decimal:
    # Separate enumeration implementation shipped and tested with the primary rule.
    candidates = {Decimal(str(v)) * (Decimal(10) ** d) for d in range(-1, 7) for v in E24}
    return min(value for value in candidates if value >= minimum)


def validate_selection(value: Decimal, minimum: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < minimum:
        raise ValueError("Current bound violated")
    # Independent oracle checks membership AND lowest acceptable standard value.
    expected = min(
        Decimal(v) * Decimal(10) ** d
        for d in range(-1, 7)
        for v in E24
        if Decimal(v) * Decimal(10) ** d >= minimum
    )
    if value != expected:
        raise ValueError("Invalid standard value selection")


def ceil_text(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.000001"), rounding=ROUND_CEILING))


def calculate(inputs: ResistorInputs) -> ResistorAdvice:
    global _quarantined  # noqa: PLW0603 - process-wide quarantine flag set once on failure
    drop = Decimal(str(inputs.supply_max_v)) - Decimal(str(inputs.led_forward_min_v))
    if drop <= 0:
        raise ValueError("Supply maximum must exceed the LED minimum forward voltage")
    limit = min(Decimal(str(inputs.target_max_ma)), Decimal(str(inputs.driver_limit_ma))) / 1000
    minimum = drop / limit / Decimal("0.95")
    if minimum > Decimal("91000000"):
        raise ValueError("Required resistance exceeds supported range")
    recovery, version = "none", "led-series-e24-v1"
    with _lock:
        try:
            if _quarantined:
                raise RuntimeError("Primary rule quarantined")
            # Known vectors run before each calculation to detect a damaged selector.
            for threshold, expected in [("1", "1"), ("261", "270"), ("1000", "1000")]:
                if primary_select(Decimal(threshold)) != Decimal(expected):
                    raise ValueError("Rule self-check failed")
            resistance = primary_select(minimum)
            validate_selection(resistance, minimum)
        except Exception:
            if not _quarantined:
                logging.getLogger(__name__).error(
                    "RULE_QUARANTINED rule=led-series-e24-v1 fallback=led-series-e24-reference-v1"
                )
            _quarantined = True
            version, recovery = "led-series-e24-reference-v1", "validated_fallback"
            try:
                resistance = fallback_select(minimum)
                validate_selection(resistance, minimum)
            except Exception:
                logging.getLogger(__name__).error(
                    "RULE_UNAVAILABLE rule=led-series-e24-reference-v1"
                )
                return ResistorAdvice(
                    advice_id=str(uuid4()),
                    inputs=inputs,
                    status="unavailable",
                    rule_version=version,
                    recovery="blocked",
                    explanation="Rule validation failed. No resistor value is recommended.",
                )
    actual_min = resistance * Decimal("0.95")
    current = drop / actual_min
    power = drop * drop / actual_min
    return ResistorAdvice(
        advice_id=str(uuid4()),
        inputs=inputs,
        status="suggestion",
        rule_version=version,
        recovery=recovery,
        resistance_ohm=str(resistance.normalize()),
        worst_case_current_ma=ceil_text(current * 1000),
        worst_case_power_w=ceil_text(power),
        minimum_rated_power_w=ceil_text(power * 2),
        explanation=(
            "R >= (supply_max_v - led_forward_min_v) / "
            "min(target_max_ma, driver_limit_ma) * 1000 / 0.95. "
            "Choose the next E24 value; allow 5% resistance tolerance. "
            "Minimum rated power uses a 2x dissipation margin."
        ),
        limitations=[
            "Conditional suggestion from user-confirmed bounds, not extracted video evidence.",
            "One LED and one series resistor on a low-voltage DC source only (up to 24 V, 20 mA).",
            "Driver current must be an allowable design limit, not an absolute maximum rating.",
            "Check LED and driver datasheets, temperature derating and wiring before use.",
            "Uses the supplied minimum LED forward voltage; brightness is not guaranteed.",
            "Excludes piezo protection, pull-ups, dividers, LED strings and whole-circuit safety.",
        ],
        references=[REFERENCE],
    )
