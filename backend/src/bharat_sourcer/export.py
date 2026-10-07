"""Redacted project views and CSV/printable HTML exports. Pure rendering; no I/O."""

import csv
import io
from datetime import datetime
from html import escape
from typing import Literal

from bharat_sourcer.schemas import (
    BomItem,
    Evidence,
    Job,
    Model,
    PartRequirement,
    ProjectContext,
    Report,
    ReportLine,
    Status,
    VerifiedOffer,
    now,
)
from bharat_sourcer.youtube_meta import apply_retention

SNAPSHOT_NOTICE = (
    "Prices, stock and compatibility are snapshots taken at each offer's checked_at time, "
    "copied from seller pages; they are not live quotes or verified seller facts. "
    "Tax and shipping are not included. Compatibility covers declared specifications only."
)
DEMO_NOTICE = "DEMO JOB: sample fixture data, not real extraction, sourcing or prices."


class SharedProject(Model):
    """Read-only, redacted project view for share links and exports.

    Excludes the job id, job token, owner identity, chat history, events, resistor
    advice and grounded-search attribution; nothing here grants access to the job.
    """

    shared: Literal[True] = True
    demo: bool
    status: Status
    source_url: str
    project: ProjectContext | None = None
    created_at: datetime
    updated_at: datetime
    items: list[BomItem]
    report: Report | None = None
    notice: str


def redact(job: Job) -> SharedProject:
    job = apply_retention(job.model_copy(deep=True))
    report = None
    if job.report:
        report = job.report.model_copy(deep=True)
        for line in report.lines:
            line.attribution = None
    return SharedProject(
        demo=job.demo,
        status=job.status,
        source_url=str(job.input.url),
        project=job.project.model_copy(deep=True) if job.project else None,
        created_at=job.created_at,
        updated_at=job.updated_at,
        items=[item.model_copy(deep=True) for item in job.items],
        report=report,
        notice=(DEMO_NOTICE + " " if job.demo else "") + SNAPSHOT_NOTICE,
    )


def lines(view: SharedProject) -> list[ReportLine]:
    """Report lines when a report exists; draft BOM items otherwise."""
    if view.report and view.report.lines:
        return view.report.lines
    return [
        ReportLine(item=item, sourcing_status="already_owned" if item.user_has_it else "not_run")
        for item in view.items
    ]


def selected(line: ReportLine) -> VerifiedOffer | None:
    if line.selected_offer_url is None:
        return None
    return next((o for o in line.offers if o.url == line.selected_offer_url), None)


def requirement_text(requirement: PartRequirement) -> str:
    operator = {"equals": "=", "at_least": ">=", "at_most": "<="}[requirement.operator]
    unit = f" {requirement.unit}" if requirement.unit else ""
    label = " (inferred)" if requirement.origin == "inferred" else ""
    return f"{requirement.name} {operator} {requirement.value}{unit}{label}"


def evidence_text(evidence: Evidence) -> str:
    if evidence.source == "video":
        return f"{evidence.timestamp} {evidence.observation}"
    return f'"{evidence.quote}" ({evidence.url})'


def data_label(view: SharedProject, line: ReportLine) -> str:
    if view.demo:
        return "demo_sample"
    if selected(line):
        return "seller_published_snapshot"
    return "no_selected_offer"


# Spreadsheet apps execute cells that start with these characters as formulas.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def cell(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


CSV_COLUMNS = [
    "data_label",
    "line_id",
    "part_name",
    "qty",
    "qty_unit",
    "qty_source",
    "qty_reason",
    "owned",
    "sourcing_status",
    "requirements",
    "offer_count",
    "selected_seller",
    "selected_offer_title",
    "selected_offer_url",
    "price_inr",
    "subtotal_inr",
    "stock",
    "checked_at",
    "compatibility_status",
    "compatibility_grade",
    "selection_grade",
    "evidence",
]


def to_csv(view: SharedProject) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")

    def row(values):
        writer.writerow([cell(value) for value in values])

    title = view.project.title if view.project else None
    if view.demo:
        row([f"# {DEMO_NOTICE}"])
    row([f"# {SNAPSHOT_NOTICE}"])
    row([f"# Project: {title or 'Untitled project'}"])
    row([f"# Source: {view.source_url}"])
    row([f"# Exported at: {now().isoformat()}"])
    row(CSV_COLUMNS)
    for line in lines(view):
        item, offer = line.item, selected(line)
        compat = offer.compatibility if offer else None
        row(
            [
                data_label(view, line),
                item.line_id,
                item.raw_name,
                item.qty,
                item.qty_unit,
                item.qty_source,
                item.qty_reason,
                "yes" if item.user_has_it else "no",
                line.sourcing_status,
                "; ".join(requirement_text(r) for r in item.requirements),
                len(line.offers),
                offer.seller if offer else None,
                offer.title if offer else None,
                offer.url if offer else None,
                line.price_inr,
                line.subtotal_inr,
                offer.stock if offer else None,
                offer.checked_at.isoformat() if offer else None,
                compat.status if compat else (offer.compatibility_status if offer else None),
                compat.grade if compat else None,
                line.grade,
                " | ".join(evidence_text(e) for e in item.evidence),
            ]
        )
    if view.report:
        row([])
        row(["# Selected parts subtotal INR", view.report.selected_parts_subtotal_inr])
        row(["# Unselected line ids", " ".join(view.report.unselected_line_ids)])
    return buffer.getvalue()


STYLE = """
body{font:14px/1.45 system-ui,sans-serif;color:#1a1a1a;background:#fff;margin:24px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:20px 0 8px}
.notice{border:1px solid #b45309;background:#fffbeb;padding:8px 12px;margin:12px 0}
.demo{border-color:#b91c1c;background:#fef2f2;font-weight:600}
.muted{color:#555}table{border-collapse:collapse;width:100%;font-size:12px}
th,td{border:1px solid #ccc;padding:4px 6px;text-align:left;vertical-align:top}
th{background:#f3f3f3}td.num{text-align:right;white-space:nowrap}
a{color:#1d4ed8;word-break:break-all}ul{margin:4px 0;padding-left:18px}
@media print{body{margin:0}a{color:#000}.noprint{display:none}
tr{break-inside:avoid}thead{display:table-header-group}}
@page{size:A4 landscape;margin:12mm}
"""


def link(url) -> str:
    # Values are validated http(s) URLs; still escape for the attribute context.
    value = escape(str(url), quote=True)
    return f'<a href="{value}" rel="noopener noreferrer nofollow">{value}</a>'


def to_html(view: SharedProject) -> str:
    e = escape
    title = (view.project.title if view.project else None) or "Untitled project"
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<meta name='referrer' content='no-referrer'>",
        f"<title>{e(title)} - Bharat Sourcer BOM</title><style>{STYLE}</style></head><body>",
        f"<h1>{e(title)}</h1>",
        f"<p class='muted'>Source: {link(view.source_url)}<br>Status: {e(view.status)}"
        f" &middot; Exported {e(now().strftime('%Y-%m-%d %H:%M UTC'))}</p>",
    ]
    if view.demo:
        parts.append(f"<div class='notice demo'>{e(DEMO_NOTICE)}</div>")
    parts.append(f"<div class='notice'>{e(SNAPSHOT_NOTICE)}</div>")
    parts.append("<p class='noprint muted'>Use your browser's Print command to save a PDF.</p>")
    if view.project:
        p = view.project
        parts.append("<h2>Project (AI-inferred, not verified)</h2>")
        if p.description:
            parts.append(f"<p>{e(p.description)}</p>")
        if p.summary:
            parts.append(f"<p class='muted'>{e(p.summary)}</p>")
        facts = [("Power", p.power), ("Controller", p.controller)]
        facts += [("Interfaces", ", ".join(p.interfaces) or None)]
        listed = [f"<li>{e(k)}: {e(v)}</li>" for k, v in facts if v]
        listed += [f"<li>Assumption: {e(a)}</li>" for a in p.assumptions]
        if listed:
            parts.append("<ul>" + "".join(listed) + "</ul>")
    parts.append(
        "<h2>Bill of materials</h2><table><thead><tr><th>#</th><th>Part</th><th>Qty</th>"
        "<th>Requirements</th><th>Selected offer</th><th>Price INR</th><th>Subtotal INR</th>"
        "<th>Stock / checked</th><th>Compatibility</th><th>Evidence</th></tr></thead><tbody>"
    )
    for line in lines(view):
        item, offer = line.item, selected(line)
        compat = offer.compatibility if offer else None
        qty = f"{e(str(item.qty or ''))} {e(item.qty_unit)}<br><span class='muted'>"
        qty += f"{e(item.qty_source)}</span>"
        if item.qty_reason:
            qty += f"<br><span class='muted'>{e(item.qty_reason)}</span>"
        name = e(item.raw_name) + (" <strong>(owned)</strong>" if item.user_has_it else "")
        name += f"<br><span class='muted'>{e(line.sourcing_status)}</span>"
        requirements = "".join(f"<li>{e(requirement_text(r))}</li>" for r in item.requirements)
        offer_cell = (
            f"{e(offer.seller)}<br>{e(offer.title)}<br>{link(offer.url)}"
            if offer
            else f"<span class='muted'>None selected ({len(line.offers)} offers)</span>"
        )
        stock = f"{e(offer.stock)}<br>{e(offer.checked_at.isoformat())}" if offer else ""
        status = compat.status if compat else (offer.compatibility_status if offer else "")
        grade = f" (grade {e(compat.grade)})" if compat and compat.grade else ""
        evidence = []
        for ev in item.evidence:
            if ev.source == "video":
                evidence.append(f"<li>{e(ev.timestamp or '')} {e(ev.observation)}</li>")
            else:
                evidence.append(f"<li>&ldquo;{e(ev.quote or '')}&rdquo; {link(ev.url)}</li>")
        parts.append(
            f"<tr><td>{e(item.line_id)}</td><td>{name}</td><td>{qty}</td>"
            f"<td><ul>{requirements}</ul></td><td>{offer_cell}</td>"
            f"<td class='num'>{e(line.price_inr or '')}</td>"
            f"<td class='num'>{e(line.subtotal_inr or '')}</td><td>{stock}</td>"
            f"<td>{e(status)}{grade}</td><td><ul>{''.join(evidence)}</ul></td></tr>"
        )
    parts.append("</tbody></table>")
    if view.report:
        parts.append(
            f"<p><strong>Selected parts subtotal: INR "
            f"{e(view.report.selected_parts_subtotal_inr)}</strong> (excludes tax and "
            "shipping)"
        )
        if view.report.unselected_line_ids:
            parts.append(
                f"<br><span class='muted'>No offer selected for: "
                f"{e(', '.join(view.report.unselected_line_ids))}</span>"
            )
        parts.append("</p>")
    parts.append("</body></html>")
    return "".join(parts)
