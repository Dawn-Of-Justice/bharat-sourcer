"""Synthetic regression fixtures; no network calls."""

from bharat_sourcer.costing import packs_for
from bharat_sourcer.recommend import apply_recommendations
from bharat_sourcer.schemas import (
    BomItem,
    BuyableSpec,
    Report,
    ReportLine,
    SpecParam,
    VerifiedOffer,
)
from bharat_sourcer.sourcing.offer_guards import fill_pack_quantity, pitch_conflict


def offer(title, **kwargs):
    return VerifiedOffer(
        url="https://seller.example/item",
        seller="fixture",
        title=title,
        price_inr="6.00",
        stock="in_stock",
        **kwargs,
    )


def spec():
    return BuyableSpec(
        origin="ai_inferred", category="connector",
        params=[SpecParam(name="pitch", value="2.54 mm", unit="m", si_value=0.00254)],
    )


def test_wrong_pitch_fallback_is_not_recommended():
    bad = offer("1x3 Pin 1.27mm Pin Headers")
    line = ReportLine(
        item=BomItem(line_id="L01", raw_name="header", buyable_spec=spec()),
        sourcing_status="offers_found",
        offers=[bad],
    )
    report = Report(demo=False, summary="Synthetic", lines=[line])
    apply_recommendations(report)
    assert bad.match.status == "mismatch"
    assert line.selected_offer_url is None
    assert line.recommended_offer_url is None


def test_correct_and_ambiguous_pitch():
    assert not pitch_conflict(spec(), offer("1x3 2.54mm pin header"))
    assert not pitch_conflict(spec(), offer("Header pitch 2.54mm, height 8mm"))
    assert not pitch_conflict(spec(), offer("Header 2mm x 8mm"))
    assert pitch_conflict(spec(), offer("1.27mm pin header"))


def test_pack_rounding_and_persistence():
    packed = offer("100 ohm resistor (Pack of 10)")
    assert packs_for(4, packed) == 1
    assert packs_for(11, packed) == 2
    fill_pack_quantity(packed)
    assert VerifiedOffer.model_validate_json(packed.model_dump_json()).pack_qty == 10


def test_variant_count_and_ambiguity():
    single = offer("Pack of 10 / individual variant", pack_qty=1)
    fill_pack_quantity(single)
    assert single.pack_qty == 1
    assert packs_for(4, single) == 4
    ambiguous = offer("Pack of 10 or pack of 20")
    fill_pack_quantity(ambiguous)
    assert ambiguous.pack_qty is None
