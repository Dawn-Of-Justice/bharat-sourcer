"""Synthetic names: battery hardware must survive generic duplicate cleanup."""

import pytest

from bharat_sourcer.fusion import fuse
from bharat_sourcer.schemas import BomItem


@pytest.mark.parametrize(
    "name",
    ["Battery retention foam or bracket", "Battery holder", "Battery charger", "Battery connector"],
)
def test_battery_accessories_are_not_the_cell(name):
    cell = BomItem(line_id="L01", raw_name="3.7V LiPo battery", qty=1, qty_source="stated")
    accessory = BomItem(line_id="L02", raw_name=name, qty=1, qty_source="inferred")
    result = fuse([[cell, accessory]])
    assert [item.raw_name for item in result] == [cell.raw_name, name]
