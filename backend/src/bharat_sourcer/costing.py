"""Compute quoted parts costs using decimal arithmetic; never infer landed costs."""

from decimal import Decimal

from bharat_sourcer.schemas import Report


def update_costs(report: Report) -> None:
    subtotal = Decimal("0.00")
    missing = []
    for line in report.lines:
        line.subtotal_inr = None
        if line.item.user_has_it:
            line.subtotal_inr = "0.00"
        elif line.selected_offer_url is not None and line.price_inr is not None:
            if line.item.qty is not None:
                amount = Decimal(line.price_inr) * line.item.qty
                line.subtotal_inr = f"{amount:.2f}"
                subtotal += amount
            else:
                missing.append(line.item.line_id)
        else:
            missing.append(line.item.line_id)
    report.unselected_line_ids = missing
    report.selected_parts_subtotal_inr = f"{subtotal:.2f}"
    report.parts_subtotal_inr = f"{subtotal:.2f}" if not missing and not report.demo else None
    report.total_inr = None
