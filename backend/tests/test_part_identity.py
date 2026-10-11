"""Synthetic regression cases for schematic labels in seller searches."""

import pytest

from bharat_sourcer.part_identity import without_reference
from bharat_sourcer.schemas import BomItem, BuyableSpec, Evidence, SpecParam
from bharat_sourcer.sourcing.part_spec import buyable_spec
from bharat_sourcer.sourcing.routing import route_queries
from bharat_sourcer.sourcing.textmatch import relevance


@pytest.mark.parametrize(
    "name, expected",
    [
        ("LM3915 (IC1)", "LM3915"),
        ("BC548 (T1)", "BC548"),
        ("R4, R5", ""),
        ("VR1", ""),
        ("Arduino Uno R3", "Arduino Uno R3"),
        ("C3 capacitor module", "C3 capacitor module"),
    ],
)
def test_reference_annotations(name, expected):
    assert without_reference(name) == expected


def test_coded_resistor_uses_guarded_value_for_routing():
    item = BomItem(
        line_id="L01",
        raw_name="R1",
        evidence=[
            Evidence(
                source="project_page",
                observation="R1 is a 10k ohm resistor.",
                quote="R1: 10k ohm resistor",
                url="https://example.com/circuit",
            )
        ],
        buyable_spec=BuyableSpec(
            category="resistor",
            params=[
                SpecParam(
                    name="resistance",
                    value="10k ohm",
                    origin="stated",
                )
            ],
            queries=["10k resistor"],
        ),
    )
    spec = buyable_spec(item)
    assert spec.part_name == "10k ohm resistor"
    rungs = route_queries(spec, item.raw_name, item.raw_name)
    assert rungs and all(q.part_terms == "10k ohm resistor" for q in rungs)
    assert relevance(rungs[0].part_terms, "10K Ohm Resistor Pack of 10") == 1
    assert relevance(rungs[0].part_terms, "100K Ohm Resistor Pack of 10") == 0


def test_ic_reference_is_not_required_from_seller():
    spec = buyable_spec(
        BomItem(
            line_id="L01",
            raw_name="LM3915 (IC1)",
            buyable_spec=BuyableSpec(category="ic", queries=["LM3915 DIP IC"]),
        )
    )
    rungs = route_queries(spec, "LM3915 (IC1)", "LM3915 (IC1)")
    assert rungs[0] == "lm3915"
    assert all("ic1" not in q.lower() for q in rungs)
    assert relevance(rungs[0].part_terms, "LM3915 LED driver IC") == 1


def test_inferred_model_is_not_promoted_to_required_identity():
    spec = buyable_spec(
        BomItem(
            line_id="L01",
            raw_name="D1",
            buyable_spec=BuyableSpec(
                category="diode",
                params=[SpecParam(name="diode_type", value="1N4148", origin="inferred")],
                queries=["silicon diode"],
            ),
        )
    )
    assert spec.part_name == "diode"
